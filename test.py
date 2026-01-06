import pdfplumber
import re
import os

# Output directory
DEBUG_DIR = "deep_debug_output"
os.makedirs(DEBUG_DIR, exist_ok=True)

def is_bold(line):
    return any("bold" in c.get("fontname", "").lower() for c in line["chars"])

def get_union_bbox(elements):
    if not elements: return None
    x0 = min(e.get('x0', e[0] if isinstance(e, tuple) else 0) for e in elements)
    top = min(e.get('top', e[1] if isinstance(e, tuple) else 0) for e in elements)
    x1 = max(e.get('x1', e[2] if isinstance(e, tuple) else 0) for e in elements)
    bottom = max(e.get('bottom', e[3] if isinstance(e, tuple) else 0) for e in elements)
    return (x0, top, x1, bottom)

def deep_debug_visualize(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:30]:
            lines = page.extract_text_lines()
            images = sorted(page.images, key=lambda x: x["top"])
            tables = page.find_tables()
            
            # 1. Initialize the visual canvas
            img_viz = page.to_image(resolution=150)
            
            # Logic tracking
            fig_boxes = []
            table_boxes = []
            img_idx = 0
            current_fig_elements = []
            is_capturing_fig = False

            # --- PART A: Identify Logical Groups ---
            for line in lines:
                text = line['text'].strip()
                bold = is_bold(line)

                if img_idx < len(images) and images[img_idx]['bottom'] <= line['top']:
                    is_capturing_fig = True
                    current_fig_elements.append(images[img_idx])
                    img_idx += 1

                if is_capturing_fig:
                    current_fig_elements.append(line)
                    if bold and re.match(r"^Figure\s+\d+", text, re.IGNORECASE):
                        fig_boxes.append(get_union_bbox(current_fig_elements))
                        current_fig_elements = []
                        is_capturing_fig = False
                    continue

                if bold and re.match(r"^Table\s+\d+", text, re.IGNORECASE):
                    for t in tables:
                        if t.bbox[1] >= line['bottom'] - 5:
                            t_bbox = {'x0': t.bbox[0], 'top': line['top'], 'x1': t.bbox[2], 'bottom': t.bbox[3]}
                            table_boxes.append(get_union_bbox([t_bbox]))
                            break

            # --- PART B: Draw Overlays ---
            
            # 1. Draw ALL detected lines (Red for normal, Purple for Bold)
            for line in lines:
                color = "purple" if is_bold(line) else "red"
                img_viz.draw_rect(line, stroke=color, stroke_width=1)

            # 2. Draw Logical Figure Blocks (Green)
            if fig_boxes:
                img_viz.draw_rects(fig_boxes, stroke="green", stroke_width=3, fill=(0, 255, 0, 40))
            
            # 3. Draw Logical Table Blocks (Blue)
            if table_boxes:
                img_viz.draw_rects(table_boxes, stroke="blue", stroke_width=3, fill=(0, 0, 255, 40))

            # 4. Save
            save_path = os.path.join(DEBUG_DIR, f"page_{page.page_number}_deep_debug.png")
            img_viz.save(save_path)
            print(f"Deep Debug saved: {save_path}")

deep_debug_visualize("main.pdf")