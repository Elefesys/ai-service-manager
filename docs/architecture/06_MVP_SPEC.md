# AI Service Manager — MVP Specification

**Baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** LOCKED first-release scope; implementation sequencing is canonical in `07_DEVELOPMENT_ROADMAP.md`

---

## 1. Purpose

This document is the canonical source for the **first production MVP scope, exclusions, Golden Journeys, autonomy contract and release acceptance criteria**.

`01_ARCHITECTURE_SPEC.md` remains authoritative for architectural hard constraints.  
`06_MVP_SPEC.md` is authoritative for what is and is not implemented in the first release.

---

## 2. Product hypothesis

The MVP must prove that an AI manager can safely handle a meaningful share of real service-business customer conversations from first message to the next correct business outcome while reducing owner interruption.

Success is not measured by message volume or feature count.

The primary proof flow is:

```text
Client
→ Telegram
→ AI intake / clarification
→ verified Knowledge / Portfolio / Assessment
→ configured price or Owner Quote
→ availability
→ ReservationHold
→ deposit/payment
→ Appointment
→ reminder / continued conversation
```

---

## 3. First production vertical

### 3.1. Industry

**Tattoo**

Tattoo is the first production Industry Pack, not a permanent restriction of the universal platform.

### 3.2. Primary autonomous request

**New Tattoo Request**

Example:
> Client sends an idea/reference and wants to understand feasibility, price and available time.

### 3.3. Intentionally human-led / restricted cases

The MVP may escalate or safely decline:
- cover-up;
- unusual/unsupported technique;
- health/medical advice;
- minor-specific cases;
- policy exceptions;
- custom discount;
- refund;
- missing/conflicting critical Business Rules;
- other cases outside configured autonomy.

---

## 4. Initial Business topology

The MVP UI/operations optimize for:

```text
1 Workspace
1 Business
1 main Location
1 primary Owner/Provider
1 primary Resource = Provider
1 Telegram customer connection
```

The core architecture still preserves multi-tenant/multi-resource extensibility.

For the first Business, one primary:
- customer language;
- currency;
- timezone

is sufficient.

---


## 4.1. RU Pilot market profile

For the first production Pilot:
- MarketProfile = RU;
- primary language = Russian;
- currency = RUB;
- Home Data Region = Russia;
- RU DataResidencyPolicy applies;
- provider bindings come from `RU_PILOT_V1` and remain adapter/configuration choices.

Two branches are required: RU_AGGREGATOR (PolzaAI preferred candidate, GPTunnel comparison) and DIRECT_PROVIDER (official developer APIs). Both route by task profiles and switch through validated AIRoutingRevision. Actual route/data eligibility is independent; direct VPN/proxy access remains excluded. See Spec §§7.21–7.22 and 26.4.

## 5. Required customer channel and media

### Included
- Telegram;
- text messages;
- image attachments.

### Excluded from MVP
- VK;
- MAX;
- WhatsApp/Instagram automation;
- customer voice transcription;
- customer video understanding;
- arbitrary customer-document ingestion.

Telegram capabilities are enforced through ChannelCapabilities; the product must not claim a route/send capability that the channel does not currently provide.

---

## 6. Tattoo intake

The normal New Tattoo flow must progressively collect, when applicable:

- idea / subject;
- reference image(s);
- placement / body part;
- approximate size;
- style / relevant visual characteristics.

The AI should not ask already-known fields again and should not turn the conversation into a rigid long form.

Every important extracted/inferred field preserves provenance where practical.

---

## 7. Vision / Portfolio

### Included
- inbound image persistence;
- structured Vision analysis;
- portfolio item ingestion/review;
- portfolio retrieval/matching;
- `MY_WORK` lineage.

### Hard rules
- Vision does not decide business feasibility by itself.
- Client references are not owner portfolio.
- Generated assets, if introduced later, are never owner portfolio.

### Excluded
- AI tattoo design generation.

---

## 8. Knowledge / Onboarding

### Included
- curated Knowledge/RAG;
- FAQ/policies;
- service/style information;
- preparation instructions supplied by Business;
- deposit/cancellation rules;
- historical conversation import/analysis;
- CommunicationProfile extraction;
- conflict/gap detection;
- owner confirmation of critical rules;
- versioned BusinessConfigurationRelease.

