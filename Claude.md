# Claude.md — Aegis Model Evaluation Prototype

**Team Aegis · ICT302 IT Professional Practice Project · Murdoch University · Trimester 2, 2026**

> **This is the prototype spec.** The goal is NOT the full risk assessment system yet.
> The goal is a focused benchmark harness: run different LLMs against a real HECVAT,
> measure their performance, and persist the results so the team can make an informed
> model decision before building the full system.
> 
> The full production system spec lives separately. This prototype feeds into it by
> answering the question: **which model, at what speed and quality, should we use?**
> 
> Any AI agent working in this repo reads this file first and follows it exactly.
> When anything is ambiguous, make the smallest assumption, comment it in code,
> and log it in `docs/OPEN_DECISIONS.md`.

-----

## 0. What we are building and why

**The prototype is a model evaluation harness with four parts:**

1. **RAG pipeline** — ingest Murdoch policy documents + the HECVAT template into
   ChromaDB, then for each HECVAT item retrieve the most relevant policy clauses
   and feed them to the LLM for gap analysis.
1. **Benchmark runner** — run any Ollama model against a set of HECVAT items,
   capture tokens/second, time-to-first-token, total latency, and output quality
   per item, and write everything to a persistent Markdown results file.
1. **Simple GUI** — a minimal React or Streamlit interface (team’s choice — see §4)
   that shows live metrics during a run: current model, speed gauge, time per query,
   running totals, and a results table. No risk scoring, no exports, no follow-up
   questions — those are Phase 2 (the full system).
1. **Persistent results log** — `docs/benchmark_results.md` — appended on every run,
   never overwritten. Survives across sessions. This is the team’s evidence base for
   the model selection decision (D2 in OPEN_DECISIONS.md).

**Why this scope?** The team needs to answer three questions before committing to
the full build: (a) which model gives usable gap-analysis output on real HECVAT
questions? (b) how slow is it on the T4-4Q 4 GB VRAM VM? (c) does `gemma3:2b`
quality hold up or do we need `phi4-mini:3.8b`? The prototype answers all three
in two to three weeks without building the full stack prematurely.

-----

## 1. Hard constraints (same as the full system — non-negotiable)

1. **100% local / offline.** No cloud LLM APIs. No telemetry. All inference via
   Ollama on `localhost:11434`. The HECVAT is confidential — it never leaves the machine.
1. **No confidential data in git.** Only synthetic samples and the template structure
   (question IDs + question text, no vendor answers) go in the repo. Real policy docs
   and filled HECVATs are git-ignored.
1. **Cross-platform.** Runs on the Ubuntu VM (NVIDIA GRID T4-4Q, 4 GB VRAM, 24 CPU,
   64 GB RAM), macOS (Apple Silicon or Intel), and Windows. One codebase, one
   `.env.example`, platform differences handled by Ollama automatically.
1. **`benchmark_results.md` is append-only.** Never truncate or overwrite it. Each
   run appends a new dated section. This is the persistent evidence log.
1. **Models are swappable via env var.** `OLLAMA_MODEL=gemma3:2b` is the default.
   Any Ollama-compatible model name must work without code changes.

-----

## 2. Deployment targets

|Platform                |Hardware                                 |Ollama backend    |Default model                  |
|------------------------|-----------------------------------------|------------------|-------------------------------|
|**Ubuntu VM** (primary) |GRID T4-4Q 4 GB VRAM · 24 CPU · 64 GB RAM|CUDA (auto)       |`gemma3:2b`                    |
|**macOS Apple Silicon** |M1–M4 unified memory                     |Metal / MLX (auto)|`gemma3:2b` or `phi4-mini:3.8b`|
|**macOS Intel**         |CPU only                                 |CPU               |`gemma3:2b`                    |
|**Windows** (NVIDIA GPU)|Any CUDA GPU                             |CUDA (auto)       |`gemma3:2b` or `phi4-mini:3.8b`|
|**Windows** (CPU only)  |Any x64 CPU                              |CPU               |`gemma3:2b`                    |

**Model shortlist for evaluation** (what the benchmark runner should test):

|Model           |VRAM (Q4_K_M)|Params|Why test it                              |
|----------------|-------------|------|-----------------------------------------|
|`gemma3:2b`     |~1.6 GB      |2B    |Default — fits T4-4Q with 2.4 GB headroom|
|`phi4-mini:3.8b`|~2.4 GB      |3.8B  |Best structured extraction at ≤4B params |
|`gemma3:4b`     |~2.8 GB      |4B    |Fits T4-4Q; benchmark to confirm         |
|`llama3.2:3b`   |~2.0 GB      |3B    |Popular 3B baseline for comparison       |

