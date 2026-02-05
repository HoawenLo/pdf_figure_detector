import os
import json
import base64
import io
from PIL import Image

def prepare_bs_audit_query(section_entry):
    """Formats the BS 2025 requirements into a text query."""
    hierarchy = section_entry.get("full_hierarchy") or " > ".join(section_entry.get("trail", []))
    
    requirements = [
        item["contents"] 
        for item in section_entry.get("information", []) 
        if item["category"] == "text"
    ]
    
    formatted_requirements = "\n".join([f"{i+1}. {text}" for i, text in enumerate(requirements)])

    return f"""
### BRITISH STANDARDS 2025 AUDIT
**Section:** {section_entry.get('title')}
**Hierarchy:** {hierarchy}

**TECHNICAL REQUIREMENTS:**
{formatted_requirements}

**TASK:**
Compare the provided engineering drawing against these BS 2025 requirements. 
The first images are reference figures from the standard. The final image is the project drawing.
Identify any non-compliance or errors.
"""

def main_audit_pipeline(json_path, images_folder, output_path, model_filepath):
    """
    End-to-end function to audit a folder of images against the British Standards JSON.
    """
    # 1. Initialize the Pipeline (using your original class)
    pipeline = GenerationPipeline(model_filepath)

    # 2. Load Resources
    with open(json_path, 'r', encoding='utf-8') as f:
        merged_data = json.load(f)
    
    valid_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp')
    project_image_paths = [
        os.path.join(images_folder, f) 
        for f in os.listdir(images_folder) 
        if f.lower().endswith(valid_extensions)
    ]

    all_audit_reports = {}

    # 3. Process every image in the folder
    for img_path in project_image_paths:
        img_name = os.path.basename(img_path)
        drawing_report = {}
        print(f"\n[AUDIT] Processing: {img_name}")

        # 4. For each drawing, check every section of the Standard
        for section in merged_data:
            title = section.get("title")
            query = prepare_bs_audit_query(section)

            # Gather reference images (b64) and the target drawing (file)
            images_to_check = []
            for item in section.get("information", []):
                if item["category"] in ["figure", "table"]:
                    try:
                        img_data = base64.b64decode(item["contents"])
                        images_to_check.append(Image.open(io.BytesIO(img_data)))
                    except Exception as e:
                        print(f"  ! Error decoding reference for {title}: {e}")

            try:
                images_to_check.append(Image.open(img_path))
            except Exception as e:
                print(f"  ! Could not open project image {img_name}: {e}")
                continue

            # Run the VLM via your existing pipeline
            print(f"  - Checking section: {title}")
            response = pipeline.run_vlm(
                query=query,
                image=images_to_check,
                chat_history=[]
            )
            drawing_report[title] = response

        all_audit_reports[img_name] = drawing_report

    # 5. Export Results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_audit_reports, f, indent=4, ensure_ascii=False)

    print(f"\n[SUCCESS] Audit complete. Report saved to: {output_path}")

if __name__ == "__main__":
    main_audit_pipeline(
        json_path="merged_bs2025.json", 
        images_folder="./drawings_to_check", 
        output_path="final_audit_report.json",
        model_filepath="models/vlm-check-v1"
    )