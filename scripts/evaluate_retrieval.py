"""
Evaluate BM25 vs Semantic Search on the 15 manually judged questions.

Expected input: evaluation_questions.json
It must contain a JSON array. Each item needs:
  question_id, question, expected_retrieval_chunk_ids
Optional: medicine_id

Run from the project root:
  python scripts/evaluate_retrieval.py --questions evaluation_questions.json --top-k 3

Outputs:
  results/retrieval_evaluation.json
  results/retrieval_evaluation.csv
"""
import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

PROJECT_DIR = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_DIR / "data" / "indexes"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Python module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metric_for_question(results, expected_ids):
    ranks = [
        item["rank"] for item in results
        if item["retrieval_chunk_id"] in expected_ids
    ]
    first_rank = min(ranks) if ranks else None
    return {
        "hit_at_k": 1 if first_rank is not None else 0,
        "reciprocal_rank": 1.0 / first_rank if first_rank is not None else 0.0,
        "first_relevant_rank": first_rank,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=PROJECT_DIR / "evaluation_questions.json")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "results")
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    questions_path = args.questions if args.questions.is_absolute() else PROJECT_DIR / args.questions
    chunks_path = PROJECT_DIR / "data" / "indexes" / "clinical_embedding_metadata.jsonl"
    vectors_path = PROJECT_DIR / "data" / "indexes" / "clinical_embeddings.npy"
    bm25_path = PROJECT_DIR / "data" / "indexes" / "clinical_bm25_index.json"

    required = [questions_path, chunks_path, vectors_path, bm25_path]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError("The questions file must contain a non-empty JSON array.")

    chunks = read_jsonl(chunks_path)
    vectors = np.load(vectors_path, mmap_mode="r")
    bm25_index = json.loads(bm25_path.read_text(encoding="utf-8"))

    if len(chunks) != vectors.shape[0]:
        raise ValueError(f"Metadata/vector mismatch: {len(chunks)} vs {vectors.shape[0]}")
    if bm25_index.get("document_ids") != [c["retrieval_chunk_id"] for c in chunks]:
        raise ValueError("BM25 index order does not match semantic metadata order.")
    if bm25_index.get("document_count") != len(chunks):
        raise ValueError("BM25 document_count does not match metadata count.")

    expected_ids_all = {c["retrieval_chunk_id"] for c in chunks}
    for q in questions:
        for key in ("question_id", "question", "expected_retrieval_chunk_ids"):
            if key not in q:
                raise ValueError(f"{q.get('question_id', 'Question')} is missing field: {key}")
        if not isinstance(q["expected_retrieval_chunk_ids"], list) or not q["expected_retrieval_chunk_ids"]:
            raise ValueError(f"{q['question_id']} has no expected_retrieval_chunk_ids.")
        unknown = set(q["expected_retrieval_chunk_ids"]) - expected_ids_all
        if unknown:
            raise ValueError(f"{q['question_id']} contains expected chunk IDs absent from index: {sorted(unknown)}")

    bm25_module = load_module("build_bm25_index", PROJECT_DIR / "scripts" / "build_bm25_index.py")
    semantic_module = load_module("build_semantic_index", PROJECT_DIR / "scripts" / "build_semantic_index.py")

    # Use the same multilingual MiniLM model as the saved vector index.
    model = SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        local_files_only=True,
    )

    detailed = []
    for q in questions:
        qid = q["question_id"]
        question = q["question"]
        medicine_id = q.get("medicine_id") or None
        expected = set(q["expected_retrieval_chunk_ids"])

        bm25_results = bm25_module.query(
            bm25_index, chunks, question, args.top_k, medicine_id
        )
        semantic_results = semantic_module.semantic_query(
            model, vectors, chunks, question, args.top_k, medicine_id
        )

        bm25_metric = metric_for_question(bm25_results, expected)
        semantic_metric = metric_for_question(semantic_results, expected)

        detailed.append({
            "question_id": qid,
            "question": question,
            "medicine_id": medicine_id,
            "expected_retrieval_chunk_ids": sorted(expected),
            "bm25": {
                **bm25_metric,
                "top_results": bm25_results,
            },
            "semantic": {
                **semantic_metric,
                "top_results": semantic_results,
            },
        })
        print(
            f"{qid}: BM25 Hit@{args.top_k}={bm25_metric['hit_at_k']} "
            f"MRR={bm25_metric['reciprocal_rank']:.3f} | "
            f"Semantic Hit@{args.top_k}={semantic_metric['hit_at_k']} "
            f"MRR={semantic_metric['reciprocal_rank']:.3f}"
        )

    n = len(detailed)
    summary = {
        "question_count": n,
        "top_k": args.top_k,
        "bm25": {
            f"hit@{args.top_k}": sum(x["bm25"]["hit_at_k"] for x in detailed) / n,
            f"mrr@{args.top_k}": sum(x["bm25"]["reciprocal_rank"] for x in detailed) / n,
        },
        "semantic": {
            f"hit@{args.top_k}": sum(x["semantic"]["hit_at_k"] for x in detailed) / n,
            f"mrr@{args.top_k}": sum(x["semantic"]["reciprocal_rank"] for x in detailed) / n,
        },
        "note": "A question is a hit if at least one expected chunk appears in the top-k. MRR uses the rank of the first expected chunk.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "retrieval_evaluation.json"
    csv_path = args.output_dir / "retrieval_evaluation.csv"
    json_path.write_text(
        json.dumps({"summary": summary, "questions": detailed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "question_id", "bm25_hit_at_k", "bm25_first_rank", "bm25_reciprocal_rank",
            "semantic_hit_at_k", "semantic_first_rank", "semantic_reciprocal_rank",
        ])
        writer.writeheader()
        for item in detailed:
            writer.writerow({
                "question_id": item["question_id"],
                "bm25_hit_at_k": item["bm25"]["hit_at_k"],
                "bm25_first_rank": item["bm25"]["first_relevant_rank"] or "",
                "bm25_reciprocal_rank": item["bm25"]["reciprocal_rank"],
                "semantic_hit_at_k": item["semantic"]["hit_at_k"],
                "semantic_first_rank": item["semantic"]["first_relevant_rank"] or "",
                "semantic_reciprocal_rank": item["semantic"]["reciprocal_rank"],
            })

    print("\n=== FINAL SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nSaved: {json_path}")
    print(f"Saved: {csv_path}")


if __name__ == "__main__":
    main()
