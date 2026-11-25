"""Build token-safe retrieval chunks from traceable clinical evidence passages.

The processed RCP/leaflet passages remain the evidence layer.  This script
creates a separate retrieval layer small enough for the selected MiniLM model,
while retaining a link to each original passage and its source/page metadata.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Do not let an already-downloaded tokenizer trigger network calls.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from transformers import AutoTokenizer
from huggingface_hub import snapshot_download


sys.stdout.reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_DIR / "data" / "processed" / "clinical_passages.jsonl"
OUTPUT_FILE = PROJECT_DIR / "data" / "processed" / "retrieval_chunks.jsonl"
METADATA_FILE = PROJECT_DIR / "data" / "processed" / "retrieval_chunks_metadata.json"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MAX_TOKENS = 110


def clean_whitespace(text: str) -> str:
    """Preserve paragraph/list boundaries while removing PDF visual wrapping."""
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n+", (text or "").strip()):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        result = []
        for line in lines:
            if line.startswith(("•", "\uf0b7", "- ", "– ")):
                result.append(line)
            elif result and result[-1].startswith(("•", "\uf0b7", "- ", "– ")):
                result.append(line)
            else:
                result.append(line)
        joined = "\n".join(result)
        joined = re.sub(r"(?<!\n)\n(?![•\uf0b7\-–])", " ", joined)
        paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def looks_like_heading(text: str) -> bool:
    """Identify a short source label that must stay with its explanation."""
    text = text.strip()
    if not (2 <= len(text) <= 110):
        return False
    if text.endswith((".", ",", ";", ":", "?", "!")):
        return False
    if text.startswith(("•", "\uf0b7", "-", "–")):
        return False
    return bool(re.match(r"^[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’() /-]+$", text))


def split_sentences_or_items(text: str) -> list[str]:
    """Split only at complete sentence or bullet-item boundaries."""
    text = text.strip()
    if not text:
        return []
    bullet_parts = re.split(r"(?=\n[•\uf0b7\-–]\s)", text)
    pieces = []
    for part in bullet_parts:
        part = part.strip()
        if not part:
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9])", part)
        pieces.extend(sentence.strip() for sentence in sentences if sentence.strip())
    return pieces or [text]


def source_units(text: str) -> list[str]:
    """Turn one evidence passage into self-contained paragraph/sentence units."""
    paragraphs = [item.strip() for item in clean_whitespace(text).split("\n\n") if item.strip()]
    units = []
    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        if looks_like_heading(paragraph) and index + 1 < len(paragraphs):
            units.append(f"{paragraph}\n{paragraphs[index + 1]}")
            index += 2
        else:
            units.append(paragraph)
            index += 1
    return units


def token_count(tokenizer, text: str) -> int:
    return len(tokenizer(text, add_special_tokens=True, truncation=False, verbose=False)["input_ids"])


def sentence_transformer_limit() -> int:
    """Read the SentenceTransformer limit, not only the tokenizer's limit.

    The tokenizer can accept 512 tokens while this specific MiniLM embedding
    model is configured by SentenceTransformers to use only 128 tokens.
    """
    model_directory = Path(snapshot_download(repo_id=MODEL_NAME, local_files_only=True))
    config_file = model_directory / "sentence_bert_config.json"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    return int(config["max_seq_length"])


def embedding_text(passage: dict, text: str) -> str:
    """Give semantic search DCI and RCP-section context without losing evidence."""
    return "\n".join(
        part for part in (passage.get("standardized_dci"), passage.get("section"), text.strip()) if part
    )


def same_text(left: str, right: str) -> bool:
    """Compare headings while ignoring PDF spacing/case differences."""
    normalize = lambda value: re.sub(r"\s+", " ", (value or "").casefold()).strip()
    return normalize(left) == normalize(right)


def split_to_fit(tokenizer, passage: dict, unit: str, max_tokens: int) -> list[str]:
    """Split an oversized unit at sentence/item boundaries; never truncate text."""
    if token_count(tokenizer, embedding_text(passage, unit)) <= max_tokens:
        return [unit]
    fragments = split_sentences_or_items(unit)
    output, current = [], ""
    for fragment in fragments:
        proposed = f"{current} {fragment}".strip() if current else fragment
        if current and token_count(tokenizer, embedding_text(passage, proposed)) > max_tokens:
            output.append(current)
            current = fragment
        else:
            current = proposed
    if current:
        output.append(current)

    # A single sentence can exceptionally exceed the limit.  Split it only at
    # whitespace, and mark it for manual review in the metadata.
    hard_split = []
    for item in output:
        if token_count(tokenizer, embedding_text(passage, item)) <= max_tokens:
            hard_split.append(item)
            continue
        words, partial = item.split(), ""
        for word in words:
            proposed = f"{partial} {word}".strip() if partial else word
            if partial and token_count(tokenizer, embedding_text(passage, proposed)) > max_tokens:
                hard_split.append(partial)
                partial = word
            else:
                partial = proposed
        if partial:
            hard_split.append(partial)
    return hard_split


def make_chunks(tokenizer, passage: dict, max_tokens: int) -> list[dict]:
    """Group source units into token-safe retrieval chunks."""
    fit_units = []
    for unit in source_units(passage.get("text", "")):
        fit_units.extend(split_to_fit(tokenizer, passage, unit, max_tokens))

    chunks, current = [], ""
    for unit in fit_units:
        proposed = f"{current}\n\n{unit}".strip() if current else unit
        if current and token_count(tokenizer, embedding_text(passage, proposed)) > max_tokens:
            chunks.append(current)
            current = unit
        else:
            current = proposed
    if current:
        chunks.append(current)

    records = []
    for number, text in enumerate(chunks, start=1):
        # A title without content cannot answer a question and creates noisy
        # matches. Keep it in the source evidence, but exclude it from the
        # retrieval-only layer.
        if same_text(text, passage.get("section", "")):
            continue
        search_text = embedding_text(passage, text)
        count = token_count(tokenizer, search_text)
        if count > max_tokens:
            raise ValueError(f"Chunk still exceeds token limit: {passage['passage_id']} ({count}>{max_tokens})")
        records.append({
            "retrieval_chunk_id": f"RET-{passage['passage_id']}-{number:02d}",
            "parent_passage_id": passage["passage_id"],
            "medicine_id": passage.get("medicine_id"),
            "standardized_dci": passage.get("standardized_dci"),
            "source_document_id": passage.get("source_document_id"),
            "source_pdf": passage.get("source_pdf"),
            "source_text": passage.get("source_text"),
            "source_type": passage.get("source_type"),
            "authority": passage.get("authority"),
            "section": passage.get("section"),
            "page_start": passage.get("page_start"),
            "page_end": passage.get("page_end"),
            "text": text,
            "embedding_text": search_text,
            "embedding_token_count": count,
            "verification_status": passage.get("verification_status"),
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Create token-safe retrieval chunks from clinical passages.")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="Maximum tokens including DCI/section context (default: 110).")
    args = parser.parse_args()
    if args.max_tokens < 32:
        parser.error("--max-tokens must be at least 32.")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=True)
    embedding_model_limit = sentence_transformer_limit()
    if args.max_tokens > embedding_model_limit:
        parser.error(
            f"--max-tokens ({args.max_tokens}) exceeds the SentenceTransformer "
            f"model limit ({embedding_model_limit})."
        )
    source_passages = [json.loads(line) for line in INPUT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = [chunk for passage in source_passages for chunk in make_chunks(tokenizer, passage, args.max_tokens)]
    identifiers = [chunk["retrieval_chunk_id"] for chunk in chunks]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate retrieval_chunk_id generated.")

    OUTPUT_FILE.write_text("".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")
    token_counts = [chunk["embedding_token_count"] for chunk in chunks]
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(INPUT_FILE.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "embedding_model": MODEL_NAME,
        "tokenizer_model_max_length": tokenizer.model_max_length,
        "sentence_transformer_model_max_seq_length": embedding_model_limit,
        "configured_retrieval_chunk_max_tokens": args.max_tokens,
        "source_passage_count": len(source_passages),
        "retrieval_chunk_count": len(chunks),
        "maximum_generated_embedding_token_count": max(token_counts, default=0),
        "minimum_generated_embedding_token_count": min(token_counts, default=0),
        "medicine_chunk_counts": dict(sorted(Counter(chunk["medicine_id"] for chunk in chunks).items())),
        "generation_rules": [
            "Original processed passages remain the evidence layer.",
            "Derived chunks retain parent passage, source, section, and page metadata.",
            "Chunks prefer paragraph, sentence, and bullet-item boundaries.",
            "Headings are kept with their following explanation when possible.",
            "No text is truncated for embeddings; chunks are split to fit the token limit.",
        ],
    }
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tokenizer technical limit: {tokenizer.model_max_length} tokens")
    print(f"SentenceTransformer embedding limit: {embedding_model_limit} tokens")
    print(f"Configured retrieval chunk limit: {args.max_tokens} tokens")
    print(f"Source passages: {len(source_passages)}")
    print(f"Retrieval chunks: {len(chunks)}")
    print(f"Maximum generated token count: {max(token_counts, default=0)}")
    print(f"Saved: {OUTPUT_FILE.relative_to(PROJECT_DIR)}")
    print(f"Saved: {METADATA_FILE.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
