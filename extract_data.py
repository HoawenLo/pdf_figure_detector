import os

from new_detect_figures import process_pdf

# Master output directory
master_output_dir = "temp"
target_dir = "target_documents"

# List all files in the directory
all_files = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]

# Ensure the master directory exists
os.makedirs(master_output_dir, exist_ok=True)

# Loop through each document
for doc in all_files:

    print(f"Currently processing document: {doc}")

    # Create a subdirectory for the document
    doc_output_dir = os.path.join(master_output_dir, doc)
    os.makedirs(doc_output_dir, exist_ok=True)

    target_filepath = os.path.join(target_dir, doc)
    process_pdf(target_filepath, doc_output_dir)
    print(f"Outputs exported to {target_filepath}")

print(all_files)
