# E-MAS DDI v1 Freeze

## Release identity

- Product: E-MAS Farmasi
- Release: E-MAS DDI v1.0
- Package version: 1.0.4
- Scope: DDI only
- Model / effort: Terra / High
- Date: 7 September 2026

## Verified implementation inventory

| Area | Evidence and status |
|---|---|
| Prescription source | Desktop/JAB and MySQL fallback exist. `MULTIPLE_PRESCRIPTION_SOURCES_ACTIVE` blocks dual producers. Automated PASS. |
| Identity and fingerprint | `no_resep`, `no_rawat`, clinical fingerprint, revision and dedup are covered by desktop/cross-prescription tests. Automated PASS. |
| Content | Regular, racikan and combined content are handled by the common prescription model. Automated PASS; final live matrix pending. |
| Mapping | Active canonical mapping, unmapped handling and new-canonical workflow are covered. Mapping does not declare DDI knowledge complete. PASS. |
| DDI and KB | Published KB is required for production screening; pairs are canonicalized and version-bound. Automated PASS. |
| Alert | Aggregated compact popup, one primary audio decision, SAFE/incomplete semantics and no reverse pair duplication are covered. Automated PASS. |
| Overlay | Severity projection, clear-first, stored-result restore and geometry fail-safe are covered. Automated PASS; final display-scale UAT pending. |
| Unmapped registry | Secondary one-worker persistence, occurrence dedup, RBAC inbox, direct mapping and new canonical mapping are covered. PASS. |
| Rajal/Ranap | Persistent installation scope and snapshot care-setting filtering are implemented. Automated PASS; live Ranap matrix pending. |
| Database | Alembic head is `0030_unmapped_drug_registry`; upgrade, rollback/re-upgrade and SQLite checks are covered. PASS. |

## Clinical-state semantics

| State | Required outcome | Automated result |
|---|---|---|
| `DDI_FOUND` | DDI popup/audio; known-DDI overlay | PASS |
| `FULLY_ASSESSED_ZERO_DDI` | SAFE audio; no severity overlay | PASS |
| `PARTIAL` / `UNMAPPED` | Never SAFE; incomplete feedback; registry stays non-blocking | PASS |
| `TECHNICAL_INCOMPLETE` | Never SAFE; fail-safe result | PASS |

## Test summary

- Targeted core regression: 154 tests, 2 stale-contract failures found and isolated.
- Regression fixes: release contract updated for schema `0030`; synthetic source fixtures now provide patient name and a stable same-day timestamp.
- Targeted recheck: 32 passed.
- Performance/source/registry recheck: 11 passed in 25.60 seconds. The popup latency check enforces commit-to-popup below 3 seconds and passed.
- Broad regression: **627 passed, 0 failed, 0 skipped**.

No latency p50/p95 telemetry is currently emitted. The release evidence therefore records the existing bounded latency test, rather than inventing a performance claim.

## Deployment and UAT status

- Desktop/JAB: automated PASS; final manual release matrix pending.
- MySQL fallback: automated contract coverage PASS; **NOT LIVE VERIFIED** because no live MySQL Khanza environment was supplied. This is a documented fallback limitation and does not block the JAB-targeted installation release.
- Rawat Jalan: automated PASS; manual matrix pending.
- Rawat Inap: automated scope coverage PASS; manual matrix pending.
- DPI 100%, 125%, 150%: prior overlay UAT exists, but the final release matrix still requires explicit operator confirmation.

## Knowledge base

- Active KB: production screening selects only `PUBLISHED` knowledge versions.
- Canonical drugs and DDI-pair totals: not read from the live clinical database during freeze verification.
- Bundled release smoke contract: 414 drug masters, 444 component mappings and 5,432 DDI rules.

## Known limitations and remaining risks

1. MySQL fallback has not received a live Khanza smoke test in this environment. It is outside the acceptance gate for the JAB-targeted installation.
2. Final manual UAT for Rajal, Ranap, racikan, rapid navigation, restart/recovery and display-scale matrix is outstanding.
3. Git checkpoint/tag cannot be created from this session because the repository index remains permission-blocked. Manual checkpoint required.

## Freeze decision

**STATUS: HOLD**

The code and automated release gate are PASS, but E-MAS DDI v1.0 must not be declared frozen until the manual checklist is completed. The unverified MySQL fallback is an accepted deployment limitation for the JAB-targeted installation and is not a freeze blocker.

## Git / tag recommendation

After manual UAT PASS, create one commit containing the reviewed dirty-worktree delta and tag it according to the existing convention, for example `v1.0.0`. Do not reset or clean the existing worktree.
