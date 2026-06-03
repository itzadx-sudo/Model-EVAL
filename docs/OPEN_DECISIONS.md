# Open Decisions — Aegis Prototype

All decisions are logged with a D-number. Agents append new decisions with the
next free number.

| #   | Decision | Status |
|-----|----------|--------|
| D1  | Exact Murdoch RMF scales → needed for full system, not prototype | Open |
| D2  | **Model selection**: decided by benchmark results in `docs/benchmark_results.md`. The shortlist is no longer restricted to ≤4B models — any Ollama model may be benchmarked (see D23). | **Open — resolved by prototype** |
| D3  | ChromaDB as vector store | Ratified |
| D5  | Private repo + confidentiality arrangement with supervisor | Open |
| D13 | Dynamic bucketed `num_ctx` [2048, 4096] for prototype | Ratified |
| D15 | `OLLAMA_KEEP_ALIVE=600`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` | Ratified |
| D16 | Blank vendor answer → omission flag, no LLM call | Ratified |
| D19 | VM: Ubuntu 20.04.6 LTS · 24 CPU · 64 GB RAM · 512 GB SSD · GRID T4-4Q 4 GB VRAM | Ratified |
| D20 | Default model `gemma3:2b` across all platforms; `phi4-mini:3.8b` as upgrade candidate | Ratified |
| D21 | Prototype GUI: Streamlit (not React) | Ratified |
| D22 | Prototype scope: RAG + benchmark runner + Streamlit GUI + persistent MD log | Ratified |
| D23 | **Unrestricted model evaluation.** The benchmark harness imposes no parameter-size cap or allow-list. Any Ollama-pullable model (e.g. `gemma3:4b`, `mistral`, `qwen2.5:7b`, `llama3.1:8b`) can be benchmarked via the GUI free-text field or `OLLAMA_MODEL`. The ≤4B note in the spec is a *VM-fit guideline*, not a code constraint: larger models simply run slower / fall back to CPU on the T4-4Q, which the benchmark will measure and record. `MODEL_SHORTLIST` is a convenience dropdown, never a gate. | Ratified |

## D23 rationale

The team wants to evaluate a broad set of models — not just the four that
comfortably fit the T4-4Q's 4 GB VRAM. The whole point of the harness is to
*measure* performance, so the code must not pre-judge which models are allowed.
The VRAM-fit table in `Claude.md §2` remains useful guidance for the primary VM,
but speed/quality on any model is now an empirical question the harness answers.
