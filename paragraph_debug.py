import pdfplumber
import os

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
            "text": " ".join(w["text"] for w in line)
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

def process_pdf_to_dir(input_path, output_directory):
    offset_val = 24.03
    os.makedirs(output_directory, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(input_path))[0]

    with pdfplumber.open(input_path) as pdf:
        for i, page in enumerate(pdf.pages):
            all_words = page.extract_words(extra_attrs=["fontname"])
            
            # Step 1 & 2: Apply Offset and Filter by Margins
            processed_words = []
            for w in all_words:
                nx0, ntop, nx1, nbot, color, status = process_word_offset(w, offset_val)
                
                if is_in_body(ntop, nbot, page.height):
                    # Attach the calculated values to the word object for grouping
                    w.update({"nx0": nx0, "new_top": ntop, "nx1": nx1, "new_bottom": nbot, "color": color})
                    processed_words.append(w)

            # Step 3: Grouping
            lines = group_words_into_lines(processed_words)
            paragraphs = merge_lines_into_paragraphs(lines)

            # Step 4: Visual and Text Output
            img = page.to_image(resolution=150)
            txt_path = os.path.join(output_directory, f"{base_name}_pg{i}_PARAGRAPHS.txt")

            with open(txt_path, "w", encoding="utf-8") as f:
                for idx, para in enumerate(paragraphs):
                    f.write(f"--- BLOCK {idx+1} ---\n{para['text']}\n\n")
                    img.draw_rect([para["x0"], para["top"], para["x1"], para["bottom"]], 
                                  stroke="green", stroke_width=2)

            img.save(os.path.join(output_directory, f"{base_name}_pg{i}_DEBUG.png"))
            print(f"Processed Page {i} (Found {len(paragraphs)} paragraphs)")

# Run
process_pdf_to_dir("main.pdf", "paragraph_debug")