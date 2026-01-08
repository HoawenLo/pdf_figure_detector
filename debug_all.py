import os

from debug import main

master_output_dir = "debug"
target_dir = "target_documents"

# List all files in the directory
all_files = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]





# Ensure the master directory exists
os.makedirs(master_output_dir, exist_ok=True)

# Loop through each document
for doc in all_files:

    dirs = {
        "chars": os.path.join("debug", doc, "char_debug"),
        "diagrams": os.path.join("debug", doc, "diagram_debug"),
        "paras": os.path.join("debug", doc, "paragraph_debug"),
        "tables": os.path.join("debug", doc, "table_debug"),
        "offsets": os.path.join("debug", doc, "text_line_debug"),
        "vectors": os.path.join("debug", doc, "vector_debug"),
    }

    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    print(f"Currently processing document: {doc}")

    target_filepath = os.path.join(target_dir, doc)
    main(target_filepath, dirs)
    print(f"Outputs exported.")