**Nothing above 4B parameters** should be in the model shortlist — the T4-4Q has
4 GB VRAM and cannot load a 7B+ model without falling back to slow CPU inference.

-----

## 3. Repository layout

```
aegis-prototype/
├── backend/
│   ├── config.py                  # pydantic-settings: reads .env
│   ├── hecvat_parser.py           # parse HECVAT xlsx → HecvatItem list
│   ├── knowledge_base.py          # chunk + embed policies → ChromaDB; retrieve()
│   ├── ollama_client.py           # async httpx wrapper: chat() + embed() + metrics
│   ├── benchmark_runner.py        # orchestrates one full benchmark run
│   └── results_writer.py          # appends to benchmark_results.md (never overwrites)
├── gui/
│   └── app.py                     # Streamlit GUI — live metrics dashboard
├── config/
│   ├── hecvat_profile.yaml        # column mappings, skip_sections, sheet names
│   └── prompts/
│       └── gap_analysis.txt       # gap analysis prompt template (Jinja2-style)
├── samples/
│   ├── sample_hecvat_template.xlsx  # template structure only — no vendor answers
│   └── sample_policy.pdf            # synthetic Murdoch-style policy (3–4 pages)
├── knowledge_base/                # ← git-ignored; real Murdoch policies go here
├── chroma/                        # ← git-ignored; ChromaDB persistent dir
├── docs/
│   ├── OPEN_DECISIONS.md          # all decisions logged with D-numbers
│   └── benchmark_results.md       # ← PERSISTENT; appended every run; never overwritten
├── app.py                         # entry point: starts Streamlit GUI
├── pyproject.toml                 # Python deps
├── .env.example
├── .gitignore
└── Makefile
```

-----

## 4. Tech stack

### Backend (Python)

|Concern      |Choice                                |Notes                                                    |
|-------------|--------------------------------------|---------------------------------------------------------|
|Language     |**Python 3.12**                       |3.11+ acceptable                                         |
|Settings     |**pydantic-settings**                 |Reads `.env`; single `Settings` object everywhere        |
|LLM runtime  |**Ollama** (latest)                   |`localhost:11434`; CUDA on VM, Metal on Mac, CPU fallback|
|Default model|**`gemma3:2b`** (Q4_K_M, ~1.6 GB VRAM)|Swappable via `OLLAMA_MODEL` env var                     |
|HTTP client  |**httpx** (async)                     |Talks to Ollama API; captures streaming metrics          |
|Embeddings   |**`nomic-embed-text`** via Ollama     |Local embeddings for RAG                                 |
|Vector store |**ChromaDB** (persistent)             |`./chroma/` dir; git-ignored                             |
|HECVAT parse |**openpyxl**                          |Reads `.xlsx`; column names from `hecvat_profile.yaml`   |
|Policy parse |**pdfplumber** + **python-docx**      |PDF and DOCX policy docs                                 |
|Results log  |**stdlib** (file append)              |Appends Markdown to `docs/benchmark_results.md`          |
|Testing      |**pytest**                            |Mock Ollama client; no real inference in tests           |
|Lint         |**Ruff**                              |Lint + format                                            |

### GUI

|Concern     |Choice                                    |Notes                                            |
|------------|------------------------------------------|-------------------------------------------------|
|Framework   |**Streamlit**                             |Fast to build; sufficient for a metrics dashboard|
|Live metrics|`st.metric`, `st.progress`, `st.dataframe`|Tokens/s gauge, per-query table, totals          |
|Charts      |`st.line_chart`                           |Tokens/s over time during a run                  |


> **Why Streamlit not React?** The prototype is a benchmark tool, not a polished product.
> Streamlit is 20x faster to build for this specific use case (metrics dashboard +
> run controls). React is reserved for the full system UI. This decision is logged as D21.

### `.env.example`

```
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:2b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_KEEP_ALIVE=600
OLLAMA_NUM_PARALLEL=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_CTX_MAX=4096
OLLAMA_NUM_THREADS=0

# Benchmark
HECVAT_PATH=./samples/sample_hecvat_template.xlsx
KB_DIR=./knowledge_base
CHROMA_DIR=./chroma
RETRIEVAL_K=4
BENCHMARK_ITEMS=20           # how many HECVAT items to run per benchmark session
BENCHMARK_RESULTS_PATH=docs/benchmark_results.md

# Logging
LOG_LEVEL=INFO
```

