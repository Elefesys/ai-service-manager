# AI Service Manager — Open Questions Register

**Baseline:** v0.28  
**Дата:** 2026-09-09

Статусы:
- **OPEN** — решение ещё не принято.
- **DEFERRED** — сознательно отложено до указанного этапа.
- **RESOLVED** — решение принято и должно быть отражено в Spec/ADR.
- **REVISED** — прежний ответ заменён новым.

---

# Stage 7 — AI Architecture

## OPEN-001 — Основная conversational model
**Status:** REVISED — v0.28

Two AI branches and profile routing accepted (ADR-259–261); initial EVAL_ONLY shortlist in Spec §7.22. Production exact mapping remains OPEN-074; no universal model brand.

## OPEN-002 — Model routing
**Status:** RESOLVED / v0.28

AIProviderBranch + AIRoutingRevision + ModelProfile with independent region/data/execution checks. Config-only switching, pinned AIRun, no implicit cross-branch fallback; Spec §7.21.

## OPEN-003 — Structured AI output contract
**Status:** RESOLVED IN PRINCIPLE / FIELD CONTRACTS OPEN-007

Versioned machine-readable schemas accepted in ADR-047. Exact per-command fields must be specified before the corresponding M4–M8 feature; they are not claimed already resolved.

## OPEN-004 — AI context budgets
**Status:** RESOLVED in principle at Stage 7

Budgets are profile-specific and token-budget based. Exact numeric thresholds are deferred to Stage 22 eval/tuning, not architectural design.

## OPEN-005 — AI Run persistence
**Status:** RESOLVED IN PRINCIPLE

AIRun/AIProviderCall/ToolTrace plus branch/routing revision, decisions/evidence/usage. Restricted prompt capture and retention governed by Spec §17; exact durations remain launch configuration.

# Stage 8 — Agent / Tools / Autonomy

## OPEN-006 — Agent architecture
**Status:** RESOLVED

One ConversationAgent; application services as tools, separate onboarding lifecycle. ADR-056.

## OPEN-007 — Tool schemas
**Status:** OPEN — BEFORE EACH M4–M8 CAPABILITY

Typed versioned narrow interfaces accepted. Specify fields, evidence, Client/object authorization, preconditions, business-intent key, result/error and replay behavior per command before implementation. No arbitrary SQL/HTTP/code.

## OPEN-008 — Autonomy policy
**Status:** RESOLVED

AUTO / REQUIRE_CONFIRMATION / ESCALATE / DISABLED hierarchy, ADR-059. Business values remain approved onboarding configuration.

## OPEN-009 — Confidence/evidence policy
**Status:** RESOLVED

ADR-061: confidence is not authorization; authoritative evidence/preconditions required. Duration candidate alone cannot book (§11.11).

# Stage 9 — Industry Modules / Workflows

## OPEN-010 — Формат Workflow Definition
**Status:** RESOLVED GRAPH / SERIALIZATION BEFORE M5

Directed graph/revisions/guards and domain-truth separation accepted. Exact code/config serialization is implementation choice before minimal M5 runtime; no universal visual DSL required.

## OPEN-011 — Industry defaults and overrides
**Status:** RESOLVED

Universal Core → IndustryPack → Business/Service overrides → validation/published revisions; ADR-065–070.

## OPEN-012 — Sensitive industry policies
**Status:** RESOLVED BOUNDARY / BUSINESS CONFIG BEFORE M5

Pilot medical/minor/unsupported flows disabled or safe handoff; exact Tattoo trigger examples and master-supported styles need approved rules/evals. Do not infer medical suitability.

# Onboarding implementation details

## OPEN-013 — MVP import formats
**Status:** OPEN — BEFORE M5

Choose minimum actual master source format(s) for concierge import, including portfolio and DurationCase labels; do not build speculative importers. Needs sample export/files from the first master.

## OPEN-014 — Exact onboarding UI
**Status:** RESOLVED CONCIERGE / DETAIL M5

Concierge with owner review/preview accepted. Implement minimum review/diff/publish surface at M5; self-service depth remains OPEN-066.

# Stage 11 — Pricing

## OPEN-016 — Pricing model
**Status:** RESOLVED — v0.28

Owner-selectable FIXED / bounded CONFIGURED_FORMULA / OWNER_QUOTE; indicative range preserved but not silently exact. First-master values/formula remain OPEN-079.

## OPEN-017 — AI role in pricing
**Status:** RESOLVED

