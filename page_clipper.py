import json
import os
import re
import pdfplumber
from PyPDF2 import PdfReader

class PDFBookmarkExtractor:
    def __init__(self, pdf_path):
        self.reader = PdfReader(pdf_path)

    def extract(self):
        outlines = self.reader.outline
        if not outlines:
            print(f"Outlines empty: {outlines}")
            return []
        return self._parse(outlines, level=0)
    
    def _parse(self, items, level):
        results = []
        items = items if isinstance(items, list) else [items]
        for item in items:
            if isinstance(item, list):
                if results:
                    results[-1]["children"].extend(self._parse(item, level + 1))
                continue
            node = {
                "title": self._get_title(item),
                "level": level,
                "page": self.reader.get_destination_page_number(item),
                "children": []
            }
            results.append(node)
        return results
    
    def _get_title(self, item):
        if hasattr(item, "title") and isinstance(item.title, str):
            return item.title
        if isinstance(item, dict) and "title" in item:
            return item["title"]
        return str(item)

# --- Logic Functions ---

def is_heading(title):
    """Regex to identify numbered sections or specific standard headers."""
    heading_regex = r'^(\d+\.?)+\s+|^Foreword|^Introduction'
    return bool(re.match(heading_regex, title.strip()))

def flatten_and_filter(bookmarks, flat_list=None, current_trail=None):
    """Flattens hierarchy into Headings only. A 'section' has no sub-headings."""
    if flat_list is None: flat_list = []
    if current_trail is None: current_trail = []

    for item in bookmarks:
        title = item['title'].strip()
        is_h = is_heading(title)
        has_heading_children = any(is_heading(child['title']) for child in item['children'])
        
        if is_h:
            node = {
                'title': title,
                'level': item['level'],
                'page': item['page'],
                'is_section': not has_heading_children,
                'trail': list(current_trail)
            }
            flat_list.append(node)
            if item['children']:
                flatten_and_filter(item['children'], flat_list, current_trail + [title])
        else:
            if item['children']:
                flatten_and_filter(item['children'], flat_list, current_trail)
    return flat_list

def find_text_top(page, title_text):
    """
    Locates the Y coordinate. Matches the section number (e.g. '7.2.1') 
    first to avoid false positives from page headers.
    """
    section_number = title_text.split()[0]
    words = page.extract_words()
    
    # 1. Try exact match on the section number
    for word in words:
        if word['text'].strip() == section_number:
            return word['top']
            
    # 2. Fallback to substring match
    search_text = re.sub(r'\s+', ' ', title_text).strip()
    for word in words:
        clean_word = re.sub(r'\s+', ' ', word['text']).strip()
        if clean_word and clean_word in search_text[:len(clean_word)+1]:
            return word['top']
    return None

def select_bookmarks_between(flat_headings, start_text, end_text):
    """Filters the flat list to a specific range."""
    def clean(s): return re.sub(r'\s+', ' ', str(s)).strip().lower()
    start_idx, end_idx = None, None
    clean_start, clean_end = clean(start_text), clean(end_text)

    for i, heading in enumerate(flat_headings):
        current_title = clean(heading['title'])
        if start_idx is None and clean_start in current_title:
            start_idx = i
        if start_idx is not None and clean_end in current_title:
            end_idx = i
            break
    
    if start_idx is None: return []
    return flat_headings[start_idx : (end_idx + 1 if end_idx is not None else None)]

