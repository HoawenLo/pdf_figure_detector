import os
from british_standards_extractor import BritishStandardExtractor

# --- CONFIGURATION ---
TARGET_DIR = "target_documents"
MASTER_OUTPUT_DIR = "temp"

def main():
    # Ensure the master directory exists
    os.makedirs(MASTER_OUTPUT_DIR, exist_ok=True)

    # List all PDF files in the target directory
    all_files = [f for f in os.listdir(TARGET_DIR) if f.lower().endswith(".pdf")]

    for doc in all_files:
        print(f"\n>>> Processing: {doc}")

        # --- AUTO-MODE SELECTION ---
        # If "8888" appears in the name, use the Script 1 logic.
        # Otherwise (ISO/EN documents), use the Script 2 logic.
        if "8888" in doc:
            mode = "bs8888"
        else:
            mode = "default"
        
        # Setup output path
        folder_name = os.path.splitext(doc)[0]
        doc_output_dir = os.path.join(MASTER_OUTPUT_DIR, folder_name)

        # Instantiate and run
        extractor = BritishStandardExtractor(mode=mode)
        target_filepath = os.path.join(TARGET_DIR, doc)
        
        # try:
        extractor.process_pdf(target_filepath, doc_output_dir)
        print(f"--- Successfully finished {doc} in '{mode}' mode.")
        # except Exception as e:
        #     print(f"!!! Error processing {doc}: {str(e)}")

    print("\nProcessing complete for all files.")

if __name__ == "__main__":
    main()