AI extracts inputs or asks Owner; deterministic PricingEngine/structured Owner decision supplies amount. QuoteAcceptance precedes payment obligation. ADR-262/263.

# Stage 12 — Scheduling / Resources

## OPEN-018 — Rescheduling representation
**Status:** RESOLVED / DB VALIDATION M7

Old Appointment CANCELLED + new CONFIRMED, atomic occupancy replacement supporting self-overlap; no competitor exclusion. Spec §12.9.1 / OPEN-055.

## OPEN-019 — Availability model
**Status:** RESOLVED / CONFIG BEFORE M7

Rules/overrides/blocks/allocations + approved duration and buffers; same-resource conflict protocol for CalendarBlock. Actual master hours/buffers remain OPEN-080.

## OPEN-020 — Multi-session constraints
**Status:** PILOT NEXT-SESSION SCOPE / MASTER INPUT OPEN

Pilot books only next approved ServiceSession. Session limits/count/interval rules require Owner; automatic whole-course planning deferred. OPEN-081.

## OPEN-021 — ReservationHold concurrency
**Status:** RESOLVED IN PRINCIPLE / IMPLEMENTATION OPEN-055

DB-level overlap protection, atomic conversion/replacement, expired occupancy cleanup with trusted time; concurrent tests M7.

# Stage 13 — Client → Business Payments

## OPEN-022 — Payment provider
**Status:** RESOLVED CANDIDATE — SEE OPEN-056

YooKassa preferred for RU subject to actual merchant eligibility. Provider-specific authenticity contract, not universal signed-webhook assumption; test before M8 live cutover.

## OPEN-023 — PaymentRequest target model
**Status:** RESOLVED LOGICAL / DDL M6–M8

Typed references to Order, optional Session, QuoteAcceptance/Quote and PaymentTermsRevision; Hold linkage separate. See Spec §§11.10/13.12. DDL and constraint tests before M8.

## OPEN-024 — Refund permissions
**Status:** RESOLVED

Owner-authorized refund; no autonomous Client-Agent refund. Cumulative pending/success refunds cannot exceed refundable balance; tests M8.

# Stage 14 — Automations / Notifications

## OPEN-025 — Notification transports
**Status:** RESOLVED PILOT / DELIVERY EVIDENCE M2–M9

Telegram first; route/window limitations produce visible owner task. No customer SMS/email fallback in Pilot. Internal operator/owner destination remains OPEN-073/082.

## OPEN-026 — Follow-up policy
**Status:** RESOLVED GUARDS / BUSINESS VALUES OPEN-082

Bounded, persistent, relevance/quiet-hours/frequency/late policy; owner wait lifecycle explicit. Exact counts/times need master/support agreement. Marketing/reactivation excluded.

## OPEN-027 — Waitlist
**Status:** DEFERRED — POST-PILOT PRODUCT EVIDENCE

No Pilot requirement. Define priority/expiry/offer behavior only if measured cancellation/demand warrants it.

# Stages 15–18 — Resolved architecture questions

## OPEN-028 — Subscription model
**Status:** RESOLVED  
**Resolution:** Workspace billing unit; SaaSPlanRevision + Entitlements; Subscription + separate WorkspaceServiceMode; exact commercial plan prices deferred to Stage 23/real unit economics.

## OPEN-029 — Usage metering
**Status:** RESOLVED IN PRINCIPLE  
**Resolution:** immutable UsageEvent ledger + rebuildable UsageAggregate; observed provider usage/cost separated from billable meters. Exact customer-facing commercial meters remain Stage 23.

## OPEN-030 — Visual generation budgets
**Status:** RESOLVED  
**Resolution:** expensive hard-quota operations use QuotaService + persistent QuotaReservation; text AI uses soft continuity budget in MVP.

## OPEN-031 — Master UI surface
**Status:** RESOLVED  
**Resolution:** responsive web `Business Console`, exception-first Action Center/Inbox/Calendar/Approvals; native mobile apps are not MVP prerequisite.

## OPEN-032 — Platform support access
**Status:** RESOLVED  
**Resolution:** explicit `SupportAccessGrant`, scope/TTL/reason/audit constrained, no tenant membership or silent impersonation; emergency break-glass is a separate restricted path.

## OPEN-033 — Data retention
**Status:** RESOLVED IN PRINCIPLE  
**Resolution:** per-data-class RetentionPolicy + PrivacyRequest/Delete workflow covering canonical/derived/files/backups. Exact retention durations depend on production market/legal/business needs.

