"""RAG knowledge base: chunk + embed Murdoch policy docs into ChromaDB, retrieve.

``build(kb_dir)`` walks the knowledge base directory, parses every .pdf / .docx /
.txt / .md, chunks into ~1000-char pieces with a clause id (``file-page-idx``),
embeds each chunk with ``nomic-embed-text`` via Ollama, and stores it in a
persistent ChromaDB collection. It is idempotent: chunks whose clause id already
exists are skipped, so re-running only adds new documents.

``retrieve(query, k)`` embeds the HECVAT question text and returns the top-k most
similar policy clauses as ``Clause`` objects — the grounding context for the
gap-analysis prompt.

ChromaDB and the heavy parsers are imported lazily so that modules which only
need parsing/benchmark logic (and the test suite) don't require them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import Settings, get_settings
from backend.models import Clause
from backend.ollama_client import OllamaClient

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
COLLECTION = "murdoch_policies"


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _read_document(path: Path) -> list[tuple[int, str]]:
    """Return [(page_number, page_text)] for a supported document, else []."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return [(1, path.read_text(encoding="utf-8", errors="ignore"))]
    if suffix == ".pdf":
        import pdfplumber

        pages: list[tuple[int, str]] = []
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                pages.append((i, page.extract_text() or ""))
        return pages
    if suffix == ".docx":
        import docx

        doc = docx.Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)
        return [(1, text)]
    return []


def _get_collection(settings: Settings):
    import chromadb

    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"}
    )


async def build(kb_dir: str | None = None, settings: Settings | None = None) -> int:
    """Ingest every document under ``kb_dir`` into ChromaDB. Returns chunks added."""
    settings = settings or get_settings()
    kb_dir = kb_dir or settings.kb_dir
    client = OllamaClient(settings)
    collection = _get_collection(settings)

    existing = set(collection.get(include=[]).get("ids", []))
    added = 0

    for path in sorted(Path(kb_dir).rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        for page_no, page_text in _read_document(path):
            for idx, chunk in enumerate(_chunk_text(page_text)):
                clause_id = f"{path.stem}-p{page_no}-c{idx}"
                if clause_id in existing:
                    continue
                vector = await client.embed(chunk)
                if not vector:
                    continue
                collection.add(
                    ids=[clause_id],
                    embeddings=[vector],
                    documents=[chunk],
                    metadatas=[{"source": path.name, "page": page_no}],
                )
                existing.add(clause_id)
                added += 1

    return added


async def retrieve(
    query: str, k: int | None = None, settings: Settings | None = None
) -> list[Clause]:
    """Return the top-k policy clauses most similar to ``query``."""
    settings = settings or get_settings()
    k = k or settings.retrieval_k
    client = OllamaClient(settings)
    collection = _get_collection(settings)

    if collection.count() == 0:
        return []

    vector = await client.embed(query)
    if not vector:
        return []

    result = collection.query(
        query_embeddings=[vector],
        n_results=min(k, collection.count()),
        include=["documents", "distances"],
    )
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    dists = result.get("distances", [[]])[0]
    clauses: list[Clause] = []
    for cid, doc, dist in zip(ids, docs, dists, strict=False):
        clauses.append(Clause(id=cid, text=doc, score=1.0 - float(dist)))
    return clauses


if __name__ == "__main__":
    n = asyncio.run(build())
    print(f"Knowledge base build complete — {n} new chunks embedded.")
