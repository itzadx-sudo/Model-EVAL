"""Streamlit GUI — live benchmark metrics dashboard.

Five sections, top to bottom:
  Header        — model name, Ollama status, timestamp, platform.
  Controls      — model selector (live `ollama list` + free-text for ANY model),
                  items slider, Start / Build KB buttons.
  Live metrics  — tok/s, TTFT, elapsed, progress, tok/s line chart.
  Results table — sortable dataframe of completed items.
  History       — avg tok/s per model parsed from docs/benchmark_results.md.

No risk scoring, exports, or follow-up questions — those are Phase 2.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.benchmark_runner import run_benchmark  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.models import BenchmarkItem  # noqa: E402
from backend.ollama_client import OllamaClient  # noqa: E402
from backend.results_writer import write_run  # noqa: E402

st.set_page_config(page_title="Aegis Model Benchmark", layout="wide")
settings = get_settings()


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@st.cache_data(ttl=10)
def _ollama_status() -> tuple[bool, str, list[str]]:
    client = OllamaClient(settings)
    try:
        models = _run_async(client.list_models())
        version = _run_async(client.version())
        return True, version, models
    except Exception:
        return False, "unknown", []


def _platform_string() -> str:
    import platform

    return f"{platform.system()} ({platform.machine()})"


def _items_df(items: list[BenchmarkItem]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Ref": it.ref,
                "Section": it.section,
                "Gap type": it.gap_type,
                "Tok/s": round(it.tokens_per_second, 1),
                "Latency ms": round(it.total_latency_ms),
                "TTFT ms": round(it.time_to_first_token_ms),
                "Parse OK": it.parse_ok,
            }
            for it in items
        ]
    )


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
online, version, available_models = _ollama_status()
st.title("🛡️ Aegis — Model Benchmark Harness")
h1, h2, h3, h4 = st.columns(4)
h1.metric("Ollama", "🟢 online" if online else "🔴 offline", help=f"version {version}")
h2.metric("Default model", settings.ollama_model)
h3.metric("Platform", _platform_string())
h4.metric("Run timestamp", time.strftime("%Y-%m-%d %H:%M"))

if not online:
    st.warning(
        "Ollama is not reachable at "
        f"`{settings.ollama_base_url}`. Start it with `make ollama` (or `ollama serve`)."
    )

# ----------------------------------------------------------------------------
# Controls
# ----------------------------------------------------------------------------
st.subheader("Controls")
c1, c2 = st.columns([2, 1])

with c1:
    # Suggestions = whatever is pulled locally + the shortlist. NOT a hard limit.
    suggestions: list[str] = []
    for name in available_models + settings.shortlist:
        if name not in suggestions:
            suggestions.append(name)
    default_idx = suggestions.index(settings.ollama_model) if settings.ollama_model in suggestions else 0
    picked = st.selectbox(
        "Model (suggestions — pulled locally + shortlist)",
        suggestions or [settings.ollama_model],
        index=default_idx if suggestions else 0,
        help="Pick a suggestion, or type any model name in the box below to try it.",
    )
    custom = st.text_input(
        "…or type ANY Ollama model name (overrides the dropdown)",
        value="",
        placeholder="e.g. gemma3:4b · mistral · qwen2.5:7b · llama3.1:8b",
        help="No size cap, no allow-list. If it isn't pulled yet, run `ollama pull <name>` first.",
    )
    model = custom.strip() or picked

with c2:
    n_items = st.slider("HECVAT items to run", 1, 50, settings.benchmark_items)
    hecvat_path = st.text_input("HECVAT file", value=settings.hecvat_path)

b1, b2 = st.columns(2)
start = b1.button("▶️ Start Benchmark", type="primary", use_container_width=True)
build_kb = b2.button("📚 Build Knowledge Base", use_container_width=True)

if model and model not in available_models and online:
    st.info(
        f"`{model}` is not in the local model list. "
        f"If the run fails, pull it first: `ollama pull {model}`."
    )

if build_kb:
    with st.spinner(f"Embedding documents from {settings.kb_dir} …"):
        from backend.knowledge_base import build as kb_build

        try:
            added = _run_async(kb_build(settings.kb_dir, settings))
            st.success(f"Knowledge base updated — {added} new chunks embedded.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"KB build failed: {exc}")

# ----------------------------------------------------------------------------
# Live metrics + run
# ----------------------------------------------------------------------------
if start:
    st.subheader("Live metrics")
    m1, m2, m3 = st.columns(3)
    tps_card = m1.empty()
    ttft_card = m2.empty()
    elapsed_card = m3.empty()
    progress = st.progress(0.0, text="Starting…")
    chart = st.line_chart(pd.DataFrame({"tok/s": []}))
    table_slot = st.empty()

    collected: list[BenchmarkItem] = []
    tps_series: list[float] = []
    run_start = time.perf_counter()

    def on_item(item: BenchmarkItem) -> None:
        collected.append(item)
        tps_card.metric("Tokens/second", f"{item.tokens_per_second:.1f}")
        ttft_card.metric("Time to first token", f"{item.time_to_first_token_ms:.0f} ms")
        elapsed_card.metric("Elapsed", f"{time.perf_counter() - run_start:.1f} s")
        progress.progress(len(collected) / n_items, text=f"{len(collected)}/{n_items} items")
        if item.tokens_per_second > 0:
            tps_series.append(item.tokens_per_second)
            chart.add_rows(pd.DataFrame({"tok/s": [item.tokens_per_second]}))
        table_slot.dataframe(_items_df(collected), use_container_width=True)

    try:
        run = _run_async(
            run_benchmark(
                hecvat_path=hecvat_path,
                model=model,
                n_items=n_items,
                progress_callback=on_item,
                settings=settings,
            )
        )
        write_run(run, settings.benchmark_results_path)
        progress.progress(1.0, text="Done")
        st.success(
            f"Run complete — {run.n_items} items · avg {run.avg_tokens_per_second:.1f} tok/s · "
            f"parse {run.parse_success_rate * 100:.0f}% · appended to "
            f"`{settings.benchmark_results_path}`."
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Benchmark failed: {exc}")

# ----------------------------------------------------------------------------
# Historical comparison — parsed from the persistent results log
# ----------------------------------------------------------------------------
st.subheader("Historical comparison (model selection view)")


def _parse_history(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    text = p.read_text(encoding="utf-8")
    blocks = re.split(r"\n## Run ", text)
    rows = []
    for block in blocks[1:]:
        model_m = re.search(r"\| Model \| (.+?) \|", block)
        tps_m = re.search(r"\| Avg tokens/second \| ([\d,\.]+) \|", block)
        lat_m = re.search(r"\| Avg total latency per item \| ([\d,\.]+) ms \|", block)
        parse_m = re.search(r"\| Parse success rate \| ([\d\.]+)%", block)
        ts_m = re.search(r"— (\S+)", block)
        if model_m and tps_m:
            rows.append(
                {
                    "Run": ts_m.group(1) if ts_m else "",
                    "Model": model_m.group(1).strip(),
                    "Avg tok/s": float(tps_m.group(1).replace(",", "")),
                    "Avg latency ms": float(lat_m.group(1).replace(",", "")) if lat_m else None,
                    "Parse %": float(parse_m.group(1)) if parse_m else None,
                }
            )
    return pd.DataFrame(rows)


history = _parse_history(settings.benchmark_results_path)
if history.empty:
    st.caption("No runs logged yet. Run a benchmark to populate the history.")
else:
    st.dataframe(history, use_container_width=True)
    by_model = history.groupby("Model")["Avg tok/s"].mean()
    st.bar_chart(by_model)
