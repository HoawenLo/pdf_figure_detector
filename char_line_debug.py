import pdfplumber
import os

PDF_PATH = "main.pdf"
DEBUG_DIR = "char_debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

def debug_chars(path):
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            im = page.to_image(resolution=150)
            
            # Pillow requires integer for stroke_width now
            # We also ensure the char objects have clean coordinates
            clean_chars = []
            for c in page.chars:
                clean_chars.append({
                    "x0": float(c["x0"]),
                    "top": float(c["top"]),
                    "x1": float(c["x1"]),
                    "bottom": float(c["bottom"])
                })
            
            # Use stroke_width=1 (integer) to avoid the TypeError
            im.draw_rects(clean_chars, stroke="blue", stroke_width=1)
            
            im.save(os.path.join(DEBUG_DIR, f"page_{i+1}_chars.png"))
            print(f"Saved Chars for Page {i+1} (Count: {len(page.chars)})")

if __name__ == "__main__":
    debug_chars(PDF_PATH)