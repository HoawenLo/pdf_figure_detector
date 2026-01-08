import pdfplumber
import os
import re
import json
import base64
from io import BytesIO
from collections import defaultdict

class BritishStandardExtractor:
    def __init__(self, mode="default", resolution=150, margin=8, offset_val=24.03):
        self.mode = mode
        self.resolution = resolution
        self.margin = margin
        self.offset_val = offset_val
        self.output_dir = "main_output"

    # --- UTILITY METHODS ---
    def obj_to_bbox(self, obj):
        return [float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"])]

    def is_bold_words(self, line):
        return any("bold" in w.get("fontname", "").lower() for w in line.get("words", []))

    def is_bold_chars(self, line):
        return any("bold" in c.get("fontname", "").lower() for c in line["chars"])

    def is_inside(self, obj_bbox, target_bbox):
        return (obj_bbox[0] >= target_bbox[0] - 4 and
                obj_bbox[1] >= target_bbox[1] - 4 and
                obj_bbox[2] <= target_bbox[2] + 4 and
                obj_bbox[3] <= target_bbox[3] + 4)

    def boxes_intersect(self, a, b, margin=10):
        return not (b[0] > a[2] + margin or b[2] < a[0] - margin or
                    b[1] > a[3] + margin or b[3] < a[1] - margin)

    def group_boxes(self, boxes, margin=15):
        n = len(boxes)
        if n == 0: return []
        graph = defaultdict(list)
        for i in range(n):
            for j in range(i + 1, n):
                if self.boxes_intersect(boxes[i], boxes[j], margin=margin):
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

    def merge_groups(self, boxes, groups):
        return [[min(boxes[i][0] for i in g), min(boxes[i][1] for i in g),
                 max(boxes[i][2] for i in g), max(boxes[i][3] for i in g)] for g in groups]

    # --- TEXT PROCESSING ---
    def is_in_body(self, top, bottom, page_height):
        header_limit = page_height * 0.08
        footer_limit = page_height * (1 - 0.05)
        return top > header_limit and bottom < footer_limit

    def process_word_offset(self, word):
        font = (word.get("fontname") or "").lower()
        is_styled = any(x in font for x in ["bold", "italic", "oblique"])
        x0, top, x1, bottom = word["x0"], word["top"], word["x1"], word["bottom"]
        if not is_styled:
            return x0, top - self.offset_val, x1, bottom - self.offset_val
        return x0, top, x1, bottom

    def get_raw_lines(self, page):
        all_words = page.extract_words(extra_attrs=["fontname"])
        processed_words = []
        for w in all_words:
            nx0, ntop, nx1, nbot = self.process_word_offset(w)
            if self.is_in_body(ntop, nbot, page.height):
                w.update({"nx0": nx0, "new_top": ntop, "nx1": nx1, "new_bottom": nbot})
                processed_words.append(w)

        if not processed_words: return []
        processed_words.sort(key=lambda w: (w["new_top"], w["nx0"]))
        
        lines, current_line = [], [processed_words[0]]
        for next_word in processed_words[1:]:
            if abs(next_word["new_top"] - current_line[-1]["new_top"]) <= 3:
                current_line.append(next_word)
            else:
                lines.append(current_line)
                current_line = [next_word]
        lines.append(current_line)
        
        line_blocks = []
        for line in lines:
            line_blocks.append({
                "x0": min(w["nx0"] for w in line), "top": min(w["new_top"] for w in line),
                "x1": max(w["nx1"] for w in line), "bottom": max(w["new_bottom"] for w in line),
                "text": " ".join(w["text"] for w in line), "words": line
            })
        return line_blocks

    def merge_lines_into_paragraphs(self, line_blocks, x_tolerance=10, y_tolerance=12):
        if not line_blocks: return []
        paragraphs = [[line] for line in line_blocks]
        merged = True
        while merged:
            merged = False
            new_paragraphs = []
            while paragraphs:
                curr_para = paragraphs.pop(0)
                has_merged = False
                c_x0 = min(l["x0"] for l in curr_para); c_top = min(l["top"] for l in curr_para)
                c_x1 = max(l["x1"] for l in curr_para); c_bot = max(l["bottom"] for l in curr_para)
                for i, other_para in enumerate(new_paragraphs):
                    o_x0 = min(l["x0"] for l in other_para); o_top = min(l["top"] for l in other_para)
                    o_x1 = max(l["x1"] for l in other_para); o_bot = max(l["bottom"] for l in other_para)
                    if not (c_x0 - x_tolerance > o_x1 or c_x1 + x_tolerance < o_x0 or 
                            c_top - y_tolerance > o_bot or c_bot + y_tolerance < o_top):
                        new_paragraphs[i].extend(curr_para)
                        has_merged = True; merged = True; break
                if not has_merged: new_paragraphs.append(curr_para)
            paragraphs = new_paragraphs
        
        final_paras = []
        for p in paragraphs:
            p.sort(key=lambda l: l["top"])
            final_paras.append({
                "x0": min(l["x0"] for l in p), "top": min(l["top"] for l in p),
                "x1": max(l["x1"] for l in p), "bottom": max(l["bottom"] for l in p),
                "text": "\n".join(l["text"] for l in p)
            })
        return sorted(final_paras, key=lambda b: b["top"])

    # --- TABLE DETECTION ---
    def detect_tables(self, page, raw_lines):
        if self.mode == "bs8888":
            heavy_segments = [l for l in page.lines if 2.2 <= float(l.get('linewidth', 0)) <= 2.3]
            groups = defaultdict(list)
            for seg in heavy_segments: groups[round(seg['top'], 1)].append(seg)
            merged_borders = []
            for y, segments in groups.items():
                merged_borders.append({'top': y, 'bottom': y, 'x0': min(s['x0'] for s in segments), 'x1': max(s['x1'] for s in segments)})
            merged_borders.sort(key=lambda x: x['top'])
            
            final_sections = []
            for text_line in raw_lines:
                if self.is_bold_words(text_line) and re.search(r"Table\s+([A-Z]\.)?\d+", text_line['text'], re.I):
                    borders_below = [b for b in merged_borders if b['top'] >= text_line['bottom'] - 2]
                    if len(borders_below) >= 2:
                        final_sections.append((min(text_line['x0'], borders_below[0]['x0'], borders_below[1]["x0"]), text_line['top'], 
                                               max(text_line['x1'], borders_below[0]['x1'], borders_below[1]['x1']), borders_below[1]['bottom']))
            return final_sections
        else:
            tables = page.find_tables()
            lines = page.extract_text_lines()
            
            final_table_sections = []
            
            for t_obj in tables:
                t_bbox = t_obj.bbox
                t_sect = list(t_bbox)
                found_table_caption = False
                
                for line in lines:
                    # Logic: Must be Bold and Start with "Table [Number]"
                    if self.is_bold_chars(line) and re.match(r"^Table\s+([A-Z]\.)?\d+", line['text'], re.I):
                        # Distance check: Caption must be above and within 35px
                        dist = t_bbox[1] - line['bottom']
                        if 0 < dist < 35:
                            found_table_caption = True
                            # Merge caption into the section bbox
                            t_sect[1] = line['top'] 
                            t_sect[0] = min(t_sect[0], line['x0'])
                            t_sect[2] = max(t_sect[2], line['x1'])
                            break # Found the caption for this specific table
                
                # ONLY add if caption was found
                if found_table_caption:
                    final_table_sections.append(tuple(t_sect))
            return final_table_sections

    # --- FIGURE DETECTION ---
    def detect_figures(self, page, paragraphs, raw_lines, table_bboxes):
        all_vectors = [self.obj_to_bbox(v) for v in (page.lines + page.rects + page.curves)]
        filtered_v = [v for v in all_vectors if self.is_in_body(v[1], v[3], page.height)]
        filtered_v = [v for v in filtered_v if not any(self.is_inside(v, t) for t in table_bboxes) 
                      and not any(self.is_inside(v, [p['x0'], p['top'], p['x1'], p['bottom']]) for p in paragraphs)]
        
        v_groups = self.group_boxes(filtered_v, margin=self.margin)
        figure_candidates = self.merge_groups(filtered_v, v_groups)
        candidate_fig_sections = []

        if self.mode == "bs8888":
            figure_candidates.sort(key=lambda x: x[1], reverse=True)
            raw_lines_sorted = sorted(raw_lines, key=lambda x: x['top'], reverse=True)
            for f_bbox in figure_candidates:
                f_x0, f_top, f_x1, f_bottom = f_bbox
                found_caption = None
                for l in raw_lines_sorted:
                    if l['bottom'] > f_top: continue
                    if self.is_bold_words(l) and re.search(r"Figure\s+([A-Z]\.)?\d+", l['text'], re.I):
                        found_caption = l; break
                if found_caption:
                    candidate_fig_sections.append((min(f_x0, found_caption['x0']), found_caption['top'], max(f_x1, found_caption['x1']), f_bottom))
        else:
            figure_candidates.sort(key=lambda x: x[1])
            for f_bbox in figure_candidates:
                f_x0, f_top, f_x1, f_bottom = f_bbox
                target_caption_idx = None
                for idx, para in enumerate(paragraphs):
                    if para['top'] < f_bottom - 5: continue
                    if re.search(r"^Figure\s+([A-Z]\.)?\d+", para['text'], re.I):
                        target_caption_idx = idx; break
                if target_caption_idx is not None:
                    c_x0, c_x1 = f_x0, f_x1
                    for para in paragraphs:
                        if para['top'] >= f_top and para['bottom'] <= paragraphs[target_caption_idx]['bottom'] + 2:
                            c_x0, c_x1 = min(c_x0, para['x0']), max(c_x1, para['x1'])
                    candidate_fig_sections.append((c_x0, f_top, c_x1, paragraphs[target_caption_idx]['bottom']))
                else:
                    candidate_fig_sections.append(tuple(f_bbox))

        final_fig_groups = self.group_boxes(candidate_fig_sections, margin=0)
        return self.merge_groups(candidate_fig_sections, final_fig_groups)

    # --- OUTPUT GENERATION ---
    def get_image_data(self, page, bbox):
        try:
            crop = page.crop(bbox)
            img = crop.to_image(resolution=self.resolution)
            buffered = BytesIO()
            img.original.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except: return None

    def process_pdf(self, path, output_directory):
        self.output_dir = output_directory
        os.makedirs(self.output_dir, exist_ok=True)
        full_document = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages[10:11]):
                raw_lines = self.get_raw_lines(page)

                final_table_sections = self.detect_tables(page, raw_lines)
                
                # Initial merge to identify potential figures
                temp_filtered = [l for l in raw_lines if not any(self.is_inside(self.obj_to_bbox(l), t) for t in final_table_sections)]
                temp_paras = self.merge_lines_into_paragraphs(temp_filtered)
                
                final_figure_sections = self.detect_figures(page, temp_paras, raw_lines, final_table_sections)
                
                # Final merge for actual paragraphs
                final_filtered_lines = [l for l in temp_filtered if not any(self.is_inside(self.obj_to_bbox(l), f) for f in final_figure_sections)]
                final_paras = self.merge_lines_into_paragraphs(final_filtered_lines)

                # Visualization
                im = page.to_image(resolution=self.resolution)
                im.draw_rects(final_table_sections, stroke="blue", stroke_width=3)
                im.draw_rects(final_figure_sections, stroke="green", stroke_width=3)
                im.draw_rects([[p['x0'], p['top'], p['x1'], p['bottom']] for p in final_paras], stroke="red", stroke_width=3)
                im.save(os.path.join(self.output_dir, f"page_{i+1}.png"))

                # Formatting Data
                page_contents = []
                for t in final_table_sections:
                    page_contents.append({"Category": "table", "contents": page.crop(t).extract_table(), "coordinates": list(t)})
                for p in final_paras:
                    page_contents.append({"Category": "paragraph", "contents": p["text"], "coordinates": [p["x0"], p["top"], p["x1"], p["bottom"]]})
                for f in final_figure_sections:
                    page_contents.append({"Category": "figure", "contents": self.get_image_data(page, f), "coordinates": list(f)})
                
                page_contents.sort(key=lambda x: x["coordinates"][1])
                full_document.append({"page_number": i + 1, "contents": page_contents})
                print(f"Processed Page {i+1}")

        with open(os.path.join(self.output_dir, "results.json"), "w", encoding="utf-8") as f:
            json.dump({"Document": full_document}, f, indent=4)