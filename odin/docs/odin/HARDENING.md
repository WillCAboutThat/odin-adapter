# Ownership hardening — a kernel-enforced write boundary for a Muninn (T-155)

**Optional deployment posture, not part of the format.** A hardened base is a
directory the *adapter's* account can read but not write: the only write path
is a privilege-restricted invocation of the Core. Every rule that today binds
the adapter by contract — "the Core owns every write," "never hand-edit" —
becomes physics.

## The threat model (why this exists)

Every rule binding an adapter is probabilistic: instructions drop under
context pressure, and a sufficiently determined prompt can talk a session past
"forbidden" with nothing but friction. Detection already exists (L19 flags
out-of-band writes at lint); this is the *prevention* rung. Honest scope:

| Threat | Under hardening |
|---|---|
| Hand-edits, frontmatter surgery, fabricated provenance, out-of-band writes | **Impossible** — kernel-enforced, argument-proof |
| Unconsented but *op-shaped* writes (a `supersede` you never asked for) | **Not prevented** — ops verify invariants, not consent; every such write is logged, linted, provenance-carrying, and therefore auditable |
| Garbage content pushed *through* ops | Partially — ops verify what is checkable (hashes, lineage, quoted-span containment per T-153) |

It also does **not** protect the base from *you*: you own the machine and root
exists. It protects the base from accidents (stray `rm`, editor auto-save,
sync clients) and from every write path that isn't a Core op.

**The trust ladder this completes:** disposition (steered) → contract
(elicited) → probes (audited weekly) → evidence-in-artifact (T-153
containment at the seam) → **OS enforcement (this document)**. Above it sits
only ADR-0024's archive-grade/WORM backend — bytes unrewritable even by root —
for evicted blobs, when built.

## Prerequisite: correction-op coverage (met as of 1.10.0)

Under hardening, a repair path that prescribes an owner hand-edit is a hard
wall. Audit result (2026-07-16): **no sanctioned hand-edit path remains in the
contracts** — the correction-op family covers every legitimate fix
(`supersede` for a doc's honest ending, `retier` for a misjudged tier,
`project --remove-member` for view reorganization, `anchor --force` with
evidence for containment overrules, versioned re-capture for content). If a
future contract ever prescribes a hand-edit again, that prescription is a bug
under this posture — file it.

## Linux / WSL2

```bash
# 1. The service account (no login shell; it exists to own the base)
sudo useradd --system --shell /usr/sbin/nologin odin

# 2. Ownership: odin writes, everyone reads (the open format survives)
sudo chown -R odin:odin /path/to/base
sudo chmod -R u+rwX,go+rX,go-w /path/to/base

# 3. The single door — a COMMAND-RESTRICTED passwordless grant.
#    /etc/sudoers.d/odin-muninn  (edit with visudo -f):
you ALL=(odin) NOPASSWD: /usr/bin/python3 /path/to/tools/muninn_core.py *, \
                         /usr/bin/python3 /path/to/tools/muninn_semantic.py *
```

Invoke every write through the door: `sudo -u odin python3 …/muninn_core.py
capture <base> …`. The MCP server launches under the same rule (wrap the
`.mcp.json` command in `sudo -u odin`). Two properties make this hold against
a persuaded adapter: the grant names the **entry points only** — `sudo -u odin
bash` and `sudo -u odin python3 -c …` are not the permitted commands — and
your own broader sudo stays password-gated, which a model cannot type. Keep
the Core files themselves owned by root or your account (not odin, and not
world-writable), or the door could be redefined by editing the script it
points at.

## macOS

Identical posture; the account creation differs:

```bash
sudo sysadminctl -addUser odin -roleAccount -shell /usr/bin/false
sudo chown -R odin /path/to/base && sudo chmod -R u+rwX,go+rX,go-w /path/to/base
# sudoers grant exactly as on Linux (visudo)
```

## Windows (the honest problem child)

The **read-only half is excellent**: NTFS ACLs are richer than POSIX.

```powershell
net user odin <password> /add /passwordchg:no      # local service account
icacls C:\Odin /inheritance:d
icacls C:\Odin /grant "odin:(OI)(CI)M" /grant "$env:USERNAME:(OI)(CI)RX" /remove:g "$env:USERNAME"
```

The **privileged-invocation half has no clean native answer**: Windows lacks a
command-restricted, passwordless run-as-another-user (`runas` prompts every
invocation; Windows 11 `sudo` elevates to admin, not across accounts). The
workable options today:

1. **Task Scheduler with stored credentials** — register a task running as
   `odin` per op-shape you need; clunky for ops with arguments and results.
2. **A small local service running as `odin`, exposing the op surface** — the
   clean answer, and it is exactly T-082's local-Core-host shape becoming
   load-bearing. Not built yet; this document records the gravity.
3. **Interim posture:** NTFS read-only + the harness deny-rules below —
   prevention of accidents and casual writes, friction against persuasion,
   with kernel-grade write enforcement waiting on the host. Or run the base
   inside WSL2 and take the Linux recipe wholesale.

## The harness companion (friction, not enforcement)

Claude Code permission rules give ergonomic, early refusal *in conversation* —
the adapter declines before the kernel would have. In the project's
`.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Write(/path/to/base/**)",
      "Edit(/path/to/base/**)"
    ]
  }
}
```

Documented honestly: this is the sandbox being operated by the party you are
guarding against — `Bash` has a thousand ways to write a file, and rule-based
command inspection is a losing cat-and-mouse. Use it *with* the OS layer, not
instead of it: the harness rule makes the refusal graceful; the kernel makes
it true.

## Git sync under hardening

You cannot commit or pull a base you cannot write. **Do not solve this with a
broad `sudo -u odin git *` grant** — `git checkout` and friends form an
arbitrary-write surface that reopens the door the posture closed. The pattern
that preserves the single-door property is **fixed-verb wrapper scripts**,
root-owned, each doing exactly one thing:

```bash
# /usr/local/bin/muninn-sync   (owned root:root, mode 755)
#!/bin/sh
exec git -C /path/to/base pull --ff-only

# /usr/local/bin/muninn-commit (owned root:root, mode 755)
#!/bin/sh
cd /path/to/base && git add -A && git commit -m "muninn: ${1:-checkpoint}" && git push
```

with sudoers lines permitting exactly those two paths as `odin`. The wrapper
IS the policy: what it doesn't do, the boundary doesn't allow. This resolves
the sync question for the common case; exotic git workflows (rebase, history
surgery) are deliberately outside a hardened base's daily life.

## Backup, restore, and fresh machines

Permissions are **per-machine operational state — never part of the base**. A
git clone or file copy arrives owned by whoever made it; the base's
readability, verifiability, and rescue story are unchanged (that is the
ADR-0008 durability floor doing its job). Hardening a new machine =
re-running the ownership + sudoers steps above. Backups need only read
access (world-readable by design); a restore lands unhardened until you
re-apply the recipe — which is correct: rescue must never require the
service account to exist.

## Verifying the posture

- `status <base>` reports **`caller_can_write: false`** from the adapter's
  context — the deterministic tell (the SKILL instructs the adapter to expect
  the privileged wrapper and never work around a denial).
- `touch /path/to/base/probe` from your account must fail;
  `sudo -u odin python3 …/muninn_core.py lint <base>` must succeed.
- `lint` stays your independent integrity check — L19 still detects any write
  that somehow bypassed the door (defense in depth: detection outlives any
  single prevention layer).
