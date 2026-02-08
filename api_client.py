"""
API Client module for AI Podcast Creator.
Handles interactions with external APIs for script, image generation, and audio.
"""

import requests
import base64
import re
from dataclasses import dataclass
from typing import Optional
from config import (
    OPENAI_API_URL,
    OPENAI_API_KEY,
    MATCHIVE_API_URL,
    MATCHIVE_API_KEY,
    IMAGE_MODEL
)


@dataclass
class Character:
    """Represents a character in the script."""
    id: str
    name: str
    gender: str
    reference_audio_url: Optional[str] = None


@dataclass
class ScriptLine:
    """Represents a line in the script."""
    id: str
    script_id: str
    character: Character
    content: str
    visual_context: str
    audio_path: str
    delay_duration_ms: int
    start_time_ms: int = 0
    end_time_ms: int = 0


def get_script_lines(script_id: str) -> list[ScriptLine]:
    """
    Fetch all script lines from the API.
    
    Args:
        script_id: The ID of the script to fetch.
        
    Returns:
        List of ScriptLine objects.
    """
    url = f"{MATCHIVE_API_URL}/manager/lesson-manager/scripts/{script_id}/all-lines"
    headers = {
        "accept": "*/*",
        "Authorization": f"Apikey {MATCHIVE_API_KEY}"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    lines_data = data.get("data", [])
    
    script_lines = []
    for line in lines_data:
        char_data = line.get("character", {})
        character = Character(
            id=char_data.get("id", ""),
            name=char_data.get("name", ""),
            gender=char_data.get("gender", ""),
            reference_audio_url=char_data.get("referenceAudioUrl")
        )
        
        script_line = ScriptLine(
            id=line.get("id", ""),
            script_id=line.get("scriptId", ""),
            character=character,
            content=line.get("content", ""),
            visual_context=line.get("visualContext", ""),
            audio_path=line.get("audioPath", ""),
            delay_duration_ms=line.get("delayDurationMs", 0),
            start_time_ms=line.get("startTimeMs", 0),
            end_time_ms=line.get("endTimeMs", 0)
        )
        script_lines.append(script_line)
    
    return script_lines


def generate_image(prompt: str, style: str = "podcast illustration") -> bytes:
    """
    Generate an image using the AI model.
    
    Args:
        prompt: The visual context/description for the image.
        style: Additional style hints for the image.
        
    Returns:
        Image bytes (PNG format).
    """
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    # Create a detailed prompt for image generation
    full_prompt = f"Create a high-quality {style} image: {prompt}. Style: modern, clean, suitable for video podcast background."
    
    payload = {
        "stream": False,
        "model": IMAGE_MODEL,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "system",
                "content": "You are an AI that generates images. When asked to create an image, generate it and return the image."
            },
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    }
    
    response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    
    data = response.json()
    
    # Extract image from response
    # The response format may vary, handle common patterns
    choices = data.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        
        # Check for images field (Gemini format)
        images = message.get("images", [])
        if images:
            for img in images:
                if isinstance(img, dict) and img.get("type") == "image_url":
                    image_url = img.get("image_url", {}).get("url", "")
                    if image_url and image_url.startswith("data:image"):
                        base64_data = image_url.split(",")[1]
                        return base64.b64decode(base64_data)
        
        # Check content field
        content = message.get("content")
        
        if content:
            # Check if content contains base64 image data
            if isinstance(content, str) and ("base64" in content.lower() or content.startswith("data:image")):
                # Handle data URL format
                if content.startswith("data:image"):
                    base64_data = content.split(",")[1] if "," in content else content
                else:
                    # Try to extract base64 from the content
                    base64_match = re.search(r'[A-Za-z0-9+/=]{100,}', content)
                    if base64_match:
                        base64_data = base64_match.group()
                    else:
                        base64_data = content
                
                return base64.b64decode(base64_data)
            
            # Check for image_url in content (another common format)
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url and image_url.startswith("data:image"):
                            base64_data = image_url.split(",")[1]
                            return base64.b64decode(base64_data)
    
    raise ValueError("Could not extract image from API response")


def download_audio(audio_path: str, max_retries: int = 3, timeout: int = 120) -> bytes:
    """
    Download audio file from the API with retry logic.
    
    Args:
        audio_path: The path to the audio file (e.g., "generated_audio/xxx/yyy.wav")
        max_retries: Maximum number of retry attempts.
        timeout: Request timeout in seconds.
        
    Returns:
        Audio file bytes.
    """
    import time
    
    # URL encode the path
    encoded_path = requests.utils.quote(audio_path, safe="")
    url = f"{MATCHIVE_API_URL}/manager/media/download-by-path?filePath={encoded_path}&view=false"
    
    headers = {
        "Authorization": f"Apikey {MATCHIVE_API_KEY}"
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Read streaming content
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            return content
            
        except (requests.exceptions.HTTPError,
                requests.exceptions.ChunkedEncodingError, 
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
            continue
    
    raise last_error


def update_script_status(script_id: str, video_url: str, status: str = "WAIT_FOR_REVIEW") -> dict:
    """
    Update the script status and video URL on the backend.
    
    Args:
        script_id: The ID of the script.
        video_url: The URL of the uploaded video.
        status: The new status (default: "WAIT_FOR_REVIEW").
        
    Returns:
        API response JSON.
    """
    url = f"{MATCHIVE_API_URL}/manager/lesson-manager/scripts/{script_id}"
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
        "Authorization": f"Apikey {MATCHIVE_API_KEY}"
    }
    
    payload = {
        "videoUrl": video_url,
        "status": status
    }
    
    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    
    return response.json()


@dataclass
class ScriptInfo:
    """Represents script metadata."""
    id: str
    title: str
    lesson_title: str
    topic_title: str
    topic_type: str = "LONG"


def get_script_info(script_id: str) -> ScriptInfo:
    """
    Fetch script metadata including titles.
    
    Args:
        script_id: The ID of the script.
        
    Returns:
        ScriptInfo object.
    """
    url = f"{MATCHIVE_API_URL}/manager/lesson-manager/scripts/{script_id}"
    headers = {
        "accept": "*/*",
        "Authorization": f"Apikey {MATCHIVE_API_KEY}"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json().get("data", {})
    
    lesson = data.get("lesson", {})
    topic = lesson.get("topic", {})
    
    return ScriptInfo(
        id=data.get("id", ""),
        title=data.get("title", ""),
        lesson_title=lesson.get("title", ""),
        topic_title=topic.get("title", ""),
        topic_type=topic.get("topicType", "LONG")
    )


if __name__ == "__main__":
    # Test the API client
    import sys
    
    print("Testing API Client...")
    
    # Test get_script_lines
    test_script_id = "01KFR5ZNEXE1J936J9BRCHFZ4J"
    print(f"\nFetching script lines for: {test_script_id}")
    
    try:
        lines = get_script_lines(test_script_id)
        print(f"Found {len(lines)} lines")
        
        if lines:
            print(f"\nFirst line:")
            print(f"  Character: {lines[0].character.name}")
            print(f"  Content: {lines[0].content[:50]}...")
            print(f"  Visual Context: {lines[0].visual_context}")
            print(f"  Audio Path: {lines[0].audio_path}")
    except Exception as e:
        print(f"Error fetching script lines: {e}")
        sys.exit(1)
    
    print("\nAPI Client test completed successfully!")
