"""Compare lexical and semantic retrieval on one processed clinical document.

This is intentionally a retrieval-only experiment: it returns source passages
and citations, never a generated medical answer.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# The selected model is downloaded once, then experiments must remain
# reproducible and runnable without an internet connection.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = PROJECT_DIR / "Pharmeazor" / "documents" / "Ibuprofène" / "processed" / (
    "IBUPROFENE ALMUS 400 mg, comprimé pelliculé RCP _passages.json"
)
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def compact(text: str, length: int = 360) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def filename_label(value: str) -> str:
    """Make a short, portable filename label supplied by the experimenter."""
    label = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return label[:60] or "custom_query"


def format_results(passages: list[dict], scores: np.ndarray, top_k: int) -> list[dict]:
    order = np.argsort(-scores)[:top_k]
    return [
        {
            "rank": rank,
            "score": round(float(scores[index]), 4),
            "passage_id": passages[index]["passage_id"],
            "section": passages[index]["section"],
            "page_start": passages[index]["page_start"],
            "page_end": passages[index]["page_end"],
            # Results must retain all retrieved evidence for manual relevance
            # assessment. A shortened preview is used only in terminal output.
            "text": passages[index]["text"],
        }
        for rank, index in enumerate(order, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare keyword and vector retrieval on processed RCP passages.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="One *_passages.json file.")
    parser.add_argument("--question", required=True, help="French retrieval question to test.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of passages to return per method.")
    parser.add_argument("--label", default="custom_query", help="Short name included in the saved result filename.")
    args = parser.parse_args()

    corpus_path = args.corpus.resolve()
    document = json.loads(corpus_path.read_text(encoding="utf-8"))
    passages = document["passages"]
    texts = [passage["text"] for passage in passages]
    if not texts:
        raise ValueError("The selected processed document has no passages.")

    # Lexical retrieval: terms must occur in the passage, so it is a useful
    # baseline for the Week 2 'recherche par mots-clés' comparison.
    lexical_vectorizer = TfidfVectorizer(lowercase=True, strip_accents="unicode", ngram_range=(1, 2))
    lexical_matrix = lexical_vectorizer.fit_transform(texts)
    lexical_question = lexical_vectorizer.transform([args.question])
    lexical_scores = (lexical_matrix @ lexical_question.T).toarray().ravel()

    # Semantic retrieval: each passage and the question become a multilingual
    # embedding vector; normalized dot product is cosine similarity.
    model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    passage_vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    question_vector = model.encode([args.question], normalize_embeddings=True, show_progress_bar=False)[0]
    semantic_scores = np.asarray(passage_vectors @ question_vector)

    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Retrieval-only experiment on one processed document; not a medical answer.",
        "corpus": str(corpus_path.relative_to(PROJECT_DIR)),
        "medicine_id": document["medicine_id"],
        "standardized_dci": document["standardized_dci"],
        "passage_count": len(passages),
        "question": args.question,
        "embedding_model": EMBEDDING_MODEL,
        "keyword_tfidf_results": format_results(passages, lexical_scores, args.top_k),
        "semantic_vector_results": format_results(passages, semantic_scores, args.top_k),
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    results_file = PROJECT_DIR / "results" / f"ibuprofen_test_{filename_label(args.label)}_{timestamp}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    results_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Corpus: {payload['corpus']} ({len(passages)} passages)")
    print(f"Question: {args.question}\n")
    for label, results in (("Keyword / TF-IDF", payload["keyword_tfidf_results"]),
                           ("Semantic / vectors", payload["semantic_vector_results"])):
        print(label)
        for item in results:
            print(f"  {item['rank']}. {item['passage_id']} | score={item['score']} | pages {item['page_start']}-{item['page_end']}")
            print(f"     {compact(item['text'])}")
        print()
    print(f"Saved: {results_file.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
