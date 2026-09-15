# AI Service Manager — Production Deployment & Runbooks

**Baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** LOCKED production operating contract for Pilot planning

---

## 1. Purpose and authority

This document is the canonical operational guide for deploying, validating, rolling back and recovering the first production Pilot.

Priority:
- `01_ARCHITECTURE_SPEC.md` — architecture hard constraints;
- `06_MVP_SPEC.md` — first-release scope/readiness;
- `07_DEVELOPMENT_ROADMAP.md` — implementation sequence;
- **this file** — deployment/cutover/recovery procedure.

Stage 26 sets RU Pilot defaults (Russia/Yandex Cloud-class infrastructure, YooKassa candidate); v0.28 revises AI to PolzaAI-preferred aggregator/direct branches while exact SKUs/model mappings/first-Business fiscalization/support terms remain release-time configuration. These bindings do not weaken the provider-neutral operating contract.

---


## 1.1. RU Pilot provider bindings

Default production profile:
- Home Data Region: Russia;
- infrastructure: `RU_PILOT_V1` (Yandex Cloud preferred);
- AI: RU_AGGREGATOR (PolzaAI preferred candidate, GPTunnel comparison) and switchable DIRECT_PROVIDER adapter; each actual route has separate execution-class/data eligibility;
- direct VPN/proxy foreign AI: forbidden;
- Client payments: YooKassa first candidate;
- fiscalization: separate BusinessLegalProfile/FiscalizationProfile workflow.

ReleaseManifest records the active RegionalProviderBundle and AI routing/config revisions. Each branch/profile can be paused independently without stopping inbound/manual service. Include AIProviderBranch/AIRoutingRevision in ReleaseManifest and AIRun attribution; automatic cross-branch fallback is not implicit.

## 2. Production release model

### 2.1. Immutable artifacts

Every deploy must identify:
- source commit;
- CI/build run;
- immutable container digest;
- application version;
- DB schema/migration version.

Do not deploy an untraceable mutable `latest` artifact.

### 2.2. ReleaseManifest

A release manifest must pin relevant:
```text
release_id
source_commit
ci_run
container_digest
application_version
database_schema_version
IndustryPackRevision
PromptRevision(s)
ModelProfileRevision(s)
AIProviderBranch / AIRoutingRevision
RegionalProviderBundle
ToolSetVersion
StructuredSchemaVersion(s)
PlatformPolicyRevision(s)
EvalSuiteRevision
```

Tenant `BusinessConfigurationRelease` is referenced separately where needed and is not silently bundled into application code.

### 2.3. Release axes

```text
Application Release
Platform AI Configuration Release
BusinessConfigurationRelease
```

Each has its own promotion/rollback semantics.

---

## 3. Environment provisioning checklist

Before Pilot deployment verify:

### Infrastructure
- [ ] one production region selected;
- [ ] production project/account separated from local/staging where practical;
- [ ] public ingress limited to required HTTPS surfaces;
- [ ] DNS configured;
- [ ] TLS valid and auto-renewing;
- [ ] application compute available;
- [ ] managed PostgreSQL provisioned;
- [ ] runtime DB role created;
- [ ] migration DB role created separately;
- [ ] private Object Storage bucket/container provisioned;
- [ ] quarantine area provisioned;
- [ ] Secret storage configured;
- [ ] Container Registry configured;
- [ ] observability backend/export configured;
- [ ] automated DB backup/PITR enabled;
- [ ] restore test completed successfully.

### Environment isolation
- [ ] production DB distinct from staging;
- [ ] production Object Storage distinct from staging;
- [ ] production channel/payment/AI secrets distinct as applicable;
- [ ] no normal development workflow depends on production customer data.

---

## 4. Pre-release checklist

### Code / DB
- [ ] build PASS;
- [ ] unit/property tests PASS;
- [ ] real PostgreSQL integration PASS;
- [ ] tenant/RLS suite PASS;
- [ ] migration tests PASS;
- [ ] concurrency/idempotency/recovery critical tests PASS.

### AI
- [ ] critical Tattoo EvalSuite PASS;
- [ ] zero critical safety/money/booking/security violations;
- [ ] relevant prompt/model/tool/schema regression PASS;
- [ ] candidate compared against ProductionBaseline where applicable.

### Security / supply chain
- [ ] dependency scan reviewed;
- [ ] secret scan reviewed;
- [ ] container/image scan reviewed;
- [ ] no production secrets embedded in image/repository.

### Release artifact
- [ ] immutable image digest known;
- [ ] ReleaseManifest generated;
- [ ] release notes include migrations/AI config/risk/rollback path.

