"""Deterministic projections and retrieval: index, fingerprint, find (the AI-free floor, ADR-0014), project pages (ADR-0017/0018), scope resolution, connectors (T-070).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from muninn_lint import (  # noqa: E402  (shared model + hashing)
    Linter,
    current_canonical,
    source_text,
)
from . import snapshot, util  # noqa: E402  (module-attr access = the patch point)
from .util import _append_log, _dump_yaml, _locked, _valid_id  # noqa: E402


# --------------------------------------------------------------------------- #
# place / regenerate_index — the deterministic projection (SPEC §5.3)
# --------------------------------------------------------------------------- #
_DERIVED_GROUPS = [("Summaries", "summary"), ("Entities", "entity"),
                   ("Concepts", "concept"), ("Questions", "question"),
                   ("Insights", "insight")]


def _cover_map(derived):
    """source id -> the derived doc that covers it (a `summary` preferred), for
    the source→summary blurb join shared by the index and project pages."""
    cover = {}
    for d in sorted(derived, key=lambda x: (x.type != "summary", x.id)):
        for s in d.data.get("sources") or []:
            sid = s.get("id") if isinstance(s, dict) else s
            cover.setdefault(sid, d)
    return cover


def _blurb(title, abstract):
    return f"{title} — {abstract}" if abstract else title


def _index_markers(d, current_by_source):
    """The compact coded metadata layer for a derived doc's index line — the
    card-catalogue 'call number' (T-056, ADR-0011/0014): the human title+abstract
    stays skimmable, and this legible marker set serves the AI librarian. A pure
    deterministic projection — assurance rung + corroboration breadth from
    frontmatter, staleness via the *same* recorded-vs-current source-hash check the
    linter uses for L4, `global` from scope. No authored prose.

    Order: `<rung> · <N source(s)> · [stale]`. Rung and count are always present
    (a uniform field an AI can rely on); `stale` appears only when true (surface the
    exception, stay quiet otherwise — the freshness posture). (`scope: global` lives
    on project pages, not derived docs, so it is marked in the Projects group.)"""
    parts = [d.data.get("derivation") or "extracted"]          # assurance rung
    srcs = d.data.get("sources") or []
    if srcs:
        parts.append(f"{len(srcs)} source" + ("s" if len(srcs) != 1 else ""))
    if d.data.get("status") == "superseded":
        # A closed record (ADR-0041): the ending is the one marker that matters —
        # staleness no longer applies (its provenance names the versions it read).
        parts.append("superseded")
        return " · ".join(parts)
    stale = d.data.get("status") == "stale"
    for s in srcs:
        recorded = s.get("hash") if isinstance(s, dict) else None
        current = current_by_source.get(s.get("id") if isinstance(s, dict) else s)
        if recorded and current and recorded != current:
            stale = True
            break
    if stale:
        parts.append("stale")
    return " · ".join(parts)


@_locked
def regenerate_index(root):
    """Rebuild index.md as a pure projection of document frontmatter (SPEC §5.3).

    Sources first — each borrowing its description from the derived doc that
    covers it (a source→summary join), or its origin locator if none covers it
    yet. Then derived docs by category, each rendering `title` (+ `abstract`).
    No free text is authored; the index is *computed*, and every registered doc
    id appears (so L8 holds). Deterministic and idempotent.
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    sources = sorted((d for d in linter.docs if d.kind == "source"), key=lambda x: x.id)
    derived = [d for d in linter.docs if d.kind == "derived"]
    projects = sorted((d for d in linter.docs if d.kind == "project"), key=lambda x: x.id)
    decisions = sorted((d for d in linter.docs if d.kind == "decision"), key=lambda x: x.id)

    # source id -> the derived doc that covers it (prefer a summary), for its blurb
    cover = _cover_map(derived)
    # source id -> its current content_hash, so the derived-doc markers can flag
    # staleness (recorded vs current) exactly as the linter's L4 does.
    current_by_source = {d.id: d.data.get("content_hash") for d in sources}

    def rel(p):
        return p.relative_to(root).as_posix()

    lines = ["# Index", ""]
    if sources:
        lines.append("## Sources")
        for d in sources:
            cov = cover.get(d.id)
            origin = d.data.get("origin") or {}
            if cov is not None:
                desc = cov.data.get("title", cov.id)
                # Surface the source's origin locator (a URL, repo, connector ref) next to its
                # summary title, so a human skimming the index sees the LINEAGE without opening
                # the source's meta.yml. Most valuable for web/reference sources.
                ref = origin.get("ref")
                if ref:
                    desc = f"{desc} — {ref}"
            else:
                desc = f"(source; {origin.get('ref') or origin.get('system') or 'not yet summarized'})"
            # Link to the actual canonical file (source.pdf, …), not a hardcoded
            # source.md that binary sources don't have (ADR-0010).
            canonical = current_canonical(d.path, d.data)
            target = f"sources/{d.id}/{canonical.name}" if canonical else f"sources/{d.id}/"
            # tier marker — a reference-tier source is authority-not-storage (can't be
            # re-verified byte-for-byte); flag it, leave full-capture (the default) bare.
            tier = " · reference" if d.data.get("capture") == "reference" else ""
            lines.append(f"- [{d.id}]({target}) — {desc}{tier}")
        lines.append("")
    for label, typ in _DERIVED_GROUPS:
        items = sorted((d for d in derived if d.type == typ), key=lambda x: x.id)
        if not items:
            continue
        lines.append(f"## {label}")
        for d in items:
            blurb = _blurb(d.data.get('title', d.id), d.data.get('abstract'))
            markers = _index_markers(d, current_by_source)
            suffix = f"  · {markers}" if markers else ""
            lines.append(f"- [{d.id}]({rel(d.path)}) — {blurb}{suffix}")
        lines.append("")
    for label, group in (("Projects", projects), ("Decisions", decisions)):
        if not group:
            continue
        lines.append(f"## {label}")
        for d in group:
            # mark the always-in-scope global hub (project pages only carry scope)
            scope_mark = "  · global" if d.data.get("scope") == "global" else ""
            lines.append(f"- [{d.id}]({rel(d.path)}) — {d.data.get('title', d.id)}{scope_mark}")
        lines.append("")

    index = root / "index.md"
    index.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    _write_llms_txt(root, linter)
    return index


