# AGENTS.md — E-MAS Farmasi Engineering Rules

## Purpose

This file is the permanent engineering contract for AI coding agents working on **E-MAS Farmasi**.

The goals are to:
- prevent repeated work;
- preserve completed and validated phases;
- reduce unnecessary repository-wide audits and regression runs;
- protect patient safety;
- keep real-time prescription processing fast;
- preserve backward compatibility;
- avoid feature creep;
- make debugging evidence-driven;
- use the lowest sufficient model/effort;
- ensure future agents understand the architecture and safety invariants.

---

# 1. Project Identity

**Project:** E-MAS Farmasi  
**Type:** Medication Safety / Clinical Decision Support desktop application.

Primary environment includes:
- Windows
- Python
- PySide6
- SQLite
- SQLAlchemy/Alembic where already used
- SIMRS Khanza integration

Prescription-source implementations include:

1. **KhanzaDesktopAdapter**
   - Java Access Bridge / KhanzaBridge
   - reads the current local Khanza UI
   - read-only

2. **MySQLKhanzaAdapter**
   - existing MySQL/four-view integration
   - retained as fallback / alternative deployment mode

Core concepts already present include:
- prescription snapshot
- prescription identity
- clinical fingerprint
- dedup/revision
- canonical drug master
- Khanza drug mapping
- DDI master
- DDI pair workflow
- DDI engine
- popup/audio
- prescription queue
- unmapped handling
- visual overlay
- audit/security
- local persistence

Treat the current repository implementation as the source of truth.

---

# 2. Golden Rule — DELTA ONLY

**DO NOT REDO COMPLETED PHASES.**

Before coding:
1. Inspect the current implementation relevant to the task.
2. Inspect relevant recent changes/commits if available.
3. Inspect existing relevant tests.
4. Inspect logs/runtime evidence when investigating a bug.
5. Determine what is already DONE/PASS.
6. Determine exactly what is missing or failing.
7. Work only on that DELTA.

Do not audit the whole repository for every small bug.
Do not rerun an old phase merely because its tests exist.

If a component was already validated and the new change does not touch it:

> LEAVE IT ALONE.

---

# 3. Evidence Before Code

For bugs, follow:

```text
evidence
  ↓
isolate
  ↓
LAST SUCCESSFUL STAGE
  ↓
FIRST FAILED STAGE
  ↓
hypothesis
  ↓
smallest diagnostic
  ↓
smallest patch
  ↓
targeted regression
  ↓
STOP
```

Do not:

```text
see symptom
  ↓
broad refactor
  ↓
hope the bug disappears
```

If evidence is insufficient, add minimal instrumentation first.

---

# 4. Regression-by-Bug Rule

When a reproducible bug is fixed, and that bug can reasonably be automated, add a regression test that specifically protects against its return.

Examples include:
- valid Desktop snapshot rejected by historical cursor;
- two prescription sources becoming active simultaneously;
- repeated JAB callbacks creating duplicate clinical occurrences;
- stale/cross-prescription overlay restoration;
- mapping invalidation failing to invalidate dependent clinical result.

The repository should become harder to break after every real bug.

---

# 5. Do Not Rewrite Stable Components Without Evidence

Stable components must not be rewritten merely because another design looks cleaner.

Treat the following carefully:
- DDI engine
- mapping core
- canonical drug identity
- clinical fingerprint/dedup
- alert decision
- popup/audio
- prescription adapters
- JAB bridge
- visual overlay
- SQLite persistence
- RBAC/security
- DDI governance

Refactor only when there is clear evidence or a justified architecture requirement.

“Cleaner code” alone is not sufficient reason to disturb clinical core.

---

# 6. One Active Prescription Source

This is a permanent invariant.

At one runtime:

```text
KhanzaDesktopAdapter XOR MySQLKhanzaAdapter
```

Only **ONE** prescription source may produce clinical prescription events.

Desktop mode:

```text
Desktop/JAB = ACTIVE
MySQL prescription adapter = NOT STARTED
MySQL prescription polling = NOT STARTED
```

MySQL mode:

```text
MySQL adapter = ACTIVE
Desktop prescription listener = NOT ACTIVE
```

Fallback means the alternative source remains available in code/config.

