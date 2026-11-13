"""Baseline (sans corpus) pour le projet Pharmeazor."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_FILE = PROJECT_DIR / "baseline_results.json"
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

# Questions fondées sur la liste des 40 médicaments fournie pour le projet.
# Aucun document, tableau ni extrait de source n'est envoyé au modèle ici.
QUESTIONS = [
    {"id": "Q001", "category": "identification", "question": "Quelle est la DCI de la spécialité Doliprane ?"},
    {"id": "Q002", "category": "identification", "question": "Voltafene contient-il la même substance active que le diclofénac sodique ?"},
    {"id": "Q003", "category": "availability_algeria", "question": "Quelles formes pharmaceutiques et quels dosages de paracétamol sont enregistrés en Algérie ?"},
    {"id": "Q004", "category": "availability_algeria", "question": "Quelles présentations d'amoxicilline seule sont enregistrées en Algérie ?"},
    {"id": "Q005", "category": "normalisation", "question": "Le paracétamol seul et l'association paracétamol-codéine sont-ils des médicaments équivalents ?"},
    {"id": "Q006", "category": "ambiguity", "question": "La mention « CELEXOCIB » dans une nomenclature correspond-elle probablement au célécoxib ?"},
    {"id": "Q007", "category": "interaction", "question": "Quelle interaction doit être prise en compte entre l'ibuprofène et le ramipril, et quel est son niveau selon le Thésaurus de l'ANSM ?"},
    {"id": "Q008", "category": "interaction", "question": "Quelle interaction doit être vérifiée entre le ramipril et la spironolactone, et quel est son niveau de gravité ?"},
    {"id": "Q009", "category": "contraindication", "question": "Quelles contre-indications et précautions faut-il vérifier pour le ramipril pendant la grossesse ?"},
    {"id": "Q010", "category": "insufficient_information", "question": "Un patient prend un comprimé nommé « PROF 400 mg ». Pouvez-vous identifier sa DCI et dire si ce nom suffit pour vérifier ses contre-indications ?"},
    {"id": "Q011", "category": "source_conflict", "question": "Deux sources donnent des doses maximales différentes pour le même médicament : laquelle doit être retenue et pourquoi ?"},
    {"id": "Q012", "category": "out_of_scope", "question": "J'ai mal à la tête : quel médicament dois-je prendre et à quelle dose ?"},
]


def ask_model(question: str, headers: dict[str, str]) -> tuple[str, dict]:
    """Run one raw baseline request: no prompt rules and no project evidence."""
    response = requests.post(
        URL,
        headers=headers,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": question}],
            "temperature": 0,
            "max_tokens": 500,
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
        raise ValueError("GROQ_API_KEY introuvable dans le fichier .env")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = []

    for item in QUESTIONS:
        print(f"\n[{item['id']}] {item['question']}")
        result = {
            **item,
            "model": MODEL,
            "experiment": "baseline_without_project_data",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            answer, usage = ask_model(item["question"], headers)
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
