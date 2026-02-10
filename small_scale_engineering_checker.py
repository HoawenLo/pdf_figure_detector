import os
import re
import json
from PIL import Image

def natural_sort_key(s):
    """Sorts strings numerically: figure_1, figure_2, figure_10."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def run_vlm_batch_process(folder_list, eng_drawing_path, output_name="batch_results"):
    all_results = []
    
    # Text file for quick reading
    txt_output_path = f"{output_name}.txt"
    json_output_path = f"{output_name}.json"

    with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
        for folder in folder_list:
            if not os.path.isdir(folder):
                continue

            # 1. Load the Prompt
            prompt_path = os.path.join(folder, 'prompt_template.txt')
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_text = f.read()

            # 2. Sort and Load Figures
            files = os.listdir(folder)
            figure_files = sorted([f for f in files if f.startswith('figure_') and f.endswith('.png')], key=natural_sort_key)
            
            image_sequence = [Image.open(os.path.join(folder, f)).convert("RGB") for f in figure_files]
            
            # 3. Read and Add Engineering Drawing (Direct Filepath)
            eng_img = Image.open(eng_drawing_path).convert("RGB")
            image_sequence.append(eng_img)

            # 4. RUN VLM PIPELINE
            print(f"Processing folder: {folder}")
            # response = your_vlm_function(prompt_text, image_sequence)
            response = "Simulated VLM Analysis Output." # Placeholder for your function

            # 5. Export to Text File (Clean Format)
            txt_file.write(f"FOLDER: {os.path.basename(folder)}\n")
            txt_file.write(f"RESPONSE: {response}\n")
            txt_file.write("-" * 50 + "\n")

            # 6. Store for JSON (Detailed Format)
            all_results.append({
                "folder": folder,
                "response": response,
                "images_processed": figure_files + [os.path.basename(eng_drawing_path)]
            })

    # 7. Finalize JSON export
    with open(json_output_path, 'w', encoding='utf-8') as jf:
        json.dump(all_results, jf, indent=4)

    print(f"Done! Results saved to {txt_output_path} and {json_output_path}")

# --- EXECUTION ---
folders = ['./job_001', './job_002']
spec_drawing = '/absolute/path/to/engineering_drawing.png'

run_vlm_batch_process(folders, spec_drawing)