def _write_llms_txt(root, linter):
    """Emit `llms.txt` beside the index (T-168): the emerging convention a
    generic AI agent fetches to orient in an unfamiliar repo. Pure projection
    (manifest name + fixed routing text, no prose authored) — the base's
    self-description made literal for readers that never heard of ODIN. A
    projection artifact like index.md: not load-bearing, not part of format
    conformance; a reader that ignores it loses nothing.
    """
    manifest = next((d for d in linter.docs if d.kind == "manifest"), None)
    name = (manifest.data.get("name") if manifest else None) or "knowledge base"
    (root / "llms.txt").write_text(
        f"# {name}\n\n"
        "> A Muninn: a durable, self-describing knowledge base of captured\n"
        "> sources and grounded derived documents. Plain Markdown, links, and\n"
        "> content-hash provenance; readable and verifiable with no AI and no\n"
        "> vendor.\n\n"
        "- [MUNINN.md](MUNINN.md): what this base is and the rules for reading it\n"
        "- [index.md](index.md): the catalog; every document, titled, sources first\n"
        "- sources/ holds immutable, authoritative captures; derived documents\n"
        "  (summaries/, insights/, ...) cite them by id and content hash; when a\n"
        "  summary and its source disagree, the source wins\n",
        encoding="utf-8")


