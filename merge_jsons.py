import json

def merge_and_preserve(media_json, text_json):
    # 1. Create a lookup map for the media elements (figures/tables)
    media_map = {item['title']: item.get('extracted_elements', []) for item in media_json}

    merged_output = []

    for entry in text_json:
        # Create a copy of the entry to avoid mutating the original data
        new_entry = entry.copy()
        
        # 2. Extract title for matching
        title = entry.get("title")
        
        # 3. Initialize the information list
        information_list = []

        # 4. Transform 'crops' (text) into the 'information' format
        if "crops" in entry:
            for crop in entry["crops"]:
                text_element = {
                    "category": "text",
                    "contents": crop.get("contents"),
                    "coordinates": crop.get("bbox"),
                    # Inherit page from the crop or the parent entry
                    "page": crop.get("page") or entry.get("page")
                }
                information_list.append(text_element)
            
            # Remove the old 'crops' key so it doesn't clutter the new JSON
            del new_entry["crops"]

        # 5. Inject the media elements (figures/tables) if title matches
        if title in media_map:
            information_list.extend(media_map[title])

        # 6. Assign the new unified list to the entry
        new_entry["information"] = information_list
        
        merged_output.append(new_entry)

    return merged_output