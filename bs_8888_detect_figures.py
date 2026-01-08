import pdfplumber
import os
import re
import json
import base64
from io import BytesIO
from collections import defaultdict

# --- CONFIGURATION ---
PDF_PATH = "main.pdf"
OUTPUT_DIR = "main_output"
MARGIN = 8            
RESOLUTION = 150
SYMBOL_THRESHOLD = 5
OFFSET_VAL = 24.03

os.makedirs(OUTPUT_DIR, exist_ok=True)

def obj_to_bbox(obj):
    return [float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"])]

def is_bold(line):
    return any("bold" in c.get("fontname", "").lower() for c in line["chars"])

def is_bold_words(line):
    return any("bold" in w.get("fontname", "").lower() for w in line["words"])

def is_inside(obj_bbox, target_bbox):
    return (obj_bbox[0] >= target_bbox[0] - 4 and
            obj_bbox[1] >= target_bbox[1] - 4 and
            obj_bbox[2] <= target_bbox[2] + 4 and
            obj_bbox[3] <= target_bbox[3] + 4)

def boxes_intersect(a, b, margin=10):
    return not (b[0] > a[2] + margin or b[2] < a[0] - margin or
                b[1] > a[3] + margin or b[3] < a[1] - margin)

def group_boxes(boxes, margin=15):
    n = len(boxes)
    if n == 0: return []
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
            stack, component = [i], []
            visited[i] = True
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
    return [[min(boxes[i][0] for i in g), min(boxes[i][1] for i in g),
             max(boxes[i][2] for i in g), max(boxes[i][3] for i in g)] for g in groups]

def get_filtered_elements(page, table_bboxes, paragraphs, lines):
    all_vectors = page.lines + page.rects + page.curves
    filtered = []
    
    text_exclusion_zones = []
    for l in lines:
        is_caption = re.match(r"^(Figure|Table)\s+\d+", l['text'], re.I)
        if not is_caption:
            text_exclusion_zones.append((l['top'], l['bottom']))

    for v in all_vectors:
        v_bbox = obj_to_bbox(v)
        
        if any(is_inside(v_bbox, t_bbox) for t_bbox in table_bboxes):
            continue
        
        if any(is_inside(v_bbox, obj_to_bbox(paragraph)) for paragraph in paragraphs):
            continue
            
        filtered.append(v_bbox)
    return filtered


#####

def is_in_body(top, bottom, page_height, top_margin_pct=0.08, bottom_margin_pct=0.05):
    """Checks if coordinates are within the main body of the page."""
    header_limit = page_height * top_margin_pct
    footer_limit = page_height * (1 - bottom_margin_pct)
    return top > header_limit and bottom < footer_limit

def process_word_offset(word, offset_value):
    """Applies 24.03 offset if font is not bold, italic, or oblique."""
    font = (word.get("fontname") or "").lower()
    is_styled = any(x in font for x in ["bold", "italic", "oblique"])
    
    x0, top, x1, bottom = word["x0"], word["top"], word["x1"], word["bottom"]
    
    if not is_styled:
        return x0, top - offset_value, x1, bottom - offset_value, "red", "Shifted"
    else:
        return x0, top, x1, bottom, "blue", "Original"

def group_words_into_lines(words, tolerance=3):
    """Groups words into horizontal lines based on vertical proximity."""
    if not words: return []
    # Sort by top, then left
    words.sort(key=lambda w: (w["new_top"], w["nx0"]))
    
    lines = []
    current_line = [words[0]]
    for next_word in words[1:]:
        if abs(next_word["new_top"] - current_line[-1]["new_top"]) <= tolerance:
            current_line.append(next_word)
        else:
            current_line.sort(key=lambda w: w["nx0"])
            lines.append(current_line)
            current_line = [next_word]
    lines.append(current_line)
    
    # Create line objects with bounding boxes
    line_blocks = []
    for line in lines:
        line_blocks.append({
            "x0": min(w["nx0"] for w in line),
            "top": min(w["new_top"] for w in line),
            "x1": max(w["nx1"] for w in line),
            "bottom": max(w["new_bottom"] for w in line),
            "text": " ".join(w["text"] for w in line),
            "words": [
                l for l in line
            ]
        })
    return line_blocks

def merge_lines_into_paragraphs(line_blocks, x_tolerance=10, y_tolerance=12):
    """Merges lines into paragraph blocks using expanding box logic."""
    if not line_blocks: return []
    
    paragraphs = [[line] for line in line_blocks]
    merged = True
    while merged:
        merged = False
        new_paragraphs = []
        while paragraphs:
            curr_para = paragraphs.pop(0)
            has_merged = False
            
            c_x0 = min(l["x0"] for l in curr_para)
            c_top = min(l["top"] for l in curr_para)
            c_x1 = max(l["x1"] for l in curr_para)
            c_bot = max(l["bottom"] for l in curr_para)
            
            for i, other_para in enumerate(new_paragraphs):
                o_x0 = min(l["x0"] for l in other_para)
                o_top = min(l["top"] for l in other_para)
                o_x1 = max(l["x1"] for l in other_para)
                o_bot = max(l["bottom"] for l in other_para)
                
                # Check for rectangle overlap with tolerances
                if not (c_x0 - x_tolerance > o_x1 or 
                        c_x1 + x_tolerance < o_x0 or 
                        c_top - y_tolerance > o_bot or 
                        c_bot + y_tolerance < o_top):
                    new_paragraphs[i].extend(curr_para)
                    has_merged = True
                    merged = True
                    break
            if not has_merged:
                new_paragraphs.append(curr_para)
        paragraphs = new_paragraphs

    # Finalize paragraph metadata
    final_paras = []
    for p in paragraphs:
        p.sort(key=lambda l: l["top"])
        final_paras.append({
            "x0": min(l["x0"] for l in p),
            "top": min(l["top"] for l in p),
            "x1": max(l["x1"] for l in p),
            "bottom": max(l["bottom"] for l in p),
            "text": "\n".join(l["text"] for l in p)
        })
    return sorted(final_paras, key=lambda b: b["top"])

def filter_lines_in_tables(line_blocks, table_sections):
    """
    Removes lines that fall within the vertical span of any detected table.
    table_sections is a list of tuples: (x0, top, x1, bottom)
    """
    filtered_lines = []
    
    for line in line_blocks:
        # Calculate the vertical center of the line
        line_midpoint = (line["top"] + line["bottom"]) / 2
        is_inside_table = False
        
        for t_bbox in table_sections:
            t_top = t_bbox[1] - 4    # index 1 is top
            t_bottom = t_bbox[3] + 4 # index 3 is bottom
            
            # Check if the line's midpoint is within the table's vertical bounds
            if t_top <= line_midpoint <= t_bottom:
                is_inside_table = True
                break # No need to check other tables
        
        if not is_inside_table:
            filtered_lines.append(line)
            
    return filtered_lines

def get_image_data(page, bbox):
    """Crops the page to the figure area and returns base64 encoded string."""
    try:
        # Crop and convert to image
        crop = page.crop(bbox)
        img = crop.to_image(resolution=RESOLUTION)
        
        buffered = BytesIO()
        img.original.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception:
        return None

def format_page_data(page, table_sections, paragraphs, figure_sections):
    """Groups all elements into a sorted list of dictionaries."""
    page_contents = []

    # 1. Format Tables
    for t_bbox in table_sections:
        page_contents.append({
            "Category": "table",
            "contents": page.crop(t_bbox).extract_table(),
            "coordinates": list(t_bbox)
        })

    # 2. Format Paragraphs
    for p in paragraphs:
        page_contents.append({
            "Category": "paragraph",
            "contents": p["text"],
            "coordinates": [p["x0"], p["top"], p["x1"], p["bottom"]]
        })

    # 3. Format Figures
    for f_bbox in figure_sections:
        page_contents.append({
            "Category": "figure",
            "contents": get_image_data(page, f_bbox),
            "coordinates": list(f_bbox)
        })

    # Sort by the 'top' coordinate (index 1) to preserve reading order
    page_contents.sort(key=lambda x: x["coordinates"][1])
    return page_contents

def get_raw_lines(page):
    all_words = page.extract_words(extra_attrs=["fontname"])
    
    # Apply Offset and Filter by Margins
    processed_words = []
    for w in all_words:
        nx0, ntop, nx1, nbot, color, status = process_word_offset(w, OFFSET_VAL)
        
        if is_in_body(ntop, nbot, page.height):
            # Attach the calculated values to the word object for grouping
            w.update({"nx0": nx0, "new_top": ntop, "nx1": nx1, "new_bottom": nbot, "color": color})
            processed_words.append(w)

    # Grouping
    raw_lines = group_words_into_lines(processed_words)
    return raw_lines

def get_merged_heavy_lines(page, tolerance=1.0):
    """Groups segments at the same height and merges them into one full-width span."""
    # 1. Filter for thickness
    heavy_segments = [l for l in page.lines if 2.2 <= float(l.get('linewidth', 0)) <= 2.3]
    
    # 2. Group by vertical position ('top')
    groups = defaultdict(list)
    for seg in heavy_segments:
        # Round the top to handle tiny floating point differences
        y_key = round(seg['top'], 1)
        groups[y_key].append(seg)
    
    merged_lines = []
    for y_key, segments in groups.items():
        # 3. Find the extreme left and right points for this Y-level
        min_x = min(s['x0'] for s in segments)
        max_x = max(s['x1'] for s in segments)
        
        merged_lines.append({
            'top': y_key,
            'bottom': y_key, # Usually horizontal lines have same top/bottom
            'x0': min_x,
            'x1': max_x,
            'width': max_x - min_x
        })
    
    # Return sorted by vertical position
    return sorted(merged_lines, key=lambda x: x['top'])

def detect_tables_with_merged_borders(page):
    final_sections = []
    merged_borders = get_merged_heavy_lines(page)
    raw_lines = get_raw_lines(page)
    
    for text_line in raw_lines:
        # Identify Caption
        if is_bold_words(text_line) and re.match(r"^Table\s+([A-Z]\.)?\d+", text_line['text'], re.I):
            caption_y = text_line['bottom']
            
            # Find the two merged borders below this caption
            borders_below = [b for b in merged_borders if b['top'] >= caption_y - 2]
            
            if len(borders_below) >= 2:
                top_border = borders_below[0]
                bottom_border = borders_below[1]
                
                # The table width is defined by the merged span
                # We use the wider of the two borders (just in case)
                x0 = min(text_line['x0'], top_border['x0'], bottom_border['x0'])
                x1 = max(text_line['x1'], top_border['x1'], bottom_border['x1'])
                
                # Final BBox: [left, top, right, bottom]
                t_sect = (x0, text_line['top'], x1, bottom_border['bottom'])
                final_sections.append(t_sect)
                
    return final_sections

# --- MAIN EXECUTION ---

def process_pdf(path, output_directory):

    full_document = []
    with pdfplumber.open(path) as pdf:
        print(f"Processing {len(pdf.pages)} pages...")
        
        for i, page in enumerate(pdf.pages):

            # test_lines = []
            # for line in sorted(page.lines, key=lambda x: x['top']):
            #     # if line["top"] >= 226.3 and line["bottom"] <= 431.19:
            #     #     print("x0: ", line["x0"], "top: ", line["top"], "x1: ", line["x1"], "bottom: ", line["bottom"], "linewidth: ", line["linewidth"])
            #     if line["linewidth"] == 2.25:
            #         test_lines.append(line)
            
                # print(line)

            # 71.2795 216.15559999999994 409.8755 226.35559999999998
            # 431.19 441.19

            page_num = i + 1
            im = page.to_image(resolution=RESOLUTION)
            
            # im.draw_rects(test_lines, stroke="blue", stroke_width=3)
            

            final_table_sections = detect_tables_with_merged_borders(page)

            # im.draw_rects(final_table_sections, stroke="blue", stroke_width=3)
            # 2. Get paragraphs
            all_words = page.extract_words(extra_attrs=["fontname"])
            
            # Apply Offset and Filter by Margins
            processed_words = []
            for w in all_words:
                nx0, ntop, nx1, nbot, color, status = process_word_offset(w, OFFSET_VAL)
                
                if is_in_body(ntop, nbot, page.height):
                    # Attach the calculated values to the word object for grouping
                    w.update({"nx0": nx0, "new_top": ntop, "nx1": nx1, "new_bottom": nbot, "color": color})
                    processed_words.append(w)

            # Grouping
            raw_lines = group_words_into_lines(processed_words)

            # for line in raw_lines:
            #     print(line["text"], line["top"], line["bottom"])

            filtered_lines = filter_lines_in_tables(raw_lines, final_table_sections)
            paragraphs = merge_lines_into_paragraphs(filtered_lines)

            # 2. VECTOR EXTRACTION (Filtered by validated tables and paragraphs)
            filtered_vectors = get_filtered_elements(page, final_table_sections, paragraphs, raw_lines)
            
            # im.draw_rects(paragraphs, stroke="red", stroke_width=3)

            # 3. GROUP VECTORS INTO FIGURE CANDIDATES

################################################## non bs 88888            
            # v_groups = group_boxes(filtered_vectors, margin=MARGIN)
            # figure_candidates = merge_groups(filtered_vectors, v_groups)

            # candidate_fig_sections = []

            # # Ensure figures are processed top-to-bottom
            # figure_candidates.sort(key=lambda x: x[1])

            # for f_bbox in figure_candidates:
            #     f_x0, f_top, f_x1, f_bottom = f_bbox
                
            #     # 1. FIND THE NEAREST CAPTION PARAGRAPH BELOW THE FIGURE
            #     for idx, para in enumerate(paragraphs):
            #         # Must be below the figure
            #         if para['top'] < f_bottom - 5:
            #             continue

            #         # Search lines within this paragraph for the Bold "Figure [number]" trigger
            #         contains_bold_caption = False
            #         para_lines = [l for l in lines if l['top'] >= para['top'] and l['bottom'] <= para['bottom']]
                    
            #         for l in para_lines:
            #             # Matches: "Figure 1", "Figure A.1", "Figure B.12", etc.
            #             if is_bold(l) and re.match(r"^Figure\s+([A-Z]\.)?\d+", l['text'], re.I):
            #                 contains_bold_caption = True
            #                 break
                    
            #         if contains_bold_caption:
            #             # Once we find the first valid caption below the figure, 
            #             # it is typically the correct one. We break to avoid 
            #             # catching Figure 2's caption for Figure 1.
            #             target_caption_idx = idx
            #             break

            #     # 2. SWALLOW ALL PARAGRAPHS BETWEEN FIGURE AND TARGET CAPTION
            #     if contains_bold_caption:
            #         current_sec_x0 = f_x0
            #         current_sec_x1 = f_x1

            #         # Iterate through paragraphs to merge everything in the gap
            #         for idx, para in enumerate(paragraphs):

            #             # If paragraph is between the figure bottom and the found caption's bottom
            #             if para['top'] >= f_top and para['bottom'] <= paragraphs[target_caption_idx]['bottom'] + 2:
            #                 # Expand the bounding box to encompass intermediate text

            #                 current_sec_x0 = min(current_sec_x0, para['x0'])
            #                 current_sec_x1 = max(current_sec_x1, para['x1'])

            #         combined_bbox = (current_sec_x0, f_top, current_sec_x1, paragraphs[target_caption_idx]['bottom'])
            #         candidate_fig_sections.append(combined_bbox)
            #     else:
            #         # Optional: If no caption is found, keep the original figure box
            #         candidate_fig_sections.append((f_x0, f_top, f_x1, f_bottom))


#################### bs 8888
            v_groups = group_boxes(filtered_vectors, margin=MARGIN)
            figure_candidates = merge_groups(filtered_vectors, v_groups)

            candidate_fig_sections = []

            # SORT BOTTOM-TO-TOP (Highest 'top' value first)
            figure_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Also sort paragraphs bottom-to-top for consistent searching
            sorted_paras = sorted(paragraphs, key=lambda x: x['top'], reverse=True)

            raw_lines_sorted = sorted(raw_lines, key=lambda x: x['top'], reverse=True)
            # im.draw_rects(paragraphs, stroke="blue", stroke_width=3)
            for f_bbox in figure_candidates:
                f_x0, f_top, f_x1, f_bottom = f_bbox
                found_caption = None
                # print("Current figure\n")
                # print(f_bbox)
                for l in raw_lines_sorted:
                    # print(f"line text: {l['text']}", f"line bottom: {l['bottom']}", f"f top: {f_top}")
                    # print("")
                    # for word in l["words"]:
                    #     print(f"text: {word['text']}, bottom: {word['bottom']}, word: {f_top}")
                    # print(f"line text: {l['text']}")
                    # print(f"bottom: {l['bottom']}, word: {f_top}")
                    if l['bottom'] > f_top:
                        # print("This line entered here")
                        continue
                    if is_bold_words(l) and re.search(r"Figure\s+([A-Z]\.)?\d+", l['text'], re.I):
                        found_caption = l
                        # print("\nFound caption\n")
                        # print(l)
                        break

                # 2. UPDATE Bounding Box if Caption is Found
                if found_caption:
                    combined_bbox = (
                        min(f_x0, found_caption['x0']),
                        found_caption['top'], # Expand top to include caption
                        max(f_x1, found_caption['x1']),
                        f_bottom
                    )
                    candidate_fig_sections.append(combined_bbox)
                # else:
                #     candidate_fig_sections.append((f_x0, f_top, f_x1, f_bottom))

            # 5. FINAL MERGE
            if candidate_fig_sections:
                final_fig_groups = group_boxes(candidate_fig_sections, margin=0)
                final_figure_sections = merge_groups(candidate_fig_sections, final_fig_groups)
            else:
                final_figure_sections = []

            # im.draw_rects(figure_candidates, stroke="red", stroke_width=3)

            # 6. VISUALIZATION

            raw_lines = group_words_into_lines(processed_words)
            filtered_lines = filter_lines_in_tables(raw_lines, final_table_sections)
            filtered_lines = filter_lines_in_tables(filtered_lines, final_figure_sections)
            paragraphs = merge_lines_into_paragraphs(filtered_lines)
            
            # im.draw_rects(filtered_lines, stroke="red", stroke_width=3)

            final_paras = []
            for v in paragraphs:
                paragraph_bbox = obj_to_bbox(v)
        
                if any(is_inside(paragraph_bbox, t_bbox) for t_bbox in final_table_sections):
                    continue
                if any(is_inside(paragraph_bbox, f_bbox) for f_bbox in final_figure_sections):
                    continue
                final_paras.append(v)
            
            final_paras_bboxes = [
                [b["x0"], b["top"], b["x1"], b["bottom"]]
                for b in final_paras
            ]

            im.draw_rects(final_table_sections, stroke="blue", stroke_width=3)
            im.draw_rects(final_figure_sections, stroke="green", stroke_width=3)
            im.draw_rects(final_paras_bboxes, stroke="red", stroke_width=3)
            
            output_path = os.path.join(output_directory, f"page_{page_num}.png")
            im.save(output_path)
            print(f"Saved image of page {page_num} with bounding boxes.")

            page_results = format_page_data(
                page, 
                final_table_sections, 
                final_paras, 
                final_figure_sections
            )
            
            full_document.append({
                "page_number": i + 1,
                "contents": page_results
            })
            print(f"Processed Page {i+1}")

    json_export = os.path.join(output_directory, "results.json")

    # Export to JSON
    with open(json_export, "w", encoding="utf-8") as f:
        json.dump({"Document": full_document}, f, indent=4)


if __name__ == "__main__":
    process_pdf(PDF_PATH)