# --------------------------------------------------------------------------- #
# read — the read-back primitive (T-159): "anyone reads, the Core writes"
# assumed a filesystem; a host that has only the op surface (the web chat
# adapter, any MCP-only client) could capture but never read content back —
# so it could not ground a summary, quote a source (T-153), or re-read for
# review/challenge. Returning stored text verbatim is a faithful transform.
# --------------------------------------------------------------------------- #
def read_doc(root, id, offset=0, limit=20000):
    """Return a doc's stored text, paged: for a **source**, its readable text
    (the extracted aid, else a text-native canonical — `muninn_lint.source_text`,
    the same text `find`/`index`/derivation read); for a derived doc, project
    page, or decision, the file's content verbatim. A bytes-only source (no text
    layer) returns empty content with `text_form: "none"` — the honest signal
    that grounding needs a model-read of the original bytes, never a guess.

    `offset`/`limit` are character paging (hosts have context/result caps);
    `truncated` says whether more remains past this page. Read-only.

    Returns {id, kind, type, text_form, chars, offset, content, truncated}.
    """
    root = Path(root)
    offset = max(0, int(offset))
    limit = int(limit)
    if limit <= 0:
        raise ValueError("limit must be positive")
    linter = snapshot.load_snapshot(root)
    d = next((x for x in linter.docs if x.id == id and x.kind != "manifest"), None)
    if d is None:
        raise ValueError(f"no doc with id {id!r} in this base")
    if d.kind == "source":
        text = source_text(d.path, d.data)
        text_form = ("none" if not text
                     else "aid" if (d.path / "source-text.md").exists()
                     else "canonical")
    else:
        text = d.path.read_text(encoding="utf-8", errors="replace")
        text_form = "file"
    page = text[offset:offset + limit]
    return {"id": d.id, "kind": d.kind, "type": d.type, "text_form": text_form,
            "chars": len(text), "offset": offset, "content": page,
            "truncated": offset + len(page) < len(text)}


# --------------------------------------------------------------------------- #
# fingerprint — the freshness hash as a Core op (ADR-0005, SPEC §4.4)
# --------------------------------------------------------------------------- #
def fingerprint(root):
    """Return the content fingerprint over all registered docs (excludes
    index.md / log.md by construction). Same value the linter computes."""
    linter = Linter(Path(root))
    linter.load()
    return linter.content_fingerprint()


# --------------------------------------------------------------------------- #
# find — deterministic retrieval (the substrate `find` presents and `ask` uses)
# --------------------------------------------------------------------------- #
def find(root, query, type=None, include_superseded=False):
    """Return docs whose id/title/abstract/tags/body contain ALL whitespace-
    separated query terms (case-insensitive). Sources also match their **origin
    locators** (`origin.ref`, `origin.upstream_ref`) — "what did I capture from
    <filename/URL>?" is a retrieval handle (T-141), the same identity handle
    capture's lineage rung and dedup-check already match on (T-045). Sources
    first, then derived, then projects/decisions, each by id.
    Returns [{id, kind, type, title, path}].

    `type` (optional) restricts results to docs of that frontmatter type — e.g.
    `type="decision"` is the retrieval half of the `why` verb (SPEC §5.5). An empty
    query with a type lists every doc of that type.

    **Superseded docs are skipped by default** (ADR-0041): retrieval serves
    current knowledge; a closed record surfacing in a grounding pass invites
    citing it. `include_superseded=True` brings the history back.
    """
    root = Path(root)
    terms = [t for t in query.lower().split() if t]
    linter = snapshot.load_snapshot(root)   # read-only; reused until the base changes (T-116)
    order = {"source": 0, "derived": 1, "project": 2, "decision": 3}
    results = []
    for d in linter.docs:
        if d.kind == "manifest":
            continue
        if type is not None and d.type != type:
            continue
        if not include_superseded and d.data.get("status") == "superseded":
            continue
        parts = [d.id]
        for k in ("title", "abstract"):
            if d.data.get(k):
                parts.append(str(d.data[k]))
        parts += [str(t) for t in (d.data.get("tags") or [])]
        if d.kind == "source":
            # Origin locators are retrieval handles, not just provenance (T-141):
            # a query shaped like the captured filename/URL must hit even when
            # the summary's vocabulary never repeats it.
            origin = d.data.get("origin") or {}
            parts += [str(origin[k]) for k in ("ref", "upstream_ref")
                      if origin.get(k)]
        try:
            # A source's searchable text is its aid/canonical text (ADR-0010) —
            # NOT a hardcoded source.md, which binary sources don't have.
            parts.append(source_text(d.path, d.data)
                         if d.kind == "source" else d.path.read_text(encoding="utf-8"))
        except OSError:
            pass
        hay = "\n".join(parts).lower()
        if all(t in hay for t in terms):
            results.append({"id": d.id, "kind": d.kind, "type": d.type,
                            "title": d.data.get("title", d.id), "path": str(d.path)})
    results.sort(key=lambda r: (order.get(r["kind"], 9), r["id"]))
    return results


