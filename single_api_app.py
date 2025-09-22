import os
import uuid
import shutil
import zipstream

import add_watermark as aw

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from celery.result import AsyncResult
from celery import chord, group

from models import InputFileBatch
from celery_worker import celery_app


single_api_app = FastAPI()

# Mapping of extensions to handler functions
EXTENSION_HANDLERS = {
    "pdf": aw.add_watermark_to_pdf,
    "docx": aw.add_watermark_to_docx,
    "doc": aw.add_watermark_to_docx,
    "jpg": aw.add_watermark_to_image,
    "jpeg": aw.add_watermark_to_image,
    "png": aw.add_watermark_to_image,
    "rtf": aw.add_watermark_to_rtf,
    "csv": aw.add_watermark_to_csv,
    "svg": aw.add_watermark_to_svg,
    "pptx": aw.add_watermark_to_pptx,
    "ppt": aw.add_watermark_to_pptx,
}

def cleanup_file(file_path: str, zipped:bool):
    
    """
    Deletes a file.
    """
    
    try:
        directory = os.path.dirname(file_path)
        print(f"Directory to clean: {directory}")
        os.remove(file_path)
    except OSError as e:
        raise ValueError(f"Error deleting file {file_path}: {e}")

def add_watermark_batch(files:dict):
    
    """
    - Initiates watermarking for a list of files and zips the output.
    - Orchestrates PARALLEL watermarking for a batch of files using a Celery Chord.
    Params:
        - file_paths: List of file paths to be watermarked.
    Returns:
        - task_id: ID of the Celery task for tracking.
    """
    
    file_paths = files["file_paths"]
    source = files["source"]
    
    job_id = str(uuid.uuid4())
    output_dir = f"output/{job_id}"
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Create a group of parallel tasks, one for each file
    header = group(
        process_single_file.s(path, source, output_dir) for path in file_paths
    )

    # 2. Define the callback task that will zip the results
    callback = zip_and_cleanup.s(task_id=job_id)
    chord_result = chord(header)(callback)
    
    return {"message": "Batch watermarking and zipping initiated.", "task_id": chord_result.id}

@celery_app.task
def get_task_status(task_id: str):
    
    """
    Checks the status of a watermarking task.
    """
    
    try:
        task_result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "status": task_result.status,
        }

        if task_result.ready():
            if task_result.successful():
                response["result"] = "Processing complete. Proceed with download."
            else:
                response["result"] = str(task_result.info)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
def process_preprod_file(file_path, output_dir):
    
    """Handle watermarking for PREPROD files."""
    
    ext = file_path.lower().split('.')[-1]
    file_name = os.path.basename(file_path).split('.')[0]

    if ext == "csv":
        output_file = f"{file_name}-DRAFT.pdf"
    else:
        output_file = f"{file_name}-DRAFT.{ext}"

    output_path = os.path.join(output_dir, output_file)

    handler = EXTENSION_HANDLERS.get(ext)
    if handler:
        handler(file_path, output_path)  # Apply watermark
        return output_path
    return None

def process_prod_file(file_path, output_dir):
    
    """Handle copying for PROD files (no watermark)."""
    
    output_path = os.path.join(output_dir, os.path.basename(file_path))
    shutil.copy(file_path, output_path)
    return output_path

@celery_app.task
def process_single_file(file_path: str, source: str, output_dir: str) -> str:
    
    """
    Celery task to process ONE file. This will run in parallel for each file.
    """
    
    try:
        if source == "PREPROD":
            return process_preprod_file(file_path, output_dir)
        elif source == "PROD":
            return process_prod_file(file_path, output_dir)
        return None
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return None

@celery_app.task(bind=True)
def zip_and_cleanup(self, processed_files: list, task_id: str) -> tuple:
    """
    Celery task to zip results. This is the chord callback, running ONCE after all
    process_single_file tasks are complete.
    """
    valid_files = [path for path in processed_files if path]
    output_dir = f"output/{task_id}"

    if not valid_files:
        raise ValueError("No files were successfully processed.")

    # If only one file was successfully processed, return it directly without zipping
    if len(valid_files) == 1:
        return (valid_files[0], False)

    # Zip the processed files if there are multiple
    zip_output_path = f"output/{task_id}"
    shutil.make_archive(zip_output_path, "zip", output_dir)

    # Clean up the directory of individual processed files
    shutil.rmtree(output_dir)

    return (f"{zip_output_path}.zip", True)

@single_api_app.get("/download")
def download(files: InputFileBatch,background_tasks: BackgroundTasks):
    
    if not files.file_paths:
        raise HTTPException(status_code=400, detail="No file paths provided.")

    wrapper_result = add_watermark_batch(files.model_dump())
    task_id = wrapper_result["task_id"]

    task_result = AsyncResult(task_id, app=celery_app)
    while not task_result.ready():
        pass  # blocking for now (better: use status endpoint)

    if not task_result.successful():
        raise HTTPException(status_code=500, detail=f"Task failed: {task_result.info}")

    file_path, zipped = task_result.result

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found.")
    
    background_tasks.add_task(cleanup_file, file_path, zipped)

    if not zipped:
        file_name = os.path.basename(file_path)
        headers = {"Content-Disposition": f'attachment; filename="{file_name}"'}
        return FileResponse(path=file_path, headers=headers, media_type="application/octet-stream")

    file_name = "draft_files.zip"
    headers = {"Content-Disposition": f'attachment; filename="{file_name}"'}
    return FileResponse(path=file_path, headers=headers, media_type="application/zip")

@single_api_app.get("/download/stream")
async def download_zip_file_stream(task_id: str):
    
    """
    Streams the zipped file of watermarked documents.
    Params:
        - task_id: ID of the Celery task.
    Returns: Streaming Zip File
    """
    
    try:
        task_result = AsyncResult(task_id, app=celery_app)

        if not task_result.ready():
            raise HTTPException(status_code=404, detail="Task not yet completed.")
        
        if not task_result.successful():
            raise HTTPException(status_code=500, detail=f"Task failed: {task_result.info}")

        zip_file_path = task_result.result

        if not os.path.exists(zip_file_path):
            raise HTTPException(status_code=404, detail="File not found.")

        # Instead of loading file fully, stream it
        z = zipstream.ZipFile(mode="w", compression=zipstream.ZIP_DEFLATED)
        z.write(zip_file_path, arcname="draft_files.zip")

        headers = {"Content-Disposition": 'attachment; filename="draft_files.zip"'}
        return StreamingResponse(z, media_type="application/zip", headers=headers)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))