from pydantic import BaseModel, Field
from typing import List, Literal

class InputFileBatch(BaseModel):
    file_paths: List[str] = Field(..., description="List of file paths to be watermarked")
    env: Literal['PROD', 'PREPROD'] = Field(..., description="Environment setting")

class Task(BaseModel):
    task_id: str = Field(..., description="Celery task ID for tracking watermarking status")
