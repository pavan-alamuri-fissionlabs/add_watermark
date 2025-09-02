import xml.sax.saxutils as saxutils  # for escaping XML
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.oxml import parse_xml
from reportlab.pdfgen import canvas
from io import BytesIO
from celery_worker import celery_app

def create_watermark_pdf(text, page_width, page_height, font_size=50, opacity=0.3, rotation_angle=45):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    c.setFont("Helvetica-Bold", font_size)
    c.setFillGray(0, opacity)  # Black with transparency

    # Move to center, rotate, then draw text
    c.saveState()
    c.translate(page_width / 2, page_height / 2)
    c.rotate(rotation_angle)
    c.drawCentredString(0, 0, text)
    c.restoreState()

    c.save()
    buffer.seek(0)
    return buffer

@celery_app.task
def add_watermark_to_pdf(input_pdf: str, output_pdf: str, text='DRAFT'):

    input_pdf_reader = PdfReader(open(input_pdf, "rb"))
    output_pdf_writer = PdfWriter()

    for page in input_pdf_reader.pages:
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        # Create watermark matching this page size
        watermark_pdf_buffer = create_watermark_pdf(text, page_width, page_height)
        watermark_reader = PdfReader(watermark_pdf_buffer)
        watermark_page = watermark_reader.pages[0]

        # Merge watermark into current page
        page.merge_page(watermark_page)
        output_pdf_writer.add_page(page)

    with open(output_pdf, "wb") as output_file:
        output_pdf_writer.write(output_file)

@celery_app.task
def add_watermark_to_image(image_path, output_path, watermark_text="DRAFT", font_path=None, font_size_ratio=0.1, color=(150, 150, 150, 100)):

    img = Image.open(image_path).convert("RGBA")
    img_width, img_height = img.size

    font_size = int(img_height * font_size_ratio)

    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default(size=font_size)
    except IOError:
        print(f"Warning: Could not load font from {font_path}. Using default font.")
        font = ImageFont.load_default()

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

def add_watermark_to_docx(input_doc_path, output_path, watermark_text="DRAFT"):
    doc = Document(input_doc_path)

    # Escape special XML characters
    safe_text = saxutils.escape(watermark_text)

    # VML-based watermark with adjusted font size, position, and opacity
    watermark_xml = f"""
    <w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:o="urn:schemas-microsoft-com:office:office">
        <v:shape id="WordPictureWatermark"
                 o:spid="_x0000_s2049"
                 type="#_x0000_t136"
                 style="position:absolute;margin-left:0;margin-top:0;width:468pt;height:117pt;
                        z-index:-251654144;rotation:315;visibility:visible;mso-wrap-style:square"
                 stroked="f" filled="t">
            <v:fill opacity="0.2" color="#000000"/>
            <v:textpath style="font-family:Calibri;font-size:400pt" string="{safe_text}"/>
        </v:shape>
    </w:pict>
    """

    # Add watermark to header of all sections
    for section in doc.sections:
        header = section.header
        paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        paragraph._element.append(parse_xml(watermark_xml))

    doc.save(output_path)

def rtf_to_docx(rtf_path):
    pass
