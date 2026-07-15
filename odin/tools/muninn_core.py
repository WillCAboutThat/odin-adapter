"""Muninn Core — deterministic, tool-neutral operations (ADR-0008).

The Core owns every file write and every invariant-carrying step, as **fat atomic
operations**, and runs with no AI present. The adapter supplies judgment and calls
into here for anything that touches the store. This module is the trust layer:
its output must always leave the Muninn conformant (the linter is the check).

**Facade (T-122):** the implementation lives in the `muninn/` package beside this
file, split by subdomain (util · usage · capture · derive · candidates ·
projections · decisions · scaffold · registry · cli). This module remains the
stable surface: `import muninn_core`, the pip entry point (`muninn_core:main`),
and the documented CLI (`python tools/muninn_core.py <op> …`) are unchanged.
Cross-cutting internals are patchable via the shared module (`core.util._now`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from muninn import util  # noqa: E402,F401  (the shared patch point: core.util._now)
from muninn.util import (  # noqa: E402,F401
    FORMAT_VERSION,
    TOOL_VERSION,
    _ID_RE,
    _WINDOWS_RESERVED,
    _valid_id,
    _now,
    _load_yaml,
    _dump_yaml,
    _append_log,
    _lock_state,
    _write_lock,
    _locked,
    _read_doc,
    _load_yaml_frontmatter,
)
from muninn.usage import (  # noqa: E402,F401
    _source_bytes,
    log_usage,
    read_usage_records,
    usage_report,
    usage_html,
    _scope_bytes,
    usage_log,
)
from muninn.capture import (  # noqa: E402,F401
    anchor,
    anchor_check,
    capture,
    capture_file,
    _capture,
    capture_repo,
    containment_report,
    dedup_check,
    log_drift_check,
    retier,
    source_status,
    upstream_identity_of,
)
from muninn.derive import (  # noqa: E402,F401
    log_challenge,
    relink,
    _TYPE_DIR,
    stamp_derived,
    supersede,
    write_derived,
)
from muninn.candidates import (  # noqa: E402,F401
    _CANDIDATES,
    _DECLINED,
    _KIND_PREFIX,
    _candidate_fingerprint,
    _source_prov,
    _fingerprints_in,
    stage_candidate,
    list_candidates,
    decline_candidate,
    _find_derived_doc,
    _fold_candidate_into,
    promote_candidate,
    regenerate_declined_index,
)
from muninn.projections import (  # noqa: E402,F401
    _DERIVED_GROUPS,
    _cover_map,
    _blurb,
    _index_markers,
    drift_worklist,
    regenerate_index,
    fingerprint,
    find,
    _render_project_body,
    write_project,
    reproject,
    resolve_scope,
    _LOCAL_ORIGINS,
    connector_projection,
)
from muninn.decisions import (  # noqa: E402,F401
    record_lint_entry,
    _AS_OF_WINDOW_DAYS,
    _days_old,
    _captures_since_last_lint,
    status,
    _source_version,
    record_decision,
    lint_report,
)
from muninn.scaffold import (  # noqa: E402,F401
    _LAYOUT,
    _TOOL_ROOT_SENTINEL,
    _tool_root_above,
    init,
)
from muninn.registry import (  # noqa: E402,F401
    _ROOT_P,
    _ID_POS,
    _op_capture,
    _usage_capture,
    _usage_derive,
    _show_list_candidates,
    _show_status,
    _show_find,
    _show_resolve,
    _show_connectors,
    _show_usage,
    _parse_connector,
    _parse_surface,
    OPS,
    UNTIMED_VERBS,
    mcp_tools,
    run_op,
)
from muninn.cli import (  # noqa: E402,F401
    _read_body,
    _cli_emit,
    main,
    build_parser,
    _main,
)

if __name__ == "__main__":
    sys.exit(main())
