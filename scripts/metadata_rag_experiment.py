"""Preliminary metadata-RAG experiment for Pharmeazor.

This uses only the cleaned 40-medicine metadata dataset. It is intentionally
not a substitute for RCP/notices or the future clinical-evidence RAG corpus.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from llm_baseline import MODEL, QUESTIONS, URL


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATASET_FILE = PROJECT_DIR / "data" / "processed" / "medicines_cleaned.json"
NOMENCLATURE_FILE = PROJECT_DIR / "data" / "processed" / "nomenclature_working.json"
METADATA_ONLY_RESULTS_FILE = PROJECT_DIR / "results" / "metadata_only_rag_results.json"
NOMENCLATURE_RESULTS_FILE = PROJECT_DIR / "results" / "rag_with_nomenclature_results.json"

SYSTEM_RULES = """Tu réponds exclusivement à partir des éléments EVIDENCE fournis.
Chaque affirmation factuelle doit citer le ou les identifiants [Mxxx] ou [SRC001:NOM-xxxx] correspondants.
Si les éléments ne répondent pas explicitement à la question, réponds exactement :
"Information insuffisante dans le jeu de données fourni." Ne complète jamais avec
tes connaissances générales. Ne prescris pas, ne donnes pas de posologie et ne poses
pas de diagnostic."""

# These baseline categories require RCP or interaction passages, which are not
# yet in the corpus. They must be blocked before model generation.
UNSUPPORTED_METADATA_CATEGORIES = {
    "interaction",
    "contraindication",
    "source_conflict",
    "out_of_scope",
}

# The nomenclature is evidence about registered products (form, labelled
# presentation dosage, brand, registration). It is not useful for every type
# of question and should not be sent when identity metadata is sufficient.
NOMENCLATURE_CATEGORIES = {"availability_algeria"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def retrieve(question: str, records: list[dict], limit: int = 3) -> list[dict]:
    """Deterministic lexical retrieval over medicine names and aliases."""
    query = normalize(question)
    # Ignore short French function words (for example "de", "la") so they
    # cannot cause a false medicine match.
    query_tokens = {token for token in query.split() if len(token) >= 4}
    scored = []
    direct_matches = []

    for record in records:
        aliases = record["search_aliases_normalized"]
        searchable = aliases + [normalize(record["standardized_dci"])]
        score = 0

        for alias in searchable:
            if alias and alias in query:
                score = max(score, 100 + len(alias))
            alias_tokens = {token for token in alias.split() if len(token) >= 4}
            score += 5 * len(query_tokens.intersection(alias_tokens))

        if score >= 5:
            scored.append((score, record))
            # Prefer a full medicine/alias phrase over a weak shared token.
            # Example: "paracetamol" should not also retrieve
            # "paracetamol + codeine".
            if any(alias and alias in query for alias in searchable):
                direct_matches.append((score, record))

    selected = direct_matches or scored
    selected.sort(key=lambda item: (-item[0], item[1]["medicine_id"]))
    return [record for _, record in selected[:limit]]


def evidence_packet(records: list[dict]) -> str:
    """Only expose structured metadata, never unverified free-text remarks."""
    items = []
    for record in records:
        fields = [
            f"DCI normalisée : {record['standardized_dci']}",
            f"Substances actives : {', '.join(record['active_ingredients'])}",
            f"Code ATC vérifié : {record['atc_code_validated']}",
            f"Statut nomenclature Algérie : {record['availability_status_normalized']}",
            f"Alias de recherche : {', '.join(record['search_aliases'])}",
            f"Association : {'oui' if record['is_combination_medicine'] else 'non'}",
        ]
        if record["combination_note"]:
            fields.append(f"Note association : {record['combination_note']}")
        items.append(f"[{record['medicine_id']}] " + " | ".join(fields))
    return "\n".join(items) if items else "Aucun élément pertinent retrouvé."


def retrieve_nomenclature_records(
    medicine_ids: set[str], nomenclature_records: list[dict], limit: int = 20
) -> list[dict]:
    """Return only current, unambiguous official nomenclature entries.

    Withdrawn/non-renewed rows are excluded from availability answers.
    Ambiguous rows remain excluded until a reviewer sets review_status to
    ``approved``.
    """
    current_rows = []
    for record in nomenclature_records:
        candidate_ids = {item["medicine_id"] for item in record["medicine_candidates"]}
        approved = record.get("review_status") == "approved"
        usable_match = record["match_status"] == "matched" or approved
        if (
            medicine_ids.intersection(candidate_ids)
            and record["worksheet"] == "Nomenclature Aout 2026"
            and usable_match
        ):
            current_rows.append(record)

    current_rows.sort(
        key=lambda record: (
            record["commercial_name_raw"] or "",
            record["pharmaceutical_form_raw"] or "",
            record["product_presentation_dosage_raw"] or "",
        )
    )
    # For questions about forms/strengths, favour different presentations over
    # twenty near-identical brands of the same tablet and strength.
    selected = []
    seen_presentations = set()
    for record in current_rows:
        # A numeric cell without a unit may depend on an Excel display format
        # (for example, a percentage). Do not let the model interpret it.
        strength = (record["product_presentation_dosage_raw"] or "").casefold()
        if not re.search(r"mg|\bg\b|ml|%", strength):
            continue
        presentation = (record["pharmaceutical_form_raw"], record["product_presentation_dosage_raw"])
        if presentation not in seen_presentations:
            selected.append(record)
            seen_presentations.add(presentation)
        if len(selected) == limit:
            return selected
    return selected


def nomenclature_evidence_packet(records: list[dict]) -> str:
    """Format product facts separately from identity metadata."""
    items = []
    for record in records:
        fields = [
            f"Brand: {record['commercial_name_raw']}",
            f"Raw INN: {record['dci_raw']}",
            f"Form: {record['pharmaceutical_form_raw']}",
            f"Product presentation dosage: {record['product_presentation_dosage_raw']}",
            f"Registration number: {record['registration_number_raw']}",
            f"Status: {record['registration_status_raw']}",
            f"Workbook reference: {record['raw_row_reference']}",
        ]
        items.append(f"[SRC001:{record['nomenclature_record_id']}] " + " | ".join(fields))
    return "\n".join(items) if items else "No current official nomenclature entry retrieved."


def ask_model(question: str, evidence: str, headers: dict[str, str]) -> tuple[str, dict, str | None]:
    response = requests.post(
        URL,
        headers=headers,
        json={
            "model": MODEL,
            "temperature": 0,
            # Form/strength questions can require a compact multi-item summary.
            # Leave enough output budget after the model's reasoning tokens.
            "max_tokens": 900,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_RULES
                    + "\nRéponse courte : maximum 160 mots, sans tableau. Regroupe les présentations par forme si nécessaire.",
                },
                {
                    "role": "user",
                    "content": f"Question : {question}\n\nEVIDENCE :\n{evidence}",
                },
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    choice = payload["choices"][0]
    return choice["message"]["content"], payload.get("usage", {}), choice.get("finish_reason")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the metadata RAG experiment.")
    parser.add_argument(
        "--with-nomenclature",
        action="store_true",
        help="Add current, reviewed official nomenclature evidence to the metadata RAG.",
    )
    args = parser.parse_args()
    use_nomenclature = args.with_nomenclature
    results_file = NOMENCLATURE_RESULTS_FILE if use_nomenclature else METADATA_ONLY_RESULTS_FILE

    load_dotenv(PROJECT_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY introuvable dans .env")

    dataset = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    records = dataset["records"]
    nomenclature_records = []
    if use_nomenclature:
        nomenclature_dataset = json.loads(NOMENCLATURE_FILE.read_text(encoding="utf-8"))
        nomenclature_records = nomenclature_dataset["records"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = []

    for item in QUESTIONS:
        retrieved = retrieve(item["question"], records)
        retrieved_medicine_ids = [record["medicine_id"] for record in retrieved]
        use_nomenclature_for_item = (
            use_nomenclature and item["category"] in NOMENCLATURE_CATEGORIES
        )
        retrieved_nomenclature = []
        evidence = "MEDICINE IDENTITY:\n" + evidence_packet(retrieved)
        if use_nomenclature_for_item:
            retrieved_nomenclature = retrieve_nomenclature_records(
                set(retrieved_medicine_ids), nomenclature_records
            )
            evidence += (
                "\n\nOFFICIAL ALGERIAN NOMENCLATURE (current, unambiguous products):\n"
                + nomenclature_evidence_packet(retrieved_nomenclature)
            )
        print(f"\n[{item['id']}] récupérés : {[record['medicine_id'] for record in retrieved]}")
        result = {
            **item,
            "model": MODEL,
            "experiment": (
                "metadata_rag_with_identity_and_official_nomenclature"
                if use_nomenclature_for_item
                else "metadata_rag_with_cleaned_40_medicine_dataset"
            ),
            "evidence_mode": (
                "identity_plus_nomenclature"
                if use_nomenclature_for_item
                else "identity_only"
            ),
            "retrieved_medicine_ids": retrieved_medicine_ids,
            "retrieved_nomenclature_ids": [
                record["nomenclature_record_id"] for record in retrieved_nomenclature
            ],
            "evidence": evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        unsupported_categories = set(UNSUPPORTED_METADATA_CATEGORIES)
        if not use_nomenclature_for_item:
            unsupported_categories.add("availability_algeria")
        missing_availability_rows = (
            use_nomenclature_for_item
            and item["category"] == "availability_algeria"
            and not retrieved_nomenclature
        )
        if item["category"] in unsupported_categories or missing_availability_rows:
            result.update(
                {
                    "status": "insufficient_evidence",
                    "answer": "Information insuffisante dans le jeu de données fourni.",
                    "tokens": {},
                    "reason": "Cette question exige des passages RCP ou des données d'interaction qui ne sont pas encore dans le corpus.",
                }
            )
            print("Bloqué : preuves cliniques absentes du corpus.")
        else:
            try:
                answer, usage, finish_reason = ask_model(item["question"], evidence, headers)
                if finish_reason == "length":
                    result.update(
                        {
                            "status": "incomplete_response",
                            "answer": answer,
                            "tokens": usage,
                            "reason": "The model reached its output-token limit; do not count this answer as correct.",
                        }
                    )
                elif answer.strip() == "Information insuffisante dans le jeu de données fourni.":
                    result.update(
                        {
                            "status": "model_refusal",
                            "answer": answer,
                            "tokens": usage,
                            "reason": "The model refused despite the retrieved evidence; review this case during evaluation.",
                        }
                    )
                else:
                    result.update({"status": "success", "answer": answer, "tokens": usage})
                print("Réponse reçue.")
            except requests.RequestException as error:
                result.update({"status": "error", "answer": None, "error": str(error)})
                print(f"Erreur API : {error}")
        results.append(result)

    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultats enregistrés dans : {results_file.name}")


if __name__ == "__main__":
    main()
