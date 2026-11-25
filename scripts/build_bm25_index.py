"""Build and query a reproducible BM25 keyword index for clinical retrieval chunks.

The index contains only token statistics and chunk IDs.  Source text and
citations remain in data/processed/retrieval_chunks.jsonl.
"""

import argparse
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


import sys

sys.stdout.reconfigure(encoding="utf-8")


PROJECT_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = PROJECT_DIR / "data" / "processed" / "retrieval_chunks.jsonl"
INDEX_DIRECTORY = PROJECT_DIR / "data" / "indexes"
INDEX_FILE = INDEX_DIRECTORY / "clinical_bm25_index.json"
METADATA_FILE = INDEX_DIRECTORY / "clinical_bm25_index_metadata.json"

K1 = 1.5
B = 0.75
STOP_WORDS = {
    "a", "ai", "aie", "aient", "ainsi", "au", "aucun", "aucune", "aura", "avec",
    "ce", "ces", "cet", "cette", "comme", "dans", "de", "des", "du", "elle", "en",
    "est", "et", "il", "ils", "je", "la", "le", "les", "leur", "leurs", "lui", "ma",
    "mais", "me", "mes", "mon", "ne", "nos", "notre", "nous", "on", "ou", "par", "pas",
    "pour", "que", "qui", "sa", "sans", "se", "ses", "son", "sur", "ta", "te", "tes",
    "toi", "ton", "tu", "un", "une", "vos", "votre", "vous", "y", "the", "and", "or",
    "of", "to", "in", "for", "with", "from", "is", "are", "be", "by", "at", "as",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").casefold())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return [token for token in normalize(text).split() if len(token) >= 2 and token not in STOP_WORDS]


def load_chunks() -> list[dict]:
    return [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_index(chunks: list[dict]) -> tuple[dict, dict]:
    """Build inverted BM25 statistics over the same corpus used by embeddings."""
    postings = defaultdict(list)
    document_lengths = []
    for document_index, chunk in enumerate(chunks):
        counts = Counter(tokenize(chunk["embedding_text"]))
        document_lengths.append(sum(counts.values()))
        for term, frequency in counts.items():
            postings[term].append([document_index, frequency])

    index = {
        "schema_version": "1.0",
        "algorithm": "BM25",
        "parameters": {"k1": K1, "b": B},
        "document_count": len(chunks),
        "average_document_length": sum(document_lengths) / len(document_lengths) if document_lengths else 0,
        "document_ids": [chunk["retrieval_chunk_id"] for chunk in chunks],
        "document_lengths": document_lengths,
        "postings": dict(sorted(postings.items())),
    }
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_chunks_file": str(CHUNKS_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "index_file": str(INDEX_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "algorithm": "BM25",
        "parameters": {"k1": K1, "b": B},
        "normalization": "casefold, accent removal, non-alphanumeric replacement",
        "token_policy": "tokens with two or more characters; French/English stop-word list removed",
        "indexed_field": "embedding_text (DCI + section + evidence text)",
        "document_count": len(chunks),
        "unique_term_count": len(postings),
        "average_document_length": index["average_document_length"],
        "chunk_id_count": len(index["document_ids"]),
    }
    return index, metadata


def score(index: dict, question: str) -> list[float]:
    """Calculate BM25 scores for a question against all indexed chunks."""
    document_count = index["document_count"]
    scores = [0.0] * document_count
    average_length = index["average_document_length"] or 1
    query_terms = set(tokenize(question))
    for term in query_terms:
        term_postings = index["postings"].get(term)
        if not term_postings:
            continue
        document_frequency = len(term_postings)
        inverse_document_frequency = math.log(1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
        for document_index, frequency in term_postings:
            length = index["document_lengths"][document_index]
            denominator = frequency + index["parameters"]["k1"] * (1 - index["parameters"]["b"] + index["parameters"]["b"] * length / average_length)
            scores[document_index] += inverse_document_frequency * frequency * (index["parameters"]["k1"] + 1) / denominator
    return scores


def query(index: dict, chunks: list[dict], question: str, top_k: int, medicine_id: str | None = None) -> list[dict]:
    scores = score(index, question)
    eligible = range(len(scores)) if medicine_id is None else (
        document_index for document_index, chunk in enumerate(chunks)
        if chunk["medicine_id"] == medicine_id
    )
    order = sorted(eligible, key=lambda item: (-scores[item], index["document_ids"][item]))[:top_k]
    return [
        {
            "rank": rank,
            "score": round(scores[document_index], 6),
            "retrieval_chunk_id": chunks[document_index]["retrieval_chunk_id"],
            "parent_passage_id": chunks[document_index]["parent_passage_id"],
            "medicine_id": chunks[document_index]["medicine_id"],
            "standardized_dci": chunks[document_index]["standardized_dci"],
            "section": chunks[document_index]["section"],
            "page_start": chunks[document_index]["page_start"],
            "page_end": chunks[document_index]["page_end"],
            "text": chunks[document_index]["text"],
        }
        for rank, document_index in enumerate(order, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/query the clinical BM25 keyword index.")
    parser.add_argument("--query", help="Optional question: print BM25 top results after building/loading.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of results to print for --query.")
    parser.add_argument("--medicine-id", help="Optional filter such as M002 after medicine identification.")
    parser.add_argument("--rebuild", action="store_true", help="Force a rebuild before querying.")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive.")

    chunks = load_chunks()
    expected_ids = [chunk["retrieval_chunk_id"] for chunk in chunks]
    rebuild = args.rebuild or not INDEX_FILE.exists()
    if not rebuild:
        index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        rebuild = index.get("document_ids") != expected_ids
    if rebuild:
        INDEX_DIRECTORY.mkdir(parents=True, exist_ok=True)
        index, metadata = build_index(chunks)
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Built BM25 index: {len(chunks)} chunks, {metadata['unique_term_count']} unique terms")
    else:
        index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        print(f"Loaded BM25 index: {index['document_count']} chunks")

    if args.query:
        print(f"Question: {args.query}")
        if args.medicine_id:
            print(f"Medicine filter: {args.medicine_id}")
        for result in query(index, chunks, args.query, args.top_k, args.medicine_id):
            print(f"{result['rank']}. {result['retrieval_chunk_id']} | score={result['score']} | {result['standardized_dci']} | pages {result['page_start']}-{result['page_end']}")
            print(f"   {result['text']}")


if __name__ == "__main__":
    main()
