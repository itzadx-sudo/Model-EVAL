.PHONY: setup venv deps ollama models sample kb run gui test lint demo help

## setup: create venv + install deps
setup: venv deps sample
	@echo "✓ Setup done. Next: make ollama (separate terminal) → make demo"

venv:
	@python3.12 -m venv .venv || python3 -m venv .venv

deps: venv
	@.venv/bin/pip install -q -e ".[dev]"

## ollama: start the Ollama server with the prototype's tuned env
ollama:
	OLLAMA_KEEP_ALIVE=600 OLLAMA_NUM_PARALLEL=1 \
	OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_NUM_THREADS=0 \
	ollama serve

## models: pull the suggested candidate models (not a limit — pull any you like)
models:
	ollama pull gemma3:2b
	ollama pull phi4-mini:3.8b
	ollama pull gemma3:4b
	ollama pull llama3.2:3b
	ollama pull nomic-embed-text
	@echo "Tip: pull anything else too, e.g. 'ollama pull mistral' or 'ollama pull qwen2.5:7b'"

## sample: (re)generate the synthetic filled HECVAT sample
sample:
	@.venv/bin/python samples/build_sample.py

## kb: build the RAG knowledge base from knowledge_base/
kb:
	@.venv/bin/python -c "import asyncio; from backend.knowledge_base import build; print(asyncio.run(build()))"

## run: run a benchmark — make run MODEL=mistral N=20
HECVAT ?= samples/sample_hecvat_template.xlsx
MODEL ?= gemma3:2b
N ?= 20
run:
	@.venv/bin/python -c "import asyncio; from backend.benchmark_runner import run_benchmark; \
	from backend.results_writer import write_run; from backend.config import get_settings; \
	run=asyncio.run(run_benchmark('$(HECVAT)', '$(MODEL)', int('$(N)'))); \
	write_run(run, get_settings().benchmark_results_path); \
	print('Appended run for $(MODEL):', round(run.avg_tokens_per_second,1), 'tok/s')"

## gui: launch the Streamlit dashboard
gui:
	@.venv/bin/streamlit run gui/app.py --server.port 8501

## demo: build KB then launch the GUI
demo: kb gui

## test: run the test suite (mocked Ollama — no real inference)
test:
	@.venv/bin/pytest tests/ -v --tb=short

## lint: ruff check
lint:
	@.venv/bin/ruff check backend/ gui/ tests/

## help: list targets
help:
	@grep -E '^## ' Makefile | sed 's/## //'
