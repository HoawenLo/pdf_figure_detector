import base64
import io
from PIL import Image

def run_compliance_audit(merged_json_data, project_drawing_path, pipeline):
    """
    Iterates through the document and runs the VLM checker for each section.
    """
    audit_results = {}

    for section in merged_json_data:
        title = section.get("title")
        print(f"--- Auditing Section: {title} ---")

        # 1. Prepare the text query
        query = prepare_bs_audit_query(section)

        # 2. Prepare the images (Standard References + Target Drawing)
        images_to_check = []
        
        # Extract figures/tables from the JSON
        for item in section.get("information", []):
            if item["category"] in ["figure", "table"]:
                try:
                    img_data = base64.b64decode(item["contents"])
                    ref_img = Image.open(io.BytesIO(img_data))
                    images_to_check.append(ref_img)
                except Exception as e:
                    print(f"Error decoding visual reference in {title}: {e}")

        # Add the actual project drawing to the list of images
        try:
            target_drawing = Image.open(project_drawing_path)
            images_to_check.append(target_drawing)
        except Exception as e:
            print(f"Error loading project drawing: {e}")
            continue

        # 3. Pass to your existing pipeline
        # Note: We pass the list of images. Your pipeline's processor 
        # will handle the multi-image input.
        response = pipeline.run_vlm(
            query=query, 
            image=images_to_check, 
            chat_history=[]
        )

        audit_results[title] = response
        print(f"Result: {response[:100]}...") # Print preview of result

    return audit_results

def prepare_bs_audit_query(section_entry):
    """
    Formats the BS 2025 requirements into a text query.
    """
    # Use full_hierarchy for maximum context, fall back to joined trail
    hierarchy = section_entry.get("full_hierarchy")
    if not hierarchy and "trail" in section_entry:
        hierarchy = " > ".join(section_entry["trail"])
    
    # Extract text categories from the information list
    requirements = [
        item["contents"] 
        for item in section_entry.get("information", []) 
        if item["category"] == "text"
    ]
    
    # Format the specs as a numbered list
    formatted_requirements = "\n".join([f"{i+1}. {text}" for i, text in enumerate(requirements)])

    # Construct the query string that will be passed into your pipeline
    query = f"""
### BRITISH STANDARDS 2025 AUDIT
**Section:** {section_entry.get('title')}
**Hierarchy:** {hierarchy}

**TECHNICAL REQUIREMENTS:**
{formatted_requirements}

**TASK:**
You are provided with reference figures/tables from the standard and an engineering drawing. 
Determine if the project drawing complies with the BS 2025 requirements listed above. 
Identify any missing dimensions, incorrect symbology, or alignment issues.
"""
    return query