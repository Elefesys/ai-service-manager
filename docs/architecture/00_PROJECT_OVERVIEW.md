# AI Service Manager — Project Overview

**Architecture baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** pre-implementation / v0.28 audit pass 1; Architecture Freeze v1.0 pending  
**Завершены этапы:** 0–27

## 1. Что мы строим

AI Service Manager — multi-tenant SaaS-платформа для самозанятых и небольших сервисных бизнесов. Цель — автоматизировать работу администратора/менеджера: вести клиента от первого обращения до согласованной услуги, записи и оплаты, подключая владельца только там, где действительно требуется человеческое решение.

Базовый сценарий:

```text
Клиент пишет бизнесу
→ AI понимает запрос
→ собирает недостающие параметры
→ анализирует изображения/файлы при необходимости
→ сверяется с правилами, знаниями и портфолио
→ инициирует оценку/расчёт через специализированные сервисы
→ согласовывает условия и время
→ инициирует предоплату
→ создаёт запись
→ уведомляет владельца/клиента
→ сопровождает дальнейший процесс
```

## 2. Целевая аудитория

Приоритет:
1. Самозанятые, оказывающие услуги.
2. Небольшие сервисные бизнесы.
3. Позже — ИП/студии/команды с несколькими специалистами.

Примеры вертикалей: тату, маникюр, барберы, фотографы, мебель, ремонт, дизайн, репетиторы и другие услуги.

Первый production-клиент — тату-мастер (подтверждено пользователем). Тату также используется как stress-test универсальной архитектуры. Конкретный legal/tax profile, правила и параметры мастера уточняются при onboarding.

## 3. Основная архитектурная идея

Не создаётся отдельная нейросеть на каждого мастера. Персонализация бизнеса строится через:

```text
общий AI/application core
+ structured business configuration
+ Business Rules
+ Knowledge / RAG
+ Portfolio intelligence
+ Communication Profile
+ Industry / Service Workflow
+ Business Tools
```

Fine-tuning per workspace не используется по умолчанию.

## 4. Главный принцип

**LLM не является источником истины.**

LLM используется для понимания языка, извлечения намерений, рассуждения в разрешённых границах и формирования ответов. Цены, расписание, свободные слоты, платежи, ограничения и другие критические факты берутся из структурированной бизнес-логики и source-of-truth сервисов.

## 5. Высокоуровневая архитектура

```text
Channels (Telegram / VK / MAX / Web / ...)
        ↓
Channel Adapters
        ↓
Normalized Events
        ↓
Conversation Engine
        ↓
AI Orchestration / Agent
        ↓
Business Tools / Services
   ├─ Knowledge / RAG
   ├─ Portfolio
   ├─ Visual Design
   ├─ Pricing
   ├─ Scheduling
   ├─ Payments
   ├─ Notifications
   └─ Industry Workflows
        ↓
Business Logic
        ↓
PostgreSQL
```

Вспомогательные компоненты: Object Storage, Redis, pgvector, Audit, Inbox/Outbox, Observability и Security.

## 6. Ключевые уже принятые решения

- SaaS, а не отдельный бот/модель на каждого мастера.
- `Workspace` — tenant boundary.
- `Workspace != Business`; в MVP допустимо 1 Workspace = 1 Business.
- PostgreSQL — source of truth.
- Shared PostgreSQL + `workspace_id` + RLS.
- Object Storage — binary files; PostgreSQL — metadata.
- Redis не хранит единственную копию критических данных.
- pgvector достаточно для начального RAG.
- Принцип данных: **Normalized Core + Flexible Edge**.
- Telegram — первый канал, но core от него независим.
- Основной Telegram MVP transport: Profile Automation / connected business bot.
- Conversation и ServiceRequest — разные сущности.
- Message и ConversationTurn — разные сущности.
- Structured state выше memory/summary модели.
- Human takeover обязателен.
- Raw historical chats — сырьё для extraction, а не authoritative truth.
- Business Rules и Knowledge разделены.
- Knowledge имеет authority, provenance и revisions.
- PortfolioItem и AI GeneratedAsset разделены.
- Сначала ищется реальная подходящая работа, затем при необходимости создаётся AI-концепт.
- Workflow не является одной жёсткой цепочкой для всех профессий.
- Полная автономность — цель, а не обязательный режим первого production запуска.
- AI models скрыты за `ModelGateway`; business code использует логические ModelProfile, а не provider model IDs.
- Две переключаемые AI-ветви: `RU_AGGREGATOR` (PolzaAI — preferred candidate; GPTunnel — comparison/fallback candidate) и `DIRECT_PROVIDER` (официальные API разработчиков моделей). Внутри каждой — task-specific ModelProfiles; production mapping проходит Evals и data/provider eligibility.
- Application-consumed AI outputs используют versioned Structured Outputs / schemas.
- Canonical conversation memory остаётся в PostgreSQL; provider-side conversation/reasoning state — только optional optimization.
- `AIRun` отделён от `AIProviderCall`; AI usage измеряется по Workspace/task/profile.
- Prompt/configuration и output schemas версионируются.

