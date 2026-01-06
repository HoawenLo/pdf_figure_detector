import pdfplumber
import os
from collections import defaultdict

# --- CONFIGURATION ---
PDF_PATH = "main.pdf"
BASE_DEBUG_DIR = "debug"
RESOLUTION = 150
OFFSET_VAL = 24.03
MIN_DIAGRAM_SIZE = 10  # Filter out noise smaller than 10x10 pts

# Define subdirectories
DIRS = {
    "chars": os.path.join(BASE_DEBUG_DIR, "char_debug"),
    "diagrams": os.path.join(BASE_DEBUG_DIR, "diagram_debug"),
    "paras": os.path.join(BASE_DEBUG_DIR, "paragraph_debug"),
    "tables": os.path.join(BASE_DEBUG_DIR, "table_debug"),
    "offsets": os.path.join(BASE_DEBUG_DIR, "text_line_debug"),
    "vectors": os.path.join(BASE_DEBUG_DIR, "vector_debug"),
}

# Create all directories
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# --- HELPER FUNCTIONS ---

def is_in_body(top, bottom, page_height, top_margin_pct=0.08, bottom_margin_pct=0.05):
    header_limit = page_height * top_margin_pct
    footer_limit = page_height * (1 - bottom_margin_pct)
    return top > header_limit and bottom < footer_limit

def process_word_data(word, offset_value):
    font = (word.get("fontname") or "").lower()
    is_styled = any(x in font for x in ["bold", "italic", "oblique"])
    if not is_styled:
        return word["x0"], word["top"] - offset_value, word["x1"], word["bottom"] - offset_value, "red"
    return word["x0"], word["top"], word["x1"], word["bottom"], "blue"

def boxes_intersect(a, b, margin=12):
    return not (b[0] > a[2] + margin or b[2] < a[0] - margin or
                b[1] > a[3] + margin or b[3] < a[1] - margin)

def group_boxes(boxes, margin=12):
    n = len(boxes)
    graph = defaultdict(list)
    for i in range(n):
        for j in range(i + 1, n):
            if boxes_intersect(boxes[i], boxes[j], margin=margin):
                graph[i].append(j); graph[j].append(i)
    visited, groups = [False] * n, []
    for i in range(n):
        if not visited[i]:
            stack, component = [i], []
            visited[i] = True
            while stack:
                u = stack.pop()
                component.append(u)
                for v in graph[u]:
                    if not visited[v]:
                        visited[v] = True; stack.append(v)
            groups.append(component)
    return groups

# --- ANALYSIS MODULES ---

def run_char_debug(page, page_num):
    im = page.to_image(resolution=RESOLUTION)
    clean_chars = [{"x0": float(c["x0"]), "top": float(c["top"]), 
                    "x1": float(c["x1"]), "bottom": float(c["bottom"])} for c in page.chars]
    im.draw_rects(clean_chars, stroke="blue", stroke_width=1)
    im.save(os.path.join(DIRS["chars"], f"page_{page_num}_chars.png"))

def run_vector_debug(page, page_num):
    im = page.to_image(resolution=RESOLUTION)
    if page.lines: im.draw_rects(page.lines, stroke="red", stroke_width=1)
    if page.rects: im.draw_rects(page.rects, stroke="blue", stroke_width=1)
    if page.curves: im.draw_rects(page.curves, stroke="green", stroke_width=1)
    im.save(os.path.join(DIRS["vectors"], f"page_{page_num}_vectors.png"))

def run_table_debug(page, page_num):
    tables = page.find_tables()
    if tables:
        im = page.to_image(resolution=RESOLUTION)
        im.draw_rects([t.bbox for t in tables], stroke="blue", stroke_width=3)
        im.save(os.path.join(DIRS["tables"], f"page_{page_num}_tables.png"))

def run_diagram_debug(page, page_num):
    elements = page.lines + page.rects + page.curves
    boxes = [[float(e["x0"]), float(e["top"]), float(e["x1"]), float(e["bottom"])] 
             for e in elements if (float(e["x1"]) - float(e["x0"])) > MIN_DIAGRAM_SIZE]
    if boxes:
        groups = group_boxes(boxes)
        merged = []
        for g in groups:
            merged.append([min(boxes[i][0] for i in g), min(boxes[i][1] for i in g),
                           max(boxes[i][2] for i in g), max(boxes[i][3] for i in g)])
        im = page.to_image(resolution=RESOLUTION)
        im.draw_rects(merged, stroke="red", stroke_width=2)
        im.save(os.path.join(DIRS["diagrams"], f"page_{page_num}_diagrams.png"))

def run_text_and_para_debug(page, page_num):
    all_words = page.extract_words(extra_attrs=["fontname"])
    img_off = page.to_image(resolution=RESOLUTION)
    
    processed_words = []
    for w in all_words:
        nx0, ntop, nx1, nbot, color = process_word_data(w, OFFSET_VAL)
        if is_in_body(ntop, nbot, page.height):
            img_off.draw_rect([nx0, ntop, nx1, nbot], stroke=color)
            w.update({"nx0": nx0, "ntop": ntop, "nx1": nx1, "nbot": nbot})
            processed_words.append(w)
    
    img_off.save(os.path.join(DIRS["offsets"], f"page_{page_num}_offsets.png"))
    # Note: You can call your paragraph merging logic here using 'processed_words'

# --- MAIN EXECUTION ---

def main():
    print(f"Starting debug process for: {PDF_PATH}")
    with pdfplumber.open(PDF_PATH) as pdf:
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            print(f"Processing Page {page_num}...")
            
            run_char_debug(page, page_num)
            run_vector_debug(page, page_num)
            run_table_debug(page, page_num)
            run_diagram_debug(page, page_num)
            run_text_and_para_debug(page, page_num)

    print(f"\nSuccess! All debug files are in the '{BASE_DEBUG_DIR}' directory.")

if __name__ == "__main__":
    main()