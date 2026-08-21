"""Enumerate a repository's *constitution* and build a manifest from it (ADR-0028).

A repo's constitution is its slow-changing, **intent-bearing** surfaces — the things
that change when its *identity* changes (re-architecture, repurpose, split/merge,
ownership) and stay flat under implementation churn: the README, ARCHITECTURE / in-repo
ADRs, the top-level module *shape*, the public contract, and the identity manifests.

Enumerating and hashing those surfaces is a **faithful transform** (it reads named
paths — no inference), so it belongs in the Core boundary. The *mental model* an adapter
authors *from* the manifest is `model-read` and stays out of the Core (ADR-0028 §6). The
payoff: because a repo-source's captured text is *only* its constitution, the ordinary
`content_hash` staleness (L4/L5) becomes **drift-on-amendment, not drift-on-commit**.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# (label, [glob patterns]) — order defines the manifest's order. Shallow globs only:
# we read a small, named set, never walk the whole tree.
SURFACES = [
    ("readme",       ["README.md", "README.rst", "README.txt", "README"]),
    ("agent_contract", ["CLAUDE.md", "AGENTS.md", "GEMINI.md",
                        ".github/copilot-instructions.md"]),  # state the project's rules/identity
    ("architecture", ["ARCHITECTURE.md", "docs/ARCHITECTURE.md", "docs/*/ARCHITECTURE.md",
                      "ARCHITECTURE"]),
    ("adrs",         ["docs/decisions/*.md", "docs/adr/*.md", "docs/adrs/*.md"]),
    ("contract",     ["openapi.yaml", "openapi.json", "openapi/*.yaml", "api/*.proto",
                      "proto/*.proto", "*.proto", "schema.graphql"]),
    ("manifest",     ["package.json", "pyproject.toml", "Cargo.toml", "go.mod",
                      "setup.py", "setup.cfg", "composer.json", "Gemfile",
                      "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]),
    # For infra / GitOps repos the identity manifest is the **deploy descriptor**: what
    # the system runs and where. ADR-0028 §4 names it generically, so the floor covers the
    # common orchestration descriptors, not only docker-compose (T-195). Shallow (root +
    # one level) and faithful (hash named files — never infer "what it deploys").
    ("deploy",       ["docker-compose.yml", "docker-compose.yaml", "compose.yml",
                      "compose.yaml", "*/docker-compose.yml", "*/docker-compose.yaml",
                      "*/compose.yml", "*/compose.yaml",
                      "Chart.yaml", "*/Chart.yaml", "charts/*/Chart.yaml",   # helm
                      "kustomization.yaml", "kustomization.yml",
                      "*/kustomization.yaml", "*/kustomization.yml",         # kustomize
                      "serverless.yml", "serverless.yaml",                   # serverless
                      "*.tf", "*/main.tf",                                   # terraform root module
                      "fly.toml", "render.yaml", "render.yml", "Procfile"]),  # PaaS descriptors
]

# top-level entries excluded from the topology surface — noise, not identity.
_TOPOLOGY_EXCLUDE = {".git", ".odin", ".hg", ".svn", "node_modules", "__pycache__",
                     ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build",
                     ".DS_Store", ".idea", ".vscode", ".ruff_cache", ".tox"}


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _real_name(p: Path) -> Path:
    """`p` with the casing the directory actually stores (T-228).

    `Path.glob` does not scandir a literal segment — it joins and existence-checks,
    which is case-insensitive on Windows, so a pattern like `docs/ARCHITECTURE.md`
    "matches" a file named `docs/architecture.md` and hands back the PATTERN's
    casing. Recording that gives a path which resolves on the machine that wrote
    it and 404s on any case-sensitive checkout. Ask the directory instead.
    """
    try:
        for entry in p.parent.iterdir():
            if entry.name.lower() == p.name.lower():
                return entry
    except OSError:                      # unreadable dir: keep what glob gave us
        pass
    return p


def _rel(repo: Path, f: Path) -> str:
    """Repo-relative path, POSIX-separated and on-disk-cased (T-228).

    This string is recorded in the manifest header AND embedded in the
    `<!-- file: … -->` markers that make up the hashed content, so it must
    describe the REPO rather than the host that read it. `str(relative_to(...))`
    renders the host separator, which made one repo at one commit hash
    differently on Windows than on Linux — the ADR-0049 lesson (line endings are
    not content) pointed at path separators.
    """
    return _real_name(f).relative_to(repo).as_posix()


def _match(repo: Path, patterns) -> list[Path]:
    hits: list[Path] = []
    for pat in patterns:
        for p in sorted(repo.glob(pat)):
            if p.is_file() and p not in hits:
                hits.append(p)
    return hits


def topology(repo: Path) -> str:
    """The repo's top-level *shape* — entry names + dir/file marker, sorted, noise
    excluded. It changes when modules are added/removed/renamed (structural) and stays
    flat under edits *inside* them — so it tracks identity, not churn."""
    entries = []
    for p in sorted(repo.iterdir(), key=lambda x: x.name):
        if p.name in _TOPOLOGY_EXCLUDE:
            continue
        entries.append(f"{p.name}/" if p.is_dir() else p.name)
    return "\n".join(entries) + "\n"


def enumerate_constitution(repo_path, extra_surfaces=None) -> list[dict]:
    """The constitution surfaces present in the repo, each
    `{label, paths (repo-relative), content, hash}`. Absent surfaces are omitted; the
    `topology` surface is always present (a repo always has a shape).

    `SURFACES` is the **AI-free floor** — a deterministic default that works with no
    model (ADR-0008/0014). `extra_surfaces` (a list of `(label, [globs])`) lets an
    *adapter* — a frontier model that looked at this repo and judged what matters here —
    **augment** the floor per repo (ADR-0028 §6: choosing surfaces is judgment; hashing
    them is the Core's faithful transform). It augments, never replaces, so the floor
    always stands. The adapter's choice is recorded in the manifest (legible, re-checkable)."""
    repo = Path(repo_path)
    out: list[dict] = []
    for label, patterns in list(SURFACES) + list(extra_surfaces or []):
        files = _match(repo, patterns)
        if not files:
            continue
        parts, rels = [], []
        for f in files:                       # concatenate matched files (sorted) so a
            rel = _rel(repo, f)               # multi-file surface (adrs) hashes stably
            rels.append(rel)
            # HTML-comment file marker: unambiguous (won't collide with the file's own
            # markdown headers) and invisible when the manifest is rendered.
            parts.append(f"<!-- file: {rel} -->\n" + f.read_text(encoding="utf-8", errors="replace"))
        content = "\n".join(parts)
        out.append({"label": label, "paths": rels, "content": content, "hash": _hash(content)})
    topo = topology(repo)
    out.append({"label": "topology", "paths": ["(top-level shape)"],
                "content": topo, "hash": _hash(topo)})
    return out


def parse_manifest_surfaces(manifest_text: str) -> list[dict]:
    """Read back the surface header a `build_manifest` wrote — `[{label, paths, hash}]`,
    in header order — a **faithful parse of stored text** (no repo touch, no inference), the
    read-side companion `repo-coverage` uses to learn which surfaces a captured constitution
    holds. Parses only the header lines (`- <label>: <p1>, <p2> — <hash>`) above the `---`
    divider; a manifest that doesn't parse yields `[]` (the caller still knows the
    constitution is present from its own frontmatter). Mirrors the writer's format exactly —
    the em-dash separator and `, `-joined paths of the `- {label}: {paths} — {hash}` line."""
    out: list[dict] = []
    for raw in manifest_text.splitlines():
        line = raw.rstrip()
        if line == "---":            # header ends at the divider; body follows
            break
        if not line.startswith("- ") or " — " not in line or ": " not in line:
            continue
        head, _, hsh = line[2:].rpartition(" — ")
        label, _, paths = head.partition(": ")
        if not label or not hsh.startswith("sha256:"):
            continue
        out.append({"label": label.strip(),
                    "paths": [p.strip() for p in paths.split(",") if p.strip()],
                    "hash": hsh.strip()})
    return out


def build_manifest(repo_path, *, head=None, extra_surfaces=None):
    """Assemble the constitution manifest — the text an adapter reads to author the repo
    mental model — and return `(manifest_text, surfaces)`. A header lists each surface and
    its hash (and the optional HEAD stamp) so *which* surface changed is legible; the body
    is the surfaces' content. Only constitution surfaces are included, so the manifest (and
    the source `content_hash` over it) is stable under implementation churn. `extra_surfaces`
    are adapter-chosen surfaces augmenting the default floor (see `enumerate_constitution`)."""
    surfaces = enumerate_constitution(repo_path, extra_surfaces=extra_surfaces)
    lines = ["# Repository constitution", ""]
    if head:
        lines.append(f"inferred-at-commit: {head}")
    lines.append(f"surfaces: {len(surfaces)}")
    # The blank line is load-bearing: without it, markdown renderers join the
    # key: value prelude and this list into one run-on paragraph (T-233 rider).
    lines.append("")
    for s in surfaces:
        lines.append(f"- {s['label']}: {', '.join(s['paths'])} — {s['hash']}")
    lines += ["", "---", ""]
    for s in surfaces:
        # Surface boundary as an HTML comment, so it never blends with the surface's own
        # markdown headers (## Status, ## Decision, …) — legible to a human and the adapter.
        lines.append(f"<!-- ═════ constitution surface: {s['label']} ═════ -->")
        lines.append(s["content"].rstrip("\n"))
        lines.append("")
    return "\n".join(lines) + "\n", surfaces
