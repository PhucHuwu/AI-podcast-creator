# AI Podcast Creator

A Python tool that automatically generates podcast videos from script data. It combines AI-generated images, audio files, and subtitles into a complete video.

## Features

- Fetches script data from API (characters, dialogues, audio paths)
- Generates photorealistic cover images using AI (Gemini 3 Pro)
- Downloads and processes audio files with multi-threading
- Creates video segments with FFmpeg
- Supports horizontal (16:9) and vertical (9:16) video formats
- Generates SRT subtitle files
- Docker support for containerized deployment
- Upload service with retry logic
- Auto-update script status after video generation

## Demo

https://github.com/user-attachments/assets/dcbf9700-89b7-4b91-aa4f-c39d4f1b4f1c

## Requirements

- Python 3.10+
- FFmpeg (auto-installed via `static-ffmpeg`)

## Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and configure your API keys:

```bash
cp .env.example .env
```

4. Edit `.env` with your settings:

```
# OpenAI Compatible API for image generation
OPENAI_API_URL=https://openai.matchive.io.vn/v1/chat/completions
OPENAI_API_KEY=your_openai_api_key_here

# Matchive API for script and audio
MATCHIVE_API_URL=https://api.matchive.io.vn
MATCHIVE_API_KEY=your_matchive_api_key_here

# Download configuration
MAX_DOWNLOAD_THREADS=3
MAX_VIDEO_THREADS=4

# Upload service configuration
UPLOAD_API_URL=https://api.matchive.io.vn/manager/media/upload-any
UPLOAD_MAX_RETRIES=3
UPLOAD_RETRY_DELAY=2
```

## Usage

### CLI Usage

```bash
# Horizontal video (YouTube/Facebook) - default
python main.py --script-id <SCRIPT_ID> --output podcast.mp4

# Vertical video (Shorts/Reels)
python main.py --script-id <SCRIPT_ID> --output podcast.mp4 --format vertical
```

### CLI Options

| Option             | Description                                    |
| ------------------ | ---------------------------------------------- |
| `--script-id`      | Required. The script ID to process             |
| `--output`         | Output video filename (default: podcast.mp4)   |
| `--format`         | Video format: `horizontal` or `vertical`       |
| `--skip-images`    | Use placeholder instead of AI-generated images |
| `--limit N`        | Process only first N lines (for testing)       |
| `--burn-subtitles` | Burn subtitles into video (slower)             |
| `--no-cleanup`     | Keep temporary files after processing          |

### Examples

```bash
# Quick test with 5 lines
python main.py --script-id 01KFR5ZNEXE1J936J9BRCHFZ4J --output test.mp4 --limit 5

# Full video with burned subtitles
python main.py --script-id 01KFR5ZNEXE1J936J9BRCHFZ4J --output podcast.mp4 --burn-subtitles

# Vertical video for Shorts/Reels
python main.py --script-id 01KFR5ZNEXE1J936J9BRCHFZ4J --output shorts.mp4 --format vertical
```

## API Usage (Service Mode)

Run as an HTTP API service for integration with other applications:

```bash
# Start the API server
python server.py

# Or with uvicorn directly
uvicorn api:app --host 0.0.0.0 --port 8000

# Development mode with auto-reload
uvicorn api:app --reload --port 8000
```

### API Endpoints

| Method | Endpoint                            | Description               |
| ------ | ----------------------------------- | ------------------------- |
| GET    | `/health`                           | Health check              |
| POST   | `/api/v1/videos`                    | Create video (async)      |
| GET    | `/api/v1/videos/{task_id}`          | Get task status           |
| GET    | `/api/v1/videos/{task_id}/download` | Download video            |
| GET    | `/api/v1/videos/{task_id}/subtitle` | Download subtitle         |
| GET    | `/api/v1/download?file={filename}`  | Download file by name     |
| GET    | `/api/v1/preview?file={filename}`   | Preview file (inline)     |
| DELETE | `/api/v1/files/{filename}`          | Delete video and subtitle |

### Example: Create Video

```bash
# Start video creation
curl -X POST http://localhost:8000/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{
    "script_id": "01KFR5ZNEXE1J936J9BRCHFZ4J",
    "video_format": "horizontal",
    "max_lines": 5
  }'

# Response: {"task_id": "abc-123", "message": "Video creation started"}

# Check status
curl http://localhost:8000/api/v1/videos/abc-123

# Download when completed
curl -o video.mp4 http://localhost:8000/api/v1/videos/abc-123/download
```

API documentation is available at `http://localhost:8000/docs` (Swagger UI).

## Docker Deployment

Build and run with Docker:

```bash
# Build image
docker build -t ai-podcast-creator .

# Run container
docker run -p 8000:8000 --env-file .env ai-podcast-creator
```

Or use Docker Compose:

```bash
docker-compose up -d
```

## Output

- Video file: `output/<filename>.mp4`
- Subtitle file: `output/<filename>.srt`

## Configuration

Edit `config.py` or use environment variables to customize:

| Variable              | Default | Description                     |
| --------------------- | ------- | ------------------------------- |
| `MAX_DOWNLOAD_THREADS`| 1       | Parallel audio download threads |
| `MAX_VIDEO_THREADS`   | 4       | Parallel video processing       |
| `SEGMENT_BATCH_SIZE`  | 50      | Lines per video segment         |
| `FFMPEG_PATH`         | ffmpeg  | Path to FFmpeg binary           |

### Video Settings

- Horizontal: 1920x1080 (16:9) - YouTube/Facebook
- Vertical: 1080x1920 (9:16) - Shorts/Reels
- FPS: 24
- Codec: H.264 (libx264) / AAC

## Project Structure

```
AI-podcast-creator/
├── main.py             # CLI entry point
├── api.py              # FastAPI server
├── server.py           # Server runner
├── schemas.py          # Pydantic models
├── config.py           # Configuration
├── api_client.py       # External API interactions
├── media_processor.py  # Image/Audio processing
├── video_generator.py  # Video creation with FFmpeg
├── upload_service.py   # Video upload with retry
├── requirements.txt    # Dependencies
├── Dockerfile          # Docker image config
├── docker-compose.yml  # Docker Compose config
├── .env.example        # Environment template
├── scripts/            # Helper scripts
│   └── setup.sh        # Setup and run script
├── temp/               # Temporary files (gitignored)
└── output/             # Generated videos (gitignored)
```

## Scripts

### Quick Setup and Run

```bash
./scripts/setup.sh
```

This script will:
1. Create/verify Python virtual environment
2. Install/update dependencies
3. Start the API server
