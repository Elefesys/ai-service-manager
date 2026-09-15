# AI Service Manager — Architecture Changelog

## v0.28 — 2026-09-09

**Status:** Audit pass 1 and user-approved revisions; pre-implementation. Architecture Freeze v1.0 remains pending; no live integrations or performance benchmarks completed in this pass.

### User decisions
- First client explicitly confirmed as Tattoo master.
- Two switchable AI branches: PolzaAI-preferred RU_AGGREGATOR (GPTunnel comparison) and DIRECT_PROVIDER official APIs; task-specific cost/quality selection. Replaces Cloud.ru-first/local-default preference.
- Owner chooses fixed price, bounded supplied formula or Owner Quote; price and payment terms independent.
- Payment modes NONE/fixed/percentage/full; first master fixed deposit regardless of ordinary scale, amount still open.
- Duration learning question addressed as owner-labelled cases and reviewed rule/Owner authority; no invented duration formula or automatic model training accepted.

### Audit corrections / clarified existing invariants
- Added QuoteAcceptance and explicit Order/Session/payment bindings, no-deposit path and exact percentage base requirement.
- Clarified same-Workspace Client authorization, stale worker/takeover command guards, self-overlap reschedule/CalendarBlock conflicts, cross-AIRun idempotency, duplicate real money and refund limits.
- Corrected generic signed-webhook assumption to provider-specific authenticity; YooKassa official reference added.
- Fiscalization gate propagated into checklists/cutover; roadmap includes local pilot Entitlements, workflow, approval, Order/Session and fiscalization.
- Recovery includes old-runtime fencing, newer deletion journal and verify-before-replay; actual engineering evidence remains open.
- Added owner-wait/route-unavailable behavior and fuller owner-workload metrics.
- Synchronized Overview, ADR supersession, Glossary aliases, scope horizons and stale Open Questions. Historical changelog/ADR text preserved as history with explicit supersession.
- ADR-259–274 added. OPEN-079–085 identify remaining owner values/calibration/provider/recovery evidence; candidate models are not falsely marked approved.

### Validation and remaining work
- Documentation consistency checked locally; no application code, provider account or production configuration was deployed.
- Need master pricing/deposit/cancellation/schedule/duration inputs, actual provider contract/account/benchmark evidence, exact operational limits and tested recovery before corresponding milestones/live gates.

---


## v0.27 — 2026-09-09

**Status:** Canonical baseline after Stages 26–27 and RU AI-provider correction. Architecture roadmap 0–27 is complete; implementation has not started.

### Stage 26 — RU-first Production
- Primary market/data region fixed as Russia; Russian/RUB defaults.
- Added MarketProfile, DataResidencyPolicy, RegionalProviderBundle, Home Data Region and ProviderExecutionClass.
- Revised Stage 7: removed universal `OpenAI first` and provider-branded Terra/Luna/Sol mapping from canonical architecture.
- Direct OpenAI/Gemini through VPN/proxy classified UNVERIFIED_PROXY and forbidden for RU production.
- Added dual RU AI lanes: RU_LOCAL_HOSTED + CONTRACTED_EXTERNAL.
- Cloud.ru Foundation Models selected as first enterprise gateway candidate; Yandex/GigaChat remain benchmark/adapters.
- External-premium GPT/Claude/Gemini routing requires explicit contract/upstream/data/legal eligibility and minimized/sanitized context.
- RU_PILOT_V1 infrastructure prefers Yandex Cloud through existing abstractions.
- YooKassa selected as first Client PaymentProvider candidate.
- Added separate FiscalizationService/Profile/Receipt/Adapter and FISCALIZATION_READY gate.
- Pilot activation phased from manual Telegram to AI, scheduling, payment and automations.

