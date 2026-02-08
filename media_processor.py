"""
Media Processing module for AI Podcast Creator.
Handles image saving, audio processing, and subtitle creation.
"""

import re
from pathlib import Path
from typing import Optional
from PIL import Image
import io
from pydub import AudioSegment

from api_client import ScriptLine
from video_generator import FINAL_FFMPEG_PATH
import shutil
import os

# Configure pydub to use the detected FFmpeg/FFprobe path
# static-ffmpeg (imported in config.py) should have added them to PATH.
_ffmpeg_path = shutil.which("ffmpeg")
_ffprobe_path = shutil.which("ffprobe")

if _ffmpeg_path:
    AudioSegment.converter = _ffmpeg_path
    print(f"Pydub configured: ffmpeg={_ffmpeg_path}")
else:
    print("Pydub warning: ffmpeg not found in system PATH (even with static-ffmpeg).")

if _ffprobe_path:
    AudioSegment.ffprobe = _ffprobe_path
    print(f"Pydub configured: ffprobe={_ffprobe_path}")
else:
    print("Pydub warning: ffprobe not found in system PATH (even with static-ffmpeg).")

# DEBUG: Verify Paths
print(f"DEBUG: FINAL_FFMPEG_PATH: {FINAL_FFMPEG_PATH}")
print(f"DEBUG: AudioSegment.converter: {AudioSegment.converter}")
if AudioSegment.converter and os.path.exists(AudioSegment.converter):
    print(f"DEBUG: Converter executable exists at: {AudioSegment.converter}")
else:
    print(f"DEBUG: Converter executable NOT FOUND at: {AudioSegment.converter}")
    
def remove_bracketed_text(text: str) -> str:
    """
    Remove all [bracketed text] patterns from a string.

    Args:
        text: The input text string.

    Returns:
        Text with all [bracketed] patterns removed and cleaned up.
    """
    # Remove all [text] patterns
    cleaned = re.sub(r'\[.*?\]', '', text)
    # Clean up multiple spaces and trim
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def save_image(image_bytes: bytes, output_path: str) -> str:
    """
    Save image bytes to a file.

    Args:
        image_bytes: The image data as bytes.
        output_path: The path to save the image to.

    Returns:
        The absolute path to the saved image.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Try to open and re-save with PIL to ensure proper format
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.save(str(path), format="PNG")
    except Exception:
        # If PIL fails, just save the raw bytes
        with open(path, "wb") as f:
            f.write(image_bytes)

    return str(path.absolute())


def save_audio(audio_bytes: bytes, output_path: str) -> str:
    """
    Save audio bytes to a file.

    Args:
        audio_bytes: The audio data as bytes.
        output_path: The path to save the audio to.

    Returns:
        The absolute path to the saved audio.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        f.write(audio_bytes)
        f.flush()
        os.fsync(f.fileno())

    abs_path = str(path.absolute())
    print(f"DEBUG: Saved audio to: {abs_path} (Size: {len(audio_bytes)} bytes)")
    return abs_path


def get_audio_duration(audio_path: str) -> float:
    """
    Get the duration of an audio file in seconds using pydub.
    This ensures consistency with the concatenation process.

    Args:
        audio_path: Path to the audio file.

    Returns:
        Duration in seconds.
    """
    try:
        # Use pydub to check duration - this reads the actual audio data/header correctly
        # and handles various formats (wav, mp3, etc.) consistent with concatenation
        audio = AudioSegment.from_file(audio_path)
        return audio.duration_seconds
    except Exception as e:
        print(f"Error getting duration for {audio_path}: {e}")
        # Default fallback
        return 3.0


