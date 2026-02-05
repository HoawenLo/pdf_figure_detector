import fitz  # PyMuPDF
import os

def pdf_to_images_fitz(pdf_path, output_dir, zoom=2, fmt="PNG", prefix="page"):
    """
    Convert PDF pages to images using PyMuPDF.

    Args:
        pdf_path (str): Path to PDF file
        output_dir (str): Folder to save images
        zoom (float): Zoom factor for higher resolution (1 = 72dpi)
        fmt (str): Image format (PNG, JPEG)
        prefix (str): Filename prefix
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    count = 0

    for i, page in enumerate(doc, start=1):
        mat = fitz.Matrix(zoom, zoom)  # scale for higher DPI
        pix = page.get_pixmap(matrix=mat)
        output_path = os.path.join(output_dir, f"{prefix}_{i}.{fmt.lower()}")
        pix.save(output_path)
        count += 1

    return count
