"""
AI Podcast Creator - Main Script

This tool creates podcast videos from script data, combining:
- AI-generated images (from visual context)
- Audio files (downloaded from API)
- Subtitles/CC (from script content)

Usage:
    python main.py --script-id <SCRIPT_ID> --output <OUTPUT_FILE> [--format vertical|horizontal]
"""

import argparse
import sys
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    VideoFormat,
    TEMP_DIR,
    OUTPUT_DIR,
    MAX_DOWNLOAD_THREADS,
    MAX_VIDEO_THREADS,
    SEGMENT_BATCH_SIZE,
    get_video_dimensions,
    validate_config
)
from api_client import get_script_lines, generate_image, download_audio, get_script_info
from media_processor import (
    save_image,
    save_audio,
    get_audio_duration,
    create_subtitle_file,
    resize_image_for_video,
    concatenate_audios
)
from video_generator import (
    check_ffmpeg,
    create_video_segment,
    concatenate_segments,
    export_video
)


def cleanup_temp_files():
    """Remove all temporary files."""
    if TEMP_DIR.exists():
        for item in TEMP_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)


def create_podcast_video(
    script_id: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL,
    skip_image_generation: bool = False,
    max_lines: int = 0,
    burn_subtitles: bool = False,
    progress_callback: callable = None
) -> str:
    """
    Create a podcast video from a script.

    Args:
        script_id: The ID of the script to process.
        output_path: Path for the output video file.
        video_format: Video format (HORIZONTAL or VERTICAL).
        skip_image_generation: If True, use placeholder images instead of AI generation.

    Returns:
        Path to the created video file.
    """
    print(f"Starting podcast video creation for script: {script_id}")
    print(f"Output format: {video_format.value}")

    # Get video dimensions
    width, height = get_video_dimensions(video_format)
    print(f"Video dimensions: {width}x{height}")

    # Helper to update progress
    def update_progress(step: int, message: str):
        if progress_callback:
            # Steps: 1=Fetch(5%), 2=Audio(25%), 3=Image(40%), 4=Subtitles(45%), 5=Segments(85%), 6=Export(100%)
            progress_map = {1: 5, 2: 25, 3: 40, 4: 45, 5: 85, 6: 100}
            progress_callback(progress_map.get(step, 0), message)

    # Step 1: Fetch script lines
    print("\n[1/6] Fetching script lines...")
    update_progress(1, "Fetching script lines")
    all_lines = get_script_lines(script_id)
    print(f"Found {len(all_lines)} lines")

    if not all_lines:
        raise ValueError("No script lines found")

    # Filter out lines without audio_path
    lines = [line for line in all_lines if line.audio_path]
    skipped = len(all_lines) - len(lines)
    if skipped > 0:
        print(f"Skipped {skipped} lines without audio")
    
    if not lines:
        raise ValueError("No lines with audio found")

    # Limit lines if specified
    if max_lines > 0:
        lines = lines[:max_lines]
        print(f"Limited to {len(lines)} lines")

    # Prepare temp directories
    images_dir = TEMP_DIR / "images"
    audio_dir = TEMP_DIR / "audio"
    segments_dir = TEMP_DIR / "segments"

    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Download audio files (sequential to avoid backend overload)
    print("\n[2/6] Downloading audio files...")
    update_progress(2, "Downloading audio files")

    def download_single_audio(args):
        """Download a single audio file. Returns (index, audio_path, duration)."""
        import sys
        import os
        from urllib.parse import urlparse, unquote
        
        i, line, audio_dir = args
        
        if not line.audio_path:
             raise ValueError(f"Audio path is empty for line {i+1}")
             
        # Extract filename from URL
        parsed_url = urlparse(line.audio_path)
        filename = os.path.basename(unquote(parsed_url.path))
        if not filename or filename == ".":
             filename = f"audio_{i:03d}.wav" # Fallback
             
        # Sanitize filename
        filename = "".join(x for x in filename if x.isalnum() or x in "._- ")
        audio_file = str(audio_dir / filename)
        
        # Check if file exists in cache (temp/audio)
        if os.path.exists(audio_file):
             print(f"  Using cached audio {i+1}/{len(lines)}: '{filename}'", flush=True)
             try:
                 duration = get_audio_duration(audio_file)
                 return (i, audio_file, duration)
             except Exception as e:
                 print(f"  Warning: Cached file {filename} invalid ({e}), re-downloading...", flush=True)
                 # Fall through to download
        
        print(f"  Downloading audio {i+1}/{len(lines)}: '{line.audio_path}' -> '{filename}'", flush=True)
        
        audio_bytes = download_audio(line.audio_path)
        save_audio(audio_bytes, audio_file)
        duration = get_audio_duration(audio_file)
        print(f"  Completed audio {i+1}/{len(lines)}: '{filename}' ({duration:.2f}s)", flush=True)
        return (i, audio_file, duration)

    # Prepare download tasks
    download_tasks = [(i, line, audio_dir) for i, line in enumerate(lines)]

    # Download with configured thread pool
    results = [None] * len(lines)
    print(f"Run download_single_audio with {MAX_DOWNLOAD_THREADS} threads")
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_THREADS) as executor:
        futures = {executor.submit(download_single_audio, task): task[0] for task in download_tasks}

        for future in as_completed(futures):
            idx, audio_file, duration = future.result()
            results[idx] = (audio_file, duration)

    # Extract results in correct order
    audio_paths = [r[0] for r in results]
    audio_durations = [r[1] for r in results]

    # Step 3: Generate single image for entire video
    print("\n[3/6] Generating cover image...")
    update_progress(3, "Generating cover image")
    cover_image_file = str(images_dir / "cover.png")

    # Extract unique characters and their info
    unique_characters = {}
    for line in lines:
        char_id = line.character.id
        if char_id not in unique_characters:
            unique_characters[char_id] = {
                "name": line.character.name,
                "gender": line.character.gender
            }

    # Build character description
    num_people = len(unique_characters)
    male_count = sum(1 for c in unique_characters.values() if c["gender"].upper() == "MALE")
    female_count = sum(1 for c in unique_characters.values() if c["gender"].upper() == "FEMALE")

    # Build gender description
    if male_count > 0 and female_count > 0:
        gender_desc = f"{male_count} man/men and {female_count} woman/women"
    elif male_count > 0:
        gender_desc = f"{male_count} man/men"
    else:
        gender_desc = f"{female_count} woman/women"

    # Get character names
    char_names = [c["name"] for c in unique_characters.values()]

    # Determine aspect ratio for image
    if video_format == VideoFormat.VERTICAL:
        aspect_desc = "vertical portrait orientation (9:16 aspect ratio)"
        composition = "The people are arranged vertically (one above the other), close-up faces stacked in portrait layout"
    else:
        aspect_desc = "horizontal landscape orientation (16:9 aspect ratio)"
        composition = "The people are sitting side by side in a wide shot"

    # Build realistic image prompt
    
    # Fetch script info for context
    try:
        script_info = get_script_info(script_id)
        # Use default if topic_type is missing or empty
        topic_type = script_info.topic_type if script_info.topic_type else "LONG"
        topic_context = f"Topic: {script_info.topic_title}. Lesson: {script_info.lesson_title}. Script: {script_info.title}."
        print(f"  Using script context: {topic_context} (Type: {topic_type})")
    except Exception as e:
        print(f"  Warning: Failed to fetch script info ({e}), proceeding without specific context")
        topic_context = ""
        topic_type = "LONG"

    if topic_type == "SHORT":
         # Short video prompt: Situation-based, 2 characters, background relevant to context
         image_prompt = (
            f"A photorealistic image of a specific situation: {topic_context} "
            f"Two characters (1 male, 1 female) interacting naturally in a suitable background. "
            f"Cinematic lighting, {aspect_desc}, high quality, 4K, realistic human faces and expressions. "
            f"The atmosphere is friendly and engaging. "
             f"Names: {', '.join(char_names)}."
         )
         print(f"  Using SHORT format prompt")
    else:
        # Long video prompt: Podcast studio (Default)
        image_prompt = (
            f"A photorealistic image in {aspect_desc} of {num_people} people ({gender_desc}) having a podcast conversation. "
            f"{composition}. Modern podcast studio with microphones. "
            f"Context: {topic_context} "
            f"Professional lighting, high quality, 4K, realistic human faces and expressions. "
            f"The atmosphere is friendly and engaging. "
            f"Names: {', '.join(char_names)}."
        )
        print(f"  Using LONG format prompt")

    print(f"  Characters: {num_people} people ({gender_desc})")
    print(f"  Names: {', '.join(char_names)}")

    if skip_image_generation:
        # Create a placeholder image
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)

        # Add text
        text = f"Podcast: {num_people} people ({gender_desc})"
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()

        # Center the text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        img.save(cover_image_file)
        print(f"  Created placeholder cover image")
    else:
        # Determine style based on topic type
        if topic_type == "SHORT":
            image_style = "cinematic photorealistic"
        else:
            image_style = "photorealistic podcast studio"

        print(f"  Generating realistic image (Style: {image_style})...")
        try:
            image_bytes = generate_image(image_prompt, style=image_style)
            save_image(image_bytes, cover_image_file)

            # Resize to fit video dimensions
            resize_image_for_video(cover_image_file, width, height)
            print(f"  Cover image generated successfully")
        except Exception as e:
            print(f"  Warning: Image generation failed ({e}), using placeholder")
            # Create placeholder on failure
            from PIL import Image
            img = Image.new('RGB', (width, height), color=(30, 30, 30))
            img.save(cover_image_file)

    # Use the same image for all segments
    image_paths = [cover_image_file] * len(lines)

    # Step 4: Create subtitle file
    print("\n[4/6] Creating subtitles...")
    update_progress(4, "Creating subtitles")
    subtitle_file = str(TEMP_DIR / "subtitles.srt")
    create_subtitle_file(lines, audio_durations, subtitle_file)
    print(f"  Subtitle file created: {subtitle_file}")

    # Step 5: Create video segments (batched)
    num_batches = (len(lines) + SEGMENT_BATCH_SIZE - 1) // SEGMENT_BATCH_SIZE
    print(f"\n[5/6] Creating video segments ({num_batches} batches, size {SEGMENT_BATCH_SIZE}, {MAX_VIDEO_THREADS} threads)...")
    update_progress(5, "Creating video segments")

    def create_batch_segment(args):
        """Create a single video segment from a batch of lines."""
        batch_idx, batch_lines, batch_audio_paths, batch_delays, batch_durations, segments_dir, video_format, cover_image, burn_subs = args
        print(f"  Processing batch {batch_idx+1}/{num_batches} ({len(batch_lines)} lines)...", flush=True)
        
        # Merge audios for this batch
        merged_audio_path = str(segments_dir / f"batch_{batch_idx:03d}_audio.wav")
        try:
             concatenate_audios(batch_audio_paths, batch_delays, merged_audio_path)
        except Exception as e:
             raise RuntimeError(f"Failed to merge audio for batch {batch_idx}: {e}")
        
        # Create subtitle file for this batch if needed
        batch_subtitle_path = None
        if burn_subs:
             sub_file = str(segments_dir / f"batch_{batch_idx:03d}_subs.srt")
             create_subtitle_file(batch_lines, batch_durations, sub_file)
             batch_subtitle_path = sub_file

        # Create video segment
        segment_file = str(segments_dir / f"segment_{batch_idx:03d}.mp4")
        create_video_segment(
            image_path=cover_image,
            audio_path=merged_audio_path,
            output_path=segment_file,
            video_format=video_format,
            subtitle_path=batch_subtitle_path
        )
        print(f"  Completed batch {batch_idx+1}/{num_batches}", flush=True)
        return (batch_idx, segment_file)

    # Prepare batch tasks
    batch_tasks = []
    for i in range(0, len(lines), SEGMENT_BATCH_SIZE):
        batch_lines = lines[i : i + SEGMENT_BATCH_SIZE]
        batch_audio_paths = audio_paths[i : i + SEGMENT_BATCH_SIZE]
        # Get delays (convert ms to int)
        batch_delays = [int(line.delay_duration_ms) for line in batch_lines]
        # Get durations (for subtitles)
        batch_durations = audio_durations[i : i + SEGMENT_BATCH_SIZE]
        
        batch_idx = i // SEGMENT_BATCH_SIZE
        
        task = (
            batch_idx,
            batch_lines,
            batch_audio_paths,
            batch_delays,
            batch_durations,
            segments_dir,
            video_format,
            cover_image_file,
            burn_subtitles
        )
        batch_tasks.append(task)

    # Create segments with configured thread pool
    batch_results = [None] * num_batches
    with ThreadPoolExecutor(max_workers=MAX_VIDEO_THREADS) as executor:
        futures = {executor.submit(create_batch_segment, task): task[0] for task in batch_tasks}

        for future in as_completed(futures):
            idx, segment_file = future.result()
            batch_results[idx] = segment_file

    # Extract segment paths in correct order
    segment_paths = batch_results

    # Step 6: Concatenate and export
    print("\n[6/6] Concatenating and exporting final video...")
    update_progress(6, "Exporting final video")

    # Concatenate segments
    merged_video = str(TEMP_DIR / "merged.mp4")
    concatenate_segments(segment_paths, merged_video)

    # Export with subtitles
    output_file = Path(output_path)
    if not output_file.is_absolute():
        output_file = OUTPUT_DIR / output_file

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Note: If burn_subtitles is True, we already burned them into the segments.
    # So we don't need to burn them again in the final export, but we might still want
    # to pass the API updated logic.
    # However, export_video function handles 'include_subtitles=True' by burning them.
    # We should set include_subtitles=False here if we already burned them per-segment.
    
    export_video(
        video_path=merged_video,
        output_path=str(output_file),
        video_format=video_format,
        include_subtitles=False, # Already burned in segments if requested
        subtitle_path=subtitle_file
    )

    print(f"\nVideo created successfully: {output_file}")

    # Copy subtitle file to output location
    subtitle_output = output_file.with_suffix('.srt')
    shutil.copy(subtitle_file, subtitle_output)
    print(f"Subtitle file: {subtitle_output}")

    return str(output_file)


