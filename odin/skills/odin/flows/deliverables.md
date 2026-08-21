## Deliverables (original work product drafted from the base — ADR-0044, T-170)

Sometimes the thing you draft belongs *outside* the base: a memo, a grant
proposal, a set of interview questions, a briefing. Draft it at the base anyway.
Grounding and citations bind even when the output departs, and drafting away
from the base loses the provenance that makes it trustworthy. Landing one mints
a judgment-typed doc, so the coverage check above (T-206) runs first, exactly as
in map and synthesize.

A deliverable is read by people who never open the base, so **all six
plain-register rules (T-221) apply here at full strength.** They are what make a
memo readable to someone outside the project. Rule 3 matters most: a term the
base uses freely may be new to the reader, so expand it on first use or do not
use it. Rule 6 matters next: never drop a hedge to make the memo shorter, since
the hedge is the part that makes the claim honest.

1. **Land it typed by what it *is*, not by its filename.** A claim-bearing
   composition, meaning one that asserts things about the world, is an
   `insight`. It takes the synthesis rung, per-span citation, and the
   composition self-check. An instrument that asserts *nothing*, such as
   questions to ask, a checklist, or an agenda, is a `question` doc. That type
   is non-assertive and regenerable, and it ripens as sources arrive, because
   `regenerate` re-derives it when the answering source lands. Type by what the
   artifact *does*. That is the dogfood's own judgment, not the filename.

   This binds even when the user names a type. A requested type is a hint, never
   an override of the artifact's nature. Sometimes honoring it would force you
   to quarantine or strip the substance, reducing a claim-bearing argument to a
   sterile `question` doc, or inflating an assertion-free checklist into an
   `insight`. That stripping *is* the mismatch signal. Surface it and offer the
   fitting type: *"this reasoning asserts positions, so a question doc would
   drop them. An `insight` keeps them cited and synthesis-stamped. Want that
   instead?"* Never silently comply by gutting the content and reporting
   success. Heavy quarantine to fit a requested type means the type is wrong,
   not that the content was unfit to keep (T-193).
2. **Export the departing copy.** The derived doc is the warranted master. The
   exported `.docx`, email, or slide is a disposable projection of it. A pure
   one-shot with no reuse value may skip the landing.
3. **Authorship never mints a source; ratification does.** A deliverable becomes
   a source only through an event *in the world*: approval, execution, sending,
   or publication. What you capture is the artifact-of-record of that event,
   meaning the signed PDF, the sent email, or the recorded call's transcript,
   taken as the ratified version from the system that holds it. Never the
   working draft. On ratification the draft's derived doc takes its honest
   ending: `supersede --by` the ratified source (ADR-0041), keeping derivation
   history. Deriving *from* the ratified source is then legitimate and is not
   chaining, because it is a source. The warranty stays honest either way. It
   says *"faithfully what the approved brief says,"* never *"its claims are
   true"* — challenge and drift govern truth, as ever.

Never capture a working draft as a source. That launders a derived doc into
ground truth, and every later derivation would chain on it invisibly. It is the
intra-base twin of the T-165 forbidden shortcut. *Worked case: interview
questions drafted from the base land as a `question` doc and never become a
source. The call where they were asked does, captured as its transcript.*