### Stage 27 — Expansion
- Repeatable RU Tattoo precedes broad expansion.
- Commercial RU Tattoo and small studios/multi-provider precede second industry.
- Slot-based Beauty recommended second vertical to test another WorkflowArchetype.
- MAX/VK are RU channel candidates; order is demand-driven.
- Voice/image generation added only after Pilot evidence and appropriate data policy.
- Added maturity lifecycles for Industry/Channel/AI provider/model capabilities.
- Foreign expansion uses one MarketProfile/DataRegion/ProviderBundle at a time.
- True multi-region uses Workspace Home Region + regional Cells; no cross-region transactional core.
- Expansion requires product/security/reliability/ops/eval/economics/rollback gates.

### Corrections
- `text-embedding-3-small` is no longer canonical RU MVP embedding default.
- OpenAI remains a future-region/approved-external adapter, not direct RU production provider.
- Existing deployment/runbook documents updated for RU provider bundle and fiscalization outage/obligation handling.

### Documentation
- Baseline advanced v0.25 → v0.27.
- No new canonical file added: existing `00–08` files are sufficient for Stages 26–27; regional/expansion policy is architecture-level and cross-cuts MVP/Roadmap/Runbooks.
- ADR log extended through ADR-258.
- Open Questions updated with concrete RU provider defaults and remaining release-gate decisions.

---

## v0.25 — 2026-09-08

**Status:** Canonical baseline after accepting Stage 25 Production Deployment / Runbooks. Stage 26 First Production Client remains intentionally undesigned.

### Stage 25 — Production Deployment / Runbooks
- Production deployment defined as reproducible/controlled rather than manual server operation.
- Immutable container artifacts + source/CI provenance and `ReleaseManifest` locked.
- Application / AI Configuration / Business Configuration release axes separated.
- Separate privileged migration identity and Expand→Migrate→Contract deployment model reinforced.
- Safe readiness/smoke/drain/observation workflow defined.
- Application rollback separated from DB/data restore.
- Narrow operational kill switches and Workspace AI pause required.
- Managed backup/PITR plus actual tested restore made Pilot gate.
- Restore-to-new-instance + RLS/invariant/privacy/provider reconciliation defined.
- Numerical RPO/RTO/SLO required before Pilot but deferred to Stage 26 concrete provider/business.
- SEV-1/2/3 incident handling and version-controlled runbooks.
- First-Business cutover made progressive: manual channel → AI → scheduling → payment → automation.
- Continuous integration + controlled production deployment selected for first AI/payment Pilot.
- Significant incidents feed tests/evals/constraints/alerts/runbook improvements.

### Documentation
- Baseline advanced v0.24 → v0.25.
- Added canonical `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`.
- Architecture Spec now includes locked Stage 25.
- ADR log extended through ADR-235.
- Open Questions distinguish resolved deployment semantics from Stage-26 provider/SLA/support choices.
- Stage 26 is not designed in this baseline.

### Still deferred
- concrete first Production Business;
- cloud/PaaS/region/Object Storage/observability/payment vendors;
- numerical Pilot RPO/RTO/SLO and alert thresholds;
- actual pilot support/on-call agreement;
- Stage 26 first-client onboarding/cutover specifics;
- Stage 27 expansion decisions.

---

## v0.24 — 2026-09-08

**Status:** Canonical baseline after accepting Stage 24 Development Roadmap. Stage 25 Production Deployment / Runbooks remains intentionally undesigned.

### Stage 24 — Development Roadmap
- Dependency-based roadmap selected instead of calendar-first estimates.
- Vertical-slice implementation selected instead of building all layers before integration.
- Production Pilot is the first implementation objective; Commercial MVP follows pilot evidence.
- Initial monorepo/modular-monolith implementation shape locked.
- M0–M12 Pilot sequence fixed from engineering foundation through pinned Pilot RC.
- First tangible coding target fixed as secure Telegram inbound/manual Owner reply, not prompt engineering.
- AI enters read/query-only before mutation tools.
- Scheduling deterministic correctness precedes Agent scheduling tools.
- Client Payments follow stable Hold/Appointment semantics.
- Telegram→AI→Quote→Hold→Payment→Appointment fixed as primary product development milestone.
- Feature Freeze and pinned Pilot Release Candidate introduced.
- Schema/entities are implemented capability-by-capability without temporary incorrect domain abstractions.
- Feature DoD includes security/tenant/reliability/telemetry/tests/evals/UI/Ops where relevant.
- M13–M16 Commercial path fixed: Pilot Findings → Repeatable Onboarding → SaaS Billing → Commercial Hardening.
- Stage-23 exclusions remain outside Pilot roadmap unless evidence/ADR changes scope.

