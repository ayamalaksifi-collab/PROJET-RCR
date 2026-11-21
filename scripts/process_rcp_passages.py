

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_DIR / "Pharmeazor" / "documents"
MEDICINES_FILE = PROJECT_DIR / "data" / "processed" / "medicines_cleaned.json"
CENTRAL_CORPUS_FILE = PROJECT_DIR / "data" / "processed" / "clinical_passages.jsonl"
REPORT_FILE = PROJECT_DIR / "data" / "processed" / "rcp_passage_processing_report.json"
MAX_CHARS = 1600
MAX_BOUNDARY_EXTENSION = 450
TOPIC_SPLIT_MIN_CHARS = 1200
TOPIC_TARGET_CHARS = 750
PAGE_MARKER = re.compile(r"^--- Page (\d+) ---\s*$", re.MULTILINE)
# RCP headings are typically written "4.1. ..." or "5.2. ...". The final
# dot avoids treating body-text cross-references such as "4.2 et ..." as a
# heading. This accepts every numbered chapter/subsection, not just 4.x/6.x.
SECTION_HEADING = re.compile(r"^\d+(?:\.\d+)*\.\s+.{3,}$", re.MULTILINE)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", (value or "").casefold())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_DIR)).replace("\\", "/")


def source_pdf(text_file: Path) -> Path | None:
    candidate = text_file.parent.parent / "raw" / f"{text_file.stem}.pdf"
    return candidate if candidate.exists() else None


def source_document_id(text_file: Path) -> str:
    """Stable unique document key used in every passage identifier."""
    readable_name = re.sub(r"[^A-Z0-9]+", "_", normalize(text_file.stem).upper()).strip("_")[:36]
    path_hash = hashlib.sha256(relative(text_file).encode("utf-8")).hexdigest()[:10]
    return f"{readable_name}-{path_hash}"


def medicine_for_folder(folder: Path, medicines: list[dict]) -> dict | None:
    folder_name = normalize(folder.name)
    for medicine in medicines:
        aliases = [medicine["standardized_dci"], *medicine.get("search_aliases", [])]
        if folder_name in {normalize(alias) for alias in aliases}:
            return medicine
    return None


def pages(text: str) -> list[tuple[int, str]]:
    markers = list(PAGE_MARKER.finditer(text))
    if not markers:
        return [(1, text.strip())]
    output = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        output.append((int(marker.group(1)), text[marker.end():end].strip()))
    return output


