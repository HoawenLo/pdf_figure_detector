def find_keyterm_in_pdf(model_filepath, to_search, show_top_results=10, verbose=False):
    """Executes a batch search for keyterms across multiple PDF files.

    Initializes the Sentence Transformer model once and iterates through a list of 
    search queries and their corresponding PDF paths. It utilizes a unified 
    search pipeline (exact then hybrid) to locate relevant information.

    Args:
        model_filepath (str): The local filesystem path to the pre-trained 
            SentenceTransformer model.
        to_search (list[tuple[str, str]]): A list of tuples where each tuple 
            contains (search_phrase, pdf_file_path).
        show_top_results (int, optional): The maximum number of results to 
            retrieve per search. Defaults to 10.
        verbose (bool, optional): If True, prints detailed scoring and text 
            snippets to the console for each match. Defaults to False.

    Returns:
        list[dict]: The results from the final search in the `to_search` list. 
            Note: If searching multiple items, only the last result set is 
            currently returned.
    """
    # Note: You currently have a hardcoded path overriding your parameter here:
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
