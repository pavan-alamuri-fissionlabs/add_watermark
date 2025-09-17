from pydantic import BaseModel, Field
from typing import List, Literal

class InputFileBatch(BaseModel):
    file_paths: List[str] = Field(..., description="List of file paths to be watermarked")
    source: Literal['PROD', 'PREPROD'] = Field(..., description="Environment setting")