-----

## 5. Data flow

```
knowledge_base/ (Murdoch policies)
        │
        ▼ pdfplumber / python-docx
  chunk (~1000 chars, clause IDs)
        │
        ▼ nomic-embed-text (Ollama)
     ChromaDB ─────────────────────────────────────┐
                                                   │ retrieve top-k clauses
HECVAT.xlsx                                        │
  │ openpyxl                                       │
  ▼                                                │
HecvatItems (ref, section, question, answer)       │
  │                                                │
  ▼ for each item:                                 │
  ├─ skip if blank answer → mark omission          │
  ├─ skip if section in skip_sections              │
  ├─ retrieve() ◀─────────────────────────────────┘
  ├─ build prompt (gap_analysis.txt template)
  ├─ ollama_client.chat() → stream tokens
  │   ├─ capture time_to_first_token
  │   ├─ capture tokens_per_second
  │   └─ capture total_latency_ms
  ├─ parse JSON response → GapFinding
  └─ append row to benchmark_results.md

GUI (Streamlit):
  ├─ show live tokens/s gauge per item
  ├─ show running table (ref, gap_type, latency, tok/s)
  ├─ show model name + run timestamp
  └─ show cumulative stats (avg tok/s, total time, items done)
```

-----

## 6. Module specs

### `backend/hecvat_parser.py`

Reads a HECVAT `.xlsx` file (full or lite) using openpyxl. Column mappings come from
`config/hecvat_profile.yaml` — never hardcoded. Returns a list of `HecvatItem`:

```python
@dataclass
class HecvatItem:
    ref: str            # e.g. "DOCU-01"
    section: str        # e.g. "Documentation"
    question: str       # full question text
    vendor_answer: str | None   # None if blank
    sheet_name: str     # which HECVAT sheet it came from
```

Blank `vendor_answer` → item is flagged as `omission` immediately; no LLM call made.
Sections in `skip_sections` (e.g. HIPAA, FERPA — US-specific) are skipped silently.
Supports both HECVAT Full (multi-sheet) and HECVAT Lite (single sheet).

### `backend/knowledge_base.py`

Two functions:

`build(kb_dir)` — walks `knowledge_base/`, parses every `.pdf` / `.docx` / `.txt`,
chunks into ~1000 char pieces with a clause ID (`filename-page-chunk_index`), embeds
with `nomic-embed-text`, stores in ChromaDB. Idempotent — re-running adds new docs,
skips already-embedded ones (compare by clause ID in ChromaDB metadata).

`retrieve(query, k)` → `list[Clause]` — takes a HECVAT question text as the query,
returns the top-k most semantically similar policy clauses with their clause IDs.
These become the grounding context in the gap analysis prompt.

### `backend/ollama_client.py`

Async httpx client. Three methods:

`chat(messages, model, num_ctx, temperature, num_predict)` — streams the response,
captures `time_to_first_token_ms` (time from request send to first token received),
`tokens_per_second` (from Ollama’s `eval_count` / `eval_duration` in the done
message), and `total_latency_ms`. Returns `(text, metrics)`.

`embed(text, model)` → `list[float]`.

`health()` → `bool` — checks `GET /api/tags` and returns True if Ollama is reachable
and the configured model is pulled.

### `backend/benchmark_runner.py`

Orchestrates one benchmark run:

```python
async def run_benchmark(
    hecvat_path: str,
    model: str,
    n_items: int,
    progress_callback: Callable,   # called per item with current metrics
) -> BenchmarkRun
```

For each of the first `n_items` non-blank, non-skipped HECVAT items:

1. `retrieve()` top-k policy clauses
1. Render the gap analysis prompt from `config/prompts/gap_analysis.txt`
1. `ollama_client.chat()` → capture metrics + response text
1. Parse response as JSON → `GapFinding` (if invalid JSON, mark as `parse_error`)
1. Collect into `BenchmarkItem` (ref, gap_type, latency, tok/s, parse_ok)

Returns `BenchmarkRun`:

```python
@dataclass
class BenchmarkItem:
    ref: str
    section: str
    question: str
    gap_type: str | None       # match / partial / mismatch / omission / parse_error
    time_to_first_token_ms: float
    tokens_per_second: float
    total_latency_ms: float
    parse_ok: bool
    response_snippet: str      # first 200 chars of raw LLM response

@dataclass
class BenchmarkRun:
    model: str
    ollama_version: str
    platform: str              # Linux / macOS / Windows + GPU/CPU info
    timestamp: str             # ISO 8601
    n_items: int
    items: list[BenchmarkItem]
    avg_tokens_per_second: float
    avg_latency_ms: float
    avg_time_to_first_token_ms: float
    parse_success_rate: float  # fraction of items with valid JSON output
    gap_type_distribution: dict[str, int]
```

