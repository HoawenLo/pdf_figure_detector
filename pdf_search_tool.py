from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer, util

# Load semantic model once (global for efficiency)
model = SentenceTransformer("all-MiniLM-L6-v2")


# -----------------------------------
# 1️⃣ Exact Phrase Search
# -----------------------------------
def exact_search_pdf(pdf_path, phrase):
    reader = PdfReader(pdf_path)
    matches = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and phrase.lower() in text.lower():
            matches.append({
                "page": i + 1,
                "match_type": "exact"
            })

    return matches


# -----------------------------------
# 2️⃣ Semantic (Paraphrase) Search
# -----------------------------------
def semantic_search_pdf(pdf_path, phrase, threshold=0.65):
    reader = PdfReader(pdf_path)
    phrase_embedding = model.encode(phrase, convert_to_tensor=True)

    matches = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        # Simple sentence split (can improve with nltk if needed)
        sentences = text.split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 5:
                continue

            sentence_embedding = model.encode(sentence, convert_to_tensor=True)
            similarity = util.cos_sim(phrase_embedding, sentence_embedding).item()

            if similarity >= threshold:
                matches.append({
                    "page": i + 1,
                    "match_type": "semantic",
                    "similarity": round(similarity, 3),
                    "text": sentence
                })

    return matches


# -----------------------------------
# 3️⃣ Unified Search Pipeline
# -----------------------------------
def search_pipeline(pdf_path, phrase, semantic_threshold=0.65):
    print("🔍 Running exact search...")
    exact_matches = exact_search_pdf(pdf_path, phrase)

    if exact_matches:
        print("✅ Exact match found.")
        return exact_matches

    print("❌ No exact match found.")
    print("🧠 Running semantic search...")
    
    semantic_matches = semantic_search_pdf(
        pdf_path, phrase, threshold=semantic_threshold
    )

    if semantic_matches:
        print("✅ Semantic matches found.")
    else:
        print("❌ No semantic matches found.")

    return semantic_matches


# -----------------------------------
# Example Usage
# -----------------------------------
if __name__ == "__main__":
    pdf_file = "document.pdf"
    search_phrase = "terminate the agreement"

    results = search_pipeline(pdf_file, search_phrase)

    print("\nResults:")
    for r in results:
        print(r)
