"""Graph projection (T-208, ADR-0048) — the base's explicit relationships as
neutral, library-agnostic JSON: `odin.graph.v1`.

The contract deliberately names no renderer: the same projection can feed the
web viewer's canvas, a CLI export, Gephi, or any later tool — the renderer is
replaceable, the projection is the surface. Three rules keep it honest:

1. **Explicit relationships only.** Every edge is a frontmatter fact — a
   provenance rung, a `see_also` link, a project membership, a decision's
   evidence link, a supersession pointer, an upstream anchor. Nothing is
   inferred (no title-mention edges, no similarity edges): the graph must
   never blur ODIN's known-vs-inferred line (ADR-0015). Inferred/proposed
   relationships, when they arrive, ride the candidates rail and are marked
   `explicit: false` — none exist in v1.
2. **No derived→derived grounding edge can exist** (I3, no chaining): the
   only derived→derived relations are `see_also` and `superseded_by`.
3. **Read-only projection.** Consumes the shared loaded snapshot (T-116);
   writes nothing, not even to the disposable tier. `cache_key` is the
   snapshot's stat-sweep — a change detector for renderers to key layout
   caches on, NOT the lint fingerprint (which hashes content and costs a
   full read).

Node degree is computed over the FULL explicit edge set before any filter, so
a filtered view still reports each node's true connectedness.
"""
from pathlib import Path

from . import snapshot

#: relation → directed? (an undirected relation renders without an arrow)
RELATIONS = {
    "grounded_by": True,    # derived doc → the source it grounds in (I2)
    "see_also": False,      # doc ↔ doc (L7-resolved link)
    "member_of": True,      # doc → project view it belongs to (ADR-0002)
    "evidence": True,       # decision → source (links, not provenance; ADR-0019)
    "superseded_by": True,  # closed doc → its replacement (ADR-0041)
    "excerpt_of": True,     # partial capture → the captured whole (ADR-0039)
    "from_repo": True,      # repo evidence capture → the repo constitution (T-196)
}


def _title(d) -> str:
    if d.kind == "source":
        origin = d.data.get("origin") or {}
        return str(origin.get("ref") or d.id)
    return str(d.data.get("title") or d.id)


def _node(d) -> dict:
    n = {
        "id": d.id,
        "label": _title(d),
        "kind": d.kind,
        "type": d.type,
        "route": f"/source/{d.id}" if d.kind == "source" else f"/doc/{d.id}",
        "status": str(d.data.get("status") or "current"),
        "degree": 0,
    }
    if d.kind == "source":
        n["tier"] = d.data.get("capture") or "full"
    else:
        if d.data.get("derivation"):
            n["derivation"] = d.data["derivation"]
    return n


def _edges_of(docs, by_id) -> tuple[list[dict], list[dict]]:
    """Every explicit edge in the base, deduped by id, targets resolved —
    plus the UNRESOLVED explicit references (an edge whose target id does not
    exist), returned separately instead of silently dropped (ADR-0052:
    courtesy diagnostics for evidence auditing; the LINTER remains the sole
    authority on base integrity — no severity, no lint codes here)."""
    edges: dict[str, dict] = {}
    unresolved: dict[str, dict] = {}
    # origin.ref → source id, for the two locator-join relations (ADR-0039/T-196)
    by_ref: dict[str, str] = {}
    for d in docs:
        if d.kind == "source":
            ref = str((d.data.get("origin") or {}).get("ref") or "")
            if ref:
                by_ref.setdefault(ref, d.id)

    def add(relation, src_id, dst_id, **extra):
        if src_id == dst_id or not dst_id:
            return
        if src_id not in by_id or dst_id not in by_id:
            uid = f"{relation}:{src_id}:{dst_id}"
            unresolved.setdefault(uid, {"source": src_id, "relation": relation,
                                        "target": dst_id,
                                        "reason": "target-not-found"})
            return
        eid = f"{relation}:{src_id}:{dst_id}"
        if eid not in edges:
            edges[eid] = {"id": eid, "source": src_id, "target": dst_id,
                          "relation": relation, "explicit": True,
                          "directed": RELATIONS[relation], **extra}

    for d in docs:
        data = d.data
        if d.kind not in ("source", "manifest"):
            for s in data.get("sources") or []:
                sid = s.get("id") if isinstance(s, dict) else s
                pinned = s.get("hash", "") if isinstance(s, dict) else ""
                src = by_id.get(sid)
                current = (src.data.get("content_hash") if src else "") or ""
                add("grounded_by", d.id, sid,
                    stale=bool(pinned) and bool(current) and pinned != current)
        for sid in data.get("see_also") or []:
            add("see_also", d.id, str(sid))
        if d.kind == "project":
            for mid in data.get("members") or []:
                add("member_of", str(mid), d.id)
        if d.kind == "decision":
            for e in data.get("evidence") or []:
                add("evidence", d.id, e.get("id") if isinstance(e, dict) else str(e))
        if data.get("superseded_by"):
            add("superseded_by", d.id, str(data["superseded_by"]))
        if d.kind == "source":
            origin = data.get("origin") or {}
            uref = str(origin.get("upstream_ref") or "")
            if uref and uref in by_ref:
                add("excerpt_of", d.id, by_ref[uref])
            ref = str(origin.get("ref") or "")
            if origin.get("system") == "repo" and "#" in ref:
                whole = by_ref.get(ref.split("#", 1)[0])
                if whole:
                    add("from_repo", d.id, whole)
    return list(edges.values()), sorted(unresolved.values(),
                                        key=lambda u: (u["source"], u["relation"],
                                                       u["target"]))


