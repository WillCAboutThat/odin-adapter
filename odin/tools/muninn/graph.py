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


def _edges_of(docs, by_id) -> list[dict]:
    """Every explicit edge in the base, deduped by id, targets resolved."""
    edges: dict[str, dict] = {}
    # origin.ref → source id, for the two locator-join relations (ADR-0039/T-196)
    by_ref: dict[str, str] = {}
    for d in docs:
        if d.kind == "source":
            ref = str((d.data.get("origin") or {}).get("ref") or "")
            if ref:
                by_ref.setdefault(ref, d.id)

    def add(relation, src_id, dst_id, **extra):
        if src_id == dst_id or src_id not in by_id or dst_id not in by_id:
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
    return list(edges.values())


def _neighborhood(center: str, depth: int, edges: list[dict]) -> set[str]:
    """Ids within `depth` undirected hops of `center` over the given edges."""
    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e["source"], set()).add(e["target"])
        adj.setdefault(e["target"], set()).add(e["source"])
    seen, frontier = {center}, {center}
    for _ in range(max(0, depth)):
        frontier = {n for f in frontier for n in adj.get(f, ()) if n not in seen}
        if not frontier:
            break
        seen |= frontier
    return seen


def project_graph(root, *, center=None, depth=None, kinds=None, relations=None):
    """Project the base's explicit relationship graph (`odin.graph.v1`).

    center/depth — restrict to the undirected neighborhood of one doc
    (depth defaults to 1 when a center is given; an unknown center raises).
    kinds — keep only these node kinds (source/derived/project/decision).
    relations — keep only these edge relations (see RELATIONS).
    Filters compose: relations are applied before the neighborhood walk, so
    e.g. center+relations answers "what grounds this, one hop out".
    """
    root = Path(root)
    snap = snapshot.load_snapshot(root)
    docs = [d for d in snap.docs if d.kind != "manifest"]
    by_id = {d.id: d for d in docs}

    all_edges = _edges_of(docs, by_id)
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

    nodes = docs
    if center is not None:
        if center not in by_id:
            raise ValueError(f"unknown center doc '{center}'")
        keep = _neighborhood(center, depth if depth is not None else 1, edges)
        nodes = [d for d in nodes if d.id in keep]
    if kinds:
        wanted_kinds = set(kinds)
        nodes = [d for d in nodes if d.kind in wanted_kinds]
        if center is not None and center in by_id and by_id[center].kind not in wanted_kinds:
            nodes.append(by_id[center])  # the center always survives its own view

    node_ids = {d.id for d in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    out_nodes = []
    for d in sorted(nodes, key=lambda x: x.id):
        n = _node(d)
        n["degree"] = degree.get(d.id, 0)
        out_nodes.append(n)
    return {
        "schema": "odin.graph.v1",
        "cache_key": snapshot.base_sweep(root),
        "center": center,
        "depth": (depth if depth is not None else 1) if center is not None else None,
        "nodes": out_nodes,
        "edges": sorted(edges, key=lambda e: e["id"]),
        "counts": {"nodes": len(out_nodes), "edges": len(edges)},
    }
