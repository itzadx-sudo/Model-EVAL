"""Benchmark runner tests — fully mocked Ollama, no real inference.

Asserts the two non-negotiables: blank answers and skip-sections produce ZERO
LLM calls, and that valid/invalid JSON map to the right gap_type / parse_ok.
"""

from __future__ import annotations

import json

import pytest

from backend.benchmark_runner import run_benchmark
from backend.config import Settings
from backend.models import ChatMetrics, Clause


@pytest.fixture
def settings(sample_hecvat, profile_path) -> Settings:
    return Settings(
        hecvat_path=sample_hecvat,
        hecvat_profile=profile_path,
        prompt_path="config/prompts/gap_analysis.txt",
        benchmark_items=50,
    )


def make_chat(call_log, response):
    async def chat_fn(messages, model, num_ctx, temperature, num_predict):
        call_log.append({"model": model, "num_ctx": num_ctx, "messages": messages})
        metrics = ChatMetrics(
            time_to_first_token_ms=120.0,
            tokens_per_second=25.0,
            total_latency_ms=900.0,
            eval_count=200,
        )
        return response, metrics

    return chat_fn


async def fake_retrieve(query, k):
    return [Clause(id="sample_policy-p1-c0", text="Encrypt in transit with TLS 1.2+.", score=0.9)]


async def test_blank_and_skip_make_no_llm_calls(settings):
    call_log: list[dict] = []
    valid = json.dumps({"gap_type": "match", "summary": "ok", "policy_refs": []})
    run = await run_benchmark(
        model="any-model:latest",
        n_items=50,
        settings=settings,
        chat_fn=make_chat(call_log, valid),
        retrieve_fn=fake_retrieve,
        ollama_version="test",
    )

    # No HIPA item should ever be sent to the model.
    sent_refs = [m["messages"][-1]["content"] for m in call_log]
    assert all("HIPA-01" not in c for c in sent_refs)

    # Omission items (blank answers) made no call and are flagged omission.
    omissions = [it for it in run.items if it.gap_type == "omission"]
    assert any(it.ref == "DOCU-03" for it in omissions)
    for it in omissions:
        assert it.total_latency_ms == 0.0  # no LLM call

    # Every LLM call used a bucketed num_ctx.
    assert all(m["num_ctx"] in (2048, 4096) for m in call_log)


async def test_num_ctx_is_bucketed(settings):
    call_log: list[dict] = []
    valid = json.dumps({"gap_type": "partial", "summary": "x", "policy_refs": []})
    await run_benchmark(
        model="m",
        n_items=50,
        settings=settings,
        chat_fn=make_chat(call_log, valid),
        retrieve_fn=fake_retrieve,
        ollama_version="test",
    )
    assert call_log
    assert all(m["num_ctx"] in (2048, 4096) for m in call_log)


async def test_invalid_json_is_parse_error(settings):
    call_log: list[dict] = []
    run = await run_benchmark(
        model="m",
        n_items=50,
        settings=settings,
        chat_fn=make_chat(call_log, "this is not json at all"),
        retrieve_fn=fake_retrieve,
        ollama_version="test",
    )
    answered = [it for it in run.items if it.gap_type != "omission"]
    assert answered
    assert all(it.gap_type == "parse_error" and not it.parse_ok for it in answered)


async def test_json_with_fences_still_parses(settings):
    call_log: list[dict] = []
    fenced = "```json\n" + json.dumps({"gap_type": "mismatch", "summary": "no", "policy_refs": []}) + "\n```"
    run = await run_benchmark(
        model="m",
        n_items=50,
        settings=settings,
        chat_fn=make_chat(call_log, fenced),
        retrieve_fn=fake_retrieve,
        ollama_version="test",
    )
    answered = [it for it in run.items if it.gap_type != "omission"]
    assert all(it.parse_ok for it in answered)
    assert all(it.gap_type == "mismatch" for it in answered)


async def test_any_model_name_accepted(settings):
    """No allow-list / size cap: an arbitrary model name runs fine (D23)."""
    call_log: list[dict] = []
    valid = json.dumps({"gap_type": "match", "summary": "ok", "policy_refs": []})
    run = await run_benchmark(
        model="mistral-nemo:12b",
        n_items=5,
        settings=settings,
        chat_fn=make_chat(call_log, valid),
        retrieve_fn=fake_retrieve,
        ollama_version="test",
    )
    assert run.model == "mistral-nemo:12b"
    assert all(m["model"] == "mistral-nemo:12b" for m in call_log)
