# Aegis — Model Evaluation Prototype

A focused, **100% local/offline** benchmark harness that runs different LLMs against
a real HECVAT, measures their performance (tokens/s, time-to-first-token, latency,
JSON-parse quality), and persists the results so Team Aegis can make an evidence-based
model decision before building the full risk-assessment system.

See [`Claude.md`](./Claude.md) for the full prototype specification.

## What it does

1. **RAG pipeline** — embeds Murdoch policy docs + HECVAT items into ChromaDB and
   retrieves the most relevant policy clauses per HECVAT question.
2. **Benchmark runner** — runs **any** Ollama model against HECVAT items, capturing
   tok/s, TTFT, latency and gap-analysis JSON quality.
3. **Streamlit GUI** — live metrics dashboard + historical model comparison.
4. **Persistent results log** — `docs/benchmark_results.md`, **append-only**.

## Try any model — no limits

There is **no parameter-size cap and no allow-list** (decision D23). Benchmark
`gemma3:2b`, `phi4-mini:3.8b`, `gemma3:4b`, `llama3.2:3b`, **`mistral`**,
`qwen2.5:7b`, `llama3.1:8b`, or anything else Ollama can pull. In the GUI, pick a
suggestion from the dropdown **or type any model name** in the free-text box. From
the CLI, set `OLLAMA_MODEL` or pass `MODEL=` to `make run`. Larger models simply run
slower / fall back to CPU on the 4 GB T4-4Q — and the harness measures exactly that.

> The VRAM-fit table in `Claude.md §2` is guidance for the primary VM, not a
> constraint enforced in code.

## Quick start

```bash
make setup          # venv + deps + generate the synthetic sample HECVAT
# then bring the whole system up in one command:
python app.py       # starts Ollama, warms models, builds the KB, launches the GUI
# Ctrl+C stops everything it started (a pre-existing Ollama server is left alone).
```

Open <http://localhost:8501>.

### One-command lifecycle (`app.py`)

`python app.py` is a lifecycle manager:

| Phase | Action |
|-------|--------|
| start | start Ollama (if not already running) → warm chat + embed models → build KB → launch GUI |
| stop  | terminate the GUI and stop Ollama **only if this script started it**; the KB is persisted, not deleted |

Flags: `--gui-only`, `--no-ollama`, `--no-pull`, `--no-kb`, `--port N`.

### Manual / Makefile workflow

```bash
make ollama         # start Ollama with the prototype's tuned env (separate terminal)
make models         # pull the suggested candidate models (pull any others too)
make sample         # regenerate samples/sample_hecvat_template.xlsx
make kb             # build the RAG knowledge base from knowledge_base/
make run MODEL=mistral N=20      # run a benchmark on any model
make gui            # launch the Streamlit dashboard
make test           # mocked-Ollama test suite (no real inference)
make lint           # ruff
```

## Robustness

The HECVAT parser handles files dynamically and defensively: a missing column,
ragged rows, an absent sheet, or a corrupt workbook are logged and skipped — they
never crash the run. Column positions and sheet names come from
`config/hecvat_profile.yaml`, never hardcoded.

## Data & confidentiality

* `samples/sample_hecvat_template.xlsx` — synthetic, filled sample (so the benchmark
  actually exercises the model). Regenerate with `make sample`.
* `samples/sample_policy.md` — synthetic Murdoch-style policy for the KB.
* `Copy of HECVAT413.xlsx` — the blank EDUCAUSE v4.1.3 template (structure only, no
  vendor answers; safe to commit).
* `knowledge_base/`, `chroma/`, and any `*_filled.xlsx` are **git-ignored** — real
  policies and filled HECVATs never enter git.

## Layout

```
backend/   config.py · hecvat_parser.py · knowledge_base.py · ollama_client.py
           benchmark_runner.py · results_writer.py · models.py
gui/       app.py (Streamlit dashboard)
config/    hecvat_profile.yaml · prompts/gap_analysis.txt
samples/   build_sample.py · sample_hecvat_template.xlsx · sample_policy.md
docs/      OPEN_DECISIONS.md · benchmark_results.md (append-only)
tests/     mocked-Ollama unit tests
app.py     one-command lifecycle entry point
```