## 6.1. Дополнения этапов 8–10

### Agent / Autonomy

- Customer-facing flow использует один `ConversationAgent`, а Pricing/Scheduling/Payments/Knowledge/Visual остаются application services/tools.
- Tools узкие, versioned, typed и не содержат произвольных SQL/HTTP/code capabilities.
- `ToolSetResolver` динамически ограничивает доступные tools по WorkflowStep, permissions и policy.
- Любой side effect проходит `ToolGateway → validation → PolicyEngine → application service`.
- Autonomy policy: `AUTO / REQUIRE_CONFIRMATION / ESCALATE / DISABLED`.
- Model confidence не является authorization mechanism; критические actions требуют evidence/preconditions.
- Owner approval хранит frozen action и повторно валидирует state перед исполнением.
- Deterministic system events не отправляются в LLM без необходимости.

### Industry / Workflow

- Профессии не создают отдельные backend-системы.
- Используются Universal Core + Workflow Archetypes + capabilities + Industry Packs + business/service overrides.
- Основные workflow families: Slot-Based, Custom Consultative, Event-Based, Onsite, Custom Production, Recurring Session, Project Delivery.
- `WorkflowDefinition / WorkflowRevision / WorkflowInstance / WorkflowStepInstance` оркестрируют процесс, но не заменяют domain state.
- Industry Pack является versioned template и не меняет существующий production business автоматически.
- Новая профессия может работать без готового Industry Pack через generic onboarding/configuration.

### Business Onboarding

- Onboarding — отдельная AI-assisted подсистема с `OnboardingAgent`.
- Поддерживаются Quick Start, Assisted Import и Full/Concierge режимы.
- Pipeline: source collection → normalization → candidate extraction → conflicts/missing data → adaptive questions → validation → simulation → owner approval → publish.
- AI работает с candidates/draft и не публикует критические production settings самостоятельно.
- Добавляется `BusinessConfigurationRelease` — immutable manifest совместно опубликованных revisions/builds.
- Readiness определяется blocking gates по Service, а не общим процентом заполнения.
- Первые production onboarding целесообразно проводить concierge/manual способом и затем автоматизировать наблюдаемый процесс.



## 6.1.1. Дополнения этапов 11–14

### Pricing
- Authoritative price создаёт `PricingEngine`/Owner decision, а не LLM.
- `PricingRevision` versioned и связан с `ServiceRevision`.
- `PriceCalculation` отделён от customer-facing `Quote`.
- Deposit/payment terms отделены от Pricing.

### Scheduling
- Availability вычисляется из rules/resources/allocations, а не хранится как заранее созданные free slots.
- `SchedulingPolicyRevision`, `AvailabilityOffer`, `ResourceAllocation`.
- Double booking предотвращается на DB-level.
- `ReservationHold → Appointment` конвертируется атомарно.

### Client → Business Payments
- `PaymentRequest`, `PaymentSession`, `PaymentTransaction`, `Refund` различаются.
- Деньги идут напрямую на merchant account бизнеса; платформа не является wallet/escrow в MVP.
- Provider webhook/API — authoritative online payment source.
- Raw card data не хранится.

### Automations / Notifications
- Automation Engine определяет when/why, Notification layer — whom/how.
- Persistent automation + relevance check перед action/send.
- NotificationIntent отделён от delivery attempts.
- Human takeover подавляет client-facing follow-ups.


## 6.1.2. Дополнения этапов 15–18

### SaaS Billing / Usage / Quotas

- `Workspace` является единицей SaaS billing; Client→Business payments остаются отдельным bounded context.
- `SaaSPlanRevision + Entitlements` заменяют hardcoded `if plan == ...`.
- Карты владельцев бизнеса токенизируются у billing provider; PAN/CVC не хранятся платформой.
- Billing state отделён от `WorkspaceServiceMode` (`NORMAL / GRACE / LIMITED / SUSPENDED`).
- `UsageEvent` — immutable usage ledger; observed usage отделён от billable usage.
- `QuotaReservation` используется для дорогих hard-quota операций; text AI получает continuity-oriented soft budget.