## OPEN-034 — AI provider processing consent
**Status:** RESOLVED IN PRINCIPLE  
**Resolution:** architecture supports PrivacyNoticeRevision/ConsentRecord/purpose tracking; consent is not hardcoded as the only legal basis. Exact notice/legal basis must be fixed for the launch jurisdiction.

## OPEN-035 — PII minimization / redaction
**Status:** RESOLVED  
**Resolution:** minimum necessary AI context, sanitized learning/eval examples, opaque analytics IDs, redacted logs, restricted short-lived debug prompt capture.

## OPEN-036 — Secret management
**Status:** RESOLVED DEFAULT / PROVISION M0–M12

Secret Manager refs and rotation accepted; Yandex Lockbox preferred under RU_PILOT_V1. Exact IAM/secrets provisioned per environment.

## OPEN-037 — Queue technology
**Status:** RESOLVED FOR MVP / FUTURE TRIGGER DEFERRED  
**Resolution:** PostgreSQL-backed durable Jobs are MVP default. Dedicated broker is added only when Stage 20/21 evidence shows DB contention/throughput/routing need.

## OPEN-038 — Conversation lock
**Status:** RESOLVED IN PRINCIPLE  
**Resolution:** logical serialization + optimistic version/CAS is correctness boundary; Redis/advisory/distributed lock may be optimization. Exact lock mechanism is implementation/infrastructure choice.

## OPEN-039 — Retry / dead-letter policy
**Status:** RESOLVED  
**Resolution:** retryability taxonomy, bounded exponential backoff+jitter, UNKNOWN external result semantics, DLQ/Platform Ops replay, idempotency required.

## OPEN-040 — Disaster recovery targets
**Status:** PARTIALLY RESOLVED / EVIDENCE BEFORE PILOT

Managed PITR/restore-to-new-instance/reconciliation accepted; planning RPO ≤5 min/RTO ≤4 h subject to measured topology. Contract/support commitments and newer deletion/fencing evidence remain OPEN-071/072/084.

# Stage 19 — Infrastructure

## OPEN-041 — Initial hosting provider
**Status:** RESOLVED RU DEFAULT / SKU OPEN

Yandex-preferred RU_PILOT_V1 accepted; actual SKU/zone/topology and recovery evidence before Pilot. See OPEN-070/071.

## OPEN-042 — Object Storage provider
**Status:** RESOLVED RU DEFAULT / LIFECYCLE OPEN

Private Yandex Object Storage through S3 abstraction preferred. Retention/versioning/recovery selected before Pilot; deletion reconciliation OPEN-084.

## OPEN-043 — Deployment topology
**Status:** RESOLVED  
**Resolution:** modular-monolith Docker API/Worker/Scheduler on disposable compute; PostgreSQL and Object Storage externalized; one production region for MVP.

---

# Stage 20 — Observability / Cost

## OPEN-044 — Logs / metrics / traces stack
**Status:** RESOLVED DEFAULT / ALERT ROUTING OPEN

OpenTelemetry with RU-compatible backend, Monium candidate; exact operator destination OPEN-073.

## OPEN-045 — AI cost attribution
**Status:** RESOLVED  
**Resolution:** local provider-call/UsageEvent attribution by Workspace/feature/model/task/time plus asynchronous reconciliation with provider financial costs.

---

# Stage 21 — Scaling

## OPEN-046 — DB scaling/sharding threshold
**Status:** RESOLVED IN PRINCIPLE / NUMERIC TRIGGERS DEFERRED  
**Resolution:** optimize/index/pool/vertical/offload/partition before cells/shards. Exact numeric thresholds come from Stage 20 production metrics.

## OPEN-047 — Vector scaling threshold
**Status:** RESOLVED IN PRINCIPLE / NUMERIC TRIGGERS DEFERRED  
**Resolution:** pgvector remains default through filtering/tuning/HNSW; dedicated vector infra only after measured latency/scale/OLTP-isolation need.

---

# Stage 22 — Testing / Evals

## OPEN-048 — AI eval suite
**Status:** RESOLVED IN PRINCIPLE  
**Resolution:** versioned EvalSuite/EvalCase/EvalRun with tool/domain/safety/RAG/injection/multi-turn/staleness/cost/latency suites and hard critical gates. Exact first-vertical corpus/thresholds remain Stage 23/24.

## OPEN-049 — Tenant isolation matrix
**Status:** RESOLVED  
**Resolution:** dedicated executable cross-tenant suite covers API/repositories/RLS/files/cache/RAG/jobs/tools/support and new tenant tables/paths.

