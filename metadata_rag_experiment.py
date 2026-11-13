"""Preliminary metadata-RAG experiment for Pharmeazor.

This uses only the cleaned 40-medicine metadata dataset. It is intentionally
not a substitute for RCP/notices or the future clinical-evidence RAG corpus.
"""

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

PROJECT_DIR = Path(__file__).resolve().parent
DATASET_FILE = PROJECT_DIR / "data" / "processed" / "medicines_cleaned.json"
RESULTS_FILE = PROJECT_DIR / "metadata_rag_results.json"

SYSTEM_RULES = """Tu réponds exclusivement à partir des éléments EVIDENCE fournis.
Chaque affirmation factuelle doit citer le ou les identifiants [Mxxx] correspondants.
Si les éléments ne répondent pas explicitement à la question, réponds exactement :
"Information insuffisante dans le jeu de données fourni." Ne complète jamais avec
tes connaissances générales. Ne prescris pas, ne donnes pas de posologie et ne poses
pas de diagnostic."""

# These baseline categories require RCP or interaction passages, which are not
# yet in the metadata-only corpus. They must be blocked before model generation.
UNSUPPORTED_METADATA_CATEGORIES = {
    "availability_algeria",
    "interaction",
    "contraindication",
    "source_conflict",
    "out_of_scope",
}


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

    scored.sort(key=lambda item: (-item[0], item[1]["medicine_id"]))
    return [record for _, record in scored[:limit]]


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


def ask_model(question: str, evidence: str, headers: dict[str, str]) -> tuple[str, dict]:
    response = requests.post(
        URL,
        headers=headers,
        json={
            "model": MODEL,
            "temperature": 0,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": SYSTEM_RULES},
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
    return payload["choices"][0]["message"]["content"], payload.get("usage", {})


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY introuvable dans .env")

    dataset = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    records = dataset["records"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = []

    for item in QUESTIONS:
        retrieved = retrieve(item["question"], records)
        evidence = evidence_packet(retrieved)
        print(f"\n[{item['id']}] récupérés : {[record['medicine_id'] for record in retrieved]}")
        result = {
            **item,
            "model": MODEL,
            "experiment": "metadata_rag_with_cleaned_40_medicine_dataset",
            "retrieved_medicine_ids": [record["medicine_id"] for record in retrieved],
            "evidence": evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if item["category"] in UNSUPPORTED_METADATA_CATEGORIES:
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
                answer, usage = ask_model(item["question"], evidence, headers)
                result.update({"status": "success", "answer": answer, "tokens": usage})
                print("Réponse reçue.")
            except requests.RequestException as error:
                result.update({"status": "error", "answer": None, "error": str(error)})
                print(f"Erreur API : {error}")
        results.append(result)

    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultats enregistrés dans : {RESULTS_FILE.name}")


if __name__ == "__main__":
    main()
