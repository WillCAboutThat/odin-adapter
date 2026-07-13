# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
# ^ PEP-723 inline metadata (ADR-0031): `uv run --script` provisions Python + pyyaml
#   cross-platform, so the plugin's `.mcp.json` launches this with `command: uv` and
#   needs no `python3` on the host. The sibling Core modules resolve via the
#   sys.path.insert below (uv's isolated env doesn't block local imports).
"""Odin Core MCP server — a second, tool-neutral transport over the Core ops
(ADR-0022, T-071).

This is a **thin wrapper** with *no business logic of its own*. It imports
`muninn_core` and exposes its existing fat atomic ops as MCP tools. Every
guarantee still lives in the ops + the linter, never in this transport (ADR-0022
§2): an MCP client calling `capture` can violate an invariant no more than the
CLI can — the op rejects chaining, requires provenance, etc., and `lint` catches
the rest. The worst a naive MCP client does is produce a base that *lints dirty*,
which is surfaced, never silent.

Three layers, deliberately separated so the mapping is testable without a
transport:

  1. ``TOOLS``     — the tool-schema surface (name, description, JSON Schema
                     for arguments), GENERATED from the op registries
                     (muninn_core.OPS ∪ muninn_semantic.OPS — T-113): the same
                     tables that generate the CLI, so the surfaces can't drift.
  2. ``dispatch``  — a PURE function ``(op, params) -> json-serializable``. It
                     maps MCP arguments onto the Core call, resolving the one
                     real mapping question (ADR-0022 build note): the CLI's
                     ``--file``/stdin *body* becomes a ``body`` string argument,
                     and ``--source-file`` becomes a ``source_file`` path the
                     server reads (both transports run local, same filesystem).
                     No MCP dependency — this is what the eval drives directly.
  3. the stdio loop — a stdlib-only JSON-RPC 2.0 server (initialize / tools/list
                     / tools/call) so the plugin needs no `mcp` wheel installed;
                     a process boundary + bundled Core is stronger encapsulation
                     than a shared-`site-packages` package (ADR-0022 Consequences).

Run as ``python3 odin_mcp.py`` (stdio). Bundled by the Claude/Codex plugins
(T-071b/T-072); also usable by any MCP client pointed at this command.
"""
import json
import os
import sys
import time
from pathlib import Path

# Import the Core from THIS directory (the plugin bundles it here — ADR-0022:
# self-contained, imports nothing from a shared site-packages). If a plugin
# SessionStart hook bootstrapped deps (pyyaml) into the plugin data dir, honor
# that path too — a controlled per-process sys.path, not a global install (§c).
sys.path.insert(0, str(Path(__file__).resolve().parent))
_DEP_DIR = os.environ.get("ODIN_DEP_DIR")
if _DEP_DIR:
    sys.path.insert(0, _DEP_DIR)
import muninn_core as core  # noqa: E402
import muninn_semantic as semantic  # noqa: E402  (the disposable semantic tier, T-087)

SERVER_NAME = "odin-core"
# One string, both identities (T-118c): the TOOL's version (what shipped) plus
# the FORMAT version it writes (what's frozen) as semver build metadata —
# previously this reported only the format version, so 1.0.x tool releases were
# indistinguishable in a client's server listing.
SERVER_VERSION = f"{core.TOOL_VERSION}+format-{core.FORMAT_VERSION}"
# Echoed to the client if it doesn't ask for a specific version; a recent stable
# MCP protocol revision. We echo the client's requested version when it sends one.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


# --------------------------------------------------------------------------- #
# 1. Tool-schema surface — one MCP tool per fat atomic op (ADR-0022 §1).
#    Descriptions carry the discipline so an MCP client/model wields the op
#    correctly; the op itself still enforces it.
# --------------------------------------------------------------------------- #
TOOLS = core.mcp_tools(core.OPS) + core.mcp_tools(semantic.OPS)
_TOOL_NAMES = {t["name"] for t in TOOLS}


def _mcp_name(verb):
    return "odin_" + verb.replace("-", "_")


# MCP tool name -> the registry handler (root, params) -> json-serializable.
# GENERATED from the two op registries (T-113): muninn_core.OPS (the
# deterministic Core) ∪ muninn_semantic.OPS (the disposable semantic tier).
# The same tables generate the CLI surfaces, so CLI ↔ MCP drift is
# structurally impossible (tests/test_op_registry.py pins the equality).
_DISPATCH = {_mcp_name(v): spec["handler"]
             for ops in (core.OPS, semantic.OPS) for v, spec in ops.items()}