### `backend/results_writer.py`

**Append-only. Never truncates or overwrites `benchmark_results.md`.**

`write_run(run: BenchmarkRun, output_path: str)` — opens the file in append mode
(`"a"`) and writes a new dated section in Markdown:

```markdown
---

## Run — 2026-06-10T14:23:01 | Model: gemma3:2b | Platform: Ubuntu Linux (CUDA · GRID T4-4Q)

| Metric | Value |
|---|---|
| Items evaluated | 20 |
| Avg tokens/second | 18.4 |
| Avg time to first token | 312 ms |
| Avg total latency | 4,820 ms |
| Parse success rate | 95% (19/20) |
| Gap type distribution | match: 4 · partial: 8 · mismatch: 5 · omission: 2 · error: 1 |

### Per-item results

| Ref | Section | Gap type | Tok/s | Latency (ms) | TTFT (ms) | Parse OK |
|---|---|---|---|---|---|---|
| DOCU-01 | Documentation | partial | 19.2 | 4,210 | 298 | ✓ |
| DOCU-02 | Documentation | mismatch | 17.8 | 5,100 | 341 | ✓ |
| ...
```

The file starts with a header section (written once if the file doesn’t exist):

```markdown
# Aegis Model Benchmark Results

Persistent log of all benchmark runs. Append-only — never delete entries.
Used to inform model selection for the full Aegis risk assessment system (D2).

Models under evaluation: gemma3:2b · phi4-mini:3.8b · gemma3:4b · llama3.2:3b
VM target: GRID T4-4Q 4 GB VRAM · Ubuntu 20.04 LTS
```

### `gui/app.py` (Streamlit)

Four sections rendered in order:

**Header** — model name, Ollama status (green/red), run timestamp, platform string.

**Controls** — model selector dropdown (reads available models from `ollama list` API),
number of items slider (1–50), “Start Benchmark” button, “Build Knowledge Base” button.

**Live metrics** (shown during a run, hidden otherwise):

- Large `st.metric` card: current tokens/second
- `st.metric`: time to first token (ms) for last item
- `st.metric`: total elapsed time
- `st.progress`: items completed / total
- `st.line_chart`: tokens/s over time (updates per item)

**Results table** — `st.dataframe` of all completed items in the current run:
ref, section, gap_type, tok/s, latency, TTFT, parse_ok. Sortable.

**Historical comparison** — reads `docs/benchmark_results.md`, parses the summary
tables from past runs, and shows a comparison chart: avg tok/s per model across runs.
This is the key view for model selection.

-----

## 7. Prompt design (`config/prompts/gap_analysis.txt`)

```
SYSTEM:
You compare a VENDOR's HECVAT response against MURDOCH UNIVERSITY policy.
The POLICY is the source of truth. Judge the vendor's answer AGAINST the policy.

Return ONLY valid JSON. No prose. No markdown fences. No explanation outside JSON.
Schema:
{
  "gap_type": "match" | "partial" | "mismatch" | "omission",
  "summary": "<one sentence explanation>",
  "policy_refs": ["<clause_id_1>", "<clause_id_2>"]
}

Rules:
- "match": vendor answer satisfies the policy requirement.
- "partial": vendor partially addresses it but gaps remain.
- "mismatch": vendor answer contradicts or fails the policy requirement.
- "omission": vendor gave no answer (blank or not applicable).
- policy_refs must only contain IDs from the retrieved clauses below.
- summary must be one sentence under 30 words.

USER:
HECVAT item {{ ref }} — {{ section }}
Question: {{ question }}
Vendor answer: {{ vendor_answer | default("(no answer provided)") }}

--- Retrieved Murdoch policy clauses ---
{% for clause in policy_clauses %}
[{{ clause.id }}] {{ clause.text }}
{% endfor %}

Return JSON only.
```

**Prompt design rules:**

- Keep it short — `gemma3:2b` at 2B parameters drifts from long system prompts.
- `gap_type` is the only required structured field — everything else is bonus.
- `policy_refs` gives traceability even in the prototype.
- Temperature: 0.1 (determinism). `num_predict`: 200 (response is small JSON).
- `num_ctx`: use bucketed sizing — `[2048, 4096]` only (prompt is short).