def process_selected_sections(pdf_path, full_headings, selected_headings):
    """
    Calculates multi-page BBoxes. 
    A section spans from its title Y to the next heading's title Y.
    """
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for heading in selected_headings:
            
            if not heading['is_section']:
                continue
            
            # print(f"heading: {heading['title']}")

            start_page_idx = heading['page']

            # print(f"page num: {start_page_idx}")

            y_start = find_text_top(pdf.pages[start_page_idx], heading['title']) or 0
            
            # print(f"y_start: {y_start}")

            # Default: end of document
            end_page_idx = len(pdf.pages) - 1
            y_end = pdf.pages[end_page_idx].height
            
            # Find boundary in master list
            try:
                master_idx = full_headings.index(heading)

                # print(f"master index: {master_idx}")

                if master_idx + 1 < len(full_headings):
                    next_h = full_headings[master_idx + 1]
                    end_page_idx = next_h['page']
                    # print(f"next_h: {next_h['title']}")
                    found_y_end = find_text_top(pdf.pages[end_page_idx], next_h['title'])
                    if found_y_end is not None:
                        y_end = found_y_end
            except (ValueError, IndexError):
                pass

            # Generate a crop for every page the section touches
            section_crops = []
            for p_idx in range(start_page_idx, end_page_idx + 1):
                page = pdf.pages[p_idx]
                
                # CASE 1: The section starts and ends on this SAME page
                if start_page_idx == end_page_idx:
                    top_limit = y_start
                    bottom_limit = y_end
                
                # CASE 2: Multi-page section - This is the FIRST page
                elif p_idx == start_page_idx:
                    top_limit = y_start
                    bottom_limit = page.height - 40 # Go to the very bottom
                
                # CASE 3: Multi-page section - This is the LAST page
                elif p_idx == end_page_idx:
                    top_limit = 60 # Start from the very top
                    bottom_limit = y_end
                
                # CASE 4: Multi-page section - This is a MIDDLE page
                else:
                    top_limit = 60
                    bottom_limit = page.height - 40
                
                # print(f"Page index: {p_idx}")
                # print(f"start page index: {start_page_idx}")
                # print(f"end page index: {end_page_idx}")
                # print(f"Top Limit: {top_limit}")
                # print(f"Bottom Limit: {bottom_limit}\n")

                # if top_limit <= 60:
                #     continue

                slice_height = bottom_limit - top_limit
                
                if slice_height < 25: 
                    (f"Skipping tiny slice on page {p_idx+1}: {slice_height}pts")
                    continue

                # Final check to ensure we don't have a zero-height or inverted crop
                if bottom_limit > top_limit:
                    section_crops.append({
                        'page_num': p_idx + 1,
                        'bbox': (30, top_limit - 10, page.width - 30, bottom_limit)
                    })

            results.append({
                'title': heading['title'],
                'hierarchy': " > ".join(heading['trail']),
                'crops': section_crops
            })

            # print(section_crops)
            # print("\n")

    return results

def save_visual_crops(pdf_path, results, output_folder="debug_crops"):
    """Saves each crop as a PNG. Handles multi-page sections by creating multiple files."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    with pdfplumber.open(pdf_path) as pdf:
        for section in results:
            # Create a filesystem-safe name
            safe_title = re.sub(r'[^\w\s-]', '', section['title']).strip().replace(' ', '_')
            
            for crop in section['crops']:
                page = pdf.pages[crop['page_num'] - 1]
                try:
                    cropped_page = page.crop(crop['bbox'])
                    img = cropped_page.to_image(resolution=150)
                    filename = f"pg{crop['page_num']}_{safe_title}.png"
                    img.save(os.path.join(output_folder, filename))
                except Exception as e:
                    print(f"Error saving {section['title']} on pg {crop['page_num']}: {e}")
def export_to_json(results, output_path="section_data.json"):
    """
    Exports the processed sections, including trails and coordinates, to a JSON file.
    """
    export_list = []
    for section in results:
        entry = {
            "title": section['title'],
            "trail": section['hierarchy'].split(" > ") if section['hierarchy'] else [],
            "full_hierarchy": section['hierarchy'],
            "crops": [
                {
                    "page": crop['page_num'],
                    "bbox": [round(val, 2) for val in crop['bbox']] # [x0, top, x1, bottom]
                } for crop in section['crops']
            ]
        }
        export_list.append(entry)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_list, f, indent=4, ensure_ascii=False)
    print(f"Data successfully exported to {output_path}")

# --- Updated Execution ---

def main():
    filepath = "/home/hoawen/projects/pdf_figure_detector/target_documents/successful/BS 8888-2025--[2026-01-07--03-27-26 PM].pdf"
    
    # 1. Extraction
    extractor = PDFBookmarkExtractor(filepath)
    raw_bookmarks = extractor.extract()
    all_headings = flatten_and_filter(raw_bookmarks)

    # 2. User Selection
    start_point = "7 Dimensioning"
    end_point = "8 Datums and datum systems"
    selected_range = select_bookmarks_between(all_headings, start_point, end_point)

    if not selected_range:
        print("No headings found in selection.")
        return

    # 3. Processing
    print(f"Processing {len(selected_range)} headings (including multi-page spans)...")
    final_sections = process_selected_sections(filepath, all_headings, selected_range)
    
    # 4. Output: Save Images
    save_visual_crops(filepath, final_sections)
    
    # 5. Output: Export Structured Data (The requested final step)
    export_to_json(final_sections, "dimensioning_sections.json")
    
    # Optional print for console verification
    print("\n" + "="*80)
    print(f"{'Section Title':<45} | {'Pages'} | Coordinates")
    print("-" * 80)
    for s in final_sections:
        pages_str = ", ".join([str(c['page_num']) for c in s['crops']])
        bbox_str = ", ".join([f"T:{round(c['bbox'][1],1)} B:{round(c['bbox'][3],1)}" for c in s["crops"]])
        print(f"{s['title']:<45} | {pages_str:<10} | {bbox_str}")
    print("="*80)
    print(f"Success! Check the '{os.path.abspath('debug_crops')}' folder and 'dimensioning_sections.json'.")

if __name__ == "__main__":
    main()