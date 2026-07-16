# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
# ^ PEP-723 (ADR-0031): launched via `uv run --script`; uv provisions Python + pyyaml
#   (the Core's one dependency) cross-platform, no host `python3` needed. The bundled
#   Core resolves via the sys.path insert in main().
"""SessionStart hook — the deterministic on-load freshness check (T-020; ADR-0005/0034).

MUNINN.md instructs every Odin to open a base with ONE read — `status` — and render
its signals as one consolidated nudge. That instruction is *elicited*: it works only
if the model follows it. This hook makes the same check *deterministic* on Claude
Code: at session start it walks up from cwd to the nearest `muninn.yml`, runs the
read-only Core `status` op (as-of today), and injects the result into session context
— the on-load signal arrives whether or not the model remembers to look.

Layering (the doctrine): the MUNINN.md instruction stays the portable floor — it
travels with the base and works on every surface (Desktop chat and Cowork run no
plugin hooks at all; on older Claude Code `${CLAUDE_PLUGIN_ROOT}` doesn't expand in
SessionStart hooks and this file silently never runs). This hook is a Claude
Code-only *upgrade over* that floor, the same shape as semantic `search` over `find`:
defense in depth, never a replacement. The injected context IS the status read — it
tells the agent not to repeat it.

Same safety posture as `warm_index.py` (T-092):

  1. **Gated.** No `muninn.yml` at/above cwd → print nothing, exit 0. A non-ODIN
     session is untouched. (Walk-up, not exact-folder: a session opened in a
     subfolder of a Muninn is still working in that Muninn.)
  2. **Best-effort + quiet.** ANY failure — missing bundled Core, a broken base,
     anything — is swallowed: exit 0, no output, session start unaffected.
  3. **Read-only.** `status` is a pure function of (bytes, as_of); nothing is
     written. Unlike the warm this hook is synchronous — the point is to have the
     answer in context before the first turn — and `status` is one lint pass, so
     hooks.json bounds it with an explicit timeout as the backstop.

Time note: the Core keeps wall-clock out (`as_of` is injected — ADR-0034); the
adapter layer owns "today", so THIS file reads the calendar and passes it down.
"""
import datetime
import json
import os
import sys
from pathlib import Path


def find_muninn(start):
    """The nearest `muninn.yml` at or above `start`, else None (same gate as the
    warm hook — kept local so each hook stays a standalone script)."""
    d = Path(start).resolve()
    for cand in (d, *d.parents):
        if (cand / "muninn.yml").exists():
            return cand
    return None


def _bundled_tools_dir():
    """The Core next to this hook: `<plugin-root>/tools` in the shipped bundle,
    `<repo-root>/tools` when running from the source tree."""
    here = Path(__file__).resolve()
    for depth in (1, 3):  # bundle: plugin-root/hooks/; repo: adapters/claude-plugin/hooks/
        try:
            cand = here.parents[depth] / "tools"
        except IndexError:
            continue
        if (cand / "muninn_core.py").exists():
            return cand
    return None


def render(root, st):
    """Pure (testable): compose the injected context from a `status` result. Mirrors
    the MUNINN.md on-load section — every signal maps to an OFFER, never an action."""
    signals = []
    if st["freshness"] != "fresh":
        signals.append("freshness=%s → suggest `lint`" % st["freshness"])
    if st["captures_since_lint"]:
        signals.append("%d capture(s) since last lint → may offer (once) to synthesize"
                       % st["captures_since_lint"])
    if st["pending_candidates"]:
        signals.append("%d pending candidate(s) → may offer (once) review-candidates"
                       % st["pending_candidates"])
    if st["stale"]:
        signals.append("stale (a cited source advanced): %s → offer regenerate"
                       % ", ".join(st["stale"]))
    if st["aged"]:
        signals.append("aged as-of facts (may have drifted with the calendar): %s"
                       % ", ".join("%s (%dd old)" % (a["id"], a["days_old"])
                                   for a in st["aged"]))
    if st.get("unmapped_connector_systems"):
        signals.append("sources came from systems the landscape doesn't describe: "
                       "%s → may offer (once) to orient the base / record the "
                       "landscape (T-146)"
                       % ", ".join(st["unmapped_connector_systems"]))
    head = ("Odin on-load status for the Muninn at %s, computed as-of %s by the "
            "plugin's deterministic SessionStart hook. This IS the MUNINN.md on-load "
            "`status` read — do not run it again." % (root, st["as_of"]))
    if not signals:
        return head + " All clear: fresh, nothing pending. No nudge needed; stay quiet."
    return (head + " Signals: " + " · ".join(signals) + ". Per MUNINN.md, surface "
            "these as ONE consolidated nudge the user can take or defer — offers "
            "only, never run synthesize/review/regenerate unasked.")


def main(argv=None):
    try:
        root = find_muninn(os.getcwd())
        if root is None:
            return 0                                    # not an ODIN session → silent
        tools = _bundled_tools_dir()
        if tools is None:
            return 0
        sys.path.insert(0, str(tools))
        import muninn_core
        st = muninn_core.status(str(root), as_of=datetime.date.today().isoformat())
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": render(root, st)}}))
    except Exception:
        pass                # best-effort: a broken base must never fail session start
    return 0


if __name__ == "__main__":
    sys.exit(main())