def format_time_srt(seconds: float) -> str:
    """
    Format time in SRT format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def create_subtitle_file(
    lines: list[ScriptLine],
    audio_durations: list[float],
    output_path: str
) -> str:
    """
    Create an SRT subtitle file from script lines.

    Args:
        lines: List of ScriptLine objects.
        audio_durations: List of audio durations for each line.
        output_path: Path to save the subtitle file.

    Returns:
        The absolute path to the saved subtitle file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    srt_content = []
    current_time = 0.0

    for i, (line, duration) in enumerate(zip(lines, audio_durations), 1):
        start_time = current_time
        end_time = current_time + duration

        # Clean content by removing [bracketed] text patterns
        cleaned_content = remove_bracketed_text(line.content)

        # Format the subtitle entry
        srt_entry = f"""{i}
{format_time_srt(start_time)} --> {format_time_srt(end_time)}
{line.character.name}: {cleaned_content}
"""
        srt_content.append(srt_entry)

        # Add delay between lines
        current_time = end_time + (line.delay_duration_ms / 1000.0)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_content))

    return str(path.absolute())


def resize_image_for_video(
    image_path: str,
    target_width: int,
    target_height: int,
    output_path: Optional[str] = None
) -> str:
    """
    Resize an image to fit the video dimensions.

    Args:
        image_path: Path to the source image.
        target_width: Target video width.
        target_height: Target video height.
        output_path: Optional output path (defaults to overwriting source).

    Returns:
        Path to the resized image.
    """
    if output_path is None:
        output_path = image_path

    with Image.open(image_path) as img:
        # Calculate scaling to cover the entire video frame
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # Image is wider, scale by height
            new_height = target_height
            new_width = int(img_ratio * target_height)
        else:
            # Image is taller, scale by width
            new_width = target_width
            new_height = int(target_width / img_ratio)

        # Resize
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        cropped = resized.crop((left, top, right, bottom))
        cropped.save(output_path, format="PNG")

    return output_path


def concatenate_audios(
    audio_paths: list[str],
    delays_ms: list[int],
    output_path: str
) -> str:
    """
    Concatenate multiple audio files with delays into a single file.
    
    Args:
        audio_paths: List of paths to audio files.
        delays_ms: List of delay durations in milliseconds (after each audio).
        output_path: Path to save the merged audio.
        
    Returns:
        Path to the merged audio file.
    """
    if not audio_paths:
        raise ValueError("No audio paths provided for concatenation")
    
    combined = AudioSegment.empty()
    
    for audio_path, delay in zip(audio_paths, delays_ms):
        print(f"DEBUG: Processing audio segment: {audio_path}")
        if not os.path.exists(audio_path):
             print(f"DEBUG: ERROR - File does not exist at {audio_path}")
             # Try absolute path resolution if relative
             abs_path = os.path.abspath(audio_path)
             if os.path.exists(abs_path):
                 print(f"DEBUG: Found at absolute path: {abs_path}")
                 audio_path = abs_path
             else:
                 print(f"DEBUG: Still not found at absolute path: {abs_path}")
        
        try:
            # Load audio - optimize for WAV to check format without external tools if possible
            if str(audio_path).lower().endswith(".wav"):
                try:
                     segment = AudioSegment.from_wav(audio_path)
                except Exception as wav_err:
                     print(f"Warning: Failed to load as WAV natively ({wav_err}), trying generic load...")
                     segment = AudioSegment.from_file(audio_path)
            else:
                segment = AudioSegment.from_file(audio_path)
            
            # Append audio
            combined += segment
            
            # Append silence (delay)
            if delay > 0:
                silence = AudioSegment.silent(duration=delay)
                combined += silence
                
        except Exception as e:
            print(f"Error processing audio {audio_path}: {e}")
            # Continue with other files/segments
            continue
            
    # Export merged file
    # Use config FFMPEG_PATH for pydub if needed? 
    # Pydub uses system ffmpeg typically. 
    # We export as wav which is standard.
    
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    combined.export(str(path), format="wav")
    
    return str(path.absolute())


if __name__ == "__main__":
    print("Media Processor module loaded successfully!")