### Business Console / Platform Operations

- Business Console и Platform Operations Console — разные application surfaces.
- Business Console строится exception-first вокруг `Action Center`, Inbox, Calendar, Approvals/Escalations.
- UI всегда вызывает те же application/domain services, что AI; прямого DB bypass нет.
- Owner видит Decision Summary/evidence, но не chain-of-thought/raw model reasoning.
- Platform Support получает временный scope-limited `SupportAccessGrant`, а не WorkspaceMembership или скрытую impersonation.
- MVP UI — responsive web; native mobile apps отложены.

### Security / Privacy / Compliance

- Client messages/files/RAG/external content считаются untrusted; LLM не является security boundary.
- Tenant isolation остаётся defense-in-depth: WorkspaceContext + authorization + PostgreSQL RLS + tenant-safe FKs.
- Object Storage private; file access через authorization + short-lived signed URLs.
- Secrets живут в Secret Manager; production/dev/staging изолированы; production data не копируется на developer PC.
- AI получает только minimum necessary context через `AIDataPolicy`.
- Prompt injection/indirect injection допускаются как ожидаемая угроза и блокируются ToolGateway/PolicyEngine/RLS.
- Retention/delete/export охватывают canonical и derived data, включая embeddings.
- SecurityEvent, privacy requests, support access audit и incident response закреплены архитектурно.

### Reliability / Idempotency / Recovery

- Distributed exactly-once не предполагается: используется at-least-once delivery + idempotent processing.
- Внешний inbound сначала durable persist в Inbox, затем acknowledgement.
- Domain mutation + Outbox записываются одной DB transaction.
- Critical side effects используют stable idempotency keys/request fingerprints.
- Persistent jobs имеют lease/reclaim, retry classification, exponential backoff+jitter и DLQ.
- Ambiguous provider timeout может иметь `UNKNOWN` result; blind retry side effect запрещён.
- Redis не source of truth; PostgreSQL остаётся hard dependency canonical mutable runtime.
- Deployments используют backward-compatible `expand → migrate → contract`.
- Backup считается готовым только вместе с проверяемым restore/reconciliation runbook.


## 6.1.3. Дополнения этапов 19–22

### Infrastructure
- Stateless/disposable application compute; canonical state вынесен в managed PostgreSQL и private S3-compatible Object Storage.
- Backend остаётся modular monolith; API/Worker/Scheduler могут быть отдельными process одного Docker image.
- MVP jobs остаются PostgreSQL-backed; Redis/Kafka/Kubernetes не являются обязательными.
- LOCAL/STAGING/PRODUCTION разделены; immutable CI/container deployment; один production region.

### Observability / AI Cost / Analytics
- Metrics/Logs/Traces отделены от AuditEvent/SecurityEvent/UsageEvent.
- Instrumentation OpenTelemetry-compatible; vendor не фиксируется.
- Correlation/causation связывают webhook→job→AIRun→tool→outbox/provider.
- AI cost attribution считается по Workspace/feature/model/task и сверяется с provider costs.
- Product analytics строится вокруг domain outcomes.
- CostGuard отделён от QuotaService и Security RateLimit.

### Scaling
- Scaling decisions metric-driven.
- Порядок: optimize → vertical → horizontal stateless compute → workload pools → cache/specialized infra → partition/cells only when justified.
- Noisy-neighbor protection обязательна.
- PostgreSQL/pgvector/PostgreSQL Jobs остаются defaults до измеренной необходимости их выноса.
- Workspace — естественная future cell/shard placement unit.
- Modular monolith не дробится без конкретного extraction trigger.

### Testing + AI Evals
- Software tests и AI Evals — разные quality systems.
- Real PostgreSQL integration/RLS/concurrency/idempotency/recovery tests обязательны.
- AI evals проверяют behavior/tool/domain correctness, а не exact wording.
- Critical safety/money/payment/scheduling/security violations — hard release gates.
- Eval suites versioned и pin model/prompt/tool/schema/knowledge/config revisions.
- Release gates: Code → AI Safety/Domain → Quality/Cost/Latency → Controlled Promotion.


## 6.1.4. Stage 23 — MVP Scope

Первый production pilot сознательно сужен:

