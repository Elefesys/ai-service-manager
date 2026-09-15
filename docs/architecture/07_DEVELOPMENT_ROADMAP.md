# AI Service Manager — Development Roadmap

**Baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** LOCKED dependency roadmap for implementation planning

---

## 1. Purpose

Canonical source for **the order in which the first Production Pilot and Commercial MVP are implemented**.

Source-of-truth hierarchy:
- `01_ARCHITECTURE_SPEC.md` — architecture and hard constraints;
- `06_MVP_SPEC.md` — what the first release contains and acceptance criteria;
- `07_DEVELOPMENT_ROADMAP.md` — dependency order, milestone DoD and Pilot→Commercial sequence.

This roadmap does not assign calendar estimates. Those are created after milestones are decomposed into engineering tickets with a known stack/team.

## 2. Development principles

1. Build vertical slices, not isolated layers.
2. Production Pilot is the first target.
3. Security/RLS/reliability/observability/tests start early and grow with every capability.
4. AI is read/query-only before state-changing tools.
5. Deterministic services are proven before AI mutation access.
6. Scheduling/Hold semantics stabilize before Client Payments.
7. Business Console and Platform Ops grow incrementally.
8. Stage-23 exclusions stay excluded without evidence/ADR.
9. No speculative microservices/empty future adapters.
10. MVP features must reach `PILOT_READY`, not merely backend-complete.


## 2.1. RU implementation bindings from Stage 26

During M0–M12, provider-neutral interfaces remain mandatory, but the first concrete implementation uses the RU profile:
- Yandex Cloud-class RU infrastructure bundle as default;
- RU_AGGREGATOR with PolzaAI preferred, GPTunnel comparison; DIRECT_PROVIDER adapter for eligible official APIs; branch-independent execution/data checks;
- YooKassa first Client payment candidate;
- FiscalizationService/FISCALIZATION_READY before real payment cutover.

Technical spikes before Pilot must validate:
1. selected aggregator/direct routes with shared Tattoo EvalSuite, structured output/tools/Vision/embeddings and measured cost/latency;
2. Yandex PostgreSQL/pgvector/RLS/PITR restore/Object Storage/Lockbox/OTel path;
3. YooKassa hosted checkout/webhook/idempotency/reconciliation;
4. actual first Business fiscalization path.

No implementation ticket may introduce direct VPN/proxy foreign AI as a shortcut.

## 3. Pilot dependency map

```text
M0 Engineering Foundation
→ M1 Tenant / Auth / DB Foundation
→ M2 Telegram Messaging Backbone
→ M3 Conversation Engine + Human Control
→ M4 Read-only AI Runtime
→ M5 Tattoo Knowledge / Onboarding / Vision / Portfolio
→ M6 Request / Assessment / Pricing / Quote
→ M7 Scheduling / Hold / Appointment
→ M8 Client Payments
→ M9 Automations
→ M10 Business Console + Platform Ops Completion
→ M11 Golden Journeys + Feature Freeze
→ M12 Security / Reliability / Eval Hardening
→ PILOT RELEASE CANDIDATE
```

Cross-cutting tracks: tests, UI, Platform Ops, observability/cost, security, CI/infrastructure and AI Evals.

## 4. M0 — Engineering Foundation

**Goal:** repeatable engineering environment.

Build repository structure, backend/frontend skeletons, real local PostgreSQL, migrations, Docker, CI, test runner and environment-based config.

**Stack checkpoint:** choose frameworks/tooling that satisfy PostgreSQL/RLS/transactions, typed schemas, async jobs, webhooks, OpenTelemetry and strong testing.

**DoD:** local stack starts; migration runs; real PostgreSQL integration test passes; CI is green; Docker image builds; no production secrets/data are ordinary local dependencies.

## 5. M1 — Tenant / Auth / DB Foundation

Build UserAccount, Workspace, Business, Membership, BusinessMember/Location baseline, WorkspaceContext, authorization, RLS, tenant-safe FKs, DB-role separation, Audit baseline and authenticated Business Console shell. Add minimal WorkspaceBillingAccount/PlanRevision/Entitlements/Subscription (TRIALING or ACTIVE+COMPED), service mode and local entitlement checks; paid provider charging stays M15.

