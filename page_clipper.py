import json
import os
import re
import io
import base64
import pdfplumber
from PyPDF2 import PdfReader

# --- Utility Functions ---

def image_to_base64(img_obj):
    """Converts a pdfplumber image object to a base64 string for JSON embedding."""
    buffered = io.BytesIO()
    img_obj.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str

class PDFBookmarkExtractor:
    def __init__(self, pdf_path):
        self.reader = PdfReader(pdf_path)

    def extract(self):
        outlines = self.reader.outline
        if not outlines:
            print(f"Outlines empty.")
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
    """Locates the Y coordinate of the section header."""
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
    """Filters the flat list to a specific range (e.g., Section 7 to 8)."""
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

# --- Processing & Image Capture ---

def process_selected_sections(pdf_path, full_headings, selected_headings):
    """Calculates Multi-page BBoxes and captures images as Base64."""
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for heading in selected_headings:
            if not heading['is_section']:
                continue

            start_page_idx = heading['page']
            y_start = find_text_top(pdf.pages[start_page_idx], heading['title']) or 60
            
            end_page_idx = len(pdf.pages) - 1
            y_end = pdf.pages[end_page_idx].height
            
            # Look ahead to find where this section ends
            try:
                master_idx = full_headings.index(heading)
                if master_idx + 1 < len(full_headings):
                    next_h = full_headings[master_idx + 1]
                    end_page_idx = next_h['page']
                    found_y_end = find_text_top(pdf.pages[end_page_idx], next_h['title'])
                    if found_y_end is not None:
                        y_end = found_y_end
            except (ValueError, IndexError):
                pass

            section_crops = []
            for p_idx in range(start_page_idx, end_page_idx + 1):
                page = pdf.pages[p_idx]
                
                # Logic to define top/bottom boundaries for this page slice
                if start_page_idx == end_page_idx:
                    t, b = y_start, y_end
                elif p_idx == start_page_idx:
                    t, b = y_start, page.height - 40
                elif p_idx == end_page_idx:
                    t, b = 60, y_end
                else:
                    t, b = 60, page.height - 40
                
                # Height threshold to ignore false-positive slivers
                slice_height = b - t
                if slice_height < 25: 
                    continue

                if b > t:
                    bbox = (30, t - 10, page.width - 30, b)
                    
                    # Capture the image and encode to base64
                    try:
                        cropped_page = page.crop(bbox)
                        img = cropped_page.to_image(resolution=150)
                        img_base64 = image_to_base64(img)
                    except Exception as e:
                        img_base64 = None
                        print(f"Error cropping {heading['title']} on pg {p_idx+1}: {e}")

                    section_crops.append({
                        'page_num': p_idx + 1,
                        'bbox': bbox,
                        'image_base64': img_base64
                    })

            results.append({
                'title': heading['title'],
                'hierarchy': " > ".join(heading['trail']),
                'crops': section_crops
            })
    return results

def export_to_json(results, output_path="dimensioning_sections.json"):
    """Saves the final structure to a JSON file."""
    export_list = []
    for section in results:
        entry = {
            "title": section['title'],
            "trail": section['hierarchy'].split(" > ") if section['hierarchy'] else [],
            "full_hierarchy": section['hierarchy'],
            "crops": [
                {
                    "page": crop['page_num'],
                    "bbox": [round(val, 2) for val in crop['bbox']],
                    "image_base64": crop['image_base64']
                } for crop in section['crops']
            ]
        }
        export_list.append(entry)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_list, f, indent=4, ensure_ascii=False)
    print(f"\nData successfully exported to {output_path}")

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

# --- Execution ---

def main():
    # 1. Setup paths
    filepath = "/home/hoawen/projects/pdf_figure_detector/target_documents/successful/BS 8888-2025--[2026-01-07--03-27-26 PM].pdf"
    
    # 2. Extract and Filter Bookmarks
    extractor = PDFBookmarkExtractor(filepath)
    all_headings = flatten_and_filter(extractor.extract())

    # 3. Select Range (Section 7 to 8)
    start_point = "7 Dimensioning"
    end_point = "8 Datums and datum systems"
    selected_range = select_bookmarks_between(all_headings, start_point, end_point)

    if not selected_range:
        print("No headings found in the specified range.")
        return

    # 4. Process and Capture Base64 Images
    print(f"Processing {len(selected_range)} sections. Encoding images to Base64...")
    final_sections = process_selected_sections(filepath, all_headings, selected_range)
    
    # 5. Export
    export_to_json(final_sections, "dimensioning_sections.json")
    
    save_visual_crops(filepath, final_sections)

    # 6. Console Summary
    print("\n" + "="*60)
    for s in final_sections:
        pages_str = ", ".join([str(c['page_num']) for c in s['crops']])
        print(f"{s['title']:<45} | Pages: {pages_str}")
    print("="*60)



if __name__ == "__main__":
    main()