"""Script Name: keyword_pdf_search.py
Purpose: For the engineering checking application with AI. With the materials checking use case after extracting the British Standard
and material from the engineering drawing the application searches a database of British Standards related to materials to find the
relevant one. It then performs a keyword search in pdf to find the page related to temper and grade of the material.

The keyword search has an exact keyword matching function and a semantic matching method. Both scores are weighted and combined
to return the top results.

Usage: Feeds into the main script TBD
Author: Hoawen Lo
Date: """

import re
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer, util

# -------------------------------------------------
# 1️⃣ Exact Phrase Search
# -------------------------------------------------
def exact_search_pdf(reader, phrase):
    """Searches a PDF for exact matches of a specified phrase.

    Args:
        reader (PyPDF2.PdfReader): The PdfReader object containing the PDF pages.
        phrase (str): The exact string phrase to search for within the PDF.

    Returns:
        list[dict]: A list of dictionaries containing the page number, match type,
            score (1.0 for exact), and the matched text.
    """
    matches = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and phrase.lower() in text.lower():
            matches.append({
                "page": i + 1,
                "match_type": "exact",
                "score": 1.0,
                "text": phrase
            })

    return matches


# -------------------------------------------------
# 2️⃣ Sentence Splitting
# -------------------------------------------------
def split_into_sentences(text):
    """Splits a block of text into individual sentences for semantic analysis.

    Args:
        text (str): The raw input text extracted from a PDF page.

    Returns:
        list[str]: A list of cleaned sentences that are longer than 5 characters.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 5]


# -------------------------------------------------
# 3️⃣ Keyword Overlap Score
# -------------------------------------------------
def keyword_overlap_score(query, sentence):
    """Calculates the keyword overlap score between a query and a sentence.

    This computes the ratio of overlapping words to the total number of words
    in the query, ignoring case and punctuation.

    Args:
        query (str): The search phrase or query.
        sentence (str): The sentence to compare against the query.

    Returns:
        float: A score between 0.0 and 1.0 representing the ratio of query words
            found in the sentence. Returns 0.0 if the query is empty.
    """
    query_words = set(re.findall(r'\w+', query.lower()))
    sentence_words = set(re.findall(r'\w+', sentence.lower()))

    if not query_words:
        return 0.0

    overlap = query_words.intersection(sentence_words)
    return len(overlap) / len(query_words)


# -------------------------------------------------
# 4️⃣ Hybrid Semantic Search
# -------------------------------------------------
def hybrid_search_top_x(reader, phrase, model,
                        top_n=5,
                        semantic_weight=0.7,
                        keyword_weight=0.3):
    """Performs a hybrid search combining semantic similarity and keyword overlap.

    Args:
        reader (PyPDF2.PdfReader): The PdfReader object containing the PDF pages.
        phrase (str): The phrase or query to search for.
        model (sentence_transformers.SentenceTransformer): The loaded embedding model.
        top_n (int, optional): The maximum number of top results to return. Defaults to 5.
        semantic_weight (float, optional): The weight applied to the semantic similarity score. Defaults to 0.7.
        keyword_weight (float, optional): The weight applied to the keyword overlap score. Defaults to 0.3.

    Returns:
        list[dict]: A list of dictionaries representing the top matches sorted by final_score. 
            Each dictionary contains the page number, final combined score, semantic score, 
            keyword score, and the matching sentence text.
    """
    sentences = []
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        for sentence in split_into_sentences(text):
            sentences.append(sentence)
            pages.append(i + 1)

    if not sentences:
        return []

    phrase_embedding = model.encode(phrase, convert_to_tensor=True)
    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    cosine_scores = util.cos_sim(phrase_embedding, sentence_embeddings)

    results = []

    for idx, sentence in enumerate(sentences):
        semantic_score = cosine_scores[idx].item()
        keyword_score = keyword_overlap_score(phrase, sentence)

        final_score = (
            semantic_score * semantic_weight +
            keyword_score * keyword_weight
        )

        results.append({
            "page": pages[idx],
            "final_score": round(final_score, 4),
            "semantic_score": round(semantic_score, 4),
            "keyword_score": round(keyword_score, 4),
            "text": sentence
        })

    results.sort(key=lambda x: x["final_score"], reverse=True)

    return results[:top_n]


# -------------------------------------------------
# 5️⃣ Unified Search Pipeline
# -------------------------------------------------
def search_pipeline(pdf_path, phrase, model, top_n=5):
    """Executes the complete search pipeline: exact match fallback to hybrid search.

    Attempts to find an exact match first. If no exact matches are found, it falls
    back to the hybrid semantic search method.

    Args:
        pdf_path (str): The file path to the PDF document.
        phrase (str): The search phrase or query.
        model (sentence_transformers.SentenceTransformer): The loaded embedding model.
        top_n (int, optional): The number of top results to return for hybrid search. Defaults to 5.

    Returns:
        list[dict]: A list of dictionaries containing the search results, either from the
            exact match or the hybrid semantic search.
    """
    print("📖 Reading PDF...")
    reader = PdfReader(pdf_path)

    print("🔍 Running exact search...")
    exact_matches = exact_search_pdf(reader, phrase)

    if exact_matches:
        print("✅ Exact match found.")
        return exact_matches

    print("❌ No exact match found.")
    print(f"🧠 Running hybrid semantic search (Top {top_n})...")

    return hybrid_search_top_x(reader, phrase, model=model, top_n=top_n)


def find_keyterm_in_pdf():
    """Main execution function to find a specific keyterm in a designated PDF.

    Initializes the sentence transformer model, sets the file paths, defines
    the search phrase, runs the search pipeline, and prints the formatted 
    results to the console.

    Returns:
        None
    """
    model_filepath = "/GINKGO/scratch/software/huggingface/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_filepath)
    pdf_file = "/GINKGO/home/hwlo/engineering_drawings_prototype/data/raw/BS EN 755-2-2025--[2026-02-11--04-05-35 PM].pdf"
    search_phrase = "Aluminium Alloy Grade EN AW-6082-T6"
    top_results = 10

    results = search_pipeline(pdf_file, search_phrase, model, top_results)

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