-----

## 8. HECVAT 4.1.3 template reference

The HECVAT used is **HECVAT™ Full v4.1.3** (EDUCAUSE). It has 332 questions
across 35 section prefixes, spread across multiple sheets. The benchmark runner
uses the **Organization sheet** as the primary source for the prototype (most
relevant to Murdoch’s IT governance context). Other sheets can be added later.

**Sheet structure:**

- `START HERE` — general info (vendor name, solution name, contact)
- `Organization` — primary governance, documentation, security questions
- `Product` — product-specific security questions
- `Infrastructure` — hosting, data centre, network questions
- `IT Accessibility` — WCAG / VPAT accessibility questions
- `Case-Specific` — consulting, on-premises, special cases
- `AI` — AI/ML specific questions (new in v4.1.x)
- `Privacy` — data privacy, GDPR, privacy policy questions
- `High-Risk Evaluation`, `Institution Evaluation`, `Privacy Analyst Evaluation` — analyst sheets (not vendor-facing)
- `Questions` — master list of all 332 question IDs (used by the parser)
- `Auto Responses`, `(backend scoring)` — formula/scoring sheets (read-only)

**Column structure (Organization sheet, row 21+):**

|Col A      |Col B        |Col C            |Col D          |Col E   |Col F        |
|-----------|-------------|-----------------|---------------|--------|-------------|
|Question ID|Question text|**Vendor answer**|Additional info|Guidance|Analyst notes|

The vendor fills **Col C (Answer)** and optionally **Col D (Additional Information)**.
Col E (Guidance) and Col F (Analyst Notes) are for the institution’s analyst.

**Skip sections for Murdoch AU context** (US-specific legislation, not applicable):

```yaml
skip_sections:
  - HIPA    # HIPAA — US health data law
  - PCID    # PCI-DSS — payment card (separate Murdoch process)
  - PRGN    # FERPA — US student records law
  - INTL    # GDPR — EU; Murdoch AU has separate process
  - CONS    # Consulting-specific (only relevant for consulting engagements)
```

**Section reference (all 35 prefixes):**

|Prefix|Section name                              |Sheet           |
|------|------------------------------------------|----------------|
|GNRL  |General Information                       |Multiple        |
|COMP  |Company Background                        |START HERE      |
|REQU  |Requirements Routing                      |START HERE      |
|DOCU  |Documentation                             |Organization    |
|ITAC  |IT Accessibility                          |IT Accessibility|
|THRD  |Third Party Assessment                    |Organization    |
|CONS  |Consulting Services                       |Case-Specific   |
|APPL  |Application Security                      |Organization    |
|AAAI  |Authentication & Access                   |Organization    |
|CHNG  |Change Management                         |Organization    |
|DATA  |Data Management                           |Organization    |
|DCTR  |Data Centre & Hosting                     |Infrastructure  |
|FIDP  |Firewall & IDS/IPS                        |Infrastructure  |
|PPPR  |Policies, Processes & Procedures          |Organization    |
|HFIH  |Incident Response                         |Organization    |
|VULN  |Vulnerability Management                  |Organization    |
|HIPA  |HIPAA (US-specific — skip for MU AU)      |Case-Specific   |
|PCID  |PCI-DSS (skip for MU AU)                  |Case-Specific   |
|OPEM  |Operational & Emerging Tech               |Organization    |
|PRGN  |FERPA/COPPA (US-specific — skip)          |Privacy         |
|PCOM  |Privacy Compliance                        |Privacy         |
|PDOC  |Privacy Documentation                     |Privacy         |
|PTHP  |Privacy Third Parties                     |Privacy         |
|PCHG  |Privacy Change Management                 |Privacy         |
|PDAT  |Personal Data Processing                  |Privacy         |
|PRPO  |Privacy Risk & Programme                  |Privacy         |
|INTL  |International (GDPR — separate MU process)|Privacy         |
|DRPV  |Data Privacy Impact Assessment            |Privacy         |
|DPAI  |AI & Data Privacy                         |AI              |
|AIQU  |AI / Machine Learning                     |AI              |
|AIGN  |AI Governance                             |AI              |
|AIPL  |AI Policies & Procedures                  |AI              |
|AISC  |AI Security & Data                        |AI              |
|AIML  |AI/ML Data Separation                     |AI              |
|AILM  |LLM Privileges                            |AI              |

**`config/hecvat_profile.yaml`:**

