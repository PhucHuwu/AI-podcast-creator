"""
Upload service for uploading videos to external API.
Handles file uploads with retry logic and cleanup.
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Upload API configuration from environment variables
UPLOAD_API_URL = os.getenv("UPLOAD_API_URL", "https://api.matchive.io.vn/manager/media/upload-any")
MAX_RETRIES = int(os.getenv("UPLOAD_MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("UPLOAD_RETRY_DELAY", "2"))  # seconds


class UploadError(Exception):
    """Custom exception for upload errors."""
    pass


def upload_file_with_retry(
    file_path: str,
    max_retries: int = MAX_RETRIES,
    is_save: bool = False
) -> Tuple[bool, Optional[dict]]:
    """
    Upload a file to the external API with retry logic.
    
    Args:
        file_path: Path to the file to upload
        max_retries: Maximum number of retry attempts
        is_save: Whether to save the file on the server
        
    Returns:
        Tuple of (success: bool, response_data: dict or None)
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False, None
    
    file_name = os.path.basename(file_path)
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Uploading {file_name} (attempt {attempt}/{max_retries})...")
            
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f, 'application/octet-stream')}
                params = {'isSave': str(is_save).lower()}
                
                response = requests.post(
                    UPLOAD_API_URL,
                    files=files,
                    params=params,
                    headers={'accept': '*/*'},
                    timeout=900  # 15 minutes timeout
                )
                
                response.raise_for_status()
                
                logger.info(f"Upload successful: {file_name}")
                return True, response.json() if response.content else None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Upload attempt {attempt} failed: {str(e)}")
            
            if attempt < max_retries:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {max_retries} upload attempts failed for {file_name}")
                return False, None
        
        except Exception as e:
            logger.error(f"Unexpected error during upload: {str(e)}")
            return False, None
    
    return False, None


def cleanup_files(*file_paths: str) -> None:
    """
    Delete files to save disk space.
    
    Args:
        *file_paths: Variable number of file paths to delete
    """
    for file_path in file_paths:
        if not file_path:
            continue
            
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted file: {file_path}")
            else:
                logger.warning(f"File not found for cleanup: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")


def upload_and_cleanup(
    video_path: str,
    subtitle_path: Optional[str] = None,
    max_retries: int = MAX_RETRIES
) -> Tuple[bool, Optional[dict]]:
    """
    Upload video file and cleanup on success.
    
    Args:
        video_path: Path to the video file
        subtitle_path: Optional path to subtitle file
        max_retries: Maximum number of retry attempts
        
    Returns:
        Tuple of (success: bool, response_data: dict or None)
    """
    # Upload video
    success, response_data = upload_file_with_retry(
        video_path,
        max_retries=max_retries,
        is_save=False
    )
    
    if success:
        logger.info("Upload successful, cleaning up files...")
        # Cleanup video and subtitle files
        cleanup_files(video_path, subtitle_path)
    else:
        logger.warning("Upload failed, keeping files for manual retry")
    
    return success, response_data
