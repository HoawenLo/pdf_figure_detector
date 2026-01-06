import pdfplumber
import os
from collections import defaultdict, deque

# --- CONFIGURATION ---
PDF_PATH = "main.pdf"
OUTPUT_DIR = "processed_pages"
MARGIN = 12
RESOLUTION = 150

def obj_to_bbox(obj):
    return [float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"])]

def get_all_elements(page):
    """Extracts vectors (lines, rects, curves) and text."""
    # Included chars to ensure text labels are part of the figure groups
    elements = page.lines + page.rects + page.curves
    return [obj_to_bbox(e) for e in elements]

def boxes_intersect(a, b, margin=10):
    return not (
        b[0] > a[2] + margin or
        b[2] < a[0] - margin or
        b[1] > a[3] + margin or
        b[3] < a[1] - margin
    )

def group_boxes(boxes, margin=15):
    n = len(boxes)
    graph = defaultdict(list)
    for i in range(n):
        for j in range(i + 1, n):
            if boxes_intersect(boxes[i], boxes[j], margin=margin):
                graph[i].append(j)
                graph[j].append(i)

    visited = [False] * n
    groups = []
    for i in range(n):
        if not visited[i]:
            stack = [i]
            visited[i] = True
            component = []
            while stack:
                u = stack.pop()
                component.append(u)
                for v in graph[u]:
                    if not visited[v]:
                        visited[v] = True
                        stack.append(v)
            groups.append(component)
    return groups

def merge_groups(boxes, groups):
    merged = []
    for group in groups:
        x0 = min(boxes[i][0] for i in group)
        y0 = min(boxes[i][1] for i in group)
        x1 = max(boxes[i][2] for i in group)
        y1 = max(boxes[i][3] for i in group)
        merged.append([x0, y0, x1, y1])
    return merged

# --- Main Execution ---

# 1. Create the output folder if it doesn't exist
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    print(f"Created folder: {OUTPUT_DIR}")

with pdfplumber.open(PDF_PATH) as pdf:
    print(f"Processing {len(pdf.pages)} pages...")
    
    for i, page in enumerate(pdf.pages):
        page_num = i + 1  # 1-indexed for filename
        
        # Extract and group
        all_boxes = get_all_elements(page)
        
        # Skip empty pages to avoid errors
        if not all_boxes:
            print(f"Page {page_num}: No elements found. Skipping.")
            continue
            
        groups = group_boxes(all_boxes, margin=MARGIN)
        final_bboxes = merge_groups(all_boxes, groups)
        
        # Visualise and save
        im = page.to_image(resolution=RESOLUTION)
        im.draw_rects(final_bboxes, stroke="red", stroke_width=2)
        
        # Save into the folder with the page number
        output_filename = os.path.join(OUTPUT_DIR, f"page_{page_num}.png")
        im.save(output_filename)
        
        print(f"Page {page_num} saved to {output_filename}")

print("Done!")


### To add if box too small discard as this will be noise, and figures are only ever large
### Or use VLM to determine if it is table or an actual diagram
### Use VLM to determine if figure needs to be separated into seperate diagrams based off the input page, perhaps give a confidence score

### Current issues > diagrams connected, small symbols in text (perhaps if you detect chars, and if non character box is surrounded in a character box discard it as non text?)
### > diagrams connected > tune the margin, use VLM to identify, with VLM must include confidence score for manual checking.
### > Is it a table or diagram