```yaml
version: "4.1.3"
primary_sheet: "Organization"
all_sheets:
  - "Organization"
  - "Product"
  - "Infrastructure"
  - "IT Accessibility"
  - "Case-Specific"
  - "AI"
  - "Privacy"
question_id_col: 0      # column A (0-indexed)
question_text_col: 1    # column B
vendor_answer_col: 2    # column C
additional_info_col: 3  # column D
header_row: 12          # data starts at row 12 (1-indexed) in Organization sheet
skip_sections:
  - "HIPA"
  - "PCID"
  - "PRGN"
  - "INTL"
  - "CONS"
section_headers:        # rows that are section dividers, not questions
  marker: " "           # section header rows start with a space in col A
```

-----

## 9. `config/hecvat_profile.yaml` — full question list reference

All 332 question IDs extracted from HECVAT v4.1.3 `Questions` sheet.
The parser uses this as the canonical ID list. Sections marked `[SKIP-MU-AU]`
are excluded by default for Murdoch Australia.

```
GNRL: GNRL-01 GNRL-02 GNRL-03 GNRL-04 GNRL-05 GNRL-06 GNRL-07 GNRL-08 GNRL-09
COMP: COMP-01 COMP-02 COMP-03 COMP-04 COMP-05
REQU: REQU-01 REQU-02 REQU-03 REQU-04 REQU-05 REQU-06 REQU-07 REQU-08
DOCU: DOCU-01 DOCU-02 DOCU-03 DOCU-04 DOCU-05 DOCU-06 DOCU-07
ITAC: ITAC-01 through ITAC-18
THRD: THRD-01 THRD-02 THRD-03 THRD-04 THRD-05
CONS: CONS-01 through CONS-08  [SKIP-MU-AU: consulting-specific]
APPL: APPL-01 through APPL-nn
AAAI: AAAI-01 through AAAI-nn
CHNG: CHNG-01 through CHNG-16
DATA: DATA-01 through DATA-nn
DCTR: DCTR-01 through DCTR-nn
FIDP: FIDP-01 through FIDP-nn
PPPR: PPPR-01 through PPPR-nn
HFIH: HFIH-01 through HFIH-nn
VULN: VULN-01 through VULN-nn
HIPA: HIPA-01 through HIPA-nn  [SKIP-MU-AU: US HIPAA]
PCID: PCID-01 through PCID-nn  [SKIP-MU-AU: PCI-DSS]
OPEM: OPEM-01 through OPEM-nn
PRGN: PRGN-01 through PRGN-nn  [SKIP-MU-AU: US FERPA]
PCOM: PCOM-01 through PCOM-nn
PDOC: PDOC-01 through PDOC-nn
PTHP: PTHP-01 through PTHP-nn
PCHG: PCHG-01 through PCHG-nn
PDAT: PDAT-01 through PDAT-nn
PRPO: PRPO-01 through PRPO-nn
INTL: INTL-01 through INTL-nn  [SKIP-MU-AU: GDPR / EU]
DRPV: DRPV-01 through DRPV-nn
DPAI: DPAI-01 through DPAI-nn
AIQU: AIQU-01 through AIQU-nn
AIGN: AIGN-01 through AIGN-nn
AIPL: AIPL-01 through AIPL-nn
AISC: AISC-01 through AISC-nn
AIML: AIML-01 through AIML-nn
AILM: AILM-01 through AILM-nn
```

> **Note:** `nn` placeholders indicate the full count from the xlsx. The parser reads
> the actual file — this list is reference only, not the authoritative source.
> The authoritative source is the `Questions` sheet in the uploaded HECVAT xlsx.

-----

## 10. `docs/benchmark_results.md` — persistent results log

This file is created on first run and appended forever. It lives in `docs/` and is
committed to git (it contains no confidential data — only metrics and question IDs).

**Initial header (written once):**

```markdown
# Aegis — Model Benchmark Results

Persistent log. Appended on every run. Never overwritten.
Purpose: inform model selection for the full Aegis risk assessment system.
See OPEN_DECISIONS.md D2 for the decision this log informs.

Models under evaluation: gemma3:2b · phi4-mini:3.8b · gemma3:4b · llama3.2:3b
VM: GRID T4-4Q 4 GB VRAM · Ubuntu 20.04 LTS · 24 CPU · 64 GB RAM
```

**Each run appends:**