def clean(text: str) -> str:
    """Conservative cleaning: retains clinical wording and removes layout noise."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        # Preserve a single blank line.  It marks a genuine paragraph in the
        # extracted document and gives the chunker a preferable break point.
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.startswith(("http://", "https://")):
            continue
        # Navigation/header/footer text added when an ANSM database page is
        # printed as PDF. It is not source content and harms retrieval.
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+.*Base de Donn", line):
            continue
        if line.startswith(("Fiche info", "Résumé des caractéristiques du produit", "Notice", "Bon usage")):
            continue
        if line in {"Nos partenaires", "Sauf mention contraire, tous les contenus de ce site sont sous licence etalab-2.0"}:
            continue
        if "base-donnees-publique.medicaments.gouv.fr/" in line:
            continue
        if re.search(r"(?:legifrance\.gouv\.fr|gouvernement\.fr|service-public\.fr|data\.gouv\.fr)", line, re.I):
            continue
        # Decorative government footer; prescription classification (for
        # example "Liste II") remains because it is regulatory information.
        if line.upper() in {"MINISTÈRE", "DU TRAVAIL, DE LA SANTÉ,", "DES SOLIDARITÉS", "ET DES FAMILLES"}:
            continue
        lines.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    # PDF extraction can weld a sentence to the next adverse-effect category.
    return re.sub(r"([.!?])(?=(?:Affections|Effets|Troubles|R\u00e9actions)\b)", r"\1\n\n", cleaned)


def split_sections(page_items: list[tuple[int, str]]) -> list[dict]:
    units = []
    current = {"section": "Document information", "page_start": page_items[0][0], "parts": []}
    for page_number, raw_text in page_items:
        page_text = clean(raw_text)
        if not page_text:
            continue
        headings = list(SECTION_HEADING.finditer(page_text))
        if not headings:
            current["parts"].append((page_number, page_text))
            continue
        prefix = page_text[:headings[0].start()].strip()
        if prefix:
            current["parts"].append((page_number, prefix))
        for index, heading in enumerate(headings):
            if current["parts"]:
                units.append(current)
            end = headings[index + 1].start() if index + 1 < len(headings) else len(page_text)
            current = {"section": heading.group(0).strip(), "page_start": page_number,
                       "parts": [(page_number, page_text[heading.start():end].strip())]}
    if current["parts"]:
        units.append(current)
    return units


def safe_boundaries(text: str, start: int, end: int) -> list[int]:
    """Return paragraph, bullet, or complete-sentence end positions."""
    boundaries = []
    for match in re.finditer(r"(?:\n\s*\n|(?<=[.!?])(?=\s|$)|(?=\n[•\-]))", text[start:end]):
        position = start + match.end()
        if position > start:
            boundaries.append(position)
    return boundaries


def is_subheading(line: str) -> bool:
    """Recognise a short, title-like line inside a long RCP warning section."""
    line = line.strip()
    return bool(re.fullmatch(r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’ -]{1,80}", line))


def topic_units(text: str) -> list[str]:
    """Keep an in-text subheading with the clinical text that follows it."""
    units, current = [], []
    for line in text.splitlines():
        # A numbered RCP section title (for example 4.6) must stay with its
        # first subheading and explanation; it is not a complete topic alone.
        section_title_alone = len(current) == 1 and bool(SECTION_HEADING.match(current[0]))
        if is_subheading(line) and current and not section_title_alone:
            units.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        units.append("\n".join(current).strip())
    return [unit for unit in units if unit]


def chunk_by_boundary(text: str) -> list[str]:
    """Split a single unit only at paragraph, sentence, or bullet boundaries."""
    if len(text) <= MAX_CHARS:
        return [text] if text else []
    output, start = [], 0
    while start < len(text):
        if len(text) - start <= MAX_CHARS:
            output.append(text[start:].strip())
            break
        target_end = start + MAX_CHARS
        before_target = safe_boundaries(text, start, target_end)
        # Prefer the last complete unit before MAX_CHARS. If that would make a
        # very short passage, permit a modest extension to the next complete
        # unit instead of splitting a clinical statement in the middle.
        if before_target and before_target[-1] >= start + MAX_CHARS // 2:
            end = before_target[-1]
        else:
            extended_end = min(len(text), target_end + MAX_BOUNDARY_EXTENSION)
            after_target = safe_boundaries(text, target_end, extended_end)
            end = after_target[0] if after_target else (before_target[-1] if before_target else extended_end)
        output.append(text[start:end].strip())
        # A clean sentence/paragraph boundary is already sufficient context.
        # Do not overlap it: repeated clinical statements make BM25/vector
        # retrieval noisy and can cause duplicate claims in the final answer.
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return output


def chunk(text: str) -> list[str]:
    text = text.strip()
    # Very long warning/adverse-effect passages often contain several labelled
    # topics. Split those labels with their explanation before applying the
    # ordinary sentence-safe maximum-length logic.
    units = topic_units(text) if len(text) >= TOPIC_SPLIT_MIN_CHARS else [text]
    if len(units) <= 1:
        return chunk_by_boundary(text)
    grouped, current = [], ""
    for unit in units:
        proposed = f"{current}\n\n{unit}".strip() if current else unit
        if current and len(proposed) > TOPIC_TARGET_CHARS:
            grouped.append(current)
            current = unit
        else:
            current = proposed
    if current:
        grouped.append(current)
    return [piece for group in grouped for piece in chunk_by_boundary(group)]


def document_type(pdf: Path | None) -> str:
    name = pdf.name.casefold() if pdf else ""
    if "rcp" in name:
        return "rcp"
    if "leaflet" in name or "notice" in name:
        return "patient_leaflet"
    return "unknown_document_type"


def document_dates(text: str) -> dict:
    """Preserve webpage and product-information dates as distinct evidence."""
    webpage = re.search(r"Dernière mise à jour le\s*:?\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    rcp = re.search(r"ANSM\s*-\s*Mis à jour le\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    return {
        "webpage_last_updated_date_raw": webpage.group(1) if webpage else None,
        "webpage_last_updated_date_meaning": "Date displayed by the public medicine database page.",
        "rcp_information_updated_date_raw": rcp.group(1) if rcp else None,
        "rcp_information_updated_date_meaning": "Date displayed by ANSM for the product information/RCP.",
    }


def usable_page_parts(section: dict) -> list[tuple[int, int, str]]:
    """Remove parent headings alone; carry real headings to following content.

    RCP page breaks often leave a heading such as "4.3. Contre-indications"
    at the foot of one page and all its content on the next. Such a heading is
    not a useful retrieval passage by itself.
    """
    heading = section["section"].strip()
    parts = [(page, clean(text)) for page, text in section["parts"] if clean(text)]
    output = []
    for index, (page, text) in enumerate(parts):
        if text == heading:
            next_part = parts[index + 1] if index + 1 < len(parts) else None
            # Parent chapter headings (for example 5.) followed by 5.1 are
            # structural only, and therefore intentionally omitted.
            if next_part and SECTION_HEADING.match(next_part[1]):
                continue
            if next_part:
                next_page, next_text = next_part
                parts[index + 1] = (next_page, f"{text}\n{next_text}")
                continue
            continue
        # A short label may be stranded at a page foot while the explanation
        # begins on the following page. Keep that label with its explanation.
        next_part = parts[index + 1] if index + 1 < len(parts) else None
        nonempty_lines = [line for line in text.splitlines() if line.strip()]
        trailing = nonempty_lines[-1] if nonempty_lines else ""
        title_like = (
            next_part and 2 <= len(trailing) <= 100
            and not trailing.rstrip().endswith((".", ",", ";", ":", "?", "!"))
            and not trailing.lstrip().startswith(("•", "\uf0b7", "-"))
            and trailing[0].isupper()
        )
        if title_like:
            prefix = "\n".join(nonempty_lines[:-1]).strip()
            next_page, next_text = next_part
            if not next_text.casefold().startswith(trailing.casefold()):
                next_text = f"{trailing}\n\n{next_text}"
            parts[index + 1] = (next_page, next_text)
            if prefix:
                output.append((page, page, prefix))
            continue
        output.append((page, page, text))

    # Preserve a bullet list split only by a PDF page break when it fits in
    # one normal passage. Page metadata then records the complete span.
    merged = []
    for page_start, page_end, text in output:
        if merged:
            prior_start, prior_end, prior_text = merged[-1]
            list_continues = prior_text.rstrip().endswith(",") and text.lstrip().startswith(("•", "\uf0b7", "-"))
            if list_continues and len(prior_text) + len(text) + 2 <= MAX_CHARS:
                merged[-1] = (prior_start, page_end, f"{prior_text}\n{text}")
                continue
        merged.append((page_start, page_end, text))
    return merged


def regulatory_metadata(text: str) -> dict | None:
    """Extract French dispensing classification outside technical RCP sections."""
    match = re.search(r"CONDITIONS DE PRESCRIPTION ET DE DELIVRANCE\s*(Liste\s+(?:I|II)\.?)(?:\s|$)", text, re.I)
    if not match:
        return None
    return {
        "jurisdiction": "France",
        "dispensing_classification_raw": match.group(1).rstrip("."),
        "source_context": "CONDITIONS DE PRESCRIPTION ET DE DELIVRANCE",
    }


def remove_regulatory_block(text: str) -> str:
    return re.sub(r"\s*CONDITIONS DE PRESCRIPTION ET DE DELIVRANCE\s*Liste\s+(?:I|II)\.?", "", text, flags=re.I).strip()


def process_one(text_file: Path, medicines: list[dict]) -> tuple[dict, list[dict]]:
    text_file = text_file.resolve()
    if text_file.parent.name != "extracted":
        raise ValueError("Text file must be under a medicine's extracted/ directory.")
    medicine = medicine_for_folder(text_file.parent.parent, medicines)
    if medicine is None:
        raise ValueError(f"No medicine ID mapped for folder: {text_file.parent.parent.name}")
    pdf = source_pdf(text_file)
    document_id = source_document_id(text_file)
    raw_document_text = text_file.read_text(encoding="utf-8")
    passages = []
    for section_number, section in enumerate(split_sections(pages(raw_document_text)), start=1):
        chunk_number = 0
        for page_start, page_end, page_text in usable_page_parts(section):
            page_text = remove_regulatory_block(page_text)
            if not page_text:
                continue
            for text in chunk(page_text):
                chunk_number += 1
                passages.append({
                "passage_id": f"RCP-{medicine['medicine_id']}-{document_id}-{section_number:03d}-{chunk_number:02d}",
                "source_document_id": document_id,
                "medicine_id": medicine["medicine_id"],
                "standardized_dci": medicine["standardized_dci"],
                "source_pdf": relative(pdf) if pdf else None,
                "source_text": relative(text_file),
                "source_type": document_type(pdf),
                "authority": "to_be_verified_from_source_registry",
                "page_start": page_start,
                "page_end": page_end,
                "section": section["section"],
                "text": text,
                "verification_status": "extracted_not_manually_verified",
            })
    destination = text_file.parent.parent / "processed" / f"{text_file.stem}_passages.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"schema_version": "1.0", "medicine_id": medicine["medicine_id"],
        "standardized_dci": medicine["standardized_dci"], "source_document_id": document_id,
        "source_text": relative(text_file),
        "source_pdf": relative(pdf) if pdf else None, "document_dates": document_dates(raw_document_text),
        "regulatory_metadata": regulatory_metadata(raw_document_text),
        "passage_count": len(passages), "passages": passages}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"source_text": relative(text_file), "output": relative(destination), "passage_count": len(passages), "status": "processed"}, passages


def rebuild_central_corpus() -> int:
    """Build the shared corpus from every individual processed document.

    This prevents a one-document processing run from accidentally replacing
    passages that were already produced for the other medicines.
    """
    corpus = []
    for processed_file in sorted(DOCUMENTS_DIR.glob("*/processed/*_passages.json")):
        document = json.loads(processed_file.read_text(encoding="utf-8"))
        corpus.extend(document.get("passages", []))
    CENTRAL_CORPUS_FILE.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in corpus),
        encoding="utf-8",
    )
    return len(corpus)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create searchable, traceable passages from extracted RCP text.")
    parser.add_argument("text_file", nargs="?", type=Path, help="One .txt file under an extracted/ folder.")
    parser.add_argument("--all", action="store_true", help="Process all extracted .txt files in all medicine folders.")
    args = parser.parse_args()
    if bool(args.text_file) == args.all:
        parser.error("Provide exactly one text file, or use --all.")
    medicines = json.loads(MEDICINES_FILE.read_text(encoding="utf-8"))["records"]
    files = sorted(DOCUMENTS_DIR.glob("*/extracted/*.txt")) if args.all else [args.text_file]
    report = []
    for file in files:
        try:
            item, _ = process_one(file, medicines)
            report.append(item)
            print(f"processed: {item['source_text']} -> {item['output']} ({item['passage_count']} passages)")
        except Exception as error:
            report.append({"source_text": str(file), "status": "error", "error": str(error)})
            print(f"error: {file}: {error}")
    corpus_count = rebuild_central_corpus()
    REPORT_FILE.write_text(json.dumps({"created_on": date.today().isoformat(), "records": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Central corpus: {relative(CENTRAL_CORPUS_FILE)} ({corpus_count} passages)")


if __name__ == "__main__":
    main()