### Documentation
- Baseline advanced v0.23 → v0.24.
- Added canonical `07_DEVELOPMENT_ROADMAP.md`.
- Architecture Spec now contains locked Stage 24 roadmap principles.
- ADR log extended through ADR-212.
- Glossary extended with Vertical Slice, Pilot RC, Feature Freeze and implementation-completeness terms.
- Open Questions now separate roadmap decisions from implementation-stack/calendar/ticket details.
- `06_MVP_SPEC.md` remains source of truth for WHAT the MVP contains; `07_DEVELOPMENT_ROADMAP.md` is source of truth for implementation order.
- Stage 25 deployment/runbooks;
- exact first Business/jurisdiction;
- final pilot-calibrated non-critical EvalSuite thresholds.

### Still deferred
- exact programming languages/frameworks/tooling;
- concrete engineering tickets and calendar estimates;
- concrete cloud/payment/observability providers;
- Stage 25 deployment/runbooks;
- exact first Business/jurisdiction;
- final pilot-calibrated non-critical AI thresholds.

---

## v0.23 — 2026-09-08

**Status:** Canonical baseline after accepting Stage 23 MVP Scope + Acceptance Criteria. Development sequencing is Stage 24.

### Stage 23 — MVP Scope
- First production vertical fixed as Tattoo.
- Primary autonomous flow fixed as New Tattoo Request.
- Initial tenant shape narrowed to one Business/Owner/Location/provider Resource/Telegram connection.
- Text + image, Vision, Portfolio and Knowledge/RAG included.
- AI image generation, extra channels, voice/video and advanced scheduling excluded.
- Pricing limited to deterministic exact/range/Owner Quote; custom AI authoritative price prohibited.
- One-resource Scheduling + Hold + deposit/payment + Appointment golden path required.
- Refund/discount/custom exceptions remain Owner-controlled.
- Human takeover/resume made hard MVP requirement.
- Platform Ops included in first production pilot.
- Production Pilot and Commercial MVP separated.
- Pilot may use TRIAL/COMPED subscription via normal EntitlementService.
- Action-specific conservative MVP autonomy contract locked.
- Golden Journeys A–J locked.
- Independent Domain/AI/Security/Reliability/BusinessConfig/Ops/Privacy readiness gates locked.
- Zero-tolerance critical release gate confirmed.
- Pilot calibration window and initial autonomy/quality targets recorded as non-contractual calibration targets.

### Documentation
- Baseline advanced v0.22 → v0.23.
- Added canonical `06_MVP_SPEC.md`.
- `00_PROJECT_OVERVIEW.md` roadmap advanced through Stage 23.
- ADR log extended through ADR-190.
- Open Questions updated: Tattoo/MVP boundary resolved; actual first Business/provider/jurisdiction/precise eval thresholds remain appropriately deferred.
- Stage 24 development sequence intentionally not designed in this baseline.

### Still deferred
- Development sequencing/epics/dependencies (Stage 24).
- Concrete production provider/jurisdiction/client choices (Stages 25–26).
- Exact non-critical EvalSuite thresholds/corpus implementation.
- Exact commercial SaaS pricing and product units.
- Exact amount of self-service onboarding required for broader Commercial MVP.

---

## v0.22 — 2026-09-07

**Status:** Canonical baseline after accepting stages 19–22. Stage 23 MVP Scope remains intentionally undesigned.

### Stage 19 — Infrastructure
- `Boring Managed Core + Simple Stateless Compute`.
- Modular monolith retained; Docker API/Worker/Scheduler.
- Managed PostgreSQL preferred; private S3-compatible Object Storage authoritative for binaries.
- PostgreSQL Jobs selected for MVP; Redis/Kafka/Kubernetes not required.
- LOCAL/STAGING/PRODUCTION isolation, immutable CI deployment and one production region locked.

