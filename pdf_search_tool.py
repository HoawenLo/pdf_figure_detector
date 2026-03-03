from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer, util
import torch

# Load model once
model = SentenceTransformer("all-MiniLM-L6-v2")


# -------------------------------------------------
# 1️⃣ Exact Phrase Search
# -------------------------------------------------
def exact_search_pdf(pdf_path, phrase):
    reader = PdfReader(pdf_path)
    matches = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and phrase.lower() in text.lower():
            matches.append({
                "page": i + 1,
                "match_type": "exact",
                "similarity": 1.0,
                "text": phrase
            })

    return matches


# -------------------------------------------------
# 2️⃣ Semantic Search (Ordered Top X)
# -------------------------------------------------
def semantic_search_top_x(pdf_path, phrase, top_n=5):
    reader = PdfReader(pdf_path)

    # Collect all candidate sentences
    sentences = []
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        for sentence in text.split("."):
            cleaned = sentence.strip()
            if len(cleaned) > 5:
                sentences.append(cleaned)
                pages.append(i + 1)

    if not sentences:
        return []

    # Encode in batch (fast)
    phrase_embedding = model.encode(phrase, convert_to_tensor=True)
    sentence_embeddings = model.encode(sentences, convert_to_tensor=True)

    # Compute similarity
    scores = util.cos_sim(phrase_embedding, sentence_embeddings)[0]

    # Get top X (already sorted descending by torch.topk)
    top_n = min(top_n, len(scores))
    top_scores, top_indices = torch.topk(scores, k=top_n)

    results = []
    for score, idx in zip(top_scores, top_indices):
        results.append({
            "page": pages[idx],
            "match_type": "semantic",
            "similarity": round(score.item(), 4),
            "text": sentences[idx]
        })

    # Explicitly ensure descending order (extra safety)
    results.sort(key=lambda x: x["similarity"], reverse=True)

    return results


# -------------------------------------------------
# 3️⃣ Unified Search Pipeline
# -------------------------------------------------
def search_pipeline(pdf_path, phrase, top_n=5):
    print("🔍 Running exact search...")
    exact_matches = exact_search_pdf(pdf_path, phrase)

    if exact_matches:
        print("✅ Exact match found.")
        return exact_matches

    print("❌ No exact match found.")
    print(f"🧠 Running semantic search (Top {top_n})...")

    return semantic_search_top_x(pdf_path, phrase, top_n=top_n)


# -------------------------------------------------
# Example Usage
# -------------------------------------------------
if __name__ == "__main__":
    pdf_file = "document.pdf"
    search_phrase = "terminate the agreement"

    results = search_pipeline(pdf_file, search_phrase, top_n=10)

    print("\nResults (Highest → Lowest):\n")

    for r in results:
        print(f"[Page {r['page']}]  Score: {r['similarity']}")
        print(r["text"])
        print("-" * 70)
