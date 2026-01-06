import pdfplumber
import os

def extract_tables_to_dir(pdf_path, output_dir):
    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # 1. Find table objects on the page
            tables = page.find_tables()
            
            if not tables:
                continue

            # 2. Generate a debug image with bounding boxes
            # We use a higher resolution (150) for clarity
            img = page.to_image(resolution=150)
            img.draw_rects([t.bbox for t in tables], stroke="blue", stroke_width=3)
            img.save(os.path.join(output_dir, f"page_{i+1}_debug.png"))

# Usage
extract_tables_to_dir("main.pdf", "extracted_tables")