### Stage 20 — Observability / Cost
- Metrics/Logs/Traces separated from Audit/Security/Usage.
- OpenTelemetry-compatible instrumentation.
- Correlation/causation, queue lag and user-journey latency made first-class.
- AI cost attribution/reconciliation architecture and CostGuard added.
- Product analytics defined around domain outcomes.
- SLI/SLO and actionable alert philosophy added.

### Stage 21 — Scaling
- Scaling made metric-driven.
- Optimize/vertical/horizontal/workload-pool ladder precedes specialized infra/cells.
- Noisy-neighbor protection formalized.
- PostgreSQL Jobs/pgvector/PostgreSQL FTS remain defaults until measured triggers.
- Workspace defined as future cell/shard placement unit.
- Microservice extraction requires concrete trigger.
- Backpressure/chunked bulk processing formalized.

### Stage 22 — Testing / Evals
- Software testing and AI Evals split into separate quality systems.
- Real PostgreSQL/RLS/concurrency/idempotency/recovery testing locked.
- EvalSuite/EvalCase/EvalRun/ProductionBaseline concepts introduced.
- Critical money/payment/scheduling/security/tool failures are hard release gates.
- RAG/injection/human-takeover/staleness/tool evals formalized.
- Production failures become sanitized regression cases where possible.
- Model/prompt/tool/schema/KnowledgeBuild changes require versioned release gates.
- Continuous learning explicitly does not mean live self-modification.

### Documentation
- Baseline advanced from v0.18 to v0.22.
- Roadmap updated through Stage 22; Stage 23 intentionally untouched.
- No new canonical file added; current six-file set remains sufficient before MVP scope freeze.
- Infrastructure/observability/scaling/eval open questions updated to resolved-in-principle or deployment/MVP-dependent status.

### Still deferred
- Stage 23 MVP scope and acceptance criteria.
- Concrete cloud/hosting/Object Storage/observability vendors.
- Exact numeric SLO/RPO/RTO/alert targets.
- Numeric triggers for optional Redis/broker/vector/search additions.
- Exact AI eval pass-rate/cost/latency thresholds for first vertical.

---

## v0.18 — 2026-09-03

**Status:** Canonical baseline after accepting stages 15–18. Stage 19 Infrastructure remains intentionally undesigned.

### Stage 15 — SaaS Billing / Usage / Quotas
- Workspace established as SaaS billing unit.
- WorkspaceBillingAccount, SaaSPlanRevision, Entitlements, Subscription, BillingInvoice projection.
- Provider-hosted/tokenized owner payment methods; no PAN/CVC storage.
- Billing state separated from WorkspaceServiceMode for grace/limited/suspended behavior.
- Immutable UsageEvent ledger and rebuildable UsageAggregate.
- Observed usage/provider cost separated from billable meters.
- QuotaService + QuotaReservation for expensive hard-quota operations.
- SaaS billing provider removed from critical path of Client runtime.

### Stage 16 — Business Console / Platform Operations
- `Master UI` renamed canonically to `Business Console`.
- Separate Business Console and Platform Operations security surfaces.
- Exception-first Action Center/Inbox/Calendar/Approvals/Escalations.
- Decision Summary/evidence instead of chain-of-thought exposure.
- Same domain services for UI/AI/support; no direct DB mutation/bypass.
- SupportAccessGrant introduced as TTL/scope/reason/audited support boundary.
- Silent support impersonation rejected.
- Responsive web selected for MVP; native apps deferred.

### Stage 17 — Security / Privacy / Compliance
- Common Data Classification and `AIDataPolicy`.
- Minimum-necessary AI context and external-provider trust boundary.
- Client/RAG/files treated as untrusted content; prompt injection considered expected.
- Private Object Storage + signed URLs + hostile-upload handling.
- Secret Manager/environment isolation/no routine production data on developer PCs.
- Secure session architecture and mandatory Platform Ops MFA.
- RetentionPolicy, PrivacyRequest, PrivacyNoticeRevision, SecurityEvent concepts.
- Privacy deletion covers derived data including embeddings.
- Raw prompt/PII logging minimized; debug capture explicit/TTL/audited.
- Incident response/vendor-subprocessor obligations added as production prerequisites.