# --------------------------------------------------------------------------- #
# write_project — create/update a project page (a curated VIEW; ADR-0002/0017)
# --------------------------------------------------------------------------- #
def _render_project_body(root, members, description=None, this_id=None, scope="project"):
    """Project each member's own title/abstract onto the page — the deterministic
    skim surface (ADR-0017). A source borrows its covering summary's title (the
    source→summary join the index uses); a derived doc renders its own
    title/abstract. Links are relative to the `projects/` dir. No prose is
    authored — the body is *computed* from member frontmatter, like the index.

    A non-global page also carries a computed **Always in scope** pointer to every
    `scope: global` view (SPEC §5.6): the global layer is unioned into every
    scope at query time (`resolve_scope`), so the human skimming this page must
    see it applies here too. It is a *reference*, not the members — single source
    of truth stays the global page; the pointer only changes when the *set* of
    global views does (not when their members do).
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    by_id = {d.id: d for d in linter.docs}
    cover = _cover_map([d for d in linter.docs if d.kind == "derived"])
    global_views = sorted(
        (d for d in linter.docs
         if d.kind == "project" and d.data.get("scope") == "global" and d.id != this_id),
        key=lambda d: d.id)

    def target_and_blurb(mid):
        d = by_id.get(mid)
        if d is None:
            return f"../{mid}", None  # dangling link — L11 flags it
        if d.kind == "source":
            cov = cover.get(mid)
            canonical = current_canonical(d.path, d.data)
            tgt = f"../sources/{mid}/{canonical.name}" if canonical else f"../sources/{mid}/"
            if cov is None:
                return tgt, "(not yet summarized)"
            return tgt, _blurb(cov.data.get("title", cov.id), cov.data.get("abstract"))
        tgt = "../" + d.path.relative_to(root).as_posix()
        return tgt, _blurb(d.data.get("title", mid), d.data.get("abstract"))

    lines = []
    if description:
        lines += [description.rstrip(), ""]
    lines.append("## Members")
    if not members:
        lines.append("_No members yet._")
    for mid in members:
        tgt, blurb = target_and_blurb(mid)
        lines.append(f"- [{mid}]({tgt})" + (f" — {blurb}" if blurb else ""))

    if scope != "global" and global_views:
        lines += ["", "## Always in scope",
                  "_Global views apply to every project (SPEC §5.6); unioned into "
                  "this scope automatically._"]
        for gv in global_views:
            title = gv.data.get("title", gv.id)
            lines.append(f"- [{gv.id}]({gv.id}.md) — {title}")
    return "\n".join(lines).rstrip("\n") + "\n"


@_locked
def write_project(root, id, *, title=None, add_members=None, remove_members=None,
                  scope=None, description=None, maintained_by=None, tags=None,
                  when=None):
    """Create or update a project page — a curated VIEW (ADR-0002, ADR-0017).

    Members are *links, not provenance*: this cannot reuse `write_derived` (that
    path demands ≥1 source + hashes). `add_members` are unioned into any existing
    members (order-stable); `remove_members` are then subtracted (T-148 — the
    inverse of the union; SPEC §5.6 "reorganizable at will"): links only, the
    member doc itself is untouched and stays findable, and removing an absent id
    is a no-op. `title`/`scope`/`description`/`maintained_by`/`tags` update in
    place, falling back to the existing page's values. The body is a
    deterministic projection of each member's own title/abstract (the skim
    surface) — no authored prose. Atomic single-file write, idempotent.

    Returns {"id", "type", "path", "members", "removed", "scope"}.
    """
    root = Path(root)
    when = when or util._now()
    _valid_id(id, what="project id")
    ppath = root / "projects" / f"{id}.md"

    existing = {}
    if ppath.exists():
        fm, _ = muninn_lint.split_frontmatter(ppath.read_text(encoding="utf-8"))
        existing = fm or {}

    title = title or existing.get("title")
    if not title:
        raise ValueError("a project needs a title")

    members = list(existing.get("members") or [])
    for m in (add_members or []):
        if m not in members:
            members.append(m)
    removed = []
    if remove_members:
        drop = set(remove_members)
        removed = [m for m in members if m in drop]
        members = [m for m in members if m not in drop]

    scope = scope or existing.get("scope") or "project"
    if scope not in muninn_lint.SCOPE_VALUES:
        raise ValueError(f"scope {scope!r} not one of "
                         f"{' | '.join(sorted(muninn_lint.SCOPE_VALUES))} (L16)")

    description = description if description is not None else existing.get("description")
    maintained_by = maintained_by if maintained_by is not None else existing.get("maintained_by")
    tags = tags if tags is not None else existing.get("tags")

    fm = {"id": id, "type": "project", "title": title}
    if description:
        fm["description"] = description
    fm["members"] = members
    if scope != "project":            # 'project' is the default (SPEC §5.6) — keep clean pages clean
        fm["scope"] = scope
    if maintained_by:
        fm["maintained_by"] = maintained_by
    if tags:
        fm["tags"] = tags

    body = _render_project_body(root, members, description, this_id=id, scope=scope)
    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + body

    ppath.parent.mkdir(exist_ok=True)
    tmp = ppath.parent / f".{id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(ppath)  # atomic replace into place
    line = f"project | {id} <- {', '.join(members) or '(empty)'}"
    if removed:
        line += f" (removed: {', '.join(removed)})"
    _append_log(root, when, line)
    return {"id": id, "type": "project", "path": str(ppath),
            "members": members, "removed": removed, "scope": scope}


@_locked
def reproject(root, when=None):
    """Re-render every project page from current state — the ADR-0018 follow-ons (T-057).

    A regenerate-class maintenance pass (like `stamp`), CLI/operational, idempotent:

    - **Migrate a pre-hub base:** if no `scope: global` view exists (a Muninn created
      before ADR-0018), seed the canonical `global` hub — exactly what `init` seeds now
      — so the always-in-scope layer is present. `resolve_scope` was always correct
      without it; this makes the *page* layer consistent too.
    - **Reproject on global-set change:** each non-global page's **Always in scope**
      pointer is a *write-time* projection (SPEC §5.6), so a hand-authored *second*
      `scope: global` view leaves older pages stale until re-rendered. Re-running
      `write_project` on every page recomputes the pointer (and refreshes each member's
      projected blurb — the sibling ADR-0017 'refresh blurbs when a member changes'
      case) from current frontmatter. No authored content is touched; the body is a
      pure projection.

    Returns {seeded_global, reprojected: [ids]}."""
    root = Path(root)
    when = when or util._now()
    linter = Linter(root)
    linter.load()
    projects = [d for d in linter.docs if d.kind == "project"]

    seeded = False
    if not any(d.data.get("scope") == "global" for d in projects):
        write_project(root, "global", title="Global context",
                      description="Standing context that applies to every project — "
                                  "always in scope.",
                      scope="global", when=when)
        seeded = True
        linter = Linter(root)
        linter.load()
        projects = [d for d in linter.docs if d.kind == "project"]

    reprojected = []
    for d in sorted(projects, key=lambda x: x.id):
        write_project(root, d.id, when=when)   # re-render in place; recomputes the pointer + blurbs
        reprojected.append(d.id)
    regenerate_index(root)
    return {"seeded_global": seeded, "reprojected": reprojected}


# --------------------------------------------------------------------------- #
# resolve_scope — a scope -> its working-set member ids (SPEC §5.6, ADR-0009 §2)
# --------------------------------------------------------------------------- #
def resolve_scope(root, project=None):
    """Resolve a scope to the set of member ids it covers — deterministic set
    math, no judgment (SPEC §5.6, ADR-0009 §2, ADR-0017). The read-side companion
    to `write_project`: `synthesize` calls this to learn its working set instead
    of re-deriving it per adapter.

    Every `scope: global` view is ALWAYS unioned in — the cross-cutting layer
    (org constraints, business model) the user never has to remember to include.

    - `project` given: working set = that project page's members ∪ every global
      view's members. An unknown project id raises ValueError (the user named a
      scope that isn't there — surface it, don't silently fall back to the base).
    - `project` None (whole base): working set = the whole base (every source +
      derived doc id); each global view is already a subset, so the union is
      implicit — `global_views` is still reported for transparency.

    Returns {"scope": project|None, "whole_base": bool,
             "global_views": [project ids, sorted],
             "members": [resolved member ids, sorted]}.
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    projects = [d for d in linter.docs if d.kind == "project"]

    global_views, global_members = [], []
    for d in projects:
        if d.data.get("scope") == "global":
            global_views.append(d.id)
            for m in (d.data.get("members") or []):
                if m not in global_members:
                    global_members.append(m)

    if project is None:
        members = sorted(d.id for d in linter.docs if d.kind in ("source", "derived"))
        return {"scope": None, "whole_base": True,
                "global_views": sorted(global_views), "members": members}

    named = next((d for d in projects if d.id == project), None)
    if named is None:
        raise ValueError(
            f"project {project!r} not found — no projects/{project}.md to scope to")
    resolved = set(named.data.get("members") or []) | set(global_members)
    return {"scope": project, "whole_base": False,
            "global_views": sorted(global_views), "members": sorted(resolved)}


