"""Orchestrate one full benchmark run over HECVAT items.

For each of the first ``n_items`` non-blank, non-skipped HECVAT items:

1. retrieve top-k policy clauses (RAG grounding),
2. render the gap-analysis prompt from ``config/prompts/gap_analysis.txt``,
3. call ``ollama_client.chat()`` capturing metrics + response text,
4. parse the response as JSON into a GapFinding (invalid JSON -> ``parse_error``),
5. collect a BenchmarkItem.

Blank vendor answers become ``omission`` immediately with no LLM call (D16).
Dependencies (chat client, retriever) are injected so the runner is fully
testable with a mocked Ollama client and no real inference.
"""

from __future__ import annotations

import json
import platform
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from jinja2 import Template

from backend.config import Settings, get_settings
from backend.hecvat_parser import load_profile, parse_hecvat
from backend.models import (
    BenchmarkItem,
    BenchmarkRun,
    ChatMetrics,
    Clause,
    HecvatItem,
)
from backend.ollama_client import OllamaClient

ChatFn = Callable[..., Awaitable[tuple[str, ChatMetrics]]]
RetrieveFn = Callable[[str, int], Awaitable[list[Clause]]]
ProgressFn = Callable[[BenchmarkItem], None]

_SYSTEM_SPLIT = re.compile(r"^USER:\s*$", re.MULTILINE)


def _platform_string() -> str:
    sys_name = platform.system()
    nice = {"Linux": "Linux", "Darwin": "macOS", "Windows": "Windows"}.get(sys_name, sys_name)
    machine = platform.machine()
    return f"{nice} ({machine})"


def _split_prompt(template_text: str, context: dict) -> list[dict[str, str]]:
    """Render the Jinja prompt and split it into system/user chat messages."""
    rendered = Template(template_text).render(**context)
    rendered = rendered.strip()
    if rendered.startswith("SYSTEM:"):
        rendered = rendered[len("SYSTEM:"):]
    parts = _SYSTEM_SPLIT.split(rendered, maxsplit=1)
    if len(parts) == 2:
        system, user = parts
    else:
        system, user = "", rendered
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": user.strip()})
    return messages


def _extract_json(text: str) -> dict | None:
    """Best-effort extraction of the first JSON object from model output."""
    text = text.strip()
    # Strip markdown fences if the model added them despite instructions.
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


async def run_benchmark(
    hecvat_path: str | None = None,
    model: str | None = None,
    n_items: int | None = None,
    progress_callback: ProgressFn | None = None,
    *,
    settings: Settings | None = None,
    chat_fn: ChatFn | None = None,
    retrieve_fn: RetrieveFn | None = None,
    sheets: list[str] | None = None,
    ollama_version: str | None = None,
) -> BenchmarkRun:
    settings = settings or get_settings()
    hecvat_path = hecvat_path or settings.hecvat_path
    model = model or settings.ollama_model
    n_items = n_items or settings.benchmark_items

    profile = load_profile(settings.hecvat_profile)
    skip_sections = list(profile.get("skip_sections", []))
    if sheets is None:
        sheets = [profile.get("primary_sheet", "Organization")]

    # Wire up real dependencies unless the caller injected fakes (tests do).
    client: OllamaClient | None = None
    if chat_fn is None or retrieve_fn is None:
        client = OllamaClient(settings)
    if chat_fn is None:
        chat_fn = client.chat
    if retrieve_fn is None:
        from backend.knowledge_base import retrieve as _retrieve

        async def retrieve_fn(query: str, k: int) -> list[Clause]:  # type: ignore[misc]
            return await _retrieve(query, k, settings=settings)

    if ollama_version is None and client is not None:
        ollama_version = await client.version()
    ollama_version = ollama_version or "unknown"

    with open(settings.prompt_path, encoding="utf-8") as f:
        prompt_template = f.read()

    items: list[HecvatItem] = parse_hecvat(hecvat_path, settings.hecvat_profile, sheets=sheets)
    selected = items[:n_items]

    results: list[BenchmarkItem] = []
    run_start = time.perf_counter()

    for item in selected:
        # D16: blank vendor answer -> omission, no LLM call.
        if not item.vendor_answer:
            bench_item = BenchmarkItem(
                ref=item.ref,
                section=item.section,
                question=item.question,
                gap_type="omission",
                time_to_first_token_ms=0.0,
                tokens_per_second=0.0,
                total_latency_ms=0.0,
                parse_ok=True,
                response_snippet="(omission — blank vendor answer, no LLM call)",
            )
            results.append(bench_item)
            if progress_callback:
                progress_callback(bench_item)
            continue

        clauses = await retrieve_fn(item.question, settings.retrieval_k)
        context = {
            "ref": item.ref,
            "section": item.section,
            "question": item.question,
            "vendor_answer": item.vendor_answer,
            "policy_clauses": clauses,
        }
        messages = _split_prompt(prompt_template, context)
        prompt_chars = sum(len(m["content"]) for m in messages)
        num_ctx = settings.bucketed_num_ctx(prompt_chars)

        text, metrics = await chat_fn(
            messages,
            model=model,
            num_ctx=num_ctx,
            temperature=settings.temperature,
            num_predict=settings.num_predict,
        )

        parsed = _extract_json(text)
        if parsed and parsed.get("gap_type") in {"match", "partial", "mismatch", "omission"}:
            gap_type = parsed["gap_type"]
            parse_ok = True
        else:
            gap_type = "parse_error"
            parse_ok = False

        bench_item = BenchmarkItem(
            ref=item.ref,
            section=item.section,
            question=item.question,
            gap_type=gap_type,
            time_to_first_token_ms=metrics.time_to_first_token_ms,
            tokens_per_second=metrics.tokens_per_second,
            total_latency_ms=metrics.total_latency_ms,
            parse_ok=parse_ok,
            response_snippet=text[:200],
        )
        results.append(bench_item)
        if progress_callback:
            progress_callback(bench_item)

    total_run_time_s = time.perf_counter() - run_start
    return _aggregate(
        model=model,
        ollama_version=ollama_version,
        results=results,
        sheets=sheets,
        skip_sections=skip_sections,
        total_run_time_s=total_run_time_s,
    )


def _aggregate(
    *,
    model: str,
    ollama_version: str,
    results: list[BenchmarkItem],
    sheets: list[str],
    skip_sections: list[str],
    total_run_time_s: float,
) -> BenchmarkRun:
    llm_items = [it for it in results if it.total_latency_ms > 0]

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    avg_tps = _avg([it.tokens_per_second for it in llm_items])
    avg_lat = _avg([it.total_latency_ms for it in llm_items])
    avg_ttft = _avg([it.time_to_first_token_ms for it in llm_items])
    parse_rate = (
        sum(1 for it in results if it.parse_ok) / len(results) if results else 0.0
    )

    distribution: dict[str, int] = {}
    for it in results:
        key = it.gap_type or "parse_error"
        distribution[key] = distribution.get(key, 0) + 1

    return BenchmarkRun(
        model=model,
        ollama_version=ollama_version,
        platform=_platform_string(),
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        n_items=len(results),
        items=results,
        avg_tokens_per_second=avg_tps,
        avg_latency_ms=avg_lat,
        avg_time_to_first_token_ms=avg_ttft,
        parse_success_rate=parse_rate,
        gap_type_distribution=distribution,
        sheets_used=sheets,
        skip_sections=skip_sections,
        total_run_time_s=total_run_time_s,
    )
