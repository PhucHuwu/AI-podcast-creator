"""
Video Generator module for AI Podcast Creator.
Handles video creation, segment concatenation, and subtitle embedding.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional

from config import (
    VideoFormat,
    VIDEO_SETTINGS,
    VIDEO_FPS,
    VIDEO_CODEC,
    AUDIO_CODEC,
    SUBTITLE_FONT,
    SUBTITLE_COLOR,
    SUBTITLE_STROKE_COLOR,
    SUBTITLE_STROKE_WIDTH,
    TEMP_DIR,
    FFMPEG_PATH,
    get_subtitle_font_size
)

# Determine the best FFmpeg path to use
# static-ffmpeg (imported in config.py) adds ffmpeg to PATH.
# We prefer the one in PATH.

if shutil.which("ffmpeg"):
    FINAL_FFMPEG_PATH = "ffmpeg"
else:
    FINAL_FFMPEG_PATH = FFMPEG_PATH or "ffmpeg"


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    return shutil.which(FINAL_FFMPEG_PATH) is not None


def check_gpu_support() -> bool:
    """
    Check if NVIDIA GPU encoding (nvenc) is available in FFmpeg.
    """
    try:
        # Check for h264_nvenc encoder support
        cmd = [FINAL_FFMPEG_PATH, "-encoders"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and "h264_nvenc" in result.stdout:
            print("NVIDIA GPU encoding (h264_nvenc) is available.")
            return True
        return False
    except Exception:
        return False


# Global variable to store GPU support status
HAS_GPU = check_gpu_support()


def create_video_segment(
    image_path: str,
    audio_path: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL,
    subtitle_path: Optional[str] = None
) -> str:
    """
    Create a video segment from an image and audio file.
    
    Args:
        image_path: Path to the image file.
        audio_path: Path to the audio file.
        output_path: Path for the output video segment.
        video_format: The video format (HORIZONTAL or VERTICAL).
        subtitle_path: Optional path to an SRT file to burn into this segment.
        
    Returns:
        Path to the created video segment.
    """
    settings = VIDEO_SETTINGS[video_format]
    width = settings["width"]
    height = settings["height"]
    
    # Determine codec and preset based on GPU support
    if HAS_GPU:
        video_codec = "h264_nvenc"
        preset = "p1"  # Fastest preset for NVENC (p1-p7 range)
        input_args = ["-hwaccel", "cuda"] # Try to use CUDA for input decoding if possible
    else:
        video_codec = VIDEO_CODEC  # Default from config (usually libx264)
        preset = "ultrafast"
        input_args = []
        
    # Spectrum bar dimensions
    spectrum_width = int(width * 0.5)  # 50% of video width
    spectrum_height = 100  # Height of spectrum bars
    
    # Complex filter for audio spectrum with mirrored bars
    # [0:v] = image input, [1:a] = audio input
    
    # Calculate spectrum position (center)
    spectrum_total_height = spectrum_height * 2
    spectrum_x = (width - spectrum_width) // 2
    spectrum_y = (height - spectrum_total_height) // 2
    
    filter_complex = (
        # Scale and pad the background image, add vignette
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"vignette=angle=PI/4,"
        # Draw semi-transparent black background for spectrum
        f"drawbox=x={spectrum_x}:y={spectrum_y}:w={spectrum_width}:h={spectrum_total_height}:color=black@0.5:t=fill[bg];"
        
        # Create audio waveform (white bars, fewer samples for cleaner look)
        f"[1:a]showwaves=s={spectrum_width}x{spectrum_height}:mode=line:n=1:colors=white:rate={VIDEO_FPS},"
        f"format=rgba[waves];"
        
        # Mirror the waveform vertically (flip and stack)
        f"[waves]split[w1][w2];"
        f"[w2]vflip[w2f];"
        f"[w1][w2f]vstack[spectrum];"
        
        # Overlay spectrum on video
        f"[bg][spectrum]overlay=(W-w)/2:(H-h)/2:eof_action=pass[outv_raw];"
    )
    
    final_map = "[outv_raw]"
    
    # Add subtitle filter if provided
    if subtitle_path:
        escaped_subtitle = subtitle_path.replace("\\", "/").replace(":", "\\:")
        font_size = get_subtitle_font_size(video_format)
        
        # Consistent subtitle styling
        subtitle_filter = (
            f"subtitles='{escaped_subtitle}':"
            f"force_style='FontName={SUBTITLE_FONT},"
            f"FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"BorderStyle=4,"
            f"Outline={SUBTITLE_STROKE_WIDTH},"
            f"Shadow=0,"
            f"Alignment=2,"
            f"MarginV=30'"
        )
        filter_complex += f"[outv_raw]{subtitle_filter}[outv]"
        final_map = "[outv]"
    else:
        # Just alias if no subtitles
        filter_complex = filter_complex.replace("[outv_raw];", "[outv]")
        final_map = "[outv]"
    
    # FFmpeg command
    cmd = [FINAL_FFMPEG_PATH, "-y"]
    
    # Add input args (hardware acceleration)
    cmd.extend(input_args)
    
    cmd.extend([
        "-loop", "1",  # Loop the image
        "-i", image_path,  # Input 0: image
        "-i", audio_path,  # Input 1: audio
        "-filter_complex", filter_complex,
        "-map", final_map,  # Use the filtered video
        "-map", "1:a",  # Use original audio
        "-c:v", video_codec,  # Video codec
        "-preset", preset,  # Encoding preset
        "-c:a", AUDIO_CODEC,  # Audio codec
        "-b:a", "192k",  # Audio bitrate
        "-pix_fmt", "yuv420p",  # Pixel format for compatibility
        "-shortest",  # End when audio ends
        "-r", str(VIDEO_FPS),  # Frame rate
        output_path
    ])
    
    msg = f"Processing segment: {Path(output_path).name} | GPU: {'ON' if HAS_GPU else 'OFF'} | Codec: {video_codec} | Preset: {preset}"
    print(msg, flush=True)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        error_msg = f"FFmpeg executable not found. Please install FFmpeg and ensure it's in your PATH. Command: {' '.join(cmd)}"
        print(f"ERROR: {error_msg}")
        raise RuntimeError(error_msg)
    except Exception as e:
        error_msg = f"Error executing FFmpeg: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise RuntimeError(error_msg)
    
    if result.returncode != 0:
        # If GPU encoding fails, fallback to CPU
        if HAS_GPU:
            print(f"GPU encoding failed for {output_path}, falling back to CPU...")
            return create_video_segment_cpu(image_path, audio_path, output_path, video_format)
            
        raise RuntimeError(f"FFmpeg error: {result.stderr}")
    
    return output_path


def create_video_segment_cpu(
    image_path: str,
    audio_path: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL
) -> str:
    """Fallback CPU implementation for create_video_segment."""
    settings = VIDEO_SETTINGS[video_format]
    width = settings["width"]
    height = settings["height"]
    spectrum_width = int(width * 0.5)
    spectrum_height = 100
    spectrum_total_height = spectrum_height * 2
    spectrum_x = (width - spectrum_width) // 2
    spectrum_y = (height - spectrum_total_height) // 2
    
    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"vignette=angle=PI/4,"
        f"drawbox=x={spectrum_x}:y={spectrum_y}:w={spectrum_width}:h={spectrum_total_height}:color=black@0.5:t=fill[bg];"
        f"[1:a]showwaves=s={spectrum_width}x{spectrum_height}:mode=line:n=1:colors=white:rate={VIDEO_FPS},"
        f"format=rgba[waves];"
        f"[waves]split[w1][w2];"
        f"[w2]vflip[w2f];"
        f"[w1][w2f]vstack[spectrum];"
        f"[bg][spectrum]overlay=(W-w)/2:(H-h)/2:eof_action=pass[outv]"
    )
    
    cmd = [
        FINAL_FFMPEG_PATH, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-filter_complex", filter_complex, "-map", "[outv]", "-map", "1:a",
        "-c:v", VIDEO_CODEC, "-preset", "ultrafast",
        "-c:a", AUDIO_CODEC, "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-shortest", "-r", str(VIDEO_FPS), output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg CPU fallback error: {result.stderr}")
    return output_path


def create_segment_list_file(segment_paths: list[str], output_path: str) -> str:
    """
    Create a file list for FFmpeg concat demuxer.
    
    Args:
        segment_paths: List of video segment file paths.
        output_path: Path for the list file.
        
    Returns:
        Path to the list file.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for segment in segment_paths:
            # Escape single quotes and use absolute path
            escaped_path = Path(segment).absolute().as_posix().replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
    
    return output_path