# MCP tool name -> the registry's best-effort usage hook (root, p, res, duration_ms).
_USAGE_HOOKS = {_mcp_name(v): spec["usage"]
                for v, spec in core.OPS.items() if spec.get("usage")}

# MCP tool name -> CLI verb, so timing records carry the same op names on both
# surfaces (T-123) and the report never splits one op into two rows.
_VERB_BY_TOOL = {_mcp_name(v): v
                 for ops in (core.OPS, semantic.OPS) for v in ops}


def dispatch(op, params):
    """Invoke a Core op by MCP tool name. Pure: maps `params` onto the Core call
    and returns its json-serializable result. Raises KeyError for an unknown op
    and lets the Core's own ValueErrors (invariant rejections) propagate — the
    transport layer turns those into a tool error, never a silent success."""
    if op not in _DISPATCH:
        raise KeyError(f"unknown tool {op!r}")
    params = params or {}
    root = params.get("root")
    if root is None:
        raise ValueError("every op needs `root` (the Muninn directory)")
    p = {k: v for k, v in params.items() if k != "root"}
    return _DISPATCH[op](root, p)


def _note_usage(op, params, result=None, duration_ms=None):
    """Record the byte-footprint + wall-time of an op to the disposable usage
    ledger (ADR-0027/T-123) — the registry's own usage hook, fired the same way
    the CLI fires it; unhooked ops get a minimal timed record under their CLI
    verb name (the same rule as `run_op`, so the two surfaces aggregate as one).
    Best-effort; never affects the result and is kept OUT of `dispatch()` so
    that stays pure (the ADR-0022 equality test)."""
    try:
        params = dict(params or {})
        root = params.pop("root", None)
        if root is None:
            return
        hook = _USAGE_HOOKS.get(op)
        if hook is not None:
            hook(root, params, result if isinstance(result, dict) else {},
                 duration_ms=duration_ms)
            return
        verb = _VERB_BY_TOOL.get(op)
        if verb is None or verb in core.UNTIMED_VERBS or duration_ms is None:
            return
        core.log_usage(root, verb, duration_ms=duration_ms)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 3. stdio JSON-RPC 2.0 loop — stdlib only, so the plugin ships no `mcp` wheel.
#    Handles the MCP lifecycle (initialize / tools/list / tools/call / ping).
# --------------------------------------------------------------------------- #
def _result(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_message(msg):
    """Handle one JSON-RPC request/notification; return a response dict, or None
    for a notification (no reply). Kept pure/synchronous for direct testing."""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        proto = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        return _result(mid, {
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    # notifications (no `id`) — acknowledge by staying silent
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _result(mid, {})

    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in _TOOL_NAMES:
            return _error(mid, -32602, f"unknown tool: {name!r}")
        t0 = time.perf_counter()
        try:
            out = dispatch(name, arguments)
        except Exception as exc:  # invariant rejection / bad args -> tool error,
            # surfaced to the client (never a silent success). ADR-0022 §2.
            return _result(mid, {
                "content": [{"type": "text",
                             "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            })
        # disposable usage ledger (ADR-0027); best-effort, timed at the seam (T-123)
        _note_usage(name, arguments, out,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 3))
        text = json.dumps(out, ensure_ascii=False, default=str)
        return _result(mid, {
            "content": [{"type": "text", "text": text}],
            "structuredContent": out if isinstance(out, dict) else {"result": out},
            "isError": False,
        })

    # Unknown method. Only error on requests (with an id); ignore stray notifications.
    if mid is None:
        return None
    return _error(mid, -32601, f"method not found: {method!r}")


def serve(stdin=None, stdout=None):
    """Newline-delimited JSON-RPC over stdio (the MCP stdio transport). Reads one
    JSON message per line, writes one response per line."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    # UTF-8 both directions, codepage-independent (see CLI). stdin included:
    # the client sends raw UTF-8 JSON-RPC, and a Windows locale (cp1252) stdin
    # would mojibake every non-ASCII character in tool arguments before the
    # Core faithfully stores the garbage (T-130).
    for stream in (stdin, stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_message(msg)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            stdout.flush()


def main(argv=None):
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
