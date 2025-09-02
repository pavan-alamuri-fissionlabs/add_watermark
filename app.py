import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from add_watermark import add_watermark_to_pdf, add_watermark_to_image, add_watermark_to_docx, rtf_to_docx
from celery_worker import celery_app
from celery.result import AsyncResult

app = FastAPI()

@app.post("/watermark/")
def add_watermark(file_path: str):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="File does not exist.")
    ext = file_path.lower().split('.')[-1]
    watermarked_path = None

    if ext == "pdf":
        task = add_watermark_to_pdf.delay(file_path,"output/output.pdf")
    elif ext in ["docx", "doc"]:
        watermarked_path = add_watermark_to_docx(file_path, output_path="output/output."+ext)
    elif ext in ["jpg", "jpeg", "png"]:
        task = add_watermark_to_image.delay(file_path, output_path="output/output."+ext)
    elif ext == "rtf":
        docx_path = rtf_to_docx(file_path)
        watermarked_path = add_watermark_to_docx(docx_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    return {"message": "Watermarking initiated", "task_id": task.id}

@app.get("/status/{task_id}")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.ready():
        return {"task_id": task_id, "status": task_result.status, "result": task_result.result}
    return {"task_id": task_id, "status": task_result.status}


