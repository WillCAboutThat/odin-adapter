"""The disposable usage ledger (ADR-0027) — byte-footprint proxies for AI-heavy verbs (T-088).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from muninn_lint import (  # noqa: E402  (shared model + hashing)
    Linter,
)
from . import util  # noqa: E402  (module-attr access = the patch point)


# --------------------------------------------------------------------------- #
# Usage ledger — the first deterministic tenant of the disposable-index tier
# (ADR-0027). A byte-footprint proxy for the token cost of AI-heavy operations,
# recorded in a git-ignored `.odin/usage.jsonl`. It is operational state, not
# knowledge: never a source, never fingerprinted/linted, and disposable.
# --------------------------------------------------------------------------- #
def _source_bytes(root, sid) -> int:
    """Bytes of a source's current text (its `source-text.md` aid, else the
    current canonical file) — a proxy for how much an adapter reads to derive
    from it. Missing/opaque sources count as 0. Never raises for a bad id."""
    d = Path(root) / "sources" / sid
    if not d.is_dir():
        return 0
    aid = d / "source-text.md"
    if aid.exists():
        return aid.stat().st_size
    cands = [p for p in d.glob("source.*")
             if p.is_file() and not p.name.startswith("source.v")]
    return max((p.stat().st_size for p in cands), default=0)


def log_usage(root, op, *, bytes_in=0, bytes_out=0, **extra) -> None:
    """Append one usage record to `<root>/.odin/usage.jsonl` (ADR-0027).

    Best-effort by design: usage accounting must never break the operation it
    measures, so every failure is swallowed. `.odin/` is disposable operational
    state — git-ignored, excluded from lint and the fingerprint."""
    try:
        d = Path(root) / ".odin"
        d.mkdir(exist_ok=True)
        rec = {"ts": util._now(), "op": str(op),
               "bytes_in": int(bytes_in or 0), "bytes_out": int(bytes_out or 0)}
        rec.update(extra)
        with (d / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def usage_report(root) -> dict:
    """Aggregate the usage ledger by op: {total_ops, by_op: {op: {count, bytes_in,
    bytes_out, tokens, tokens_n}}}. Absent ledger → empty.

    `tokens` sums the *real* token counts when they were recorded; `tokens_n` is how
    many records carried one — so a reader can tell "0 tokens logged" (proxy-only, the
    common case) from "tokens genuinely summed to 0" (never happens for an AI verb)."""
    out: dict = {"total_ops": 0, "by_op": {}}
    p = Path(root) / ".odin" / "usage.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        op = str(rec.get("op", "?"))
        agg = out["by_op"].setdefault(
            op, {"count": 0, "bytes_in": 0, "bytes_out": 0, "tokens": 0, "tokens_n": 0})
        agg["count"] += 1
        agg["bytes_in"] += int(rec.get("bytes_in", 0) or 0)
        agg["bytes_out"] += int(rec.get("bytes_out", 0) or 0)
        if rec.get("tokens") is not None:
            agg["tokens"] += int(rec.get("tokens") or 0)
            agg["tokens_n"] += 1
        out["total_ops"] += 1
    return out


def _scope_bytes(root, ids) -> int:
    """Deterministic byte-footprint of a set of doc/source ids — the readable bytes an
    AI-heavy verb (ask/review/synthesize) grounded in. A source counts its current
    text (its `source-text.md` aid or text canonical, via `_source_bytes`); any other
    doc (summary/insight/decision/…) counts its file size. Unknown ids count 0. This
    is the honest *proxy* for cost when real token counts aren't exposed (T-088)."""
    root = Path(root)
    linter = Linter(root)
    linter.load()
    total = 0
    for i in ids or []:
        d = linter.by_id.get(i)
        if d is None:
            continue
        if d.kind == "source":
            total += _source_bytes(root, i)
        else:
            try:
                total += d.path.stat().st_size
            except OSError:
                pass
    return total


def usage_log(root, op, *, scope=None, bytes_in=None, bytes_out=0, tokens=None,
              note=None):
    """Append a usage record for an **adapter verb** the Core never sees itself —
    `ask`, `review`, `synthesize` (T-088). These are the real token spenders, so
    measuring them is what answers "is routine `review` worth its cost?".

    `bytes_in` defaults to the deterministic `_scope_bytes` of `scope` (the doc/source
    ids the verb read) — a faithful, reproducible *proxy* for how much it chewed. An
    explicit `bytes_in` overrides it. `tokens` is the **real** count when the harness
    exposes it (Claude Code /cost, an API `usage` field, subagent task metadata) and
    stays null otherwise — the ledger is honest about which it has. Best-effort like
    all usage accounting: it never fails the verb it measures.

    Returns the record's computed fields (for the caller to echo)."""
    ids = list(scope or [])
    if bytes_in is None:
        bytes_in = _scope_bytes(root, ids)
    extra = {}
    if tokens is not None:
        extra["tokens"] = int(tokens)
    if ids:
        extra["scope_n"] = len(ids)
    if note:
        extra["note"] = str(note)
    log_usage(root, op, bytes_in=bytes_in, bytes_out=bytes_out, **extra)
    return {"op": op, "bytes_in": bytes_in, "bytes_out": int(bytes_out or 0),
            "tokens": tokens, "scope_n": len(ids)}
