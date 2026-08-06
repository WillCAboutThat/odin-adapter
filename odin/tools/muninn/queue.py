"""The work queue's lifecycle ops (T-209, refining ADR-0048's Phase 3).

`queue/` is pre-cognition staging: durable, git-carried, owner-legible task
files awaiting an executor session. Tasks are **not knowledge** — never cited,
never grounding, invisible to lint and retrieval — which is why the directory
itself carries no format guarantee (the `inbox/` species, ADR-0037 additive).

**Files remain the protocol; these ops are its shared writer.** ADR-0048 built
the queue web-side with no Core ops (the inbox precedent), but the queue
differs from the inbox in one load-bearing way: a task has a *lifecycle* with
invariants — re-statused never deleted, legal transitions only, an append-only
per-task log. Lifecycle-bearing staging already has Core ops (candidates,
ADR-0033); hand-editing task files from every executor session re-derives the
protocol per session and lets any of them get it wrong. So the lifecycle
moved here — one implementation both planes drive (the web through the same
registry, ADR-0042). Executing a task stays entirely the executor's job; the
Core only keeps the ledger honest. Explicitly still NOT a job system: no
claiming, no ownership, no attempt history (ADR-0048's rejections stand).
"""
from pathlib import Path

import re

from .util import _locked, _now


_QUEUE = "queue"


#: The task types the authoring surfaces offer. The web derives its form
#: options from this enum via the op schema (odin_mcp.TOOLS) — one source.
TASK_TYPES = ("ingest", "synthesize", "map", "explore", "drift-check",
              "ask", "review", "other")


#: Lifecycle (ADR-0048): pending → done | declined (executor verdicts),
#: blocked (parked, may resume), cancelled (owner withdrew). Terminal states
#: stay terminal — a finished task is history, not a slot to reuse.
TRANSITIONS = {
    "pending": {"done", "declined", "blocked", "cancelled"},
    "blocked": {"pending", "done", "declined", "cancelled"},
    "done": set(),
    "declined": set(),
    "cancelled": set(),
}


_STATUS_ORDER = {"pending": 0, "blocked": 1, "done": 2, "declined": 3,
                 "cancelled": 4}


def _parse_task(path: Path):
    """A task file into a dict, or None if unreadable/idless. The format is
    deliberately hand-editable (owner-legible staging), so this parser is
    forgiving: `key: value` frontmatter + an `inputs:` dash-list + the body."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None
    front, body = m.group(1), m.group(2)
    task: dict = {"file": path.name, "body": body.strip(), "inputs": []}
    for line in front.splitlines():
        if line.startswith("  - "):
            task["inputs"].append(line[4:].strip())
        elif ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            if k.strip() != "inputs":
                task[k.strip()] = v.strip()
    return task if task.get("id") else None


def queue_list(root, status=None):
    """Enumerate the queue — pending first, then blocked, then history.
    `status` filters to one lifecycle state. Read-only; the executor's first
    call ("process the Muninn work queue") and the web page's render."""
    root = Path(root)
    d = root / _QUEUE
    tasks = []
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            t = _parse_task(p)
            if t and (status is None or t.get("status") == status):
                tasks.append(t)
    tasks.sort(key=lambda t: (_STATUS_ORDER.get(t.get("status", ""), 9), t["id"]))
    return {"tasks": tasks,
            "pending_count": sum(1 for t in tasks if t.get("status") == "pending")}


@_locked
def queue_create(root, type, outcome, *, inputs=None, created_by=None,
                 when=None):
    """Author a task into `queue/`. Authoring IS the scoped consent act
    (ADR-0048): the task authorizes exactly the named operations on the named
    inputs, and results land on the candidates rail — never direct base
    writes. Never overwrites: an id collision gets a numeric suffix."""
    if type not in TASK_TYPES:
        raise ValueError(f"unknown task type {type!r} (one of {', '.join(TASK_TYPES)})")
    outcome = (outcome or "").strip()
    if not outcome:
        raise ValueError("a task needs a requested outcome — say what you want done")
    when = when or _now()
    created_by = created_by or "core"
    inputs = [i.strip() for i in (inputs or []) if i.strip()]
    tid = f"task-{when[:10].replace('-', '')}-{when[11:19].replace(':', '')}-{type}"
    lines = ["---", f"id: {tid}", f"type: {type}", "status: pending",
             f"created_by: {created_by}", f"created_at: {when}"]
    if inputs:
        lines.append("inputs:")
        lines.extend(f"  - {i}" for i in inputs)
    lines += ["---", "", outcome, "",
              "Results land as candidates for review; nothing writes to the "
              "base directly from this task.", "",
              "## Log", f"- {when} created ({created_by})", ""]
    d = Path(root) / _QUEUE
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{tid}.md"
    stem, n = target.stem, 2
    while target.exists():
        target = d / f"{stem}-{n}.md"
        n += 1
    target.write_text("\n".join(lines), encoding="utf-8")
    return {"action": "created", "id": target.stem, "path": str(target),
            "type": type, "status": "pending"}


@_locked
def queue_restatus(root, id, status, *, note=None, actor=None, when=None):
    """Move a task through its lifecycle: rewrite the status line, append one
    log line. Never a delete — tasks are re-statused, never deleted (the
    append-only worklog discipline). Illegal transitions are refused: terminal
    states (done/declined/cancelled) stay terminal."""
    root = Path(root)
    when = when or _now()
    actor = actor or "core"
    path = root / _QUEUE / f"{id}.md"
    task = _parse_task(path) if path.is_file() else None
    if task is None:
        raise ValueError(f"no task {id!r} in the queue")
    old = task.get("status", "")
    if status == old:
        return {"action": "noop", "id": id, "status": status,
                "note": "already in that state"}
    allowed = TRANSITIONS.get(old)
    if allowed is None or status not in allowed:
        legal = ", ".join(sorted(allowed)) if allowed else "none (terminal)"
        # ASCII arrow: this message reaches cp1252 Windows consoles via the CLI
        raise ValueError(
            f"illegal transition {old!r} -> {status!r} for {id!r} "
            f"(legal from {old!r}: {legal})")
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^status: .*$", f"status: {status}", text, count=1)
    line = f"- {when} re-statused {old} → {status} ({actor})"
    if note:
        line += f" — {note}"
    text = text.rstrip("\n") + "\n" + line + "\n"
    path.write_text(text, encoding="utf-8")
    return {"action": "re-statused", "id": id, "from": old, "to": status,
            "path": str(path)}