### Stage 18 — Reliability / Idempotency / Recovery
- At-least-once + idempotency selected instead of distributed exactly-once assumption.
- Durable Inbox-before-acknowledge and transactional Outbox formalized.
- IdempotencyRecord/request fingerprint for critical side effects.
- Short DB transactions; no external HTTP inside long domain transaction.
- Optimistic version/CAS as stale-state correctness boundary.
- Persistent jobs with lease/reclaim, retry taxonomy, backoff+jitter and DLQ.
- `UNKNOWN` external-result state for ambiguous timeouts; blind side-effect retry rejected.
- Tool/AIRun recovery reuses successful side effects.
- Provider circuit-breaker/degradation and logical workload priorities.
- PostgreSQL confirmed as hard dependency canonical mutable runtime; Redis remains noncanonical.
- Expand→Migrate→Contract deployment pattern.
- Backup + tested restore/reconciliation required; exact numeric RPO/RTO deferred.

### Documentation cleanup
- Project Overview corrected to stages 0–18 and baseline date 2026-09-03.
- OPEN-028 through OPEN-040 updated to resolved/partially resolved status.
- Infrastructure-specific choices (queue product, secret product, hosting, Object Storage, RPO/RTO numbers) remain explicitly deferred to Stage 19.
- No new canonical file was added; existing six-file structure remains sufficient.

### Still deferred
- Stage 19 Infrastructure.
- Concrete hosting/region/managed services.
- Exact queue/worker technology.
- Exact Secret Manager/Object Storage provider.
- Numeric RPO/RTO/SLA targets.
- Stage 20 observability stack.
- Final MVP scope and commercial plans.

---

## v0.14 — 2026-09-02

**Status:** Canonical baseline after accepting stages 11–14.

### Documentation
- Added `Delivery Horizon`: MVP / CORE_POST_MVP / FUTURE_OPTIONAL.
- Architecture status remains separate from implementation horizon.

### Stage 11 — Pricing
- PricingEngine as authoritative price source.
- PricingPlan/PricingRevision.
- PriceCalculation separated from Quote.
- Structured pricing strategies, evidence and immutable calculation snapshots.
- Quote only from authoritative calculation/owner decision.

### Stage 12 — Scheduling
- Dynamic Availability Engine, no persisted free-slot rows.
- SchedulingPolicyRevision/ServiceResourceRequirement.
- AvailabilityOffer, ResourceAllocation, Hold/Appointment conversion.
- DB-level double-booking protection and atomic rescheduling.

### Stage 13 — Client → Business Payments
- PaymentRequest/PaymentSession/PaymentTransaction/Refund separated.
- Hosted/provider-tokenized checkout; platform not wallet/escrow.
- Provider-authoritative evidence; idempotency and reconciliation.
- Late money retained, booking separately revalidated.

### Stage 14 — Automations / Notifications
- Automation Engine separated from Notification layer.
- Persistent automation + relevance + idempotency + late policy.
- NotificationIntent/DeliveryAttempt and routing/category policies.
- Transactional content template-first/hybrid.

### Revised
- PaymentTransaction no longer uses REFUNDED as its own state; Refund is separate.
- PaymentRequest obligation state is separated from collection state.
- Generic Notification is clarified as channel-independent NotificationIntent.
- Delivery planning is now explicitly documented.

### Still deferred
- Stage 15 SaaS billing/usage/quota architecture.
- Exact pricing DSL.
- Exact DB overlap implementation.
- Concrete payment provider.
- First proactive fallback route.
- Country-specific fiscalization/compliance.

---

## v0.10 — 2026-09-02

**Status:** Stage 8–10 architecture accepted.