- первая vertical: **Tattoo**;
- основной autonomous flow: **new tattoo request**;
- один Workspace / Business / primary Owner-Provider / main Location / primary bookable Resource;
- один customer-facing channel: **Telegram**;
- customer media MVP: **text + image**;
- Vision / Portfolio matching / Knowledge RAG входят;
- AI image generation не входит;
- pricing: Owner-selected fixed / bounded owner-supplied formula / Owner Quote; indicative range is not an accepted final exact amount;
- scheduling: one provider resource, Hold, Appointment, cancel/simple reschedule;
- payment terms independent of pricing: no prepayment / fixed deposit / percentage deposit / full prepayment; first master uses fixed deposit, amount remains onboarding input;
- refunds/discount exceptions/custom final price требуют Owner;
- complex/cover-up/risky/medical/minor-specific cases эскалируются или отключены;
- Business Console и Platform Ops входят в pilot;
- first Business допускает TRIALING or ACTIVE+COMPED SaaS subscription; real owner charging требуется до broader commercial rollout;
- readiness определяется отдельными Domain / AI / Security / Reliability / BusinessConfig / Ops / Privacy gates;
- production pilot и public Commercial MVP — разные rollout milestones.

Точный canonical scope и acceptance criteria вынесены в `06_MVP_SPEC.md`.


## 6.1.5. Stage 24 — Development Roadmap

Development strategy is dependency-based and vertical-slice oriented:

- first target is a **Production Pilot**, not the full Commercial MVP;
- security, tenant isolation, tests, reliability and observability are built continuously rather than as final cleanup;
- implementation milestones M0–M12 lead to a pinned Pilot Release Candidate;
- M13–M16 convert pilot learning into repeatable onboarding, SaaS billing and commercial hardening;
- initial coding starts with secure Owner login + Telegram→Inbox→manual reply, not with an LLM prompt;
- AI is introduced first in read/query-only mode, then gains narrow mutation tools as deterministic domain services mature;
- Scheduling is stabilized before Client Payments;
- feature freeze precedes final pilot hardening;
- exact calendar estimates and framework/provider choices are intentionally not locked here.

Detailed canonical sequencing and milestone DoD are maintained in `07_DEVELOPMENT_ROADMAP.md`.


## 6.1.6. Stage 25 — Production Deployment / Runbooks

Stage 25 фиксирует production operating contract:

- immutable container artifacts + source/CI provenance;
- `ReleaseManifest` для composition application/schema/AI/platform release;
- отдельные Application / AI Configuration / Business Configuration release axes;
- privileged migration job + runtime least privilege;
- `Expand → Migrate → Contract` и запрет same-step destructive migration/cutover;
- readiness/smoke/observation gates before production activation;
- application / AI / business-config rollback paths separated from data restore;
- narrow subsystem kill switches и Workspace AI pause;
- managed PostgreSQL backup/PITR + **tested restore** as Pilot gate;
- restore-to-new-instance + invariant/privacy/provider reconciliation;
- SEV-1/2/3 incident handling and version-controlled runbooks;
- controlled first-Business cutover: manual channel path → AI → transactional tools → payments → automations;
- continuous integration with controlled production deployment for the first pilot.

Detailed operational procedures live in `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`.


## 6.1.7. Stages 26–27 — RU-first Production + Expansion

Stage 26 фиксирует первый реальный market/deployment profile:

- primary market до multi-region: **Russia**;
- primary data region: **Russia**;
- primary pilot language/currency: **Russian / RUB**;
- Russia реализуется через `MarketProfile=RU`, `DataResidencyPolicy` и `RegionalProviderBundle`, а не через `if country == RU` в domain code;
- рекомендуемый RU infrastructure bundle: Yandex Cloud managed PostgreSQL/Object Storage/Secrets/Registry/Observability;
- первый Client PaymentProvider: YooKassa hosted checkout, merchant connection принадлежит Business;
- `PaymentTransaction` отделён от `FiscalReceipt`; введён отдельный `FiscalizationService`/profile;
- RU AI strategy пересмотрена: production routing provider-neutral и region-qualified; direct foreign API through VPN/proxy is forbidden as production foundation;
- AI branches revised in v0.28: `RU_AGGREGATOR` prefers PolzaAI, compares GPTunnel; `DIRECT_PROVIDER` uses official model-developer APIs. Branch is independent of ProviderExecutionClass; aggregator does not imply RU-local execution;
- any external route may receive only policy-eligible/minimized context; actual processing location, retention and provider/upstream eligibility must be recorded;
- model choice is task-specific and Eval-driven, not one global model brand.

