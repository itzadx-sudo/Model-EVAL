"""Aegis prototype entry point — full lifecycle manager.

Running ``python app.py`` brings the whole system up in one command and tears it
all down cleanly on stop (Ctrl+C / SIGTERM):

  START  →  1. start the Ollama server (if not already running)
            2. pull/warm the default model + embedding model
            3. build the RAG knowledge base (KB / KV store) from knowledge_base/
            4. launch the Streamlit GUI
  STOP   →  terminate the Streamlit process, and stop the Ollama server *only if
            this script started it* (a pre-existing server the user launched is
            left running). The KB is persisted to disk, not deleted.

Everything is best-effort: if the `ollama` binary is missing or a model can't be
pulled, the GUI still launches (and shows Ollama offline) instead of crashing.

Flags:
  --no-ollama   don't manage the Ollama server (assume it's already up)
  --no-pull     don't pull/warm models
  --no-kb       don't build the knowledge base on startup
  --gui-only    just launch the GUI (equivalent to --no-ollama --no-pull --no-kb)
  --port N      Streamlit port (default 8501)
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402

# Child processes we own and must clean up on exit.
_children: list[subprocess.Popen] = []
_ollama_proc: subprocess.Popen | None = None


def _log(msg: str) -> None:
    print(f"[aegis] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Ollama lifecycle
# ---------------------------------------------------------------------------
def _ollama_up(base_url: str) -> bool:
    try:
        httpx.get(f"{base_url.rstrip('/')}/api/version", timeout=2.0).raise_for_status()
        return True
    except Exception:
        return False


def start_ollama(settings) -> bool:
    """Ensure Ollama is reachable. Returns True if we *started* it ourselves."""
    global _ollama_proc
    if _ollama_up(settings.ollama_base_url):
        _log("Ollama already running — reusing it.")
        return False
    if shutil.which("ollama") is None:
        _log("⚠ 'ollama' binary not found on PATH; GUI will show Ollama offline.")
        return False

    env = os.environ.copy()
    env.update(
        {
            "OLLAMA_KEEP_ALIVE": str(settings.ollama_keep_alive),
            "OLLAMA_NUM_PARALLEL": str(settings.ollama_num_parallel),
            "OLLAMA_KV_CACHE_TYPE": settings.ollama_kv_cache_type,
            "OLLAMA_NUM_THREADS": str(settings.ollama_num_threads),
        }
    )
    _log("Starting Ollama server (ollama serve)…")
    _ollama_proc = subprocess.Popen(
        ["ollama", "serve"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to ~20s for it to come up.
    for _ in range(40):
        if _ollama_up(settings.ollama_base_url):
            _log("Ollama is up.")
            return True
        time.sleep(0.5)
    _log("⚠ Ollama did not become ready in time; continuing anyway.")
    return True


def warm_models(settings) -> None:
    """Pull (if needed) and warm the default chat + embedding models."""
    if shutil.which("ollama") is None or not _ollama_up(settings.ollama_base_url):
        return
    for model in {settings.ollama_model, settings.ollama_embed_model}:
        try:
            present = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=30
            ).stdout
            if model.split(":")[0] not in present:
                _log(f"Pulling {model} (first run can take a while)…")
                subprocess.run(["ollama", "pull", model], timeout=1800, check=False)
            else:
                _log(f"Model {model} already present.")
        except Exception as exc:  # noqa: BLE001
            _log(f"⚠ Could not prepare model {model}: {exc}")


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------
def build_kb(settings) -> None:
    docs = [
        p
        for p in Path(settings.kb_dir).rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    ]
    if not docs:
        _log(
            f"No documents in {settings.kb_dir}/ — skipping KB build. "
            "(Drop policy .pdf/.docx/.md/.txt there, or use the GUI button.)"
        )
        return
    if not _ollama_up(settings.ollama_base_url):
        _log("Ollama offline — skipping KB build (embeddings need Ollama).")
        return
    try:
        from backend.knowledge_base import build

        _log(f"Building knowledge base from {len(docs)} document(s)…")
        added = asyncio.run(build(settings.kb_dir, settings))
        _log(f"Knowledge base ready — {added} new chunk(s) embedded.")
    except Exception as exc:  # noqa: BLE001
        _log(f"⚠ KB build failed (continuing): {exc}")


# ---------------------------------------------------------------------------
# Streamlit GUI
# ---------------------------------------------------------------------------
def launch_gui(port: int) -> subprocess.Popen:
    gui = ROOT / "gui" / "app.py"
    _log(f"Launching Streamlit GUI on http://localhost:{port} …")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(gui),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ]
    )
    _children.append(proc)
    return proc


# ---------------------------------------------------------------------------
# Teardown — stop everything we started
# ---------------------------------------------------------------------------
def _terminate(proc: subprocess.Popen | None, name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    _log(f"Stopping {name}…")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _log(f"Force-killing {name}.")
        proc.kill()


def shutdown() -> None:
    for proc in _children:
        _terminate(proc, "Streamlit GUI")
    # Only stop Ollama if we started it; a user's own server is left alone.
    _terminate(_ollama_proc, "Ollama server")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis prototype lifecycle manager")
    parser.add_argument("--no-ollama", action="store_true")
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--no-kb", action="store_true")
    parser.add_argument("--gui-only", action="store_true")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    if args.gui_only:
        args.no_ollama = args.no_pull = args.no_kb = True

    settings = get_settings()
    atexit.register(shutdown)
    signal.signal(signal.SIGTERM, lambda *_: (shutdown(), sys.exit(0)))

    try:
        if not args.no_ollama:
            start_ollama(settings)
        if not args.no_pull:
            warm_models(settings)
        if not args.no_kb:
            build_kb(settings)

        gui = launch_gui(args.port)
        _log("System is up. Press Ctrl+C to stop everything.")
        gui.wait()  # block until the GUI exits
    except KeyboardInterrupt:
        _log("Interrupted — shutting down.")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
