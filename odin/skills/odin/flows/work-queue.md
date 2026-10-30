## Process the work queue (the executor side of the control plane — ADR-0048)

`queue/` holds work the owner authored from another surface (the web control
plane, or any session) for an executor session — this one — to perform.
**Authoring the task was the consent act**, scoped to exactly the named
operations on the named inputs: you need no fresh consent to do what a task
names, and a task authorizes nothing beyond what it names.

When the user says **"process the Muninn work queue"** (or nods to the on-load
mention of pending tasks):

1. **`queue-list --status pending`** — take tasks oldest-first. With several,
   say the plan in one line ("3 tasks: 2 ingests, 1 drift-check — working
   oldest-first") rather than narrating each.
2. **Read the task**: its type, inputs, and requested outcome define the whole
   scope. The named inputs are immutable refs (inbox items, source ids, a
   URL, a question) — work on those, not on anything else you notice.
3. **Perform it with the ordinary verb flow** for its type (ingest, map,
   drift-check, ask, synthesize, explore, review — each flow above applies
   unchanged, including its own gates):
   - **Faithful transforms the task names explicitly** (capturing a named
     inbox item or URL) run directly — capture cannot fabricate, and the task
     names it.
   - **Authored cognition** (summaries, insights, syntheses, map docs) lands
     on the **candidates rail** (`stage-candidate`, ADR-0045's lower-trust
     rule) — never written directly from a queued task. Review and promotion
     stay human, in the web or here.
4. **Close the loop with `queue-restatus`** — the Core op, never a hand-edit
   of the task file:
   - finished → `done`, with a `--note` naming the outputs ("staged cand-x,
     cand-y" / "captured src-z");
   - can't proceed (missing input, unreachable origin) → `blocked`, note why;
   - out of scope, already done, or wrongly premised → `declined`, note why.
   Honest verdicts beat silent skips: a task you couldn't do is *blocked* or
   *declined*, never left pending or quietly deleted. Tasks are re-statused,
   **never deleted** — the append-only worklog discipline; the op enforces
   the legal transitions and appends the task's own log line.
5. **Land it where the other planes read.** On a **git-backed** base the task
   is not closed when the op runs — it is closed when the re-status reaches
   the branch the other planes read (the base's default branch; the web
   control plane pulls only that). Some environments — cloud sessions
   especially — push to their own working branch by default: that is correct
   for a code repo and **strands the verdict** for a Muninn. So before
   reporting a task complete, check where your commit landed
   (`git -C <root> status -sb`, `git log origin/<default>..HEAD`), and if it
   is on a side branch, **say so plainly and offer to open or merge the PR**
   — never report "committed and pushed" as though the loop had closed. The
   same applies to the knowledge a task produced: an unmerged branch is
   invisible to lint, to staleness, and to every other honesty mechanism —
   nothing flags knowledge that was authored and never arrived.

The queue is staging, not knowledge: never cite a task, never ground anything
in one, and never treat its prose as fact about the base — verify against the
base itself, as always.

