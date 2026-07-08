"""SessionStart dependency bootstrap for the Odin plugin (ADR-0022 §6, T-071c).

A plugin cannot ship a Python wheel, and Python + `pyyaml` remain a genuine
prerequisite the plugin can *smooth* but not remove. This runs at SessionStart:
if `pyyaml` already imports (ambient interpreter), it does nothing; otherwise it
`pip install`s pyyaml into the plugin's **persistent data dir** (passed as argv[1],
`${CLAUDE_PLUGIN_DATA}/site`) — never into a shared `site-packages`. The MCP
server puts that dir on its own `sys.path` via `ODIN_DEP_DIR`, so the install is
process-scoped, matching the ADR's "controlled sys.path, no pollution" posture.

Idempotent and quiet: a no-op on the common path (pyyaml present), a one-time
install otherwise. Never fails the session — a bootstrap error is reported and
swallowed so a missing network doesn't block startup (the server will then fail
loudly with an honest ImportError, which is the correct degradation).
"""
import subprocess
import sys
from pathlib import Path


def ensure(dep_dir: str) -> int:
    site = Path(dep_dir)
    # Already importable from the ambient interpreter or a prior bootstrap?
    if str(site) not in sys.path:
        sys.path.insert(0, str(site))
    try:
        import yaml  # noqa: F401
        return 0
    except ImportError:
        pass

    site.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--target", str(site), "pyyaml"],
            check=True,
        )
        print(f"[odin] bootstrapped pyyaml into {site}")
        return 0
    except Exception as exc:  # never block the session
        print(f"[odin] could not bootstrap pyyaml ({exc}); "
              f"install it manually: python -m pip install pyyaml", file=sys.stderr)
        return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / ".odin-deps")
    sys.exit(ensure(target))