**DoD:** Owner login works; Workspace A cannot access B through real runtime role/RLS; trusted context is server-created.

## 6. M2 — Durable Telegram Messaging Backbone

Build Telegram adapter, ChannelConnection/Route, verified webhook, InboxEvent, Client/Identity, Conversation/Message, Outbox, FileObject/Object Storage image path, Inbox UI and manual Owner reply.

```text
Telegram Client → durable Inbox → correct Workspace → Business Console
→ manual Owner reply → Outbox → Telegram
```

**DoD:** text/image persist correctly; duplicate webhook does not duplicate canonical message; private files work; Outbox recovery works; connection health visible.

This is the **first tangible development target** and intentionally has no AI.

## 7. M3 — Conversation Engine + Human Control

Build TurnAggregator, ConversationTurn/State, awaiting-response structure, version/stale/control-generation guards, Human/AI control and Escalation basics. Include command/send admission, stale worker rejection, in-flight send visibility and owner wait lifecycle.

**DoD:** multi-message turns work; stale output is suppressible; Takeover stops automation; Resume works.

## 8. M4 — Read-only AI Runtime

Build provider-neutral ModelGateway, selected PolzaAI-candidate aggregator adapter and selected direct-provider adapter, AIProviderBranch/AIRoutingRevision, ModelProfile, PromptRegistry, ContextBuilder, Structured Outputs, AIRun/ProviderCall/ToolCall, query-only tools, usage/cost/latency telemetry and small EvalSuite.

**No state-changing tools.** Both selected adapters pass shared fake/sandbox contract tests and synthetic branch-switch tests; live direct route is conditional on eligibility. Pin routing revision per AIRun; test failed activation and rollback. Do not implement a third unused vendor adapter.

**DoD:** Telegram→Turn→AIRun→safe reply works with pinned revisions/tool trace; injection smoke passes; prompt data is bounded/minimized; usage/cost recorded.

## 9. M5 — Tattoo Knowledge / Onboarding / Vision / Portfolio

Build Service/Revision, Rules, Knowledge/RAG+pgvector, CommunicationProfile, Portfolio, Vision/MediaAnalysis, historical chat analysis, ConfigurationDraft/Validation/Release and TattooIndustryPack v1. Add minimal WorkflowDefinition/Revision/Instance/StepInstance runtime, owner-labelled DurationCase ingestion and per-service price/duration/payment configuration validation.

Pack v1: NEW_TATTOO; COVER_UP→escalate; OTHER_COMPLEX→escalate.

**DoD:** realistic Tattoo config supports correct intake, image interpretation, real portfolio/knowledge retrieval, authority handling and safe escalation.

## 10. M6 — Request / Assessment / Pricing / Quote

Build ServiceRequest/provenance, approved Assessment, fixed/bounded-formula/Owner PricingEngine, PriceCalculation, immutable Quote/QuoteAcceptance, ServiceOrder/next ServiceSession, ApprovalRequest/frozen action/revalidation and Owner Quote Action Center. Keep price and duration authority independent; allow one owner decision to supply both. Client-scoped tool access and cross-AIRun intent idempotency are mandatory.

**DoD:** normal request can reach valid Quote; custom price can route through Owner; unsupported case escalates safely.

## 11. M7 — Scheduling / Hold / Appointment

Build deterministic Resource/availability/policy/duration/buffer/AvailabilityOffer/Hold/Allocation/Appointment/cancel/reschedule and DB overlap protection before Agent scheduling mutations.

Add Agent tools only after deterministic tests, using server-generated option/Hold IDs. Implement approved-duration gating, atomic self-overlap reschedule, CalendarBlock conflict protocol and deterministic NONE-prepayment Hold→Appointment path.

**DoD:** real availability options, one authoritative winner in slot race, Calendar reflects state; concurrency/timezone/DST tests pass.

## 12. M8 — Client Payments

The path below is the prepayment variant; NONE booking from M7 remains independent.

Build provider sandbox adapter, PaymentTerms/Request/Session/Transaction, provider-specific verified webhook, idempotency/reconciliation, manual offline confirmation and Owner-approved Refund. Add BusinessLegalProfile/FiscalizationProfile/Receipt obligation/manual or provider flow, deadlines, Action Center and fiscal gate. Test fixed/percentage/full/NONE terms, acceptance binding, duplicate real payment, cumulative refunds and early callback/UNKNOWN.

