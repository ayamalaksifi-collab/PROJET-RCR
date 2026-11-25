"""Build and query a persistent MiniLM vector index for clinical retrieval chunks.

The index is intentionally simple and transparent: a NumPy matrix of normalized
embeddings plus JSONL metadata with matching retrieval_chunk_id values.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent.parent
CHUNKS_FILE = PROJECT_DIR / "data" / "processed" / "retrieval_chunks.jsonl"
CHUNK_METADATA_FILE = PROJECT_DIR / "data" / "processed" / "retrieval_chunks_metadata.json"
INDEX_DIRECTORY = PROJECT_DIR / "data" / "indexes"
VECTORS_FILE = INDEX_DIRECTORY / "clinical_embeddings.npy"
VECTOR_METADATA_FILE = INDEX_DIRECTORY / "clinical_embedding_metadata.jsonl"
INDEX_METADATA_FILE = INDEX_DIRECTORY / "clinical_embedding_index_metadata.json"
PARTIAL_VECTORS_FILE = INDEX_DIRECTORY / "clinical_embeddings_in_progress.npy"
PROGRESS_FILE = INDEX_DIRECTORY / "clinical_embedding_progress.json"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_chunks() -> list[dict]:
    return [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, local_files_only=True)


def validate_chunks(chunks: list[dict], model: SentenceTransformer) -> None:
    """Fail early if Person 1's token-safe chunk contract was broken."""
    if not chunks:
        raise ValueError("No retrieval chunks found.")
    identifiers = [chunk["retrieval_chunk_id"] for chunk in chunks]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate retrieval_chunk_id values in retrieval chunk corpus.")
    oversized = [chunk for chunk in chunks if chunk.get("embedding_token_count", 0) > model.max_seq_length]
    if oversized:
        raise ValueError(f"{len(oversized)} chunks exceed the embedding model limit of {model.max_seq_length} tokens.")


def corpus_fingerprint(chunks: list[dict]) -> str:
    """Detect whether a checkpoint belongs to the current retrieval corpus."""
    joined = "\n".join(chunk["retrieval_chunk_id"] for chunk in chunks)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def clear_partial_build() -> None:
    for path in (PARTIAL_VECTORS_FILE, PROGRESS_FILE):
        if path.exists():
            path.unlink()


