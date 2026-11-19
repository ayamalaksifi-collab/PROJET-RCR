"""Create a readable side-by-side comparison of the two RAG experiments."""

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
METADATA_FILE = PROJECT_DIR / "results" / "metadata_only_rag_results.json"
NOMENCLATURE_FILE = PROJECT_DIR / "results" / "rag_with_nomenclature_results.json"
OUTPUT_FILE = PROJECT_DIR / "results" / "rag_comparison.md"


def compact(answer: str | None, limit: int = 280) -> str:
    answer = " ".join((answer or "").split())
    return answer[:limit] + ("…" if len(answer) > limit else "")


def displayed_status(item: dict) -> str:
    """Classify old and new result files without calling a model again."""
    status = item.get("status", "missing")
    answer = (item.get("answer") or "").strip()
    if status != "success":
        return status
    if answer == "Information insuffisante dans le jeu de données fourni.":
        return "model_refusal"
    if answer.endswith("["):
        return "incomplete_response"
    return "success"


def main() -> None:
    metadata = {
        item["id"]: item
        for item in json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    }
    nomenclature = {
        item["id"]: item
        for item in json.loads(NOMENCLATURE_FILE.read_text(encoding="utf-8"))
    }
    lines = [
        "# RAG comparison: metadata only vs. metadata + nomenclature",
        "",
        "Generated file. Check the complete JSON files for full evidence and answers.",
        "",
    ]
    for question_id in sorted(metadata):
        left = metadata[question_id]
        right = nomenclature.get(question_id, {})
        lines.extend([
            f"## {question_id} — {left['question']}",
            "",
            f"- **Metadata only** (`{displayed_status(left)}`): {compact(left.get('answer'))}",
            f"- **Selective nomenclature RAG** (`{displayed_status(right)}`, `{right.get('evidence_mode', 'unknown')}`): {compact(right.get('answer'))}",
            f"- **Nomenclature rows retrieved**: {len(right.get('retrieved_nomenclature_ids', []))}",
            "",
        ])
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
