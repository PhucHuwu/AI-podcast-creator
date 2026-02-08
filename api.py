"""
FastAPI application for AI Podcast Creator.
Provides HTTP API endpoints to create podcast videos from scripts.
"""

import uuid
from pathlib import Path
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import VideoFormat, OUTPUT_DIR, APP_BASE_URL, validate_config
from schemas import (
    CreateVideoRequest,
    CreateVideoResponse,
    TaskStatusResponse,
    TaskStatusEnum,
    VideoFormatEnum,
    HealthResponse,
    ErrorResponse
)
from main import create_podcast_video, cleanup_temp_files
from upload_service import upload_and_cleanup
from api_client import update_script_status


# In-memory task storage
tasks: Dict[str, dict] = {}


def process_video_task(task_id: str, request: CreateVideoRequest):
    """
    Background task to process video creation.
    Updates task status as it progresses.
    """
    try:
        tasks[task_id]["status"] = TaskStatusEnum.PROCESSING
        tasks[task_id]["progress"] = 10

        # Map video format
        video_format = (
            VideoFormat.VERTICAL
            if request.video_format == VideoFormatEnum.VERTICAL
            else VideoFormat.HORIZONTAL
        )

        # Generate output filename
        output_filename = f"{task_id}.mp4"
        output_path = str(OUTPUT_DIR / output_filename)

        tasks[task_id]["progress"] = 20

        # Progress callback
        def update_progress(progress: int, message: str):
            tasks[task_id]["progress"] = progress
            tasks[task_id]["message"] = message

        result_path = create_podcast_video(
            script_id=request.script_id,
            output_path=output_path,
            video_format=video_format,
            skip_image_generation=request.skip_image_generation,
            max_lines=request.max_lines,
            burn_subtitles=request.burn_subtitles,
            progress_callback=update_progress
        )

        tasks[task_id]["progress"] = 90

        # Set output paths
        tasks[task_id]["video_path"] = result_path

        # Check for subtitle file
        subtitle_path = result_path.replace(".mp4", ".srt")
        if Path(subtitle_path).exists():
            tasks[task_id]["subtitle_path"] = subtitle_path

        tasks[task_id]["status"] = TaskStatusEnum.COMPLETED
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "Video created, uploading..."

        tasks[task_id]["message"] = "Video created, updating status..."
        
        # Skip external upload and use local file
        # Check if file exists (it should, based on result_path)
        if Path(result_path).exists():
            # Construct local download URL (supports streaming/download)
            # output_filename was defined earlier as f"{task_id}.mp4"
            video_url = f"{APP_BASE_URL}/api/v1/download?file={output_filename}"
            tasks[task_id]["video_url"] = video_url
            
            try:
                update_script_status(request.script_id, video_url)
                tasks[task_id]["message"] = "Process completed successfully (Local)"
            except Exception as e:
                tasks[task_id]["message"] = f"Video created but failed to update status: {str(e)}"
                print(f"Error updating script status: {e}")
        else:
             tasks[task_id]["message"] = "Video creation reported success but file missing"
             tasks[task_id]["status"] = TaskStatusEnum.FAILED
             tasks[task_id]["upload_failed"] = True # reusing flag or create new error state

        # Cleanup temp files
        cleanup_temp_files()

    except Exception as e:
        tasks[task_id]["status"] = TaskStatusEnum.FAILED
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["progress"] = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: validate configuration
    try:
        validate_config()
        print("Configuration validated successfully")
    except ValueError as e:
        print(f"Warning: {e}")

    yield

    # Shutdown: cleanup
    print("Shutting down API server...")


app = FastAPI(
    title="AI Podcast Creator API",
    description="API service for creating podcast videos from scripts",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")


@app.post(
    "/api/v1/videos",
    response_model=CreateVideoResponse,
    responses={500: {"model": ErrorResponse}},
    tags=["Videos"]
)
async def create_video(
    request: CreateVideoRequest,
    background_tasks: BackgroundTasks
):
    """
    Create a new podcast video from a script.

    This endpoint starts video creation in the background and returns a task ID.
    Use the task ID to check the status and download the video when complete.
    """
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "status": TaskStatusEnum.PENDING,
        "progress": 0,
        "message": "Waiting to start",
        "video_path": None,
        "subtitle_path": None,
        "error": None,
        "request": request.model_dump()
    }

    # Start background processing
    background_tasks.add_task(process_video_task, task_id, request)

    return CreateVideoResponse(
        task_id=task_id,
        message="Video creation started"
    )


