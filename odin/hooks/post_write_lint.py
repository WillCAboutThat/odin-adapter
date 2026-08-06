# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
# ^ PEP-723 (ADR-0031): launched via `uv run --script`; uv provisions Python + pyyaml
#   cross-platform. The bundled Core resolves via the sys.path insert in main().
"""PostToolUse hook — the deterministic convergence check after a base write (T-201; ADR-0045 §4).

MUNINN.md and SKILL.md *elicit* "the Muninn lints clean is the definition of done";
that discipline thins as work fans out across subagents (ADR-0045). This hook makes
the check deterministic on Claude Code: after any base-mutating `odin_*` op it
records which base was touched (for the Stop backstop, `stop_lint_check.py`), and
after a SETTLING op — one that creates or rewires derived docs — it runs the
read-only Linter engine on that base immediately. Lint errors exit 2, which feeds
stderr straight back to the driving agent while the op that caused them is still
in context; a clean base stays silent.

Consent posture: this calls `muninn_lint.Linter` (load/check — side-effect-free),
NEVER the `lint` op — `lint_report` records an ADR-0005 baseline entry in log.md
(T-124), and a hook must not write to the base uninvited (the ADR-0034 stance:
consent guards writes; reads may be quiet). Same safety contract as the session
hooks (T-020/T-092): gated to real Muninns, best-effort, silent on ANY
infrastructure failure — only lint errors are ever loud.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Base-mutating ops (verb names as the MCP server exposes them). Everything here
# gets its root RECORDED for the Stop backstop. `usage-log`/`reindex`/`refresh`
# write only the disposable .odin/ tier (never the base, never fingerprinted) and
# are deliberately absent. tests/test_hook_registry_coverage.py pins these sets
# against the Core registry so a new op cannot silently escape the net.
MUTATING = {
    "odin_init", "odin_capture", "odin_capture_repo", "odin_reextract", "odin_retier",
    "odin_anchor", "odin_drift_log", "odin_derive", "odin_stage_candidate",
    "odin_promote_candidate", "odin_decline_candidate", "odin_index",
    "odin_stamp", "odin_reproject", "odin_relink", "odin_challenge_log",
    "odin_map_log", "odin_review_log", "odin_supersede", "odin_project", "odin_record_decision",
}

# The SETTLING subset — ops that create or rewire derived docs / projections,
# where cross-doc invariants (provenance links, index completeness, staleness,
# self-hashes) can break. These lint IMMEDIATELY. Bulk-heavy ops (capture,
# capture-repo, stage-candidate) and append-only logs stay recorder-only so a
# bulk ingest is O(N), not O(N^2); the Stop backstop covers them once at the end.
SETTLING = {
    "odin_derive", "odin_promote_candidate", "odin_supersede", "odin_relink",
    "odin_record_decision", "odin_stamp", "odin_reproject", "odin_index",
    "odin_project", "odin_retier", "odin_anchor",
}

MAX_ERRORS_SHOWN = 10


def state_file(session_id):
    """Where this session's touched-base list lives (shared with the Stop hook;
    tempdir so residue is harmless and cleaned by the OS eventually)."""
    d = Path(tempfile.gettempdir()) / "odin-hooks"
    d.mkdir(exist_ok=True)
    return d / ("%s.roots" % session_id)


def record_root(session_id, root):
    """Append `root` to the session's touched list (idempotent)."""
    f = state_file(session_id)
    seen = set()
    if f.exists():
        seen = set(f.read_text(encoding="utf-8").splitlines())
    if str(root) not in seen:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(str(root) + "\n")


def _bundled_tools_dir():
    """The Core next to this hook: `<plugin-root>/tools` in the shipped bundle,
    `<repo-root>/tools` when running from the source tree."""
    here = Path(__file__).resolve()
    for depth in (1, 3):  # bundle: plugin-root/hooks/; repo: adapters/claude-plugin/hooks/
        try:
            cand = here.parents[depth] / "tools"
        except IndexError:
            continue
        if (cand / "muninn_lint.py").exists():
            return cand
    return None


def lint_errors(root):
    """Error-severity findings from the side-effect-free Linter engine (the same
    load/check pass `lint_report` runs, WITHOUT the log-recording op layer)."""
    import muninn_lint
    linter = muninn_lint.Linter(Path(root))
    with muninn_lint.prefetched(root):
        linter.load()
        linter.check()
    return [f for f in linter.findings if f.severity == "error"]


def render_errors(root, errors, verb):
    """The exit-2 stderr block: what broke, where, and the posture for fixing it."""
    lines = ["Muninn lint FAILED after %s on %s — %d error(s):"
             % (verb, root, len(errors))]
    for f in errors[:MAX_ERRORS_SHOWN]:
        lines.append("  [%s] %s  (%s)" % (f.rule, f.message, f.path))
    if len(errors) > MAX_ERRORS_SHOWN:
        lines.append("  … and %d more." % (len(errors) - MAX_ERRORS_SHOWN))
    lines.append("Fix through the proper verbs (regenerate/index/relink/supersede — "
                 "never hand-edit provenance), or surface the errors to the user. "
                 "The base must lint clean before this work is done.")
    return "\n".join(lines)


def verb_of(tool_name):
    """`mcp__<server>__odin_x` → `odin_x` (server names may contain underscores)."""
    return tool_name.rsplit("__", 1)[-1]


def main():
    try:
        payload = json.load(sys.stdin)
        verb = verb_of(payload.get("tool_name", ""))
        if verb not in MUTATING:
            return 0                                     # matcher belt-and-braces
        root = (payload.get("tool_input") or {}).get("root")
        if not root:
            return 0
        root = Path(payload.get("cwd") or os.getcwd(), root).resolve()
        if not (root / "muninn.yml").exists():
            return 0                                     # not a Muninn → silent
        if payload.get("session_id"):
            record_root(payload["session_id"], root)
        if verb not in SETTLING:
            return 0
        tools = _bundled_tools_dir()
        if tools is None:
            return 0
        sys.path.insert(0, str(tools))
        errors = lint_errors(root)
    except Exception:
        return 0        # best-effort: infrastructure failure must never block work
    if errors:
        print(render_errors(root, errors, verb), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