#: origin systems that are LOCAL, not reachable connectors — skipped in the projection.
_LOCAL_ORIGINS = {"file", "chat"}


def connector_projection(root, project=None):
    """Project the distinct connectors the **resource-landscape layer** references
    (ADR-0021 §2, ADR-0028) — a deterministic, faithful view (no inference, no registry):
    the computed *skeleton* to the landscape docs' authored *flesh*. Over every
    `scope: global` view's members it unions two grounded inputs:

      (a) the `origin.{system, ref}` of **source** members — the connectors your durable
          knowledge came *from* (a repo mental model's source contributes `repo:<url>` for
          free); local origins (`file`, `chat`) are not connectors and are skipped.
      (b) an explicit `connectors: [{system, ref}]` field on **derived** members — for a
          connector a landscape doc *asserts* but hasn't ingested from ("contracts in Drive").

    With `project`, the roster is that project's members UNIONED with the global
    layer (T-128) — "the connectors your world touches" resolved the way queries
    are (`resolve_scope`: project ∪ always-in-scope global). Global-only stays
    the no-arg default; a project-scoped assertion never leaks into it.

    Returns `[{system, ref, referenced_by: [ids]}]`, sorted. Like `index.md`, it is a pure
    projection of frontmatter — it goes stale like any projection, never a durable registry."""
    from collections import defaultdict
    root = Path(root)
    linter = Linter(root)
    linter.load()
    by_id = {d.id: d for d in linter.docs}

    members: list[str] = []
    for d in linter.docs:
        if d.kind == "project" and d.data.get("scope") == "global":
            for m in (d.data.get("members") or []):
                if m not in members:
                    members.append(m)
    if project is not None:
        pdoc = by_id.get(project)
        if pdoc is None or pdoc.kind != "project":
            raise ValueError(f"no such project: {project}")
        for m in (pdoc.data.get("members") or []):
            if m not in members:
                members.append(m)

    conns: dict = defaultdict(set)
    for mid in members:
        d = by_id.get(mid)
        if d is None:
            continue
        if d.kind == "source":                                   # (a) origin-union
            origin = d.data.get("origin") or {}
            system = origin.get("system")
            if system and system not in _LOCAL_ORIGINS:
                conns[(system, origin.get("ref"))].add(mid)
        for c in (d.data.get("connectors") or []):               # (b) explicit assertions
            if isinstance(c, dict) and c.get("system"):
                conns[(c["system"], c.get("ref"))].add(mid)

    out = [{"system": s, "ref": r, "referenced_by": sorted(ids)}
           for (s, r), ids in conns.items()]
    out.sort(key=lambda c: (c["system"], c["ref"] or ""))
    return out