---

# Stage 23 / 26 — MVP and First Production Client

## OPEN-050 — Первая вертикаль / клиент
**Status:** RESOLVED TATTOO MASTER / ONBOARDING INPUTS OPEN

User confirms first client is a tattoo master; Russia/Russian/RUB defaults. Exact identity/contact is not inferred. Deposit fixed; amount and operating/legal data remain OPEN-076/079–082.

## OPEN-051 — MVP feature boundary
**Status:** RESOLVED  
**Resolution:** точный first-release scope/exclusions/Golden Journeys/readiness gates зафиксированы Stage 23 и в `06_MVP_SPEC.md`.

---

# Continuous external verification

## OPEN-052 — Telegram capabilities
**Status:** OPEN / periodic verification

Перед production перепроверить:
- Premium requirement;
- reply window;
- number of connected bots;
- rights;
- региональные/client restrictions.

## OPEN-053 — Current AI provider capabilities
**Status:** OPEN / periodic verification

Перед Stage 7 implementation перепроверить current models, pricing, context limits, image generation/editing и embeddings.


# Post-Stage-14 implementation questions

## OPEN-054 — Exact pricing rule representation
**Status:** BOUNDED FORMULA PILOT / ADVANCED DSL DEFERRED

Owner-supplied formula is supported through allowlisted deterministic templates/validated units/rounding/applicability. Choose minimal representation against actual master formula before M6. Universal executable DSL excluded.

## OPEN-055 — Exact DB overlap implementation for ResourceAllocation
**Status:** RESOLVED IN PRINCIPLE / IMPLEMENTATION DEFERRED  
**Resolve at:** Stage 19/24 database implementation

Architecture requires authoritative DB-level overlap prevention on exclusive ResourceAllocation plus atomic multi-resource acquisition. Exact PostgreSQL exclusion/index/transaction syntax remains implementation-level.

## OPEN-056 — First Client Payment Provider
**Status:** RESOLVED FOR RU PILOT / FALLBACK CONDITIONAL  
**Resolution:** YooKassa is the first RU PaymentProvider candidate using hosted checkout to the Business merchant account. If the actual Business cannot onboard/use it, select another RU-compatible provider behind the same adapter and document ADR.

## OPEN-057 — External calendar provider priority
**Status:** DEFERRED  
**Resolve at:** CORE_POST_MVP planning

Exact Google/other calendar integration priority remains open.

## OPEN-058 — First proactive notification fallback channel
**Status:** RESOLVED FOR MVP  
**Resolution:** дополнительный email/SMS fallback channel не входит в MVP. NotificationRouter/ChannelCapabilities должны честно обрабатывать недоступный Telegram route/window и при необходимости эскалировать/показывать owner-visible route-unavailable state.

## OPEN-059 — Country-specific fiscalization
**Status:** RESOLVED ARCHITECTURALLY / EXACT RU PROFILE OPEN  
**Resolution:** Fiscalization is a separate service/profile/receipt adapter layer and `FISCALIZATION_READY` is a launch gate. Exact NPD/IP/legal-entity provider/manual workflow is determined from the actual first Business and verified professionally before live payments.


# Post-Stage-22 unresolved deployment / MVP-dependent questions

## OPEN-060 — Numeric SLO / alert thresholds
**Status:** OPEN — IMPLEMENTATION BEFORE LIVE PILOT

SLI categories accepted. Set actual uptime/latency/queue-lag thresholds and operator routes using pilot expectations/budget/provider measurements. Architecture Stage 26 is complete; operational values are still release-blocking inputs.

## OPEN-061 — Exact future queue / Redis / vector-search triggers
**Status:** DEFERRED  
**Resolve when measured need occurs

PostgreSQL Jobs, no mandatory Redis, pgvector and PostgreSQL FTS remain defaults. New infrastructure requires Stage 20/21 evidence and ADR.

## OPEN-062 — Eval-suite numeric release thresholds
**Status:** PARTIALLY RESOLVED  
**Resolution:** critical violations remain zero-tolerance and Stage 23 sets ~95% curated non-critical domain/tool correctness as an initial calibration target. Stage 24 assigns concrete evaluator/denominator/repetition implementation to M12; final suite-specific numeric tolerances remain implementation/pilot-calibration details rather than architecture constants.

