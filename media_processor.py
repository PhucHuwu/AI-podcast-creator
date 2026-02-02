"""
Media Processing module for AI Podcast Creator.
Handles image saving, audio processing, and subtitle creation.
"""

import re
import struct
import wave
from pathlib import Path
from typing import Optional
from PIL import Image
import io

from api_client import ScriptLine


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

    return str(path.absolute())


def get_audio_duration(audio_path: str) -> float:
    """
    Get the duration of an audio file in seconds.

    Args:
        audio_path: Path to the audio file (WAV format).

    Returns:
        Duration in seconds.
    """
    try:
        with wave.open(audio_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)
            return duration
    except Exception:
        # If wave module fails, try to read manually
        with open(audio_path, 'rb') as f:
            # Read WAV header
            f.read(4)  # RIFF
            f.read(4)  # file size
            f.read(4)  # WAVE

            # Find fmt chunk
            while True:
                chunk_id = f.read(4)
                if not chunk_id:
                    break
                chunk_size = struct.unpack('<I', f.read(4))[0]

                if chunk_id == b'fmt ':
                    f.read(2)  # audio format
                    channels = struct.unpack('<H', f.read(2))[0]
                    sample_rate = struct.unpack('<I', f.read(4))[0]
                    f.read(chunk_size - 8)  # skip rest
                elif chunk_id == b'data':
                    data_size = chunk_size
                    # Calculate duration
                    bytes_per_sample = 2  # Assuming 16-bit
                    duration = data_size / (sample_rate * channels * bytes_per_sample)
                    return duration
                else:
                    f.read(chunk_size)

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


if __name__ == "__main__":
    print("Media Processor module loaded successfully!")
