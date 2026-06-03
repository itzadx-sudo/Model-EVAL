"""Central configuration — pydantic-settings reads .env once, used everywhere.

A single ``Settings`` object is the only source of runtime configuration. No
module reads ``os.environ`` directly. Models are intentionally *not* validated
against a fixed allow-list: any Ollama-compatible model name must work without
code changes (see OPEN_DECISIONS D20/D23).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:2b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_keep_alive: int = 600
    ollama_num_parallel: int = 1
    ollama_kv_cache_type: str = "q8_0"
    ollama_num_ctx_max: int = 4096
    ollama_num_threads: int = 0

    # Benchmark
    hecvat_path: str = "./samples/sample_hecvat_template.xlsx"
    hecvat_profile: str = "./config/hecvat_profile.yaml"
    prompt_path: str = "./config/prompts/gap_analysis.txt"
    kb_dir: str = "./knowledge_base"
    chroma_dir: str = "./chroma"
    retrieval_k: int = 4
    benchmark_items: int = 20
    benchmark_results_path: str = "docs/benchmark_results.md"

    # Models — suggestions surfaced in the GUI dropdown. NOT a hard limit; the
    # GUI also lets you type any model name (gemma3:4b, mistral, qwen2.5:7b, ...).
    model_shortlist: str = Field(
        default="gemma3:2b,phi4-mini:3.8b,gemma3:4b,llama3.2:3b,mistral,gemma2:9b,qwen2.5:7b"
    )

    # Gap-analysis inference params (D13: bucketed num_ctx only)
    temperature: float = 0.1
    num_predict: int = 200

    # Logging
    log_level: str = "INFO"

    @property
    def shortlist(self) -> list[str]:
        """Suggested models as a clean list (duplicates/blank entries removed)."""
        seen: list[str] = []
        for name in self.model_shortlist.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.append(name)
        return seen

    def bucketed_num_ctx(self, prompt_chars: int) -> int:
        """Pick a context window from the allowed buckets only (D13).

        The prompt is short in the prototype, so we only ever use 2048 or 4096.
        Roughly ~4 chars/token; 2048 tokens ~= 8k chars of headroom.
        """
        buckets = [2048, 4096]
        buckets = [b for b in buckets if b <= self.ollama_num_ctx_max] or [buckets[0]]
        estimated_tokens = prompt_chars / 4
        for b in buckets:
            if estimated_tokens < b * 0.7:
                return b
        return buckets[-1]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