## OPEN-063 — First production vertical eval corpus
**Status:** RESOLVED IN SCOPE / DATASET BUILD DEFERRED  
**Resolution:** first deep corpus is Tattoo and must cover Golden Journeys A–J plus tool/pricing/scheduling/payment/RAG/injection/takeover/staleness cases. A small synthetic corpus is required before substantial M4–M5 integration; M12 expands/hardens it. Exact case count/content grows during implementation and pilot regression.


## OPEN-064 — Exact first Business language / currency / timezone
**Status:** RESOLVED DEFAULT / TIMEZONE BUSINESS-SPECIFIC  
**Resolution:** RU Pilot defaults to Russian language and RUB. Exact IANA timezone follows the first Business location/configuration inside Russia.

## OPEN-065 — Commercial SaaS plan price
**Status:** DEFERRED — M13–M15 / UNIT ECONOMICS

Pilot may use TRIALING or ACTIVE+COMPED with normal Entitlements. Determine price/included units from measured pilot economics before commercial paid onboarding.

## OPEN-066 — Commercial MVP self-service onboarding depth
**Status:** DEFERRED / ROADMAP POSITION RESOLVED  
**Resolution:** Stage 24 places repeatable onboarding in M14 after pilot findings. Exact minimum owner self-service depth remains evidence-driven and is finalized from pilot support burden before broader Commercial MVP.


## OPEN-067 — Initial implementation stack
**Status:** DEFERRED TO IMPLEMENTATION START

Stage 24 locks required capabilities but not backend/frontend framework, ORM/query library, migration tooling or test framework. Selection should occur before M0/M1 coding and satisfy PostgreSQL/RLS/transactions/typed-schema/jobs/OpenTelemetry/test requirements.

## OPEN-068 — Calendar estimates / team capacity
**Status:** DEFERRED

Canonical roadmap is dependency-based. Calendar estimates depend on chosen stack, actual developer capacity, provider friction and ticket decomposition.

## OPEN-069 — Exact engineering ticket decomposition
**Status:** DEFERRED TO IMPLEMENTATION

`07_DEVELOPMENT_ROADMAP.md` defines milestone-level sequence/DoD. Concrete epics/issues are generated from milestones when development begins.

# Post-Stage-25 production deployment questions

## OPEN-070 — Concrete production cloud / region
**Status:** RESOLVED AS RU PILOT DEFAULT / FINAL PROCUREMENT CONDITIONAL

**Resolution:** `RU_PILOT_V1` prefers Yandex Cloud in Russia: Docker compute, Managed PostgreSQL+pgvector, Object Storage, Lockbox, Container Registry and RU-managed observability. Final SKU/zone/topology are implementation/procurement choices, not domain contracts.

## OPEN-071 — Pilot RPO / RTO / operational SLO values
**Status:** PARTIALLY RESOLVED / CONTRACTUAL VALUES OPEN

**Resolution:** initial internal planning targets are PostgreSQL RPO ≤5 minutes and RTO ≤4 hours, subject to actual topology/restore verification. Contractual SLA/support values remain open until the first Business agreement.

## OPEN-072 — Pilot support/on-call expectation
**Status:** OPEN — BEFORE LIVE PILOT

Agree real support channel/window and escalation/incident communication; no invented 24/7 SLA. Needed from user/first master. Tie owner-wait defaults to OPEN-082.

## OPEN-073 — Concrete production observability/alert routing
**Status:** PARTIALLY RESOLVED

**Resolution:** RU Pilot uses OpenTelemetry with an RU-compatible managed backend; Monium is the first Yandex-stack candidate. Exact operator notification destination is chosen during implementation/cutover.

# Post-Stage-27 implementation / market questions

## OPEN-074 — Exact production AI mapping for both branches
**Status:** OPEN — BEFORE M4–M5 LIVE ROUTING

Architecture: PolzaAI-preferred RU_AGGREGATOR and DIRECT_PROVIDER accepted. Spec §7.22 gives EVAL_ONLY task shortlist. Need current catalog API IDs/capabilities/prices and synthetic Tattoo task benchmark with full cost, p50/p95 latency, failures and fallback tests. Choose one aggregator and one direct adapter; GPTunnel is comparison, not mandatory third implementation. Embedding candidate needs Russian retrieval/effect of branch-switch validation. Do not label candidates APPROVED without evidence.

## OPEN-075 — Aggregator/direct data and provider eligibility
**Status:** OPEN — BEFORE REAL CLIENT DATA ON EACH ROUTE

For PolzaAI/GPTunnel or direct API, record agreement/upstream route, actual processing/storage/retention, model identity/fallback controls and permitted data classes. Branch preference does not prove this. Needs actual provider terms/account/contract evidence; pricing-only comparison cannot close it. Preserve no-unverified-VPN rule.

