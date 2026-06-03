"""Append benchmark runs to docs/benchmark_results.md — APPEND-ONLY.

This file is the team's persistent evidence base for the model-selection decision
(OPEN_DECISIONS D2). It is opened in ``"a"`` mode and never truncated. A header is
written once if the file does not yet exist; every run appends a new dated section.
"""

from __future__ import annotations

from pathlib import Path

from backend.models import BenchmarkRun

_HEADER = """# Aegis — Model Benchmark Results

Persistent log. Appended on every run. Never overwritten.
Purpose: inform model selection for the full Aegis risk assessment system.
See OPEN_DECISIONS.md D2 for the decision this log informs.

Models under evaluation are not restricted — any Ollama model can be benchmarked
(gemma3:2b, phi4-mini:3.8b, gemma3:4b, llama3.2:3b, mistral, qwen2.5:7b, ...).
VM target: GRID T4-4Q 4 GB VRAM · Ubuntu 20.04 LTS · 24 CPU · 64 GB RAM
"""


def _next_run_number(path: Path) -> int:
    if not path.exists():
        return 1
    text = path.read_text(encoding="utf-8")
    return text.count("\n## Run ") + 1


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def render_run(run: BenchmarkRun, run_number: int) -> str:
    total = len(run.items)
    parse_ok = sum(1 for it in run.items if it.parse_ok)
    lines: list[str] = []
    lines.append("\n---\n")
    lines.append(f"## Run {run_number:03d} — {run.timestamp}\n")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Model | {run.model} |")
    lines.append(f"| Platform | {run.platform} |")
    lines.append(f"| Ollama version | {run.ollama_version} |")
    lines.append(f"| Items evaluated | {run.n_items} |")
    lines.append(f"| Sheets used | {' · '.join(run.sheets_used) or 'Organization'} |")
    lines.append(f"| Skip sections | {' · '.join(run.skip_sections) or '(none)'} |")
    lines.append("")
    lines.append("### Summary metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Avg tokens/second | {_fmt(run.avg_tokens_per_second)} |")
    lines.append(f"| Avg time to first token | {_fmt(run.avg_time_to_first_token_ms, 0)} ms |")
    lines.append(f"| Avg total latency per item | {_fmt(run.avg_latency_ms, 0)} ms |")
    lines.append(
        f"| Parse success rate | {_fmt(run.parse_success_rate * 100, 0)}% ({parse_ok}/{total}) |"
    )
    lines.append(f"| Total run time | {_fmt(run.total_run_time_s)} s |")
    lines.append("")
    lines.append("### Gap type distribution\n")
    lines.append("| Gap type | Count | % |")
    lines.append("|---|---|---|")
    for gap_type in ["match", "partial", "mismatch", "omission", "parse_error"]:
        count = run.gap_type_distribution.get(gap_type, 0)
        pct = (count / total * 100) if total else 0
        lines.append(f"| {gap_type} | {count} | {pct:.0f}% |")
    lines.append("")
    lines.append("### Per-item results\n")
    lines.append("| Ref | Section | Gap type | Tok/s | Latency ms | TTFT ms | Parse |")
    lines.append("|---|---|---|---|---|---|---|")
    for it in run.items:
        check = "✓" if it.parse_ok else "✗"
        lines.append(
            f"| {it.ref} | {it.section} | {it.gap_type} | "
            f"{it.tokens_per_second:.1f} | {it.total_latency_ms:.0f} | "
            f"{it.time_to_first_token_ms:.0f} | {check} |"
        )
    lines.append("")
    lines.append("### Notes")
    lines.append("<!-- space for manual observations after reviewing the run -->")
    lines.append("")
    return "\n".join(lines)


def write_run(run: BenchmarkRun, output_path: str) -> None:
    """Append a rendered run section to the results log (creating header once)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    run_number = _next_run_number(path)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if is_new:
            f.write(_HEADER)
        f.write(render_run(run, run_number))
