import json

def process_and_export_json(media_file_path, text_file_path, output_file_path):
    """
    Merges figure/table data with text data based on title, 
    preserves all metadata from the text JSON, and exports to a new file.
    """
    try:
        # 1. Load the data from files
        with open(media_file_path, 'r', encoding='utf-8') as f:
            media_json = json.load(f)
        with open(text_file_path, 'r', encoding='utf-8') as f:
            text_json = json.load(f)

        # 2. Create a lookup map for media elements (Figures/Tables)
        media_map = {item['title']: item.get('extracted_elements', []) for item in media_json}

        merged_output = []

        # 3. Process the Text JSON
        for entry in text_json:
            # Copy all metadata (id, page, tags, etc.)
            new_entry = entry.copy()
            title = entry.get("title")
            
            # Initialize our new 'information' list
            information_list = []

            # A. Convert 'crops' (text) to the new format
            if "crops" in entry:
                for crop in entry["crops"]:
                    information_list.append({
                        "category": "text",
                        "contents": crop.get("contents"),
                        "coordinates": crop.get("bbox"),
                        "page": crop.get("page") or entry.get("page")
                    })
                # Remove the old 'crops' key
                del new_entry["crops"]

            # B. Inject matching 'extracted_elements' (Figures/Tables)
            if title in media_map:
                information_list.extend(media_map[title])

            # C. Assign the unified list back to the entry
            new_entry["information"] = information_list
            merged_output.append(new_entry)

        # 4. Export the final result
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(merged_output, f, indent=4, ensure_ascii=False)

        print(f"Successfully created: {output_file_path}")
        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False

# Example Usage:
# process_and_export_json('media_source.json', 'text_source.json', 'final_merged_output.json')