"""Create a scoped nomenclature working set for the 40 project medicines.

The source XLSX is read directly from its ZIP/XML structure so this script has
no third-party dependency and never modifies the original workbook.
"""

import json
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_WORKBOOK = PROJECT_DIR / "data" / "raw" / "clean_NOMENCLATURE.VERSION.AOUT_.2026- (1).xlsx"
MEDICINES_FILE = PROJECT_DIR / "data" / "processed" / "medicines_cleaned.json"
OUTPUT_FILE = PROJECT_DIR / "data" / "processed" / "nomenclature_working.json"
MANUAL_REVIEWS_FILE = PROJECT_DIR / "data" / "review" / "nomenclature_manual_reviews.json"

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SHEET_NAMES = ["Nomenclature Aout 2026", "Non Renouvelés ", "Retraits"]


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", (value or "").casefold())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference).group(0)
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    if cell.attrib.get("t") == "s":
        return shared_strings[int(cell.findtext("x:v", default="0", namespaces=NS))]
    if cell.attrib.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//x:t", NS))
    return cell.findtext("x:v", default="", namespaces=NS)


def workbook_sheets(workbook: Path):
    """Yield (sheet_name, row_number, {header: value}) for each non-empty row."""
    with zipfile.ZipFile(workbook) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(text.text or "" for text in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                for item in root
            ]

        book = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            item.attrib["Id"]: "xl/" + item.attrib["Target"].removeprefix("/").removeprefix("xl/")
            for item in rels
        }
        sheets = book.find("x:sheets", NS)
        for sheet in sheets:
            sheet_name = sheet.attrib["name"]
            relationship_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            root = ET.fromstring(archive.read(rel_targets[relationship_id]))
            headers = None
            for row in root.findall(".//x:sheetData/x:row", NS):
                values = {}
                for cell in row.findall("x:c", NS):
                    values[column_index(cell.attrib["r"])] = cell_value(cell, shared_strings).strip()
                if not any(values.values()):
                    continue
                # The workbook has one header row per worksheet. The DCI field
                # is a stable marker even when title rows are inserted above it.
                if any(normalize(value) == "denomination commune internationale" for value in values.values()):
                    headers = values
                    continue
                if headers and values.get(0, "").isdigit():
                    yield sheet_name, int(row.attrib["r"]), {
                        headers[index]: value for index, value in values.items() if index in headers
                    }


def build_search_dictionary(medicines: list[dict]) -> list[dict]:
    entries = []
    for medicine in medicines:
        aliases = [medicine.get("standardized_dci", ""), medicine.get("inn_raw", "")]
        aliases.extend(medicine.get("search_aliases", []))
        aliases = sorted({normalize(alias) for alias in aliases if normalize(alias)}, key=len, reverse=True)
        entries.append({"medicine_id": medicine["medicine_id"], "dci": medicine["standardized_dci"], "aliases": aliases})
    return entries


def match_row(dci_raw: str, brand_raw: str, dictionary: list[dict]) -> tuple[list[dict], str]:
    dci = normalize(dci_raw)
    brand = normalize(brand_raw)
    matches = []
    for item in dictionary:
        exact_dci = dci in item["aliases"]
        alias_in_dci = any(len(alias) >= 5 and alias in dci for alias in item["aliases"])
        alias_in_brand = any(len(alias) >= 5 and alias in brand for alias in item["aliases"])
        if exact_dci:
            matches.append({"medicine_id": item["medicine_id"], "standardized_dci": item["dci"], "match_basis": "exact_dci"})
        elif alias_in_dci or alias_in_brand:
            matches.append({"medicine_id": item["medicine_id"], "standardized_dci": item["dci"], "match_basis": "partial_or_alias_match"})

    # A row can match a single medicine exactly, several medicines (often a
    # combination/salt), or only a weak alias. Preserve all candidates.
    if not matches:
        return [], "no_match"
    if len(matches) == 1 and matches[0]["match_basis"] == "exact_dci":
        return matches, "matched"
    return matches, "manual_review"


def value(row: dict, header: str) -> str | None:
    return row.get(header) or None


def main() -> None:
    medicines = json.loads(MEDICINES_FILE.read_text(encoding="utf-8"))["records"]
    dictionary = build_search_dictionary(medicines)
    manual_reviews = {}
    if MANUAL_REVIEWS_FILE.exists():
        manual_reviews = json.loads(MANUAL_REVIEWS_FILE.read_text(encoding="utf-8"))["reviews"]
    records = []

    for sheet, row_number, row in workbook_sheets(RAW_WORKBOOK):
        dci = value(row, "DENOMINATION COMMUNE INTERNATIONALE")
        brand = value(row, "NOM DE MARQUE")
        matches, match_status = match_row(dci or "", brand or "", dictionary)
        if not matches:
            continue
        record_id = f"NOM-{len(records) + 1:04d}"
        reviewer_decision = manual_reviews.get(record_id, {})
        records.append({
            "nomenclature_record_id": record_id,
            "worksheet": sheet.strip(),
            "raw_row_number": row_number,
            "raw_row_reference": f"{sheet.strip()}!{row_number}",
            "commercial_name_raw": brand,
            "dci_raw": dci,
            "pharmaceutical_form_raw": value(row, "FORME"),
            "strength_raw": value(row, "DOSAGE"),
            "registration_number_raw": value(row, "N°ENREGISTREMENT"),
            "registration_code_raw": value(row, "CODE"),
            "registration_status_raw": value(row, "STATUT"),
            "medicine_candidates": matches,
            "match_status": match_status,
            "review_status": reviewer_decision.get(
                "review_status", "pending" if match_status == "manual_review" else "not_required"
            ),
            "source_id": "SRC001",
            "review_notes": reviewer_decision.get(
                "review_notes",
                "Manual review required for non-exact, combination, salt-variant, or multi-medicine matches."
                if match_status == "manual_review"
                else None,
            ),
        })

    output = {
        "schema_version": "1.0",
        "purpose": "Candidate nomenclature entries scoped to the project's 40 medicines. This is not clinical evidence.",
        "input_source": {
            "source_id": "SRC001",
            "file": "data/raw/clean_NOMENCLATURE.VERSION.AOUT_.2026- (1).xlsx",
            "read_only": True,
        },
        "created_on": date.today().isoformat(),
        "matching_policy": "Exact DCI matches are marked matched. Partial aliases, combinations, salt variants, and multi-medicine results are retained and sent to manual review.",
        "record_count": len(records),
        "manual_review_count": sum(record["match_status"] == "manual_review" for record in records),
        "records": records,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} candidate entries to {OUTPUT_FILE}")
    print(f"Manual review required: {output['manual_review_count']}")


if __name__ == "__main__":
    main()