def _adjacency(edges: list[dict], direction: str) -> dict[str, list[tuple]]:
    """Adjacency honoring ADR-0052's direction rule: direction follows the
    STORED edge (source field → target field); intrinsically undirected
    relations behave identically in every direction."""
    adj: dict[str, list[tuple]] = {}
    for e in edges:
        fwd = direction in ("both", "outbound") or not e["directed"]
        rev = direction in ("both", "inbound") or not e["directed"]
        if fwd:
            adj.setdefault(e["source"], []).append((e["target"], e["relation"]))
        if rev:
            adj.setdefault(e["target"], []).append((e["source"], e["relation"]))
    for k in adj:
        adj[k].sort()  # stable expansion order (ADR-0052 §4)
    return adj


def _bfs(seeds, edges, direction, depth, max_nodes):
    """Deterministic bounded BFS (ADR-0052): complete depth layers expanded in
    stable id order; a node cap interrupts a layer in that same order. Returns
    (traversal metadata by id, complete, limited_by, frontier). Frontier
    entries are ordinary doc ids the caller can re-seed — the continuation
    mechanism; there is no cursor."""
    adj = _adjacency(edges, direction)
    meta = {s: {"depth": 0, "reached_from": [], "reached_by": ["seed"]}
            for s in seeds}
    complete, limited_by = True, None
    frontier: list[dict] = []
    layer = sorted(seeds)
    for dist in range(1, max(0, depth) + 1):
        nxt: list[str] = []
        for node in layer:
            for nbr, rel in adj.get(node, ()):
                if nbr in meta:
                    m = meta[nbr]
                    if m["depth"] == dist:  # another path, same layer: record it
                        if node not in m["reached_from"]:
                            m["reached_from"].append(node)
                        if rel not in m["reached_by"]:
                            m["reached_by"].append(rel)
                    continue
                if max_nodes is not None and len(meta) >= max_nodes:
                    complete, limited_by = False, "max_nodes"
                    remaining = sum(1 for n2, _ in adj.get(node, ())
                                    if n2 not in meta)
                    if remaining and not any(f["id"] == node for f in frontier):
                        frontier.append({"id": node, "remaining_edges": remaining})
                    continue
                meta[nbr] = {"depth": dist, "reached_from": [node],
                             "reached_by": [rel]}
                nxt.append(nbr)
        if limited_by:
            # nodes discovered but never expanded are frontier too
            for node in nxt:
                remaining = sum(1 for n2, _ in adj.get(node, ()) if n2 not in meta)
                if remaining:
                    frontier.append({"id": node, "remaining_edges": remaining})
            break
        layer = sorted(nxt)
        if not layer:
            break
    frontier.sort(key=lambda f: f["id"])
    return meta, complete, limited_by, frontier


