import json

def is_inside(content_coords, section_bbox):
    """
    Checks if the content coordinates fall within the section bounding box.
    """
    c_left, c_top, c_right, c_bottom = content_coords
    s_left, s_top, s_right, s_bottom = section_bbox
    
    # Check vertical midpoint
    content_midpoint_y = (c_top + c_bottom) / 2
    return s_top <= content_midpoint_y <= s_bottom

def filter_sections(section_map_path, page_data_path):
    with open(section_map_path, 'r') as f:
        sections = json.load(f)
        
    with open(page_data_path, 'r') as f:
        page_data = json.load(f)["Document"]

    pages_dict = {p['page_number']: p['contents'] for p in page_data}
    
    refined_output = []
    # Define allowed categories
    ALLOWED_CATEGORIES = ["table", "figure"]

    for section in sections:
        section_content = {
            "title": section['title'],
            "full_hierarchy": section['full_hierarchy'],
            "extracted_elements": []
        }
        
        for crop in section['crops']:
            page_num = crop['page']
            bbox = crop['bbox']
            
            if page_num in pages_dict:
                for element in pages_dict[page_num]:
                    # NEW: Filter by coordinates AND category
                    category = element.get('Category', '').lower()
                    
                    if category in ALLOWED_CATEGORIES and is_inside(element['coordinates'], bbox):
                        section_content['extracted_elements'].append({
                            "category": category,
                            "contents": element.get('contents'), # This might be the base64 image or table data
                            "coordinates": element['coordinates'],
                            "page": page_num
                        })
        
        # Only add the section to output if it actually contains figures or tables
        if section_content['extracted_elements']:
            refined_output.append(section_content)
    
    return refined_output

# --- Execution ---
if __name__ == "__main__":
    SECTION_MAP = "dimensioning_sections.json"
    PAGE_DATA = "/home/hoawen/projects/pdf_figure_detector/outputs/BS 8888-2025--[2026-01-07--03-27-26 PM].pdf/results.json"
    
    final_data = filter_sections(SECTION_MAP, PAGE_DATA)
    
    with open("final_section_visuals.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=4)

    # Preview Output
    print(f"Filtering complete. Found visuals in {len(final_data)} sections.")
    for item in final_data:
        print(f"\n--- {item['full_hierarchy']} ---")
        for el in item['extracted_elements']:
            print(f"[{el['category'].upper()}] found on page {el['page']}")