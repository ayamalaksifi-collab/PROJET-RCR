# Project structure

```text
data/
  raw/        Original shared source files; never edit.
  reference/  Teacher-provided reference material.
  processed/  Generated cleaned datasets and the central clinical corpus.
  review/     Human decisions for ambiguous nomenclature matches.
  sources/    Source registry: authority, access rules, and provenance.

Pharmeazor/
  documents/
    <medicine>/
      raw/        Original RCP, leaflet, or prescribing-information PDFs.
      extracted/  Text extracted from the matching source PDFs.
      processed/  Searchable passage JSON generated from extracted text.

scripts/      Reproducible Python programs.
results/      Saved baseline, RAG, and retrieval experiment outputs.
docs/         Project documentation and evaluation summaries.
```

## Document-corpus rule

`Pharmeazor/documents/<medicine>/` is the only document-corpus location.
Every contributor must use the same lowercase subfolder names: `raw`,
`extracted`, and `processed`.

Do not add parallel top-level medicine folders, copied corpus folders, or a
second `Raw/Extracted/Processed` hierarchy elsewhere in the repository. Before
adding a source, check whether that medicine already has a standard folder.
Keep the original PDF in `raw/`, create its text in `extracted/`, then create
the passages JSON in `processed/`.

## Data flow

1. `data/reference/Projet2_Liste_40_medicaments.xlsx` is transformed into
   `data/processed/medicines_staging.json` and `medicines_cleaned.json`.
2. The untouched national nomenclature workbook in `data/raw/` is filtered by
   `scripts/build_nomenclature_working.py` into
   `data/processed/nomenclature_working.json`.
3. Ambiguous nomenclature matches are decided in
   `data/review/nomenclature_manual_reviews.json`. Approved rows become
   eligible for the metadata RAG on the next build.
4. A clinical source PDF moves through:

   ```text
   documents/<medicine>/raw/*.pdf
     -> extract_rcp_text.py
     -> documents/<medicine>/extracted/*.txt
     -> process_rcp_passages.py
     -> documents/<medicine>/processed/*_passages.json
     -> data/processed/clinical_passages.jsonl
   ```
5. `scripts/test_clinical_retrieval.py` compares keyword TF-IDF retrieval with
   multilingual embedding/vector retrieval on processed passages. It saves a
   separate result JSON for every experiment.

## Important rules

- Never edit files in `data/raw/` or `documents/<medicine>/raw/`.
- Do not manually edit generated files in `data/processed/` or a document's
  `processed/` folder; fix the source text or script and rebuild instead.
- Preserve source metadata: document type, source path, section, page range,
  and verification status.
- Do not commit `.env`; it contains the Groq API key.
- The nomenclature strength describes a product presentation, not patient
  posology. Clinical answers must use RCP/leaflet or interaction passages.
