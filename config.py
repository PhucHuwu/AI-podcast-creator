"""
Configuration module for AI Podcast Creator.
Loads environment variables and defines video output settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from enum import Enum
import sys

# Import static_ffmpeg to ensure binaries are available
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
    print("static-ffmpeg: FFmpeg/FFprobe paths added to system PATH.")
except ImportError:
    print("static-ffmpeg not found. Please install it via 'pip install static-ffmpeg'.")

# Load environment variables from .env file
load_dotenv()

# API Configuration
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://openai.matchive.io.vn/v1/chat/completions")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MATCHIVE_API_URL = os.getenv("MATCHIVE_API_URL", "https://api.matchive.io.vn")
MATCHIVE_API_KEY = os.getenv("MATCHIVE_API_KEY", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# Video configuration
MAX_DOWNLOAD_THREADS = int(os.getenv("MAX_DOWNLOAD_THREADS", "1"))
MAX_VIDEO_THREADS = int(os.getenv("MAX_VIDEO_THREADS", "4"))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
SEGMENT_BATCH_SIZE = int(os.getenv("SEGMENT_BATCH_SIZE", "50"))

# Model configuration
IMAGE_MODEL = "gemini-3-pro-image-preview"


class VideoFormat(Enum):
    """Video format options."""
    HORIZONTAL = "horizontal"  # YouTube/Facebook: 1920x1080 (16:9)
    VERTICAL = "vertical"      # Shorts/Reels: 1080x1920 (9:16)


# Video output settings
VIDEO_SETTINGS = {
    VideoFormat.HORIZONTAL: {
        "width": 1920,
        "height": 1080,
        "aspect_ratio": "16:9",
        "description": "YouTube/Facebook",
        "subtitle_font_size": 20
    },
    VideoFormat.VERTICAL: {
        "width": 1080,
        "height": 1920,
        "aspect_ratio": "9:16",
        "description": "Shorts/Reels",
        "subtitle_font_size": 10
    }
}

# Default video settings
DEFAULT_VIDEO_FORMAT = VideoFormat.HORIZONTAL
VIDEO_FPS = 24
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

# Font settings for subtitles
SUBTITLE_FONT = "Arial"
SUBTITLE_COLOR = "white"
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 2

# Directories
BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

# Create directories if they don't exist
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def get_video_dimensions(format: VideoFormat) -> tuple[int, int]:
    """Get video dimensions for the specified format."""
    settings = VIDEO_SETTINGS[format]
    return settings["width"], settings["height"]


def get_subtitle_font_size(format: VideoFormat) -> int:
    """Get subtitle font size for the specified format."""
    return VIDEO_SETTINGS[format]["subtitle_font_size"]


def validate_config():
    """Validate that required configuration is set."""
    errors = []
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is not set")
    
    if not MATCHIVE_API_KEY:
        errors.append("MATCHIVE_API_KEY is not set")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(errors))
    
    return True