Fallback does **NOT** mean both sources run simultaneously.

Preserve protection such as:

```text
MULTIPLE_PRESCRIPTION_SOURCES_ACTIVE
```

Do not silently remove this guard.

---

# 7. Desktop/JAB Semantics

MySQL and Desktop/JAB are not the same type of source.

MySQL is historical/data-record oriented.

Desktop/JAB is current-active-UI-snapshot oriented.

Desktop prescription adoption should fundamentally rely on:

```text
current prescription identity
+
clinical fingerprint
```

A historical time cursor must not become a gate that causes a valid current Desktop snapshot to be skipped.

Cursor may be used as telemetry/progress where useful.

It must not override correct active prescription identity.

---

# 8. JAB Must Remain Read-Only

E-MAS may READ Khanza using Java Access Bridge.

Do not use E-MAS to:
- edit Khanza fields;
- call setText;
- save;
- invoke clinical actions;
- change Khanza data;
- automate clinical button clicks;
- modify Khanza through JAB.

Do not introduce as shortcuts:
- OCR
- screenshot-based extraction
- fixed screen-coordinate automation
- memory hooks
- traffic sniffing
- JDBC interception
- credential extraction

Any major departure requires explicit user approval and safety/security review.

---

# 9. No Duplicate Bridge

Do not start additional KhanzaBridge processes while the production E-MAS bridge is active unless absolutely required for controlled diagnostics.

If a diagnostic bridge/process is started:
- identify its PID;
- ensure it does not compete for callbacks;
- terminate it immediately afterward.

Production runtime should have one clearly owned bridge instance.

---

# 10. Clinical Priority Order

Always preserve this priority:

1. Correct prescription/patient
2. Complete prescription data
3. Correct regular/racikan drug content
4. Correct identity/fingerprint
5. Correct mapping state
6. No cross-patient contamination
7. No false SAFE
8. Correct DDI result
9. Correct alert/audio
10. Reliability
11. Performance
12. UX enhancement
13. Code elegance

Performance or UI convenience must never outrank clinical correctness.

---

# 11. Fail-Safe — Never Turn Unknown Into SAFE

Never silently interpret these as SAFE:
- unmapped drug
- unassessed drug
- incomplete snapshot
- unstable snapshot
- missing racikan component
- JAB read failure
- parser failure
- stale result
- missing clinically necessary identity
- unavailable assessment data

Reuse the existing clinical state taxonomy where possible.

Do not invent a second competing state model without need.

---

# 12. Clinical Result Semantics

E-MAS must distinguish at minimum:
- `DDI_FOUND`
- `FULLY_ASSESSED_ZERO_DDI`
- `PARTIAL / UNMAPPED`
- `TECHNICAL_INCOMPLETE`

These are **NOT** equivalent.

Safe/no-DDI semantics are allowed only when:

```text
prescription complete
AND
relevant drugs mapped
AND
required assessment completed
AND
zero DDI found
```

“No DDI found” does not mean total clinical safety.

---

# 13. Audio Semantics

A successfully completed **NEW** prescription evaluation should give meaningful audio feedback.

Priority:

1. **Known DDI found**
   - DDI audio
   - popup as required

2. **Zero DDI + fully assessed**
   - SAFE / NO-DDI audio
   - no DDI popup

3. **Zero known DDI + unmapped/partial**
   - distinct UNMAPPED / INCOMPLETE audio
   - no DDI popup
   - mapping recommendation remains available

4. **Technical incomplete**
   - never SAFE audio

Only **ONE** primary completion audio per evaluation.

Do not play:
- DDI + SAFE
- DDI + UNMAPPED

for one evaluation cycle.

Use existing fingerprint/dedup to prevent repeated nuisance audio caused by noisy JAB events.

---

# 14. Mapping ≠ DDI Knowledge Completeness

Mapping a Khanza product to a canonical drug means its identity is known.

It does **NOT** automatically prove that the canonical drug has complete DDI knowledge.

This is especially important for brand-new canonical drugs.

Example:

```text
Brand drug
  ↓
new canonical active ingredient
  ↓
mapping ACTIVE
```

does not automatically mean:

```text
all DDI pairs for this new drug are already known/published
```

Do not create a false fully-assessed SAFE state merely because identity mapping now exists.