### Added — Stage 8 Agent / Tools / Autonomy

- `ConversationAgent` as the single primary customer-facing agent.
- `AgentRuntime`, `ToolRegistry`, `ToolSetResolver`, `ToolGateway`, `PolicyEngine`.
- `ToolExecutionContext` with server-inherited Workspace/Business/permissions.
- Narrow, typed, versioned tools instead of arbitrary SQL/HTTP/code capabilities.
- Autonomy modes: `AUTO`, `REQUIRE_CONFIRMATION`, `ESCALATE`, `DISABLED`.
- `ApprovalRequest` with frozen action + revalidation before execution.
- Evidence-based action requirements instead of AI self-confidence as authorization.
- Bounded agent loop, explicit stop outcomes and tool budgets.
- `AIToolCall/ToolTrace` separated from `AuditEvent`.
- Deterministic system events bypass LLM whenever semantics are already known.

### Added — Stage 9 Industry Modules / Workflow

- Workflow archetypes and composable Service capabilities.
- Seven initial workflow families:
  Slot-Based, Custom Consultative, Event-Based, Onsite, Custom Production, Recurring Session, Project Delivery.
- Versioned `IndustryPack` templates.
- `WorkflowDefinition`, `WorkflowRevision`, `WorkflowInstance`, `WorkflowStepInstance`.
- Workflow graph with guards/dependencies/optional branches/wait states.
- Deterministic workflow completion from domain state.
- Generic onboarding path for professions without prebuilt IndustryPack.
- Separate Workflow Complexity and Risk/Regulatory Complexity classification.

### Added — Stage 10 Business Onboarding

- `OnboardingAgent` and `OnboardingSession`.
- Quick Start, Assisted Import and Concierge modes.
- `ImportBatch` / normalized sources boundary.
- Service discovery, capability/workflow inference, rule/knowledge candidates.
- Conflict detection and adaptive dependency-aware questionnaire.
- Readiness gates per Service instead of completion percentage.
- `ConfigurationDraft`, deterministic validation, simulation and Owner approval.
- Atomic immutable `BusinessConfigurationRelease`.
- Calibration period and progressive autonomy after production launch.

### Revised

- Architecture files are no longer expected to be regenerated after every single stage; baselines may bundle several accepted stages.
- Workflow is now explicitly a first-class orchestration layer rather than only an abstract future concept.
- Business configuration publication is now versioned atomically via `BusinessConfigurationRelease`.

### Still deferred

- Pricing architecture;
- exact Scheduling/Payment tool field contracts;
- concrete payment provider;
- exact MVP import formats/UI;
- Security/Privacy hardening;
- infrastructure/observability/scaling;
- final MVP scope.

---

## v0.7 — 2026-09-01

**Status:** Stage 7 — AI Architecture accepted.

### Added

- `ModelGateway`, `ModelProfile`, `ModelRouter`, `PromptRegistry`, `SchemaRegistry`, `SafetyGateway`.
- `AIRun` separate from `AIProviderCall`; provider usage/cost attribution.
- Task profiles with initial GPT-5.6 Luna/Terra/Sol mapping.
- Schema registry and versioned Structured Outputs.
- Prompt/config revisions and bounded ContextBuilder.
- EmbeddingProfile/versioned projections for Knowledge/Portfolio.
- AIDataPolicy/provider boundary concepts.

### Confirmed

- Responses API is the primary OpenAI integration direction for current GPT-5.6 workflows.
- Visual generation remains a separate service; image model does not control business workflow.
- Voice messages use separate transcription service; realtime voice is not required for MVP.
- Customer-facing AI does not receive unrestricted web/computer/provider tools by default.
- Full chain-of-thought is not required for auditability.

### Resolved Open Questions

- OPEN-001 — default conversation profile/model mapping.
- OPEN-002 — model routing architecture.
- OPEN-003 — Structured Outputs principle; exact Agent schema deferred to Stage 8.
- OPEN-004 — context budgeting principle.
- OPEN-005 — AIRun persistence principle.

### Revised

