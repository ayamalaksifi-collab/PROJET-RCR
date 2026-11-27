#!/usr/bin/env python3
"""
Pharmeazor - conservative extraction of RCP Section 4.1 (Indications).

SAFE BY DEFAULT:
- Reads clinical_passages.jsonl.
- Prints a check report only.
- Does NOT modify nodes.jsonl, edges.jsonl, ontology.json or review_queue.jsonl.
- Optional --export-preview writes candidates to a NEW, separate JSONL file.
"""

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


BULLET_RE = re.compile(r"^\s*(?:[•●▪◦‣⁃\-–−])\s*(.+?)\s*$")
HEADING_RE = re.compile(r"^\s*4\.1(?:\.\s*|\s+).*indications?", re.IGNORECASE)
INDICATED_RE = re.compile(r"\best indiqué(?:e|s|es)?\b", re.IGNORECASE)

# These lines are contextual/administrative, not indication phrases.
EXCLUDE_STARTS = (
    "il convient", "cette présentation", "les recommandations",
    "voir rubrique", "chez l’adulte", "chez l'adulte",
)

# Conservative non-bullet phrases accepted only when they clearly describe a use.
USE_STARTS = (
    "traitement ", "prévention ", "prophylaxie ",
    "prise en charge ", "soulagement ",
)


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path}, line {line_number}: {exc}"
                ) from exc
    return rows


def clean_phrase(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" \t\r\n;")
    # Remove a trailing comma/full stop without changing the phrase itself.
    value = value.rstrip(" ,.;:")
    return value


def extract_candidates(section_text: str):
    """Extract explicit bullet items and a small set of clear use statements."""
    candidates = []

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if HEADING_RE.match(line):
            continue

        bullet_match = BULLET_RE.match(line)
        if bullet_match:
            phrase = clean_phrase(bullet_match.group(1))
            if phrase and not phrase.casefold().startswith(EXCLUDE_STARTS):
                candidates.append(phrase)
            continue

        lower = line.casefold()
        if lower.startswith(EXCLUDE_STARTS):
            continue

        if lower.startswith(USE_STARTS):
            phrase = clean_phrase(line)
            if phrase:
                candidates.append(phrase)
            continue

        # For "X est indiqué ... :" keep only the text after the colon.
        # If there is no colon, skip the introductory sentence to avoid
        # treating product/context wording as a separate medical indication.
        if INDICATED_RE.search(line) and ":" in line:
            tail = clean_phrase(line.split(":", 1)[1])
            if tail:
                candidates.append(tail)

    # Deduplicate repeated lines within this passage, preserving source wording.
    result = []
    seen = set()
    for phrase in candidates:
        key = phrase.casefold()
        if len(phrase) >= 4 and key not in seen:
            seen.add(key)
            result.append(phrase)
    return result


def normalize_for_id(phrase: str) -> str:
    value = unicodedata.normalize("NFKD", phrase)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value[:70] or "indication"


def stable_indication_id(phrase: str) -> str:
    digest = hashlib.sha1(phrase.casefold().encode("utf-8")).hexdigest()[:10]
    return f"indication:{normalize_for_id(phrase)}_{digest}"


def main():
    parser = argparse.ArgumentParser(
        description="Check RCP Section 4.1 indications without changing graph files."
    )
    parser.add_argument(
        "--passages",
        default="data/processed/clinical_passages.jsonl",
        help="Path to clinical_passages.jsonl",
    )
    parser.add_argument(
        "--export-preview",
        default=None,
        help=(
            "Optional NEW output file for extracted candidates, e.g. "
            "data/processed/indications_preview.jsonl. Existing files are not overwritten."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of candidate examples printed (default: 20).",
    )
    args = parser.parse_args()

    passages_path = Path(args.passages)
    if not passages_path.exists():
        raise SystemExit(
            f"ERROR: passages file not found: {passages_path}\n"
            "Run this script from the project root, or pass --passages with the correct path."
        )

    passages = read_jsonl(passages_path)
    section_rows = [
        row for row in passages
        if str(row.get("section", "")).strip().startswith("4.1")
    ]

    output_rows = []
    for passage in section_rows:
        medicine_id = passage.get("medicine_id")
        passage_id = passage.get("passage_id")
        if not medicine_id or not passage_id:
            continue

        for phrase in extract_candidates(str(passage.get("text", ""))):
            output_rows.append({
                "indication_id": stable_indication_id(phrase),
                "label": phrase,
                "type": "Indication",
                "medicine_id": medicine_id,
                "evidence_passage_id": passage_id,
                "source_document_id": passage.get("source_document_id"),
                "section": passage.get("section"),
                "page_start": passage.get("page_start"),
                "page_end": passage.get("page_end"),
                "source_pdf": passage.get("source_pdf"),
                "source_dataset": "data/processed/clinical_passages.jsonl",
                "extraction_method": "section_4_1_conservative_candidate_rules",
                "verification_status": "extracted_not_manually_verified",
            })

    unique_medicines = sorted({
        row["medicine_id"] for row in section_rows if row.get("medicine_id")
    })
    unique_phrases = {row["indication_id"] for row in output_rows}

    print("=== SECTION 4.1 CHECK (READ-ONLY) ===")
    print(f"Passages file: {passages_path}")
    print(f"Section 4.1 passages found: {len(section_rows)}")
    print(f"Medicines represented in Section 4.1: {len(unique_medicines)}")
    print(f"Candidate indication occurrences: {len(output_rows)}")
    print(f"Unique candidate indication nodes: {len(unique_phrases)}")
    print()
    print("Candidate examples (NOT manually verified):")

    for row in output_rows[:max(args.limit, 0)]:
        print(
            f"- {row['medicine_id']} | {row['label']} "
            f"| pages {row['page_start']}-{row['page_end']} "
            f"| passage {row['evidence_passage_id']}"
        )

    if args.export_preview:
        output_path = Path(args.export_preview)
        if output_path.exists():
            raise SystemExit(
                f"ERROR: preview file already exists: {output_path}\n"
                "Choose a different filename; no file was overwritten."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as handle:
            for row in output_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print()
        print(f"Preview exported to a NEW file: {output_path}")

    print()
    print("SAFE MODE: nodes.jsonl, edges.jsonl, ontology.json and review_queue.jsonl were not changed.")


if __name__ == "__main__":
    main()
