# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
# ^ PEP-723 (ADR-0031): launched via `uv run --script`; uv provisions Python + pyyaml
#   cross-platform. The bundled Core resolves via the sys.path insert in main().
"""Stop hook — the end-of-turn backstop over every base touched this session
(T-201 lint; T-212 uncommitted-git-changes; ADR-0045 §4).

`post_write_lint.py` lints immediately after the SETTLING ops; bulk-heavy ops
(capture, capture-repo, stage-candidate) only *record* their base so an ingest of N
sources costs one sweep, not N. This hook is where that debt comes due: when the
agent tries to finish, every recorded base is re-checked with the read-only Linter
engine. A dirty base blocks the stop ONCE — exit 2 hands the errors to the agent,
which can fix through the proper verbs or surface them to the user; the
`stop_hook_active` flag guarantees the block cannot loop. Clean bases clear the
session's state file and stay silent.

The same once-only block also carries the T-212 nudge: a **git-backed** base this
session wrote whose working tree holds uncommitted changes. Interactive plugin
sessions write the base but never auto-commit (by design — a commit+push is the
user's consented act, unlike the web plane's synced writes), so a forgetful
session-end is where clone divergence is BORN; this surfaces it at that moment
instead of at the next machine's merge. The check is local-only (`git status`,
never fetch/pull — the T-167 posture) and the hook NEVER commits: it hands the
agent the fact, the agent offers, the human decides.

Same posture as every hook in this layer: side-effect-free (never the
log-recording `lint` op, never a git write), gated, best-effort, silent on
infrastructure failure. Only lint errors and the once-only commit nudge are
ever loud.
"""
import json
import subprocess
import sys
from pathlib import Path

# Shared helpers live in the sibling PostToolUse hook; each hook is otherwise a
# standalone script (the house rule), but the state-file contract MUST be single-
# sourced — two hand-copied paths is how a backstop silently checks nothing.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def uncommitted_changes(root):
    """A short porcelain summary of uncommitted changes in a git-backed base,
    or None (not a git root / clean / git unavailable). LOCAL-ONLY read — never
    fetch, never pull, never write (T-167 posture). Scoped to bases that are
    themselves the repo root, so a base nested in a larger repo never triggers
    a nudge about someone else's working tree."""
    try:
        if not (root / ".git").exists():
            return None
        out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return None
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        return lines or None
    except Exception:
        return None                        # infra failure → silent, never a block


def render_nudge(root, lines):
    shown = "\n".join(f"  {ln}" for ln in lines[:8])
    more = f"\n  … and {len(lines) - 8} more" if len(lines) > 8 else ""
    return (
        f"odin: {root} — this session wrote this git-backed base and its "
        f"working tree holds uncommitted changes ({len(lines)} path(s)):\n"
        f"{shown}{more}\n"
        "Nothing is lost, but only a commit+push carries the work to the "
        "base's remote — uncommitted local changes are how clone divergence "
        "starts (T-167/T-212). OFFER the user a commit (and push, if a remote "
        "exists) before finishing, or surface it so leaving it is their "
        "deliberate choice. Never commit without their word. This reminder "
        "fires once per session.")


def main():
    try:
        import post_write_lint as shared
        payload = json.load(sys.stdin)
        if payload.get("stop_hook_active"):
            return 0                       # this stop was already hook-driven → never loop
        session = payload.get("session_id")
        if not session:
            return 0
        f = shared.state_file(session)
        if not f.exists():
            return 0                       # nothing mutated this session → silent
        roots = [r for r in f.read_text(encoding="utf-8").splitlines() if r.strip()]
        tools = shared._bundled_tools_dir()
        if tools is None:
            return 0
        sys.path.insert(0, str(tools))
        blocks = []
        for r in roots:
            root = Path(r)
            if not (root / "muninn.yml").exists():
                continue                   # base gone/moved → not this hook's problem
            try:
                errors = shared.lint_errors(root)
            except Exception:
                continue                   # a broken base must not wedge the stop
            if errors:
                blocks.append(shared.render_errors(root, errors, "this session's writes"))
            dirty = uncommitted_changes(root)
            if dirty:
                blocks.append(render_nudge(root, dirty))
        if not blocks:
            f.unlink(missing_ok=True)      # settled clean → the debt is paid
            return 0
    except Exception:
        return 0        # best-effort: infrastructure failure must never block the stop
    print("\n\n".join(blocks), file=sys.stderr)
    return 2



if __name__ == "__main__":
    sys.exit(main())
