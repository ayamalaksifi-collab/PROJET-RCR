# Pharmeazor — RCR Project 2

Pharmeazor is a source-grounded medicine-information project. It separates
medicine identity and official nomenclature evidence from clinical evidence in
RCPs, leaflets, and prescribing information.

## Current workflow

```text
40-medicine reference list -> cleaned identity dataset
official nomenclature -> filtered product-evidence dataset
RCPs / leaflets -> extracted text -> traceable clinical passages
question -> keyword and/or semantic retrieval -> evidence for a future RAG answer
```

The metadata layer supports identity, brand, form, presentation strength, and
registration facts. Clinical questions require retrieved passages from RCPs,
leaflets, or interaction sources.

## Main folders

- `Pharmeazor/documents/<medicine>/` — source PDFs, extracted text, and
  processed passages for each medicine.
- `data/processed/` — cleaned metadata datasets and `clinical_passages.jsonl`,
  the central clinical retrieval corpus.
- `scripts/` — extraction, processing, RAG, and retrieval experiments.
- `results/` — saved baseline, RAG, and retrieval-test outputs.
- `docs/` — project structure and test summaries.

Read [the project structure guide](docs/PROJECT_STRUCTURE.md) before adding
documents. Do not create parallel medicine folders outside
`Pharmeazor/documents/`.

## Run the main scripts

From the repository root:

```powershell
# Build the filtered official nomenclature evidence
py scripts/build_nomenclature_working.py

# Extract one clinical PDF to its medicine's extracted/ folder
py scripts/extract_rcp_text.py "Pharmeazor\documents\paracetamol\raw\paracetamol 500mg RCP france .pdf"

# Process one extracted clinical text into searchable passages
py scripts/process_rcp_passages.py "Pharmeazor\documents\paracetamol\extracted\paracetamol 500mg RCP france .txt"

# Compare keyword and semantic retrieval on the processed ibuprofen RCP
py scripts/test_clinical_retrieval.py --label "renal_precautions" --question "Quelles précautions prendre chez les patients présentant une insuffisance rénale lors de l'utilisation de l'ibuprofène ?" --top-k 5
```

The first semantic-retrieval run downloads the multilingual embedding model.
Subsequent runs use the local cache.
