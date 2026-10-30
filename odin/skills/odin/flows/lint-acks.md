## Acknowledge expected lint warnings (operator judgment - ADR-0053)

A long-lived base accumulates warnings that are *expected* - the canonical
case is L10 on a base that deliberately grounds in reference-tier sources.
Acknowledging one records the operator's judgment (rule, path, reason, date -
durable in `lint-acks.yml`, history in `log.md`) and moves it from `warnings`
to the report's always-visible `acknowledged` bucket: it stops being restated
without ever disappearing.

- **Only on the user's explicit request** (the record-decision consent
  posture). Never acknowledge proactively, and never as a side effect of
  lint/ask/synthesize. *Offering* - "these three L10s look deliberate; want
  them acknowledged?" - is fine; acting without the user's word is not.
- `… lint-ack <root> <rule> <path> --reason "<why>"` - the (rule, path) pair
  must match a **current** warning, verbatim from the lint report. The reason
  is required: record the *user's* why, in their vocabulary - the next reader
  inherits it.
- **Errors can never be acknowledged.** The Core refuses them; don't offer it.
  An error is healed (regenerate, or the proper verb), never silenced.
- **Presenting lint results:** report errors and live warnings as ever. Do
  NOT restate acknowledged findings - summarize ("2 acknowledged warnings on
  record") and list them (reason · date · still-firing) only when the user
  asks for the acknowledged list.
- An entry with `matched: false` means its warning no longer fires. Mention
  it once and offer `… lint-unack <root> <rule> <path>` to tidy the record.
  It masks nothing new: a warning at any other (rule, path) always surfaces
  live, and only the exact acknowledged finding re-engages its ack if it ever
  returns - that is the recorded judgment doing its job.
- Withdrawing on request: `lint-unack` returns the warning to the live list.