@app.get(
    "/api/v1/videos/{task_id}",
    response_model=TaskStatusResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Videos"]
)
async def get_task_status(task_id: str):
    """
    Get the status of a video creation task.

    Returns the current status, progress, and download URLs when complete.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    # Build response
    response = TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task.get("message"),
        error=task.get("error")
    )

    # Add download URLs if completed
    if task["status"] == TaskStatusEnum.COMPLETED:
        if task.get("video_path"):
            response.video_url = f"/api/v1/videos/{task_id}/download"
        if task.get("subtitle_path"):
            response.subtitle_url = f"/api/v1/videos/{task_id}/subtitle"

    return response


@app.get(
    "/api/v1/videos/{task_id}/download",
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse}
    },
    tags=["Videos"]
)
async def download_video(task_id: str):
    """
    Download the completed video file.

    Only available after the task status is 'completed'.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    if task["status"] != TaskStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Current status: {task['status'].value}"
        )

    video_path = task.get("video_path")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"podcast_{task_id}.mp4"
    )


@app.get(
    "/api/v1/videos/{task_id}/subtitle",
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse}
    },
    tags=["Videos"]
)
async def download_subtitle(task_id: str):
    """
    Download the subtitle file for the completed video.

    Only available after the task status is 'completed'.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    if task["status"] != TaskStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Subtitle not ready. Current status: {task['status'].value}"
        )

    subtitle_path = task.get("subtitle_path")
    if not subtitle_path or not Path(subtitle_path).exists():
        raise HTTPException(status_code=404, detail="Subtitle file not found")

    return FileResponse(
        subtitle_path,
        media_type="text/plain",
        filename=f"podcast_{task_id}.srt"
    )


@app.get(
    "/api/v1/download",
    tags=["Videos"],
    summary="Download video file by name"
)
async def download_file_by_name(file: str):
    """
    Download video content by filename from the output directory.
    
    Args:
        file: The filename of the video (e.g., "task_id.mp4").
    """
    import os
    
    # Sanitize filename (simple check to prevent directory traversal)
    if ".." in file or "/" in file or "\\" in file:
         raise HTTPException(status_code=400, detail="Invalid filename")
         
    video_path = OUTPUT_DIR / file
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
        
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=file 
        , content_disposition_type="attachment"
    )



@app.get(
    "/api/v1/preview",
    tags=["Videos"],
    summary="Preview video file by name"
)
async def preview_file_by_name(file: str):
    """
    Preview video content by filename from the output directory.
    
    Args:
        file: The filename of the video (e.g., "task_id.mp4").
    """
    # Sanitize filename (simple check to prevent directory traversal)
    if ".." in file or "/" in file or "\\" in file:
         raise HTTPException(status_code=400, detail="Invalid filename")
         
    video_path = OUTPUT_DIR / file
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
        
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=file,
        content_disposition_type="inline"
    )


@app.delete(
    "/api/v1/files/{filename}",
    tags=["Management"],
    summary="Delete video and subtitle files"
)
async def delete_file(filename: str):
    """
    Delete a video file and its corresponding subtitle file.
    
    Args:
        filename: The name of the video file to delete (e.g., "7a02...mp4").
    """
    import os
    
    # Sanitize filename
    if ".." in filename or "/" in filename or "\\" in filename:
         raise HTTPException(status_code=400, detail="Invalid filename")
    
    deleted_files = []
    errors = []
    
    # Paths to potential files
    video_path = OUTPUT_DIR / filename
    
    # Verify it is a file inside output dir
    if not str(video_path.absolute()).startswith(str(OUTPUT_DIR.absolute())):
        raise HTTPException(status_code=400, detail="Invalid file path")
        
    # Delete video
    if video_path.exists():
        try:
            os.remove(video_path)
            deleted_files.append(filename)
        except Exception as e:
            errors.append(f"Failed to delete video: {str(e)}")
            
    # Check for subtitle (replace extension)
    # Assuming standard pattern: video.mp4 -> video.srt
    stem = video_path.stem
    subtitle_filename = f"{stem}.srt"
    subtitle_path = OUTPUT_DIR / subtitle_filename
    
    if subtitle_path.exists():
        try:
             os.remove(subtitle_path)
             deleted_files.append(subtitle_filename)
        except Exception as e:
             errors.append(f"Failed to delete subtitle: {str(e)}")
             
    if not deleted_files and not errors:
        return {"message": "File not found", "deleted": []}
        
    return {
        "message": "Cleanup operation completed",
        "deleted": deleted_files,
        "errors": errors
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
