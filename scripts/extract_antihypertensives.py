import argparse
import json
from datetime import date
from pathlib import Path

from pypdf import PdfReader

# Project paths
PROJECT_DIR = Path(__file__).resolve().parent.parent

DOCUMENTS_DIR = PROJECT_DIR / "Pharmeazor" / "documents"

REPORT_FILE = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "antihypertensive_text_extraction_report.json"
)


# The 14 antihypertensive medicines
ANTIHYPERTENSIVE_MEDICINE_FOLDERS = [
    "Amlodipine",
    "Nifedipine",
    "Perindopril",
    "Ramipril",
    "Enalapril",
    "Losartan",
    "Valsartan",
    "Bisoprolol",
    "Atenolol",
    "Nebivolol",
    "Hydrochlorothiazide",
    "Indapamide",
    "Spironolactone",
    "Methyldopa",
]


def output_path(pdf: Path) -> Path:
    """Map a PDF in a medicine's raw/ folder to its extracted text file."""

    if pdf.parent.name.lower() != "raw":
        raise ValueError(
            "The PDF must be inside a medicine folder's raw/ directory."
        )

    destination = (
        pdf.parent.parent
        / "extracted"
        / f"{pdf.stem}.txt"
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

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

            pages.append(
                f"--- Page {number} ---\n{text}"
            )

        
        extracted_text = "\n\n".join(pages) + "\n"

        
        destination.write_text(
            extracted_text,
            encoding="utf-8"
        )

        
        needs_ocr = (
            non_empty_pages == 0
            or len(extracted_text.strip()) < 100
        )

        return {
            "source_pdf": str(
                pdf.relative_to(PROJECT_DIR)
            ).replace("\\", "/"),

            "output_text": str(
                destination.relative_to(PROJECT_DIR)
            ).replace("\\", "/"),

            "page_count": len(reader.pages),

            "non_empty_page_count": non_empty_pages,

            "character_count": len(extracted_text.strip()),

            "status": (
                "needs_ocr"
                if needs_ocr
                else "extracted"
            ),

            "error": None,
        }

    except Exception as error:

        return {
            "source_pdf": str(pdf),

            "output_text": str(destination),

            "page_count": None,

            "non_empty_page_count": 0,

            "character_count": 0,

            "status": "error",

            "error": str(error),
        }


def all_antihypertensive_pdfs() -> list[Path]:
    """Find PDFs in the raw folders of all 14 medicines."""

    files = []

    for folder_name in ANTIHYPERTENSIVE_MEDICINE_FOLDERS:

        raw_dir = (
            DOCUMENTS_DIR
            / folder_name
            / "raw"
        )

        if raw_dir.exists():

            # Find PDFs, including uppercase .PDF extensions
            for file in raw_dir.iterdir():

                if file.is_file() and file.suffix.lower() == ".pdf":
                    files.append(file)

        else:

            print(f"Folder not found: {raw_dir}")

    return sorted(files)


def main():

    parser = argparse.ArgumentParser(
        description="Extract text locally from antihypertensive PDFs."
    )

    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        help="One PDF inside a medicine's raw/ folder."
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Extract all PDFs for the 14 antihypertensive medicines."
    )

    args = parser.parse_args()

    
    if bool(args.pdf) == args.all:

        parser.error(
            "Provide exactly one PDF path, or use --all."
        )

    
    if args.all:

        pdfs = all_antihypertensive_pdfs()

    else:

        pdfs = [args.pdf]

    report = []

    
    for pdf in pdfs:

        result = extract_one(pdf)

        report.append(result)

        print(
            f"{result['status']}: "
            f"{result['source_pdf']} -> "
            f"{result['output_text']}"
        )

    
    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    
    REPORT_FILE.write_text(
        json.dumps(
            {
                "created_on": date.today().isoformat(),

                "purpose": (
                    "Local PDF-to-text extraction report "
                    "for antihypertensive medicines. "
                    "Original PDFs remain unchanged."
                ),

                "records": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8"
    )

    print("\nExtraction finished!")

    print(f"PDFs processed: {len(report)}")

    print(
        f"Report saved: "
        f"{REPORT_FILE.relative_to(PROJECT_DIR)}"
    )


if __name__ == "__main__":
    main()