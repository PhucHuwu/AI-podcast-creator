"""
Pydantic schemas for FastAPI request/response models.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class VideoFormatEnum(str, Enum):
    """Video format options."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class TaskStatusEnum(str, Enum):
    """Task status options."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateVideoRequest(BaseModel):
    """Request model for creating a video."""
    script_id: str = Field(..., description="The script ID to process")
    video_format: VideoFormatEnum = Field(
        default=VideoFormatEnum.HORIZONTAL,
        description="Video format: horizontal (16:9) or vertical (9:16)"
    )
    skip_image_generation: bool = Field(
        default=False,
        description="Use placeholder instead of AI-generated images"
    )
    max_lines: int = Field(
        default=0,
        ge=0,
        description="Process only first N lines (0 = all lines)"
    )
    burn_subtitles: bool = Field(
        default=False,
        description="Burn subtitles into video"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "script_id": "01KFR5ZNEXE1J936J9BRCHFZ4J",
                    "video_format": "horizontal",
                    "skip_image_generation": False,
                    "max_lines": 0,
                    "burn_subtitles": False
                }
            ]
        }
    }


class CreateVideoResponse(BaseModel):
    """Response model for video creation request."""
    task_id: str = Field(..., description="Unique task identifier")
    message: str = Field(..., description="Status message")


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatusEnum = Field(..., description="Current task status")
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Progress percentage (0-100)"
    )
    message: Optional[str] = Field(
        default=None,
        description="Current step description"
    )
    video_url: Optional[str] = Field(
        default=None,
        description="URL to download video when completed"
    )
    subtitle_url: Optional[str] = Field(
        default=None,
        description="URL to download subtitle file when completed"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if task failed"
    )


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(default="healthy")


class ErrorResponse(BaseModel):
    """Response model for errors."""
    detail: str = Field(..., description="Error message")
