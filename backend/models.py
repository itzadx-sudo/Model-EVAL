"""Shared dataclasses for the benchmark harness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HecvatItem:
    ref: str  # e.g. "DOCU-01"
    section: str  # e.g. "Documentation"
    question: str  # full question text
    vendor_answer: str | None  # None if blank
    sheet_name: str  # which HECVAT sheet it came from

    @property
    def prefix(self) -> str:
        """Section prefix used for skip logic, e.g. 'DOCU' from 'DOCU-01'."""
        return self.ref.split("-")[0].strip().upper()


@dataclass
class Clause:
    id: str  # clause id: filename-page-chunk_index
    text: str
    score: float = 0.0


@dataclass
class ChatMetrics:
    time_to_first_token_ms: float
    tokens_per_second: float
    total_latency_ms: float
    eval_count: int = 0


@dataclass
class GapFinding:
    gap_type: str  # match / partial / mismatch / omission
    summary: str
    policy_refs: list[str] = field(default_factory=list)


@dataclass
class BenchmarkItem:
    ref: str
    section: str
    question: str
    gap_type: str | None  # match / partial / mismatch / omission / parse_error
    time_to_first_token_ms: float
    tokens_per_second: float
    total_latency_ms: float
    parse_ok: bool
    response_snippet: str  # first 200 chars of raw LLM response


@dataclass
class BenchmarkRun:
    model: str
    ollama_version: str
    platform: str  # Linux / macOS / Windows + GPU/CPU info
    timestamp: str  # ISO 8601
    n_items: int
    items: list[BenchmarkItem]
    avg_tokens_per_second: float
    avg_latency_ms: float
    avg_time_to_first_token_ms: float
    parse_success_rate: float
    gap_type_distribution: dict[str, int]
    sheets_used: list[str] = field(default_factory=list)
    skip_sections: list[str] = field(default_factory=list)
    total_run_time_s: float = 0.0