```text
Hold → PaymentRequest → hosted checkout → SUCCEEDED
→ PaymentRequest SATISFIED → revalidate Hold → Appointment
```

**DoD:** full Golden Journey A succeeds; duplicate/out-of-order/timeout/late-payment behavior is safe; Golden Journey E passes.

## 13. M9 — Automations

Build Appointment reminder, payment reminder/Hold warning, bounded Client follow-up and Owner escalation notification over persistent jobs. Include ROUTE_UNAVAILABLE owner task, owner decision timeout/staleness and explicit HUMAN-mode notification policy.

**DoD:** cancel/reschedule/reply/takeover/restart/late-policy tests pass; no stale/duplicate sends.

## 14. M10 — Business Console + Platform Ops Completion

Complete Business Console Action Center/Inbox/Takeover/Approvals/Escalations/Calendar/Clients/Requests/Quotes/Payments/Knowledge/Portfolio/basic config/connection health.

Complete Platform Ops Workspace/provider health, Inbox/Outbox lag, Jobs/DLQ, AIRun/tool diagnostics, payment mismatch, SupportAccessGrant, Audit and safe Retry/Replay/Resync.

**DoD:** routine Pilot operation requires no ad-hoc SQL/SSH/manual DB mutation. Pixel-perfect UI is not required.

## 15. M11 — Golden Journeys + Feature Freeze

Run Stage-23 Golden Journeys A–J and v0.28 variants in MVP Spec §19.1 end to end.

Enter **Feature Freeze**. After freeze only bug/security/reliability/critical UX/eval fixes enter Pilot RC without scope ADR.

## 16. M12 — Hardening / Eval / Pilot RC

Close all Stage-23 readiness gates.

Build `Tattoo EvalSuite v1` including ordinary/missing/multi-message/slang/image/unsupported/cover-up/Owner Quote/price/scheduling/payment/RAG/injection/takeover/staleness scenarios.

Run RLS/auth/files/webhook/support/secrets hardening; duplicate/race/retry/failure injection; backup restore including external effects/newer deletion state/old-worker fencing; dashboards/critical alerts; privacy and fiscal readiness inputs.

**DoD:** DOMAIN_READY, AI_READY, SECURITY_READY, RELIABILITY_READY, BUSINESS_CONFIG_READY, OPERATIONS_READY and PRIVACY_READY are all green; FISCALIZATION_READY is green before RU live payments.

## 17. Pilot Release Candidate

Pin application/container, DB schema/migration, TattooIndustryPack, Prompt revisions, ModelProfiles, Tool/schema versions, KnowledgeBuild, BusinessConfigurationRelease and EvalSuiteRevision.

Pilot deploys this known bundle, not a moving branch.

## 18. Parallel tracks

Throughout M0–M12:

| Track | Responsibility |
|---|---|
| Backend/Domain | capability path |
| Tests | unit/integration/concurrency/security/recovery |
| Business Console | incremental operational UX |
| Platform Ops | support/diagnostics |
| Observability | metrics/logs/traces/cost |
| AI Evals | regression from first AI milestone |
| Security | auth/RLS/files/secrets/support |
| CI/Infrastructure | build/deployability |

## 19. Schema rollout by capability

Do not pre-create the whole future model.

- M1: Workspace/Business/UserAccount/Membership/Audit + local Subscription/Plan/Entitlements.
- M2: Channel/Client/Conversation/Message/File/Inbox/Outbox.
- M3: ConversationTurn/State/Escalation.
- M4: AIProviderBranch/AIRoutingRevision/AI run+calls and selected adapter pair.
- M5: Service/Rules/Knowledge/Portfolio/MediaAnalysis/Configuration + Workflow runtime/DurationCase.
- M6: ServiceRequest/Assessment/PriceCalculation/Quote/QuoteAcceptance/Order/Session/ApprovalRequest.
- M7: Resource/Availability/Hold/Allocation/Appointment.
- M8: PaymentTerms/Request/Session/Transaction/Refund + legal/fiscal profile/receipt obligation.

Use canonical concepts immediately; do not invent temporary generic Booking/state models.

