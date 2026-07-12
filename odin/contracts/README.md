# Muninn format contracts — machine-readable, frozen at 1.0

These JSON Schemas are the **machine-readable projection of the Muninn format
contract** (ADR-0037). They exist so that "the format is frozen" is checkable by
tools that are not ODIN: any JSON Schema validator, in any language, can verify
that a document's frontmatter conforms — no AI, no vendor, no Python required.

| Schema | Validates | SPEC |
|--------|-----------|------|
| `source-meta.schema.json` | `sources/<id>/meta.yml` — an immutable captured record (a meeting note, a contract, a recipe, a scanned PDF, a repo constitution) | §5.1 |
| `derived.schema.json` | frontmatter of `summaries/`, `entities/`, `concepts/`, `questions/`, `insights/` | §5.2 |
| `project.schema.json` | frontmatter of `projects/<name>.md` view pages | §5.6 |
| `decision.schema.json` | frontmatter of `decisions/<id>.md` — the KB owner's own recorded decisions | §5.5 |
| `manifest.schema.json` | `muninn.yml` — the file that marks a directory as a Muninn | §5.7 |

## The three layers of the contract

1. **`docs/muninn/SPEC.md`** — the narrative authority: the invariants (I1–I5)
   and the prose semantics. Frozen at 1.0; additive amendments only.
2. **These schemas** — the shape of each document's frontmatter, exact where
   the format is exact (required fields, enums, `sha256:<hex>` hashes) and
   silent about fields it doesn't know (unknown fields are always permitted —
   forward compatibility is part of the format, SPEC §5).
3. **`tools/muninn_lint.py` (L1–L19)** — the operative enforcement, which also
   checks what a per-document schema *cannot*: the cross-document invariants.
   No chaining (a provenance id resolving to a derived doc, L2), staleness
   (recorded vs current hash, L4), hash correctness against the bytes on disk
   (L5), ledger ↔ disk coverage (L13), every-source-has-a-summary (L15). A
   base is conformant when it satisfies **both** the schemas and the linter.

On any conflict between the layers, **the SPEC governs** and the divergence is
a bug; `tests/test_contracts_schema.py` pins the layers together (schema enums
== linter enums; what the Core writes validates against these schemas).

## Validating

Schemas apply to the **parsed YAML mapping** (the frontmatter block of a `.md`
document, or the whole `meta.yml` / `muninn.yml`). Load timestamps as plain
strings (JSON has no timestamp type). For example, in Python:

```python
import json, yaml, jsonschema
from pathlib import Path

schema = json.loads(Path("contracts/source-meta.schema.json").read_text())
meta = yaml.safe_load(Path("my-kb/sources/src-vendor-contract/meta.yml").read_text())
jsonschema.validate(meta, schema)   # raises on non-conformance
```

Any draft 2020-12 validator in any ecosystem works the same way.

## The freeze (ADR-0037)

From 1.0, the format evolves **additively only**: new optional fields, new enum
values, new document types — opt-in, gated by the `muninn:` manifest version.
Never removed, renamed, re-meant, or tightened. Every 1.0-conformant Muninn
remains conformant, readable, and verifiable under every 1.x rule set,
unchanged. Anything that can't keep that promise is a 2.0 with its own ADR and
an explicit migration story.