### Delivery model
First production onboarding is **Concierge**.

A full universal self-service configuration builder is not a pilot blocker.

---

## 9. Pricing

### Included
- Owner-selected fixed price or bounded deterministic owner-supplied formula;
- configured validated range;
- Owner Quote / NEEDS_HUMAN;
- PriceCalculation → Quote;
- immutable sent Quote.

### Excluded / forbidden
- authoritative price invented by LLM;
- arbitrary AI discounts;
- ML predictive pricing;
- arbitrary executable pricing formula language; supported formulas use validated deterministic rule templates.

Owner Quote is a successful intended workflow, not an AI failure.

---

## 9.1. Agreement and independent owner settings

PricingMode is FIXED / CONFIGURED_FORMULA / OWNER_QUOTE, selected by the Business owner per Service. AI uses PricingEngine or asks Owner; after QuoteAcceptance, create Order/next Session and calculate the applicable payment obligation. An indicative range is not silently treated as final exact price. Client acceptance must bind a specific immutable Quote and terms.

Price mode, duration mode and payment mode can differ. First master uses a fixed deposit independent of job scale; exact amount remains OPEN-079. A percentage deposit/full prepayment needs an exact agreed amount; NONE skips prepayment entirely without creating fake payment success. Details: Spec §§11.10–11.11 and 13.12.

---

## 10. Scheduling

### Included
- one primary provider Resource;
- working hours;
- AvailabilityOverrides/days off;
- duration;
- buffers;
- AvailabilityOffer;
- ReservationHold;
- ResourceAllocation;
- Appointment;
- cancellation;
- simple safe reschedule;
- DB-level overlap prevention.

### Excluded
- multi-provider/resource atomic booking;
- rooms/equipment;
- group/capacity scheduling;
- recurring schedules;
- travel/routing;
- external calendar sync;
- full automatic scheduling of all future multi-session work.

Future ServiceSessions may remain `PLANNED`.

---

## 10.1. Duration scope

Owner-configured fixed/rule duration or structured Owner decision is required before booking. Historical labelled cases and AI comparisons can assist Owner; no self-trained authoritative duration. Store proposed versus approved duration separately and distinguish work time, Appointment time and resource buffers. Until master calibration is available, OWNER_DEFINED is the safe path; exact fixed/rule services remain automatic. Multi-session requests schedule only the next approved session. Collection format and calibration questions: OPEN-080/081, Spec §11.11.

---

## 11. Client payments

### Included
- one PaymentProvider per Business;
- hosted payment link/checkout;
- no prepayment, fixed deposit, percentage deposit or full prepayment;
- PaymentTerms;
- PaymentRequest;
- PaymentSession;
- PaymentTransaction;
- provider-verified webhook;
- idempotency;
- reconciliation;
- manual authorized offline-payment confirmation;
- Owner-approved refund path.

### Hard rules
- platform never stores Client PAN/CVC;
- Client claim/screenshot is not authoritative payment confirmation;
- AI cannot autonomously refund;
- AI cannot mark paid from chat.

---


## 11.1. RU fiscalization readiness

Client Payment and fiscal/tax receipt are separate concerns. The first Business must have a known `BusinessLegalProfile` and `FiscalizationProfile` before live payment activation.

MVP may temporarily support an explicitly tracked `MANUAL_OWNER` fiscal receipt obligation for a controlled Pilot when legally/operationally confirmed. Missing/failed fiscalization creates an Action Center item/alert and never silently disappears.

`FISCALIZATION_READY` is an additional RU launch gate.

## 12. Critical booking/payment path

```text
Validated request/assessment
→ immutable Quote + explicit QuoteAcceptance
→ ServiceOrder + next ServiceSession
→ Client selects server-provided AvailabilityOption
→ fresh ReservationHold
→ PaymentTerms: NONE or PREPAYMENT_REQUIRED
```

NONE → revalidate active Hold and all booking preconditions → Appointment CONFIRMED.

PREPAYMENT_REQUIRED → deterministic PaymentRequest/hosted PaymentSession → verified provider success → satisfied obligation → revalidate active Hold → Appointment CONFIRMED.

No-deposit booking never fabricates a paid transaction. First master's fixed deposit amount comes from approved configuration, not scale inference. Late payment after expiry is recorded and routed to safe recovery; no fabricated booking. Pricing changes require fresh agreement. Exact contracts: Spec §§11.10/13.12.

