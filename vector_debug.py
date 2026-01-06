import pdfplumber
import os

# --- CONFIGURATION ---
PDF_PATH = "main.pdf"
DEBUG_DIR = "vector_debug"
RESOLUTION = 150  # Higher resolution for sharper lines

os.makedirs(DEBUG_DIR, exist_ok=True)

def debug_vectors(path):
    with pdfplumber.open(path) as pdf:
        print(f"Analyzing vectors for {len(pdf.pages)} pages...")
        
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            
            # Create a blank white image based on the page size
            # This helps see vectors without text distraction
            im = page.to_image(resolution=RESOLUTION)
            
            # 1. Draw Lines (Red)
            if page.lines:
                im.draw_rects(page.lines, stroke="red", stroke_width=1)
                
            # 2. Draw Rects (Blue)
            if page.rects:
                im.draw_rects(page.rects, stroke="blue", stroke_width=1)
                
            # 3. Draw Curves (Green)
            if page.curves:
                im.draw_rects(page.curves, stroke="green", stroke_width=1)
            
            # Save the result
            output_path = os.path.join(DEBUG_DIR, f"page_{page_num}_vectors.png")
            im.save(output_path)
            
            # Print a quick summary for the terminal
            print(f"Page {page_num}: Lines={len(page.lines)}, Rects={len(page.rects)}, Curves={len(page.curves)}")

if __name__ == "__main__":
    debug_vectors(PDF_PATH)
    print(f"\nDebug complete. Check the '{DEBUG_DIR}' folder.")