def build(chunks: list[dict], model: SentenceTransformer, batch_size: int, restart: bool = False) -> dict:
    """Embed in batches, persist progress, and resume safely after interruption."""
    validate_chunks(chunks, model)
    INDEX_DIRECTORY.mkdir(parents=True, exist_ok=True)
    fingerprint = corpus_fingerprint(chunks)
    total = len(chunks)
    dimension = model.get_sentence_embedding_dimension()
    start = 0

    if restart:
        clear_partial_build()
    if PARTIAL_VECTORS_FILE.exists() and PROGRESS_FILE.exists():
        progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        compatible = (
            progress.get("corpus_fingerprint") == fingerprint
            and progress.get("total_chunks") == total
            and progress.get("embedding_dimension") == dimension
        )
        if not compatible:
            raise ValueError(
                "The existing embedding checkpoint belongs to a different corpus. "
                "Run with --rebuild to discard it deliberately."
            )
        start = int(progress.get("completed_chunks", 0))
        vectors = np.lib.format.open_memmap(PARTIAL_VECTORS_FILE, mode="r+", dtype="float32", shape=(total, dimension))
        print(f"Resuming semantic index: {start}/{total} chunks ({start / total:.1%})")
    else:
        vectors = np.lib.format.open_memmap(PARTIAL_VECTORS_FILE, mode="w+", dtype="float32", shape=(total, dimension))

    for batch_start in range(start, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_texts = [chunk["embedding_text"] for chunk in chunks[batch_start:batch_end]]
        vectors[batch_start:batch_end] = model.encode(
            batch_texts,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")
        vectors.flush()
        progress = {
            "status": "building",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "embedding_model": MODEL_NAME,
            "corpus_fingerprint": fingerprint,
            "total_chunks": total,
            "completed_chunks": batch_end,
            "percent_complete": round(batch_end / total * 100, 2),
            "embedding_dimension": dimension,
            "batch_size": batch_size,
            "partial_vectors_file": str(PARTIAL_VECTORS_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        }
        write_json(PROGRESS_FILE, progress)
        print(f"Progress: {batch_end}/{total} chunks ({progress['percent_complete']}%)")

    del vectors
    PARTIAL_VECTORS_FILE.replace(VECTORS_FILE)
    vectors = np.load(VECTORS_FILE, mmap_mode="r")

    # Keep the metadata in exactly the same order as vector rows. This is the
    # lookup table from a vector result to its evidence/source citation.
    VECTOR_METADATA_FILE.write_text(
        "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    chunk_build = json.loads(CHUNK_METADATA_FILE.read_text(encoding="utf-8"))
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "embedding_model": MODEL_NAME,
        "model_max_seq_length": model.max_seq_length,
        "embedding_dimension": int(vectors.shape[1]),
        "vector_count": int(vectors.shape[0]),
        "vector_dtype": str(vectors.dtype),
        "normalization": "L2 normalized; vector dot product equals cosine similarity.",
        "input_chunks_file": str(CHUNKS_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "input_chunk_count": len(chunks),
        "input_chunk_max_tokens": chunk_build["configured_retrieval_chunk_max_tokens"],
        "vectors_file": str(VECTORS_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "metadata_file": str(VECTOR_METADATA_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "batch_size": batch_size,
    }
    write_json(INDEX_METADATA_FILE, metadata)
    write_json(PROGRESS_FILE, {
        "status": "complete",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_chunks": total,
        "completed_chunks": total,
        "percent_complete": 100.0,
        "vectors_file": str(VECTORS_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
    })
    return metadata


def load_index() -> tuple[np.ndarray, list[dict], dict]:
    vectors = np.load(VECTORS_FILE)
    chunks = [json.loads(line) for line in VECTOR_METADATA_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    metadata = json.loads(INDEX_METADATA_FILE.read_text(encoding="utf-8"))
    if vectors.shape[0] != len(chunks):
        raise ValueError("Saved vector rows do not match saved metadata rows.")
    return vectors, chunks, metadata


def semantic_query(model: SentenceTransformer, vectors: np.ndarray, chunks: list[dict], question: str,
                   top_k: int, medicine_id: str | None = None) -> list[dict]:
    query_vector = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    scores = vectors @ query_vector
    eligible = range(len(chunks)) if medicine_id is None else (
        index for index, chunk in enumerate(chunks) if chunk["medicine_id"] == medicine_id
    )
    order = sorted(eligible, key=lambda index: (-float(scores[index]), chunks[index]["retrieval_chunk_id"]))[:top_k]
    return [
        {
            "rank": rank,
            "score": round(float(scores[index]), 6),
            "retrieval_chunk_id": chunks[index]["retrieval_chunk_id"],
            "parent_passage_id": chunks[index]["parent_passage_id"],
            "medicine_id": chunks[index]["medicine_id"],
            "standardized_dci": chunks[index]["standardized_dci"],
            "section": chunks[index]["section"],
            "page_start": chunks[index]["page_start"],
            "page_end": chunks[index]["page_end"],
            "text": chunks[index]["text"],
        }
        for rank, index in enumerate(order, start=1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/query the persistent clinical MiniLM embedding index.")
    parser.add_argument("--rebuild", action="store_true", help="Create vectors again even if an index exists.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size; lower it if memory is limited.")
    parser.add_argument("--query", help="Optional question: print semantic top results after building/loading.")
    parser.add_argument("--medicine-id", help="Optional filter such as M002 after medicine identification.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of results to print for --query.")
    parser.add_argument("--status", action="store_true", help="Print saved build progress and exit.")
    args = parser.parse_args()
    if args.batch_size < 1 or args.top_k < 1:
        parser.error("--batch-size and --top-k must be positive.")

    if args.status:
        if PROGRESS_FILE.exists():
            print(PROGRESS_FILE.read_text(encoding="utf-8"))
        else:
            print("No semantic-index build progress has been recorded yet.")
        return

    chunks = load_chunks()
    needs_build = args.rebuild or not (VECTORS_FILE.exists() and VECTOR_METADATA_FILE.exists() and INDEX_METADATA_FILE.exists())
    if needs_build:
        model = load_model()
        metadata = build(chunks, model, args.batch_size, restart=args.rebuild)
        print(f"Built semantic index: {metadata['vector_count']} vectors x {metadata['embedding_dimension']} dimensions")
    else:
        metadata = json.loads(INDEX_METADATA_FILE.read_text(encoding="utf-8"))
        print(f"Loaded semantic index: {metadata['vector_count']} vectors x {metadata['embedding_dimension']} dimensions")

    if args.query:
        model = load_model()
        vectors, vector_chunks, _ = load_index()
        print(f"Question: {args.query}")
        if args.medicine_id:
            print(f"Medicine filter: {args.medicine_id}")
        for result in semantic_query(model, vectors, vector_chunks, args.query, args.top_k, args.medicine_id):
            print(f"{result['rank']}. {result['retrieval_chunk_id']} | score={result['score']} | {result['standardized_dci']} | pages {result['page_start']}-{result['page_end']}")
            print(f"   {result['text']}")


if __name__ == "__main__":
    main()
