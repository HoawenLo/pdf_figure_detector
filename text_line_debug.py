import pdfplumber
import os

def is_in_body(top, bottom, page_height, top_margin_pct=0.08, bottom_margin_pct=0.05):
    """
    Checks if coordinates are within the main body of the page.
    Uses 8% for the header (top) and 5% for the footer (bottom).
    """
    header_limit = page_height * top_margin_pct
    footer_limit = page_height * (1 - bottom_margin_pct)
    
    # Return True only if the word is entirely within the body area
    return top > header_limit and bottom < footer_limit

def process_word_data(word, offset_value):
    """
    Determines if a word needs an offset based on font style.
    Returns (x0, new_top, x1, new_bottom, color, status)
    """
    font = (word.get("fontname") or "").lower()
    is_styled = any(x in font for x in ["bold", "italic", "oblique"])
    
    x0, top, x1, bottom = word["x0"], word["top"], word["x1"], word["bottom"]
    
    if not is_styled:
        return x0, top - offset_value, x1, bottom - offset_value, "red", "Shifted"
    else:
        return x0, top, x1, bottom, "blue", "Original"

def process_pdf_to_dir(input_path, output_directory):
    offset_value = 24.03
    os.makedirs(output_directory, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(input_path))[0]

    with pdfplumber.open(input_path) as pdf:
        # Processing pages
        pages_to_process = pdf.pages
        
        for i, page in enumerate(pages_to_process):
            page_num = i
            all_words = page.extract_words(extra_attrs=["fontname"])
            
            img_orig = page.to_image(resolution=150)
            img_off = page.to_image(resolution=150)
            
            p_orig_txt = os.path.join(output_directory, f"{base_name}_pg{page_num}_ORIGINAL.txt")
            p_off_txt = os.path.join(output_directory, f"{base_name}_pg{page_num}_OFFSET.txt")

            with open(p_orig_txt, "w", encoding="utf-8") as f_orig, \
                 open(p_off_txt, "w", encoding="utf-8") as f_off:
                
                header_row = f"{'Word':<20} | {'X0':<10} | {'Top':<10} | {'Font'}\n"
                f_orig.write(header_row + "-"*75 + "\n")
                f_off.write(header_row + "-"*75 + "\n")

                for word in all_words:
                    # 1. Process Offset First
                    nx0, ntop, nx1, nbot, color, status = process_word_data(word, offset_value)

                    # 2. Filter based on the NEW coordinates (8% Top / 5% Bottom)
                    if is_in_body(ntop, nbot, page.height, top_margin_pct=0.08, bottom_margin_pct=0.05):
                        
                        # Save Original Data (for words that passed the offset filter)
                        f_orig.write(f"{word['text'][:20]:<20} | {word['x0']:<10.2f} | {word['top']:<10.2f} | {word['fontname']}\n")
                        img_orig.draw_rect([word['x0'], word['top'], word['x1'], word['bottom']], stroke="blue")

                        # Save Offset Data
                        f_off.write(f"{word['text'][:20]:<20} | {nx0:<10.2f} | {ntop:<10.2f} | {word['fontname']}\n")
                        img_off.draw_rect([nx0, ntop, nx1, nbot], stroke=color)

            img_orig.save(os.path.join(output_directory, f"{base_name}_pg{page_num}_ORIGINAL.png"))
            img_off.save(os.path.join(output_directory, f"{base_name}_pg{page_num}_OFFSET.png"))
            print(f"Page {page_num} saved. (Margins: Top 8%, Bottom 5%)")

# Run
process_pdf_to_dir("main.pdf", "text_line_debug")