def _parse_older_than(spec):
    """'30d' / '2w' / '12h' / bare number (days) → timedelta (T-145)."""
    s = str(spec).strip().lower()
    unit = "d"
    if s and s[-1] in ("d", "w", "h"):
        unit, s = s[-1], s[:-1]
    try:
        n = float(s)
    except ValueError:
        raise ValueError(f"older_than {spec!r}: use <N>[d|w|h], e.g. 30d")
    return timedelta(hours=n * {"h": 1, "d": 24, "w": 168}[unit])


def _last_checked_map(root):
    """id → (timestamp, verdict) from the newest drift-check log entry naming the
    id (T-145). The aggregate counts can't carry per-item memory; the `checked:`
    segment can, and file order is chronological so later entries win."""
    logp = Path(root) / "log.md"
    out = {}
    if not logp.exists():
        return out
    for m in re.finditer(
            r"^## \[([^\]]+)\] drift-check \|[^\n]*?checked: ([^|\n]+)",
            logp.read_text(encoding="utf-8"), re.MULTILINE):
        when, pairs = m.group(1), m.group(2)
        for pair in pairs.split(","):
            pair = pair.strip()
            if "=" in pair:
                sid, verdict = pair.split("=", 1)
                out[sid.strip()] = (when, verdict.strip())
    return out


