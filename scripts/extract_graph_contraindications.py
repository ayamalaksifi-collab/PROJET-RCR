#!/usr/bin/env python3
"""Add conservative contraindication candidates from RCP section 4.3 to the graph.

This is deliberately rule-based, evidence preserving, and conservative.  It
does not claim medical validation: clear list items become candidate graph
facts with `extracted_not_manually_verified`; incomplete or suspicious text is
sent to `review_queue.jsonl`.

Run after scripts/build_knowledge_graph.py:
    py scripts/extract_graph_contraindications.py --check
    py scripts/extract_graph_contraindications.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
GRAPH_DIR = PROJECT_DIR / "data" / "knowledge_graph"
PASSAGES_FILE = PROJECT_DIR / "data" / "processed" / "clinical_passages.jsonl"
NODES_FILE = GRAPH_DIR / "nodes.jsonl"
EDGES_FILE = GRAPH_DIR / "edges.jsonl"
METADATA_FILE = GRAPH_DIR / "graph_metadata.json"
REVIEW_FILE = GRAPH_DIR / "review_queue.jsonl"

BULLET = re.compile(r"(?:^|\n)\s*[•·▪◦‣]\s*")
HEADING = re.compile(r"^\s*4\.3\s*\.\s*contre[- ]indications?\s*", re.IGNORECASE)
INTRO = re.compile(
    r"^(?:ce m[ée]dicament|.+?)\s+(?:est\s+)?contre[- ]indiqu[ée](?:e)?"
    r"(?:\s+dans\s+les\s+situations\s+suivantes)?\s*:?\s*",
    re.IGNORECASE,
)
WHITESPACE = re.compile(r"\s+")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def normalize_id(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{value[:80]}_{digest}" if value else f"unknown_{digest}"


def compact(value: str) -> str:
    return WHITESPACE.sub(" ", value).strip(" ;,.")


def is_section_43(section: str | None) -> bool:
    return bool(section and re.match(r"^4\.3(?:\.|\s|$)", section.strip()))


def is_incomplete(candidate: str) -> str | None:
    lower = candidate.casefold()
    if len(candidate) < 18:
        return "candidate_too_short"
    if re.search(r"(?:\bà la rubrique|\bvoir rubrique|\bmentionné[e]?s? à la rubrique)\s*$", lower):
        return "ends_with_unresolved_cross_reference"
    if re.search(r"(?:\bà|\baux|\bdes|\bde|\bdu|\bet|\bou|,|:)\s*$", lower):
        return "candidate_ends_mid_phrase"
    if "dfg" in lower and ("ml/min" in lower or "hémodialyse" in lower):
        return "likely_mislabelled_dosage_or_renal_table"
    if re.search(r"\b(?:maximum|mg/kg|ml/min)\b", lower) and "hypersensibilité" not in lower:
        return "likely_dosage_table_or_fragment"
    return None


def candidate_items(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return high-confidence bullet candidates and (text, reason) for review."""
    text = HEADING.sub("", text).strip()
    text = INTRO.sub("", text).strip()
    parts = BULLET.split(text)
    # If no bullet marker exists, a full reliable item cannot be separated from
    # narrative text automatically. Leave it for review rather than guessing.
    if len(parts) == 1:
        cleaned = compact(parts[0])
        return [], [(cleaned, "no_clear_bullet_structure")] if cleaned else []

    candidates: list[str] = []
    review: list[tuple[str, str]] = []
    # Text before the first bullet is a heading/introduction, not a fact.
    for part in parts[1:]:
        value = compact(part)
        if not value:
            continue
        reason = is_incomplete(value)
        if reason:
            review.append((value, reason))
        else:
            candidates.append(value)
    return candidates, review


