import re
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer, util


# -------------------------------------------------
# 1️⃣ Exact Phrase Search
# -------------------------------------------------
def exact_search_pdf(reader, phrase):
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
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 5]


# -------------------------------------------------
# 3️⃣ Keyword Overlap Score
# -------------------------------------------------
def keyword_overlap_score(query, sentence):
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
                        semantic_weight=0.8,
                        keyword_weight=0.2):

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

    cosine_scores = util.cos_sim(phrase_embedding, sentence_embeddings)[0]

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
def search_pipeline(pdf_path, phrase, top_n=5):
    print("🔄 Loading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("📖 Reading PDF...")
    reader = PdfReader(pdf_path)

    print("🔍 Running exact search...")
    exact_matches = exact_search_pdf(reader, phrase)

    if exact_matches:
        print("✅ Exact match found.")
        return exact_matches

    print("❌ No exact match found.")
    print(f"🧠 Running hybrid semantic search (Top {top_n})...")

    return hybrid_search_top_x(reader, phrase, model, top_n=top_n)


# -------------------------------------------------
# Example Usage (edit directly here)
# -------------------------------------------------
if __name__ == "__main__":

    pdf_file = "document.pdf"
    search_phrase = "terminate the agreement"
    top_results = 5

    results = search_pipeline(pdf_file, search_phrase, top_results)

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
