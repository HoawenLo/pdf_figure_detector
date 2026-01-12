import json
import os
import re

# --- CONFIGURATION ---
PAGE_WIDTH = 595.276
PAGE_HEIGHT = 841.89
VLM_SCALE = 1000  # Standard scale for VLM spatial reasoning

# --- 1. COORDINATE UTILITIES ---

def scale_bbox(bbox, src_w, src_h, dst_w, dst_h, as_int=False):
    """
    Scales [x0, top, x1, bottom] from one dimension to another.
    """
    x0, top, x1, bottom = bbox
    
    x_scale = dst_w / src_w
    y_scale = dst_h / src_h
    
    scaled = [
        x0 * x_scale,
        top * y_scale,
        x1 * x_scale,
        bottom * y_scale
    ]
    
    return [int(v) for v in scaled] if as_int else [round(v, 2) for v in scaled]

# --- 2. PROMPT GENERATOR ---

def get_vlm_prompt(normalized_extractions):
    """
    Constructs the full auditor prompt with normalized JSON data.
    """
    return f'''
You are a professional **Document Layout Auditor**. Your task is to evaluate the accuracy of a PDF extraction tool page-by-page. 

## Page Context
- **Actual Dimensions:** Width: 595.276, Height: 841.89
- **Coordinate System:** [x0, top, x1, bottom] (Normalized to a 0-1000 scale for spatial reasoning).

---

## Content Categories & Layout Rules

### 1. Figures (Green Bounding Boxes)
- **Visuals:** Diagrams
- **Captions:** Usually prefixed with "Figure [Number]" or "Figure [Letter].[Number]". These can be **ABOVE or BELOW** the figure.
- **Notes/Keys/Labels:** These are part of the figure. They may appear:
    - Between the figure and the caption.
    - **Inside** the figure's visual area (if the figure has a border).
- **Audit Rule:** The Green box MUST encapsulate the visual, the caption, and all associated notes/keys.

### 2. Tables (Blue Bounding Boxes)
- **Visuals:** Grid-based data, rows, and columns.
- **Captions:** Usually prefixed with "Table [Number]". These are **ALWAYS ABOVE** the table.
- **Audit Rule:** The Blue box MUST include both the caption and the entire tabular area.

### 3. Text (Red Bounding Boxes)
- **Content:** Standard body prose and paragraphs.
- **Exclusion:** Must NOT contain text related to figures and tables such as figure captions, table captions, figure notes or table text.

---

## Verification Instructions

Analyse the provided image and the extraction data below. An extraction is correct ONLY when the box fully surrounds the relevant content, matches its category, includes all captions/notes, and does not overlap others.

1. **Category Integrity:** Confirm content matches its label (e.g., ensure Blue boxes contain tabular data, not prose).
2. **Encapsulation & Accuracy:** Verify boxes fully enclose the intended content without cutting off text, figure or table (like "Source:" or "Note:"). 
3. **Ghost Captions:** Identify Red (Text) boxes that contain figure/table captions or notes. These are errors; they must be merged into the relevant Green or Blue box.
4. **Table Integrity:** Ensure Blue boxes are not partial tables or prose mislabeled as tables.

---

## Current Extractions for this Page
{json.dumps(normalized_extractions, indent=2)}

---

## Output Requirements

Return a JSON list of objects. Provide an assessment for every box provided in the input, plus any "missing" boxes you find. Also remove irrelevant boxes if there are any.

**Each object must follow this schema:**
- `bounding_box`: [x0, top, x1, bottom] (Provide the CORRECTED coordinates on the 0-1000 scale).
- `error_type`: "na" (correct), "missing" (new box), or "adjusted" (resized or reclassified).
   - **na**: Correct box and category.
   - **adjusted**: Box exists but requires resizing, repositioning, or category correction.
   - **missing**: A required bounding box is missing entirely.
- `category`: "text", "table", or "figure".
- `content`: 
    - Reuse the original content string if `error_type` is "na".
    - Use "TBD" if `error_type` is "missing" or "adjusted".
- `comment`: A brief explanation of the error or "na".

**Example Format:**
[
  {{
    "bounding_box": [150, 200, 850, 450],
    "error_type": "adjusted",
    "category": "table",
    "content": "TBD",
    "comment": "Expanded box upward to include the table caption which was previously in a red text box."
  }}
]
'''

# --- 3. MAIN WORKFLOW ---

def run_page_audit(page_data, page_image):
    """
    The full cycle: 
    1. Scale UP (Normalize) -> 2. Ask VLM -> 3. Scale DOWN (Denormalize)
    """
    
    # --- STEP A: NORMALIZE (Prepare for VLM) ---
    raw_extractions = page_data.get('contents', [])
    norm_extractions = []
    for item in raw_extractions:
        norm_box = scale_bbox(item['coordinates'], PAGE_WIDTH, PAGE_HEIGHT, VLM_SCALE, VLM_SCALE, as_int=True)
        norm_extractions.append({
            "category": item['Category'],
            "coordinates": norm_box,
            "contents": item['contents']
        })

    # --- STEP B: CALL VLM ---
    prompt = get_vlm_prompt(norm_extractions)
    
    # # This is your actual model call (e.g., Phi-4)
    # # It returns a JSON string based on the 0-1000 scale
    vlm_json_string = call_phi4_model(image=page_image, prompt=prompt) 
    
    # # Convert string response to Python list
    vlm_output_list = json.loads(vlm_json_string)

    # # --- STEP C: DENORMALIZE (The Missing Piece) ---
    # # We take the VLM's 0-1000 coordinates and turn them back into 595.276 units
    final_corrected_data = []
    
    for obj in vlm_output_list:
    #     # Scale back to PDF units
        actual_box = scale_bbox(
            obj['coordinates'], 
            src_w=VLM_SCALE, src_h=VLM_SCALE, # From 1000
            dst_w=PAGE_WIDTH, dst_h=PAGE_HEIGHT # To 595.276
        )
        
        # Update the object with the real-world coordinates
        obj['coordinates'] = actual_box
        final_corrected_data.append(obj)

    return final_corrected_data

def process_document(directory):
    """
    directory: Contains document.json and page images named page_1.jpg, page_2.jpg, ...
    """

    # Load JSON
    json_path = os.path.join(directory, "results.json")
    with open(json_path, "r") as f:
        document_json = json.load(f)

    # Collect and sort page images
    image_paths = sorted(
        [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if re.match(r"page_\d+\.(png|jpg|jpeg)$", f, re.IGNORECASE)
        ],
        key=lambda x: int(re.search(r"page_(\d+)", x).group(1))
    )

    pages = document_json.get("Document", {})
    all_audit_results = []

    if len(image_paths) != len(pages):
        print(f"⚠️ Warning: Number of images does not match number of pages. Number of images: {len(image_paths)}, number of pages: {len(pages)}")

    for i, page_data in enumerate(pages):
        page_image = image_paths[i]

        print(f"--- Auditing Page {i + 1} ---")
        print(f"Image: {os.path.basename(page_image)}")
        audited_page_data = run_page_audit(page_data, page_image)

        # # need to load image with PIL in run page audit
        # all_audit_results.append(audited_page_data)

    return all_audit_results

if __name__ == "__main__":
    target_directory = "/home/hoawen/projects/pdf_figure_detector/outputs/BS 8888-2025--[2026-01-07--03-27-26 PM].pdf"
    process_document(target_directory)