def project_graph(root, *, center=None, centers=None, depth=None, kinds=None,
                  relations=None, direction="both", max_nodes=None,
                  max_edges=None, project=None):
    """Project the base's explicit relationship graph (`odin.graph.v1`).

    center/centers — restrict to the neighborhood of one doc / the deduped
    union of several (ADR-0052: the caller always chooses the seeds; both
    params together is an error; unknown seeds raise; depth defaults to 1
    when seeds are given). Seeds survive kind filters.
    direction — both (default, today's undirected behavior) | outbound
    (stored source-field → target-field: a derived doc's grounded_by reaches
    its sources and STOPS) | inbound (the reverse). Intrinsically undirected
    relations behave identically in every direction.
    kinds/relations — node/edge filters, applied BEFORE the walk.
    max_nodes/max_edges — deterministic bounds beyond depth (a single hub
    can otherwise connect most of a base). A capped result reports
    `complete: false`, `limited_by`, and a re-seedable `unexpanded_frontier`
    — the continuation mechanism; there is no cursor.
    project — annotation, never suppression: nodes gain `in_scope` against
    the same resolver as scoped retrieval; an out-of-project grounding
    source is disclosed and labeled, never hidden.

    `complete` is scope-honest: complete for THESE seeds, relations,
    direction, depth, and caps — not complete evidence for a question, and
    not proof the base is valid (lint is the authority; `unresolved_edges`
    here is courtesy diagnostics only).
    """
    if center is not None and centers:
        raise ValueError("pass center OR centers, not both")
    if direction not in ("both", "outbound", "inbound"):
        raise ValueError(f"unknown direction {direction!r} "
                         "(both | outbound | inbound)")
    seeds = list(centers) if centers else ([center] if center is not None else [])

    root = Path(root)
    snap = snapshot.load_snapshot(root)
    docs = [d for d in snap.docs if d.kind != "manifest"]
    by_id = {d.id: d for d in docs}

    all_edges, unresolved = _edges_of(docs, by_id)
    degree: dict[str, int] = {}
    for e in all_edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    edges = all_edges
    if relations:
        wanted = set(relations)
        unknown = wanted - set(RELATIONS)
        if unknown:
            raise ValueError(f"unknown relation(s): {sorted(unknown)} "
                             f"(known: {sorted(RELATIONS)})")
        edges = [e for e in edges if e["relation"] in wanted]

    complete, limited_by, frontier = True, None, []
    traversal = None
    nodes = docs
    if seeds:
        missing = [s for s in seeds if s not in by_id]
        if missing:
            raise ValueError(f"unknown center doc(s): {sorted(missing)}")
        traversal, complete, limited_by, frontier = _bfs(
            sorted(set(seeds)), edges, direction,
            depth if depth is not None else 1, max_nodes)
        nodes = [d for d in nodes if d.id in traversal]
    if kinds:
        wanted_kinds = set(kinds)
        seed_set = set(seeds)
        nodes = [d for d in nodes if d.kind in wanted_kinds or d.id in seed_set]

    node_ids = {d.id for d in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
    edges = sorted(edges, key=lambda e: e["id"])
    omitted_edges = 0
    if max_edges is not None and len(edges) > max_edges:
        omitted_edges = len(edges) - max_edges
        edges = edges[:max_edges]  # stable order decides survival, never rank
        complete = False
        limited_by = limited_by or "max_edges"

    scope_members = None
    if project is not None:
        from .projections import resolve_scope  # same resolver as scoped retrieval
        scope_members = set(resolve_scope(root, project)["members"])

    out_nodes = []
    for d in sorted(nodes, key=lambda x: x.id):
        n = _node(d)
        n["degree"] = degree.get(d.id, 0)
        if traversal is not None:
            n.update(traversal[d.id])
        if scope_members is not None:
            n["in_scope"] = d.id in scope_members
        out_nodes.append(n)

    out = {
        "schema": "odin.graph.v1",
        "cache_key": snapshot.base_sweep(root),
        "center": center,
        "depth": (depth if depth is not None else 1) if seeds else None,
        "nodes": out_nodes,
        "edges": edges,
        "counts": {"nodes": len(out_nodes), "edges": len(edges)},
        "complete": complete,
        "unresolved_edges": unresolved,
    }
    if centers:
        out["centers"] = sorted(set(centers))
    if seeds:
        out["direction"] = direction
    if not complete:
        out["limited_by"] = limited_by
        out["unexpanded_frontier"] = frontier
        if omitted_edges:
            out["omitted_edges"] = omitted_edges
    if project is not None:
        out["scope"] = project
        out["counts"]["in_scope"] = sum(1 for n in out_nodes if n.get("in_scope"))
    return out
