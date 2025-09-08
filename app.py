import os
import uuid
import shutil

from typing import List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from celery.result import AsyncResult

from add_watermark import add_watermark_to_pdf, add_watermark_to_image, add_watermark_to_docx, add_watermark_to_rtf
from models import InputFileBatch
from celery_worker import celery_app


app = FastAPI()

@app.post("/watermark/batch/")
def add_watermark_batch(files: InputFileBatch):
    
    """
    Initiates watermarking for a list of files and zips the output.
    Params:
        - file_paths: List of file paths to be watermarked.
    Returns:
        - task_id: ID of the Celery task for tracking.
    """
    
    if not files.file_paths:
        raise HTTPException(status_code=400, detail="No file paths provided.")
    task = add_watermark_to_files_and_zip.delay(files.file_paths, files.env)
    return {"message": "Batch watermarking and zipping initiated.", "task_id": task.id}

@app.get("/status/")
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
                response["result"] = "Processing complete. Please use the download link."
                response["download_url"] = f"/download/{task_id}"
            else:
                response["result"] = str(task_result.info)  # Get exception info
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/")
def download_zip_file(task_id: str, background_tasks: BackgroundTasks):
    
    """
    Downloads the zipped file of watermarked documents.
    Params:
        - task_id: ID of the Celery task.
    Returns: Zip File
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

        file_name = "draft_files.zip"
        headers = {
            'Content-Disposition': f'attachment; filename="{file_name}"'
        }
        
        background_tasks.add_task(cleanup_file, zip_file_path)

        return FileResponse(
            path=zip_file_path, 
            headers=headers, 
            media_type='application/zip'
        )


    except Exception as e:
        raise e

@celery_app.task
def add_watermark_to_files_and_zip(file_paths, env):
    
    """
    Celery task to watermark a list of files and zip them.
    Params:
        - file_paths: List of file paths to be watermarked.
    Returns:
        - Path to the zipped output file or Zipped file.
    """
    if env == 'PREPROD':
        job_id = str(uuid.uuid4())
        output_dir = f"output/{job_id}"
        os.makedirs(output_dir, exist_ok=True)

        processed_files = []

        for file_path in file_paths:
            try:
                ext = file_path.lower().split('.')[-1]
                file_name = os.path.basename(file_path).split('.')[0] + f"-DRAFT.{ext}"
                output_path = os.path.join(output_dir, file_name)

                if ext == "pdf":
                    add_watermark_to_pdf(file_path, output_path)
                elif ext in ["docx", "doc"]:
                    add_watermark_to_docx(file_path, output_path)
                elif ext in ["jpg", "jpeg", "png"]:
                    add_watermark_to_image(file_path, output_path)
                elif ext == "rtf":
                    add_watermark_to_rtf(file_path, output_path)
                else:
                    # Skip unsupported files or handle them as needed
                    continue
                processed_files.append(output_path)
            except Exception as e:
                raise e

        if not processed_files:
            shutil.rmtree(output_dir)
            raise Exception("No files were successfully processed.")

        zip_output_path = f"output/{job_id}"
        
        # Clean up the individual watermarked files
        shutil.make_archive(zip_output_path, 'zip', output_dir)
        shutil.rmtree(output_dir)

        return f"{zip_output_path}.zip"
    else:
        raise Exception("Batch processing is only allowed in PREPROD environment.")

def cleanup_file(file_path: str):
    
    """
    Deletes a file.
    """
    
    try:
        os.remove(file_path)
    except OSError as e:
        raise f"Error deleting file {file_path}: {e}"