def concatenate_segments(
    segment_paths: list[str],
    output_path: str
) -> str:
    """
    Concatenate multiple video segments into one video.
    
    Args:
        segment_paths: List of video segment file paths.
        output_path: Path for the output video.
        
    Returns:
        Path to the concatenated video.
    """
    # Create temporary list file
    list_file = str(TEMP_DIR / "segments.txt")
    create_segment_list_file(segment_paths, list_file)
    
    # FFmpeg concat command
    cmd = [
        FINAL_FFMPEG_PATH,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",  # Copy streams without re-encoding
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat error: {result.stderr}")
    
    return output_path


def add_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL
) -> str:
    """
    Add subtitles to a video using FFmpeg.
    
    Args:
        video_path: Path to the input video.
        subtitle_path: Path to the SRT subtitle file.
        output_path: Path for the output video with subtitles.
        video_format: The video format for font size.
        
    Returns:
        Path to the output video.
    """
    # Escape the subtitle path for FFmpeg filter
    escaped_subtitle = subtitle_path.replace("\\", "/").replace(":", "\\:")
    
    # Get font size based on video format
    font_size = get_subtitle_font_size(video_format)
    
    # Subtitle filter with styling (black semi-transparent background)
    subtitle_filter = (
        f"subtitles='{escaped_subtitle}':"
        f"force_style='FontName={SUBTITLE_FONT},"
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"  # White text
        f"OutlineColour=&H00000000,"  # Black outline
        f"BackColour=&H80000000,"  # Semi-transparent black background
        f"BorderStyle=4,"  # 4 = opaque box behind text
        f"Outline={SUBTITLE_STROKE_WIDTH},"
        f"Shadow=0,"
        f"Alignment=2,"  # Bottom center
        f"MarginV=30'"
    )
    
    # Determine codec and preset based on GPU support
    if HAS_GPU:
        video_codec = "h264_nvenc"
        # Subtitles filter is complex, might need CPU decoding or specific handling,
        # but encoding can be GPU.
        # Note: burning subtitles requires decoding video frames.
        # If we use hwaccel for decoding, we need to handle format conversion for filters.
        # For simplicity/safety, we might let CPU decode (no -hwaccel) but GPU encode.
        preset = "p1"
    else:
        video_codec = VIDEO_CODEC
        preset = "ultrafast"

    cmd = [
        FINAL_FFMPEG_PATH,
        "-y",
        "-i", video_path,
        "-vf", subtitle_filter,
        "-c:a", "copy",  # Copy audio
        "-c:v", video_codec,
        "-preset", preset,
        "-pix_fmt", "yuv420p", # Ensure compatibility
        output_path
    ]
    
    msg = f"Adding subtitles: {Path(output_path).name} | Codec: {video_codec} | Preset: {preset}"
    print(msg, flush=True)

    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle error: {result.stderr}")
    
    return output_path


