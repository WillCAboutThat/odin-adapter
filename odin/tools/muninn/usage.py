"""The disposable usage ledger (ADR-0027) — byte-footprint proxies for AI-heavy verbs (T-088).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from . import snapshot, util  # noqa: E402  (module-attr access = the patch point)


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


def read_usage_records(root) -> list:
    """The raw ledger, tolerantly parsed: one dict per well-formed line, bad lines
    skipped (the ledger is disposable — a torn tail must never break a report)."""
    p = Path(root) / ".odin" / "usage.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _pctl(sorted_vals, q):
    """Nearest-rank percentile of an already-sorted, non-empty list."""
    import math
    return sorted_vals[max(0, math.ceil(q * len(sorted_vals)) - 1)]


_AI_VERBS = ("ask", "review", "synthesize")
# Ops whose presence implies reasoning happened around them (derive writes the
# products; find/retrieve/search are the lookups reasoning rides on).
_AI_SIGNAL_OPS = ("derive", "find", "retrieve", "search")
_UNDERREPORT_THRESHOLD = 5   # below this, a base is too young to judge


def usage_report(root) -> dict:
    """Aggregate the usage ledger by op: {total_ops, by_op: {op: {count, bytes_in,
    bytes_out, tokens, tokens_n, timed_n, total_ms, p50_ms, p95_ms}}}. Absent
    ledger → empty.

    `tokens` sums the *real* token counts when they were recorded; `tokens_n` is how
    many records carried one — so a reader can tell "0 tokens logged" (proxy-only, the
    common case) from "tokens genuinely summed to 0" (never happens for an AI verb).
    Durations get the same honesty (T-123): `timed_n` counts records that carried a
    `duration_ms` (older ledgers predate timing), and the percentiles are `None` —
    never a fake zero — when nothing was timed."""
    out: dict = {"total_ops": 0, "by_op": {}}
    durations: dict = {}
    for rec in read_usage_records(root):
        op = str(rec.get("op", "?"))
        agg = out["by_op"].setdefault(
            op, {"count": 0, "bytes_in": 0, "bytes_out": 0, "tokens": 0, "tokens_n": 0,
                 "timed_n": 0, "total_ms": 0, "p50_ms": None, "p95_ms": None})
        agg["count"] += 1
        agg["bytes_in"] += int(rec.get("bytes_in", 0) or 0)
        agg["bytes_out"] += int(rec.get("bytes_out", 0) or 0)
        if rec.get("tokens") is not None:
            agg["tokens"] += int(rec.get("tokens") or 0)
            agg["tokens_n"] += 1
        if rec.get("duration_ms") is not None:
            durations.setdefault(op, []).append(float(rec["duration_ms"]))
        out["total_ops"] += 1
    for op, ds in durations.items():
        ds.sort()
        agg = out["by_op"][op]
        agg["timed_n"] = len(ds)
        agg["total_ms"] = round(sum(ds), 1)
        agg["p50_ms"] = round(_pctl(ds, 0.50), 1)
        agg["p95_ms"] = round(_pctl(ds, 0.95), 1)

    # T-152(c): the report discloses its own blind spot. Core ops are
    # auto-recorded and trustworthy; the AI verbs (ask/review/synthesize) are
    # adapter SELF-reports — extrinsic bookkeeping that sessions demonstrably
    # drop. When the ledger shows real reasoning-shaped traffic and NO AI-verb
    # record, the honest reading is "under-reported", never "no AI verbs ran" —
    # surface it, don't let the absence masquerade as measurement (I5).
    ai_records = sum(a["count"] for op, a in out["by_op"].items()
                     if op in _AI_VERBS)
    signal = sum(a["count"] for op, a in out["by_op"].items()
                 if op in _AI_SIGNAL_OPS)
    out["ai_verb_records"] = ai_records
    out["underreported"] = ai_records == 0 and signal >= _UNDERREPORT_THRESHOLD
    if out["underreported"]:
        out["caveat"] = (
            "AI-verb records absent (ask/review/synthesize) while the ledger "
            "shows reasoning-shaped Core traffic — the sessions doing this work "
            "did not log them; treat verb/token figures as a floor, not the "
            "picture.")
    return out


# --------------------------------------------------------------------------- #
# The HTML view (T-123) — one self-contained file rendered FROM the ledger.
# JSONL stays the storage; this is a disposable projection of disposable state,
# so it carries no Core guarantee and can be regenerated at will. No external
# requests (no CDN, no fonts, no scripts): the file must open anywhere, forever.
# --------------------------------------------------------------------------- #
_HTML_CSS = """
:root { --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --bar:#2a78d6;
        --grid:#e7e6e2; }
@media (prefers-color-scheme: dark) {
  :root { --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --bar:#3987e5;
          --grid:#33322f; }
}
body { background:var(--surface); color:var(--ink); margin:2rem auto; max-width:52rem;
       padding:0 1rem; font:15px/1.5 system-ui, sans-serif; }
h1 { font-size:1.3rem; } h2 { font-size:1.05rem; margin-top:2rem; }
.meta { color:var(--ink-2); font-size:0.85rem; }
.caveat { border:1px solid var(--grid); border-left:4px solid var(--bar);
          padding:0.5rem 0.75rem; border-radius:4px; font-size:0.9rem; }
table { border-collapse:collapse; width:100%; margin-top:0.75rem;
        font-variant-numeric:tabular-nums; }
th, td { text-align:right; padding:0.3rem 0.6rem; border-bottom:1px solid var(--grid); }
th:first-child, td:first-child { text-align:left; }
th { color:var(--ink-2); font-weight:600; font-size:0.8rem; }
.tiles { display:flex; gap:1.5rem; flex-wrap:wrap; margin-top:1rem; }
.tile .v { font-size:1.5rem; font-weight:650; font-variant-numeric:tabular-nums; }
.tile .k { color:var(--ink-2); font-size:0.8rem; }
svg text { font:12px system-ui, sans-serif; fill:var(--ink); }
svg .val { fill:var(--ink-2); }
svg .bar { fill:var(--bar); }
"""


def _fmt(n):
    if n is None:
        return "—"
    if isinstance(n, float) and n != int(n):
        return f"{n:,.1f}"
    return f"{int(n):,}"


def _bar_chart(rows, fmt=_fmt):
    """One single-series horizontal bar chart as inline SVG. `rows` = [(label, value)],
    already sorted. Single series → one hue, no legend; identity is the row label and
    the value is direct-labeled at the data end (text tokens, never the series color)."""
    import html as _h
    if not rows:
        return ""
    label_w, chart_w, bh, gap, r = 110, 420, 20, 8, 4
    vmax = max(v for _, v in rows) or 1
    h = len(rows) * (bh + gap)
    parts = [f'<svg viewBox="0 0 640 {h}" width="100%" height="{h}" role="img">']
    for i, (label, v) in enumerate(rows):
        y = i * (bh + gap)
        w = max(1.0, chart_w * v / vmax)
        lab = _h.escape(str(label))
        parts.append(f'<g><title>{lab}: {fmt(v)}</title>')
        parts.append(f'<text x="{label_w - 8}" y="{y + bh - 6}" text-anchor="end">{lab}</text>')
        if w > r:  # square baseline edge, 4px-rounded data end
            parts.append(
                f'<path class="bar" d="M{label_w},{y} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} '
                f'v{bh - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z"/>')
        else:
            parts.append(f'<rect class="bar" x="{label_w}" y="{y}" width="{w:.1f}" height="{bh}"/>')
        parts.append(f'<text class="val" x="{label_w + w + 8:.1f}" y="{y + bh - 6}">{fmt(v)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def usage_html(root) -> str:
    """Render the usage ledger as one self-contained HTML page: summary tiles, the
    per-op table (the full data — every chart's fallback), and two single-series bar
    charts (time by op · bytes by op). Empty ledger → an honest empty page."""
    import html as _h
    rep = usage_report(root)
    when = util._now()
    head = ("<meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'>"
            f"<title>Odin usage — {_h.escape(str(root))}</title>"
            f"<style>{_HTML_CSS}</style>"
            f"<h1>Odin usage ledger</h1>"
            f"<p class='meta'>{_h.escape(str(root))} · generated {_h.escape(when)} · "
            "disposable operational state (ADR-0027) — regenerate at will</p>")
    if rep.get("underreported"):
        head += f"<p class='caveat'>⚠ {_h.escape(rep['caveat'])}</p>"
    if not rep["by_op"]:
        return head + "<p>No usage recorded yet.</p>"
    ops = sorted(rep["by_op"].items(), key=lambda kv: -kv[1]["count"])
    tokens = sum(a["tokens"] for _, a in ops)
    tiles = [("ops", rep["total_ops"]),
             ("bytes in", sum(a["bytes_in"] for _, a in ops)),
             ("bytes out", sum(a["bytes_out"] for _, a in ops)),
             ("real tokens", tokens if tokens else None),
             ("timed", sum(a["timed_n"] for _, a in ops))]
    tile_html = "".join(f"<div class='tile'><div class='v'>{_fmt(v)}</div>"
                        f"<div class='k'>{k}</div></div>" for k, v in tiles)
    rows = "".join(
        f"<tr><td>{_h.escape(op)}</td><td>{_fmt(a['count'])}</td>"
        f"<td>{_fmt(a['bytes_in'])}</td><td>{_fmt(a['bytes_out'])}</td>"
        f"<td>{_fmt(a['tokens']) if a['tokens_n'] else '—'}</td>"
        f"<td>{_fmt(a['total_ms'])}</td><td>{_fmt(a['p50_ms'])}</td>"
        f"<td>{_fmt(a['p95_ms'])}</td></tr>" for op, a in ops)
    table = ("<table><tr><th>op</th><th>count</th><th>bytes in</th><th>bytes out</th>"
             "<th>tokens</th><th>total ms</th><th>p50 ms</th><th>p95 ms</th></tr>"
             f"{rows}</table>")
    time_rows = sorted(((op, a["total_ms"]) for op, a in ops if a["timed_n"]),
                       key=lambda kv: -kv[1])
    byte_rows = sorted(((op, a["bytes_in"] + a["bytes_out"]) for op, a in ops
                        if a["bytes_in"] + a["bytes_out"]), key=lambda kv: -kv[1])
    charts = ""
    if time_rows:
        charts += "<h2>Time by op (total ms)</h2>" + _bar_chart(time_rows)
    if byte_rows:
        charts += "<h2>Bytes by op (in + out)</h2>" + _bar_chart(byte_rows)
    return head + f"<div class='tiles'>{tile_html}</div>{table}{charts}"


def _scope_bytes(root, ids) -> int:
    """Deterministic byte-footprint of a set of doc/source ids — the readable bytes an
    AI-heavy verb (ask/review/synthesize) grounded in. A source counts its current
    text (its `source-text.md` aid or text canonical, via `_source_bytes`); any other
    doc (summary/insight/decision/…) counts its file size. Unknown ids count 0. This
    is the honest *proxy* for cost when real token counts aren't exposed (T-088)."""
    root = Path(root)
    linter = snapshot.load_snapshot(root)   # read-only; reused until the base changes (T-116)
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
