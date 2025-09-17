import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from add_watermark import add_watermark_to_pdf, add_watermark_to_image, add_watermark_to_docx, rtf_to_docx

app = FastAPI()

@app.post("/watermark/")
def add_watermark(file_path: str):
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="File does not exist.")
    ext = file_path.lower().split('.')[-1]
    watermarked_path = None

    if ext == "pdf":
        watermarked_path = add_watermark_to_pdf(file_path,"output/output.pdf")
    elif ext in ["docx", "doc"]:
        watermarked_path = add_watermark_to_docx(file_path, output_path="output/output."+ext)
    elif ext in ["jpg", "jpeg", "png"]:
        watermarked_path = add_watermark_to_image(file_path, output_path="output/output."+ext)
    elif ext == "rtf":
        docx_path = rtf_to_docx(file_path)
        watermarked_path = add_watermark_to_docx(docx_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    return "Successful"