Reuse existing DDI knowledge lifecycle/governance.

---

# 15. Brand Products Must Reuse Canonical DDI

Do not create duplicate brand-specific DDI databases if the brand maps to an existing canonical ingredient.

Example:

```text
NORVASC
  ↓
AMLODIPINE
  ↓
existing canonical DDI knowledge
```

Do **NOT** create an entire second set of:

```text
NORVASC ↔ Drug X
NORVASC ↔ Drug Y
```

when canonical Amlodipine already represents the clinical identity.

---

# 16. Clinical Knowledge Governance

For clinical-rule/knowledge changes:

```text
source / provenance
  ↓
normalized rule
  ↓
test
  ↓
review / approval
  ↓
publish
```

Do not invent clinical facts from AI memory and directly publish them.

Reuse existing workflow/status such as:
- DRAFT
- REVIEW / PENDING
- APPROVED
- PUBLISHED
- RETIRED

where present.

---

# 17. Mapping Governance

Do not aggressively guess active ingredient mappings.

Do not auto-approve uncertain mappings.

Administrative mapping should use the existing canonical master workflow.

If Admin Utama has an explicitly designed direct mapping workflow, follow that product rule.

Do not silently map based only on fuzzy string similarity or AI suggestion.

---

# 18. Clinical Fingerprint & Dedup

Reuse existing fingerprint infrastructure.

Do not create a second fingerprint engine unless strictly necessary.

Fingerprint should describe clinically relevant prescription content.

Avoid transient UI state such as:
- focus
- selected row
- paint state
- transient display timing

from causing clinically identical prescriptions to appear different.

Same prescription + same fingerprint:

```text
do not repeatedly alert because of UI noise
```

Changed clinical fingerprint:

```text
reevaluate
```

---

# 19. Rawat Jalan / Rawat Inap / Racikan

Do not assume only one Khanza workflow.

Changes that touch prescription acquisition or clinical evaluation must consider where relevant:
- rawat jalan
- rawat inap
- regular drugs
- racikan
- regular + racikan

However, do not rerun the entire workflow matrix for every tiny isolated UI change.

Test only what could realistically be affected.

---

# 20. Clinical Critical Path Is Protected

Protected real-time path:

```text
PRESCRIPTION SNAPSHOT
  ↓
IDENTITY / FINGERPRINT
  ↓
MAPPING
  ↓
CLINICAL EVALUATION
  ↓
POPUP / AUDIO / CLINICAL RESULT
```

Administrative/secondary work must not block this path unless that work is explicitly required for clinical correctness.

Examples of SECONDARY work:
- unmapped drug registry persistence
- occurrence counters
- first_seen / last_seen
- admin inbox refresh
- visual overlay rendering
- analytics
- statistics
- export
- reporting
- UI badges
- housekeeping
- non-critical audit enrichment

**Prescription B must not wait for secondary work created by Prescription A.**

Preferred:

```text
clinical result
  ↓
popup/audio dispatch
  ↓
lightweight enqueue
  ↓
background secondary worker
```

---

# 21. Secondary Work Must Be Non-Blocking

Do not implement:

```text
Prescription A
  ↓
unmapped registry DB commit
  ↓
admin inbox refresh
  ↓
then allow Prescription B
```

Instead:

```text
Prescription A clinical evaluation
  ↓
enqueue unmapped observation
  ↓
Prescription B may begin immediately
```

while registry work completes separately.

Use:
- lightweight queues
- coalescing/dedup
- short transactions
- bounded retry
- separate DB session/worker according to current architecture

If secondary persistence fails:
- do not suppress a valid DDI result;
- do not delay popup/audio;
- do not convert prescription to SAFE;
- log/retry according to existing reliability policy.

---

# 22. SQLite / Database Write Discipline

Do not hold long SQLite write transactions.

For secondary writes:
- keep transactions short;
- use indexed lookup;
- use atomic UPSERT where appropriate;
- do not hold a transaction while performing unrelated work;
- do not refresh entire admin tables from the clinical worker;
- avoid GUI-thread database writes.

Do not make Excel export/import part of the real-time clinical pipeline.

---

# 23. Occurrence Counters Must Represent Clinical Occurrences

Never use raw JAB callback count as a clinical occurrence counter.

