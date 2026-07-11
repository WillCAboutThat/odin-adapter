# /// script
# requires-python = ">=3.9"
# ///
# ^ PEP-723 (ADR-0031): launched via `uv run --script`, cross-platform, no host
#   `python3` needed. Stdlib-only, so no dependencies are declared.
"""SessionStart hook — best-effort, NON-BLOCKING warm of the semantic index (T-092).

The ingest-boundary warm (T-091) covers *ingest → retrieve*; this covers the other
flow — *open a cold session → query first* — by loading the embedding model into VRAM
at session start, so the user's first `retrieve`/`search` doesn't pay the ~27s cold-load.
`retrieve` self-heals regardless (T-090), so this only ever *removes latency*, never a
correctness step.

KNOWN LIMITATION (2026-07-11, T-020 research): `${CLAUDE_PLUGIN_ROOT}` is **not
expanded inside SessionStart hooks** on current Claude Code (an open upstream bug —
anthropics/claude-code #27145 / #39550 / #43380), so `hooks.json`'s launch command
`uv run --script "${CLAUDE_PLUGIN_ROOT}/hooks/warm_index.py"` resolves to an empty
prefix and this hook is **silently inert on marketplace installs** until that bug is
patched. Impact is only the cold-load latency above (a comfort optimization, never
correctness — retrieve self-heals). No in-repo workaround exists: a SessionStart hook
has no reliable way to locate its own bundled script. Re-enables automatically when
upstream fixes the variable; tracked with the (also-blocked) freshness hook, T-020.

Three properties make it safe to ship to every plugin user:

  1. **Non-blocking.** A SessionStart hook that *waited* on a model load would make every
     session start slow — the opposite of the goal. So this only *gates + spawns a
     detached child* and returns immediately; the child does the (blocking) warm in the
     background while the user reads/types.
  2. **Gated.** It warms ONLY when a `muninn.yml` **and** an existing `.odin/semantic.db`
     are found at/above cwd — i.e. semantic retrieval is actually in use here. An
     unrelated (non-ODIN) session touches no Ollama at all.
  3. **Best-effort + quiet.** Every failure is swallowed (no Ollama, no index, whatever)
     — like `ensure_deps.py`, it never fails the session, and `find` is unaffected.

Stdlib only (urllib + sqlite3) — no `muninn_core`/`pyyaml` import, so it needs no
dependency bootstrap and can't break on a missing one.

Residency tail: Ollama unloads an idle model after ~5 min, so the warm sets a longer
`keep_alive` (env `ODIN_OLLAMA_KEEP_ALIVE`, default 30m). For a fully persistent model,
set `OLLAMA_KEEP_ALIVE` on the Ollama host (see `docs/odin/ollama-setup.md`).
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DEFAULT_URL = os.environ.get("ODIN_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("ODIN_EMBED_MODEL", "nomic-embed-text")
KEEP_ALIVE = os.environ.get("ODIN_OLLAMA_KEEP_ALIVE", "30m")


def find_muninn(start):
    """The nearest `muninn.yml` at or above `start`, else None."""
    d = Path(start).resolve()
    for cand in (d, *d.parents):
        if (cand / "muninn.yml").exists():
            return cand
    return None


def should_warm(cwd):
    """Pure gate (testable): return `(root, model)` to warm, or None. Warms ONLY when a
    Muninn **and** an existing semantic index are present — so a non-ODIN session never
    spawns Ollama. Reads the index's own embedding model from the sidecar (stdlib
    sqlite3) so the warm loads the *right* model."""
    root = find_muninn(cwd)
    if root is None:
        return None
    db = root / ".odin" / "semantic.db"
    if not db.exists():
        return None
    model = DEFAULT_MODEL
    try:
        con = sqlite3.connect(str(db))
        row = con.execute("SELECT value FROM meta WHERE key='model'").fetchone()
        con.close()
        if row and row[0]:
            model = row[0]
    except Exception:
        pass
    return str(root), model


def _do_warm(model, url):
    """The detached child's job: a single embed → loads the model into VRAM with a long
    keep_alive. Blocking (that's why it's a background child), best-effort."""
    import json
    import urllib.request
    try:
        payload = json.dumps({"model": model, "input": ["warm"],
                              "keep_alive": KEEP_ALIVE}).encode("utf-8")
        req = urllib.request.Request(url.rstrip("/") + "/api/embed", data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=180).read()
    except Exception:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--do-warm":                 # re-entrant: the detached child
        _do_warm(argv[1], argv[2] if len(argv) > 2 else DEFAULT_URL)
        return 0

    decision = should_warm(os.getcwd())                 # SessionStart: gate
    if decision is None:
        return 0                                        # no Muninn / no index → nothing
    _root, model = decision

    # Fire-and-forget: a DETACHED child does the (slow) warm; we return at once so
    # session start never waits on a model load. Cross-platform detachment.
    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  stdin=subprocess.DEVNULL)
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__),
                          "--do-warm", model, DEFAULT_URL], **kwargs)
    except Exception:
        pass                                            # best-effort; retrieve self-heals
    return 0


if __name__ == "__main__":
    sys.exit(main())
