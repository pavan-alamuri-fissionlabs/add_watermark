from docx import Document
from io import BytesIO
# from PyPDF2 import PdfReader, PdfWriter
from pypdf import PdfReader, PdfWriter
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

from celery_worker import celery_app


def create_watermark_pdf(watermark_text, page_width, page_height, font_size=50, opacity=0.3, rotation_angle=45):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    c.setFont("Helvetica-Bold", font_size)
    c.setFillGray(0, opacity)  # Black with transparency

    # Move to center, rotate, then draw text
    c.saveState()
    c.translate(page_width / 2, page_height / 2)
    c.rotate(rotation_angle)
    c.drawCentredString(0, 0, watermark_text)
    c.restoreState()

    c.save()
    buffer.seek(0)
    return buffer

@celery_app.task
def add_watermark_to_pdf(input_pdf: str, output_pdf: str, watermark_text='DRAFT'):

    input_pdf_reader = PdfReader(open(input_pdf, "rb"))
    output_pdf_writer = PdfWriter()

    for page in input_pdf_reader.pages:
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        # Create watermark matching this page size
        watermark_pdf_buffer = create_watermark_pdf(watermark_text, page_width, page_height)
        watermark_reader = PdfReader(watermark_pdf_buffer)
        watermark_page = watermark_reader.pages[0]

        # Merge watermark into current page
        page.merge_page(watermark_page)
        output_pdf_writer.add_page(page)

    with open(output_pdf, "wb") as output_file:
        output_pdf_writer.write(output_file)

@celery_app.task
def add_watermark_to_image(image_path, output_path, watermark_text="DRAFT"):

    img = Image.open(image_path).convert("RGBA")
    img_width, img_height = img.size

    font_size_ratio=0.1
    color=(150, 150, 150, 100)
    font_size = int(img_height * font_size_ratio)
    font = ImageFont.load_default(size=font_size)

    # Transparent layer for text
    text_layer = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    # Get text size
    text_bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    # Center position
    x = (img_width - text_width) / 2
    y = (img_height - text_height) / 2

    draw.text((x, y), watermark_text, font=font, fill=color)

    # Rotate
    rotated_text = text_layer.rotate(45, expand=False)

    # Overlay
    watermarked = Image.alpha_composite(img, rotated_text)

    if output_path.lower().endswith((".jpg", ".jpeg")):
        watermarked = watermarked.convert("RGB")
    
    watermarked.save(output_path)

@celery_app.task
def add_watermark_to_rtf(rtf_path, output_path, watermark_text="DRAFT"):
    pass

@celery_app.task
def add_watermark_to_docx(input_doc_path, output_doc_path, watermark_text="DRAFT"):
    pass