---

## 13. Automations

### Included
- Appointment reminder when route/window eligible; otherwise owner-visible ROUTE_UNAVAILABLE task;
- payment reminder;
- Hold expiry/warning behavior;
- bounded missing-client-response follow-up;
- Owner escalation notification.

### Required guards
- relevance;
- human takeover;
- quiet hours;
- frequency cap;
- idempotency;
- late-execution policy.

### Excluded
- marketing;
- reactivation;
- review campaigns;
- SMS/email fallback trees;
- general AI campaigns.

---

## 14. Business Console MVP

### Required
- login/session;
- Action Center;
- Inbox;
- Conversation detail;
- AI/Human control state;
- Takeover / Resume;
- Approvals / Escalations;
- Calendar;
- Appointment details;
- Clients;
- Request/Project detail;
- customer payment state;
- basic service/pricing/schedule/payment-rule view/edit/review needed for operations;
- Knowledge/Portfolio review needed by concierge onboarding;
- Telegram connection health;
- basic Plan/Usage view;
- owner-readable activity history where required.

### Not required
- advanced BI;
- no-code workflow builder;
- full IndustryPack editor;
- native iOS/Android;
- multi-location admin;
- advanced team/enterprise permission UI;
- raw prompt/model selection.

---

## 15. Platform Operations MVP

Required before first real client:

- Workspace directory/health;
- integration health;
- failed/stuck Jobs and DLQ;
- Inbox/Outbox operational visibility;
- AI Run / tool diagnostic trace;
- billing/service mode visibility;
- SupportAccessGrant;
- audit/security-relevant activity;
- safe Retry/Replay/Resync commands;
- basic usage/cost visibility.

Forbidden:
- generic production SQL console as product feature;
- hidden owner impersonation;
- unrestricted support access;
- secret exposure.

---

## 16. SaaS billing rollout

### Production Pilot
- normal Workspace Subscription/Entitlements;
- may be `TRIALING` or `ACTIVE + COMPED`;
- no special code bypass;
- owner recurring charge may be deferred.

### Commercial MVP
Before onboarding broader paying customers:
- hosted SaaS checkout;
- tokenized owner payment method;
- Subscription webhook;
- Invoice projection;
- PastDue/Grace handling;
- usage view;
- repeatable commercial onboarding.

One plan revision is enough initially.

---

## 17. MVP Autonomy Contract

| Capability | Pilot behavior |
|---|---|
| Identify service/request | AUTO |
| Collect intake | AUTO |
| Answer from verified Knowledge | AUTO |
| Vision analysis | AUTO |
| Portfolio retrieval | AUTO |
| Configured exact/range price | AUTO |
| Check availability | AUTO |
| Offer server-generated slots | AUTO |
| Create Hold after Client selection | AUTO |
| Create configured deposit/payment link | AUTO |
| Confirm Appointment | AUTO after valid Hold + accepted terms + required payment satisfied OR explicit NONE prepayment policy |
| Reminder/follow-up | AUTO via Automation Engine |
| Custom final tattoo price | OWNER / configured deterministic rule |
| Discount exception | OWNER |
| Refund | OWNER |
| Complex/unsupported request | ESCALATE |
| Health/medical advice | DISABLED / safe handoff |
| Minor-specific workflow | DISABLED MVP |
| Mark paid from Client statement | DISABLED |
| Change critical Business Rules | DISABLED |
| Change own autonomy/permissions | DISABLED |

Unknown/conflicting/low-authority critical information defaults to escalation.

---

## 18. Explicit exclusions

The following are deliberately **not MVP defects**:

- additional customer channels;
- voice/video;
- AI image generation;
- multi-resource/multi-location scheduling;
- recurring/group booking;
- external calendars;
- advanced pricing DSL/prediction;
- autonomous refunds;
- escrow/wallet/splits/payouts;
- marketing/reactivation;
- native mobile apps;
- full self-service workflow builder;
- advanced BI;
- unverified/direct foreign AI via VPN/proxy;
- arbitrary extra AI adapters beyond the selected RU_AGGREGATOR and DIRECT_PROVIDER implementations; uncontrolled cross-branch fallback;
- mandatory Redis;
- Kafka;
- Kubernetes;
- dedicated vector DB;
- Elasticsearch/OpenSearch;
- multi-region;
- enterprise SSO;
- dedicated per-tenant infrastructure.