### Stage-23 readiness
- [ ] DOMAIN_READY;
- [ ] AI_READY;
- [ ] SECURITY_READY;
- [ ] RELIABILITY_READY;
- [ ] BUSINESS_CONFIG_READY;
- [ ] OPERATIONS_READY;
- [ ] PRIVACY_READY;
- [ ] FISCALIZATION_READY before RU live payment activation.

---

## 5. Database migration procedure

1. Confirm migration is backward compatible with currently serving application.
2. Confirm required recent backup/PITR state exists for high-risk migration.
3. Run migration using migration identity, never regular runtime role.
4. Verify migration result/schema version.
5. If backfill is required, run controlled persistent job with progress/idempotency.
6. Deploy compatible application revision.
7. Observe production behavior.
8. Only in a later safe release apply CONTRACT/destructive cleanup.

### Migration failure rule

If migration fails before required schema is ready:
- stop deployment;
- keep prior application serving where safe;
- diagnose migration state;
- use documented repair/recovery;
- do not improvise destructive reverse SQL under live traffic.

---

## 6. Application rollout procedure

```text
Build/pin new revision
→ run required migration
→ start new API/Worker revision
→ liveness/readiness
→ safe smoke suite
→ route traffic
→ stop old API accepting work
→ old Workers stop claiming
→ drain/release work
→ terminate old revision
→ observation window
```

Readiness must validate critical internal dependencies/configuration but must not fail solely because an optional/external provider is temporarily degraded.

---

## 7. Post-deploy smoke suite

Use dedicated internal Test Workspace.

Safe checks:
- [ ] Business Console login/session;
- [ ] API read/write path;
- [ ] PostgreSQL transaction;
- [ ] Object Storage temporary put/read/delete;
- [ ] job enqueue/claim/complete;
- [ ] Inbox/Outbox path;
- [ ] cross-Workspace denial smoke;
- [ ] safe AI provider/query-only Agent call;
- [ ] Telegram/other provider connection health.

Do **not** issue uncontrolled real refund, payment, customer Appointment or production customer message as a generic smoke test.

---

## 8. Post-deployment observation

During the observation window actively inspect:
- API error rate;
- DB errors/connections;
- Inbox lag;
- Outbox lag;
- interactive Job lag;
- Worker/DLQ state;
- AI provider error/latency;
- Telegram send/connection state;
- payment-webhook processing;
- unexpected cost spikes.

If user-visible symptoms worsen after release, stop rollout and choose the correct rollback/recovery axis.

---

## 9. Rollback matrix

| Failure source | Primary response | DB restore? |
|---|---|---|
| Bad application code | deploy prior known-good image / roll-forward hotfix | normally no |
| Bad Prompt/ModelProfile | restore previous ProductionBaseline mapping | no |
| Bad Business configuration | publish/reactivate known-good semantics for new work | no |
| Bad migration without data corruption | stop rollout / compatible app / repair migration | normally no |
| Data corruption/loss | controlled repair or restore-to-new-instance | maybe yes |
| External provider outage | degrade/pause affected subsystem, reconcile later | no |

Database restore is a disaster/data-recovery operation, not ordinary application rollback.

---

## 10. Operational kill switches

At minimum operational control must support narrow actions such as:
- pause AI run admission, AI mutations and AI sends independently/globally/per Workspace;
- pause new optional bulk work;
- pause new payment-session creation if payment integration is unsafe;
- pause optional media processing.

AI pause behavior:
```text
Client inbound → persist normally
AI runs/mutations/auto-response → disabled when AI capability pause selected
Owner/manual operation → available
Payments/appointments/history → preserved
```

Avoid one indiscriminate global switch that disables unrelated critical persistence/webhooks.

---

## 10.1. AI branch change procedure

1. Select immutable target AIRoutingRevision for RU_AGGREGATOR or DIRECT_PROVIDER; verify credentials, API/model capabilities, data eligibility, cost and Eval evidence.
2. Confirm compatible embeddings/query projection; prepare reindex separately if required.
3. Run synthetic Test Workspace contract/smoke checks without customer side effects.
4. Atomically activate routing binding for new AIRuns; pin existing run revisions or cancel unsafe runs. Retain successful tool results/business-intent keys across restart.
5. Observe actual selected route, latency, cost, errors and domain correctness; rollback binding to prior approved revision if needed.

No provider-side chat state migration, domain data rewrite or silent geographic transfer. Gateway-internal fallback must satisfy the same route policy.

## 11. Secret rotation procedure

