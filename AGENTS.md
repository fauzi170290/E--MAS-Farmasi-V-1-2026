# E-MAS permanent engineering rules

## 1. Delta only
- Inspect the current repository first, identify DONE/PASS, work only on the missing or failing delta, and never redo completed phases without evidence.

## 2. Evidence before code
`evidence → isolate last successful stage → first failed stage → hypothesis → smallest diagnostic → smallest patch → targeted regression → STOP`

## 3. Regression by bug
Every reproducible, fixed bug that can be automated must have a regression test.

## 4. Stable components
Do not disturb the DDI engine, mapping core, fingerprint/dedup, JAB bridge, overlay, popup/audio, adapters, or RBAC/security without direct evidence.

## 5. Prescription source and Desktop/JAB
Desktop/JAB XOR MySQL: never run both producers. Preserve `MULTIPLE_PRESCRIPTION_SOURCES_ACTIVE`. Desktop adoption is based on current prescription identity plus clinical fingerprint; a historical cursor must not reject a valid current snapshot. JAB is read-only: no setText, clicks of clinical actions, saves, edits, OCR, screenshot extraction, fixed-coordinate automation, memory hooks, or credential extraction. Production has one clearly owned Khanza bridge.

## 6. Fail-safe clinical state and audio
Never silently classify unmapped, incomplete, unassessed, stale, unstable, parser/read failures as SAFE. Distinguish `DDI_FOUND`, `FULLY_ASSESSED_ZERO_DDI`, `PARTIAL/UNMAPPED`, and `TECHNICAL_INCOMPLETE`. One primary audio per new evaluation: DDI→DDI audio; fully assessed zero DDI→SAFE audio; unmapped/partial with zero known DDI→INCOMPLETE audio; technical incomplete→never SAFE audio.

## 7. Mapping and knowledge governance
Mapping identity active does not imply complete DDI knowledge for a new canonical drug. Brands reuse canonical DDI knowledge; do not duplicate DDI pairs. Knowledge follows `source/provenance → normalized rule → tests → review/approval → publish`. Never auto-map or auto-approve uncertain active ingredients from fuzzy/string/AI inference. Reuse clinical fingerprint without transient focus/paint state.

## 8. Scope and critical path
Preserve Rawat Jalan, Rawat Inap, and Racikan where relevant without unrelated full matrices. Protect `Prescription Snapshot → Identity/Fingerprint → Mapping → Clinical Evaluation → Popup/Audio/Clinical Result`. Secondary work (registry persistence, counters, inbox refresh, analytics, exports, overlay, housekeeping) cannot block it: B must not wait for A. Popup/audio cannot wait for analytics, refresh, export, non-essential persistence, or overlay.

## 9. Secondary persistence, SQLite, and performance
Prefer lightweight enqueue → background worker → short transaction. Failure must not suppress valid DDI, delay popup/audio, or mark SAFE. Use short transactions, indexed lookup, atomic UPSERT where appropriate, no GUI-thread heavy writes, and no Excel work in the clinical path. Count clinical occurrences using prescription identity + fingerprint + normalized source code, never raw JAB callbacks. Measure before optimizing and prevent meaningful selection→result→popup/audio regression.

## 10. Overlay, privacy, and compatibility
Overlay is secondary UX; a wrong row is worse than no highlight, so clear/hide when uncertain. Prefer reason/count/hash/timing in logs, avoid unnecessary patient identity, and never log credentials/secrets. Preserve MySQLKhanzaAdapter fallback.

## 11. Test and delivery discipline
Run targeted tests first. Broaden only when shared core/schema/adapter contract/fingerprint/DDI/mapping/threading/release candidate changes. Finish only the requested objective. After PASS, stop; recommend at most three next options and never implement one without authorization. Use the lowest sufficient model/effort.

## 12. Engineering priority
`correctness > patient safety > fail-safe > reliability > compatibility > performance > deployment simplicity > convenience > visual polish > code elegance`
