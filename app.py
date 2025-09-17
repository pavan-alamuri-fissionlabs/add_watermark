import os
import uuid
import shutil
import zipstream

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from celery.result import AsyncResult

from add_watermark import add_watermark_to_pdf, add_watermark_to_image, add_watermark_to_docx, add_watermark_to_rtf, add_watermark_to_csv, add_watermark_to_svg, add_watermark_to_pptx
from models import InputFileBatch
from celery_worker import celery_app


app = FastAPI()

# Mapping of extensions to handler functions
EXTENSION_HANDLERS = {
    "pdf": add_watermark_to_pdf,
    "docx": add_watermark_to_docx,
    "doc": add_watermark_to_docx,
    "jpg": add_watermark_to_image,
    "jpeg": add_watermark_to_image,
    "png": add_watermark_to_image,
    "rtf": add_watermark_to_rtf,
    "csv": add_watermark_to_csv,
    "svg": add_watermark_to_svg,
    "pptx": add_watermark_to_pptx,
    "ppt": add_watermark_to_pptx,
}

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
    
    # Generate a task ID
    task_id = str(uuid.uuid4())
    task = add_watermark_to_files_and_zip.apply_async(
        args=[files.file_paths, files.source, task_id],
        task_id=task_id
    )
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
            else:
                response["result"] = str(task_result.info)  # Get exception info
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/")
def download_zip_file(task_id: str):
    
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
        
        # background_tasks.add_task(cleanup_file, zip_file_path)

        return FileResponse(
            path=zip_file_path, 
            headers=headers, 
            media_type='application/zip'
        )


    except Exception as e:
        raise e
    
@app.get("/download/stream")
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

@celery_app.task
def add_watermark_to_files_and_zip(file_paths, source, task_id):
    
    """
    Celery task to watermark a list of files and zip them.
    Params:
        - file_paths: List of file paths to be watermarked.
        - source: str, must be 'PREPROD' for processing.
    Returns:
        - Path to the zipped output file.
    """
    
    if source != "PREPROD":
        raise Exception("Batch processing is only allowed in PREPROD environment.")

    output_dir = f"output/{task_id}"
    os.makedirs(output_dir, exist_ok=True)

    processed_files = []

    for file_path in file_paths:
        try:
            ext = file_path.lower().split('.')[-1]
            file_name = os.path.basename(file_path).split('.')[0]

            # Special case: CSV always produces PDF
            if ext == "csv":
                output_file = f"{file_name}-DRAFT.pdf"
            else:
                output_file = f"{file_name}-DRAFT.{ext}"

            output_path = os.path.join(output_dir, output_file)

            handler = EXTENSION_HANDLERS.get(ext)
            if handler:
                handler(file_path, output_path)
                processed_files.append(output_path)
            else:
                # Skip unsupported files
                continue
        except Exception as e:
            raise e

    if not processed_files:
        shutil.rmtree(output_dir)
        raise Exception("No files were successfully processed.")

    # Zip the processed files
    zip_output_path = f"output/{task_id}"
    shutil.make_archive(zip_output_path, "zip", output_dir)

    # Remove original watermarked files after zipping
    shutil.rmtree(output_dir)

    return f"{zip_output_path}.zip"

def cleanup_file(file_path: str):
    
    """
    Deletes a file.
    """
    
    try:
        os.remove(file_path)
    except OSError as e:
        raise f"Error deleting file {file_path}: {e}"