For each critical credential:
1. identify owner/provider and dependent services;
2. issue new secret/key;
3. store new version in Secret storage;
4. deploy/reload consumers;
5. verify successful authentication/operation;
6. revoke old credential;
7. record SecurityEvent/change evidence where appropriate.

For suspected compromise:
- revoke/disable immediately where safe;
- replace credential;
- invalidate affected sessions/tokens if needed;
- inspect logs/provider usage;
- assess tenant/data exposure;
- create incident follow-up.

---

## 12. Backup / restore procedure

### 12.1. Restore principle

Restore into a **new database instance/environment** first.

### 12.2. Procedure

```text
contain incident / fence old effect-producing runtime
→ select backup/PITR point
→ provision new DB
→ restore
→ verify schema/migrations
→ verify RLS/roles
→ run invariant checks
→ connect Object Storage/secrets
→ apply privacy deletion/tombstone reconciliation
→ reconcile Payments/SaaS Billing/providers
→ recover Inbox/Outbox/Jobs/Holds/Automations
→ rebuild derived state if required
→ run smoke/Golden Journey checks
→ controlled traffic cutover
```

### 12.3. Validation checklist
- [ ] expected schema version;
- [ ] tenant RLS active;
- [ ] Workspace/Business counts plausible;
- [ ] critical Payment/Appointment/Allocation invariants;
- [ ] Inbox/Outbox/job states reviewed;
- [ ] BusinessConfiguration releases present;
- [ ] FileObject refs/Object Storage access valid;
- [ ] completed privacy deletions recovered from approved journal/checkpoint newer than restore point; otherwise affected data quarantined;
- [ ] old API/Workers/Scheduler cannot dispatch/write; only one recovery generation active;
- [ ] post-backup external effects reconciled before Outbox replay; ambiguous sends remain UNKNOWN;
- [ ] provider reconciliation performed where applicable.

---

## 13. Incident model

### SEV-1
Critical security/canonical impact, e.g. suspected tenant exposure, money corruption, escaped double-booking, DB/durable-loss condition, critical secret compromise.

### SEV-2
Major degradation while canonical state is preserved, e.g. sustained AI/channel/payment availability problem or severe interactive backlog.

### SEV-3
Limited/localized/optional impact.

Lifecycle:
```text
DETECTED → ACKNOWLEDGED → MITIGATING → RECOVERING → RESOLVED → FOLLOW_UP
```

Priority:
1. stop harmful effects;
2. preserve incoming/canonical data;
3. restore essential operation;
4. reconcile;
5. diagnose root cause;
6. prevent recurrence.

---

# 14. Incident Runbooks

Each runbook below is a Pilot minimum. Fill concrete commands/links against the selected provider account/SKU during implementation; provider defaults are already selected, actual recovery evidence is still required.

## RB-01 — PostgreSQL unavailable

**Trigger/Symptoms**
- DB connection failures;
- API readiness failure;
- inability to durably persist critical inbound work.

**Immediate Safety**
- fail closed for canonical mutations;
- do not acknowledge critical external events as safely persisted if they are not durable.

**Diagnose**
- managed DB/provider health;
- network/private endpoint;
- credentials/certificates;
- DB CPU/storage/connections/locks.

**Recover**
- restore connectivity/provider failover if available;
- if data recovery is required, execute RB-13.

**Verify**
- DB transaction;
- RLS;
- Inbox/Outbox/jobs;
- payment/appointment invariants;
- queue lag recovery.

---

## RB-02 — Worker / Queue backlog

**Trigger**: interactive lag rises, oldest READY job age exceeds operational threshold.

**Immediate Safety**
- throttle/pause BULK and optional work.

**Diagnose**
- Worker heartbeat/capacity;
- DB locks/connection pool;
- provider rate limits;
- repeated poison job.

**Recover**
- restart/add Worker capacity;
- allow expired leases to reclaim;
- isolate permanent poison jobs to DLQ.

**Verify**
- interactive lag decreases;
- no duplicate effects;
- DLQ understood.

---

## RB-03 — AI provider degraded

**Immediate Safety**
- keep inbound messages durable;
- retry according to bounded policy;
- pause AI auto-send if sustained/unsafe.

**Fallback**
- notify Owner / use Human takeover;
- do not route to an unevaluated alternative model/provider.

**Verify**
- provider success/latency restored;
- stale queued replies fail relevance checks before send.

---

## RB-04 — Telegram degraded

**Behavior**
- canonical state remains;
- outbound is queued/unknown/retryable according to adapter semantics; a closed reply window is ROUTE_UNAVAILABLE, not an endlessly retryable outage. Create owner-visible task; Console uses the same channel rights.