## 20. Implementation completeness

- `SKELETON` — scaffolding only.
- `PILOT_READY` — meets MVP plus security/reliability/telemetry/tests/UI/Ops obligations.
- `EXPANSION_READY` — broader post-pilot complexity.

M0–M12 pursue `PILOT_READY` only where Stage 23 requires it.

## 21. Technical spikes

Allowed short spikes: Telegram connection mode, RLS/WorkspaceContext, Resource overlap/concurrency, AI Structured Outputs/tool loop, signed Object Storage flow and payment sandbox/idempotency.

Each spike ends with a decision/test/constraint. Prototype code is not automatically production code.

## 21.1. Required spike timing / audit pass 1

- Before M2 completes: actual Telegram connect/rights/native owner message behavior, reply window and delivery UNKNOWN test.
- Before substantial M4–M5 build: small synthetic Tattoo corpus across shortlisted routes; catalog IDs/capabilities, data eligibility, cost and p50/p95 latency. Early suite precedes full M12 corpus.
- Before M6 formula/duration publish: master supplies approved rules/examples; missing duration uses Owner decision.
- Before substantial M8 integration: merchant onboarding/fiscalization eligibility, authentication/webhook/reconciliation sandbox path.
- Before live Pilot: restore fencing and independent deletion state, support window/operator destination, numeric SLO/RPO/RTO and all applicable gates.

## 22. Feature Definition of Done

Where applicable, feature DoD includes domain semantics, authorization/tenant isolation, idempotency/recovery, Audit/Usage/Telemetry, errors, tests, AI evals, UI/Ops visibility and migrations/config docs.

Backend endpoint alone is not `PILOT_READY`.

## 23. Engineering issue template

```text
Goal
Architecture references
MVP/Roadmap references
Domain/schema changes
Application/API commands
UI / Platform Ops
Security / tenant isolation
Reliability / idempotency
Telemetry / usage / cost
Tests / AI Evals
Definition of Done
```

## 24. Post-Pilot → Commercial MVP

```text
Production Pilot
→ M13 Pilot Findings / Regression
→ M14 Repeatable Onboarding
→ M15 SaaS Billing
→ M16 Commercial Hardening
→ Commercial MVP
```

**M13:** review 20–50 conversation calibration, corrections, escalations, failures, UX and economics; create fixes/regression cases.

**M14:** automate only onboarding patterns proven repetitive; preserve concierge fallback.

**M15:** wider paid Workspace billing: hosted checkout, Subscription, PaymentMethodReference, Invoice/webhook, Grace/Limited.

**M16:** make deployment/support/onboarding/privacy/unit economics/usage/billing repeatable for multiple paying Businesses without code forks.

Stage-27 expansion starts only after Commercial MVP readiness, not merely because Pilot code exists.

## 25. Key target checkpoints

### Target 1
```text
Owner login + Telegram inbound + correct Workspace Inbox + manual Owner reply
```

### Target 2
```text
Tattoo configuration + image + AI structured intake + verified Knowledge/Portfolio
```

### Target 3
```text
AI → Quote → Hold
```

### Primary product milestone
```text
Telegram → AI → Quote → Hold → Payment → Appointment
```

### Pilot RC
The primary path remains correct under duplicate delivery, concurrent slot selection, Hold/payment race, provider timeout, process restart, prompt injection, Human takeover and stale AI output.

## 26. Intentionally not decided here

- backend/frontend framework/package tooling;
- exact calendar estimates/team assignments;
- exact ticket sizing;
- exact provider commands completing Stage-25 runbooks;
- actual first Tattoo master onboarding inputs/legal profile inside RU;
- final pilot-calibrated non-critical AI thresholds.


## Production handoff

After M12/Pilot RC, production deployment/cutover/rollback/restore procedures are canonical in `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`.

## Stage-27 Expansion Gate

After Commercial RU Tattoo, new Business/industry/channel/market capabilities enter the roadmap only after repeatability evidence and the Stage-27 Product/Architecture/Security/Reliability/Ops/Test/Eval/Economics/Rollback gate. The default sequence is more RU Tattoo Businesses → studio/multi-provider → second slot-based IndustryPack → additional RU channels → rich media → first foreign market.
