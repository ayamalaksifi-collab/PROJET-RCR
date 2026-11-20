

import argparse
import json
from datetime import date
from pathlib import Path

from pypdf import PdfReader


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = PROJECT_DIR / "Pharmeazor" / "documents"
REPORT_FILE = PROJECT_DIR / "data" / "processed" / "rcp_text_extraction_report.json"

WEEK_2_MEDICINE_FOLDERS = [
    "paracetamol",
    "Ibuprofène",
    "diclofenac",
    "ketoprofene",
    "naproxéne",
    "acide acétylsalicylique",
    "Méloxicam",
    "piroxicam",
    "Célécoxib",
    "Tramadol",
    "Paracétamol + Codéine",
    "Néfopam",
    "Amoxicilline",
]


def output_path(pdf: Path) -> Path:
    """Map a PDF in a medicine's raw/ folder to its extracted/ text file."""
    if pdf.parent.name != "raw":
        raise ValueError("The PDF must be inside a medicine folder's raw/ directory.")
    destination = pdf.parent.parent / "extracted" / f"{pdf.stem}.txt"
    destination.parent.mkdir(exist_ok=True)
    return destination


def extract_one(pdf: Path) -> dict:
    pdf = pdf.resolve()
    destination = output_path(pdf)
    try:
        reader = PdfReader(pdf)
        pages = []
        non_empty_pages = 0
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                non_empty_pages += 1
            pages.append(f"--- Page {number} ---\n{text}")

        extracted_text = "\n\n".join(pages) + "\n"
        destination.write_text(extracted_text, encoding="utf-8")
        needs_ocr = non_empty_pages == 0 or len(extracted_text.strip()) < 100
        return {
            "source_pdf": str(pdf.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "output_text": str(destination.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "page_count": len(reader.pages),
            "non_empty_page_count": non_empty_pages,
            "character_count": len(extracted_text.strip()),
            "status": "needs_ocr" if needs_ocr else "extracted",
            "error": None,
        }
    except Exception as error:
        return {
            "source_pdf": str(pdf.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "output_text": str(destination.relative_to(PROJECT_DIR)).replace("\\", "/"),
            "page_count": None,
            "non_empty_page_count": 0,
            "character_count": 0,
            "status": "error",
            "error": str(error),
        }


def all_week_2_pdfs() -> list[Path]:
    files = []
    for folder_name in WEEK_2_MEDICINE_FOLDERS:
        raw_dir = DOCUMENTS_DIR / folder_name / "raw"
        if raw_dir.exists():
            files.extend(sorted(raw_dir.glob("*.pdf")))
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text locally from RCP/leaflet PDFs.")
    parser.add_argument("pdf", nargs="?", type=Path, help="One PDF inside a medicine raw/ folder.")
    parser.add_argument("--all", action="store_true", help="Extract all PDFs for the 13 Week-2 medicines.")
    args = parser.parse_args()

    if bool(args.pdf) == args.all:
        parser.error("Provide exactly one PDF path, or use --all.")

    pdfs = all_week_2_pdfs() if args.all else [args.pdf]
    report = []
    for pdf in pdfs:
        result = extract_one(pdf)
        report.append(result)
        print(f"{result['status']}: {result['source_pdf']} -> {result['output_text']}")

    REPORT_FILE.write_text(
        json.dumps(
            {
                "created_on": date.today().isoformat(),
                "purpose": "Local PDF-to-text extraction report. Original PDFs remain unchanged.",
                "records": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report: {REPORT_FILE.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