**Recovery**
- verify provider/connection health;
- resume dispatch;
- run relevance/staleness checks before delayed sends.

**Do not** blindly flush every delayed outbound message.

---

## RB-05 — Telegram credential/connection invalid

- mark `ChannelConnection` as ACTION_REQUIRED/DEGRADED;
- stop unsafe sends for that connection;
- notify Owner/Platform Ops;
- rotate/reconnect credential;
- verify only the affected Workspace route is impacted.

---

## RB-06 — Client Payment provider unavailable

- do not mark anything paid;
- keep PaymentRequest canonical state unchanged/open as appropriate;
- pause new checkout/session creation if needed;
- durably persist callbacks under provider-specific verification/quarantine; only verified object/merchant/amount/currency/test-mode state authorizes money effects;
- reconcile after recovery.

---

## RB-07 — Payment mismatch / reconciliation

Example: provider `SUCCEEDED`, local `PENDING`.

- verify provider-authoritative event/API;
- run idempotent reconciliation;
- update canonical transaction through PaymentService;
- if Hold expired, follow late-payment recovery: record payment, do not fabricate Appointment, escalate/alternative/refund decision.

Never repair payment state based on AI/client assertion.

---

## RB-08 — Object Storage unavailable

- text-only flows may continue if no file dependency;
- image-dependent processing enters pending/wait state;
- do not hallucinate Vision/file contents;
- retry file processing after provider recovery;
- verify private access/signed URL behavior.

---

## RB-09 — Bad application release

**Signal**: errors/user-visible regressions correlate with deployment.

- stop further rollout;
- deploy previous known-good immutable image if schema compatible, or roll-forward targeted fix;
- verify critical smoke/Golden Journey slice;
- observe queue recovery;
- add regression test.

---

## RB-10 — Bad Prompt / ModelProfile / AI config

- disable candidate mapping;
- activate previous ProductionBaseline;
- do not rollback DB;
- inspect affected conversations/tool traces;
- convert incident into EvalCase/regression before re-promotion.

---

## RB-11 — Bad Business Configuration

- stop unsafe affected automation/action if necessary;
- publish/reactivate corrected/known-good configuration semantics for new work;
- preserve immutable historical Quote/Order/Service revisions;
- identify any already-affected Clients/Orders and repair through scoped commands.

---

## RB-12 — Migration failure

If migration did not complete safely:
- do not deploy dependent app;
- hold current compatible application;
- inspect migration version/state;
- use documented repair/forward migration;
- escalate to restore only when actual data corruption/loss requires it.

---

## RB-13 — Backup Restore / Disaster Recovery

Follow Section 12 restore-to-new-instance procedure.

Before cutover prove the old runtime is fenced, newer deletion state is recoverable (OPEN-084), and already executed external effects cannot be blindly replayed. If evidence is unavailable, keep affected processing paused.

After restore additionally:
- reconcile Payments/SaaS Billing;
- recover due automations using late policy;
- reconcile pending/expired Holds;
- validate Outbox/Jobs;
- reapply privacy deletion state;
- run critical invariant/smoke checks before cutover.

---

## RB-14 — Suspected tenant data exposure

**Severity**: SEV-1.

- disable affected access path/capability;
- preserve logs/evidence;
- revoke compromised support/session/token if applicable;
- determine affected Workspaces/data/actions;
- create SecurityEvent/incident evidence;
- follow jurisdiction-specific notification/legal process;
- do not delete evidence in an attempt to “clean up”.

---

## RB-15 — Secret compromise

- revoke/disable compromised secret;
- issue replacement;
- update Secret storage/deployment;
- invalidate dependent sessions/tokens where needed;
- inspect provider/account usage;
- assess exposure;
- document SecurityEvent/follow-up.

---

## RB-16 — AI cost runaway

- identify Workspace/feature/model source via Stage 20 usage;
- pause BULK/optional expensive work first;
- apply CostGuard/throttling;
- preserve essential Client/payment/booking/manual paths;
- diagnose loop/abuse/config regression;
- add alert/eval/test if caused by product bug.

---

## RB-17 — DLQ / poison event

- identify event/job/failure class/Workspace/correlation chain;
- determine permanent vs transient cause;
- fix root cause/config;
- Replay only through normal handler;
- normal authorization/idempotency/state checks remain active.

---

## RB-18 — Human takeover failure

**Immediate Safety**
- pause AI auto-send for affected Workspace; global pause if scope unknown.