def main():
    parser = argparse.ArgumentParser(
        description="AI Podcast Creator - Create podcast videos from scripts"
    )
    parser.add_argument(
        "--script-id",
        required=True,
        help="The ID of the script to process"
    )
    parser.add_argument(
        "--output",
        default="podcast.mp4",
        help="Output video file path (default: podcast.mp4)"
    )
    parser.add_argument(
        "--format",
        choices=["horizontal", "vertical"],
        default="horizontal",
        help="Video format: horizontal (16:9) or vertical (9:16)"
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip AI image generation and use placeholders"
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't cleanup temporary files after completion"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of lines to process (0 = no limit)"
    )
    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn subtitles into video (slower, but subtitle visible without player support)"
    )

    args = parser.parse_args()

    # Validate configuration
    try:
        validate_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease ensure your .env file is properly configured.")
        sys.exit(1)

    # Check FFmpeg
    if not check_ffmpeg():
        print("Error: FFmpeg is not installed or not in PATH.")
        print("Please install FFmpeg to use this tool.")
        sys.exit(1)

    # Determine video format
    video_format = VideoFormat.HORIZONTAL if args.format == "horizontal" else VideoFormat.VERTICAL

    try:
        # Create the video
        output_path = create_podcast_video(
            script_id=args.script_id,
            output_path=args.output,
            video_format=video_format,
            skip_image_generation=args.skip_images,
            max_lines=args.limit,
            burn_subtitles=args.burn_subtitles
        )

        print(f"\nSuccess! Your podcast video is ready: {output_path}")

    except Exception as e:
        print(f"\nError creating video: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if not args.no_cleanup:
            print("\nCleaning up temporary files...")
            cleanup_temp_files()


if __name__ == "__main__":
    main()