def evidence(passage: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_passage_id": passage["passage_id"],
        "source_document_id": passage["source_document_id"],
        "section": passage.get("section"),
        "page_start": passage.get("page_start"),
        "page_end": passage.get("page_end"),
        "source_pdf": passage.get("source_pdf"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Show proposed counts without writing graph files.")
    args = parser.parse_args()

    if not NODES_FILE.exists() or not EDGES_FILE.exists():
        raise FileNotFoundError("Baseline graph missing. Run py scripts/build_knowledge_graph.py first.")

    # Remove the previous output of this exact extraction step. This makes the
    # script safe to run again after improving rules, without duplicating its
    # own candidate layer. Other future clinical relation types remain intact.
    baseline_nodes = [
        item for item in read_jsonl(NODES_FILE)
        if item.get("type") != "Contraindication"
        or item.get("properties", {}).get("relation_scope") != "candidate_extracted_from_rcp_section_4_3"
    ]
    baseline_edges = [
        item for item in read_jsonl(EDGES_FILE)
        if item.get("extraction_method") != "section_4_3_conservative_bullet_rule"
    ]
    passages = read_jsonl(PASSAGES_FILE)
    clinical_nodes: dict[str, dict[str, Any]] = {}
    clinical_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    review_rows: list[dict[str, Any]] = []
    section_passages = [item for item in passages if is_section_43(item.get("section"))]

    for passage in section_passages:
        candidates, review_items = candidate_items(passage.get("text", ""))
        for candidate, reason in review_items:
            review_rows.append({
                "review_id": f"review:{hashlib.sha256((passage['passage_id'] + reason + candidate).encode('utf-8')).hexdigest()[:16]}",
                "relation_type": "has_contraindication",
                "reason": reason,
                "candidate_text": candidate,
                "medicine_id": passage["medicine_id"],
                "verification_status": "needs_manual_review",
                **evidence(passage),
            })
        for candidate in candidates:
            concept_id = f"contraindication:{normalize_id(candidate)}"
            clinical_nodes.setdefault(concept_id, {
                "id": concept_id,
                "type": "Contraindication",
                "label": candidate,
                "properties": {
                    "normalization_status": "source_wording_not_manually_normalized",
                    "relation_scope": "candidate_extracted_from_rcp_section_4_3",
                },
            })
            edge_key = (f"med:{passage['medicine_id']}", "has_contraindication", concept_id)
            edge = clinical_edges.setdefault(edge_key, {
                "edge_id": f"edge:{hashlib.sha256('|'.join(edge_key).encode('utf-8')).hexdigest()[:16]}",
                "subject_id": edge_key[0],
                "predicate": edge_key[1],
                "object_id": edge_key[2],
                "source_dataset": "data/processed/clinical_passages.jsonl",
                "extraction_method": "section_4_3_conservative_bullet_rule",
                "verification_status": "extracted_not_manually_verified",
                "evidence": [],
            })
            item_evidence = evidence(passage)
            if item_evidence not in edge["evidence"]:
                edge["evidence"].append(item_evidence)

    total_nodes = baseline_nodes + [clinical_nodes[key] for key in sorted(clinical_nodes)]
    total_edges = baseline_edges + [clinical_edges[key] for key in sorted(clinical_edges)]
    # No ID can exist in both lists because the ontology baseline does not yet
    # create Contraindication nodes or has_contraindication edges.
    node_ids = {item["id"] for item in total_nodes}
    missing_endpoints = sorted({
        endpoint for edge in total_edges for endpoint in (edge["subject_id"], edge["object_id"])
        if endpoint not in node_ids
    })
    if missing_endpoints:
        raise ValueError(f"Graph contains missing edge endpoints: {missing_endpoints[:10]}")

    summary = {
        "section_4_3_passages_seen": len(section_passages),
        "medicines_with_section_4_3": len({p["medicine_id"] for p in section_passages}),
        "contraindication_nodes_created": len(clinical_nodes),
        "contraindication_edges_created": len(clinical_edges),
        "review_items_created": len(review_rows),
        "review_reasons": dict(sorted(Counter(item["reason"] for item in review_rows).items())),
        "missing_edge_endpoints": len(missing_endpoints),
    }
    if args.check:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    write_jsonl(NODES_FILE, total_nodes)
    write_jsonl(EDGES_FILE, total_edges)
    write_jsonl(REVIEW_FILE, review_rows)
    metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    metadata["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["clinical_extraction"] = {
        "contraindications": {
            **summary,
            "method": "section_4_3_conservative_bullet_rule",
            "verification_status": "extracted_not_manually_verified",
            "scope_note": "Only clear bullet items were extracted. Non-list, fragmentary or suspicious content was routed to review_queue.jsonl.",
        }
    }
    metadata["counts"]["total_nodes"] = len(total_nodes)
    metadata["counts"]["total_edges"] = len(total_edges)
    metadata["counts"]["node_types"]["Contraindication"] = len(clinical_nodes)
    metadata["counts"]["relation_types"]["has_contraindication"] = len(clinical_edges)
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Contraindication candidate extraction complete:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