Stage 27 defines expansion order:

`first RU Tattoo → repeatable RU Tattoo → Commercial RU Tattoo → small studios/multi-provider → second RU industry → additional RU channels → voice/image capabilities → multi-industry RU SaaS → first foreign MarketProfile → regional Cells / true multi-region`.

Expansion is evidence-driven, one major axis at a time where practical. New IndustryPacks/Channels/AI models have explicit maturity states and release gates.

## 6.2. Delivery Horizon

Помимо архитектурного статуса используется горизонт реализации:

- **PRODUCTION_PILOT** — первый реальный бизнес; **COMMERCIAL_MVP** — повторяемое платное подключение. Старые метки **MVP** уточняются через `06_MVP_SPEC.md`; они не расширяют pilot scope.
- **CORE_POST_MVP** — ожидаемая часть основного продукта после доказанного MVP; архитектура должна учитывать её заранее.
- **FUTURE_OPTIONAL** — возможное расширение или vertical-specific capability; не должно усложнять MVP без необходимости.

`LOCKED / OPEN / DEFERRED / REVISED` отвечают на вопрос *насколько решение зафиксировано*, а `MVP / CORE_POST_MVP / FUTURE_OPTIONAL` — *когда его реализовывать*.

## 6.3. v0.28 — Audit pass 1 / user decisions

- AIProviderBranch and immutable AIRoutingRevision support config-only branch switching with the same domain state/tools.
- Price authority and payment terms are independent owner settings; deposit is derived after agreement, never guessed by AI.
- Duration authority is independent of price: fixed/configured rule or Owner; historical duration cases produce reviewed candidates, not automatic production rules.
- QuoteAcceptance → ServiceOrder/ServiceSession → active Hold → payment-required/no-prepayment branch → Appointment is explicit in Spec §11.10 / §13.12.
- Client-scoped tool access, takeover/mutation guards, safe overlapping reschedule, restore fencing and fiscalization gates are clarified.
- Open items with owner inputs/technical evidence are tracked in `04_OPEN_QUESTIONS.md`, OPEN-079 onward. No made-up first-master price, duration or deposit amount is published.

## 7. Текущий roadmap

```text
[✓] 0–25. Architecture / MVP / Development / Production Runbooks
[✓] 26. First Production Client — RU-first market/provider/compliance profile
[✓] 27. Expansion — tenants / industries / channels / AI capabilities / regions

Architecture roadmap 0–27 complete.
Next engineering step: implementation from `07_DEVELOPMENT_ROADMAP.md`, with RU production bindings from Stages 26–27.
```

## 8. Канонические файлы

- `01_ARCHITECTURE_SPEC.md` — актуальная архитектура.
- `02_ARCHITECTURE_DECISIONS.md` — почему приняты ключевые решения.
- `03_GLOSSARY.md` — единый словарь.
- `04_OPEN_QUESTIONS.md` — нерешённые вопросы.
- `05_CHANGELOG.md` — значимые изменения архитектуры.
- `06_MVP_SPEC.md` — canonical scope, exclusions, Golden Journeys и acceptance criteria первого production MVP.
- `07_DEVELOPMENT_ROADMAP.md` — canonical dependency order, milestones, implementation DoD и Pilot→Commercial sequence.
- `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md` — production deployment contract, cutover/rollback/restore procedures и incident runbooks.

Для архитектурных решений приоритет имеет `01_ARCHITECTURE_SPEC.md`. Для границ и acceptance criteria первого релиза приоритет имеет `06_MVP_SPEC.md`. Для порядка реализации и milestone DoD первого релиза приоритет имеет `07_DEVELOPMENT_ROADMAP.md`. Для production deployment/recovery procedures приоритет имеет `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`. MVP/Roadmap документы не могут ослаблять архитектурные hard constraints.

## 9. Статусы решений

- **LOCKED** — принято.
- **DEFERRED** — сознательно отложено до конкретного этапа.
- **OPEN** — вопрос обнаружен, решение не принято.
- **REVISED** — старое решение заменено новым.

## 10. Правило дальнейшей работы

Архитектурный чат используется для обсуждения и пересмотра. Project хранит только актуальный baseline. Канонические файлы обновляются пакетно через несколько завершённых этапов или после значимого архитектурного пересмотра. Перед production-разработкой формируется Architecture Freeze v1.0.