**Recover**
- restore control-mode/staleness invariant;
- verify no pending AI output or uncommitted AI command can bypass HUMAN/control generation;
- inspect already in-flight external sends separately; do not claim they were recalled;
- review affected messages;
- add critical regression Eval/test before re-enable.

---

## RB-19 — Scheduling invariant alarm

- pause new booking/Hold creation for affected Resource/Workspace;
- preserve/read existing Appointments;
- inspect allocations/holds/version history;
- repair only through validated scheduling/domain operation;
- verify exclusion/invariant protection before resume.

---

## RB-20 — SaaS Billing provider outage

- continue runtime using local canonical Subscription/Entitlement state;
- do not suspend Workspaces solely because billing provider API is unavailable;
- persist/retry provider billing events where applicable;
- reconcile invoices/subscriptions when provider returns;
- notify owner only according to canonical billing policy, not provider transient state alone.

---

## 15. First Business cutover procedure

1. Provision production environment and verify backups/restore/observability.
2. Deploy Pilot Release Candidate and complete smoke suite.
3. Publish approved BusinessConfigurationRelease.
4. Connect Telegram with **AI auto-send disabled**.
5. Receive a real controlled inbound message and verify correct Workspace/Conversation/Inbox.
6. Verify Owner manual reply reaches the Client.
7. Verify image attachment → private Object Storage → FileObject path.
8. Enable AI for controlled test conversation and verify Knowledge/Tool trace.
9. Enable AI for pilot intake/knowledge/pricing scope.
10. Enable Scheduling/Hold actions.
11. Verify actual merchant, agreed price/payment terms, fiscal profile/receipt workflow and FISCALIZATION_READY, then enable payment flow. First master uses approved fixed deposit; NONE path remains available for other configured services.
12. Enable MVP Automations.
13. Maintain enhanced operational review during initial calibration conversations.

Rollback/pause at any step if the corresponding readiness/health signal is not green.

---

## 16. Release notes template

```text
Release ID:
Source commit / image digest:
Risk class:
What changed:
DB migrations/backfills:
AI config/model/prompt changes:
Business config impact:
Tests/Evals executed:
Known risks:
Rollback/recovery path:
Operator / deployment time:
Post-deploy observation result:
```

Prefer small releases. Avoid combining unrelated high-risk payment + scheduling + model + destructive DB changes in one release where practical.

---

## 17. Post-incident follow-up checklist

For significant incidents answer:
- What happened and what was the actual impact?
- Which safeguard failed or was absent?
- How was it detected?
- How was harmful effect stopped?
- How was canonical state reconciled?
- What regression test/EvalCase/constraint/alert/runbook change prevents recurrence?

Follow-up is incomplete until appropriate preventive artifact(s) exist.

---

## 18. Stage-26 values still required before live Pilot

The RU market, Yandex-preferred bundle, Tattoo first master and fixed-deposit mode are accepted. Remaining release configuration:
- exact managed PostgreSQL SKU/zone/PITR retention and measured RPO ≤5 min / RTO ≤4 h feasibility;
- Object Storage lifecycle/restore mechanism;
- approved aggregator/direct model IDs, costs, route eligibility and latency evidence;
- actual merchant connection and Business legal/tax/fiscalization responsibility;
- exact fixed deposit amount, approved pricing/duration rules and cancellation policy;
- numeric SLO/alerts, operator destination, support window and Business IANA timezone;
- independent deletion journal and old-runtime fencing procedure;
- provider-specific commands/links and tested recovery evidence.

These are release gates assigned to M0–M12/actual onboarding, not a claim that already-completed architecture Stage 26 must be designed again. Track OPEN-071–076 and OPEN-079–084. Do not invent contractual/Business values.

## Runbook 21 — Fiscalization pending/failed

**Trigger:** confirmed Client payment has no required fiscal receipt/registration within the configured compliance workflow, or fiscalization provider/manual confirmation fails.

**Immediate safety action:** preserve PaymentTransaction as authoritative money state; do not fabricate/rollback payment. Create/highlight Fiscalization obligation and notify authorized Owner/Platform Ops.

**Diagnosis:** verify BusinessLegalProfile/FiscalizationProfile, provider/manual responsibility, payment/receipt correlation, provider credentials/status and deadline policy.

**Recovery:** retry through the configured FiscalizationAdapter when safe or complete the authorized manual Owner flow. Never let AI invent receipt success.

**Verification:** receipt/obligation reaches a valid terminal/compliant state; audit link to PaymentTransaction exists; no duplicate receipt was created.

**Escalation:** repeated/system-wide failures pause new automated payment activation if required by the applicable compliance policy, while preserving reconciliation/manual handling.
