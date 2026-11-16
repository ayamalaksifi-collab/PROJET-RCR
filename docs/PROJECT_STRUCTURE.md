# Project structure

```text
data/
  raw/        Original source files. Never edit these files.
  reference/  Teacher-provided reference material.
  processed/  Reproducible cleaned and filtered datasets.
  review/     Human decisions for ambiguous matches.
  sources/    Source register: authority, access rules, provenance.
scripts/      Reproducible Python programs.
results/      Cached LLM/RAG experiment outputs.
docs/         Project documentation.
```

## Data flow

1. `data/reference/Projet2_Liste_40_medicaments.xlsx` is transformed into
   `data/processed/medicines_staging.json` and `medicines_cleaned.json`.
2. The untouched national nomenclature workbook in `data/raw/` is filtered by
   `scripts/build_nomenclature_working.py` into
   `data/processed/nomenclature_working.json`.
3. Ambiguous nomenclature matches are decided in
   `data/review/nomenclature_manual_reviews.json`. Approved rows become
   eligible for the RAG on the next build.
4. `scripts/metadata_rag_experiment.py` uses the cleaned 40-medicine identity
   data first, then retrieves relevant current nomenclature entries.

## Important rules

- Never edit files in `data/raw/`.
- Do not manually edit generated files in `data/processed/`; change the source
  data, script, or review file, then rebuild.
- Do not commit `.env`; it contains the Groq API key.
- The nomenclature strength describes a product presentation, not patient
  posology. Clinical answers need RCP/leaflet or interaction-source passages.