```markdown
---

## Run 001 — 2026-06-10T14:23:01

| Field | Value |
|---|---|
| Model | gemma3:2b (Q4_K_M) |
| Platform | Ubuntu 20.04 · CUDA · GRID T4-4Q |
| Ollama version | 0.19.1 |
| Items evaluated | 20 / 332 |
| Sheets used | Organization |
| Skip sections | HIPA · PCID · PRGN · INTL · CONS |

### Summary metrics

| Metric | Value |
|---|---|
| Avg tokens/second | 18.4 |
| Avg time to first token | 312 ms |
| Avg total latency per item | 4,820 ms |
| Parse success rate | 95% (19/20) |
| Total run time | 96.4 s |

### Gap type distribution

| Gap type | Count | % |
|---|---|---|
| match | 4 | 20% |
| partial | 8 | 40% |
| mismatch | 5 | 25% |
| omission | 2 | 10% |
| parse_error | 1 | 5% |

### Per-item results

| Ref | Section | Gap type | Tok/s | Latency ms | TTFT ms | Parse |
|---|---|---|---|---|---|---|
| DOCU-01 | Documentation | partial | 19.2 | 4210 | 298 | ✓ |
| DOCU-02 | Documentation | mismatch | 17.8 | 5100 | 341 | ✓ |
| DOCU-03 | Documentation | match | 21.1 | 3980 | 276 | ✓ |
| ...

### Notes
<!-- space for manual observations after reviewing the run -->
```

-----

## 11. Build plan

We are at **Week 5 of 12**. The prototype should be working by **end of Week 7**,
leaving Weeks 8–12 for the full system build.

**Week 5 (now) — foundations:**

- Repo scaffold, `.env.example`, `pyproject.toml`, Makefile, `.gitignore`
- Ollama running on the VM: `gemma3:2b` + `nomic-embed-text` pulled
- `hecvat_parser.py` reading `samples/sample_hecvat_template.xlsx` → HecvatItem list
- `knowledge_base.py` — `build()` working on a synthetic policy PDF
- *Owner: Fahad (parser + KB), Aditya (Ollama client)*

**Week 6 — benchmark runner + results writer:**

- `ollama_client.py` — `chat()` streaming with metric capture
- `benchmark_runner.py` — full run loop on 20 items
- `results_writer.py` — appending to `benchmark_results.md`
- Run `gemma3:2b` vs `phi4-mini:3.8b` on the VM, compare results
- *Owner: Aditya (Ollama client + runner), Fahad (results writer)*

**Week 7 — Streamlit GUI + first real benchmark:**

- `gui/app.py` — all four sections working (controls, live metrics, results table, history)
- Run all four candidate models on the VM, log results
- Review `benchmark_results.md` as a team → decide D2 (model selection)
- *Owner: Sakina (GUI), Saleh + Izaan (review outputs for quality)*
- Ryan: write synthetic sample policy document (3–4 pages) for the knowledge base

**Week 8 onwards — full system** (separate spec / Claude.md update)

-----

## 12. Work split for the prototype

|Person    |Task                                                                                          |Deliverable                                                       |
|----------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------|
|**Aditya**|`ollama_client.py` (chat + embed + metrics capture) + `benchmark_runner.py` orchestration     |Working benchmark loop on 20 HECVAT items                         |
|**Fahad** |`hecvat_parser.py` + `knowledge_base.py` (chunk + embed + retrieve) + `results_writer.py`     |Parser + ChromaDB working; MD results file appending correctly    |
|**Sakina**|`gui/app.py` — Streamlit dashboard with live metrics + history comparison chart               |Working GUI that shows live tok/s and results table               |
|**Saleh** |Prompt design iteration in `config/prompts/gap_analysis.txt` + quality review of model outputs|Tested prompt that gets valid JSON from `gemma3:2b` reliably      |
|**Izaan** |`config/hecvat_profile.yaml` + skip_sections logic + validate parser output correctness       |Correct section filtering; omission detection working             |
|**Ryan**  |Synthetic sample docs (`samples/`) + `docs/benchmark_results.md` initial header + README      |Team can run `make demo` end to end without real confidential docs|

-----

## 13. Makefile

