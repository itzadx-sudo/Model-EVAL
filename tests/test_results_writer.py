"""Results writer tests — append-only behaviour and run numbering."""

from __future__ import annotations

from backend.models import BenchmarkItem, BenchmarkRun
from backend.results_writer import write_run


def _run(model: str = "gemma3:2b") -> BenchmarkRun:
    items = [
        BenchmarkItem("DOCU-01", "Documentation", "q", "partial", 300, 19.2, 4210, True, "..."),
        BenchmarkItem("DOCU-03", "Documentation", "q", "omission", 0, 0, 0, True, "(omission)"),
    ]
    return BenchmarkRun(
        model=model,
        ollama_version="0.0.test",
        platform="Linux (x86_64)",
        timestamp="2026-06-10T14:23:01+00:00",
        n_items=len(items),
        items=items,
        avg_tokens_per_second=19.2,
        avg_latency_ms=4210,
        avg_time_to_first_token_ms=300,
        parse_success_rate=1.0,
        gap_type_distribution={"partial": 1, "omission": 1},
        sheets_used=["Organization"],
        skip_sections=["HIPA", "PCID"],
        total_run_time_s=8.4,
    )


def test_header_written_once_and_appends(tmp_path):
    path = tmp_path / "benchmark_results.md"

    write_run(_run("gemma3:2b"), str(path))
    first = path.read_text()
    assert first.count("# Aegis — Model Benchmark Results") == 1
    assert "## Run 001" in first

    write_run(_run("mistral"), str(path))
    second = path.read_text()
    # Header still appears exactly once — never overwritten.
    assert second.count("# Aegis — Model Benchmark Results") == 1
    assert "## Run 001" in second
    assert "## Run 002" in second
    # The first run's content survives (append-only).
    assert first in second


def test_never_truncates(tmp_path):
    path = tmp_path / "benchmark_results.md"
    write_run(_run(), str(path))
    size_after_one = len(path.read_text())
    write_run(_run(), str(path))
    assert len(path.read_text()) > size_after_one