Repeated:
- focus event
- table event
- value change
- repaint
- reread

must not increment an unmapped drug occurrence repeatedly.

Deduplicate using a key conceptually equivalent to:

```text
prescription identity
+
clinical fingerprint
+
normalized source drug identity
```

One prescription/evaluation occurrence should count once.

---

# 24. Performance Debugging

Do not optimize by guessing.

Measure relevant stages.

Example:

```text
UI/JAB event
→ snapshot
→ stability
→ adoption
→ mapping
→ DDI
→ alert creation
→ popup visible
→ audio start
```

Optimize the proven bottleneck only.

If DDI takes 50 ms but popup takes 2 seconds:

> do not rewrite DDI.

---

# 25. Alert Critical Path

Prefer:

```text
clinical result
  ↓
minimal clinically required persistence
  ↓
popup/audio
  ↓
non-critical UI/dashboard/statistics work
```

Do not make alert presentation wait for:
- dashboard refresh
- export
- analytics
- full admin table refresh
- non-essential enrichment
- overlay rendering

---

# 26. Visual Overlay Is Secondary

Where DDI row highlighting exists:

Overlay is a UX layer, not clinical authority.

It must never block:
- DDI result
- popup
- audio

If overlay becomes uncertain:

> CLEAR / HIDE it rather than display the wrong row.

No stale cross-patient highlight is acceptable.

Wrong-row highlight is worse than no highlight.

---

# 27. Overlay Restore Safety

When restoring overlay after navigation such as:

```text
A → B → A
```

a stored result may be reused only when it is still clinically valid.

Restore must be bound to:

```text
prescription identity
+
clinical fingerprint
```

and must respect current:
- assessment completeness
- mapping validity
- screening/result validity
- knowledge-base version
- retry/recheck state
- current geometry validity

Do not restore cached overlay for stale, invalidated, partial, unmapped, or technically incomplete results.

Native revision may be used for geometry freshness but must not become the clinical-result identity.

---

# 28. DPI / Geometry / Native Overlay Safety

Overlay geometry must remain fail-safe.

Do not use arbitrary hard-coded pixel corrections.

Support or explicitly validate coordinate conversion between:
- JAB bounds
- Windows screen/physical coordinates
- Qt device-independent coordinates
- monitor origin
- per-monitor DPI

If coordinate correctness cannot be proven:

> hide/clear overlay.

Never weaken safety merely to make color appear.

---

# 29. Logging & Privacy

Prefer technical logs containing:
- stage
- reason code
- item count
- fingerprint/hash
- timing
- source state
- non-clinical geometry metrics where needed

Avoid unnecessary:
- patient names
- diagnosis
- full prescriptions
- sensitive clinical content

Never log:
- passwords
- secrets
- database credentials

---

# 30. Test Strategy — Targeted First

For localized bugs:

```text
targeted unit tests
+
relevant integration test
+
minimal runtime/UAT where needed
```

Do not automatically run broad/full regression.

Broad regression is justified when changes affect:
- shared clinical core
- adapter contract
- DB schema/shared models
- fingerprint
- DDI engine
- mapping core
- shared threading
- release candidate

A tiny UI change does not justify hundreds of unrelated clinical tests.

---

# 31. Backward Compatibility

Preserve `MySQLKhanzaAdapter`.

Do not remove existing MySQL/four-view integration simply because Desktop/JAB is preferred.

Shared changes must remain compatible where reasonably supported.

---

# 32. No Feature Creep

If task is:

```text
fix popup
```

do not build:
- SignaParser
- dose checker
- Compatibility Wizard
- inventory

If task is:

```text
unmapped registry
```

do not simultaneously redesign DDI engine.

Complete the current objective first.

---

# 33. STOP Rule

When the requested objective passes:

> STOP.

Do not automatically:
- start another phase
- refactor unrelated code
- redesign unrelated UI
- add optional features
- rewrite documentation broadly

Report results and wait for user approval.

---

# 34. Model / Effort Efficiency

Do not recommend the most expensive model merely because it exists.

Use the lowest sufficient model/effort.

General guideline:

### LOW
- labels
- text
- tiny isolated UI edits

### MEDIUM
- localized bugs
- CRUD
- straightforward workflow
- existing-service integration
- targeted tests

