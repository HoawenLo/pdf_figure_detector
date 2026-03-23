def find_keyterm_in_pdf(model_filepath, to_search, show_top_results=10, verbose=False):
    """Main execution function to find a specific keyterm in a designated PDF.

    Initializes the sentence transformer model, sets the file paths, defines
    the search phrase, runs the search pipeline, and prints the formatted 
    results to the console.

    Returns:
        None
    """
    model_filepath = "/GINKGO/scratch/software/huggingface/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_filepath)

    for search_phrase, pdf_file in to_search:
        results = search_pipeline(pdf_file, search_phrase, model, show_top_results)
        
        if verbose:
            print("\n===== RESULTS (Highest → Lowest) =====\n")

            for r in results:
                print(f"[Page {r['page']}]")
                print(f"Final Score: {r.get('final_score', r.get('score'))}")
                if "semantic_score" in r:
                    print(f"Semantic Score: {r['semantic_score']}")
                    print(f"Keyword Score: {r['keyword_score']}")
                print("Text:")
                print(r["text"])
                print("-" * 70)

    return results