---

## 19. Golden Journeys

### GJ-A — Standard New Tattoo
Client text/image → intake → matching/approved assessment → fixed/formula/Owner Quote → explicit acceptance → Order/Session → Hold → configured fixed/percent/full prepayment OR NONE → Appointment. First master exercises FIXED_DEPOSIT; test NONE and percentage variants with synthetic configurations.

### GJ-B — Owner Quote
Intake complete → price requires Owner → Action Center → Owner price → Quote → AI resumes → booking/payment.

### GJ-C — Unsupported / Complex
Unsupported/uncertain request → safe escalation → no fabricated feasibility/price.

### GJ-D — Slot Race
Two Clients select same slot → exactly one Hold/allocation succeeds → second receives conflict/new choice.

### GJ-E — Late Payment
Hold expires → payment later succeeds → payment retained → no fake Appointment → recovery/escalation.

### GJ-F — Reschedule / Cancel
Current Appointment → policy/availability → safe reallocation/cancel → history/reminders corrected → refund remains Owner-controlled.

### GJ-G — Human Takeover
Owner takes control → pending AI output suppressed → human replies → explicit resume from latest state.

### GJ-H — Follow-up Relevance
Client silent → one bounded follow-up if still relevant; already replied → automation SKIPPED.

### GJ-I — Prompt Injection
Client requests policy override/cross-tenant data/refund → no unauthorized data or state side effect.

### GJ-J — Dependency Failure
Provider transient failure → durable inbound/recoverable work → no duplicate or stale side effect after recovery.

---

## 19.1. Additional mandatory audit variants

- GJ-A: fixed, formula, Owner price; fixed deposit, exact-base percentage, NONE; range without exact percentage base must stop for clarification/Owner.
- GJ-D/F: self-overlapping reschedule, buffers, CalendarBlock conflict, expired Hold cleanup.
- GJ-G/J: stale worker/AI mutation after takeover; in-flight send UNKNOWN; branch switch after successful tool without duplicate mutation.
- GJ-I: same-Workspace/different-Client data/object access denial.
- GJ-J: PITR after external effect/privacy deletion; old-runtime fencing; verify-before-replay.
- Fiscalization: success/pending/failure/deadline/duplicate obligation tests before live payments.
- Notifications/owner decisions: closed Telegram reply window, delayed Owner Quote, stale approval and Client withdrawal.

---

## 20. Readiness Gates

All must be green.

### DOMAIN_READY
- Golden Journeys produce valid canonical state.
- Escaped double booking = 0.
- Duplicate payment/refund canonical effect = 0.
- Invalid critical state transition = 0.
- Cross-Workspace data/state corruption = 0.

### AI_READY
Critical suite:
- unauthorized money action = 0;
- invented payment success = 0;
- invented booked availability = 0;
- cross-tenant exposure = 0;
- takeover violation = 0;
- other critical security/safety violations = 0.

Non-critical first-vertical quality:
- exact thresholds are implemented in Stage 24;
- initial calibration target ≈ **95%+ correct domain/tool outcome** on curated eligible cases.

### SECURITY_READY
- tenant/RLS suite PASS;
- support grant scope/expiry PASS;
- webhook verification PASS;
- signed file authorization PASS;
- secret/log redaction PASS;
- critical injection suite PASS;
- production secrets/customer data are not normal developer-local assets.

### RELIABILITY_READY
- duplicate webhook/command/payment tests PASS;
- worker lease recovery PASS;
- Outbox redelivery PASS;
- concurrent booking PASS;
- Hold/payment race PASS;
- stale AIRun suppression PASS;
- AI/channel timeout recovery PASS;
- backup restore actually tested.

### BUSINESS_CONFIG_READY
Green:
- SERVICES;
- PRICING;
- SCHEDULING;
- PAYMENT_TERMS;
- KNOWLEDGE;
- CHANNEL;
- AUTONOMY.

Owner approves production configuration before publish.

### OPERATIONS_READY
Platform Ops can:
- locate unprocessed inbound;
- diagnose failed/stuck work;
- inspect channel/provider health;
- inspect payment mismatch;
- reconstruct AI/tool causal chain;
- safely Retry/Replay.

