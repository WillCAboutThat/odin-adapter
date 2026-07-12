"""init — scaffold a new Muninn (with the tool-root guard, ADR-0032).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from . import util  # noqa: E402  (module-attr access = the patch point)
from .projections import regenerate_index, write_project  # noqa: E402
from .util import FORMAT_VERSION, _append_log  # noqa: E402


# --------------------------------------------------------------------------- #
# init — scaffold a new Muninn (operational verb; deterministic, SPEC §3, §5.8)
# --------------------------------------------------------------------------- #
_LAYOUT = ("sources", "summaries", "entities", "concepts", "questions",
           "insights", "projects", "decisions", "candidates", "candidates/declined")


_TOOL_ROOT_SENTINEL = ".odin-tool-root"


def _tool_root_above(target) -> Path | None:
    """The nearest dir at/above `target` carrying the ODIN tool-root sentinel, else
    None. The deterministic half of the T-032 guard (ADR-0032): a Muninn must live
    separately from ODIN-the-tool (ADR-0002). The sentinel is committed to ODIN's dev
    repo root and is NOT copied into the shipped plugin bundle, so a real user running
    from their own folder never trips it; only a dev checkout does. `target` need not
    exist yet — we walk its resolved path's parents."""
    p = Path(target).resolve()
    for cand in (p, *p.parents):
        if (cand / _TOOL_ROOT_SENTINEL).exists():
            return cand
    return None


def init(root, name=None, when=None, allow_tool_root=False):
    """Scaffold a Muninn: manifest, MUNINN.md (from the template), the standard
    layout, index.md, log.md. No-op with a report if already a Muninn.

    **Soft-warn tool-repo guard (T-032/ADR-0032):** if the target sits inside ODIN's
    own checkout (sentinel found) and `allow_tool_root` is not set, return an
    `action: "warn"` result and write **nothing** — the adapter surfaces it and, on the
    user's consent, re-calls with `allow_tool_root=True`. Surface-don't-block
    (principle 5): the consented op still proceeds."""
    root = Path(root)
    when = when or util._now()
    manifest = root / "muninn.yml"
    if manifest.exists():
        return {"action": "noop", "path": str(root), "reason": "already a Muninn"}
    if not allow_tool_root:
        tr = _tool_root_above(root)
        if tr is not None:
            return {"action": "warn", "path": str(root), "tool_root": str(tr),
                    "warning": f"target is inside the ODIN tool checkout ({tr}/"
                               f"{_TOOL_ROOT_SENTINEL}); a Muninn should live separately "
                               f"(ADR-0002). Re-run elsewhere, or pass --allow-tool-root "
                               f"to scaffold here anyway."}
    root.mkdir(parents=True, exist_ok=True)
    for d in _LAYOUT:
        (root / d).mkdir(exist_ok=True)
    name = name or root.name
    # The integrity knob is written present-but-off, so it is discoverable in the file
    # (self-documenting) rather than an invisible absent key (ADR-0029). Off by default;
    # flip to true — or ask the adapter to — to enforce L19 (out-of-band derived-doc edits).
    manifest.write_text(
        f"muninn: {FORMAT_VERSION}\nname: {name}\ncreated_at: {when}\n"
        f"integrity:\n  derived_self_hash: false  # opt-in: enforce L19 (out-of-band edits)\n",
        encoding="utf-8")

    # MUNINN.md from the scaffold template: drop the leading comment, fill tokens.
    # templates/ lives beside the muninn_core facade (one level up from this
    # package, T-122) — and ships there in both the pip install and the bundle.
    tmpl = (Path(__file__).resolve().parent.parent / "templates" / "MUNINN.md").read_text(encoding="utf-8")
    if tmpl.startswith("<!--"):
        end = tmpl.find("-->")
        if end != -1:
            tmpl = tmpl[end + 3:].lstrip("\n")
    tmpl = (tmpl.replace("{{NAME}}", name)
                .replace("{{FORMAT_VERSION}}", FORMAT_VERSION)
                .replace("{{CREATED}}", when))
    (root / "MUNINN.md").write_text(tmpl, encoding="utf-8")

    (root / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    # The disposable-index tier is operational, never knowledge — keep it out of
    # git (ADR-0027). Written only if the Muninn has no .gitignore of its own.
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(".odin/\n", encoding="utf-8")
    _append_log(root, when, f"init | created Muninn '{name}' (format {FORMAT_VERSION})")

    # Seed the one canonical global view (ADR-0018): the always-in-scope home for
    # cross-cutting context, discoverable from the moment you init. An empty
    # placeholder — projected into the index so the fresh base is lint-clean out of
    # the box (L8 index-complete, L16 scope-enum).
    write_project(root, "global", title="Global context",
                  description="Standing context that applies to every project — "
                              "always in scope.",
                  scope="global", when=when)
    regenerate_index(root)
    return {"action": "created", "path": str(root), "name": name}