## OPEN-076 — Exact first Business legal/tax/fiscalization profile
**Status:** OPEN — PAYMENT ACTIVATION BLOCKER

Determine NPD/IP/legal-entity status, receipt responsibility and provider/manual fiscalization path for the actual first Business before real payment activation.

## OPEN-077 — Second RU channel priority
**Status:** DEFERRED UNTIL PRODUCTION DATA

MAX and VK are expansion candidates. Select order from actual channel demand among target Businesses/Clients and integration maturity.

## OPEN-078 — First foreign market
**Status:** DEFERRED UNTIL MATURE RU COMMERCIAL PRODUCT

Select one foreign market only after repeatable RU operation; create its MarketProfile/DataResidencyPolicy/RegionalProviderBundle and legal/payment/fiscal/eval package.

# v0.28 — Remaining owner inputs and implementation evidence

## OPEN-079 — First-master price and payment configuration
**Status:** OPEN — OWNER INPUT BEFORE M6/M8

Known: first master is Tattoo; deposit is FIXED_DEPOSIT independent of ordinary scale. Need exact RUB amount, FIXED/CONFIGURED_FORMULA/OWNER_QUOTE selection, actual price formula/table and allowed inputs, whether a range can be agreed provisionally, handling if fixed deposit exceeds total, cancellation/refund/no-show/reschedule policy and deposit transfer between sessions. No numeric value invented. Price and PaymentTerms choices are independent. Supply 3–5 example calculations if formula mode is desired.

## OPEN-080 — First-master duration authority and examples
**Status:** OPEN — OWNER CALIBRATION BEFORE AUTO DURATION

Provide representative owner-labelled works: image/reference, size/unit, placement/style/detail/fill, active work minutes, full occupied slot, setup/cleanup/break treatment, number of sessions and reasons. Suggested initial collection 10–20 varied cases is a practical starting point, not a statistical release gate. Prefer actual measured times; label recalled estimates. Until approved rule is calibrated use OWNER_DEFINED, with AI draft/case comparisons. Need owner working hours and buffer settings too. See Spec §11.11.

## OPEN-081 — Session limits and duration calibration
**Status:** OPEN — MASTER INPUT; FULL AUTO MULTI-SESSION DEFERRED

Master defines maximum session length, how work is split and which cases require manual assessment, plus any approved interval constraints. No AI medical/healing recommendation. Compare predictions to actual occupied time, track underestimates/overruns separately and choose acceptable reserve/threshold with master before publishing a duration rule. Pilot books only next approved session. No universal tattoo time formula or per-master fine-tuning is accepted.

## OPEN-082 — Owner wait / follow-up business values
**Status:** OPEN — BEFORE M9/LIVE PILOT

Need owner response window/contact, bounded reminder counts/intervals, quiet hours, approval expiry and client-wait wording. When channel reply window is closed, create owner task; no claim Console send bypasses Telegram. Exact values need user/master agreement; lifecycle/guards are already accepted (§14.11).

## OPEN-083 — HUMAN-mode transactional notification exceptions
**Status:** OPEN OPTIONAL OVERRIDE / SAFE DEFAULT IMPLEMENTABLE

Default: no new AI mutations/conversational sends; Client follow-ups suppressed; transactional customer notices become owner-review tasks during HUMAN. Payment reconciliation/expiry/internal notices continue. Master may approve specific deterministic transactional exceptions later; no blanket automatic resumption. In-flight external effect semantics remain Spec §5.12.1.

## OPEN-084 — Restore fencing and newer deletion state
**Status:** OPEN — ENGINEERING RELEASE GATE M12

Choose/test durable deletion journal/checkpoint surviving rollback, restricted retention, old-runtime/credential/network fencing and provider reconciliation evidence. Restore drill must include external payment/send and deletion after backup time. Cannot be closed by documentation alone. If newer deletion state is unavailable, quarantine affected processing. See Spec §18.15.1 and Runbook §12.

## OPEN-085 — Concrete provider and performance verification
**Status:** OPEN — ENGINEERING/ACCOUNT EVIDENCE

Confirm API credentials/limits, merchant acceptance, Telegram native owner message events/reply rights, exact model/embedding IDs, gateway fallback controls and observable actual upstream. Synthetic API benchmarks require account access; never send customer images for comparison before data eligibility. This pass did not create accounts, pay providers or run live benchmark calls.
