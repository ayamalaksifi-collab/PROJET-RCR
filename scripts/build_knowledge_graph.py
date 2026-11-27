#!/usr/bin/env python3
"""Build the traceable baseline knowledge graph for the 40-medicine corpus.

This script deliberately creates only safe, structured relations:
medicine identity, nomenclature product facts, documents and processed
passages.  It does not guess clinical facts from RCP text.  A later, reviewed
step can add clinical candidate relations using the evidence fields defined in
data/knowledge_graph/ontology.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
MEDICINES_FILE = PROJECT_DIR / "data" / "processed" / "medicines_cleaned.json"
NOMENCLATURE_FILE = PROJECT_DIR / "data" / "processed" / "nomenclature_working.json"
PASSAGES_FILE = PROJECT_DIR / "data" / "processed" / "clinical_passages.jsonl"
ONTOLOGY_FILE = PROJECT_DIR / "data" / "knowledge_graph" / "ontology.json"
OUTPUT_DIR = PROJECT_DIR / "data" / "knowledge_graph"


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from error
    return rows


def normalized_id(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "unknown"


def stable_edge_id(subject_id: str, predicate: str, object_id: str) -> str:
    key = f"{subject_id}|{predicate}|{object_id}".encode("utf-8")
    return f"edge:{hashlib.sha256(key).hexdigest()[:16]}"


def add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    node_id = node["id"]
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = node
        return
    if existing == node:
        return
    if existing["type"] != node["type"]:
        raise ValueError(f"Conflicting node types for {node_id}")
    # Nomenclature values can differ only in capitalization, punctuation or
    # spelling details while resolving to the same normalized identifier. Keep
    # the first label as the display value and retain the other source spelling
    # instead of creating duplicate concept nodes.
    if existing["label"] != node["label"]:
        variants = existing.setdefault("properties", {}).setdefault("label_variants", [])
        if node["label"] not in variants and node["label"] != existing["label"]:
            variants.append(node["label"])
        return
    # The existing node may already have label variants collected above.  The
    # source-specific proof remains on the edge, so no further node merge is
    # required for these shared normalized concepts.
    return


def add_edge(edges: dict[tuple[str, str, str], dict[str, Any]], *, subject_id: str,
             predicate: str, object_id: str, source_dataset: str,
             extraction_method: str, verification_status: str,
             properties: dict[str, Any] | None = None) -> None:
    key = (subject_id, predicate, object_id)
    edge = {
        "edge_id": stable_edge_id(*key),
        "subject_id": subject_id,
        "predicate": predicate,
        "object_id": object_id,
        "source_dataset": source_dataset,
        "extraction_method": extraction_method,
        "verification_status": verification_status,
    }
    if properties:
        edge["properties"] = properties
    existing = edges.get(key)
    if existing is None:
        edges[key] = edge
    elif existing != edge:
        # The same fact can occur in several nomenclature rows.  Preserve the
        # original row references together instead of duplicating the edge.
        existing_refs = existing.setdefault("properties", {}).setdefault("source_references", [])
        new_refs = edge.get("properties", {}).get("source_references", [])
        for reference in new_refs:
            if reference not in existing_refs:
                existing_refs.append(reference)


def node(node_id: str, node_type: str, label: str, **properties: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": node_id, "type": node_type, "label": label}
    if properties:
        payload["properties"] = properties
    return payload


def build_graph() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ontology = read_json(ONTOLOGY_FILE)
    medicine_data = read_json(MEDICINES_FILE)
    nomenclature_data = read_json(NOMENCLATURE_FILE)
    passages = read_jsonl(PASSAGES_FILE)

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    medicine_ids: set[str] = set()

    # 1. Stable medicine identity nodes and DCI links for all 40 medicines.
    for record in medicine_data["records"]:
        medicine_id = record["medicine_id"]
        medicine_ids.add(medicine_id)
        medicine_node_id = f"med:{medicine_id}"
        dci = record["standardized_dci"]
        dci_node_id = f"dci:{normalized_id(dci)}"
        add_node(nodes, node(
            medicine_node_id,
            "Medicine",
            dci,
            medicine_id=medicine_id,
            standardized_dci=dci,
            atc_code=record.get("atc_code_validated"),
            therapeutic_class=record.get("therapeutic_class_normalized"),
            is_combination_medicine=record.get("is_combination_medicine", False),
            source_row=record.get("source_row"),
        ))
        add_node(nodes, node(dci_node_id, "DCI", dci))
        add_edge(
            edges,
            subject_id=medicine_node_id,
            predicate="has_dci",
            object_id=dci_node_id,
            source_dataset="data/processed/medicines_cleaned.json",
            extraction_method="direct_structured_mapping",
            verification_status=record.get("normalization_status", "lexically_normalized_pending_source_validation"),
        )

    # 2. Nomenclature product facts.  Only already-approved matched rows are used.
    for record in nomenclature_data["records"]:
        if record.get("match_status") != "matched" or record.get("review_status") != "not_required":
            continue
        reference = record.get("raw_row_reference") or record.get("nomenclature_record_id")
        for candidate in record.get("medicine_candidates", []):
            medicine_id = candidate.get("medicine_id")
            if medicine_id not in medicine_ids:
                continue
            medicine_node_id = f"med:{medicine_id}"
            evidence = {"source_references": [reference], "nomenclature_record_id": record.get("nomenclature_record_id")}
            facts = (
                ("commercial_name_raw", "Brand", "brand", "has_brand"),
                ("pharmaceutical_form_raw", "PharmaceuticalForm", "form", "has_form"),
                ("product_presentation_dosage_raw", "Strength", "strength", "has_strength"),
                ("registration_number_raw", "Registration", "registration", "has_registration"),
            )
            for field, node_type, prefix, predicate in facts:
                value = record.get(field)
                if not value or not str(value).strip():
                    continue
                value = str(value).strip()
                object_id = f"{prefix}:{normalized_id(value)}"
                add_node(nodes, node(object_id, node_type, value))
                add_edge(
                    edges,
                    subject_id=medicine_node_id,
                    predicate=predicate,
                    object_id=object_id,
                    source_dataset="data/processed/nomenclature_working.json",
                    extraction_method="direct_structured_mapping",
                    verification_status="matched_nomenclature_record",
                    properties=evidence,
                )

    # 3. Documents and exact processed-passage links.
    documents: dict[str, dict[str, Any]] = {}
    passage_ids: set[str] = set()
    document_medicines: dict[str, set[str]] = defaultdict(set)
    for passage in passages:
        required = ("passage_id", "source_document_id", "medicine_id", "source_pdf", "source_text")
        missing = [field for field in required if not passage.get(field)]
        if missing:
            raise ValueError(f"Passage is missing required graph metadata {missing}: {passage.get('passage_id')}")
        if passage["medicine_id"] not in medicine_ids:
            raise ValueError(f"Unknown medicine_id in passage corpus: {passage['medicine_id']}")
        if passage["passage_id"] in passage_ids:
            raise ValueError(f"Duplicate passage_id in passage corpus: {passage['passage_id']}")
        passage_ids.add(passage["passage_id"])
        document_medicines[passage["source_document_id"]].add(passage["medicine_id"])
        documents.setdefault(passage["source_document_id"], passage)

    cross_medicine_documents = {
        doc_id: sorted(ids) for doc_id, ids in document_medicines.items() if len(ids) != 1
    }
    if cross_medicine_documents:
        raise ValueError(f"A source document is linked to multiple medicines: {cross_medicine_documents}")

    for document_id, representative in documents.items():
        medicine_id = representative["medicine_id"]
        document_node_id = f"doc:{normalized_id(document_id)}"
        document_label = Path(representative["source_pdf"]).stem
        add_node(nodes, node(
            document_node_id,
            "SourceDocument",
            document_label,
            source_document_id=document_id,
            document_type=representative.get("source_type"),
            source_path=representative["source_pdf"],
            source_text=representative["source_text"],
            authority=representative.get("authority"),
            medicine_id=medicine_id,
        ))
        add_edge(
            edges,
            subject_id=f"med:{medicine_id}",
            predicate="has_source_document",
            object_id=document_node_id,
            source_dataset="data/processed/clinical_passages.jsonl",
            extraction_method="processed_corpus_metadata",
            verification_status=representative.get("verification_status", "extracted_not_manually_verified"),
            properties={"source_document_id": document_id, "source_pdf": representative["source_pdf"]},
        )

    for passage in passages:
        document_node_id = f"doc:{normalized_id(passage['source_document_id'])}"
        passage_node_id = f"passage:{passage['passage_id']}"
        label = f"{passage.get('section') or 'Untitled section'} (pages {passage.get('page_start')}-{passage.get('page_end')})"
        add_node(nodes, node(
            passage_node_id,
            "Passage",
            label,
            passage_id=passage["passage_id"],
            medicine_id=passage["medicine_id"],
            source_document_id=passage["source_document_id"],
            section=passage.get("section"),
            page_start=passage.get("page_start"),
            page_end=passage.get("page_end"),
            source_pdf=passage.get("source_pdf"),
            source_text=passage.get("source_text"),
            source_type=passage.get("source_type"),
            verification_status=passage.get("verification_status"),
        ))
        add_edge(
            edges,
            subject_id=document_node_id,
            predicate="contains_passage",
            object_id=passage_node_id,
            source_dataset="data/processed/clinical_passages.jsonl",
            extraction_method="processed_corpus_metadata",
            verification_status=passage.get("verification_status", "extracted_not_manually_verified"),
            properties={
                "passage_id": passage["passage_id"],
                "page_start": passage.get("page_start"),
                "page_end": passage.get("page_end"),
            },
        )

    node_rows = [nodes[node_id] for node_id in sorted(nodes)]
    edge_rows = [edges[key] for key in sorted(edges)]
    node_type_counts = dict(sorted(Counter(item["type"] for item in node_rows).items()))
    predicate_counts = dict(sorted(Counter(item["predicate"] for item in edge_rows).items()))
    medicines_with_documents = {
        edge["subject_id"].removeprefix("med:")
        for edge in edge_rows if edge["predicate"] == "has_source_document"
    }
    metadata = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/build_knowledge_graph.py",
        "ontology": "data/knowledge_graph/ontology.json",
        "inputs": [
            "data/processed/medicines_cleaned.json",
            "data/processed/nomenclature_working.json",
            "data/processed/clinical_passages.jsonl",
        ],
        "scope": "Baseline identity, nomenclature-product, document and passage graph. Clinical candidate relations are not generated in this baseline.",
        "counts": {
            "medicine_nodes_expected": len(medicine_ids),
            "medicine_nodes_with_documents": len(medicines_with_documents),
            "source_document_nodes": len(documents),
            "passage_nodes": len(passage_ids),
            "total_nodes": len(node_rows),
            "total_edges": len(edge_rows),
            "node_types": node_type_counts,
            "relation_types": predicate_counts,
        },
        "validation": {
            "all_40_medicine_nodes_present": len(medicine_ids) == 40,
            "all_40_medicines_have_source_document": len(medicines_with_documents) == len(medicine_ids),
            "duplicate_passage_ids": [],
            "documents_linked_to_multiple_medicines": cross_medicine_documents,
            "clinical_edges_generated": 0,
            "clinical_edge_policy": "Clinical candidate edges require a later section-aware extraction and remain extracted_not_manually_verified until manually checked.",
        },
    }
    return node_rows, edge_rows, metadata


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate inputs and print counts without writing files.")
    args = parser.parse_args()

    nodes, edges, metadata = build_graph()
    if args.check:
        print(json.dumps(metadata["counts"], ensure_ascii=False, indent=2))
        print(json.dumps(metadata["validation"], ensure_ascii=False, indent=2))
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUTPUT_DIR / "nodes.jsonl", nodes)
    write_jsonl(OUTPUT_DIR / "edges.jsonl", edges)
    (OUTPUT_DIR / "graph_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "review_queue.jsonl").write_text("", encoding="utf-8")
    print("Knowledge graph written:")
    print(f"  nodes: {OUTPUT_DIR / 'nodes.jsonl'} ({len(nodes):,})")
    print(f"  edges: {OUTPUT_DIR / 'edges.jsonl'} ({len(edges):,})")
    print(f"  documents: {metadata['counts']['source_document_nodes']:,}")
    print(f"  passages: {metadata['counts']['passage_nodes']:,}")
    print(f"  medicines with documents: {metadata['counts']['medicine_nodes_with_documents']}/40")


if __name__ == "__main__":
    main()