def drift_worklist(root, project=None, all=False, older_than=None):
    """The deterministic worklist for the consented **drift-check** sweep (T-136):
    the recoverable, connector-origin sources whose remote system may have moved.
    Hash staleness (L4) measures the base against itself; currency with the WORLD
    costs a deliberate reach, and this op names exactly what is worth reaching for.

    Scope (T-147): default is **every eligible source in the base** — view
    membership was never designed to scope drift, and a well-curated landscape
    global (ADR-0021/0028) holds no sweepable sources at all, so the old
    global-members default went empty precisely on well-formed bases. `project`
    NARROWS to that project's members ∪ the global views (T-128 semantics kept);
    `all` is accepted as a no-op for back-compat. Whatever the scope, the result
    **always discloses `outside_scope`** — eligible sources the requested scope
    excluded — so a thin or empty list can never silently read as "all current"
    (the T-142 discipline in a Core return value). Local origins (`file`, `chat`,
    `inbox`) never drift remotely and are excluded everywhere. `recoverable` must
    be True — False is the standing never-retry mark (flip it back with `retier
    --recoverable true`), and unset means the capture never claimed
    re-fetchability.

    Each item carries its per-item memory (T-145): `last_checked`/`last_verdict`
    joined from the drift log's `checked:` segments, and `last_contact` =
    max(captured_at, last_checked) — a re-capture IS contact with the world.
    Items sort **oldest contact first**. `older_than` ('30d', '2w', '12h')
    keeps only items whose last contact is older than the cutoff; what it drops
    is counted in `age_filtered`, never silently (no silent caps).

    Returns `{"items": [{id, origin_system, origin_ref, tier, version,
    captured_at, upstream_ref, upstream_identity, last_checked, last_verdict,
    last_contact}], "scope", "in_scope", "outside_scope", "age_filtered"}`.
    Read-only; the fetch/compare/re-capture that follow are the adapter's
    consented orchestration over `fetch` + `dedup-check` + `capture`.
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    by_id = {d.id: d for d in linter.docs}

    def _eligible(d):
        if d.kind != "source":
            return False
        origin = d.data.get("origin") or {}
        system = origin.get("system")
        if not system or system in _LOCAL_ORIGINS or system == "inbox":
            return False
        # Two gates admit a source to the sweep (T-140d): `recoverable: true`
        # (the SOURCE's own bytes re-fetch via origin.ref) OR an upstream anchor
        # (ADR-0039: a partial capture's sweep fetches the WHOLE via
        # upstream_ref — which the anchor itself proves fetchable; recoverable
        # was the wrong gate for this class and dropped anchored excerpts from
        # the first live sweep).
        return origin.get("recoverable") is True or bool(origin.get("upstream_ref"))

    eligible = [d for d in linter.docs if _eligible(d)]

    if project is None:
        candidates, scope_label = eligible, "all"
    else:
        pdoc = by_id.get(project)
        if pdoc is None or pdoc.kind != "project":
            raise ValueError(f"no such project: {project}")
        members: list[str] = []
        for d in linter.docs:
            if d.kind == "project" and d.data.get("scope") == "global":
                for m in (d.data.get("members") or []):
                    if m not in members:
                        members.append(m)
        for m in (pdoc.data.get("members") or []):
            if m not in members:
                members.append(m)
        member_set = set(members)
        candidates = [d for d in eligible if d.id in member_set]
        scope_label = f"project:{project}"
    outside_scope = len(eligible) - len(candidates)

    checked = _last_checked_map(root)
    out = []
    for d in candidates:
        origin = d.data.get("origin") or {}
        cur_entry = next((e for e in (d.data.get("history") or [])
                          if isinstance(e, dict)
                          and e.get("version") == d.data.get("version")), {})
        last_checked, last_verdict = checked.get(d.id, (None, None))
        captured_at = str(d.data.get("captured_at") or "")
        last_contact = max(filter(None, (captured_at, last_checked)), default="")
        out.append({
            "id": d.id,
            "origin_system": origin.get("system"),
            "origin_ref": origin.get("ref"),
            "tier": d.data.get("capture", "full"),
            "version": d.data.get("version", 1),
            "captured_at": captured_at,
            # ADR-0039 anchor columns: the whole an excerpt was read from + its
            # identity as of that read. Identity present → the sweep's tier-1
            # comparison is exact (git-blob even needs no content fetch); absent
            # → the source is checked the pre-anchor way, hedged honestly.
            "upstream_ref": origin.get("upstream_ref"),
            "upstream_identity": cur_entry.get("upstream_identity"),
            "last_checked": last_checked,
            "last_verdict": last_verdict,
            "last_contact": last_contact,
        })

    age_filtered = 0
    if older_than is not None:
        cutoff = (datetime.now(timezone.utc)
                  - _parse_older_than(older_than)).strftime("%Y-%m-%dT%H:%M:%SZ")
        kept = [w for w in out if w["last_contact"] < cutoff]
        age_filtered = len(out) - len(kept)
        out = kept

    out.sort(key=lambda w: (w["last_contact"], w["id"]))
    return {"items": out, "scope": scope_label, "in_scope": len(out),
            "outside_scope": outside_scope, "age_filtered": age_filtered}
