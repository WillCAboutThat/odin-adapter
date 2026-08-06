"""The CLI projection of the registry: generated argparse tree, one presenter (T-117), clean error boundary.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from .decisions import record_lint_entry  # noqa: E402
from .registry import OPS, run_op  # noqa: E402


def _read_body(args) -> str:
    if getattr(args, "file", None) and args.file != "-":
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read()


def _cli_emit(res, args):
    """The ONE presenter (T-117): `--json` emits the structured result as a JSON
    document; the default renders legible `key: value` lines — never a Python
    dict repr (the CLI's primary consumer is a model or a script)."""
    if getattr(args, "as_json", False):
        print(json.dumps(res, ensure_ascii=False, default=str))
    elif isinstance(res, dict):
        print("\n".join(f"{k}: {v}" for k, v in res.items()))
    elif isinstance(res, list):
        for item in res:
            print("  ".join(f"{k}={v}" for k, v in item.items())
                  if isinstance(item, dict) else item)
    else:
        print(res)


def main(argv=None):
    """CLI entry — `_main` does the work; this boundary turns an invariant
    rejection (ValueError — e.g. the T-045 lineage refusal, a new user's
    likeliest first error) or a missing file into a clean one-line message +
    exit 1, never a raw traceback (T-117)."""
    try:
        return _main(argv)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"error: not found: {getattr(e, 'filename', None) or e}", file=sys.stderr)
        return 1


def build_parser():
    """The argparse tree, GENERATED from the op registry (T-113) — the CLI
    projection of the same table odin_mcp projects into MCP tool schemas.
    Exposed for the parity test (tests/test_op_registry.py)."""
    p = argparse.ArgumentParser(prog="muninn_core",
                                description="Muninn Core — deterministic operations (ADR-0008).")
    sub = p.add_subparsers(dest="cmd", required=True)
    for verb, spec in OPS.items():
        sp = sub.add_parser(verb, help=spec.get("help") or spec["description"])
        body_param = (spec.get("cli") or {}).get("body_param")
        for name, ps in spec["params"].items():
            if name == body_param:
                continue                       # body arrives via --file / stdin
            c = ps.get("cli") or {}
            desc = ps.get("description", "")
            if c.get("positional"):
                kw = {"help": desc}
                if c.get("nargs"):
                    kw["nargs"] = c["nargs"]
                sp.add_argument(name, **kw)
                continue
            flag = c.get("flag") or "--" + name.replace("_", "-")
            kw = {"dest": name, "help": desc}
            if ps.get("required"):
                kw["required"] = True
            if c.get("metavar"):
                kw["metavar"] = c["metavar"]
            if ps.get("type") == "boolean":
                if c.get("tristate"):
                    kw["action"] = argparse.BooleanOptionalAction
                    kw["default"] = None
                else:
                    kw["action"] = "store_true"
            elif c.get("append"):
                kw["action"] = "append"
            else:
                if ps.get("type") == "integer":
                    kw["type"] = int
                if ps.get("enum"):
                    kw["choices"] = sorted(ps["enum"])
                if "default" in ps:
                    kw["default"] = ps["default"]
            sp.add_argument(flag, **kw)
        if body_param:
            sp.add_argument("--file", help="read the body from this file "
                                           "(default: stdin)")
        # Universal --json (T-117): every verb can emit its structured result.
        sp.add_argument("--json", action="store_true", dest="as_json",
                        help="emit the structured result as JSON (machine-readable)")
    return p


def _main(argv=None):
    # Help text and `find`/`resolve` output carry non-ASCII (—, ·, ∪), and stdin
    # bodies arrive as UTF-8 bytes. On a Windows console defaulted to cp1252,
    # argparse/print raise UnicodeEncodeError mid-write and `_read_body` mojibakes
    # inbound text (T-130); force UTF-8 in both directions so the CLI is
    # codepage-independent (no-op where a stream is already UTF-8 or can't be
    # reconfigured, e.g. a captured buffer).
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    spec = OPS[args.cmd]
    cli = spec.get("cli") or {}

    # collect params from the parsed args (the argparse → registry projection)
    params = {}
    for name, ps in spec["params"].items():
        if name == cli.get("body_param"):
            continue
        val = getattr(args, name, None)
        if val is None:
            continue
        c = ps.get("cli") or {}
        if c.get("join"):
            val = " ".join(val)
        if c.get("parse"):
            val = [c["parse"](v) for v in val]
        params[name] = val
    if cli.get("body_param") and not any(params.get(s)
                                         for s in cli.get("body_skip_if", ())):
        params[cli["body_param"]] = _read_body(args)
    root = params.pop("root")

    # lint keeps its human contract: the Linter's own report + exit code —
    # plus the ADR-0005 baseline entry (T-124), recorded at the op layer here
    # exactly as lint_report records it for --json/MCP.
    if args.cmd == "lint" and not args.as_json:
        linter = muninn_lint.Linter(Path(root))
        code = linter.run()
        errors = [f for f in linter.findings if f.severity == "error"]
        warns = [f for f in linter.findings if f.severity == "warn"]
        record_lint_entry(root, ok=not errors, n_errors=len(errors),
                          n_warnings=len(warns),
                          fingerprint=linter.content_fingerprint())
        return code

    res = run_op(OPS, args.cmd, root, params)
    if spec.get("presenter") and not args.as_json:
        spec["presenter"](res)
    else:
        _cli_emit(res, args)
    if args.cmd == "lint":
        return 0 if res["ok"] else 1
    return 0