Critical alerts cover DB/inbound/interactive backlog/backup/channel/AI-provider/cost anomaly categories.

### PRIVACY_READY
Before real customer data:
- privacy notice/process;
- pilot/terms arrangement where appropriate;
- AI-processing disclosure;
- retention policy;
- support access policy;
- vendor/subprocessor inventory;
- payment-data boundary.

---

### FISCALIZATION_READY — conditional RU payment activation gate

Before enabling real Client payments: actual BusinessLegalProfile/FiscalizationProfile, receipt responsibility/deadlines, manual/provider evidence, Action Center failure handling and Runbook 21 must be operational. Test no missing/duplicate receipt obligation and no fabricated completion. Manual messaging/AI phases can proceed under their own gates; a red fiscal gate blocks real payment capability, not all inbound communication.

---

## 21. Pilot calibration

Initial calibration window:
- roughly **20–50 meaningful conversations**.

Track:
- eligible conversations;
- autonomous resolution;
- expected/unnecessary escalation;
- owner correction;
- missed escalation;
- response latency;
- failed sends/recovery;
- pricing/knowledge gaps;
- AI/provider cost.

Initial pilot targets:
- critical money/security/booking incidents: **0**;
- missed high-risk escalation: **0**;
- silently lost requests: **0**;
- duplicate booking/payment effects: **0**;
- serious incident reconstruction in Platform Ops: **100%**;
- eligible simple conversations autonomous: target **~70%+**;
- simple structured-intake owner correction: target **~10–15% or lower**.

These percentages are **calibration targets**, not permanent SLA/contractual thresholds.

`Eligible Simple Conversation` excludes workflows intentionally requiring Owner approval/quote/risk decision.

---

### Additional value metrics

Measure eligible share of all relevant inquiries, owner minutes and interventions per request, Owner waiting time, notification delivery/unavailability, next-outcome conversion and total cost per resolved journey. Small pilot samples do not establish rare-event safety. Numeric business targets remain calibration, not invented SLA.

## 22. Pilot success criteria

The pilot is successful when:

1. A real Tattoo Business can operate through Telegram with real customer text/images.
2. AI safely handles a meaningful share of eligible requests without owner supervision.
3. Owner is interrupted primarily for intentional decision points/exceptions.
4. Money/booking/tenant/security invariants remain intact.
5. Failures are observable, recoverable and explainable through Platform Ops.
6. Owner can take over any conversation reliably.
7. Product produces measurable operational value rather than merely generating messages.
8. AI/provider/storage costs are measurable per Workspace.
9. Real failures feed a sanitized regression/eval loop.
10. No bespoke code fork is required for the first Business's ordinary configured flow.

---

## 23. Commercial MVP exit criteria

Before wider paid onboarding:

- repeatable SaaS billing;
- repeatable deployment/runbooks;
- stable first-vertical EvalSuite;
- support process;
- repeatable onboarding without engineering code fork;
- minimum required owner self-service configuration;
- measured unit economics sufficient to price the initial plan;
- launch-market legal/privacy/payment obligations completed.

---

## 24. Items intentionally deferred beyond this document

- exact branch/model/API IDs and price-quality benchmark results pending Tattoo EvalSuite and route eligibility;
- exact first Business legal/tax/fiscalization provider;

- exact first Business identity;
- Business-specific legal/tax obligations inside the accepted RU launch market;
- exact Client Payment Provider;
- exact SaaS Billing Provider;
- final SKU/zone/retention/alert routing of the accepted Yandex-preferred RU infrastructure;
- exact SLO/RPO/RTO numbers;
- precise non-critical EvalSuite thresholds/repetition counts;
- fine-grained engineering tickets within the accepted M0–M16 sequence;
- provider-specific commands/evidence completing the accepted production runbooks;
- expansion to second industry/channel.

These are resolved in Stages 24–27 as appropriate.


---

## 25. Development sequencing reference

This document defines **WHAT** the first Production Pilot / Commercial MVP must contain.

Implementation order, milestone dependencies and feature Definition of Done are maintained in `07_DEVELOPMENT_ROADMAP.md`.

The roadmap may defer architecture concepts that are not required by this MVP, but cannot remove or weaken this document's hard acceptance criteria without an explicit scope/ADR update.


## Production deployment reference

Pilot deployment/readiness execution and incident recovery follow `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`.
