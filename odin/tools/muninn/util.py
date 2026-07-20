"""Shared plumbing: versions, id validation (T-114), yaml + log I/O (T-115), the advisory write lock, THE frontmatter parser (T-117).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import contextlib
import functools
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402


FORMAT_VERSION = "1.2"  # 1.0 frozen (ADR-0037); 1.1 anchors (ADR-0039); 1.2 supersession (ADR-0041)


# The TOOL's version, distinct from the format's (T-118c): single-sourced from
# pyproject [project] version — tests/test_id_validation.py pins the two equal.
TOOL_VERSION = "1.17.0"


# Ids become filesystem paths (sources/<id>/, <id>.md) and arrive as
# model-generated arguments over MCP — so they are validated at every write
# boundary (T-114): lowercase slug, no path separators, no traversal, and no
# Windows-reserved device names (CON/NUL/… are reserved even with a suffix).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


_WINDOWS_RESERVED = ({"con", "prn", "aux", "nul"}
                     | {f"com{i}" for i in range(1, 10)}
                     | {f"lpt{i}" for i in range(1, 10)})


def _valid_id(id, *, what="id"):
    """Reject any id that is not a safe, cross-platform slug (T-114).

    Returns the id unchanged so call sites can validate inline. ValueError on
    anything else — before any write, matching _capture's atomicity contract.
    """
    if not isinstance(id, str) or not _ID_RE.match(id):
        raise ValueError(
            f"invalid {what} {id!r}: an id must be a slug matching "
            f"[a-z0-9][a-z0-9._-]* (max 128 chars — lowercase, no spaces, no "
            f"path separators)")
    if ".." in id or id.endswith("."):
        raise ValueError(f"invalid {what} {id!r}: '..' and a trailing '.' are not allowed")
    if id.split(".", 1)[0] in _WINDOWS_RESERVED:
        raise ValueError(f"invalid {what} {id!r}: a Windows-reserved device name")
    return id


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _dump_yaml(data: dict) -> str:
    # allow_unicode keeps §/— legible in frontmatter (T-018); sort_keys=False
    # preserves the field order the spec presents.
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _append_log(root: Path, when: str, line: str) -> None:
    # True O(1) append (T-115): the old read-whole-file → rewrite-whole-file left
    # the ENTIRE history exposed to a crash mid-write — the one file whose whole
    # point is append-only (cf. the WSL2 zero-byte incident). Append mode can at
    # worst truncate the final line. Every write here ends with \n, so the header
    # check on an empty/new file is the only shape logic needed.
    logp = root / "log.md"
    with open(logp, "a", encoding="utf-8") as f:
        if f.tell() == 0:
            f.write("# Log\n")
        f.write(f"## [{when}] {line}\n")


# --------------------------------------------------------------------------- #
# Advisory inter-process write lock (T-115). The MCP server is a long-lived
# process and a concurrent CLI (or a second session) could interleave a
# multi-file sequence like capture-versioning. One OS-level advisory lock per
# Muninn (`.odin/write.lock` — the disposable tier, never fingerprinted) held
# for the duration of each write op closes that. flock/msvcrt locks release
# automatically when the process dies, so there is no stale-lock recovery to
# get wrong. Re-entrant per root+thread (promote → derive nests); read ops
# deliberately take no lock — the format is crash-consistent to read.
# --------------------------------------------------------------------------- #
_lock_state = threading.local()


@contextlib.contextmanager
def _write_lock(root: Path):
    key = os.path.realpath(root)
    held = getattr(_lock_state, "held", None)
    if held is None:
        held = _lock_state.held = {}
    if held.get(key):                        # re-entrant: already ours
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return
    lock_dir = Path(root) / ".odin"
    lock_dir.mkdir(exist_ok=True)            # root itself must already exist
    f = open(lock_dir / "write.lock", "a+")
    try:
        if os.name == "nt":                  # pragma: no cover (POSIX CI)
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        held[key] = 1
        try:
            yield
        finally:
            held[key] = 0
    finally:
        try:
            if os.name == "nt":              # pragma: no cover (POSIX CI)
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()


def _locked(fn):
    """Run a write op under the Muninn's advisory write lock (first arg = root)."""
    @functools.wraps(fn)
    def wrapper(root, *args, **kwargs):
        with _write_lock(Path(root)):
            return fn(root, *args, **kwargs)
    return wrapper


def _read_doc(p: Path):
    """(frontmatter, body) of a Markdown doc — via THE one frontmatter parser
    (`muninn_lint.split_frontmatter`, T-117). Three conventions used to coexist
    (this helper's own terminator scan, and raw `.split("---\\n", 2)[2]` body
    extraction that mis-split any doc whose YAML block carried a `---` line,
    e.g. inside a block scalar). One parser, shared with the linter and the
    hashing rule, means writer and every reader agree by construction."""
    fm, body = muninn_lint.split_frontmatter(p.read_text(encoding="utf-8"))
    return (fm or {}), body


def _load_yaml_frontmatter(p: Path) -> dict:
    """Parse just the leading `--- … ---` YAML block of a Markdown doc."""
    return _read_doc(p)[0]