```makefile
.PHONY: setup venv deps ollama kb run gui test lint demo help

setup: venv deps
	@echo "✓ Setup done. Next: make ollama (separate terminal) → make demo"

venv:
	@python3.12 -m venv .venv

deps: venv
	@.venv/bin/pip install -q -e ".[dev]"

ollama:
	OLLAMA_KEEP_ALIVE=600 OLLAMA_NUM_PARALLEL=1 \
	OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_THREADS=0 \
	ollama serve

models:
	ollama pull gemma3:2b
	ollama pull phi4-mini:3.8b
	ollama pull gemma3:4b
	ollama pull llama3.2:3b
	ollama pull nomic-embed-text

kb:
	@.venv/bin/python -c \
	  "import asyncio; from backend.knowledge_base import build; asyncio.run(build('knowledge_base/'))"

run:
	@.venv/bin/python -c \
	  "import asyncio; from backend.benchmark_runner import run_benchmark; \
	   asyncio.run(run_benchmark('$(HECVAT)', '$(MODEL)', int('$(N)')))" \
	  HECVAT?=samples/sample_hecvat_template.xlsx MODEL?=gemma3:2b N?=20

gui:
	@.venv/bin/streamlit run gui/app.py --server.port 8501

demo: kb gui

test:
	@.venv/bin/pytest backend/ -v --tb=short

lint:
	@.venv/bin/ruff check backend/ gui/

help:
	@grep -E '^## ' Makefile | sed 's/## //'
```

-----

## 14. Cross-platform setup

#### Ubuntu VM (primary)

```bash
# Run setup script (provided separately: aegis_server_setup.sh)
bash ~/aegis_server_setup.sh
cd ~/aegis-prototype
source .venv/bin/activate
make models    # pull all candidate models (~8 GB total)
make demo
```

#### macOS

```bash
brew install python@3.12 ollama
brew services start ollama
git clone <repo> aegis-prototype && cd aegis-prototype
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make models
make demo
# Open http://localhost:8501
```

#### Windows (PowerShell)

```powershell
# Install Ollama from https://ollama.com/download/windows
# Install Python 3.12 from https://www.python.org/downloads/
git clone <repo> aegis-prototype; cd aegis-prototype
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ollama pull gemma3:2b; ollama pull nomic-embed-text
streamlit run gui/app.py
# Open http://localhost:8501
```

-----

## 15. Open decisions (`docs/OPEN_DECISIONS.md`)

|#  |Decision                                                                                                                                                                  |Status                          |
|---|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------|
|D1 |Exact Murdoch RMF scales → needed for full system, not prototype                                                                                                          |Open                            |
|D2 |**Model selection**: `gemma3:2b` vs `phi4-mini:3.8b` vs `gemma3:4b` vs `llama3.2:3b` — **decided by benchmark results in `docs/benchmark_results.md`**                    |**Open — resolved by prototype**|
|D3 |ChromaDB as vector store                                                                                                                                                  |Ratified                        |
|D5 |Private repo + confidentiality arrangement with supervisor                                                                                                                |Open                            |
|D13|Dynamic bucketed `num_ctx` [2048, 4096] for prototype (smaller prompts than full system)                                                                                  |Ratified                        |
|D15|`OLLAMA_KEEP_ALIVE=600`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`                                                                                             |Ratified                        |
|D16|Blank vendor answer → omission flag, no LLM call                                                                                                                          |Ratified                        |
|D19|VM: Ubuntu 20.04.6 LTS · 24 CPU · 64 GB RAM · 512 GB SSD · GRID T4-4Q 4 GB VRAM · `ICT30226T2TD01` · `10.51.33.69`                                                        |Ratified                        |
|D20|Default model `gemma3:2b` across all platforms; `phi4-mini:3.8b` as upgrade candidate                                                                                     |Ratified                        |
|D21|Prototype GUI: Streamlit (not React). React reserved for full system.                                                                                                     |Ratified                        |
|D22|Prototype scope: RAG pipeline + benchmark runner + Streamlit GUI + persistent MD log. No risk scoring, no exports, no follow-up questions — those are full system Phase 2.|Ratified                        |

-----

## 16. Agent guidance

- **Scope is the prototype only.** Do not build risk scoring, PDF/PPTX export,
  follow-up questions, FastAPI, or React. Those are Phase 2.
- `benchmark_results.md` is **append-only**. Open it with `"a"` mode. Never truncate.
- Model must be swappable via `OLLAMA_MODEL` env var. No model names hardcoded in Python.
- Every HECVAT section in `skip_sections` must produce zero LLM calls. Assert this in tests.
- Blank `vendor_answer` → `gap_type = "omission"`, no LLM call. Assert this in tests.
- `num_ctx` values sent to Ollama must be from `[2048, 4096]` only — never raw integers.
- Temperature 0.1, `num_predict` 200 for all gap analysis calls.
- No confidential data in git. `knowledge_base/`, `chroma/`, real xlsx files are git-ignored.
- Tests must pass with a mocked Ollama client. No real inference in CI.
- Log new decisions in `docs/OPEN_DECISIONS.md` with the next D-number.