- Embeddings are no longer modeled as a single field tightly coupled to canonical `knowledge_chunks`; they are versioned projections so multiple embedding profiles can coexist during migration/eval.

---

## v0.6 — 2026-09-01

**Status:** первый канонический baseline после завершения этапов 0–6 и повторного аудита направления.

### Added

- Каноническая структура архитектурных файлов.
- Статусы LOCKED / DEFERRED / OPEN / REVISED.
- Отдельный Stage 10: Business Onboarding & Configuration.
- Отдельный Stage 15: SaaS Plans / Billing / Usage / Quotas.
- Явное различие Workspace и Business.
- Progressive autonomy.
- Workflow-driven design вместо единого глобального pipeline.
- Visual Design Service / GeneratedAsset.
- KnowledgeBuild / KnowledgeCandidate / HistoricalCase / CommunicationProfile.
- Portfolio-first visual policy.
- Отдельные retrieval scopes: Business Knowledge, Client History, Portfolio, Historical Cases.

### Confirmed after audit

Сохранены без фундаментальной переделки:

- один multi-tenant SaaS вместо отдельных AI models per master;
- Workspace как tenant boundary;
- shared PostgreSQL + workspace_id;
- PostgreSQL RLS + defense in depth;
- PostgreSQL как source of truth;
- Object Storage для binary;
- Redis как non-authoritative support layer;
- pgvector для initial RAG;
- Conversation != ServiceRequest;
- Message != ConversationTurn;
- Assessment != Quote;
- ServiceOrder != ServiceSession;
- ServiceSession != Appointment;
- ReservationHold != Appointment;
- PaymentRequest != PaymentTransaction;
- independent state machines;
- Channel Adapter abstraction;
- Telegram Profile Automation как основной initial transport;
- Human Takeover;
- structured state выше LLM memory/summary;
- RAG вместо fine-tuning per workspace по умолчанию;
- raw chats как extraction material, а не business truth;
- knowledge authority/provenance;
- visual generation как отдельный сервис.

### Revised

#### 1. Глобальный линейный workflow

**Ранее:** схемы часто показывали:
```text
Request → Assessment → Quote → Order → Session → Appointment
```

**Теперь:** это только один вариант. Workflow Definition конкретной услуги определяет нужные этапы и порядок.

Примеры:
```text
Manicure: Request → Appointment → Payment after service
Tattoo: Request → Assessment → Quote → Deposit → Sessions/Appointments
Furniture: Request → Assessment → Design → Quote → Deposit → Production → Delivery
```

#### 2. Workspace vs Business

**Ранее:** в ранних черновиках местами почти отождествлялись.

**Теперь:**
- Workspace = tenant/security boundary;
- Business = business context;
- MVP всё ещё может использовать 1 Workspace = 1 Business.

#### 3. Первая вертикаль

**Ранее:** тату рассматривалась как вероятная первая ниша из-за сложности/stress-test.

**Теперь:** тату остаётся архитектурным stress-test, но первый production client выбирается по практической пригодности и готовности тестировать.

### Deferred intentionally

Не зафиксированы:
- conversational LLM;
- model routing;
- Agent/tools;
- formal workflow format;
- Pricing;
- Scheduling;
- payment provider;
- notification transports;
- SaaS billing provider;
- UI tech;
- infrastructure;
- observability;
- scaling thresholds;
- final MVP scope.

См. `04_OPEN_QUESTIONS.md`.

### External assumptions reverified for baseline

По официальной документации на 2026-09-01:

- Telegram connected business/profile automation bot можно подключать без Premium.
- Telegram `can_reply` сейчас использует 24-часовое окно после входящего сообщения в подходящем приватном чате.
- Telegram сейчас допускает один connected business bot на пользовательский аккаунт.
- PostgreSQL 18 — текущая stable branch и имеет native `uuidv7()`.
- OpenAI `text-embedding-3-small` остаётся доступной text embedding model и сохраняется как текущий MVP candidate до Stage 7 review.

Эти внешние факты считаются mutable и перепроверяются перед production.
