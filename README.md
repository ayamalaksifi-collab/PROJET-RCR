# Pharmeazor — RCR Project 2

This repository contains the first data and RAG experiments for Pharmeazor:
a source-grounded assistant for medicine-information lookup.

## Project layout

- `data/` — raw inputs, source register, processed datasets, and review files.
- `scripts/` — programs to build datasets and run experiments.
- `results/` — cached baseline and RAG outputs.
- `docs/` — documentation, including the detailed [project structure](docs/PROJECT_STRUCTURE.md).

## Current workflow

```text
40-medicine reference list → cleaned identity dataset
National nomenclature workbook → filtered product dataset
identity match + product retrieval → evidence-only RAG response
```

The RAG currently supports identification and official nomenclature facts
(brand, form, product strength, registration reference). It does not yet have
the RCP/leaflet and interaction passages needed for clinical questions.

## Run the scripts

From the project root, after adding `GROQ_API_KEY` to a local `.env` file:

```powershell
py scripts/build_nomenclature_working.py
py scripts/llm_baseline.py
# Metadata-only RAG (the original 40-medicine evidence)
py scripts/metadata_rag_experiment.py
# RAG enriched with official nomenclature evidence
py scripts/metadata_rag_experiment.py --with-nomenclature
# Side-by-side readable comparison of the two RAG runs
py scripts/compare_rag_results.py
# Extract a single RCP/leaflet PDF to its medicine's extracted/ folder
py scripts/extract_rcp_text.py "Pharmeazor\documents\paracetamol\raw\paracetamol 500mg RCP france .pdf"
```

The generated outputs are saved in `results/` as separate files, so one RAG
experiment never overwrites the other. See `docs/PROJECT_STRUCTURE.md` before
manually reviewing nomenclature candidates.