### HIGH
- native/JAB complexity
- concurrency
- race conditions
- difficult schema/shared-core migrations
- security-critical changes
- clinical engine architecture
- complex cross-thread invalidation

Escalate based on evidence, not habit.

---

# 35. Post-Task Development Recommendation

After a task has PASSED:

Agent may offer **up to 3** next-development options.

But:

> DO NOT IMPLEMENT THEM.

Each recommendation should state:
- Value
- Why now
- Dependency
- Risk
- Suggested model
- Suggested effort

Then wait for user approval.

---

# 36. Stability Before Feature Expansion

Before introducing a major new clinical capability, confirm that the critical prescription path is sufficiently stable:

```text
Khanza
→ snapshot
→ identity/fingerprint
→ mapping
→ clinical evaluation
→ popup/audio
→ audit
```

If there are unresolved:
- lost prescriptions
- stale snapshots
- cross-patient results
- unexplained latency
- duplicate alerts
- unstable bridge behavior

prioritize stability before adding major clinical features.

---

# 37. Shared Core Extraction — Only When Justified

Do not prematurely extract a giant reusable framework.

Recommend shared modules only when:
- at least two real consumers exist;
- API is stable enough;
- maintenance benefit is clear.

Potential future reusable domains include:
- drug identity
- mapping
- rules
- audit
- security
- config
- Khanza access

Do not refactor merely for theoretical reuse.

---

# 38. Current Phase 2.7 Product Invariants

For **Automatic Unmapped Drug Registry & Admin Mapping Inbox**:

- unmapped persistence is SECONDARY and non-blocking;
- same prescription/fingerprint/source drug must not create repeated occurrence counts;
- registry should deduplicate primarily by normalized source drug code;
- `first_seen` is set once;
- `last_seen` changes on valid distinct clinical occurrence;
- only current unresolved items belong in the Admin inbox;
- the inbox does not need a redundant “PERLU PEMETAAN” status column;
- Admin Utama may directly map an unresolved Khanza product to an existing canonical drug;
- direct Admin mapping becomes ACTIVE immediately;
- mapped item disappears from unresolved list after successful commit;
- source Khanza code/name should be auto-filled and not retyped;
- brand products reuse canonical DDI knowledge;
- new canonical drug creation must reuse existing Master Obat domain/services;
- new canonical + active mapping does not mean DDI knowledge is complete;
- existing DDI pair workflow must be reused;
- Excel export/import must not create a second mapping engine;
- normal master-import governance such as `PENDING_REVIEW` must not be globally weakened merely to support Phase 2.7;
- no historical alert flood after mapping;
- A → B → C switching must remain responsive while registry persistence for A is still running.

---

# 39. Engineering Priority

For E-MAS:

```text
correctness
>
patient safety
>
fail-safe
>
reliability
>
backward compatibility
>
performance
>
deployment simplicity
>
convenience
>
visual polish
>
code elegance
```

Never reverse this hierarchy.

---

# 40. Final Task Report Format

Keep final reports concise and evidence-based.

```text
ROOT CAUSE:
...

EVIDENCE:
...

CHANGE:
...

TESTS:
...

PERFORMANCE:
...

RESULT:
...

REMAINING RISK:
...

NEXT RECOMMENDED ACTION:
...

SUGGESTED MODEL:
...

SUGGESTED EFFORT:
...
```

Do not repeat project history unnecessarily.

---

# 41. Repository Discipline

At the beginning of every task:
1. confirm repository root;
2. read this `AGENTS.md`;
3. inspect `git status`;
4. preserve dirty/uncommitted user work;
5. never reset, clean, revert, or overwrite unrelated changes without explicit user approval.

If Git operations fail because of permissions:
- do not block safe source inspection or user-requested implementation solely because a commit cannot be created;
- do not attempt destructive workarounds;
- report the Git limitation;
- continue only if the user explicitly authorizes continuing without the checkpoint commit.

---

# 42. Final Instruction

This file is a repository-level engineering contract.

When any task-specific prompt conflicts with patient safety, fail-safe behavior, source isolation, or critical-path protection defined here:

> preserve the safer invariant and report the conflict.

When the requested objective is complete:

> STOP and wait for the user.