def add_subtitles_burn_in(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL
) -> str:
    """
    Burn subtitles directly into video (alternative method).
    
    Args:
        video_path: Path to the input video.
        subtitle_path: Path to the SRT subtitle file.
        output_path: Path for the output video with subtitles.
        video_format: The video format for font size.
        
    Returns:
        Path to the output video.
    """
    # Use drawtext for more reliable subtitle rendering
    # This reads the SRT and burns text directly
    
    # First, try the subtitles filter
    try:
        return add_subtitles(video_path, subtitle_path, output_path, video_format)
    except RuntimeError as e:
        # Fallback: just copy video without embedded subtitles
        # Keep the SRT file separate
        shutil.copy(video_path, output_path)
        print(f"Warning: Could not embed subtitles. Error: {e}")
        print(f"SRT file available at: {subtitle_path}")
        return output_path


def export_video(
    video_path: str,
    output_path: str,
    video_format: VideoFormat = VideoFormat.HORIZONTAL,
    include_subtitles: bool = False,
    subtitle_path: Optional[str] = None
) -> str:
    """
    Export the final video with optional subtitle embedding.
    
    Args:
        video_path: Path to the input video.
        output_path: Path for the final output video.
        video_format: The video format.
        include_subtitles: Whether to embed subtitles.
        subtitle_path: Path to the subtitle file (required if include_subtitles is True).
        
    Returns:
        Path to the final video.
    """
    if include_subtitles and subtitle_path:
        return add_subtitles_burn_in(video_path, subtitle_path, output_path, video_format)
    else:
        # Just copy the video
        shutil.copy(video_path, output_path)
        return output_path


def get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video file.
    
    Args:
        video_path: Path to the video file.
        
    Returns:
        Duration in seconds.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe error: {result.stderr}")
    
    return float(result.stdout.strip())


if __name__ == "__main__":
    print("Video Generator module loaded successfully!")
    
    if check_ffmpeg():
        print("FFmpeg is available.")
    else:
        print("WARNING: FFmpeg is not found. Please install FFmpeg to use this module.")
