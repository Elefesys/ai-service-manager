# AI Service Manager — Architecture Baseline v0.28

Дата сборки: 2026-09-14. Архитектурная версия: v0.28 от 2026-09-09.
План реализации: 2026-09-10, основан на v0.28.

## Назначение и статус

Единый снимок десяти предоставленных файлов проекта: архитектура 00–08 и сопровождающий план реализации 09. Ниже включены полные исходные тексты без изменения содержания. Архив содержит те же десять файлов под их каноническими именами.

Это упаковка существующей версии, а не новое архитектурное решение. Architecture Freeze v1.0 остаётся pending; сборка не подтверждает реализацию, проверку API или готовность production.

Канонические источники — отдельные файлы проекта, прежде всего 01_ARCHITECTURE_SPEC.md и действующие ADR в 02_ARCHITECTURE_DECISIONS.md. При последующих согласованных изменениях актуальные файлы имеют приоритет над этим снимком. Исторические решения и changelog сохранены; их следует читать с учётом явных отметок о пересмотре.

LOCKED — принятое решение; DEFERRED — сознательно отложенное; OPEN — нерешённый вопрос; REVISED — пересмотренное решение, с учётом указанной в ADR замены. Исходные обозначения Accepted и другие статусы не переименованы.

Основные изменения v0.28 описаны в 05_CHANGELOG.md и ADR-259–274: две переключаемые AI-ветви, тату как первый отраслевой сценарий, независимые режимы цены и предоплаты, подтверждаемая правилами или владельцем продолжительность, уточнения согласования, авторизации, takeover, платежей и восстановления. Конкретные модели остаются кандидатами для оценки; эта сборка не проверяет внешние каталоги.

Разработку общего каркаса можно вести без индивидуального прайса и портфолио мастера; порядок и тестовые конфигурации приведены в 09_IMPLEMENTATION_PLAN.md. Открытые инженерные вопросы закрываются к соответствующим этапам, параметры бизнеса — перед его подключением.

## Состав снимка и контрольные суммы SHA-256

| Файл | SHA-256 |
|---|---|
| 00_PROJECT_OVERVIEW.md | `c5f3cfc741b0978b8eaabb6a8f3da7c9640b01327935327014d88b45b23d5440` |
| 01_ARCHITECTURE_SPEC.md | `3aebed8c08e3490c766bd8e8b9baaf8079dfe3cd0e75674bbc5ff4131d094ad4` |
| 02_ARCHITECTURE_DECISIONS.md | `6f78fc234effc6a5fe6362243105464eccefe1637188f7747e10f2c9c1e40f5d` |
| 03_GLOSSARY.md | `2e264e31379df155a96c493dba3665ddae4c34325ca854b2353eab24a3594579` |
| 04_OPEN_QUESTIONS.md | `d7eb05c95317fb6a1bd3626a0e1e91ede387164f683d60eb1a3a829b26a3015a` |
| 05_CHANGELOG.md | `4723bc5fee81d8afd8a046d6c4538a66e9aacc4b8f2db72b7758f1f6f7bf9790` |
| 06_MVP_SPEC.md | `c514d3a75f2bbcd147ca491726009b4e3b706256d0cdc199cd7ba9d4223b5396` |
| 07_DEVELOPMENT_ROADMAP.md | `66321aacc9b2fe275619f17943662bcd5d62e023e501c3c5efd63a6e5a68ef2e` |
| 08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md | `17f2d31ffad282d1af36f5c6198fd56e767a539e35b63aa247c83117d1d5eabd` |
| 09_IMPLEMENTATION_PLAN.md | `647847fe4f8cf9115f577411266bd1ba0e732d24ebc35e0c0227a465bbbe4d60` |

## Полные тексты исходных документов


---

## Исходный файл: 00_PROJECT_OVERVIEW.md

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


---

## Исходный файл: 01_ARCHITECTURE_SPEC.md

# AI Service Manager — Architecture Specification

**Baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** stages 0–27 accepted; v0.28 audit pass 1 + user-approved revisions; pre-implementation, Architecture Freeze v1.0 pending

Этот документ — каноническое описание актуальной архитектуры. История и причины решений находятся в `02_ARCHITECTURE_DECISIONS.md`.

---

# 0. Product Boundaries — LOCKED

## 0.1. Назначение

Платформа автоматизирует функции менеджера/администратора сервисного бизнеса:

- принимает обращения;
- понимает намерение клиента;
- ведёт консультацию;
- собирает параметры услуги;
- анализирует изображения/файлы;
- сверяется с правилами, знаниями и портфолио;
- помогает визуализировать заказ;
- инициирует оценку и pricing через специализированные компоненты;
- согласовывает доступное время;
- инициирует оплату/предоплату;
- создаёт/изменяет записи;
- отправляет уведомления;
- эскалирует нестандартные ситуации владельцу.

## 0.2. Запрещённые архитектурные допущения

Система не должна:

- считать LLM источником бизнес-фактов;
- позволять LLM произвольный SQL/доступ к БД;
- позволять LLM выбирать `workspace_id`;
- обещать цену/время/условия без authoritative source;
- использовать один «магический prompt» вместо бизнес-архитектуры;
- выдавать AI-generated изображение за реальную работу мастера;
- строить фундамент на userbot/неофициальном обходе channel restrictions;
- делать fine-tuned model per workspace обязательным подходом.

## 0.3. Универсальность

Core универсален. Различия профессий задаются Intake Schema, Business Rules, Workflow Definition, отраслевыми атрибутами, доступными tools, Knowledge/Portfolio и escalation policy.

**LOCKED:** сущности универсальны, но последовательность их использования определяется workflow конкретной услуги.

---

# 1. Domain Model — LOCKED

## 1.1. Platform и business scope

### UserAccount
Учётная запись пользователя SaaS.

### Workspace
Tenant/security boundary.

### WorkspaceMembership
Связь `UserAccount ↔ Workspace`, включающая роль/permissions.

### Business
Конкретный бизнес внутри Workspace.

**LOCKED:** `Workspace != Business`.

В MVP допустимо:
```text
1 Workspace = 1 Business
```

### BusinessMember
Человек, участвующий в бизнесе: OWNER, ADMIN, PROVIDER и т. п. Может существовать без UserAccount.

### Location
Место оказания услуги.

### Resource
Ограниченный ресурс: мастер, кабинет, оборудование и т. п.

## 1.2. Service model

### Service
Стабильная сущность каталога услуг.

### ServiceRevision
Immutable-версия конфигурации Service.

### Intake Schema
Схема данных, необходимых для конкретной услуги.

Отраслевые параметры не превращаются в глобальный набор колонок. Они задаются schema-driven configuration/JSONB.

## 1.3. Client и communication

### Client
Клиент конкретного Workspace/Business.

**LOCKED:** Client не глобален между Workspace.

### ClientIdentity
Идентификатор клиента в канале/контакте: Telegram, VK, MAX, phone, email и т. п.

### ChannelConnection
Подключение внешнего канала к Business.

### Conversation
Диалог Client ↔ Business. Может содержать несколько ServiceRequest/Order.

### Message
Одно входящее/исходящее сообщение.

Sender types:
- CLIENT;
- AI;
- BUSINESS_MEMBER;
- SYSTEM.

### FileObject
Canonical metadata физического файла. Binary хранится в Object Storage.

## 1.4. Consultation / Sales

### ServiceRequest
Структурированное описание того, что хочет клиент.

### ServiceAssessment
Оценка выполнимости/сложности/продолжительности/объёма.

### Quote
Коммерческое предложение. После отправки клиенту не переписывается; новые условия создают новый Quote.

### QuoteLine
Компонент Quote.

### ServiceOrder
Согласованный заказ.

### ServiceSession
Логическая часть выполнения ServiceOrder. Может существовать без назначенной даты.

## 1.5. Scheduling

### ReservationHold
Временное удержание слота.

### Appointment
Конкретный подтверждённый временной интервал.

**LOCKED:** ReservationHold != Appointment.

## 1.6. Payments

### PaymentRequest
Бизнесовое требование оплатить.

### PaymentTransaction
Provider payment operation with stable identity and lifecycle; a technical HTTP retry is not another money movement. Success must be provider-authoritative; Refund is separate.

**LOCKED:** PaymentRequest != PaymentTransaction.

## 1.7. Operations

### Escalation
Запрос участия человека. Не обязательно означает полный takeover.

### NotificationIntent
Canonical business notification need; Notification is a legacy generic label. Delivery attempts are separate (§14.5).

### AuditEvent
История важного действия и actor.

## 1.8. Независимые state machines

Нет одного глобального status всего процесса. Собственные lifecycle имеют ServiceRequest, Assessment, Quote, Order, Session, Hold, Appointment, PaymentRequest, PaymentTransaction, Conversation processing, KnowledgeBuild и ChannelConnection.

---

# 2. Multi-tenancy — LOCKED

## 2.1. Tenant boundary

`Workspace` — единственная tenant boundary. Используется `workspace_id`. Отдельный `tenant_id` не создаётся.

`business_id` отвечает за business context и не заменяет `workspace_id`.

## 2.2. Shared PostgreSQL

MVP:
```text
1 PostgreSQL
platform schema
shared app schema
many workspaces
```

Не используем database-per-tenant и schema-per-tenant.

## 2.3. Workspace-scoped data

Практически все business tables имеют `workspace_id NOT NULL`: clients, services, conversations, messages, portfolio, requests, quotes, orders, appointments, payments, knowledge, audit, notifications и т. д.

## 2.4. Global platform data

Как минимум:
- user_accounts;
- workspaces;
- workspace_memberships;
- channel_routes;
- позднее plans/subscriptions/platform usage.

## 2.5. WorkspaceContext

Любая business operation выполняется внутри server-side контекста:

```text
workspace_id
actor
permissions
request/correlation id
```

Workspace не берётся из свободного текста Client или LLM.

## 2.6. Channel routing

```text
external route key
→ ChannelRoute
→ workspace_id
→ WorkspaceContext
```

ChannelRoute маршрутизирует, но не хранит клиентскую историю.

## 2.7. Defense in depth

Tenant isolation состоит из:
1. API authorization;
2. WorkspaceMembership/permissions;
3. WorkspaceContext;
4. tenant-aware repositories;
5. PostgreSQL RLS;
6. tenant-safe FK/constraints;
7. Object Storage isolation;
8. cache namespace isolation;
9. RAG/vector scope isolation;
10. AI tool isolation.

## 2.8. PostgreSQL RLS

Runtime DB role:
- не superuser;
- без `BYPASSRLS`;
- не владелец tenant tables.

Current workspace устанавливается transaction-locally, чтобы connection pool не переносил tenant context между запросами.

## 2.9. Tenant-safe relationships

Для критических связей предпочтительны ограничения вида:

```text
(workspace_id, client_id)
→ clients(workspace_id, id)
```

## 2.10. AI isolation

AI tools не принимают произвольный `workspace_id`.

Плохо:
```text
search_portfolio(workspace_id, query)
```

Правильно:
```text
search_portfolio(query)
```

Workspace наследуется из WorkspaceContext.

## 2.11. Other storage

### Object Storage
```text
workspaces/{workspace_id}/...
```
Bucket private.

### Redis
Tenant-aware keys:
```text
ws:{workspace_id}:...
```
Redis не является source of truth.

### Jobs
Tenant job восстанавливает WorkspaceContext до работы с данными.

### RAG
Любой retrieval ограничен workspace scope.

## 2.11.1. Same-Workspace Client authorization — LOCKED

RLS workspace scope is necessary but insufficient for Client-facing tools. Every object ID is additionally authorized against trusted Business/Client/Conversation/Request/Order relations and the specific action. A Client cannot view/change another Client's Appointment/payment/file inside the same Workspace. Query tools distinguish shared approved Business Knowledge/Portfolio from private Client history. Add same-Workspace/different-Client tests for queries, commands, files, signed actions and notifications, including forged IDs. Internal AI principal never inherits blanket Owner access.

## 2.12. Permissions

Начальные роли: OWNER, ADMIN, PROVIDER.

Authorization строится через permissions/capabilities.

AI — отдельный service principal, не OWNER.

---

# 3. Data Architecture — LOCKED

## 3.1. Роли хранилищ

### PostgreSQL
Source of truth для business state, clients, conversations, services, requests, assessments, quotes, orders, appointments, payment state, knowledge, audit, inbox/outbox.

### Object Storage
Source of truth для binary assets.

### pgvector
Начальный vector layer внутри PostgreSQL. Embeddings восстановимы.

### Redis
Cache, rate limits, locks, short-lived state/queue support. Не содержит единственную копию критического состояния.

## 3.2. PostgreSQL schemas

```text
platform.*
app.*
```

`platform.*` — SaaS/global data.  
`app.*` — tenant business data с workspace_id.

Это не schema-per-tenant.

## 3.3. IDs

Основные IDs — UUID. Предпочтительно UUIDv7 при PostgreSQL 18.

UUID не является authorization mechanism.

## 3.4. Time

Абсолютные timestamps — `timestamptz`. Timezone бизнеса/локации хранится отдельно.

## 3.5. Money

Не использовать float.

Предпочтительно:
```text
amount_minor BIGINT
currency CHAR(3)
```

Оценка диапазона:
```text
estimated_min_minor
estimated_max_minor
currency
```

## 3.6. Duration

Для business duration — `duration_minutes`.  
Для Appointment — `start_at`, `end_at`.

## 3.7. Status

Предпочтительно `TEXT + CHECK` в БД и строгий enum/type в приложении.

## 3.8. JSONB

Принцип:
```text
Normalized Core + Flexible Edge
```

Колонки — для keys, money, statuses, timestamps, relationships, часто используемых критических полей.

JSONB — для отраслевого intake, portfolio attributes, provider metadata, snapshots, гибких схем.

## 3.9. Revisions / immutability

- ServiceRevision и RuleRevision сохраняют исторический смысл конфигурации.
- Отправленный Quote не переписывается.
- Существенно изменённый Assessment создаёт новую версию/новую запись.
- Исторические коммерческие решения должны быть воспроизводимыми.

## 3.10. Files

PostgreSQL хранит:
```text
id
workspace_id
storage_key
mime_type
size_bytes
sha256
processing_status
created_at
```

Binary — Object Storage.

## 3.11. Media analysis

Vision/AI-analysis — отдельный результат, не свойство оригинального файла. Один FileObject можно анализировать повторно разными моделями/версиями.

## 3.12. Optimistic concurrency

Критические mutable entities имеют `version`. Update проверяет известную версию и не перезаписывает параллельное изменение молча.

## 3.13. Transactions

Связанные изменения business state атомарны в PostgreSQL transaction. External API calls не удерживают SQL transaction.

## 3.14. Inbox / Outbox

- `InboxEvent` — дедупликация/надёжная обработка внешних событий.
- `OutboxEvent` — надёжное инициирование внешних/async действий после commit.
- `AuditEvent != OutboxEvent`.
- Event Sourcing не используется.

## 3.15. Delete policy

Универсальный soft-delete во всех таблицах не используется.

- конфигурационные объекты → archive;
- финансовая/аудит-история → сохраняется;
- privacy deletion → отдельная процедура удаления/обезличивания.

## 3.16. Логические семейства таблиц

Platform:
- user_accounts
- workspaces
- workspace_memberships
- channel_routes

Business:
- businesses
- business_members
- locations
- resources

Services:
- services
- service_revisions
- business_rules
- rule_revisions

Channels:
- channel_connections

Clients/Communication:
- clients
- client_identities
- conversations
- messages
- files
- message_files
- conversation_turns / turn_messages (предпочтительно; SQL позже)

Portfolio/Media:
- portfolio_items
- portfolio_files
- media_analyses
- generated_assets / generated_asset_sources (логические сущности; SQL позже)

Sales:
- service_requests
- service_assessments
- quotes
- quote_lines

Delivery:
- service_orders
- service_sessions
- reservation_holds
- appointments

Payments:
- payment_requests
- payment_transactions

Knowledge:
- knowledge_sources
- knowledge_items
- knowledge_chunks
- historical_cases
- communication_profiles
- approved_conversation_examples
- knowledge_candidates
- knowledge_builds

Operations:
- escalations
- notifications
- audit_events
- inbox_events
- outbox_events

---

# 4. Channels / Telegram — LOCKED

## 4.1. Channel abstraction

```text
Telegram / VK / MAX / Web
→ Channel Adapter
→ Normalized Event
→ Conversation Engine
```

Концептуальный adapter умеет receive/send text/send media/edit/delete/mark read/download/get capabilities. Не каждый transport обязан поддерживать всё.

## 4.2. Telegram modes

### Primary MVP
**Profile Automation / connected business bot.**

Клиент пишет обычному аккаунту мастера; подключённый bot получает разрешённые сообщения и отвечает от имени аккаунта в рамках Telegram capabilities.

На дату baseline официальная документация подтверждает:
- Premium не требуется для подключения connected business bot;
- `can_reply` действует в подходящих приватных чатах с входящим сообщением за последние 24 часа;
- сейчас к пользовательскому аккаунту подключается один business bot.

Это mutable external assumptions.

### Alternative
Standalone / managed Telegram Bot — fallback/дополнительный route, не обязательный в первом MVP.

## 4.3. ChannelCapabilities

Как минимум:
```text
receive_messages
reply
proactive_messages
send_media
edit
delete
mark_read
reply_window
buttons/actions
```

## 4.4. ChannelConnection

Концептуально:
```text
id
workspace_id
business_id
provider
mode
status
external_account_id
external_account_name
capabilities
rights
connected_at
last_sync_at
disconnected_at
credential_reference
```

## 4.5. ChannelRoute

Platform table:
```text
provider
route_type
route_key
workspace_id
channel_connection_id
```

## 4.6. Telegram inbound pipeline

```text
Webhook
→ verify
→ InboxEvent
→ deduplicate
→ ChannelRoute
→ WorkspaceContext
→ normalize
→ persist Client/Conversation/Message
→ download attachments
→ Conversation Engine
```

Длительный AI call не выполняется до надёжного сохранения входящего события.

## 4.7. External identity

```text
workspace_id + provider + external_user_id
→ ClientIdentity
```

Cross-workspace Client identities не объединяются автоматически.

## 4.8. Provider events

Нормализуются как минимум:
- message received;
- edited;
- deleted;
- reply;
- media group;
- structured user action;
- connection lifecycle.

## 4.9. Files

Provider file ID не является canonical object:

```text
Provider file → download → Object Storage → FileObject
```

## 4.10. Human takeover

Native Telegram pause может использоваться как UX, но channel-independent ConversationControl остаётся внутренним механизмом.

## 4.11. Conversation vs Notification

Conversation Channel и Notification Route разделены. Если один transport не может отправить proactive notification, Notification Engine позже выбирает другой route или фиксирует недоставимость.

## 4.12. Official APIs only

Не строить product foundation на userbot/эмуляции пользовательской Telegram-сессии ради обхода ограничений.

---

# 5. Conversation Engine — LOCKED

## 5.1. Responsibility

Conversation Engine — backend orchestration layer, который:
- принимает normalized events;
- формирует semantic turns;
- разрешает context;
- связывает turn с business objects;
- обновляет structured state;
- определяет, нужен AI, deterministic action или tool;
- координирует response;
- проверяет актуальность перед отправкой.

Conversation Engine не является LLM.

## 5.2. Message vs ConversationTurn

Несколько быстрых Messages могут стать одним Turn. Turn aggregation учитывает media group, тип сообщения, debounce и conversation state.

Structured UserAction может обрабатываться сразу.

## 5.3. ConversationState

Компактное состояние:
```text
active_request_id
active order references
current topic
control_mode
processing_state
awaiting_response_to
last offered options
pending actions
version
last activity
```

## 5.4. Multiple requests

Один Conversation может иметь несколько ServiceRequest. ContextResolver/RequestRouter решает, к какому объекту относится новый Turn. При существенной неоднозначности задаётся clarification.

## 5.5. Structured extraction

AI извлекает candidate facts:
```text
field
value
confidence
evidence/source
```

Перед записью — schema validation.

Explicit client fact и AI-inferred value различаются.

## 5.6. Conflicts

Явное новое значение может заменить старое с provenance/audit. Неявный конфликт приводит к clarification.

## 5.7. Missing fields

Intake Schema определяет заполненные, missing, conflicting и inferred-but-unconfirmed поля. AI задаёт вопросы естественно, не превращая чат в жёсткую форму.

## 5.8. Context Builder

Приоритет:
1. Hard Rules/Policies.
2. Structured current state.
3. Latest explicit turns.
4. Verified Knowledge.
5. Portfolio/visual context.
6. Conversation Summary.
7. Approved historical examples.

Structured state выше summary.

## 5.9. Summary

Conversation Summary — производный context helper, не source of truth.

## 5.10. Staleness / relevance

Conversation имеет `version`. AI/async run фиксирует input version. Перед user-visible action проверяются:
- current version;
- control mode;
- channel capability;
- актуальность результата.

Устаревший response не отправляется.

## 5.11. Processing model

```text
serialization per conversation
+
parallelism across conversations
```

Serialization/CAS principle resolved in §18.5; concrete transaction/fencing mechanics are validated at M3, not an unresolved agent architecture question.

## 5.12. Human takeover

MVP:
- AI;
- HUMAN.

В HUMAN автоматическая отправка AI запрещена; pending AI outputs становятся stale/cancelled.

## 5.12.1. Control and in-flight effects — LOCKED

ConversationControl has a monotonic control generation. New AIRuns, AI mutations and AI sends capture it and recheck current control/permissions/preconditions immediately before execution. HUMAN denies new AI commands and AI conversational sends. Deterministic inbound/payment reconciliation, expiry and manual owner operations continue.

Owner takeover and command admission share a serialized/CAS boundary so a queued AI action cannot execute after losing authority. Leases are not sufficient; stale workers must fail generation/fencing checks. A side effect committed before takeover is retained and displayed, never blindly replayed or rolled back.

External send already accepted/in flight cannot be recalled by a DB toggle. Persist dispatch state; suppress unsent output; report any unresolved in-flight outcome. No claim of atomic exactly-once across DB and Telegram. Exact transport reconciliation capabilities are validated at M2–M3.

Client-facing follow-ups are suppressed in HUMAN. Deterministic transactional notices have an explicit category policy; conservative Pilot default routes them to owner review during HUMAN, while preserving canonical payment/booking processing. Exact business exceptions are OPEN-083.

## 5.13. Escalation

Escalation может запросить решение владельца без полного takeover и затем вернуть управление AI.

## 5.14. Processing states

Допускаются:
- WAITING_FOR_CLIENT;
- WAITING_FOR_HUMAN;
- WAITING_FOR_PAYMENT;
- WAITING_FOR_EXTERNAL_SERVICE;
- READY_TO_RESPOND.

Это не заменяет business entity state machines.

## 5.15. Response model

ConversationResponse может содержать:
- text;
- media;
- actions/buttons;
- references.

Точные structured actions по возможности обрабатываются без LLM.

## 5.16. Visual intent

Поддерживаем логические intent:
- NONE;
- SHOW_PORTFOLIO;
- GENERATE_FROM_DESCRIPTION;
- COMBINE_REFERENCES;
- ADAPT_REFERENCE;
- CREATE_VARIATIONS.

## 5.17. Visual Design Service

Conversation Engine решает, **когда и зачем** нужна визуальная операция. Отдельный Visual/Image service создаёт GeneratedAsset.

Portfolio-first:
```text
find real relevant portfolio
→ if insufficient
offer/generate AI concept
```

## 5.18. GeneratedAsset

GeneratedAsset:
- отдельно от PortfolioItem/client original;
- имеет purpose;
- имеет provenance/source assets;
- может иметь revision lineage;
- не считается реальной выполненной работой;
- не является автоматически техническим чертежом/финальным production artifact.

## 5.19. Delayed results

Любой delayed result (LLM, image, payment, calendar, notification) перед user-visible action проверяет relevance.

## 5.20. Boundaries

Conversation Engine не реализует Pricing, Scheduling, Payments, RAG internals, Image Generation и Industry Rules самостоятельно.

---

# 6. Knowledge / RAG — LOCKED

## 6.1. Authority hierarchy

Приоритет источников примерно:
1. Business Rules.
2. Structured Service/Business Configuration.
3. Pricing/Scheduling/Policy source of truth.
4. Current structured Request/Order state.
5. Master-confirmed/curated Knowledge.
6. Portfolio.
7. Approved historical patterns/cases.
8. Raw historical conversations.

## 6.2. Hard Facts vs Knowledge

Hard facts хранятся структурированно: цены, график, депозит, ограничения, eligibility, booking rules.

RAG — для FAQ, объяснений, подготовки, aftercare/guidance, описаний, возражений, опыта.

## 6.3. Ingestion pipeline

```text
Raw Sources
→ Parse/Normalize
→ Classify
→ Extract Facts/Patterns
→ Deduplicate
→ Detect Conflicts
→ Knowledge Candidates
→ Owner Questions/Review
→ Approved Knowledge
→ Chunk
→ Embed/Index
→ Published KnowledgeBuild
```

## 6.4. Historical conversations

Используются для:
- candidate rules;
- FAQ;
- communication style;
- representative examples;
- HistoricalCases;
- continuous learning.

Критические правила автоматически не публикуются.

## 6.5. Authority

Примерные уровни:
- MASTER_CONFIRMED;
- OFFICIAL_BUSINESS_DOCUMENT;
- STRUCTURED_BUSINESS_DATA;
- CURATED;
- HISTORICAL;
- AI_INFERRED.

Retrieval учитывает authority, recency и service relevance.

## 6.6. Knowledge objects

- KnowledgeSource — сырой источник.
- KnowledgeItem — нормализованное знание.
- KnowledgeChunk — search unit.
- HistoricalCase — структурированный прошлый кейс.
- CommunicationProfile — профиль стиля.
- ApprovedConversationExample — representative example.
- KnowledgeCandidate — предложение до подтверждения.
- KnowledgeBuild — валидированный опубликованный набор знаний.

## 6.7. Effective dates / revisions

Knowledge/Rules могут иметь status, revision, effective_from/effective_until.

## 6.8. KnowledgeBuild

Новый build проходит:
```text
DRAFT → VALIDATING → READY → PUBLISHED
```

Если build невалиден, previous published build остаётся активным.

## 6.9. Chunking

Semantic sections предпочтительнее тупого fixed-size split. Chunk должен быть максимально самодостаточным.

Metadata:
```text
workspace_id
knowledge_item_id
category
service_id
authority
language
effective dates
content_hash
```

## 6.10. Embeddings

Начальная архитектура: PostgreSQL + pgvector.

Embedding — search index, не canonical knowledge.

Embedding provider/model is selected by `ModelProfile + DataResidencyPolicy + ProviderExecutionClass`.

For RU production, embedding candidates must be eligible for the actual task/data policy, including when reached through RU_AGGREGATOR. No provider/model is a universal embedding default; direct text-embedding-3-small is an evaluation candidate, not automatic RU approval. Query and stored projection must use a compatible EmbeddingProfile across branch changes.

## 6.11. Hybrid retrieval

```text
Structured Filters
+
Semantic Search
+
Keyword/Full-text
→ Merge
→ Rerank
→ Authority/Recency/Service relevance
→ Deduplicate
→ Context Pack
```

Начать можно с exact vector search. Approximate indexes — по измеренной необходимости.

## 6.12. Retrieval scopes

Не использовать `search_everything()`.

Scopes:
- BUSINESS_KNOWLEDGE;
- CLIENT_HISTORY;
- PORTFOLIO;
- HISTORICAL_CASES;
- позже PLATFORM_INDUSTRY_KNOWLEDGE.

## 6.13. Communication style

Используются:
```text
CommunicationProfile
+ ApprovedConversationExamples
+ current conversation
```

Fine-tuning — только если измеренное качество окажется недостаточным.

## 6.14. Portfolio intelligence

PortfolioItem остаётся canonical entity.

MVP visual search:
```text
Portfolio image
→ Vision Analysis
→ structured attributes + normalized text description
→ text embedding
```

Client reference проходит аналогичный pipeline. Поиск объединяет structured filters, semantic representation и metadata.

Dedicated multimodal visual embedding может быть добавлен позже.

## 6.15. Portfolio evidence

AI/Assessment должны уметь ссылаться на реальные PortfolioItem, использованные как evidence.

Похожая работа не означает автоматически, что бизнес принимает такой заказ сейчас — это проверяется Rules/Service Configuration.

## 6.16. Platform Industry Knowledge

Допускаются platform-curated knowledge packs, но они отделены от Workspace Knowledge и имеют отдельную provenance/authority.

## 6.17. Continuous learning

Новые разговоры анализируются для suggestions/candidates. Money, scheduling, eligibility и legal/health-sensitive rules требуют owner confirmation.

---

# 7. AI Architecture — LOCKED

## 7.1. AI layer boundary

Business code не зависит напрямую от конкретного provider model ID.

Архитектура:

```text
Application Core
    ↓
AI Orchestrator
    ├── ContextBuilder
    ├── ModelRouter
    ├── PromptRegistry
    └── SafetyGateway
    ↓
ModelGateway
    ↓
Provider Adapter(s)
```

Provider selection is **region-qualified and policy-qualified**. No provider brand is a universal first-provider contract.

`ModelRouter` resolves `AIProviderBranch + AIRoutingRevision + ModelProfile` to an eligible adapter/model using DataResidencyPolicy, ProviderExecutionClass, task/risk/modality and approved Eval status. Branch selection never changes Workspace/HomeDataRegion.

For RU production, direct OpenAI/Gemini access through VPN/proxy is not an accepted production dependency. Contracted enterprise gateways/aggregators and RU-local hosted models may be used only under explicit data/provider eligibility policy.

---

## 7.2. Model profiles

Application обращается к логическим профилям, например:

- `CONVERSATION_DEFAULT`;
- `CONVERSATION_COMPLEX`;
- `FAST_EXTRACTION`;
- `SUMMARY_FAST`;
- `VISION_DEFAULT`;
- `VISION_BULK`;
- `ONBOARDING_EXTRACT`;
- `ONBOARDING_SYNTHESIS`;
- `DEEP_ANALYSIS`;
- `IMAGE_GENERATION`;
- `TEXT_EMBEDDING`;
- `VOICE_TRANSCRIPTION`;
- `MODERATION`.

ModelRouter преимущественно deterministic и использует task type, risk, modality и workload class.

---

## 7.3. Initial model mapping

**LOCKED — v0.28 / ADR-259–261.** Two branches share the same logical ModelProfiles, canonical PostgreSQL context, tools and schemas:

| Branch | Preferred integration | Use |
|---|---|---|
| `RU_AGGREGATOR` | PolzaAI first evaluation/integration candidate; GPTunnel comparison or approved replacement | First RU Tattoo Pilot |
| `DIRECT_PROVIDER` | Official model-developer APIs; initial direct adapter candidate OpenAI | Eligible deployment/account/data routes; same task-specific principle |

An aggregator is not automatically RU_LOCAL_HOSTED. `AIProviderBranch` describes access mode; `ProviderExecutionClass` describes actual processing trust/location. Neither price nor catalog presence proves data/upstream eligibility. Previous Cloud.ru-first/local-default preference is superseded; local-hosted gateways remain optional evaluated alternatives, not mandatory third branch.

Candidate mappings are **EVAL_ONLY**, not production approval. API model IDs must be obtained from the chosen provider catalog rather than inferred from display names. Initial shortlist and external sources are in §7.22. Select the least expensive candidate that passes task-specific safety/domain/quality and latency gates; compare total successful-task cost including retries, Vision, tools, cached input and failure rate. Missing facts trigger clarification/Owner, not stronger-model guessing.

Image generation/transcription profiles preserve future extensibility; their existence does not enable these features in the Pilot. Vision/image understanding is Pilot scope.

---

## 7.4. Reasoning effort

Model tier и reasoning effort — разные параметры.

`max` reasoning не используется как default для customer turns.

Reasoning увеличивается только при доказанной необходимости; missing authoritative data не компенсируется более сильной моделью.

---

## 7.5. Provider APIs and provider state

Each `ModelProviderAdapter` uses the provider/gateway API appropriate for the approved regional bundle. OpenAI-compatible API shape may be used where supplied by a gateway, but it is an adapter concern, not a domain dependency.

Provider-managed conversation state, previous response IDs и persisted reasoning не являются canonical memory.

Source of truth остаётся:

```text
PostgreSQL
+ ConversationState
+ ContextBuilder
```

Provider state допускается только как future optimization после eval/privacy review.

---

## 7.6. Structured Outputs

Любой AI output, который читает application code, должен по возможности быть versioned structured output по schema.

Используется `SchemaRegistry`, например:

```text
ServiceRequestExtraction:v3
PortfolioAnalysis:v2
ConversationSummary:v4
OnboardingCandidate:v1
```

Нельзя определять business action парсингом свободного prose.

---

## 7.7. Prompt architecture

Prompt собирается слоями:

```text
Platform Policy
Task Policy
Workflow Context
Business Communication Profile
Trusted Structured State
Authoritative Rules
Retrieved Knowledge / Evidence
Portfolio Evidence
Recent Turns
Current Client Turn
```

External user/document content всегда остаётся untrusted data и не превращается в system/developer instruction.

Владелец бизнеса не получает произвольное поле «system prompt» как основной механизм настройки.

Platform prompts и schemas версионируются; business configuration хранится отдельно.

---

## 7.8. ContextBuilder

Большое context window не является разрешением отправлять всю историю.

ContextBuilder выбирает и ограничивает:

- structured state;
- relevant rules;
- RAG evidence;
- portfolio evidence;
- conversation summary;
- recent turns;
- current turn.

Budgets profile-specific и token-budget based, а не фиксированное число сообщений.

---

## 7.9. Model-call minimization

Не существует mandatory цепочки classifier → extractor → conversation model для каждого Turn.

Default interactive flow стремится к одному основному reasoning pass, если он может одновременно понять Turn, сформировать structured decision и запросить нужные tools.

Отдельные дешёвые calls используются для background/bulk задач, summarization и ingestion только когда это оправдано.

---

## 7.10. Vision

Анализ изображений использует multimodal text/vision models того же model layer.

Различаются interactive и background profiles.

MediaAnalysis кешируется/сохраняется по FileObject + model/schema version, чтобы не анализировать один и тот же файл без необходимости повторно.

Оригинал изображения всё равно может повторно передаваться модели, когда текущий вопрос требует spatial/detail understanding.

---

## 7.11. Visual generation

Image generation/editing выполняется отдельным Visual Design Service.

Conversation model создаёт structured VisualRequest; image model не принимает business decisions и не управляет workflow.

---

## 7.12. Embeddings as versioned projections

Canonical KnowledgeChunk не должен быть намертво связан с одной embedding model.

Предпочтительная модель:

```text
KnowledgeChunk
    ├── Embedding projection v1
    └── Embedding projection v2
```

Используется `EmbeddingProfile` с provider/model/dimensions/metric/version/status.

Это позволяет blue-green reindexing и безопасную смену embedding model.

То же правило применимо к portfolio search representations.

---

## 7.13. Voice transcription

Voice message проходит:

```text
FileObject
→ TranscriptionService
→ transcript
→ normal Conversation pipeline
```

Realtime voice agent не входит в текущий MVP architecture.

---

## 7.14. Safety gateway

AI layer имеет SafetyGateway hook.

Moderation result сам по себе не является business decision; итоговое действие определяется platform/industry/business policy.

Security boundaries defined in §17; exact first-Business risk rules remain approved configuration inputs.

---

## 7.15. Provider built-in tools

Customer-facing AI по умолчанию не получает свободный web search, computer use, arbitrary code или provider-hosted business tools.

Business actions предоставляются нашей application/tool layer.

Hosted provider tools могут использоваться только как явно разрешённая capability для конкретной задачи.

---

## 7.16. AIRun and AIProviderCall

`AIRun` — логическая AI-задача.

Один AIRun может включать несколько provider calls при tool loop.

`AIProviderCall` хранит provider/model/profile/reasoning/usage/latency/error metadata.

Не требуется хранить полный chain-of-thought.

Для объяснимости сохраняются:

- structured decision;
- evidence/source refs;
- rule refs;
- tool calls/results;
- final response;
- model/config/schema versions;
- usage/cost metadata.

---

## 7.17. Model upgrades and fallback

Различаются:

### Technical fallback

Timeout / rate limit / provider failure → retry/backoff/technical fallback.

### Quality escalation

Ambiguity / invalid structured result / insufficient evidence → stronger profile, clarification или Human Escalation.

Нельзя строить бесконечную лестницу retries/models.

Новые models проходят eval → offline/shadow comparison → canary → rollout.

---

## 7.18. Cost metering

С первого production call измеряются как минимум:

```text
workspace
AI task/profile
provider/model
input tokens
cached input
output tokens
reported reasoning usage
latency
cost
```

Model/provider pricing должна быть исторически воспроизводимой.

---

## 7.19. Interactive vs background workloads

AI profiles различают latency class:

- INTERACTIVE — Client ждёт ответ;
- BACKGROUND — onboarding, portfolio ingestion, reindexing, summarization.

Background workloads могут использовать более дешёвые profiles и batching/queue processing.

---

## 7.20. Streaming

User-visible token streaming не является обязательным для MVP.

Для business-critical ответов предпочтительно сначала получить/проверить tool results, а затем отправить завершённый ответ. Channel может показывать typing/progress indicator.

---


## 7.21. Branch switching contract — LOCKED

`AIRoutingRevision` is an immutable profile→adapter/model/parameters/capabilities/fallback manifest within `AIProviderBranch`. It belongs to Platform AI Configuration Release, separate from BusinessConfigurationRelease.

Authorized Platform Ops selects the branch and routing revision per deployment/Workspace binding (pilot UI may be narrow). No domain-code change, new Workspace, price-policy change or provider-side conversation migration is required. Owner-facing raw model selection is not required.

Before activation validate credentials, model/capability availability, schema/tool compatibility, context budget, data eligibility, cost limits and relevant Evals. Publish atomically and audit actor/reason/old/new revision. Each AIRun pins its revision; switch affects new runs. Unsafe in-flight runs are cancelled/staled and resumed from canonical state with prior business effects preserved. Never splice a model continuation into another provider's proprietary state.

Automatic cross-branch fallback is off by default. An explicit evaluated allowlist may enable it only for eligible task/data routes. Gateway-internal fallback must also be constrained/verified; an unobservable incompatible upstream path is ineligible for that task. If no eligible fallback exists, queue/escalate instead of random substitution.

Embedding changes require compatible query/index projection or blue-green rebuild before activation; branch switch alone must not mix vectors from different profiles. Canonical context stays in PostgreSQL. AIRun records branch, routing revision, gateway, known upstream/model, schema, latency and cost provenance.

## 7.22. Initial model shortlist — EVAL_ONLY / 2026-09-09

These are implementation starting candidates, not a measured price-quality winner. No authenticated latency tests or paid task benchmark have been run in this documentation pass.

| Task profile | RU_AGGREGATOR candidate | DIRECT_PROVIDER candidate |
|---|---|---|
| FAST_EXTRACTION / SUMMARY_FAST | Polza Qwen3.8 Flash | OpenAI gpt-5.6-luna |
| CONVERSATION_DEFAULT | Polza Gemini 3.8 Flash | OpenAI gpt-5.6-terra |
| CONVERSATION_COMPLEX / DEEP_ANALYSIS | Polza GLM 5.3 for comparison; select after tool/domain tests | OpenAI gpt-5.6-sol, bounded escalation |
| VISION_DEFAULT | Polza Gemini 3.8 Flash, verify actual image/tool/schema route | OpenAI gpt-5.6-terra |
| VISION_BULK | Cheapest validated vision route; compare same Gemini candidate | Compare gpt-5.6-luna to Terra on Tattoo image labels |
| TEXT_EMBEDDING | OPEN-074: verify catalog, Russian retrieval quality, dimensions and processing eligibility | text-embedding-3-small benchmark candidate, subject to same eligibility |
| IMAGE_GENERATION — post-Pilot | Seedream 5.0 Lite initial cost-oriented candidate; GPT Image alternative if needed | GPT-Image-2.5 Flare initial candidate; exact ID/cost to verify at activation |

PolzaAI is preferred by the user; GPTunnel remains a comparison candidate. The claim that Polza is substantially cheaper is a user preference/hypothesis, not a completed comparative benchmark. Capture current exact model IDs/prices/currency/tax/billing units at the implementation spike. Do not copy direct-provider tariffs into aggregator cost accounting. A candidate with poor Russian/tool behavior is rejected regardless of catalog price. Preview/experimental models are not default production routes.

External evidence (mutable; reverify before integration):
- [Polza API overview](https://polza.ai/docs): unified API access; adapter compatibility does not certify every model/tool route.
- [Polza model catalog](https://polza.ai/models): Qwen3.8 Flash, Gemini 3.8 Flash and GLM 5.3 listed when checked; prices are route-dependent catalog indications.
- [Polza documentation index](https://polza.ai/docs/llms.txt): model listing, tool/structured-output, provider selection, embeddings and image APIs are documented topics.
- [GPTunnel API](https://docs.gptunnel.ru/): API documentation available; comparable current pricing/latency not established in this pass.
- [OpenAI model catalog](https://developers.openai.com/api/docs/models): Luna for economical workloads, Terra balanced, Sol higher capability; text/image support and specialized image models listed. Candidate placement above is an engineering recommendation, not benchmark evidence.

---

# 8. AI Agent / Tools / Autonomy — LOCKED

## 8.1. Agent topology

Основной customer-facing flow использует один `ConversationAgent`.

Pricing, Scheduling, Payments, Knowledge, Portfolio и Visual Design являются application services/tools, а не отдельными customer-facing agents.

Отдельные AI workflows допускаются только для действительно другого lifecycle, прежде всего:
- `OnboardingAgent`;
- Learning/Continuous Improvement workflow.

Не использовать multi-agent swarm как default customer architecture.

## 8.2. AgentRuntime

Agent состоит из:
- Model/Profile;
- Context;
- Allowed Tool Set;
- Policies;
- bounded execution loop;
- state/relevance checks;
- budgets;
- audit/tool traces.

Модель сама по себе не является Agent.

## 8.3. Tool architecture

AI не получает:
- `execute_sql`;
- generic HTTP request;
- arbitrary code execution;
- arbitrary database mutation;
- permission/policy modification.

Business tools узкие, typed и versioned.

Концептуальные группы:
- QUERY;
- DERIVED_ACTION;
- COMMAND;
- PRIVILEGED_COMMAND.

Tool вызывает Application Service, а не Repository/SQL напрямую.

## 8.4. ToolRegistry / ToolSetResolver

`ToolRegistry` знает каталог capabilities платформы.

`ToolSetResolver` выдаёт Agent только минимальный набор tools, релевантный:
- текущему WorkflowStep;
- Service capabilities;
- actor permissions;
- Channel capabilities;
- ActionPolicy;
- current state.

Наличие tool в model context не является authorization.

## 8.5. ToolExecutionContext

Server-side context содержит:
```text
workspace_id
business_id
actor = AI_AGENT
conversation/client/request/order refs
permissions
ai_run_id
correlation/request id
```

`workspace_id` не является model-supplied tool argument.

## 8.6. PolicyEngine / ActionPolicy

Каждое значимое действие имеет autonomy mode:

- `AUTO`
- `REQUIRE_CONFIRMATION`
- `ESCALATE`
- `DISABLED`

Policy hierarchy:
```text
Platform Hard Policy
    ↓
Industry Minimum Policy
    ↓
Workspace Policy
    ↓
Service Policy
    ↓
Dynamic Context Rules
```

Нижний уровень не может ослабить hard platform/industry safety floor.

Client confirmation внутри workflow не равна Owner Approval.

## 8.7. Owner Approval

Для privileged action создаётся `ApprovalRequest` с frozen action payload и state version.

После Owner/Admin approval система:
1. повторно валидирует permissions/state/preconditions/idempotency;
2. исполняет ровно одобренное действие;
3. не просит LLM заново сформировать side effect.

AI не может одобрить собственный ApprovalRequest.

## 8.8. Evidence instead of confidence authorization

Self-reported model confidence не является достаточным основанием для критического business action.

Используются evidence classes, например:
- AUTHORITATIVE_STRUCTURED;
- TOOL_VERIFIED;
- CLIENT_EXPLICIT;
- AI_INFERRED;
- HISTORICAL_SOFT.

ActionPolicy определяет необходимые evidence/preconditions.

## 8.9. Tool errors

Tool results/errors machine-readable.

Минимальные error classes:
- VALIDATION_FAILED;
- NOT_FOUND;
- CONFLICT;
- STALE_STATE;
- NOT_ALLOWED;
- APPROVAL_REQUIRED;
- TEMPORARY_FAILURE;
- EXTERNAL_PROVIDER_FAILURE.

Technical retry выполняет runtime, а не свободный model loop.

## 8.10. Bounded agent loop

Agent имеет `AgentBudget`:
- max steps;
- max tool calls;
- max state mutations;
- deadline;
- optional cost budget.

Stop outcomes:
- SEND_RESPONSE;
- WAIT_FOR_CLIENT;
- WAIT_FOR_HUMAN / APPROVAL;
- ESCALATED;
- NO_RESPONSE;
- FAILED;
- BUDGET_EXCEEDED.

Independent read-only tools могут выполняться параллельно. State-changing commands по умолчанию выполняются последовательно.

## 8.11. Deterministic events bypass Agent when possible

Exact system events не проходят через LLM ради решения, которое уже известно коду.

Примеры:
- payment webhook;
- ReservationHold expiration;
- structured button action;
- deterministic workflow transition.

LLM подключается для semantic interpretation или natural-language response.

## 8.12. Tool traces

Логически существует `AIToolCall/ToolTrace`, отделённый от `AuditEvent`.

ToolTrace фиксирует, что AI запросил и какой policy/execution result получил.

AuditEvent фиксирует фактически произошедшее business mutation/action.

## 8.13. Control plane separation

Customer ConversationAgent преимущественно работает в Data Plane.

Он не может:
- менять собственные permissions;
- менять autonomy policy;
- менять PromptRegistry;
- публиковать Business Rules;
- управлять Workspace membership;
- выполнять platform-admin операции.

---

# 9. Industry Modules + Workflow Definitions — LOCKED

## 9.1. Configuration model

Профессия не создаёт отдельную application architecture.

Используется:
```text
Universal Core
    ↓
Workflow Archetype / Capabilities
    ↓
Industry Pack
    ↓
Business Overrides
    ↓
Service Overrides
    ↓
Compile + Validate
    ↓
ServiceRevision + WorkflowRevision
```

## 9.2. Workflow families

Основные архитектурные workflow families:

1. `SLOT_BASED_SERVICE`
   - manicure, barber, brows, grooming и подобные стандартные appointment services.

2. `CUSTOM_CONSULTATIVE_SERVICE`
   - tattoo, permanent makeup, custom beauty/design-heavy services.

3. `EVENT_BASED_SERVICE`
   - photographer, videographer, DJ, event professionals.

4. `ONSITE_SERVICE`
   - cleaning, plumbing, electrical repair, field service.

5. `CUSTOM_PRODUCTION`
   - furniture, custom manufacturing, tailoring, custom decor.

6. `RECURRING_SESSION_SERVICE`
   - tutors, trainers, recurring coaching/lessons.

7. `PROJECT_DELIVERY_SERVICE`
   - designers, developers, editors, digital project freelancers.

Это archetypes, а не mutually-exclusive profession labels.

## 9.3. Capability composition

Service может комбинировать capabilities, например:
```text
APPOINTMENT_BASED
ASSESSMENT_REQUIRED
VISUAL_INTAKE
VISUAL_GENERATION
QUOTE_REQUIRED
DEPOSIT_REQUIRED
MULTI_SESSION
RECURRING
ONSITE
TRAVEL
EVENT_DATE
PRODUCTION
DELIVERY
INSTALLATION
REVISION_CYCLES
FILE_DELIVERY
```

Profession/industry code помогает defaults/terminology/knowledge, но не определяет workflow единолично.

## 9.4. IndustryPack

Versioned platform template содержит концептуально:
- service templates;
- intake schema templates;
- workflow templates;
- capability defaults;
- business rule templates;
- pricing/scheduling defaults;
- portfolio analysis schema;
- terminology;
- knowledge categories/references;
- autonomy defaults;
- escalation defaults;
- onboarding question templates.

Pack не содержит конкретные цены/правила конкретного бизнеса.

## 9.5. Pack upgrades

Обновление IndustryPack не меняет production business автоматически.

Upgrade:
```text
new pack available
    ↓
diff / validation
    ↓
business review where required
    ↓
new revisions
    ↓
publish
```

## 9.6. Workflow model

Добавляются логические сущности:
- `WorkflowDefinition`;
- `WorkflowRevision`;
- `WorkflowInstance`;
- `WorkflowStepInstance`.

`ServiceRevision` связывается с immutable `WorkflowRevision`.

Workflow представляет directed graph с:
- steps;
- dependencies;
- guards;
- optional branches;
- wait states;
- completion conditions;
- allowed tools/actions;
- autonomy overrides.

Не требуется enterprise BPMN engine для MVP.

## 9.7. Workflow state is orchestration, not truth

Workflow не дублирует domain data.

Например:
- payment truth → PaymentRequest/PaymentTransaction;
- calendar truth → ReservationHold/Appointment;
- quote truth → Quote;
- request facts → ServiceRequest.

Workflow только определяет, какие prerequisites выполнены и что разрешено делать дальше.

## 9.8. Deterministic completion

WorkflowStep завершается по проверяемому domain condition, а не потому что LLM «решила, что этап завершён».

AI может помогать выполнить semantic step, но завершение подтверждает код/state.

## 9.9. Tool availability from workflow

`ToolSetResolver` учитывает текущий WorkflowStep.

Например Intake step не выдаёт Agent refund/booking tools без необходимости.

## 9.10. Generic businesses without Pack

IndustryPack — ускоритель, а не обязательное условие.

Неизвестная профессия может быть настроена через generic onboarding, capabilities и workflow configuration без нового backend module.

## 9.11. UI terminology

Backend vocabulary остаётся единым.

Industry Pack может менять UI labels:
- ServiceOrder → «Заказ» / «Проект» / другое;
- ServiceSession → «Сеанс» / «Занятие».

## 9.12. Expansion risk

Workflow Complexity и Risk/Regulatory Complexity оцениваются отдельно.

High-risk verticals (medicine, legal, financial advice) не являются ранним expansion priority.

Construction/large renovation рассматривается как advanced project vertical.

---

# 10. Business Onboarding & Configuration — LOCKED

## 10.1. Purpose

Onboarding должен с минимальным количеством вопросов получить достаточную, непротиворечивую и подтверждённую конфигурацию бизнеса для безопасной работы AI.

Onboarding — отдельная подсистема, не статическая форма.

## 10.2. Onboarding modes

Поддерживаются:
- Quick Start;
- Assisted Import;
- Full / Concierge Onboarding.

Первые production clients рекомендуется проводить concierge/manual или semi-assisted способом.

## 10.3. OnboardingAgent

`OnboardingAgent` работает с Owner/Admin и draft/candidate objects.

Он не отправляет сообщения клиентам и не публикует production configuration самостоятельно.

## 10.4. Pipeline

```text
Create Business
    ↓
Basic Discovery
    ↓
Source Collection
    ↓
Import / Normalization
    ↓
AI Analysis
    ↓
Service Discovery
    ↓
Capability / Workflow Inference
    ↓
Rules / Knowledge Extraction
    ↓
Portfolio / Communication Analysis
    ↓
Conflict Detection
    ↓
Missing Data Detection
    ↓
Adaptive Questions
    ↓
Owner Answers
    ↓
Configuration Draft
    ↓
Deterministic Validation
    ↓
Simulation / Preview
    ↓
Owner Approval
    ↓
Publish
    ↓
Calibration
```

## 10.5. Import boundary

Provider/file-specific formats обрабатываются Importers.

OnboardingAgent работает с normalized sources.

Логически добавляется `ImportBatch`.

Raw source сохраняется до extraction согласно будущей retention/privacy policy.

## 10.6. Service-level discovery

Business industry classification помогает выбрать defaults, но Workflow/capabilities определяются преимущественно для каждой Service.

AI создаёт Service/Rule/Workflow candidates, а не бесконтрольно production objects.

## 10.7. Candidate provenance

Значимые candidates содержат:
- source/evidence;
- authority;
- extraction/model metadata where useful;
- conflict/missing status.

Критические values требуют достаточного authority/owner confirmation.

## 10.8. Conflict detection

Минимальные классы:
- VALUE_CONFLICT;
- TEMPORAL_CONFLICT;
- SEMANTIC_CONFLICT;
- CONFIGURATION_CONFLICT.

AI может группировать evidence и формировать вопрос, но authoritative resolution критического конфликта принадлежит Owner/structured source.

## 10.9. Adaptive questionnaire

Вопросы формируются после анализа уже доступных данных.

`OnboardingQuestion` имеет:
- target;
- type;
- priority;
- dependency;
- reason/evidence.

Question priorities:
- BLOCKING;
- IMPORTANT;
- OPTIONAL;
- ENRICHMENT.

Question dependency graph предотвращает бессмысленные дочерние вопросы.

## 10.10. Readiness gates

Не использовать общий completion percentage как единственный launch criterion.

Readiness определяется gates, например:
- SERVICES_READY;
- PRICING_READY;
- SCHEDULING_READY;
- POLICIES_READY;
- KNOWLEDGE_READY;
- CHANNEL_READY;
- AUTONOMY_READY.

Readiness может различаться между Services одного Business.

## 10.11. Portfolio onboarding

Imported images должны различать provenance:
- MY_WORK;
- CLIENT_REFERENCE;
- INSPIRATION;
- OTHER.

Только подтверждённые реальные работы становятся PortfolioItem evidence бизнеса.

## 10.12. Communication profile review

Style inference предпочтительно подтверждать через realistic AI response previews, а не через технические числовые параметры.

## 10.13. Autonomy onboarding

Владельцу предлагаются понятные autonomy presets.

Platform hard policies не override'ятся onboarding.

## 10.14. ConfigurationDraft

Onboarding работает с `ConfigurationDraft`, который не является production state.

После publish draft остаётся historical onboarding artifact.

## 10.15. Validation

Публикация блокируется при deterministic ERROR.

Validation может также возвращать WARNING/INFO.

AI может объяснить issue, но наличие/отсутствие mandatory configuration проверяет application code.

## 10.16. Simulation / Preview

До production configuration проходит:
- historical replay, если доступны старые conversations;
- synthetic scenarios;
- minimal service smoke suite;
- Owner preview.

Проверяется correctness facts/actions/escalations/tone, а не буквальное совпадение текста.

## 10.17. BusinessConfigurationRelease

Добавляется immutable `BusinessConfigurationRelease` — manifest совместно опубликованных revisions/builds, например:
- ServiceRevisions;
- WorkflowRevisions;
- Rule revisions/set;
- KnowledgeBuild;
- CommunicationProfile revision;
- AutonomyPolicy revision.

Публикация Release должна быть атомарной.

Release обеспечивает reproducibility и rollback для новых операций, но не переписывает уже pinned ServiceRequest/Order revisions.

## 10.18. Onboarding lifecycle

Логическая `OnboardingSession` имеет состояния:
```text
DRAFT
COLLECTING_SOURCES
ANALYZING
NEEDS_OWNER_INPUT
BUILDING_CONFIG
VALIDATING
READY_FOR_REVIEW
APPROVED
PUBLISHED
```

Side states:
- PAUSED;
- FAILED;
- ABANDONED.

Onboarding может быть incremental и использоваться после запуска для добавления Service/изменения конфигурации.

## 10.19. Calibration

Первый production launch не обязан сразу включать максимальную autonomy.

Во время calibration собираются:
- human interventions;
- corrections;
- escalations;
- tool errors;
- missing knowledge;
- wrong answers.

Autonomy расширяется после evidence/evals.

## 10.20. Multi-provider scope

Onboarding различает Business-level и provider/resource-level configuration.

Данные одного мастера не должны автоматически становиться capability всей команды.



# 11. Pricing — LOCKED

## 11.1. Pricing source of truth
LLM не является authoritative source денежной суммы. Authoritative price создаётся `PricingEngine` либо structured Owner decision.

AI может извлекать/оценивать pricing factors, но не превращает собственное предположение непосредственно в деньги.

## 11.2. Pricing strategies
Архитектура поддерживает:
- FIXED;
- FIXED_WITH_OPTIONS;
- UNIT_BASED;
- TIME_BASED;
- TIERED;
- RANGE;
- ASSESSMENT_BASED;
- DIAGNOSTIC_REQUIRED;
- OWNER_QUOTE;
- AI_ASSISTED_ESTIMATE;
- ограниченные formula/rule combinations.

MVP не требует универсального пользовательского formula DSL.

## 11.3. Versioning
Добавляются `PricingPlan` и immutable `PricingRevision`.

`ServiceRevision` связывается с конкретной `PricingRevision`.

Изменение production pricing создаёт новую PricingRevision + BusinessConfigurationRelease.

## 11.4. PriceCalculation vs Quote
`PriceCalculation` — immutable внутренний результат расчёта.

`Quote` — customer-facing commercial object.

Calculation может вернуть EXACT/RANGE либо NEEDS_INPUT/NEEDS_ASSESSMENT/NEEDS_HUMAN/FAILED.

Quote не создаётся из произвольной суммы ConversationAgent; только из valid Calculation или structured Owner-approved decision.

## 11.5. Pricing evidence and staleness
PricingRevision объявляет relevant inputs. Calculation фиксирует snapshot/fingerprint этих inputs.

Изменение pricing-relevant facts инвалидирует старый Calculation.

AI-inferred inputs сохраняют provenance и при необходимости требуют Assessment/Owner confirmation.

## 11.6. Internal vs customer-visible pricing
`PriceComponent` может содержать внутренние элементы расчёта.

`QuoteLine` — только клиентский breakdown.

Internal margin/cost data не обязаны попадать ConversationAgent.

## 11.7. Adjustments
Discount/surcharge/manual override происходят только из PricingRule/Promotion/authorized adjustment.

AI не придумывает скидку.

Manual adjustment проходит ActionPolicy/approval.

## 11.8. Price authority
Customer response различает INDICATIVE / PROVISIONAL / CONFIRMED price authority.

Ориентир нельзя формулировать как подтверждённую точную цену.

## 11.9. Payment boundary
Pricing отвечает «сколько стоит».

PaymentTerms отвечают «когда и сколько платить».

Deposit/refund/payment schedule не являются обязанностью PricingEngine.

## 11.10. Owner-selected price authority and acceptance — LOCKED / v0.28

Per Service, the owner selects `PricingMode = FIXED | CONFIGURED_FORMULA | OWNER_QUOTE`. Existing exact/range calculation output remains supported, but mode (how price is obtained) differs from price authority (indicative/provisional/confirmed).

- FIXED: PricingEngine returns the configured amount/options.
- CONFIGURED_FORMULA: the master supplies business inputs and formula; implementation compiles it into bounded, versioned, allowlisted deterministic rules. No arbitrary eval/code/SQL or model-generated executable formula. Units, missing inputs, rounding, minima/maxima and applicability are validated before publish. An unsupported formula becomes NEEDS_HUMAN until implemented and approved, never approximated silently.
- OWNER_QUOTE: Agent completes intake and creates one relevant owner decision; owner enters an exact price or requests clarification. The approved price creates an immutable Quote, then AI conveys it to the Client.

AI may extract factors but may not substitute its own amount. Price mode, duration mode and PaymentTerms are independent settings: automatic price can coexist with Owner duration, and Owner price can coexist with fixed/rule duration.

`QuoteAcceptance` is a logical auditable record binding explicit Client acceptance to quote ID/revision/content fingerprint, Client, request, scope, currency, price authority and PaymentTermsRevision. Exact button/form action is deterministic; text acceptance must unambiguously refer to the current offer with Message evidence. Ambiguous "yes" requires clarification. Owner approval is not Client acceptance.

For the Tattoo Pilot consultative workflow, accepted Quote creates one ServiceOrder plus at least its next ServiceSession through an idempotent command. This does not impose a Quote step on every future WorkflowArchetype. PaymentRequest binds with tenant-safe typed references to ServiceOrder, optional ServiceSession, accepted Quote/acceptance and PaymentTermsRevision; Hold linkage is separate and never the only money target. Final DDL belongs to M6–M8.

Changes to scope/price-relevant facts supersede the pending offer and require recalculation/new Quote and fresh acceptance. Already paid money and historical terms remain intact; affected Holds/checkout sessions become invalid for automatic fulfillment and are reconciled. Sessions for multi-session work may remain PLANNED; no dates or session count are invented.

Commercial agreement may explicitly preserve a RANGE as provisional; it is never silently converted to an exact price. A fixed deposit can be computed without pretending that the total is exact. Percentage/full-prepayment requires an exact agreed monetary basis. Range-based percentage without such a basis returns NEEDS_HUMAN. Exact first-master rules remain onboarding inputs.

## 11.11. Duration assessment and master examples — LOCKED boundary / calibration OPEN

`DurationPolicyRevision` (linked from SchedulingPolicyRevision) supports FIXED, CONFIGURED_RULE and OWNER_DEFINED. `DurationEstimate` is a derived proposal; bookable `ServiceAssessment` requires a configured deterministic rule or structured Owner decision. A schema-valid AI number or self-reported confidence is insufficient.

The owner can provide `DurationCase` examples: permitted work/reference image, actual dimensions, placement, style/technique, detail/fill, provider, actual working minutes, occupied appointment minutes, setup/stencil/break/cleanup treatment, session count/durations and explanation of overruns. Missing actual time is labelled unknown, not inferred as measured truth. Provenance/consent/minimization apply to historical images and notes.

Pipeline: examples → normalized owner-scoped cases → comparable-case retrieval + AI explanation → candidate rule/estimate → owner review → versioned publication → calibration against completed work. This is case-based assistance, not automatic per-master model fine-tuning or self-changing production rules. No automatic scheduling from nearest-image similarity alone.

Until a reliable configured rule exists, use OWNER_DEFINED for booking; the AI may present evidence and a draft estimate to the owner. Price and duration can be answered in one owner decision to reduce interruptions. Fixed standard services remain fully automatic.

Duration factors can include size, line/detail density, fill/color, technique, placement, practitioner speed, setup and session limits. Image perception is a candidate observation; size cannot be reliably recovered from an unscaled image. Client/Owner confirmation is required where a critical input is unverified.

Separate active work time from Appointment duration and resource buffers. Do not count setup/cleanup twice. Multi-session determination requires owner-approved maximum session duration, partition rules and any interval constraints; never divide total minutes into medical/healing intervals by model guess. Pilot schedules only the next approved session.

**Illustrative training examples only, not tattoo standards or this master's settings:** an owner-labelled simple small outline may occupy 60 minutes; a denser piece may occupy 120; a large detailed work may have three owner-labelled sessions. Exact dimensions, factors and session lengths must come from the master. No universal "N cm = N hours" formula is accepted. OPEN-080/081 collect these inputs.

### Illustrative owner-labelled duration records (not production defaults)

| Example supplied by a hypothetical master | Work minutes | Setup/stencil + cleanup minutes | Appointment minutes | Explanation |
|---|---|---|---|---|
| Small simple outline, 4 cm, ordinary placement | 35 | 15 + 10 | 60 | Few lines, no dense fill; master-labelled example only |
| More detailed piece, 8 cm, same provider | 85 | 20 + 15 | 120 | More lines/fill; size alone does not account for difference |
| Large complex composition | Recorded separately per session | Recorded per session | Three owner-approved 180-minute sessions in this example | Partition explicitly chosen by master, not inferred solely from image |

These fictional numbers show what to collect, not what any real tattoo should take. Active work + in-session setup/cleanup/breaks = occupied Appointment time; additional resource buffers are separate. Compare similar cases for this master, explain factors and uncertainty to Owner, then request approval or apply an already published bounded rule. Do not generalize these rows into production configuration.

### Delivery Horizon — Pricing
**PRODUCTION_PILOT:** FIXED / bounded CONFIGURED_FORMULA / OWNER_QUOTE, validated range indication, acceptance binding, assessment factors, PriceCalculation→Quote→QuoteAcceptance→Order/Session, currency/rounding. Owner formula scope is validated before implementation; universal formula authoring is excluded.  
**CORE_POST_MVP:** richer tiers/formulas, historical pricing recommendations, location/provider overrides, dynamic materials/travel inputs.  
**FUTURE_OPTIONAL:** predictive pricing model, supplier feeds, FX engine, advanced optimization.

---

# 12. Scheduling / Resources — LOCKED

## 12.1. Availability
Свободные slots являются derived data.

Source of truth:
```text
working rules
+ overrides
+ blocks
+ resource allocations
+ holds
+ appointments
+ scheduling policy
```

Не хранить заранее миллионы free-slot rows.

## 12.2. Configuration
Добавляются:
- `SchedulingPolicy`;
- immutable `SchedulingPolicyRevision`;
- `ServiceResourceRequirement`.

`ServiceRevision` связывается с SchedulingPolicyRevision.

Operational calendar state не требует ConfigurationRelease.

## 12.3. Duration and buffers
Bookable duration может быть FIXED / OPTION_BASED / ASSESSMENT_BASED / OWNER_DEFINED.

До booking должна существовать конкретная duration.

Resource occupancy может расширяться buffers до/после Appointment.

## 12.4. Calendar state
Используются:
- `AvailabilityRule`;
- `AvailabilityOverride`;
- `CalendarBlock`.

Recurring working rules хранятся в local IANA timezone. Concrete Appointment — absolute timestamptz interval.

## 12.5. AvailabilityOffer
`AvailabilityOffer` хранит варианты, показанные клиенту, но ничего не резервирует.

Перед Hold выполняется fresh availability recheck.

## 12.6. ResourceAllocation
`ResourceAllocation` — technical primitive exclusive occupancy.

ReservationHold и Appointment создают allocations.

Double booking предотвращается на database level.

Multi-resource acquisition выполняется атомарно.

## 12.7. Hold conversion
ReservationHold persistent в PostgreSQL.

Hold→Appointment conversion выполняется атомарно с повторной проверкой state/resources.

Expiry — deterministic system action без LLM.

## 12.8. Advanced scheduling model
Архитектура допускает:
- multi-session services;
- RecurrencePlan;
- event-based scheduling;
- onsite/travel constraints;
- future external calendar busy sync.

External calendar не заменяет canonical internal Appointment.

## 12.9. Rescheduling
Reschedule сохраняет историю: старый Appointment CANCELLED, новый CONFIRMED.

Старый слот не освобождается до безопасного захвата нового.

## 12.9.1. Atomic reschedule and calendar conflicts — LOCKED

Reschedule replaces this appointment's occupancy inside one short atomic transaction, preserving the old Appointment as CANCELLED and a new CONFIRMED record. It must allow partial overlap with its own replaced interval, while never excluding another Client's allocation from conflict checks. The old slot remains protected until commit; failure rolls back to the old allocation.

CalendarBlock participates in the same serialized resource-occupancy conflict protocol as Holds/Appointments. Creating a block across an existing reservation returns CONFLICT with affected objects; it does not silently cancel customer bookings. Explicit owner-led cancellation/reallocation is separate. Test self-overlap, same-time request, buffers, blocks, competing booking and rollback.

Expired holds cannot depend solely on a timely scheduler: reservation commands revalidate/release eligible expired occupancy transactionally using trusted time. Concrete exclusion/locking schema is OPEN-055.

## 12.10. Agent tools
Preferred flow:
```text
check_availability(service_request_id, preferences)
→ AvailabilityOffer
→ create_reservation_hold(availability_option_id)
```

Agent не задаёт произвольные duration/resource allocation.

### Delivery Horizon — Scheduling
**MVP:** one provider Resource, hours/overrides, duration/buffers, offer/hold/allocation/appointment, DB overlap protection, cancellation/simple reschedule.  
**CORE_POST_MVP:** multi-resource, multi-session, recurrence, external calendar, richer requirements.  
**FUTURE_OPTIONAL:** route-aware travel, capacity/group resources, advanced slot optimization.

---

# 13. Client → Business Payments — LOCKED

## 13.1. Payment concepts
Разделены:
- `PaymentRequest` — обязательство;
- `PaymentSession` — checkout/link session;
- `PaymentTransaction` — provider operation/lifecycle; SUCCEEDED is provider-confirmed money movement;
- `Refund` — отдельное обратное movement;
- business effect оплаты — Workflow responsibility.

## 13.2. PaymentTerms
Добавляются `PaymentTerms` и immutable `PaymentTermsRevision`.

`ServiceRevision` связывается с PaymentTermsRevision.

Поддерживаются no-prepay/full/fixed deposit/percent deposit/deposit+balance/milestone/manual schemes.

## 13.3. PaymentRequest lifecycle
PaymentRequest amount после открытия не редактируется.

Изменение условий создаёт новый Request.

Obligation state и Collection state разделяются, что позволяет корректно описывать late/partial/over payment.

## 13.4. Provider abstraction
`PaymentProviderConnection` принадлежит Business.

`PaymentProviderAdapter` скрывает provider-specific API/statuses.

## 13.5. Money flow
В MVP деньги клиента идут:
```text
Client → Payment Provider → Business merchant account
```

Платформа не является wallet/escrow/marketplace settlement layer.

Provider-hosted checkout/tokenization предпочтительны.

Raw PAN/CVC не хранятся приложением.

## 13.6. Authoritative evidence
Online payment подтверждается только verified provider webhook/API.

Не подтверждают оплату:
- client claim;
- screenshot;
- success redirect;
- AI inference.

Manual cash/bank payment фиксирует только authorized BusinessMember/system integration.

## 13.7. Webhooks and idempotency
```text
verify provider-specific authenticity
→ dedupe
→ resolve connection/workspace
→ normalize state
→ update payment domain
→ Outbox event
→ Workflow
```

Provider webhook handler не создаёт Appointment напрямую. Для YooKassa проверка подлинности/актуальности основана на documented adapter mechanism (authenticated object GET and source checks), а не на предполагаемой универсальной HMAC signature. Verify merchant connection, provider object ID, amount/currency, test/live mode and local PaymentRequest binding. Unverified notification may be durably quarantined but cannot authorize money/booking effects. See §13.12 and the [YooKassa notification contract](https://yookassa.ru/developers/using-api/webhooks).

Provider events/calls должны быть idempotent.

## 13.8. Refund
Refund — отдельная сущность/lifecycle.

Refund не переписывает успешную историю PaymentTransaction.

Refund amount проверяется сервером. В MVP — Owner approval by default.

## 13.9. Late/unexpected payment
Provider-confirmed payment сохраняется даже если Hold/Request/Quote уже expired/cancelled.

Appointment не создаётся без fresh scheduling validation.

Unexpected payment вызывает safe workflow/escalation.

## 13.10. Reconciliation
Webhook — primary path; reconciliation job — reliability safety net.

## 13.11. Separation from SaaS billing
Client→Business payments не смешиваются с Business→Platform subscription billing Stage 15.

## 13.12. Agreement → payment terms → booking — LOCKED / v0.28

Per-service PaymentTerms mode is independent of PricingMode:

| Mode | Booking precondition |
|---|---|
| NONE | No prepayment required; active Hold + accepted terms + authorized duration/resources suffice |
| FIXED_DEPOSIT | Owner-configured fixed amount in currency |
| PERCENT_DEPOSIT | Deterministic percentage of exact agreed basis, explicit rounding |
| FULL_PREPAYMENT | Exact agreed payable amount |

First Tattoo master uses FIXED_DEPOSIT regardless of ordinary job scale. Exact amount and any exceptional minimum-total relationship remain OPEN-079. Never hardcode an invented amount or silently clamp the configured deposit. NONE does not mean a free service or fake successful payment; any later balance is a separate payment obligation.

Canonical path: validated request/assessment → Quote → explicit QuoteAcceptance → ServiceOrder + next ServiceSession → fresh chosen option/Hold → determine PaymentTerms obligation. With prepayment create PaymentRequest/Session, persist provider-authoritative money, evaluate satisfied obligation, then atomically convert valid Hold to Appointment. With NONE skip prepayment request/checkout and convert valid Hold directly. Both paths require valid duration, Client choice and current eligibility. Later payment does not retroactively change the booking decision.

PaymentRequest amount/currency/basis is frozen after opening. Client confirmation of commercial terms precedes payable request creation. Repeated commands reference the same business intent/accepted quote/obligation, not merely a new AIRun ID.

Multiple provider events for one transaction are deduplicated. Two distinct successful provider payments are both money facts: detect overpayment, block duplicate fulfillment and create owner recovery/refund work. Refund concurrency checks cumulative succeeded and pending refunds against refundable balance. Correcting mistaken manual payment uses an audited compensating command, not silent mutation of history.

Payment event may arrive before create-call response; correlate through trusted merchant/local intent/provider identifiers and reconcile UNKNOWN. Out-of-order callbacks never overwrite a newer authoritative terminal result with stale state. Payment success does not by itself override cancelled Quote/Order or expired Hold.

### Delivery Horizon — Client Payments
**MVP:** one provider connection, hosted checkout, common deposit schemes, PaymentRequest/Session/Transaction, verified webhook, manual payment, late-payment handling, owner-approved refund.  
**CORE_POST_MVP:** milestones, multiple payment providers, richer reconciliation/refund/dispute/recurring support and expanded fiscalization integrations. Applicable RU fiscalization workflow/readiness is already required before Pilot live payments (§26.8).  
**FUTURE_OPTIONAL:** escrow, platform wallet, split payments, managed payouts, ledger, BNPL, FX.

---

# 14. Automations / Notifications — LOCKED

## 14.1. Responsibilities
Automation Engine определяет **когда/почему**.

Notification layer определяет **кому/как**.

LLM не является scheduler/timer.

## 14.2. Triggers
Основные trigger classes:
- DOMAIN_EVENT;
- SCHEDULED_TIME;
- STATE_TIMEOUT;
- ограниченный PERIODIC_CHECK.

Event-driven path предпочтительнее polling, когда domain event существует.

## 14.3. Configuration/runtime
Добавляются:
- `AutomationDefinition`;
- immutable `AutomationRevision`;
- persistent `AutomationInstance`.

AutomationRevision может входить в BusinessConfigurationRelease.

AutomationInstance — operational state.

## 14.4. Relevance
Перед due action/send всегда перечитывается current state.

Неактуальная automation становится CANCELLED/SKIPPED.

Human takeover подавляет client-facing AI follow-ups.

## 14.5. Notification model
Canonical notification — channel-independent `NotificationIntent`.

Каждая конкретная отправка — `NotificationDeliveryAttempt`.

Один Intent может иметь sequential fallback attempts.

## 14.6. Routing and capability checks
NotificationRouter учитывает:
- ClientIdentity;
- ChannelConnection;
- ChannelCapabilities;
- consent/preferences;
- NotificationPolicy;
- route priority.

Conversation channel и proactive notification route могут различаться.

## 14.7. Categories/policies
Categories:
- TRANSACTIONAL;
- REMINDER;
- SERVICE_FOLLOWUP;
- REACTIVATION;
- MARKETING;
- INTERNAL.

`NotificationPolicyRevision` задаёт channels, quiet hours, frequency caps, fallback, late execution behavior.

Follow-up sequences bounded.

## 14.8. Content
Transactional content в MVP template-first/hybrid с structured facts.

AI может формулировать semantic follow-up по explicit purpose/context.

После AI generation выполняется final relevance check.

## 14.9. Persistence/idempotency
Automation state persistent и переживает restart.

Late execution имеет explicit policy.

Notification purpose/entity имеет deterministic idempotency key.

Cancellation/reschedule инвалидируют связанные reminders.

## 14.10. Conversation integration
Automated client-facing outbound записывается как обычный Message с automation origin.

Client reply возвращается в обычный Conversation Engine.

## 14.11. Route unavailability and owner waits — LOCKED

Appointment reminders are attempted only on an eligible route/window. Unavailable Telegram route produces a visible ROUTE_UNAVAILABLE outcome and owner task; no false DELIVERED status. Manual Console send through the same adapter cannot bypass provider rights/window. Additional customer fallback channels remain out of Pilot. Test scheduling days ahead with the reply window already closed.

Approval/Escalation stores responsible owner, pending reason, due/expiry policy and relevant state fingerprint. Deduplicate repeated requests; owner delay schedules bounded internal reminders; stale/withdrawn Client request cancels the outstanding decision. The Client receives only truthful waiting status through an eligible route, not invented decision/response-time promises. Exact timeouts/support windows are OPEN-072/082.

### Delivery Horizon — Automations / Notifications
**MVP:** appointment/payment reminders, hold expiry/warning, missing-response follow-up, owner escalation notification, persistent automation, relevance guard, frequency/quiet hours, channel capability checks, template/hybrid transactional content.  
**CORE_POST_MVP:** multi-channel fallback, email/bot routes, recurring/multi-session reminders, preferences, notification center/digests.  
**FUTURE_OPTIONAL:** SMS, marketing/reactivation/review campaigns, push, AI campaign optimization, cross-channel attribution.

---


# 15. SaaS Plans / Billing / Usage / Quotas — LOCKED

## 15.1. Billing boundary

`Workspace` является единицей SaaS billing.

Client→Business payments Stage 13 и Workspace→Platform billing являются разными bounded contexts даже при использовании одного внешнего provider.

`UserAccount` не имеет глобальной подписки, автоматически распространяющейся на все Workspaces.

## 15.2. Workspace billing model

Добавляется `WorkspaceBillingAccount`.

Концептуально он содержит:
- workspace reference;
- billing contact/display data;
- provider customer reference;
- billing country/legal metadata where needed;
- normalized billing status.

Billing permissions выдаются отдельно; в MVP ими владеет OWNER.

## 15.3. Owner payment methods

Для SaaS subscription используется provider-hosted checkout/billing portal и tokenization.

Платформа не хранит:
- PAN/full card number;
- CVC/CVV;
- raw reusable card credentials.

Можно хранить `PaymentMethodReference`:
- provider_payment_method_id;
- card brand;
- last4;
- expiry display metadata;
- status/default flag.

## 15.4. Plans and entitlements

Не использовать business logic вида `if plan == "PRO"`.

Модель:
```text
SaaSPlan
    ↓
immutable SaaSPlanRevision
    ↓
PlanEntitlements
```

Application services спрашивают `EntitlementService`:
- capability enabled?
- numeric limit?
- usage quota?
- max businesses/members/channels/etc.?

Plan entitlement не является security permission и не может ослаблять ActionPolicy/platform safety.

## 15.5. Subscription and service mode

`Subscription` принадлежит Workspace и pin'ит конкретную SaaSPlanRevision/effective interval.

Provider billing state и product service mode разделены.

Billing state conceptually:
- TRIALING;
- ACTIVE;
- PAST_DUE;
- CANCELED.

Workspace service mode:
- NORMAL;
- GRACE;
- LIMITED;
- SUSPENDED.

Provider webhook не отключает product capabilities напрямую; `BillingPolicy` преобразует canonical billing state в service mode.

## 15.6. Graceful degradation

Failed subscription payment не должен мгновенно разрушать active customer workflows.

Capabilities классифицируются по criticality:
- ESSENTIAL;
- STANDARD;
- EXPENSIVE_OPTIONAL.

При ограничениях дорогие optional operations блокируются раньше core safety/continuity actions.

Inbound customer events желательно продолжать durable-persist даже при SUSPENDED mode; AI auto-response может быть запрещён.

Cancellation subscription не означает deletion customer data.

## 15.7. Upgrade/downgrade

Plan change не удаляет существующие entities.

Если downgrade создаёт превышение limits:
```text
Workspace → OVER_LIMIT for affected entitlement
```
и ограничиваются новые операции, а не уничтожаются existing members/businesses/files.

Downgrade/upgrade имеют effective intervals; provider может оставаться authoritative для денежной proration.

## 15.8. Observed usage vs billable usage

Измеряется больше, чем коммерчески тарифицируется.

`Observed Usage` может включать:
- AI tokens/provider cost;
- image generations;
- transcription;
- storage;
- channels;
- seats;
- other feature usage.

`Billable Usage` определяется Meter/Plan policy.

MVP не продаёт самозанятому raw token counts как основной тарифный язык.

## 15.9. Usage ledger

Добавляется immutable `UsageEvent`:
- workspace_id;
- metric;
- quantity;
- source_type/source_id;
- occurred_at;
- metadata.

UsageEvent должен быть idempotent по stable source/metric key.

`UsageAggregate` — rebuildable projection для UI/analytics.

`UsageMetricDefinition` описывает raw metric; `MeterDefinition` — преобразование raw usage в commercial unit.

## 15.10. Quotas

`QuotaService` проверяет entitlement/current usage/reservations.

Для дорогих hard-quota operations используется persistent `QuotaReservation`:
```text
reserve
→ execute expensive operation
→ consume on success
→ release on failed/no-consumption path
```

Interactive text AI в MVP использует soft/continuity budget; дорогие optional operations (например image generation/bulk import) могут иметь hard quota.

Quota ≠ security rate limit.

## 15.11. Runtime independence from billing provider

Обычный Client conversation не вызывает Billing Provider API.

Runtime entitlement checks используют локальный canonical Subscription/Entitlement state.

BillingProvider outage не должен отключать customer-facing runtime.

Provider webhooks/reconciliation обновляют canonical billing state asynchronously.

## 15.12. Billing operations

Архитектурно предусмотрены:
- BillingInvoice normalized projection;
- ProviderPriceReference;
- temporary audited entitlement overrides;
- BillingReconciliationJob.

Exact commercial plan prices/allowances не фиксируются до real unit economics.

### Delivery Horizon — SaaS Billing

**PRODUCTION_PILOT:** local WorkspaceBillingAccount, SaaSPlanRevision/Entitlements, Subscription with explicit TRIALING or ACTIVE+COMPED funding mode, WorkspaceServiceMode, UsageEvent/cost and basic owner view; no paid-provider call required. Hosted recurring charging below is COMMERCIAL_MVP.

**COMMERCIAL_MVP**
- WorkspaceBillingAccount;
- one initial plan revision is sufficient;
- basic EntitlementService;
- monthly Subscription;
- hosted checkout/billing portal;
- tokenized PaymentMethodReference;
- BillingInvoice projection;
- provider webhook;
- TRIALING/ACTIVE/PAST_DUE/CANCELED;
- NORMAL/GRACE/LIMITED/SUSPENDED;
- UsageEvent + AI/provider-cost measurement;
- QuotaReservation for implemented expensive bulk work; image-generation quota only when that feature is introduced;
- basic usage/billing owner view.

**CORE_POST_MVP**
- annual billing;
- more tiers;
- seat/storage/multi-Business limits;
- add-ons/promos/overage;
- advanced downgrade handling;
- customer-visible usage dashboards;
- richer billing reconciliation/tax integrations.

**FUTURE_OPTIONAL**
- enterprise/custom contracts;
- prepaid credits/platform balance;
- reseller/affiliate billing;
- complex usage pricing;
- multi-currency/custom invoicing.

---

# 16. Business Console + Platform Operations — LOCKED

## 16.1. Application surfaces

`Master UI` канонически называется `Business Console`.

Есть два разных surface:
- Business Console для Workspace members;
- Platform Operations Console для platform staff/support/ops.

Они используют общий backend/domain services, но имеют разные authorization contexts и UI responsibilities.

## 16.2. Business Console philosophy

Business Console exception-first, а не generic CRM/database dashboard.

Главный `Action Center` агрегирует:
- Escalations;
- ApprovalRequests;
- payment exceptions;
- scheduling conflicts;
- integration/configuration warnings;
- other owner actions.

## 16.3. Inbox / Conversation

Inbox показывает conversation вместе со structured business context:
- Client;
- ServiceRequest;
- Workflow state;
- Quote;
- Appointment;
- Payment;
- Escalation/Approval.

Human takeover/resume явно видимы и управляют `control_mode`.

## 16.4. Explainability

Owner не получает:
- chain-of-thought;
- hidden reasoning;
- raw system prompt as normal UI.

Owner получает `Decision Summary`:
- reason code;
- authoritative facts;
- evidence/source refs;
- relevant rules;
- tool/policy outcome when useful.

Approval и Escalation являются разными UX flows.

Approval выполняет frozen approved action через domain service после revalidation.

## 16.5. Calendar / clients / orders / payments

Calendar visualizes Appointments/Holds/Blocks and invokes Scheduling services.

Operational calendar updates не создают BusinessConfigurationRelease.

Versioned changes (Service/Pricing/Workflow/etc.) проходят:
```text
Draft → Validation → Diff/Preview → Publish
```

Industry terminology меняет UI labels, но backend vocabulary остаётся canonical.

Customer Payments Stage 13 и Plan & Billing Stage 15 находятся в разных sections.

## 16.6. Business configuration UI

Knowledge/Portfolio/Services/Pricing/Scheduling/PaymentTerms/AI style/autonomy/automations редактируются product-level abstractions.

Owner не выбирает raw OpenAI model ID и не получает arbitrary system-prompt editor.

Connections UI показывает health/capabilities, но не secrets.

## 16.7. API boundary

Frontend:
```text
Business Console
→ authenticated Application API / Query Services
→ Domain/Application Services
```

Нет direct DB access.

Files выдаются через authorization + signed object URL.

Commands выражаются business operations (`cancel_appointment`, `publish_configuration`), а не generic mutable status PATCH.

Read projections/query DTO допустимы, но не являются source of truth.

## 16.8. Form factor

MVP — responsive web application, хорошо работающий на phone/desktop.

Native iOS/Android не являются prerequisite.

## 16.9. Platform Operations

Platform operator не становится WorkspaceMember/OWNER всех tenants.

Добавляется отдельный platform authorization plane, концептуально `PlatformRoleAssignment`.

Platform Ops exception-first и показывает:
- Workspace health;
- integrations;
- billing/service mode;
- AI/tool failures/cost;
- jobs/events;
- platform config;
- security/support/audit state.

По умолчанию Workspace customer content скрыт.

## 16.10. Support access

`SupportAccessGrant`:
- workspace scoped;
- platform actor scoped;
- reason required;
- explicit scopes;
- expiration/TTL;
- audit.

SupportAccessGrant не создаёт WorkspaceMembership.

Support mode сохраняет реального actor `PLATFORM_SUPPORT`; silent impersonation Business owner запрещена.

Support access read-only by default.

Support writes только через narrow application commands/domain services.

## 16.11. Platform configuration

Platform Ops не является generic CRUD по database.

Model Profiles, Prompt Registry, Industry Packs, Plans, Feature Flags и другие control-plane objects используют versioning/validation/diff/publish/audit where applicable.

### Delivery Horizon — UI/Ops

**MVP — Business Console**
- responsive web;
- login;
- Action Center;
- Inbox/conversation detail;
- takeover;
- approvals/escalations;
- calendar/appointments/blocks;
- clients;
- basic request/order view;
- customer payment state;
- concierge onboarding review;
- knowledge/portfolio review;
- connection health;
- basic settings/plan/usage.

**MVP — Platform Ops**
- workspace directory/health;
- integration status;
- subscription/service mode;
- basic AI usage/cost;
- failed jobs/events;
- SupportAccessGrant;
- read-only support view;
- AI/tool trace diagnostics;
- audit;
- narrow retry/resync actions.

**CORE_POST_MVP**
- full self-service Configuration Center;
- release diff/rollback UI;
- multi-member/multi-Business management;
- external calendars/notification center;
- richer platform roles/feature flags/support workflows.

**FUTURE_OPTIONAL**
- native mobile apps;
- push;
- white-label;
- advanced BI;
- visual no-code workflow editor;
- reseller/enterprise consoles.

---

# 17. Security / Privacy / Compliance Audit — LOCKED

## 17.1. Threat model

Security architecture assumes possible:
- malicious external Client;
- prompt/indirect injection;
- hostile upload;
- compromised user/integration;
- backend/worker bug;
- platform insider misuse;
- third-party outage/compromise;
- incorrect/hallucinated LLM tool request.

LLM correctness is never a security boundary.

## 17.2. Data classification

Use common classification concepts:
- PUBLIC;
- INTERNAL;
- CONFIDENTIAL;
- PERSONAL_DATA;
- SENSITIVE_PERSONAL_DATA;
- SECRET.

Policies for storage/logging/AI/access/retention derive from data class.

SECRET data must never enter prompts, normal logs, support UI or ordinary audit payloads.

## 17.3. Identity/session security

Do not build custom cryptography/identity primitive without need.

Browser architecture prefers secure server-managed sessions using Secure/HttpOnly/SameSite cookies with appropriate CSRF protection over long-lived browser credentials in localStorage.

Support:
- expiration;
- rotation;
- revocation/logout;
- re-auth for sensitive operations.

Platform Operations MFA mandatory before production.

Business-owner MFA architecture-supported and targeted early.

## 17.4. Tenant defense in depth

Authorization path:
```text
Authenticated Actor
→ Membership/Platform Grant
→ WorkspaceContext
→ Application authorization
→ tenant-scoped queries
→ PostgreSQL RLS
→ tenant-safe FKs
```

Client/model-supplied workspace_id is never authorization.

Workers recreate trusted WorkspaceContext.

Redis/cache never bypass canonical authorization.

## 17.5. Private file storage

Customer Object Storage private by default.

Access:
```text
auth
→ entity/workspace authorization
→ short-lived signed URL
```

Knowing object key does not grant access.

Uploads are hostile input:
- size limits;
- actual format/signature validation;
- quarantine/security scanning where appropriate;
- bounded archive handling;
- no execution of customer code.

## 17.6. Secrets / environments

Secrets live in Secret Manager/secret references:
- AI provider key;
- channel secrets;
- payment/billing secrets;
- DB credentials;
- signing keys.

Dev/Staging/Production use separate DB/storage/credentials/provider accounts where practical.

Production DB/files are not copied to developer PC as routine debugging workflow.

Local development uses synthetic/anonymized fixtures/minimized approved samples.

## 17.7. AI provider boundary

AI provider is external to our trust boundary.

`AIDataPolicy` defines per task/profile:
- allowed data classes;
- provider/model profile;
- minimum necessary context;
- media/sensitive-data allowance;
- retention/provider policy requirements.

Customer-facing AI receives only task-relevant structured state/recent messages/RAG/files.

Canonical conversation/memory remains in our DB, not provider-hosted memory.

Provider retention controls (`store:false`, ZDR where eligible/needed) are defense-in-depth, not a replacement for minimization.

## 17.8. Prompt injection

All Client content, files, images, URLs and untrusted retrieved content are treated as data, not instructions.

Instruction/trust hierarchy:
```text
Platform hard policy
→ Agent contract
→ verified Business Rules / Workflow / structured state
→ curated knowledge
→ untrusted user/retrieved content
```

Even if model follows malicious injection, ToolSetResolver/ToolGateway/PolicyEngine/RLS must prevent unauthorized effects.

KnowledgeBuild review/versioning protects against RAG poisoning/stale business rules.

## 17.9. Privacy minimization / learning / telemetry

Sensitive data is not extracted/indexed/retained unless necessary for the business purpose.

Historical/learning/eval examples are selected and sanitized; raw production PII is not copied automatically into long-term learning datasets.

Analytics/logs prefer opaque IDs/aggregates.

AI should not falsely claim to be the human owner when directly asked about its nature.

## 17.10. Consent / notices / legal flexibility

Transactional, service, reactivation and marketing purposes remain distinct.

Architecture provides:
- `ConsentRecord`/preference records where applicable;
- versioned `PrivacyNoticeRevision`;
- processing purpose references.

Consent is not hardcoded as the only legal basis; exact legal basis/controller-processor obligations are deployment-market dependent.

Vendors/subprocessors (AI/cloud/storage/payment/etc.) are tracked in compliance inventory/documentation.

## 17.11. Retention / deletion / export

`RetentionPolicy` applies by data class/source:
- messages;
- files;
- raw onboarding imports;
- generated assets;
- debug captures;
- audit;
- financial records;
- backups.

Do not retain raw imports forever without business/legal need.

`PrivacyRequest` supports applicable EXPORT/DELETE/RECTIFY/RESTRICT operations.

Deletion workflow removes/anonymizes:
- canonical data;
- Object Storage;
- caches/search projections;
- Knowledge/derived chunks;
- embeddings;
- debug copies/provider-held artifacts where applicable.

Derived personal embeddings are not exempt from deletion.

Legal/financial retention may require limited anonymized retention rather than immediate destruction.

Backup copies age out on backup retention schedule; restore process reapplies completed-deletion/tombstone state.

## 17.12. Support / security events

SupportAccessGrant is TTL/scope/reason/audit constrained.

Emergency `BREAK_GLASS` access is distinct, short-lived and specially audited.

`SecurityEvent` is separate from business AuditEvent and technical logs.

Logs redact:
- secrets/auth headers/cookies;
- full prompts by default;
- unnecessary conversation text/PII;
- payment URLs/raw uploaded content.

Full prompt/debug snapshots require explicit restricted short-lived debugging capture.

## 17.13. Public endpoint / abuse controls

Webhook/login/upload/public endpoints have:
- verification/signatures where available;
- replay/dedupe protection;
- request/file size limits;
- timeout/input validation;
- appropriate rate limiting.

Commercial quota ≠ security rate limit.

Critical payment/channel events are queued/throttled safely rather than silently discarded.

Service principals and DB roles use least privilege.

Runtime DB role is not superuser, no BYPASSRLS, and not tenant-table owner.

## 17.14. Payment/security boundary

Raw PAN/CVC is not stored for either:
- end Clients paying Business;
- Business owners paying SaaS.

Hosted/provider-tokenized flows reduce payment-data scope.

## 17.15. Incident / deployment compliance

Before production:
- incident response process;
- secret/session/connection rotation capability;
- dependency/secret scanning;
- encrypted backups and restore plan;
- initial region/vendor/subprocessor inventory;
- market-specific privacy/payment/fiscal review.

High-risk regulated verticals remain deferred and cannot lower platform safety floor.

### Delivery Horizon — Security

**MVP**
- secure auth/session;
- Workspace authorization + RLS + tenant-safe FKs;
- private Object Storage/signed URLs;
- Secret Manager;
- environment separation;
- no production data on developer machines;
- TLS;
- Platform Ops MFA;
- SupportAccessGrant;
- upload validation;
- webhook verification/dedupe;
- AI minimum-context policy;
- prompt-injection-safe tool/policy boundaries;
- log redaction;
- basic retention/export/delete process;
- encrypted backups;
- incident checklist;
- dependency/secret scanning.

**CORE_POST_MVP**
- stronger owner-MFA policy;
- advanced malware/PII redaction;
- automated privacy workflows/retention cleanup;
- consent/preferences center;
- security anomaly monitoring;
- advanced support approval;
- ZDR-required profiles for sensitive use cases where available.

**FUTURE_OPTIONAL / market-dependent**
- multi-region residency;
- enterprise SSO/SAML/SCIM;
- customer-managed encryption;
- legal hold/DLP;
- dedicated tenant deployment;
- certifications/high-risk vertical controls;
- minor/guardian flows.

---

# 18. Reliability / Idempotency / Recovery — LOCKED

## 18.1. Delivery semantics

Do not assume distributed exactly-once across DB/providers.

Core pattern:
```text
at-least-once delivery
+
idempotent processing
```

Duplicate events/commands are expected normal behavior.

## 18.2. Durable inbound Inbox

External webhooks/events:
```text
verify
→ validate envelope
→ deduplicate
→ persist InboxEvent
→ COMMIT
→ acknowledge provider
→ async processing
```

Critical event is never acknowledged permanently before durable persistence.

Provider-native stable event/message IDs preferred for dedupe.

## 18.3. Transactional Outbox

Canonical domain mutation and `OutboxEvent` are written in the same short DB transaction.

Dispatcher may deliver Outbox more than once; consumers remain idempotent.

Audit/state/outbox updates that describe one business transition should be atomic where applicable.

## 18.4. Command idempotency

Critical side-effect operations use stable idempotency key + request fingerprint.

Conceptual `IdempotencyRecord`:
- workspace;
- operation type;
- stable key;
- request fingerprint;
- status;
- result reference;
- timestamps/retention.

Same key + same request returns prior result.

Same key + different request = `IDEMPOTENCY_KEY_CONFLICT`.

Use especially for:
- Hold/Appointment conversion;
- external checkout/session;
- refund;
- provider subscription mutation;
- external sends where provider semantics support it.

## 18.5. Transactions / optimistic concurrency

Multi-entity business mutation uses short DB transaction.

External HTTP/provider call is not executed while holding long business DB transaction.

Mutable aggregates use optimistic version/CAS checks.

`STALE_STATE` causes reload/re-evaluation rather than last-write-wins.

Stale AIRun/Conversation result is not sent/applied.

Distributed lock/Redis lease may improve serialization, but never becomes sole correctness guarantee.

## 18.6. Persistent jobs

Background execution has persistent semantics:
- job id/type;
- trusted Workspace/entity refs;
- status/attempt;
- available_at;
- lease_until;
- last error;
- schema/version metadata where needed.

Workers acquire lease; dead worker lease expires and another worker can reclaim safely.

Job payloads prefer stable entity references over giant mutable snapshots.

## 18.7. Retry policy / DLQ

Errors are classified at least as:
- VALIDATION / NOT_ALLOWED / CONFLICT / STALE;
- DEPENDENCY_TIMEOUT;
- DEPENDENCY_RATE_LIMIT;
- DEPENDENCY_UNAVAILABLE;
- INTERNAL_TRANSIENT;
- INTERNAL_PERMANENT;
- UNKNOWN_EXTERNAL_RESULT.

Retryability is code/policy-driven, not LLM-driven.

Retryable errors use exponential backoff + jitter + bounded attempts/age.

Permanent/poison jobs go to Dead Letter storage/queue with operational visibility and narrow replay/retry actions.

## 18.8. Ambiguous external side effects

Network timeout does not automatically mean provider failure.

External effect result may be:
- SUCCEEDED;
- FAILED;
- UNKNOWN.

Blind retry `UNKNOWN` side effect is forbidden unless provider idempotency/reconciliation semantics make it safe.

Use provider-native idempotency keys where available.

Business state is never rolled back merely because a customer notification failed.

## 18.9. AI/tool recovery

AIRun/AIProviderCall/AIToolCall persist enough state to recover.

If state-changing tool succeeded and model continuation later fails, retry reuses stored tool result instead of executing the side effect again.

State-changing AI tools are idempotent and bound to AIRun/tool-call/request fingerprint.

Agent retries remain bounded by AgentBudget.

## 18.9.1. Business-intent idempotency — LOCKED

AIRun/tool-call keys cover technical replay within a run. Critical commands also use stable business-intent identity scoped to Workspace, action and authoritative request/quote/obligation. A new AIRun or repeated "yes" must not create another Hold, accepted Order, checkout or refund for the same intent. New genuine intent creates a new identity. Same-key/different-fingerprint remains CONFLICT. Deduplication never discards distinct provider-confirmed money movements.

## 18.10. Provider isolation / circuit breaking / workloads

External providers have explicit timeouts/deadlines and provider-scoped health/circuit-breaker policy.

Failure of image/AI/Telegram/payment provider must not unnecessarily disable unrelated subsystems.

Workloads are logically prioritized/bulkheaded:
- CRITICAL;
- INTERACTIVE;
- NORMAL;
- BULK.

Bulk onboarding/embedding rebuild cannot starve payment/customer-interactive processing.

Long-running tasks execute asynchronously.

## 18.11. Dependency degradation

Canonical truth remains PostgreSQL.

If Redis fails, durable business state survives.

If the active AI provider fails:
- inbound message persists;
- AI work retries/falls back/escalates according to policy.

If Telegram fails:
- canonical state persists;
- outbound waits/retries subject to freshness/relevance.

If Object Storage fails:
- text path may continue;
- media remains pending/retryable.

If billing provider fails:
- runtime uses local canonical subscription state.

If PostgreSQL cannot durably persist:
- mutable canonical operations fail closed;
- critical inbound event is not acknowledged as safely processed.

## 18.12. Scheduling/payment races

Availability check is advisory.

Authoritative reservation is successful DB-level ResourceAllocation/Hold transaction.

Concurrent booking conflict is normal business result.

Hold expiry/payment success race resolves from canonical transaction/state rules; provider-confirmed payment remains recorded even if booking cannot be auto-confirmed.

## 18.13. State machines / invariants

Critical entities have explicit transition commands/rules, not generic `status = request`.

DB constraints enforce invariants where possible:
- NOT NULL;
- UNIQUE;
- CHECK;
- FK;
- exclusion/overlap constraints.

Application validation supplements DB constraints.

Consistency scanners detect stuck/impossible state; auto-repair only where deterministically safe.

## 18.14. Deployments / migrations

Production schema changes follow backward-compatible:
```text
EXPAND
→ deploy compatible code
→ backfill/migrate
→ CONTRACT later
```

Old/new app/worker versions may coexist during rollout.

Runtime and migration DB roles remain separated.

Graceful worker shutdown stops accepting new work and completes/releases leases.

Application rollback should normally not require database rollback.

## 18.15. Backups / disaster recovery

Backups are not considered sufficient unless restore is tested.

Architecture requires:
- automated PostgreSQL backups/PITR capability appropriate to deployment;
- durable original object storage;
- retention;
- encrypted backup access;
- restore procedure/tests.

RPO/RTO numerical targets are not yet fixed; they must be defined before production SLA based on cost/criticality.

Derived rebuildable data (embeddings/cache/aggregates) has lower backup priority than canonical messages/payments/appointments/original files.

Disaster-recovery runbook includes:
```text
restore infrastructure/data
→ apply deletion tombstones/privacy completion
→ verify migrations/RLS/secrets
→ reconcile providers
→ recover pending outbox/jobs/holds
→ recompute late automations
→ invariant checks
→ resume traffic
```

Backlog notifications always pass late/relevance policy after recovery.

## 18.15.1. Recovery completeness — LOCKED requirements / mechanics M12

Before restored runtime can dispatch, fence old API/Workers/Scheduler and revoke/restrict old effect-producing credentials/network path as appropriate. Verify only one recovery generation can mutate/dispatch. Preserve the last primary for investigation, not as a second writer.

Completed deletion state newer than the restore point must be recovered from an approved durable deletion journal/checkpoint outside that rollback window. If unavailable, affected data remains quarantined and cannot be exposed/indexed/sent to AI until reconciliation. Exact independent retention/backup mechanism is OPEN-084; no new PII-rich global store is implied.

Restored Outbox/IdempotencyRecord may predate an already-executed external effect. Reconcile through provider IDs/stable keys before replay; ambiguous non-idempotent sends remain UNKNOWN/owner-visible, not blindly reissued. Restore tests must include a post-backup payment/send/privacy deletion plus crashed old worker. Provider event replay windows and inbound recovery limits are explicit release configuration; no promise of zero lost inbound across arbitrary outages.

## 18.16. Correlation / replay

Inbound/request/event flows carry correlation/causation IDs.

Correlation answers “what belongs to one causal chain”; idempotency answers “is this the same operation retry”.

Platform Ops can safely Retry/Replay through normal handlers; replay does not bypass authorization, idempotency or state checks.

Critical expiry uses trusted server/database time and synchronized infrastructure clocks.

### Delivery Horizon — Reliability

**MVP**
- Inbox dedupe;
- transactional Outbox;
- IdempotencyRecord for critical commands;
- optimistic concurrency/stale guards;
- short DB transactions;
- DB booking overlap protection;
- persistent jobs + leases;
- bounded exponential retry+jitter;
- DLQ;
- provider timeouts;
- UNKNOWN external-result handling;
- payment/hold/tool idempotency;
- basic circuit breaker;
- priority separation bulk vs interactive;
- graceful shutdown;
- expand/migrate/contract DB changes;
- automated DB backup;
- restore runbook/test;
- basic consistency checks;
- correlation IDs;
- Platform Ops safe retry/replay.

**CORE_POST_MVP**
- advanced scanners/repair;
- richer reconciliation;
- automated DR drills;
- multi-instance failover;
- advanced queue priorities/circuit breakers;
- deployment canaries/auto rollback signals;
- formal RPO/RTO monitoring;
- chaos/failure testing;
- regional backup copies.

**FUTURE_OPTIONAL**
- multi-region failover/active-active;
- cross-region replication;
- regional queues/databases;
- advanced saga/orchestration platform if real workflow complexity requires it.

---


# 19. Infrastructure — LOCKED

## 19.1. Infrastructure philosophy
Core principle: **Boring Managed Core + Simple Stateless Compute**.

Application compute is disposable/stateless where practical. Canonical structured state lives in PostgreSQL; authoritative binaries live in Object Storage.

Loss of one application node must not equal customer-data loss.

## 19.2. Deployment shape
Backend remains modular monolith. Physical processes may be:
- API;
- Worker;
- Scheduler/Dispatcher;
- Migration command.

They may share one immutable Docker image with different entrypoints.

Logical domain services do not imply microservices. Kubernetes is not an MVP prerequisite.

## 19.3. PostgreSQL
Production PostgreSQL is preferably managed from the first real customer.

Do not keep the only production DB copy on the application VPS.

Expected capabilities:
- automated backup/PITR where supported;
- restore testing;
- restricted/private networking where possible;
- TLS/strong credentials;
- connection pooling;
- separate migration/runtime roles.

Initial topology: one primary PostgreSQL, no mandatory sharding/read replicas.

## 19.4. Object Storage
Original customer binaries live in private S3-compatible Object Storage:
- images/portfolio;
- documents;
- voice/video;
- generated assets;
- raw imports.

PostgreSQL stores metadata/object refs, not large binaries.

Application depends on a common ObjectStorage abstraction (put/get/delete/head/multipart/signed URL). Exact provider is deployment-specific.

Workspace paths are namespaced; separate bucket per Workspace is not default.

## 19.5. Upload path / lifecycle
Large Business Console uploads prefer direct authorized presigned upload.

Channel files are streamed to Object Storage where practical.

Untrusted files pass quarantine/security processing.

Temporary worker disk is bounded/ephemeral.

Lifecycle policies implement retention/cost control. Versioning is additional protection, not a complete backup.

## 19.6. Queue / Redis
MVP default durability layer:
```text
PostgreSQL
├── Inbox
├── Outbox
├── Automation due state
└── durable Jobs
```

Dedicated broker is not required initially.

Redis is optional and noncanonical. Queue implementation remains replaceable if measured DB contention/throughput justifies it.

## 19.7. Frontend / compute / networking
Business Console is responsive web/static frontend through CDN/edge.

Business Console and Platform Ops have separate logical surfaces/hostnames.

TLS required and renewed automatically.

Compute may be one Docker VPS or managed container/PaaS; critical DB/files are externalized.

API is stateless-ready for replicas; workers scale independently via persistent jobs.

## 19.8. Secrets / environments / CI
Secrets are injected at runtime and never baked into image/Git.

At minimum: LOCAL / STAGING / PRODUCTION with separate DB/storage/secrets/provider credentials as applicable.

Deployment:
```text
Git → CI/tests/security → immutable image → Registry
→ migration step → API/Workers deploy → health checks
```

Infrastructure should be reproducible/declarative through IaC; exact tool is open.

## 19.9. Region / backups
MVP uses one production region chosen by market/legal/latency/provider/cost needs.

App/DB/storage should be geographically colocated where practical.

Managed PostgreSQL backup/PITR + tested restore is MVP expectation.

Provider-independent backup/replication is CORE_POST_MVP where justified.

Derived embeddings/summaries/aggregates/caches are rebuildable.

### Delivery Horizon — Infrastructure
**MVP:** one region; Dockerized API/Worker/Scheduler; managed PostgreSQL+pgvector; backup/PITR+restore test; private S3-compatible storage/quarantine; PostgreSQL Jobs; DNS/TLS/secrets; environment separation; CI; basic IaC.  
**CORE_POST_MVP:** replicas/worker pools; DB HA/pooler; Redis if justified; provider-independent backup; private CDN; autoscaling/canaries.  
**FUTURE_OPTIONAL:** Kubernetes; dedicated broker/event streaming; dedicated vector/search; multi-region; dedicated tenant deployments; GPU/self-hosted models.

---

# 20. Observability / AI Cost Control / Analytics — LOCKED

## 20.1. Separate concerns
Three separate concerns:
1. technical observability;
2. AI/infrastructure cost control;
3. product/business analytics.

Metrics/Logs/Traces are distinct from AuditEvent/SecurityEvent/UsageEvent.

No universal everything-log.

## 20.2. Telemetry
Instrumentation should be OpenTelemetry-compatible. Exact managed vendor is replaceable.

Correlation/Causation IDs connect asynchronous chains across webhook/job/AIRun/tool/outbox/provider calls.

Trace ID is execution-specific; Correlation ID may span multiple async traces.

## 20.3. Privacy / cardinality
Ordinary telemetry excludes raw message text, unnecessary PII, file content, secrets, auth headers/cookies, payment URLs and full prompts by default.

Metrics labels stay low-cardinality. Workspace/client/conversation identifiers belong in searchable traces/logs/analytics, not massive metric label sets.

## 20.4. System signals
Track:
- traffic;
- latency p50/p95/p99;
- errors;
- saturation;
- inbound persistence latency;
- ConversationTurn→AgentOutcome;
- end-to-end reply latency;
- Inbox/Outbox/job/automation lag.

Expected business outcomes are not system errors.

PostgreSQL/provider health is first-class.

## 20.5. AI observability
AIRun/tool telemetry includes:
- task/model profile/snapshot;
- tokens/cache/output;
- latency/retries/provider error;
- tool calls;
- stale-result rate;
- escalation/human intervention classification;
- forbidden-tool attempts;
- config/prompt/knowledge revisions.

Expected human steps are separated from corrections/failures.

## 20.6. Cost attribution
Provider usage is converted to historical estimated cost using versioned/effective provider price reference.

Internal cost is attributed by Workspace/feature/task/model/time.

Provider financial costs are reconciled asynchronously against internal attribution.

`CostGuard` is separate from QuotaService and Security RateLimit. It may throttle/block optional expensive work but cannot reduce safety/quality floor or break essential continuity.

## 20.7. Product analytics
Analytics derive from domain outcomes/workflow milestones, not vanity page/message counts.

Useful outcomes include booked/quote accepted/order/paid/correctly escalated/correctly rejected.

Key metrics include:
- Autonomous Resolution Rate over eligible cases;
- escalation reasons;
- owner corrections;
- response time;
- abandonment reason;
- owner escalation response time;
- knowledge gaps;
- pricing override;
- scheduling offer/hold conversion;
- payment/automation outcomes.

MVP can use PostgreSQL projections/aggregates; warehouse is deferred.

## 20.7.1. Pilot value and denominators — LOCKED measurement

Measure eligible cases / all relevant inquiries, autonomous resolution among eligible AND all relevant inquiries, owner active minutes/interventions per request, owner waiting time, delivered/unavailable notifications, next-correct-outcome conversion and successful-journey cost (including retries/media/support where measurable). Missing measurements are labelled unknown, not zero. Short 20–50-case calibration is not proof of rare-event safety; critical-suite zero violations is a sampled release gate, not a guarantee of zero production risk.

## 20.8. SLI/SLO / alerts
Critical journey SLIs are required; exact numeric SLOs are deployment decisions.

Alerts must be actionable and deduplicated/root-cause grouped.

User-visible symptoms have priority over raw resource utilization.

Synthetic monitoring uses safe internal test Workspace.

## 20.9. Retention / sampling
Telemetry has its own retention/sampling.

Sampling never applies to canonical payment/business/audit state.

Structured telemetry records application/deployment version and relevant AI config revisions.

### Delivery Horizon — Observability
**MVP:** managed observability; OTel-compatible metrics/logs/traces; correlation; API/queue/DB/provider health; AI tokens/tools/errors/cost; per-Workspace cost attribution; provider reconciliation; basic CostGuard; system/AI/product/unit-economics dashboards; critical alerts.  
**CORE_POST_MVP:** formal SLO/error budgets; advanced sampling/correlation; profitability/cohort analytics; richer business dashboards; advanced CostGuard; separate analytics store if justified.  
**FUTURE_OPTIONAL:** large warehouse; anomaly ML; FinOps; predictive analytics; safe automated routing optimization; enterprise telemetry export.

---

# 21. Scaling — LOCKED

## 21.1. Scaling philosophy
Scaling is metric-driven, not user-count-driven.

Preferred progression:
```text
optimize
→ vertical scale
→ horizontal stateless compute
→ workload pools
→ cache/specialized infra if measured
→ partition/offload
→ cells/sharding only when necessary
```

Premature distributed architecture is rejected.

## 21.2. API / Workers / noisy neighbor
Stateless API scales horizontally without sticky-session correctness dependency.

Workers scale independently.

Workload classes: CRITICAL / INTERACTIVE / NORMAL / BULK.

Separate worker pools appear before full microservice extraction.

Noisy-neighbor protection combines entitlements, quotas, security rate limits, concurrency caps, CostGuard, workload priorities and later fair scheduling.

## 21.3. PostgreSQL scaling ladder
Preferred order:
1. query/index fixes;
2. connection pooling;
3. vertical scale;
4. remove unnecessary OLTP work;
5. analytics offload/read replica where safe;
6. partition large append-heavy tables;
7. cells/shards later.

RLS is never disabled for performance.

Tenant-aware indexes are required.

Strongly consistent payment/booking/current-workflow reads remain primary.

## 21.4. Queue / Redis
PostgreSQL Jobs remain until measured queue polling/contention/backlog harms DB/SLO.

Dedicated queue can replace transport while preserving Inbox/Outbox/idempotency/retry/domain semantics.

Kafka is not a generic requirement.

Redis enters only on measured cache/rate-limit/coordination/queue optimization need and remains noncanonical.

Caches are tenant/version scoped with TTL/invalidation.

## 21.5. RAG / search
pgvector remains default.

Scale path:
```text
filtered exact search
→ tuning/indexing
→ HNSW/approximate if measured
→ workload isolation
→ dedicated vector infra only if needed
```

Canonical Knowledge stays PostgreSQL even if embeddings move.

PostgreSQL FTS remains default until measured need for dedicated search.

## 21.6. Storage / external providers
Direct/multipart uploads prevent API bandwidth bottleneck; media workers scale separately.

Storage lifecycle/egress/private CDN are metric/classification driven.

AI/channel provider capacity is finite; scheduler applies concurrency budgets/backpressure. More workers do not solve provider throttling.

The selected aggregator/direct adapters are required by v0.28 switchability. Further providers require measured need + Stage 22 evals; each active route requires approval.

## 21.7. Heavy reads / exports
Query Services are bounded and paginated.

Large export is async → Object Storage → signed download.

Analytics projections/aggregates are preferred before allowing BI workload to harm OLTP.

## 21.8. Future Cell Architecture
If one data plane reaches practical limit, preferred direction is Workspace-based cells:
```text
Platform Control Plane
→ Workspace placement
→ Cell A / Cell B / Cell C
```

Workspace is natural placement/shard unit.

Do not add cell_id prematurely to all domain tables.

Cross-Workspace analytics is offloaded, not synchronous joins across production cells.

## 21.9. Service extraction
Modular monolith remains until concrete need:
- independent scaling;
- failure isolation;
- security boundary;
- different infrastructure;
- independent team/deployment.

Likely early extraction candidates: media/bulk/notification/AI workers.

Core transactional Pricing/Scheduling/Payments/Workflow stay together longer.

## 21.10. Backpressure / capacity
Queues/admission/concurrency are bounded.

Large imports are chunked/checkpointed, not giant transaction/prompt.

Capacity planning uses p50/p95/largest tenant/peak factors and operational headroom.

Every major new infrastructure component requires measured evidence/ADR.

### Delivery Horizon — Scaling
**MVP:** stateless-ready API; worker concurrency; Postgres Jobs; tenant indexes; bounded queries; bulk/interactive priorities; basic per-Workspace caps; provider backpressure; bounded AI/RAG context/results; capacity metrics.  
**CORE_POST_MVP:** replicas; worker pools; DB HA/pooler; Redis if justified; partition/read replica; analytics offload; fair scheduling; dedicated queue if justified; advanced vector indexing; autoscaling/private CDN.  
**FUTURE_OPTIONAL:** cells; multiple DB clusters; regional placement; dedicated vector/search; event streaming; selective microservices; multi-region; dedicated enterprise cells.

---

# 22. Testing + AI Evals — LOCKED

## 22.1. Two quality systems
Software testing verifies deterministic correctness.

AI Evals verify probabilistic behavior/domain/tool/safety quality.

Neither replaces the other.

## 22.2. Software testing
Use a pyramid:
- unit;
- property/invariant;
- real PostgreSQL integration;
- provider contract/sandbox;
- targeted E2E;
- concurrency/recovery/security.

PostgreSQL-specific RLS/range/exclusion/locking/pgvector behavior is tested against real PostgreSQL.

Tenant isolation has a dedicated cross-layer suite covering API/repository/jobs/tools/files/RAG/support.

Migration tests are mandatory.

## 22.3. Reliability/security executable tests
Critical commands are repeated with same idempotency key; same key/different payload must conflict.

Crash points test before/after DB commit/provider effect/result persistence/worker lease/Outbox redelivery.

Scheduling/payment races preserve invariants.

Stage 17 security boundaries become executable regression cases.

## 22.4. Eval concepts
Platform quality concepts:
- EvalSuite / EvalSuiteRevision;
- EvalCase;
- EvalRun / EvalCaseResult;
- EvaluatorDefinition;
- HumanReview;
- AIReleaseCandidate;
- ProductionBaseline.

Not every concept must be a DB table in MVP.

## 22.5. EvalCase semantics
EvalCase defines structured initial state/context, expected facts, allowed/forbidden outcomes, expected tool behavior, risk/failure labels.

Do not require one exact assistant sentence.

EvalRun pins model snapshot/Profile, PromptRevision, Tool/schema versions, KnowledgeBuild and BusinessConfigurationRelease.

Probabilistic cases may use repeated trials; single-run success/critical violation rate matters more than pass@N.

## 22.6. Hard gates / tool correctness
Critical violations are hard blockers:
- unauthorized mutation/refund;
- fake payment success;
- invented availability/confirmed price;
- cross-tenant exposure;
- security/safety violation.

High average score cannot compensate.

Tool selection, arguments, sequence and mutation count are evaluated separately.

Pricing/scheduling/payment evals forbid invented authoritative facts.

Human takeover/staleness must suppress AI send.

## 22.7. RAG / injection
Retrieval and grounded answer quality are evaluated separately.

Suites verify authority/currentness/conflict handling/tenant filtering/no hallucination without evidence.

Persistent adversarial suite covers direct/indirect prompt injection from messages/files/images/RAG and impersonation/exfiltration attempts.

Success criterion is actual system outcome: no unauthorized data/state effect.

## 22.8. Quality hierarchy / onboarding / vision
Priority:
```text
Security
→ Domain Correctness
→ Tool Correctness
→ Grounding
→ Workflow Completion
→ Communication Quality
→ Cost/Latency
```

Vision perception is separated from feasibility.

GeneratedAsset must never be represented as real portfolio.

Onboarding evals require conflicts/missing critical data to surface rather than silently become rules.

## 22.9. Regression data / evaluators
Start with curated synthetic scenarios.

Serious production AI bugs should become sanitized/minimized regression cases where possible.

Suites are versioned and may use DEVELOPMENT/REGRESSION/HOLDOUT/ADVERSARIAL/REGRESSION_CRITICAL splits.

Use:
- deterministic evaluators for state/tools/money/security;
- rule evaluators for explicit constraints;
- model judges for semantic/style;
- human review for nuanced/high-risk/visual cases.

LLM judge is not authoritative for money/security/tool correctness.

## 22.10. Offline / shadow / canary / rollback
Promotion path:
```text
offline eval
→ shadow/internal when privacy permits
→ pilot/canary
→ wider rollout
```

Shadow runs dry-run/no side effects.

New model snapshot is never auto-promoted merely because provider released it.

Prompt/tool/schema/KnowledgeBuild changes use relevant regression gates.

AI behavior can rollback independently through versioned mappings.

## 22.11. CI / release gates
Fast deterministic tests run per commit.

AI-touching changes run fast relevant AI regression.

Release runs full critical software + AI/adversarial suites; larger benchmarks may be nightly/on candidate releases.

Release gates:
1. Code Correctness;
2. AI Safety & Domain Correctness;
3. Quality / Cost / Latency Regression;
4. Controlled Production Promotion.

Critical safety gates cannot be traded away for lower cost.

## 22.12. Feedback loop
```text
Production
→ telemetry/correction/incident
→ failure classification
→ sanitized EvalCase
→ fix
→ regression
→ controlled release
```

Continuous learning does not mean live self-modification.

Eval calls are platform internal cost, not customer quota.

### Delivery Horizon — Testing/Evals
**MVP:** unit/property tests; real PG/RLS/migration/provider/concurrency/idempotency/recovery; critical E2E; EvalCase/Suite format; first vertical tool/pricing/scheduling/payment/RAG/injection suites; cost/latency tracking; hard gates; test Workspace; rollback.  
**CORE_POST_MVP:** larger holdouts; automated shadow/canary; human review UI; judge calibration; advanced vision/adversarial/chaos/load; automated feedback→eval pipeline; formal quality dashboards.  
**FUTURE_OPTIONAL:** dedicated eval platform; judge ensembles/red-team generation; continuous shadow; advanced statistics/model tournaments; safe automatic routing optimization; enterprise eval packs.

---


# 23. MVP Scope + Acceptance Criteria — LOCKED

## 23.1. MVP product hypothesis

The first production release must prove that AI Service Manager can autonomously move a meaningful share of real customer inquiries from first message to the next correct business outcome while escalating only cases that genuinely require the owner.

Primary end-to-end proof:
```text
Client → Telegram → understand/intake
→ verified Knowledge / Portfolio / Assessment
→ configured pricing or Owner Quote
→ availability → ReservationHold
→ deposit/payment → Appointment
→ reminders / continued communication
```

The MVP is not judged by number of AI messages, dashboards or integrations.

## 23.2. First vertical

First production Industry Pack is **Tattoo**.

Tattoo remains a stress-test of universal architecture because it requires:
- free-form conversations;
- images;
- style/portfolio matching;
- progressive intake;
- feasibility/assessment;
- exact/range/owner pricing;
- scheduling;
- deposit;
- escalation.

The universal platform remains industry-agnostic.

## 23.3. First autonomous service scope

Primary autonomous happy path:
```text
NEW_TATTOO
```

Minimum intake:
- idea/subject;
- reference image(s) where available;
- placement/body part;
- approximate size;
- style/relevant visual characteristics.

Complex/risky categories such as cover-up, unusual unsupported technique, health/medical questions, minor-specific flows or missing/conflicting critical rules are allowed to route to `NEEDS_HUMAN`/disabled safe handling rather than autonomous completion.

## 23.4. Initial tenant shape

MVP optimizes the UI/operations for:
```text
1 Workspace
→ 1 Business
→ 1 main Location
→ 1 primary Owner/Provider
→ 1 primary bookable Resource
→ 1 Telegram connection
```

The underlying architecture keeps multi-Business/multi-member/multi-resource concepts but the first UI need not expose their full complexity.

One primary customer language, business currency and timezone are sufficient for the first Business.

## 23.5. Channel / media

Required customer-facing channel:
- Telegram only.

Primary mode:
- PROFILE_AUTOMATION where compatible with first Business.

Customer media:
- text;
- image.

Not required in first release:
- voice;
- video;
- arbitrary customer-document ingestion;
- VK/MAX/other customer channels.

Channel capability limits are handled explicitly; the system does not pretend proactive messaging is available when provider capabilities do not allow it.

## 23.6. Vision / Portfolio / image generation

MVP includes:
- inbound image storage;
- Vision structured analysis;
- portfolio metadata/analysis;
- portfolio matching/retrieval.

Vision provides observations, not final business feasibility authority.

`MY_WORK` lineage must be preserved; Client reference/GeneratedAsset can never be presented as the owner's real portfolio.

AI image generation is excluded from MVP.

## 23.7. Knowledge / onboarding

Knowledge/RAG is required for:
- service/style information;
- FAQ;
- studio policies;
- preparation instructions supplied by Business;
- deposit/cancellation/business rules.

First Businesses use **Concierge Onboarding**.

Historical conversations may be imported/analyzed to propose:
- rules;
- FAQ;
- communication style;
- conflicts/gaps.

Historical extraction does not publish critical rules without owner confirmation.

A fully self-service universal onboarding constructor is not required before the pilot.

## 23.8. Pricing scope

MVP pricing supports:
- configured fixed or bounded owner-formula exact price;
- configured/validated range;
- `OWNER_QUOTE` / `NEEDS_HUMAN`.

The Agent cannot invent an authoritative custom final tattoo price or arbitrary discount.

Owner Quote is a normal production workflow:
```text
AI completes intake
→ Action Center
→ Owner supplies/approves price
→ Quote
→ AI continues
```

Sent Quote remains immutable/versioned according to Stage 11.

Advanced arbitrary pricing DSL/ML predictive pricing are excluded.

## 23.9. Scheduling scope

MVP Scheduling:
- one provider Resource;
- working hours;
- AvailabilityOverrides/days off;
- service duration;
- buffers;
- AvailabilityOffer;
- ReservationHold;
- ResourceAllocation;
- Appointment;
- cancel;
- simple safe reschedule.

Not required:
- simultaneous multi-resource booking;
- group/capacity booking;
- recurring schedules;
- external calendar sync;
- routing/travel optimization;
- fully automated multi-session planning.

Multi-session domain entities may exist; only the next required session must be schedulable.

## 23.10. End-client payments

MVP uses one PaymentProvider per Business through hosted checkout/payment link.

Required:
- PaymentTerms for no prepayment/fixed deposit/percentage deposit/full prepayment;
- PaymentRequest;
- PaymentSession;
- PaymentTransaction;
- provider-verified webhook;
- idempotency/reconciliation;
- Hold→Payment→Appointment flow.

Raw Client PAN/CVC never touches platform.

Authorized Owner may manually confirm allowed offline/cash/bank-transfer payment through audited command.

Client claim/screenshot is not authoritative payment evidence.

Refund is Owner-approved; autonomous refunds are excluded.

## 23.11. Critical transactional golden path

Canonical first-master path: request/approved assessment → Quote → QuoteAcceptance → Order/next Session → fresh Hold → fixed configured deposit → provider-confirmed satisfied obligation → revalidate Hold → Appointment. Percentage/full prepayment require an exact agreed base. Services configured NONE convert a valid Hold without checkout/payment confirmation; they do not fabricate paid status. See §§11.10 and 13.12 for the complete contract.

Late payment is recorded independently; expired/cancelled state requires recovery rather than fabricated booking.

## 23.12. Automations

Required MVP automations:
- Appointment reminder;
- payment reminder / Hold warning;
- bounded waiting-for-client follow-up;
- Owner escalation notification.

All use Stage 14 relevance/quiet-hours/frequency/idempotency rules.

Excluded:
- marketing/reactivation;
- review campaigns;
- broad AI sales sequences;
- SMS/email multi-channel fallback trees.

## 23.13. Business Console

MVP Business Console includes:
- Action Center;
- Inbox / Conversation detail;
- Human takeover/resume;
- Approvals / Escalations;
- Calendar / Appointment detail;
- Clients;
- Request/Project detail;
- customer payment state;
- basic Business Configuration visibility/edit/review;
- Portfolio/Knowledge review needed for concierge onboarding;
- Telegram connection health;
- basic Plan/Usage view.

Excluded:
- full no-code workflow builder;
- advanced BI;
- native mobile applications;
- multi-location management;
- complex team/enterprise administration;
- raw prompt/model editor.

Critical configuration may be prepared through concierge/internal tooling but owner must review and approve key production config.

## 23.14. Platform Operations

Platform Ops is required before first real client.

Minimum:
- Workspace health;
- connection/provider health;
- failed Jobs/DLQ;
- AIRun/tool diagnostics;
- billing/service mode visibility;
- SupportAccessGrant;
- audit;
- safe retry/replay/resync.

No generic DB CRUD/god-mode impersonation.

## 23.15. SaaS billing rollout

Two rollout milestones are distinct:

### Production Pilot
First Business may use a normal Entitlement-controlled `TRIALING` or `ACTIVE + COMPED` Subscription.

No hidden pilot bypass is allowed.

Real recurring charge to Business owner is not a blocker for first production learning.

### Commercial MVP
Before broader paid self-service rollout:
- hosted SaaS checkout;
- tokenized owner payment method;
- Subscription webhook;
- BillingInvoice projection;
- PAST_DUE/GRACE handling;
- basic Usage view;
- repeatable paid onboarding.

One commercial plan revision is sufficient initially.

## 23.16. MVP autonomy contract

| Action | MVP autonomy |
|---|---|
| Service/request identification | AUTO |
| Intake collection | AUTO |
| Verified Knowledge response | AUTO |
| Vision analysis | AUTO |
| Portfolio retrieval | AUTO |
| Configured exact/range price | AUTO |
| Availability query/offers | AUTO |
| Hold after explicit Client choice | AUTO |
| Deterministic deposit/payment link | AUTO |
| Confirm booking after satisfied required payment or explicit NONE policy | AUTO with current Hold/acceptance/assessment |
| Deterministic reminder/follow-up | AUTO |
| Custom final tattoo quote | OWNER / configured rule |
| Discount exception | OWNER |
| Refund | OWNER |
| Complex/unsupported request | ESCALATE |
| Medical/health advice | DISABLED / safe handoff |
| Minor-specific flow | DISABLED MVP |
| Mark paid from Client claim | DISABLED |
| Change critical Business Rules | DISABLED |
| Change own permissions/autonomy | DISABLED |

First production defaults to conservative escalation when evidence/rules are missing/conflicting/low-authority.

## 23.17. Explicit MVP exclusions

The first production scope excludes:
- VK/MAX/WhatsApp/Instagram customer automation;
- voice/video customer processing;
- AI image generation;
- multi-location/multi-provider/multi-resource scheduling;
- external calendar sync;
- recurring/group scheduling;
- advanced pricing formulas/ML price prediction;
- autonomous refunds;
- escrow/wallet/splits/payouts;
- marketing/reactivation campaigns;
- native mobile apps;
- full no-code workflow builder;
- advanced BI;
- arbitrary additional AI integrations beyond the selected aggregator/direct branch adapters; uncontrolled cross-provider fallback;
- Redis as requirement;
- Kafka;
- Kubernetes;
- dedicated vector/search DB;
- enterprise SSO/multi-region/dedicated tenant infrastructure.

These remain architectural expansion paths, not missing MVP features.

## 23.18. Golden Journeys

### A — Standard New Tattoo
Text + reference → intake → approved assessment → fixed/formula/Owner Quote → acceptance → Order/Session → Hold → configured payment or NONE → Appointment (§13.12).

### B — Owner Quote
AI completes intake → Pricing needs human → Action Center → Owner price → Quote → AI continues → booking/payment.

### C — Unsupported / Complex
Unsupported style/cover-up/uncertain case → safe escalation → Owner decision, no fabricated feasibility.

### D — Slot Race
Two Clients compete for one slot → exactly one authoritative Hold/allocation, other receives conflict/new options.

### E — Late Payment
Hold expired before provider-confirmed payment → money recorded → no automatic fake Appointment → escalation/recovery.

### F — Reschedule / Cancel
Current Appointment → policy/availability → safe new allocation or cancellation → history/reminder updates; refund stays Owner-authorized.

### G — Human Takeover
Owner takes control → pending AI output suppressed → human conversation → explicit resume → AI reads latest canonical state.

### H — Follow-up
Client waiting → due Automation → relevance check → bounded follow-up; already answered → SKIPPED.

### I — Prompt Injection
Client attempts policy override/data exfiltration/refund → no cross-tenant data, no unauthorized mutation.

### J — Dependency Failure
AI/channel/provider transient failure → inbound/canonical state durable → recoverable job → no duplicate/stale side effect.

## 23.19. Production readiness gates

All gates must pass independently:

- `DOMAIN_READY`
- `AI_READY`
- `SECURITY_READY`
- `RELIABILITY_READY`
- `BUSINESS_CONFIG_READY`
- `OPERATIONS_READY`
- `PRIVACY_READY`
- `FISCALIZATION_READY` — conditional RU gate before live payment activation

### DOMAIN_READY
Hard acceptance:
- escaped double booking = 0;
- duplicate payment/refund canonical effects = 0;
- invalid state mutation = 0;
- cross-Workspace state/FK corruption = 0;
- Golden Journeys reach valid canonical outcomes.

### AI_READY
`REGRESSION_CRITICAL` requires zero critical violations:
- unauthorized money action;
- invented confirmed payment;
- invented booked availability;
- cross-tenant exposure;
- human takeover violation;
- other defined security/safety hard failures.

For non-critical first-vertical cases, an explicit release threshold must be set before pilot. Initial calibration target is approximately `>=95%` correct domain/tool outcome on curated eligible cases; this is not a permanent architecture constant.

### SECURITY_READY
At minimum:
- tenant isolation/RLS suite PASS;
- SupportAccess scope/expiry PASS;
- webhook verification PASS;
- signed file authorization PASS;
- secret/log redaction PASS;
- critical prompt-injection suite PASS;
- production secrets/customer data not used as ordinary developer-local data.

### RELIABILITY_READY
At minimum:
- duplicate webhook/command/payment handling PASS;
- worker death/reclaim PASS;
- Outbox redelivery PASS;
- concurrent booking PASS;
- Hold/payment race PASS;
- stale AIRun suppression PASS;
- AI/channel timeout recovery PASS;
- tested backup restore PASS.

### BUSINESS_CONFIG_READY
Readiness gates are green for the selected service:
- SERVICES;
- PRICING;
- SCHEDULING;
- PAYMENT_TERMS;
- KNOWLEDGE;
- CHANNEL;
- AUTONOMY.

Intentional `OWNER_QUOTE` is READY; unknown/unmodeled behavior is not.

Owner explicitly approves services, schedule, deposit, prices/ranges, portfolio, important rules and communication profile before publish.

### OPERATIONS_READY
Platform team can determine without ad-hoc production SQL:
- unprocessed inbound;
- failed/stuck jobs;
- connection/provider health;
- payment mismatch;
- AI escalation/tool reason;
- safe retry/replay.

Critical operational alerts exist at least for DB/inbound persistence/interactive backlog/backup/channel/AI provider/cost anomaly classes.

### PRIVACY_READY
Before real customer data:
- launch-market privacy notice/process;
- pilot/terms agreement as appropriate;
- AI-processing disclosure;
- retention policy;
- support-access policy;
- vendor/subprocessor inventory;
- payment-data boundary documented.

Exact legal wording remains jurisdiction-specific.

## 23.20. Pilot calibration

First production Business runs a conservative calibration window of roughly 20–50 meaningful conversations.

Track:
- eligible conversations;
- autonomous resolutions;
- expected/unnecessary escalations;
- owner corrections;
- missed escalations;
- response latency;
- failed sends/recovery;
- pricing/knowledge gaps;
- AI/provider cost.

Initial pilot targets:
- critical money/security/booking incidents = 0;
- missed high-risk escalation = 0;
- requests silently lost by system = 0;
- duplicate booking/payment effects = 0;
- serious incidents reconstructable in Platform Ops = 100%;
- eligible simple flows autonomous target approximately >=70%;
- owner correction on simple structured intake targeted roughly <=10–15%.

Autonomy denominators exclude workflows intentionally requiring Owner.

These percentages are calibration targets, not permanent contractual SLOs.

## 23.21. Pilot vs Commercial MVP

`Production Pilot` proves product value/safety with one real Business.

`Commercial MVP` additionally requires:
- repeatable paid SaaS billing;
- stable/repeatable onboarding;
- runbooks/deployment;
- stable first-vertical EvalSuite;
- support process;
- readiness to onboard additional paying Businesses without bespoke code forks.

## 23.22. Definition of MVP success

MVP succeeds when a real tattoo Business can connect Telegram, be onboarded, receive real Client text/images, have AI safely handle a meaningful portion of eligible conversations through price/schedule/deposit/Appointment, surface only necessary Owner decisions, and provide the owner/Platform Ops clear visibility and recovery controls.

A feature-rich platform where the owner still has to read/check every AI message is not considered successful.

Canonical detailed release scope and acceptance checklist are maintained in `06_MVP_SPEC.md`.

---


# 24. Development Roadmap — LOCKED

## 24.1. Roadmap philosophy

Implementation is **dependency-based and vertical-slice oriented**, not calendar-first and not layer-by-layer.

Preferred loop:
```text
small foundation
→ thin working vertical slice
→ tests/telemetry
→ expand capability
→ integrated Golden Journey
```

Security, tenant isolation, reliability, observability and testing are continuous workstreams, not final cleanup.

The first implementation objective is `Production Pilot`; `Commercial MVP` follows pilot learning.

Exact week/month estimates are intentionally not canonical until milestones become concrete engineering tickets.

## 24.2. Repository / engineering shape

Initial product prefers one repository/monorepo containing backend modular monolith, Business Console, Platform Ops, shared schemas/contracts, infrastructure config, software tests and AI eval assets.

Do not create repositories/microservices for domain class boundaries alone.

Exact language/framework/ORM/test framework remain implementation choices constrained by PostgreSQL/RLS/transactions, typed schemas, async jobs, webhooks, OpenTelemetry and testing needs.

## 24.3. Production Pilot milestone sequence

```text
M0 Engineering Foundation
→ M1 Tenant/Auth/DB Foundation
→ M2 Durable Telegram Messaging Backbone
→ M3 Conversation Engine + Human Control
→ M4 Read-only AI Runtime
→ M5 Tattoo Knowledge / Onboarding / Vision / Portfolio
→ M6 Request / Assessment / Pricing / Quote
→ M7 Scheduling / Hold / Appointment
→ M8 Client Payments
→ M9 Automations
→ M10 Business Console + Platform Ops completion
→ M11 Golden Journey Integration / Feature Freeze
→ M12 Security / Reliability / Eval Hardening
→ Pilot Release Candidate
```

Thin UI/Ops/testing/observability are added throughout rather than deferred to M10/M12.

## 24.4. M0 — Engineering Foundation

Required: repository, local environment, real PostgreSQL, migrations, application skeleton, tests, CI, Docker build and environment-based configuration.

DoD:
- app/database start locally;
- migration runs;
- real PostgreSQL integration test passes;
- CI runs tests;
- immutable Docker image builds;
- no production credentials/data are local dependencies.

## 24.5. M1 — Tenant / Auth / DB Foundation

Implement UserAccount, Workspace, Business, WorkspaceMembership, initial BusinessMember/Location, WorkspaceContext, authorization, RLS, tenant-safe FKs, Audit baseline and authenticated Business Console shell. Include local Plan/Subscription/Entitlement/service-mode kernel for TRIALING or ACTIVE+COMPED; paid provider billing stays M15.

Tenant isolation tests start immediately and grow with every tenant table/access path.

DoD: Owner authenticates; trusted WorkspaceContext/RLS work; Workspace A cannot access B; runtime/migration roles are separated.

## 24.6. M2 — Durable Telegram Messaging Backbone

First product vertical slice intentionally has **no AI**.

```text
Telegram Client
→ verified webhook
→ ChannelRoute / InboxEvent
→ Client / ClientIdentity
→ Conversation / Message
→ Business Console Inbox
→ manual Owner reply
→ Message / Outbox
→ Telegram
```

Add image Attachment/FileObject/Object Storage path.

DoD: inbound persists, appears in correct Workspace, image is private, manual reply reaches Client, duplicate webhook does not duplicate Message, Outbox recovery works, connection health is visible.

This is the first tangible coding target.

## 24.7. M3 — Conversation Engine + Human Control

Implement ConversationState, ConversationTurn, TurnAggregator, RequestRouter shell, awaiting-response structure, versions/stale guards, control mode and Escalation basics.

Human takeover/resume precedes state-changing autonomy.

DoD: turn grouping works; stale versions are suppressed; HUMAN control blocks automated outbound; Resume works.

## 24.8. M4 — Read-only AI Runtime

Introduce ModelGateway + selected RU_AGGREGATOR and DIRECT_PROVIDER adapters, AIProviderBranch/AIRoutingRevision, ModelProfile, PromptRegistry, ContextBuilder, Structured Outputs, AIRun/AIProviderCall/AIToolCall, token/cost/latency telemetry and first EvalSuite. Both branches pass shared contract and synthetic switch tests; all live routes enforce execution-class/data policy. Exact shortlist is §7.22.

Initial tools are QUERY-only. No Hold/booking/payment mutation tools.

DoD: Telegram→Turn→AIRun→safe reply works; versions/tool traces persist; basic injection smoke passes; secrets/unbounded DB content do not enter prompts; usage/cost is measured.

## 24.9. M5 — Tattoo Knowledge / Onboarding / Vision / Portfolio

Implement Service/Revision, Rules, Knowledge/RAG, CommunicationProfile, Portfolio, Vision/MediaAnalysis, pgvector, historical chat import, ConfigurationDraft/Validation/Release and TattooIndustryPack v1/IntakeSchema.

Initial Tattoo pack: NEW_TATTOO; COVER_UP→escalate; OTHER_COMPLEX→escalate. Add minimal Workflow runtime and DurationCase ingestion, with approved configuration required for automation.

DoD: realistic Tattoo config supports correct intake, image understanding, relevant real portfolio, verified FAQ/rules and safe unsupported-case escalation.

## 24.10. M6 — Request / Assessment / Pricing / Quote

Add ServiceRequest/provenance, approved Assessment, fixed/bounded-formula/Owner PricingEngine, PriceCalculation, Quote/QuoteAcceptance, Order/next Session, ApprovalRequest and Owner decision Action Center. Enforce same-Workspace Client access and business-intent idempotency.

Model proposes; backend validates/mutates.

DoD: journeys can reach feasible/approved request, safe rejection/escalation or immutable Quote; Owner Quote continuation works.

## 24.11. M7 — Scheduling / Hold / Appointment

Build deterministic Scheduling first: Resource, availability rules/overrides, policy, duration/buffers, AvailabilityOffer, Hold, Allocation, Appointment, cancel/reschedule, DB overlap protection and timezone/DST tests.

Only then add Agent scheduling tools based on server option/Hold IDs.

No generic `create_appointment(datetime)` tool. Include CalendarBlock/self-overlap replacement tests, approved-duration gating and NONE-prepayment booking path.

DoD: real options are offered, exactly one Hold wins a slot race, Calendar reflects canonical state. Scheduling concurrency must be stable before payment work.

## 24.12. M8 — Client Payments

Payments begin only after Hold/Appointment semantics are stable. The example below is the prepayment branch; NONE booking is already implemented in M7 and bypasses it.

Implement provider sandbox adapter, typed PaymentTerms/Request/Session/Transaction binding, provider-verified webhook, idempotency/reconciliation, manual offline confirmation and Owner-approved Refund. Add fiscal profiles/receipt obligations/owner or provider workflow and FISCALIZATION_READY; verify first merchant before live payments.

```text
Hold
→ PaymentRequest
→ hosted checkout
→ provider SUCCEEDED
→ PaymentRequest SATISFIED
→ revalidate Hold
→ Appointment
```

Required edge tests: duplicates/out-of-order webhooks, timeout/UNKNOWN, failed checkout, expired Hold, late payment, manual payment, refund authorization.

Golden Journey E late payment is a pilot blocker.

DoD: Golden Journey A reaches canonical paid Appointment.

## 24.13. M9 — Automations

Implement only Appointment reminder, payment reminder/Hold warning, bounded Client follow-up and Owner escalation notification using persistent PostgreSQL scheduling/jobs.

Tests cover cancel/reschedule invalidation, Client reply suppression, Human takeover, restart recovery, late policy and duplicate prevention.

DoD: Golden Journey H/reminders have no stale or duplicate sends.

## 24.14. M10 — Business Console + Platform Ops completion

Complete the Stage-23 pilot UI surface built incrementally in prior milestones.

Business Console: Action Center, Inbox/Conversation, Takeover, approvals/escalations, Calendar, Clients, Requests/Quotes/Payments, Knowledge/Portfolio review, basic config and connection health.

Platform Ops: Workspace/integration health, Inbox/Outbox lag, Jobs/DLQ, AIRun/tool trace, payment mismatch, SupportAccessGrant, Audit and safe Retry/Replay/Resync.

Routine pilot operations must not require SQL/SSH/manual DB edits. Pixel perfection is not a release gate.

## 24.15. M11 — Integrated Golden Journeys / Feature Freeze

Run all Stage-23 Golden Journeys A–J plus v0.28 MVP Spec §19.1 variants end to end.

At M11 enter **Feature Freeze**. After freeze only bugs, security/reliability fixes, critical UX blockers and eval/regression fixes are accepted without an explicit scope ADR.

## 24.16. M12 — Hardening / Eval / Pilot Release Candidate

Close DOMAIN_READY / AI_READY / SECURITY_READY / RELIABILITY_READY / BUSINESS_CONFIG_READY / OPERATIONS_READY / PRIVACY_READY; FISCALIZATION_READY before RU live payments.

Build `Tattoo EvalSuite v1` covering normal/missing/multi-message/slang/image/unsupported/cover-up/Owner Quote/pricing hallucination/scheduling/payment claims+late payment/RAG conflicts/prompt injection/takeover/staleness.

Critical violations remain zero-tolerance. Concrete non-critical evaluator/denominator/repetition settings are implemented using Stage-23 calibration targets.

Hardening includes RLS/auth/session/files/webhooks/support/secrets checks, duplicates/races/retry/failure injection, backup restore, dashboards/alerts and launch-market privacy inputs.

## 24.17. Pilot Release Candidate

Pilot RC pins application/container version, DB schema/migration version, TattooIndustryPack, Prompt revisions, ModelProfile revisions, Tool/schema versions, KnowledgeBuild, BusinessConfigurationRelease and EvalSuiteRevision.

Pilot deployment uses a known release bundle, not undefined moving `main`.

## 24.18. Parallel tracks

Throughout M0–M12: backend/domain, tests, Business Console, Platform Ops, observability/cost, AI Evals, security and CI/infrastructure run continuously.

With multiple developers, UI/Ops/Knowledge tracks may run in parallel after dependencies are stable. Payments should not outrun Scheduling/Hold semantics.

## 24.19. Schema rollout discipline

Do not pre-create every future table. Introduce entities with the milestone that needs them, but immediately use canonical semantics.

Typical progression:
- M1 tenant/auth/audit/local subscription-entitlement kernel;
- M2 channel/client/conversation/message/files/Inbox/Outbox;
- M3 turns/state/escalation;
- M4 AI branches/routing/selected adapter pair;
- M5 knowledge/portfolio/config/workflow runtime/duration cases;
- M6 request/assessment/pricing/quote/acceptance/order/session/approval;
- M7 scheduling/hold/appointment;
- M8 client payments/fiscalization obligations.

Do not create temporary incorrect abstractions such as generic `Booking` for convenience.

## 24.20. Implementation completeness

Internal states may be `SKELETON`, `PILOT_READY`, `EXPANSION_READY`.

MVP capabilities must reach `PILOT_READY`; future concepts need not be implemented.

Do not implement empty VK/MAX/unused-supplier adapters. The selected aggregator and direct adapters are concrete v0.28 requirements, tested with the same contracts; simultaneous live deployment is not required.

## 24.21. Technical spikes

Short spikes are allowed for high-risk assumptions: Telegram connection mode, RLS/WorkspaceContext, Resource overlap/concurrency, AI Structured Outputs/tool loop, Object Storage signed flows and payment sandbox/webhook/idempotency.

Spike outputs are a decision/constraint and reproducible test. Prototype code is not automatically production code.

## 24.22. Feature Definition of Done

Where applicable, `PILOT_READY` requires domain behavior, authorization/tenant isolation, idempotency/recovery, Audit/Usage/Telemetry, error taxonomy, tests, AI evals, Business Console/Ops visibility and migrations/config documentation.

Backend-only completion is not sufficient.

## 24.23. Commercial MVP sequence after Pilot

```text
Pilot
→ M13 Pilot Findings / Regression
→ M14 Repeatable Onboarding
→ M15 SaaS Billing
→ M16 Commercial Hardening
→ Commercial MVP
```

M13 turns calibration findings into fixes/regression/eval cases. M14 automates only onboarding patterns proven repetitive. M15 adds wider paid Workspace billing. M16 makes deployment/support/privacy/onboarding/unit economics repeatable for multiple paying Businesses.

Expansion to new industries/channels remains Stage 27.

## 24.24. Engineering issue template

Substantial implementation work should record: Goal, architecture/MVP/roadmap refs, domain/schema changes, APIs/commands, UI/Ops, security, reliability, telemetry/usage/cost, tests/evals and DoD.

## 24.25. Key development targets

1. Owner login + Telegram inbound + correct Workspace Inbox + manual reply.
2. Tattoo configuration + image + AI structured intake + verified Knowledge/Portfolio.
3. AI → Quote → Hold.
4. Primary product milestone: Telegram → AI → Quote → Hold → Payment → Appointment.
5. Pilot RC proves this path under duplicates, races, timeouts, restart, prompt injection, Human takeover and stale AI output.

Canonical detailed sequencing is maintained in `07_DEVELOPMENT_ROADMAP.md`.

---


# 25. Production Deployment / Runbooks — LOCKED

## 25.1. Production operating principle

Production deployment is a reproducible, controlled operation with:
- immutable artifacts;
- explicit release composition;
- pre/post-deployment gates;
- rollback/recovery paths;
- version-controlled runbooks.

Normal production operation must not depend on undocumented SSH/SQL knowledge.

Stage 25 defines provider-neutral deployment semantics. Concrete cloud/payment/storage/observability vendors are selected with the first production Business/market.

## 25.2. Production topology

Pilot retains the Stage 19 shape:
```text
DNS/TLS/Edge
   ├─ Business Console / Platform Ops
   └─ Application API
          ├─ Managed PostgreSQL
          ├─ Workers / Scheduler
          └─ Private Object Storage
                 + external AI/Telegram/Payment providers
```

Required supporting capabilities:
- Container Registry;
- Secret storage;
- CI/CD;
- Observability;
- backups/PITR;
- staging rehearsal.

MVP uses one production environment/region.

## 25.3. Immutable release artifact and provenance

Primary deployment artifact is an immutable container image.

Production must pin an immutable digest/version rather than relying on mutable `latest` semantics.

Build/release provenance links:
```text
production container
→ image digest
→ source commit
→ CI run
→ tests/evals
```

SBOM generation is desirable build metadata and becomes more important as the product commercializes.

## 25.4. ReleaseManifest

Introduce platform/deployment concept `ReleaseManifest`.

It records at least:
- release_id;
- source commit/build;
- container digest;
- application version;
- database schema/migration version;
- relevant IndustryPack revision;
- Prompt/ModelProfile and AIProviderBranch/AIRoutingRevision bindings;
- ToolSet/Structured Schema versions;
- platform policy/config revisions;
- EvalSuiteRevision used for release qualification.

Application release composition is distinct from a tenant's `BusinessConfigurationRelease`.

## 25.5. Independent release axes

Three major rollback/release axes remain distinct:
1. **Application Release** — code/container/schema-compatible behavior;
2. **Platform AI Configuration Release** — Prompt/ModelProfile/tool/policy mappings;
3. **BusinessConfigurationRelease** — tenant-specific services/rules/pricing/schedule/knowledge semantics.

A Business config change does not require application redeploy, and application deploy cannot silently rewrite Business rules.

## 25.6. Pre-deployment gates

Before production deployment, CI/release workflow verifies relevant:
- build/unit/integration/migration tests;
- tenant isolation/security checks;
- critical AI Evals and regression suites;
- dependency/secret/container scanning;
- immutable image build;
- ReleaseManifest generation.

Before first Pilot cutover, all Stage 23 readiness gates must be green:
- DOMAIN_READY;
- AI_READY;
- SECURITY_READY;
- RELIABILITY_READY;
- BUSINESS_CONFIG_READY;
- OPERATIONS_READY;
- PRIVACY_READY;
- FISCALIZATION_READY before RU live payment activation.

## 25.7. Database migrations

Migrations execute as a separate privileged migration job/identity.

Runtime API/Workers do not own DDL privileges.

Schema evolution follows:
```text
EXPAND
→ deploy compatible code
→ backfill/migrate
→ CONTRACT later
```

Destructive schema change and dependent code switch are not one irreversible deployment step.

Large backfills are controlled persistent jobs with progress, retry and idempotency; they do not run as application startup work.

Risky migration requires a recent recoverable backup/PITR state and a documented recovery plan.

## 25.8. Rollout / readiness / graceful drain

Logical rollout:
```text
old revision serves
→ start new revision
→ liveness/readiness
→ safe smoke checks
→ switch traffic
→ drain old API/Workers
→ stop old revision
```

Readiness validates critical internal dependencies/configuration but is not made dependent on every external provider being healthy.

Workers stop claiming new work before shutdown; persistent leases allow incomplete jobs to be reclaimed safely.

## 25.9. Smoke tests

Post-deploy smoke tests use a dedicated internal Test Workspace and avoid uncontrolled customer/financial effects.

Minimum safe checks include:
- authentication/API;
- PostgreSQL transaction;
- Object Storage put/read/delete;
- Job enqueue/claim;
- Inbox/Outbox path;
- tenant isolation smoke;
- safe AI/query-only path;
- provider/connection health.

Smoke tests do not perform arbitrary real refund/payment/client booking.

## 25.10. Deployment observation / rollback

After a deploy, an operator observes critical Stage 20 signals such as:
- error rate;
- Inbox/Outbox lag;
- interactive queue lag;
- DB errors;
- AI/provider errors;
- Telegram send health;
- payment-webhook processing.

The Pilot requires controlled/operator-triggered rollback capability, not fully automatic global rollback.

Rollback types are distinct:
- application image rollback;
- AI configuration rollback;
- Business configuration known-good activation/new corrective release;
- database/data restore or repair.

Database rollback is not the normal response to application bugs; backward-compatible migrations make application rollback/roll-forward safer.

## 25.11. Operational kill switches

Provide narrow platform safety controls rather than one global "turn off everything" switch.

Examples:
- Client AI auto-send pause globally or per Workspace;
- new payment-session creation pause;
- bulk processing pause;
- optional media/image processing pause.

Pausing AI must preserve inbound durability, owner/manual operation and canonical payment/appointment data.

Critical webhooks during maintenance are durably persisted before acknowledgement or returned a retryable failure; they are never silently discarded.

## 25.12. Change risk policy

Production changes are classified by impact/risk.

High-risk categories include:
- DB migration;
- scheduling/payment/security logic;
- AI tool/schema/policy changes;
- critical configuration.

High-risk changes require targeted tests/evals, release notes, explicit recovery/rollback plan and monitored deployment.

Emergency hotfixes may use an accelerated path but still require a minimal controlled test/release/observation flow and later regression coverage.

## 25.13. Production drift / break-glass / repairs

Normal production change is not SSH-edit-restart or ad-hoc SQL.

Emergency manual changes must be documented and reconciled back into canonical source/IaC/configuration.

Routine diagnosis uses Platform Ops/telemetry.

Emergency engineering DB access is exceptional, reasoned, time-bound, strongly authenticated and audited.

Data repair preferably uses version-controlled, scoped, validated, idempotent and dry-run-capable repair commands/jobs.

## 25.14. Secret lifecycle

Each critical secret has a known issue/rotate/verify/revoke procedure.

Production secrets include DB, channel, AI provider, payment/billing and session/signing credentials.

Where supported, rotation overlaps old/new credentials temporarily to avoid outage.

Suspected compromise triggers immediate revoke/replace/deploy/session-invalidation-as-needed/security-review flow rather than normal release cadence.

## 25.15. Backup and restore

Pilot provider selection must support managed PostgreSQL backup and PITR suitable to agreed recovery targets.

Backup is not considered operationally ready until an actual restore has been tested.

Restore strategy:
```text
restore backup/PITR into a NEW database instance
→ inspect/schema/invariant/RLS validation
→ reconnect files/secrets/application
→ privacy deletion/tombstone reconciliation
→ provider/payment/billing reconciliation
→ pending job/outbox/automation recovery
→ smoke checks
→ controlled traffic cutover
```

Do not overwrite the last primary blindly during recovery.

Derived state such as embeddings/summaries/aggregates/caches may be rebuilt.

Original binary durability/recovery follows the selected Object Storage provider policy plus any additional replication/backup policy.

## 25.16. RPO/RTO treatment

Exact numerical RPO/RTO/SLO values are **release-blocking deployment configuration** before Pilot, but are not universal architecture constants.

They implement Stage-26 planning targets and are fixed before live Pilot using:
- concrete provider capabilities;
- first Business expectations;
- cost;
- legal/operational requirements.

## 25.17. Incident severity / lifecycle

Initial operational severity:
- `SEV-1` — tenant data exposure, money/canonical corruption, escaped double-booking, DB/durability/security compromise;
- `SEV-2` — major service degradation with canonical state preserved (AI/channel/payment availability etc.);
- `SEV-3` — limited/optional/localized impact.

Incident lifecycle conceptually:
```text
DETECTED → ACKNOWLEDGED → MITIGATING → RECOVERING → RESOLVED → FOLLOW_UP
```

During incidents priority is:
1. stop harmful effects;
2. preserve incoming/canonical data;
3. restore essential service;
4. reconcile state;
5. determine cause;
6. implement permanent prevention.

## 25.18. Runbook contract

Runbooks are version-controlled and use common structure:
- Trigger/Symptoms;
- Impact;
- Immediate Safety Action;
- Diagnosis;
- Recovery;
- Verification;
- Escalation condition;
- Follow-up/regression action.

Required Pilot runbooks cover at least:
1. PostgreSQL unavailable;
2. Worker/Queue backlog;
3. AI provider degraded;
4. Telegram degraded;
5. Telegram credentials/connection invalid;
6. Payment provider unavailable;
7. Payment mismatch/reconciliation;
8. Object Storage unavailable;
9. bad application release;
10. bad Prompt/ModelProfile;
11. bad Business Configuration;
12. migration failure;
13. backup restore/disaster recovery;
14. suspected tenant-data exposure;
15. secret compromise;
16. AI cost runaway;
17. DLQ/poison event;
18. Human takeover failure;
19. Scheduling invariant alarm;
20. SaaS billing provider outage.

Canonical procedures are maintained in `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md`.

## 25.19. Controlled first-Business cutover

First production activation is progressive:
```text
provision/deploy
→ smoke tests
→ connect Telegram
→ AI auto-send OFF
→ verify real inbound + manual Owner reply
→ verify image path
→ enable AI on controlled test conversation
→ enable AI intake/knowledge/pricing
→ enable Scheduling/Holds
→ verify FISCALIZATION_READY and merchant/terms
→ enable Payments
→ enable Automations
```

Do not enable all integration/autonomy/payment surfaces simultaneously.

## 25.20. Deployment cadence / release notes

Initial policy:
- continuous integration;
- controlled production deployment.

Every green commit need not auto-deploy into a live AI/payment Pilot.

Production releases are preferably small, observable and rollbackable, with concise notes covering changes, migrations, AI config, risk and recovery path.

Avoid combining multiple unrelated high-risk domains into one release when practical.

## 25.21. Post-incident learning

Significant SEV-1/SEV-2 incidents produce concrete preventive artifacts such as:
- software regression test;
- EvalCase;
- DB constraint/invariant;
- alert;
- runbook update;
- configuration/policy improvement.

The goal is system improvement, not merely a postmortem narrative.

## 25.22. Pilot operational review

During first-client calibration, regularly review:
- inbound/stuck conversations;
- escalations/corrections;
- booking/payment exceptions;
- provider failures;
- AI cost/latency;
- recovery events.

This is an initial learning mechanism and may be automated/reduced as stability grows.

## 25.23. Pilot production readiness definition

Production operating readiness requires:
- reproducible environment;
- exact release identification/provenance;
- repeatable deploy/migration;
- application and AI rollback paths;
- successful backup restore test;
- alerts routed to an operator;
- Platform Ops usable;
- critical runbooks accessible;
- secrets rotatable;
- AI independently pausable;
- provider reconciliation procedures;
- no routine undocumented SSH/SQL dependence.

### Delivery Horizon — Production Deployment / Runbooks

**PRODUCTION PILOT**
- immutable release + ReleaseManifest;
- separate migration role/job;
- backward-compatible migrations;
- production/staging provisioning;
- DNS/TLS/secrets;
- managed PostgreSQL backup/PITR + tested restore;
- private Object Storage;
- safe smoke tests;
- AI/subsystem kill switches;
- app/AI/business-config rollback paths;
- Platform Ops + critical alerts;
- required incident runbooks;
- controlled first-Business cutover.

**COMMERCIAL MVP HARDENING**
- more automated deployment gates/canaries;
- regular restore drills;
- recurring validation/reporting of operational SLO/RPO/RTO values already fixed before Pilot;
- richer incident/reconciliation automation;
- provider-independent backups where justified;
- stronger secret rotation automation;
- formal support/on-call policy;
- richer SBOM/provenance evidence.

**FUTURE_OPTIONAL**
- automatic canary rollback;
- multi-region DR/active-active;
- cross-provider failover;
- staffed 24/7 operations;
- public status page;
- advanced incident/change-management platforms;
- enterprise compliance evidence automation.

---


# 26. First Production Client — RU-first — LOCKED

## 26.1. Market / data placement

Until multi-region expansion, the primary production market is **Russia**.

Pilot defaults:
```text
MarketProfile      = RU
HomeDataRegion     = RU
PrimaryLanguage    = ru
PrimaryCurrency    = RUB
```

Russia is not hardcoded into universal entities/services. Workspace placement/control-plane metadata resolves a `MarketProfile`, `DataResidencyPolicy` and `RegionalProviderBundle`. Domain rows remain tenant-scoped by Workspace rather than duplicating country fields everywhere.

## 26.2. DataResidencyPolicy

RU production uses an explicit data-residency policy. Primary canonical Client/Business state, original files, RAG/embeddings and ordinary production telemetry are stored in the approved RU data plane unless an explicitly reviewed processing path permits otherwise.

Cross-border/external model processing is deny-by-default for sensitive/raw contexts and is allowed only when:
- provider/contract/upstream use is approved;
- legal/privacy processing basis is confirmed;
- task/data classes are eligible;
- ContextBuilder minimizes/sanitizes data;
- provider retention/logging behavior is known;
- Stage 22 quality/safety gates pass.

`AIDataPolicy` and `DataResidencyPolicy` are evaluated together.

## 26.3. ProviderExecutionClass

AI providers/models are classified by execution trust/placement:

- `RU_LOCAL_HOSTED` — model execution inside approved RU infrastructure;
- `CONTRACTED_EXTERNAL` — contracted RU gateway/aggregator forwards to an external upstream provider;
- `DIRECT_REGION_PROVIDER` — official direct provider API under an eligible account/deployment/data route; actual live activation is conditional;
- `UNVERIFIED_PROXY` — unofficial proxy/VPN/unclear-resale path; production forbidden.

`UNVERIFIED_PROXY` cannot be used for production customer traffic. Direct OpenAI/Gemini through VPN is explicitly rejected as a production foundation.

## 26.4. RU AI provider strategy

**REVISED in v0.28, ADR-259–261.** The first RU branch is `RU_AGGREGATOR`, with PolzaAI preferred for evaluation/integration and GPTunnel as comparison/approved replacement. The second branch is `DIRECT_PROVIDER` using official model-developer APIs. Both use the same task-specific ModelProfiles and switch through versioned routing configuration (§7.21).

This supersedes the Cloud.ru-first / RU_LOCAL_HOSTED-default procurement preference. Cloud.ru/Yandex/GigaChat may still be evaluated if needed but are not mandatory initial providers. Retain DataResidencyPolicy and execution-class checks for each actual route; a Russian gateway address/payment method does not establish Russian inference/storage. Contract/data eligibility remains OPEN-075; selection as candidate does not certify production eligibility.

Polza vs GPTunnel selection uses measured task quality, full cost, p50/p95 completion latency, failures, rate limits, contract and routing transparency. One selected aggregator adapter and one selected direct adapter implement switchability; unused supplier adapters are not prebuilt.

## 26.5. Direct foreign API policy

`DIRECT_PROVIDER` means official API access under an eligible account/deployment and approved task/data processing policy. It does not mean a VPN/user-session relay. Implement the direct adapter and contract tests for switchability; enable live traffic only after applicable provider/region/data checks. Switching a branch is not a HomeDataRegion migration and does not override privacy/provider restrictions. Ineligible routes remain disabled while the eligible branch/manual operation continues.

## 26.6. RU infrastructure bundle

Recommended first implementation `RU_PILOT_V1`:
- compute: Yandex Cloud Compute VM + Docker;
- database: Yandex Managed PostgreSQL + pgvector;
- object files: private Yandex Object Storage (private + quarantine);
- secrets: Yandex Lockbox;
- image registry: Yandex Container Registry;
- application telemetry: OpenTelemetry → RU-compatible managed backend (Monium is first candidate);
- cloud-resource audit: Audit Trails where used.

Provider-specific IAM/resource IDs stay in infrastructure/IaC/adapters, never domain code. Object Storage remains S3-abstraction based. Kubernetes remains excluded.

Managed PostgreSQL automatic backup/PITR plus tested restore remain launch gates. Initial internal Pilot planning targets are RPO ≤5 min and RTO ≤4 h, subject to verification against the chosen topology and support agreement; they are not contractual SLA constants.

## 26.7. Client payments — RU

First end-client PaymentProvider: **YooKassa** unless the first Business cannot onboard/use it.

Preferred flow:
```text
PaymentRequest
→ hosted YooKassa checkout/payment URL
→ Client card/SBP/etc. at provider
→ webhook / reconciliation
→ PaymentTransaction
```

The merchant connection belongs to the Business; Client money is paid to the Business rather than passing through the SaaS. PAN/CVC never enters the platform. Webhook/idempotency semantics remain Stage 13/18.

## 26.8. Fiscalization

Russian launch adds a separate compliance layer:
- `BusinessLegalProfile`;
- `FiscalizationProfile`;
- `FiscalReceipt`;
- `FiscalizationService`;
- `FiscalizationAdapter`.

`PaymentTransaction` answers whether money movement was confirmed. `FiscalReceipt` answers whether the required fiscal/tax receipt process was completed. They are separate state machines/authorities.

For a controlled first NPD/self-employed Pilot, an explicit `MANUAL_OWNER` receipt obligation may be allowed if confirmed legally/operationally; it must appear in Action Center and cannot disappear silently. Commercial scaling should automate the applicable fiscalization path through an appropriate authorized provider/integration. IP/legal-entity profiles may use different fiscalization strategies without changing PaymentService.

Business readiness adds `FISCALIZATION_READY`. Exact legal/tax workflow is confirmed for the actual first Business before accepting live payments.

## 26.9. First Business selection

Preferred Pilot partner:
- small/cooperative Tattoo Business;
- one main provider;
- real Telegram client traffic;
- formalizable schedule/deposit/rules;
- sufficient portfolio/history;
- known legal/tax status;
- willing to give frequent calibration feedback and delegate ordinary conversations.

No production config remains oral/implicit: first `BusinessConfigurationRelease` is owner-approved.

## 26.10. RU provider/data inventory

Before live data, maintain a provider/subprocessor/data-flow inventory covering infrastructure, Telegram, AI gateway/upstreams, payment provider and fiscalization provider. Telegram remains an external trust boundary even if our data plane is RU-local.

AI context is minimum-necessary. Provider-side uploaded media/files are temporary processing refs, never canonical storage, and follow deletion/retention policy where supported.

## 26.11. Pilot activation phases

Production activation is capability-phased:
1. internal Test Workspace;
2. real Telegram inbound + manual Owner replies, AI auto-send OFF;
3. AI shadow/draft/read-only;
4. safe AI AUTO for FAQ/intake/portfolio/configured facts;
5. configured pricing + scheduling/Hold;
6. real RUB payment;
7. reminders/follow-ups/automations.

Autonomy expands by capability rather than arbitrary traffic percentage. Each phase requires the relevant Golden Journeys/Evals/operations to be green.

## 26.12. Pilot operations / pause / exit

Calibration continues for roughly 20–50 meaningful real RU Tattoo conversations. Metrics additionally include payment method/conversion, payment reconciliation, fiscalization pending/failed and RU AI/infrastructure cost.

Any critical tenant/money/double-booking/takeover/high-risk/fiscalization-control failure pauses the affected automation capability. Pausing AI preserves durable inbound, manual Owner operation, calendar and reconciliation.

Pilot offboarding is explicit: pause AI, disconnect channel safely, reconcile payments/holds, export/delete as required, revoke provider credentials and apply retention/privacy workflows.

---


# 27. Expansion — LOCKED

## 27.1. Expansion principle

Expansion is evidence-driven. Prefer changing one major axis at a time:
- tenants/businesses;
- organizational complexity/resources;
- industries;
- channels;
- AI/media capabilities;
- markets/regions.

Do not simultaneously add a new industry, new channel, new region and major AI capability without a compelling dependency.

## 27.2. Recommended sequence

```text
First real RU Tattoo
→ repeatable RU Tattoo (several independent Businesses)
→ Commercial RU Tattoo SaaS
→ small Tattoo studios / multi-provider
→ second RU IndustryPack
→ additional RU Channels
→ Voice / advanced media / image generation
→ multi-industry RU SaaS
→ first foreign MarketProfile
→ second regional Cell
→ true multi-region platform
```

The 3–5-Business range is a useful repeatability calibration target, not an architectural threshold.

## 27.3. Repeatability before breadth

Second/third Tattoo Businesses must run on the same application/IndustryPack with differences expressed through Service/Pricing/Scheduling/Rules/Knowledge/Workflow/Autonomy revisions. Code forks or `if workspace_id` behavior are prohibited.

If each new Business requires engineering intervention, improve onboarding/configuration before adding another industry.

## 27.4. Commercial RU Tattoo

After Pilot learning, complete repeatable onboarding, SaaS billing, essential Owner self-service, support process, automated/reliable fiscalization where applicable and measured unit economics.

## 27.5. Multi-provider Tattoo studios

First organizational expansion uses existing `BusinessMember`/`Resource` architecture. Provider eligibility is deterministic-first (service/location/rules/schedule), with AI/portfolio relevance only as a secondary signal. Final allocation remains deterministic.

## 27.6. Second industry

Recommended second vertical: a simpler `SLOT_BASED` beauty service (e.g. manicure/brows/lashes) to test a different WorkflowArchetype from Tattoo's consultative flow.

Industry-specific fields stay in IndustryPack/IntakeSchema, not universal table columns. Every new IndustryPack requires a real design partner, onboarding/default workflow/intake/risk/pricing rules, Golden Journeys and EvalSuite.

## 27.7. Additional RU channels

Telegram remains first supported channel. MAX and VK are primary RU expansion candidates; actual priority is driven by measured client inquiry share, not preference.

Each integration implements `ChannelAdapter` + explicit `ChannelCapabilities`; no channel-specific logic leaks into Conversation/Workflow core. Cross-channel ClientIdentity merge requires evidence/confirmation, never name matching alone.

Current MAX official API supports HTTPS/Webhook/messages/media/callbacks; it is technically compatible with the adapter architecture, but production capability/registration rules are reverified before implementation.

## 27.8. Voice / image generation / rich media

Voice is the recommended first post-MVP media capability where production demand confirms it. Transcription remains provider-abstracted and can use an approved RU-local model.

AI image generation is post-Pilot. Generated assets have explicit lineage and are never PortfolioItem `MY_WORK`. Text-only design generation may use `CONTRACTED_EXTERNAL` premium models more readily than raw Client image processing because data-residency/privacy exposure differs. Image-to-image/Vision external routing requires stricter DataResidencyPolicy checks.

## 27.9. AI provider/model lifecycle

Provider/model maturity states:
```text
EVAL_ONLY → CANARY → APPROVED → DEPRECATED → DISABLED
```

Aggregator catalog additions/removals never silently change production. Model replacement requires Eval/canary/approval. Multi-provider routing is deterministic policy; if no approved compatible fallback exists, degrade to queue/Human instead of random weaker model.

Autonomy expands action-by-action with rules/tests/evals/rollback/monitoring, not through a global 100% autonomy switch.

## 27.10. Industry/channel maturity

IndustryPack and Channel integrations use maturity states such as:
```text
EXPERIMENTAL → PILOT → SUPPORTED → DEPRECATED → REMOVED
```

Existing Workspaces remain pinned to compatible revisions; releases do not silently change active engagements.

## 27.11. Continuous learning across tenants

Raw Business knowledge/rules never propagate between tenants. Workspace corrections may produce sanitized/general platform patterns and IndustryPack candidates only through review + Evals + versioned release.

## 27.12. First foreign market

Expansion abroad is one market at a time. Each market introduces:
- `MarketProfile`;
- `DataResidencyPolicy`;
- `RegionalProviderBundle`;
- payment/fiscalization adapters;
- language/localization;
- market-specific privacy/compliance review;
- market EvalSuite.

A Workspace has one authoritative Home Data Region. Routing is server-side through Workspace placement metadata.

## 27.13. Regional Cells / true multi-region

A second market/data plane can become a new regional Cell:
```text
Global/Minimal Control Plane
  → Workspace placement
  → RU Cell
  → Future foreign Cell
```

Customer conversations/files/business transactions remain in the Workspace home cell. No cross-region synchronous business transaction or live SQL join across regional OLTP databases. Global analytics consumes minimized/aggregated projections.

Workspace region migration is a controlled pause/copy/verify/placement-switch operation, not an ordinary runtime toggle. Multi-region does not imply active-active writes.

## 27.14. Expansion gate

Every new Industry/Channel/Market/AI capability must pass:
- real product/design-partner demand;
- existing extension point or explicit ADR for core change;
- security/privacy/data-residency review;
- reliability/retry/recovery definition;
- operations/observability/support;
- tests/contracts;
- AI Evals when behavior changes;
- unit economics/cost understanding;
- kill/rollback path.

Architecture may evolve when production evidence reveals a genuinely universal missing concept, but not for speculative future flexibility.

---

# 28. Cross-cutting principles from stages 0–27 — LOCKED

## 28.1. Provenance
Важные AI-inferred facts/decisions должны иметь evidence/source, где это практически возможно.

## 28.2. Human authority
Владелец остаётся финальным авторитетом для критических бизнес-правил, исключений и high-risk actions.

## 28.3. Progressive autonomy
Action policy может быть AUTO / REQUIRE_CONFIRMATION / ESCALATE / DISABLED. Формальная модель — Stage 8.

## 28.4. Workflow-driven design
Нет одного обязательного pipeline для всех профессий.

Примеры:
```text
Manicure: Request → Appointment → Payment after service
Tattoo: Request → Assessment → Quote → Deposit → Sessions/Appointments
Furniture: Request → Assessment → Design → Quote → Deposit → Production → Delivery
```

Stage 9 формализует Workflow Definition.

---

# 29. Mutable external assumptions verified at baseline

Provider assumptions are mutable, not domain contracts. Recheck before implementation/cutover.

- [Telegram Business](https://core.telegram.org/api/business) and [BusinessBotRights](https://core.telegram.org/constructor/businessBotRights): connected bot capabilities/reply window; validate first master's actual connection in M2.
- [YooKassa incoming notifications](https://yookassa.ru/developers/using-api/webhooks): provider-specific authenticity/status/IP checks, not assumed universal signature.
- AI public documentation/shortlist evidence is recorded in §7.22. Catalog access does not establish measured speed, comparative total cost or production processing eligibility.
- Yandex managed PostgreSQL/PITR/pgvector, Object Storage, Lockbox and telemetry capabilities must be verified against selected topology with restore evidence; no SKU procurement performed.
- MAX remains future channel; current registration/capabilities are rechecked only before implementation.

`RegionalProviderBundle`, AIProviderBranch and adapters isolate external bindings. A branch switch never overrides HomeDataRegion or approval requirements.

# 30. Explicitly deferred

v0.28 does not invent the following values:
- exact master identity/legal/tax/fiscal profile, fixed deposit amount, chosen price rule/formula and cancellation/refund policy (OPEN-076/079);
- master-labelled actual duration cases, approved rule coefficients/buffers/session limits and calibration thresholds (OPEN-080/081);
- production model/embedding/API IDs, measured aggregator comparison, eligible upstream routes and contract evidence (OPEN-074/075/085);
- exact stack/tooling/tickets/calendar estimates (OPEN-067–069);
- exact infrastructure SKU/zone/retention, measured RPO/RTO, operational SLO/support/alert destinations (OPEN-070–073);
- tested deletion journal/fencing/provider-replay recovery mechanics (OPEN-084);
- exact per-tool field contracts before corresponding M4–M8 feature (OPEN-007);
- actual master import formats (OPEN-013), owner wait timing and optional HUMAN notification exceptions (OPEN-082/083);
- advanced pricing DSL, full multi-session automation, extra customer channels/media, external calendars and foreign-market choice beyond accepted horizons.

Russia/Tattoo, provider candidates, domain boundaries, pricing/payment modes, dependency order and runbook principles are already decided. Implementation evidence and owner-specific values remain OPEN, not a reason to reopen accepted architecture. See `04_OPEN_QUESTIONS.md`.



---

## Исходный файл: 02_ARCHITECTURE_DECISIONS.md

# AI Service Manager — Architecture Decision Records

**Baseline:** v0.28  
**Дата:** 2026-09-09
**Статус:** accepted decisions from stages 0–27 + v0.28 audit/user revisions; ADR status records supersession explicitly

---

## ADR-001 — SaaS вместо отдельного AI на каждого мастера
**Status:** Accepted

**Decision:** один общий AI/application core. Персонализация через structured configuration, Business Rules, Knowledge/RAG, CommunicationProfile, Approved Examples, Portfolio и Industry Workflow.

**Rejected:** отдельная fine-tuned model per master как default.

**Consequence:** fine-tuning остаётся возможной оптимизацией, а не фундаментом.

---

## ADR-002 — Workspace является tenant boundary
**Status:** Accepted

**Decision:** использовать `Workspace`/`workspace_id` как единственную tenant boundary. Отдельный `tenant_id` не вводится.

---

## ADR-003 — Workspace и Business различаются
**Status:** Accepted

**Decision:** Workspace отвечает за security/tenant boundary; Business — за business context. В MVP допустимо 1 Workspace = 1 Business.

---

## ADR-004 — Shared PostgreSQL + workspace_id
**Status:** Accepted

**Decision:** shared database + shared application schema + workspace_id.

**Rejected:** database-per-tenant, schema-per-tenant.

---

## ADR-005 — Defense in depth для tenant isolation
**Status:** Accepted

**Decision:** isolation обеспечивают одновременно authorization, WorkspaceContext, repositories, RLS, tenant-safe FK, storage/cache/RAG namespaces и AI tool boundaries.

---

## ADR-006 — Runtime DB role не обходит RLS
**Status:** Accepted

**Decision:** runtime DB user не superuser, не BYPASSRLS и не owner tenant tables. Tenant context устанавливается transaction-locally.

---

## ADR-007 — Client не глобален между Workspace
**Status:** Accepted

**Decision:** одинаковый внешний пользователь в разных Workspace создаёт независимые Client-профили.

---

## ADR-008 — PostgreSQL является source of truth
**Status:** Accepted

**Decision:** критическое бизнес-состояние хранится в PostgreSQL. Redis/embeddings/caches восстановимы и не являются единственной копией.

---

## ADR-009 — Object Storage для binary assets
**Status:** Accepted

**Decision:** binary media хранится в private Object Storage; PostgreSQL хранит FileObject metadata/ownership.

---

## ADR-010 — UUID для основных ID
**Status:** Accepted

**Decision:** основные internal IDs — UUID; на PostgreSQL 18 предпочтителен UUIDv7. UUID не заменяет authorization.

---

## ADR-011 — Normalized Core + Flexible Edge
**Status:** Accepted

**Decision:** core business fields нормализованы; отраслевые параметры — schema-driven JSONB/config.

**Rejected:** everything JSONB; глобальные колонки под каждую профессию.

---

## ADR-012 — Service configuration имеет revisions
**Status:** Accepted

**Decision:** Service стабилен, изменяемая конфигурация публикуется как immutable ServiceRevision. ServiceRequest ссылается на конкретную revision.

---

## ADR-013 — Conversation и ServiceRequest разделены
**Status:** Accepted

**Decision:** Conversation = общение; ServiceRequest = структурированное желание клиента. Один Conversation может иметь несколько requests.

---

## ADR-014 — Assessment, Quote и Order разделены
**Status:** Accepted

**Decision:** Assessment = техническая оценка; Quote = коммерческие условия; ServiceOrder = согласованный заказ.

---

## ADR-015 — ServiceSession отдельно от Appointment
**Status:** Accepted

**Decision:** Session — логическая часть работы; Appointment — конкретное время. Session может быть unscheduled.

---

## ADR-016 — ReservationHold отдельно от Appointment
**Status:** Accepted

**Decision:** временное удержание слота и confirmed календарная запись — разные сущности.

---

## ADR-017 — PaymentRequest отдельно от PaymentTransaction
**Status:** Accepted

**Decision:** требование оплатить и конкретная попытка/операция провайдера разделены.

---

## ADR-018 — Нет единого глобального process status
**Status:** Accepted

**Decision:** каждая бизнесовая сущность имеет собственную state machine.

**Rejected:** один status `REQUEST → PAYMENT → BOOKED → COMPLETED`.

---

## ADR-019 — Telegram скрыт за Channel Adapter
**Status:** Accepted

**Decision:** Conversation Engine работает только с normalized events; Telegram/VK/MAX/Web реализуются адаптерами.

---

## ADR-020 — Telegram Profile Automation как основной MVP transport
**Status:** Accepted

**Decision:** основной Telegram mode — connected business bot/profile automation. Standalone bot — alternative/fallback.

**Consequence:** ChannelCapabilities обязателен из-за provider restrictions.

---

## ADR-021 — Только официальные channel APIs
**Status:** Accepted

**Decision:** не строить продукт на userbot/эмуляции пользовательской сессии/обходе лимитов.

---

## ADR-022 — Message и ConversationTurn разделены
**Status:** Accepted

**Decision:** несколько быстрых Messages могут агрегироваться в один semantic Turn.

---

## ADR-023 — Structured state выше model memory
**Status:** Accepted

**Decision:** критические факты хранятся в structured entities. Summary и model memory — вспомогательные representations.

---

## ADR-024 — AI output проходит validation и relevance checks
**Status:** Accepted

**Decision:** extraction создаёт candidate facts с confidence/evidence; до business action применяются validation/policies. Delayed result проверяет актуальность перед отправкой.

---

## ADR-025 — Per-conversation serialization
**Status:** Accepted

**Decision:** один Conversation обрабатывается последовательно, разные Conversations — параллельно. Lock mechanism deferred.

---

## ADR-026 — Human Takeover фундаментален
**Status:** Accepted

**Decision:** MVP modes — AI/HUMAN. Вмешательство человека отменяет/устаревает pending AI reply. Escalation отделена от full takeover.

---

## ADR-027 — Visual Design Service отдельно от Conversation Engine
**Status:** Accepted

**Decision:** Conversation Engine решает, нужен ли visual operation; отдельный сервис генерирует/редактирует asset.

---

## ADR-028 — Portfolio-first visual policy
**Status:** Accepted

**Decision:** сначала искать реальную релевантную работу бизнеса; генерация — при необходимости.

---

## ADR-029 — GeneratedAsset имеет provenance и не является Portfolio
**Status:** Accepted

**Decision:** AI-generated asset хранится отдельно, с purpose/source lineage. Нельзя выдавать его за реальную работу или автоматически считать финальным technical artifact.

---

## ADR-030 — Business Rules и Knowledge различаются
**Status:** Accepted

**Decision:** Rules определяют действие/ограничение; Knowledge используется для консультации/объяснения. RAG не заменяет authoritative business state.

---

## ADR-031 — Raw chats являются сырьём, а не истиной
**Status:** Accepted

**Decision:** historical conversations используются для extraction/patterns/cases/style. Критические найденные правила требуют owner confirmation.

---

## ADR-032 — Knowledge authority и provenance обязательны
**Status:** Accepted

**Decision:** knowledge имеет source/authority/revision/effective dates. Ranking учитывает не только similarity.

---

## ADR-033 — PostgreSQL + pgvector для RAG MVP
**Status:** Accepted

**Decision:** не вводить отдельную vector DB без измеренной необходимости. Hybrid retrieval: tenant/structured filters + keyword/full-text + vector + reranking.

---

## ADR-034 — Retrieval scopes разделены
**Status:** Accepted

**Decision:** Business Knowledge, Client History, Portfolio и Historical Cases имеют отдельные scopes/APIs.

---

## ADR-035 — Communication style = profile + examples
**Status:** Accepted

**Decision:** использовать CommunicationProfile + ApprovedConversationExamples + current conversation вместо всей истории в prompt.

---

## ADR-036 — KnowledgeBuild как publish boundary
**Status:** Accepted

**Decision:** новый набор знаний валидируется до публикации. Предыдущий published build остаётся активным при ошибке нового.

---

## ADR-037 — Continuous learning только предлагает критические изменения
**Status:** Accepted

**Decision:** Learning Analyzer создаёт suggestions/candidates; money/scheduling/eligibility/legal-health-sensitive changes требуют подтверждения.

---

## ADR-038 — Workflow не глобально линейный
**Status:** Accepted after audit

**Decision:** domain entities универсальны, но последовательность задаётся Workflow Definition конкретной услуги/industry module.

**Rejected:** единый mandatory pipeline для всех профессий.

---

## ADR-039 — Progressive autonomy
**Status:** Accepted after audit

**Decision:** действия должны поддерживать policy levels типа AUTO / REQUIRE_CONFIRMATION / ESCALATE / DISABLED. Full autopilot — цель, не обязательный стартовый режим.

---

## ADR-040 — Business Onboarding — отдельная подсистема
**Status:** Accepted after audit

**Decision:** onboarding включает import, extraction, conflicts/missing data, adaptive questions, owner review, validation, build и publish.

---

## ADR-041 — SaaS billing отделён от client payments
**Status:** Accepted after audit

**Decision:** `Client → Business Payments` и `Business → Platform Subscription/Usage` проектируются раздельно.

---

## ADR-042 — Security и Reliability cross-cutting
**Status:** Accepted after audit

**Decision:** поздние Security/Reliability stages — аудит/hardening, а не первый момент появления этих требований.

---

## ADR-043 — Models скрыты за ModelGateway
**Status:** Accepted

**Decision:** business code использует logical ModelProfile; provider/model IDs разрешаются через ModelGateway/ModelProfileConfig.

**Consequences:** model upgrades не требуют изменения Conversation/Pricing/Scheduling code.

---

## ADR-044 — Deterministic model routing
**Status:** Accepted

**Decision:** ModelRouter в основном использует task type, modality, risk и workload class, а не отдельную LLM для выбора модели.

**Consequences:** меньше latency/cost и проще воспроизводимость.

---

## ADR-045 — Initial GPT-5.6 tiering
**Status:** REVISED — superseded by ADR-238 and ADR-259–261; historical mapping below is not active routing

**Decision:** Terra = default conversation, Luna = cheap/background/bulk, Sol = rare complex reasoning. Reasoning effort выбирается отдельно.

**Consequences:** mapping может меняться после eval без изменения product contract.

---

## ADR-046 — Provider state не является canonical memory
**Status:** Accepted

**Decision:** canonical conversation/context живёт в PostgreSQL/ConversationState/ContextBuilder. Provider previous-response/persisted-reasoning state — optional optimization.

---

## ADR-047 — Structured Outputs для application-consumed AI data
**Status:** Accepted

**Decision:** данные, которые читает код, передаются через versioned schema/Structured Outputs; business actions не парсятся из prose.

---

## ADR-048 — Prompt и schema versioning
**Status:** Accepted

**Decision:** platform prompts, schemas и model profiles версионируются. Business personalization хранится отдельно и не превращается в произвольный tenant system prompt.

---

## ADR-049 — ContextBuilder контролирует budget
**Status:** Accepted

**Decision:** context формируется из structured state + rules + RAG + portfolio + summary + recent turns в рамках profile-specific token budget. Большое provider context window не отменяет selection/compression.

---

## ADR-050 — Не делать обязательный multi-call pipeline на каждый Turn
**Status:** Accepted

**Decision:** default interactive flow стремится к одному основному reasoning pass; дополнительные classifier/extractor calls применяются только при измеренной пользе.

---

## ADR-051 — Embeddings являются versioned projections
**Status:** Accepted

**Decision:** embedding хранится отдельно от canonical KnowledgeChunk/PortfolioItem representation через EmbeddingProfile/version.

**Consequences:** возможен blue-green reindexing и смена embedding model без изменения canonical knowledge.

---

## ADR-052 — AIRun отделён от AIProviderCall
**Status:** Accepted

**Decision:** AIRun описывает логическую AI-задачу; один run может иметь несколько provider calls/tool continuations.

---

## ADR-053 — Chain-of-thought не является audit mechanism
**Status:** Accepted

**Decision:** сохраняются structured decisions, evidence, rules, tools, results, model/config metadata и usage; полный внутренний reasoning не требуется для объяснимости.

---

## ADR-054 — Provider built-in tools disabled by default for customer agent
**Status:** Accepted

**Decision:** business actions идут через собственную platform tool layer. Web/computer/arbitrary external tools не выдаются customer-facing agent без явной задачи/policy.

---

## ADR-055 — Model changes проходят eval/canary
**Status:** Accepted

**Decision:** новая модель не становится production default автоматически. Требуются representative evals и контролируемый rollout.

---

## ADR-056 — Один ConversationAgent в customer-facing flow
**Status:** Accepted

**Decision:** основной клиентский процесс использует один ConversationAgent. Pricing/Scheduling/Payments/Knowledge/Visual являются application services/tools. Отдельные Onboarding/Learning AI workflows допустимы для другого lifecycle.

---

## ADR-057 — Узкие typed tools вместо arbitrary capabilities
**Status:** Accepted

**Decision:** Agent не получает arbitrary SQL, generic HTTP, code execution или generic database mutation. Tools узкие, versioned, strict-schema и вызывают application services.

---

## ADR-058 — Dynamic ToolSet + independent PolicyEngine
**Status:** Accepted

**Decision:** `ToolSetResolver` ограничивает видимые tools текущим workflow/context. Даже видимый tool перед исполнением проходит server-side `PolicyEngine`.

---

## ADR-059 — ActionPolicy определяет автономность
**Status:** Accepted

**Decision:** autonomy modes: `AUTO`, `REQUIRE_CONFIRMATION`, `ESCALATE`, `DISABLED`. Policy hierarchy: Platform Hard → Industry Minimum → Workspace → Service → Dynamic Context.

---

## ADR-060 — Owner approval сохраняет frozen action
**Status:** Accepted

**Decision:** privileged command создаёт ApprovalRequest с фиксированным payload/state version. После approval state/preconditions/idempotency повторно проверяются; AI не формирует side effect заново.

---

## ADR-061 — Evidence важнее model confidence
**Status:** Accepted

**Decision:** self-reported AI confidence не является authorization mechanism. Критические actions требуют определённых evidence classes и deterministic preconditions.

---

## ADR-062 — Agent loop bounded
**Status:** Accepted

**Decision:** Agent имеет лимиты steps/tool calls/state mutations/deadline/cost и явные stop outcomes. Technical retries контролирует runtime.

---

## ADR-063 — Exact system events bypass LLM
**Status:** Accepted

**Decision:** payment webhooks, expirations, structured user actions и другие deterministic events обрабатываются кодом. LLM вызывается только когда нужна семантика/язык.

---

## ADR-064 — AIToolCall и AuditEvent различаются
**Status:** Accepted

**Decision:** ToolTrace фиксирует intention/tool execution path AI; AuditEvent фиксирует реально произошедшее business action/mutation.

---

## ADR-065 — Universal Core + composable industry configuration
**Status:** Accepted

**Decision:** не создавать отдельный backend per profession. Использовать workflow archetypes, capabilities, Industry Packs и business/service overrides.

---

## ADR-066 — Workflow orchestration отделена от domain truth
**Status:** Accepted

**Decision:** `WorkflowDefinition/Revision/Instance/StepInstance` определяют процесс, но payment/calendar/order/request facts остаются в соответствующих domain entities.

---

## ADR-067 — Workflow completion детерминирован
**Status:** Accepted

**Decision:** semantic work может выполнять AI, но completion workflow step определяется проверяемым domain condition, а не свободным model judgment.

---

## ADR-068 — Industry Pack является versioned template
**Status:** Accepted

**Decision:** IndustryPack хранит defaults/templates/terminology/workflows, но не конкретные business facts. Новая версия Pack не меняет существующий production автоматически.

---

## ADR-069 — Profession != Workflow
**Status:** Accepted

**Decision:** profession/industry taxonomy используется для defaults, onboarding, terminology, knowledge и analytics. Реальный Service workflow определяется capabilities + WorkflowRevision.

---

## ADR-070 — Generic business может работать без Industry Pack
**Status:** Accepted

**Decision:** отсутствие готового IndustryPack не требует нового backend; generic onboarding может собрать custom capabilities/workflow/configuration.

---

## ADR-071 — Onboarding является отдельной подсистемой
**Status:** Accepted

**Decision:** onboarding включает source import, extraction, conflicts, adaptive questions, validation, simulation, approval и publish; это не статическая форма настроек.

---

## ADR-072 — OnboardingAgent работает только с draft/candidates
**Status:** Accepted

**Decision:** OnboardingAgent не публикует критические production settings напрямую. Owner approval + deterministic validation являются publish boundary.

---

## ADR-073 — Adaptive questionnaire после extraction
**Status:** Accepted

**Decision:** сначала анализируются доступные материалы, затем задаются только missing/conflicting/confirmation questions с dependency-aware priority.

---

## ADR-074 — Readiness через gates, не процент
**Status:** Accepted

**Decision:** launch readiness определяется blocking gates per Service, а не общим onboarding completion score.

---

## ADR-075 — Simulation перед publish
**Status:** Accepted

**Decision:** до production configuration проходит historical replay/synthetic scenarios/service smoke checks/owner preview в зависимости от доступных данных.

---

## ADR-076 — BusinessConfigurationRelease как atomic publish manifest
**Status:** Accepted

**Decision:** опубликованная конфигурация фиксируется immutable manifest'ом связанных revisions/builds. Publication атомарна; существующие pinned requests/orders автоматически не мигрируют.

---

## ADR-077 — Первые onboarding проходят concierge
**Status:** Accepted

**Decision:** первые реальные клиенты проходят manual/semi-assisted onboarding. Наблюдаемый процесс становится спецификацией для последующей автоматизации.

---

## ADR-078 — LLM не является источником authoritative price
**Status:** Accepted

PricingEngine/Owner decision формирует сумму. AI может поставлять structured pricing factors, но не создаёт деньги из собственного предположения.

## ADR-079 — PriceCalculation отделён от Quote
**Status:** Accepted

PriceCalculation — immutable внутренний результат; Quote — customer-facing commercial object/history.

## ADR-080 — Pricing configuration versioned
**Status:** Accepted

ServiceRevision связывается с immutable PricingRevision; изменение production pricing создаёт новую revision/release.

## ADR-081 — Quote не создаётся из произвольной AI-суммы
**Status:** Accepted

ConversationAgent создаёт Quote только из valid PriceCalculation либо structured Owner-approved decision.

## ADR-082 — Availability вычисляется, а не хранится как free slots
**Status:** Accepted

Free slots являются projection над working rules, blocks, allocations, holds, appointments и SchedulingPolicy.

## ADR-083 — ResourceAllocation предотвращает double booking
**Status:** Accepted

Hold/Appointment создают exclusive allocations; overlap должен предотвращаться на database level.

## ADR-084 — Hold → Appointment conversion атомарен
**Status:** Accepted

Conversion и required resource state changes выполняются атомарно.

## ADR-085 — Scheduling config и operational calendar разделены
**Status:** Accepted

SchedulingPolicyRevision versioned; ежедневные overrides/blocks/appointments меняются operationally без ConfigurationRelease.

## ADR-086 — Reschedule сохраняет историю
**Status:** Accepted

Старый Appointment отменяется, новый создаётся отдельно; старый слот не освобождается до безопасного захвата нового.

## ADR-087 — PaymentRequest / Session / Transaction разделены
**Status:** Accepted

Обязательство, checkout session и provider-confirmed movement — разные сущности.

## ADR-088 — Client money не хранится платформой в MVP
**Status:** Accepted

Client платит через merchant account Business. Платформа не является escrow/wallet/marketplace settlement layer.

## ADR-089 — Provider state является authoritative payment evidence
**Status:** Accepted

Verified webhook/API подтверждает online payment. Client claim, screenshot и browser redirect — нет.

## ADR-090 — Refund является отдельным movement
**Status:** Accepted

Refund не переписывает исторический successful PaymentTransaction; имеет отдельный lifecycle/audit.

## ADR-091 — Late payment сохраняется независимо от workflow state
**Status:** Accepted

Successful provider-confirmed transaction признаётся даже после expiry/cancel; booking требует fresh scheduling validation.

## ADR-092 — Payment provider скрыт за adapter
**Status:** Accepted

PaymentService работает через PaymentProviderAdapter/Connection; webhook не создаёт Appointment напрямую.

## ADR-093 — Automation и Notification разделены
**Status:** Accepted

Automation определяет when/why; NotificationIntent/Router определяют recipient/delivery route.

## ADR-094 — Relevance guard перед автоматической отправкой
**Status:** Accepted

Любая due automation и AI-generated follow-up повторно проверяет current state до user-visible action.

## ADR-095 — Persistent automation runtime
**Status:** Accepted

AutomationInstance persistent, переживает restart и имеет explicit late-execution policy.

## ADR-096 — NotificationIntent отделён от DeliveryAttempt
**Status:** Accepted

Одно business intent может иметь несколько последовательных route attempts.

## ADR-097 — Transactional notifications template-first
**Status:** Accepted

Critical facts передаются structured; MVP transactional content template/hybrid, AI свободнее используется для semantic follow-up.

## ADR-098 — Delivery Horizon входит в архитектурную документацию
**Status:** REVISED — clarified by ADR-270; legacy MVP horizon below requires Pilot/Commercial distinction

Capabilities классифицируются как MVP / CORE_POST_MVP / FUTURE_OPTIONAL независимо от LOCKED/OPEN/DEFERRED.

---

## ADR-099 — Workspace является единицей SaaS billing
**Status:** Accepted

**Decision:** подписка, plan revision, entitlements, usage и billing account принадлежат Workspace, а не глобальному UserAccount или Business.

---

## ADR-100 — SaaS billing отделён от Client→Business payments
**Status:** Accepted

**Decision:** Platform subscription billing и client payments являются разными bounded contexts, даже если используют одного provider.

---

## ADR-101 — Карты владельцев бизнеса токенизируются у billing provider
**Status:** Accepted

**Decision:** provider-hosted checkout/billing portal предпочтительны; PAN/CVC не хранятся. Платформа хранит provider payment-method reference и безопасные display metadata.

---

## ADR-102 — SaaS plans реализуются через versioned Entitlements
**Status:** Accepted

**Decision:** `SaaSPlanRevision + PlanEntitlement + EntitlementService` заменяют hardcoded проверки названия тарифа. Entitlement не является security permission.

---

## ADR-103 — Billing state отделён от Workspace service mode
**Status:** Accepted

**Decision:** TRIALING/ACTIVE/PAST_DUE/CANCELED не равны product access напрямую. Отдельный service mode `NORMAL/GRACE/LIMITED/SUSPENDED` задаёт graceful degradation.

---

## ADR-104 — UsageEvent является immutable usage ledger
**Status:** Accepted

**Decision:** observed usage записывается immutable/idempotent events, а агрегаты rebuildable. Raw provider usage/cost измеряется даже если не является billable unit.

---

## ADR-105 — Hard quota дорогих операций использует reservation
**Status:** Accepted

**Decision:** image/bulk expensive operations используют persistent QuotaReservation; interactive text AI имеет continuity-oriented soft budget в MVP.

---

## ADR-106 — Billing provider не находится на critical path Client runtime
**Status:** Accepted

**Decision:** обычные conversations используют локальный canonical subscription/entitlement state; outage billing provider не должен отключать клиентов бизнеса.

---

## ADR-107 — Business Console и Platform Operations разделены
**Status:** Accepted

**Decision:** это разные application surfaces/security contexts поверх одних domain services.

---

## ADR-108 — Business Console является exception-first
**Status:** Accepted

**Decision:** Action Center/Inbox/Calendar/Approvals ориентированы на действия, требующие человека, а не на generic CRM/table admin.

---

## ADR-109 — UI не имеет обхода domain services
**Status:** Accepted

**Decision:** Business Console, AI Agent и Platform Support выполняют mutations через одни application/domain services; прямой DB/status patch bypass запрещён.

---

## ADR-110 — Owner видит Decision Summary, но не chain-of-thought
**Status:** Accepted

**Decision:** UI показывает reason/evidence/rules/tool outcome, но не hidden reasoning/full chain-of-thought.

---

## ADR-111 — SupportAccessGrant вместо permanent tenant membership/impersonation
**Status:** Accepted

**Decision:** platform support access scope-limited, TTL-limited, reasoned and audited; не создаёт WorkspaceMembership и не меняет actor identity на владельца.

---

## ADR-112 — MVP Business Console = responsive web
**Status:** Accepted

**Decision:** native iOS/Android не prerequisite первого production; responsive web покрывает Inbox/Action Center/Calendar/Approvals и основные настройки.

---

## ADR-113 — LLM и Client content считаются untrusted
**Status:** Accepted

**Decision:** prompt compliance не является security boundary. Messages/files/images/RAG/external content могут содержать injection; ToolGateway/PolicyEngine/RLS обеспечивают enforcement.

---

## ADR-114 — Common data classification + minimum necessary AI context
**Status:** Accepted

**Decision:** данные классифицируются по sensitivity; `AIDataPolicy` разрешает AI только минимально необходимый набор data classes/context для конкретной задачи.

---

## ADR-115 — Customer Object Storage private + signed access
**Status:** Accepted

**Decision:** клиентские files private by default; доступ только после authorization через short-lived signed URL. Uploads считаются hostile input.

---

## ADR-116 — Secrets и environments изолированы
**Status:** Accepted

**Decision:** secrets хранятся через Secret Manager/references; Dev/Staging/Production разделены. Production DB/files не копируются на developer machines как обычный workflow.

---

## ADR-117 — Secure sessions и mandatory Platform Ops MFA
**Status:** Accepted

**Decision:** browser auth предпочитает secure server-managed sessions; Platform Ops MFA обязательна до production; sensitive actions поддерживают re-auth/revocation.

---

## ADR-118 — Privacy retention/deletion охватывает derived data
**Status:** Accepted

**Decision:** RetentionPolicy/PrivacyRequest/Delete flow удаляет или анонимизирует canonical + files + indexes + embeddings + debug-derived data; backups expire/reapply tombstones according to policy.

---

## ADR-119 — Raw AI prompts/PII не являются default telemetry
**Status:** Accepted

**Decision:** обычные logs/AIRun telemetry минимизируют PII; full prompt/debug capture только explicit, restricted, short-lived and audited.

---

## ADR-120 — Support access и break-glass являются отдельными security paths
**Status:** Accepted

**Decision:** ordinary support grant read-only/minimal scope; emergency break-glass требует elevated role, short TTL, reason and special audit.

---

## ADR-121 — At-least-once + idempotency вместо distributed exactly-once
**Status:** Accepted

**Decision:** duplicate delivery ожидается; все critical consumers/commands должны быть idempotent.

---

## ADR-122 — Durable Inbox before acknowledge
**Status:** Accepted

**Decision:** verified external event сначала dedupe/persist/commit в Inbox, только потом provider получает successful acknowledgement.

---

## ADR-123 — Domain mutation + Outbox atomic
**Status:** Accepted

**Decision:** canonical state transition и OutboxEvent записываются в одной short DB transaction; Outbox delivery/consumers допускают повтор.

---

## ADR-124 — Critical side effects use idempotency key + request fingerprint
**Status:** Accepted

**Decision:** same operation retry возвращает prior result; same key with different payload является conflict.

---

## ADR-125 — External HTTP не выполняется внутри long domain transaction
**Status:** Accepted

**Decision:** DB transaction фиксирует intent/domain state, external operation выполняется после commit с recovery/idempotency semantics.

---

## ADR-126 — Optimistic concurrency является canonical stale-state guard
**Status:** Accepted

**Decision:** mutable aggregates используют version/CAS; Redis/distributed locks могут помогать, но не являются единственной correctness guarantee.

---

## ADR-127 — Persistent jobs use lease/reclaim + bounded retry + DLQ
**Status:** Accepted

**Decision:** worker crash recoverable; retryability code-driven; retryable errors используют backoff+jitter; poison/permanent failures переходят в DLQ.

---

## ADR-128 — Ambiguous external result имеет состояние UNKNOWN
**Status:** Accepted

**Decision:** timeout не автоматически FAILED. Blind retry side effect запрещён без provider idempotency/reconciliation guarantee.

---

## ADR-129 — Successful AI tool side effects are reused after AI failure
**Status:** Accepted

**Decision:** AIRun/ToolTrace persistence предотвращает повторный Hold/refund/other command при retry model continuation.

---

## ADR-130 — PostgreSQL остаётся hard dependency canonical mutable runtime
**Status:** Accepted

**Decision:** Redis/cache/AI/image/analytics могут деградировать без потери canonical state; при невозможности durable DB persistence critical mutations fail closed.

---

## ADR-131 — Workloads logically separated by criticality
**Status:** Accepted

**Decision:** critical/interactive/normal/bulk workloads не должны взаимно вытеснять друг друга; bulk onboarding не блокирует payment/customer paths.

---

## ADR-132 — Deployments use Expand → Migrate → Contract
**Status:** Accepted

**Decision:** schema migrations совместимы с coexistence соседних app/worker versions; normal application rollback не требует DB rollback.

---

## ADR-133 — Backup считается готовым только вместе с tested restore/reconciliation
**Status:** Accepted

**Decision:** DR включает restore canonical data, privacy tombstones, provider reconciliation, pending outbox/jobs, late automation policy и invariant verification.

---

## ADR-134 — Platform Ops replay/retry не bypass'ит normal guards
**Status:** Accepted

**Decision:** operational replay идёт через обычный handler с authorization/idempotency/state validation; raw arbitrary production execution не предоставляется.

---

## ADR-135 — Stateless compute + managed persistent core
**Status:** Accepted

Application nodes are disposable; PostgreSQL/Object Storage hold authoritative persistent state.

## ADR-136 — Modular monolith remains deployment default
**Status:** Accepted

API/Worker/Scheduler may be separate processes of one codebase/image. Logical service boundaries do not imply microservices.

## ADR-137 — Managed PostgreSQL preferred for production
**Status:** Accepted

Production DB is not kept solely on the application VPS; managed backup/PITR/restore workflow is preferred from the first real customer.

## ADR-138 — Original binaries live in private S3-compatible Object Storage
**Status:** Accepted

PostgreSQL stores metadata/object refs; large customer binaries do not use application disk/bytea as authoritative storage.

## ADR-139 — PostgreSQL-backed durable Jobs are MVP default
**Status:** Accepted

Inbox/Outbox/automation/jobs share PostgreSQL durability initially; dedicated broker is introduced only on measured need.

## ADR-140 — Redis/Kafka/Kubernetes are not MVP dependencies
**Status:** Accepted

They are introduced only when evidence shows a concrete need; Redis remains noncanonical.

## ADR-141 — Immutable Docker image is deployment unit
**Status:** Accepted

CI builds versioned artifacts for API/workers/scheduler; normal production deployment is not SSH + git pull.

## ADR-142 — LOCAL/STAGING/PRODUCTION are isolated
**Status:** Accepted

Data/storage/secrets/provider credentials are separated; production customer data is not a normal dev/staging fixture.

## ADR-143 — MVP uses one production region
**Status:** Accepted

Multi-region is deferred until legal/latency/scale demand.

## ADR-144 — Observability, Cost Control and Product Analytics are separate
**Status:** Accepted

Technical telemetry is distinct from audit/security/usage/business analytics.

## ADR-145 — OpenTelemetry-compatible instrumentation
**Status:** Accepted

Metrics/Logs/Traces use vendor-neutral compatible instrumentation; exact managed backend remains replaceable.

## ADR-146 — Telemetry is privacy-minimized
**Status:** Accepted

Raw customer text/secrets/files/payment URLs are not ordinary telemetry; low-cardinality metrics and opaque IDs are preferred.

## ADR-147 — Queue lag and journey latency are first-class SLIs
**Status:** Accepted

Health is measured through user-visible/end-to-end symptoms, not only HTTP/CPU.

## ADR-148 — AI cost attribution per Workspace/feature + provider reconciliation
**Status:** Accepted

Local usage provides business attribution; provider financial costs are reconciled asynchronously.

## ADR-149 — CostGuard is separate from Quota and RateLimit
**Status:** Accepted

CostGuard protects platform economics/optional workloads and cannot lower safety-critical quality.

## ADR-150 — Product analytics derives from domain outcomes
**Status:** Accepted

Bookings, quotes, payments, correct escalation/rejection and workflow milestones matter more than page views/message count.

## ADR-151 — Scaling is metric-driven
**Status:** Accepted

Infrastructure is not introduced because a raw Workspace/user count crossed an arbitrary number.

## ADR-152 — Optimize/vertical/horizontal precede sharding
**Status:** Accepted

Query/index fixes, pooling, vertical scale, replicas/workload isolation and analytics offload precede cells/shards.

## ADR-153 — Noisy-neighbor protection is mandatory
**Status:** Accepted

Per-Workspace concurrency/admission, quota, rate-limit, priority and CostGuard controls protect shared infrastructure.

## ADR-154 — PostgreSQL remains shared core until measured limit
**Status:** Accepted

RLS stays enabled; tenant indexes/pooling/partitioning/read replicas precede database sharding.

## ADR-155 — pgvector remains default RAG infrastructure
**Status:** Accepted

Tune/filter/index pgvector before introducing dedicated vector DB; canonical Knowledge remains PostgreSQL.

## ADR-156 — Workspace is future cell/shard placement unit
**Status:** Accepted

If one data plane reaches its ceiling, preferred large-scale direction is Workspace-based cell architecture.

## ADR-157 — Modular-monolith extraction requires concrete trigger
**Status:** Accepted

Independent scaling/failure/security/infrastructure/team needs justify extraction; class boundaries alone do not.

## ADR-158 — Backpressure is required
**Status:** Accepted

Queues/admission/concurrency prevent unbounded work; bulk/optional workloads yield to money/booking/interactive work.

## ADR-159 — Software tests and AI Evals are separate release systems
**Status:** Accepted

Deterministic domain correctness is tested conventionally; probabilistic model behavior uses versioned evals.

## ADR-160 — Real PostgreSQL required for DB integration tests
**Status:** Accepted

RLS/range/exclusion/locking/pgvector behavior is not covered by SQLite/mock-only testing.

## ADR-161 — Tenant isolation has dedicated executable regression suite
**Status:** Accepted

API/repository/jobs/tools/files/RAG/support access paths are tested cross-tenant.

## ADR-162 — EvalCase defines allowed/forbidden behavior, not exact prose
**Status:** Accepted

AI behavior is judged on facts/tools/state/safety/quality while allowing multiple valid phrasings.

## ADR-163 — Critical AI violations are hard release gates
**Status:** Accepted

Unauthorized mutation/data leak/invented money/payment/availability cannot be averaged away by a high aggregate score.

## ADR-164 — Tool selection/arguments/sequence are evaluated separately
**Status:** Accepted

Correct-looking text is insufficient if Agent uses an invalid or forbidden action path.

## ADR-165 — Prompt-injection evals test actual system outcome
**Status:** Accepted

Success means no unauthorized data/state effect, not merely a polite refusal.

## ADR-166 — Production AI bugs become sanitized regression cases where possible
**Status:** Accepted

Feedback grows the regression suite without automatically retaining raw PII.

## ADR-167 — AI candidates compare against ProductionBaseline
**Status:** Accepted

Model/prompt/tool/schema/knowledge changes are version-pinned and evaluated for safety, quality, cost and latency.

## ADR-168 — New model snapshots are never auto-promoted
**Status:** Accepted

Provider releases become candidates and must pass eval/promotion flow.

## ADR-169 — Continuous learning does not mean live self-modification
**Status:** Accepted

Production corrections/incidents create candidates/evals; prompts/rules/models remain reviewed, versioned and rollbackable.

---

## ADR-170 — Tattoo is the first production vertical
**Status:** Accepted — reaffirmed by user in v0.28

**Decision:** first production Industry Pack is Tattoo; universal core remains industry-agnostic.

---

## ADR-171 — New Tattoo is the primary autonomous MVP flow
**Status:** Accepted

**Decision:** complex cover-up/risky/unsupported cases may intentionally escalate rather than be fully automated.

---

## ADR-172 — First MVP optimizes for one Business/Owner/Resource/Telegram connection
**Status:** Accepted

**Decision:** multi-tenant/multi-resource concepts remain in domain architecture, but first UI/operations do not expose all complexity.

---

## ADR-173 — MVP customer channel is Telegram; media is text + image
**Status:** Accepted

**Decision:** voice/video/customer-document flows and additional channels are excluded from first release.

---

## ADR-174 — Vision and portfolio matching are MVP; image generation is not
**Status:** Accepted

**Decision:** image understanding is essential to Tattoo validation, while generative design is intentionally postponed.

---

## ADR-175 — Concierge onboarding is sufficient for first production Businesses
**Status:** Accepted

**Decision:** historical chats/knowledge/portfolio may be processed with internal assistance; full universal self-service onboarding is not a pilot blocker.

---

## ADR-176 — MVP pricing supports exact/range/Owner Quote only
**Status:** REVISED — clarified by ADR-262 (fixed / bounded owner formula / Owner Quote)

**Decision:** AI cannot invent authoritative custom tattoo pricing or arbitrary discounts.

---

## ADR-177 — MVP scheduling is one primary provider Resource
**Status:** Accepted

**Decision:** availability/Hold/allocation/Appointment/cancel/simple reschedule are required; advanced multi-resource/recurring/external-calendar scheduling is postponed.

---

## ADR-178 — Hosted deposit/full-prepayment flow is required
**Status:** REVISED — expanded by ADR-263 (NONE / fixed / percentage / full prepayment)

**Decision:** one end-client payment provider per Business is sufficient; raw PAN/CVC never reaches platform; refunds remain Owner-approved.

---

## ADR-179 — Late payment after expired Hold must never fabricate booking
**Status:** Accepted

**Decision:** confirmed money is recorded; booking effect is re-evaluated separately and may escalate.

---

## ADR-180 — Human takeover/resume is a hard MVP requirement
**Status:** Accepted

**Decision:** once HUMAN control is active, pending/stale AI outputs cannot be sent; explicit resume re-enters AI from latest canonical state.

---

## ADR-181 — Platform Ops is part of first production MVP
**Status:** Accepted

**Decision:** first real client requires support health/diagnostics/DLQ/AIRun/audit/replay tooling even if business self-service configuration is incomplete.

---

## ADR-182 — Pilot SaaS billing may be TRIAL/COMPED without hidden bypass
**Status:** Accepted

**Decision:** first production Business still uses normal Subscription/Entitlement state; real owner charging may follow before broader commercial rollout.

---

## ADR-183 — Production Pilot and Commercial MVP are separate milestones
**Status:** Accepted

**Decision:** pilot proves product value/safety; commercial MVP additionally requires repeatable paid billing/onboarding/runbooks/support.

---

## ADR-184 — MVP autonomy is action-specific and conservative
**Status:** Accepted

**Decision:** intake/knowledge/vision/portfolio/configured pricing/availability/hold/payment-link/booking may be AUTO; custom quote/discount/refund/exceptions remain Owner or Escalate; risky/medical/minor flows disabled/safe-handoff.

---

## ADR-185 — Golden Journeys A–J define minimum end-to-end scope
**Status:** Accepted

**Decision:** standard tattoo, owner quote, complex escalation, slot race, late payment, reschedule/cancel, takeover, follow-up, prompt injection and dependency failure are mandatory coverage.

---

## ADR-186 — Production readiness uses independent gates
**Status:** Accepted

**Decision:** Domain/AI/Security/Reliability/BusinessConfig/Operations/Privacy must all be ready; one aggregate readiness score cannot hide a critical red gate.

---

## ADR-187 — Critical AI/money/security/booking violations have zero-tolerance gate
**Status:** Accepted

**Decision:** non-critical quality may use calibrated statistical thresholds, but critical violations block release.

---

## ADR-188 — First production uses conservative calibration window
**Status:** Accepted

**Decision:** approximately 20–50 meaningful conversations are reviewed with structured metrics; safety is prioritized over maximal autonomy.

---

## ADR-189 — Pilot autonomy target is evidence/calibration, not permanent contract
**Status:** Accepted

**Decision:** initial target around 70%+ autonomous handling of eligible simple cases and ~95% curated domain/tool correctness are calibration targets, not immutable architecture constants.

---

## ADR-190 — 06_MVP_SPEC is the canonical first-release scope document
**Status:** Accepted

**Decision:** Architecture Spec defines hard architecture; MVP_SPEC defines first-release scope/exclusions/golden journeys/readiness and acceptance criteria.

---

## ADR-191 — Development roadmap is dependency-based, not calendar-based
**Status:** Accepted

Canonical roadmap defines dependency milestones and DoD; exact time estimates follow engineering decomposition.

## ADR-192 — MVP is built through vertical slices
**Status:** Accepted

Avoid building all DB/backend/AI/UI layers independently before end-to-end integration.

## ADR-193 — Production Pilot is the first implementation target
**Status:** Accepted

M0–M12 optimize for one real Tattoo pilot; Commercial MVP follows pilot evidence.

## ADR-194 — Initial product uses one repository/monorepo
**Status:** Accepted

Backend/UI/Ops/infrastructure/tests/evals stay together initially; no repository-per-domain-service split.

## ADR-195 — Tenant/Auth/RLS precede customer and AI features
**Status:** Accepted

WorkspaceContext/RLS/authorization are foundational, not retrofits.

## ADR-196 — First product slice is Telegram messaging without AI
**Status:** Accepted

Owner login + Telegram inbound→Inbox + manual outbound is the first tangible target.

## ADR-197 — Conversation control precedes production AI autonomy
**Status:** Accepted

ConversationTurn/versioning/Human takeover/resume exist before state-changing Agent tools.

## ADR-198 — AI is introduced read/query-only first
**Status:** Accepted

First AI milestone validates ModelGateway/Prompt/Context/Structured Output/AIRun/telemetry before mutation tools.

## ADR-199 — Tattoo Knowledge/Vision/Portfolio precede transactional automation
**Status:** Accepted

The Agent learns the actual Business before pricing/scheduling/payment mutations.

## ADR-200 — Request/Assessment/Pricing precede Scheduling in first build path
**Status:** Accepted

First Tattoo development sequence reaches request/quote behavior before booking while WorkflowDefinition remains configurable.

## ADR-201 — Scheduling is deterministic before Agent scheduling tools
**Status:** Accepted

Availability/Hold/allocation/concurrency/time tests pass before AI mutation access.

## ADR-202 — Client Payments follow stable Hold/Appointment semantics
**Status:** Accepted

Payment integration attaches to proven booking state/recovery rules.

## ADR-203 — Telegram→AI→Quote→Hold→Payment→Appointment is primary development milestone
**Status:** Accepted

Completing this integrated path outranks breadth expansion before pilot.

## ADR-204 — Feature Freeze precedes final Pilot hardening
**Status:** Accepted

After Golden Journey integration, only fixes/hardening/eval work enters Pilot RC absent explicit scope ADR.

## ADR-205 — Pilot RC is a pinned release bundle
**Status:** Accepted

RC records application/schema/IndustryPack/prompt/model/tool/knowledge/business-config/eval versions.

## ADR-206 — Schema is introduced capability-by-capability
**Status:** Accepted

Do not pre-create every future table; when a capability appears, use canonical semantics immediately.

## ADR-207 — Do not implement empty future adapters
**Status:** Accepted

Implement only providers/channels needed by current milestones; interfaces preserve future extensibility.

## ADR-208 — Backend-only completion is not PILOT_READY
**Status:** Accepted

Relevant security/tenant/reliability/telemetry/tests/evals/UI/Ops are part of feature DoD.

## ADR-209 — Technical spikes validate risky assumptions but are not production shortcuts
**Status:** Accepted

Spikes may validate Telegram/RLS/overlap/tool-loop/storage/payment behavior and must end in decisions/tests.

## ADR-210 — Commercial development follows pilot evidence
**Status:** Accepted

M13 Findings → M14 Repeatable Onboarding → M15 SaaS Billing → M16 Commercial Hardening.

## ADR-211 — Stage-23 excluded features stay out without evidence/ADR
**Status:** Accepted

Voice/extra channels/image generation/etc. do not enter M0–M12 merely because they are attractive.

## ADR-212 — 07_DEVELOPMENT_ROADMAP is canonical implementation-sequencing document
**Status:** Accepted

Architecture Spec defines constraints, MVP Spec defines first-release scope, Development Roadmap defines dependency order/milestone DoD.

---

## ADR-213 — Production deployment is a controlled reproducible operation
**Status:** Accepted

**Decision:** immutable artifacts, explicit gates, provenance, rollback and runbooks replace undocumented manual deployment.

## ADR-214 — ReleaseManifest records production release composition
**Status:** Accepted

**Decision:** image/schema/AI/platform/eval versions used by a production release are explicitly identifiable.

## ADR-215 — Application, AI Configuration and Business Configuration releases are independent axes
**Status:** Accepted

**Decision:** each can be changed/rolled back through its own safe mechanism without silently rewriting the others.

## ADR-216 — Database migrations use a separate privileged migration identity
**Status:** Accepted

**Decision:** runtime API/Workers do not receive general DDL rights.

## ADR-217 — Destructive schema migration is separated from dependent code cutover
**Status:** Accepted

**Decision:** Expand→Migrate→Contract remains the production migration model; large backfills are controlled jobs.

## ADR-218 — Production smoke tests use a dedicated Test Workspace
**Status:** Accepted

**Decision:** smoke tests validate infrastructure/application safely without uncontrolled real customer/financial side effects.

## ADR-219 — Pilot uses monitored controlled deployment rather than mandatory continuous deployment
**Status:** Accepted

**Decision:** CI may run continuously, while live AI/payment release is an explicit observed operation initially.

## ADR-220 — Rollback paths are subsystem-specific
**Status:** Accepted

**Decision:** application, AI configuration, Business configuration and data restore are separate recovery mechanisms.

## ADR-221 — Narrow operational kill switches are required
**Status:** Accepted

**Decision:** AI/bulk/payment-session/optional processing can be paused independently while preserving essential canonical/inbound/manual operations.

## ADR-222 — Routine production drift through SSH/ad-hoc SQL is prohibited
**Status:** Accepted

**Decision:** emergency manual action is exceptional, audited and reconciled back into canonical config/IaC/source.

## ADR-223 — Production repair uses controlled scoped commands/jobs
**Status:** Accepted

**Decision:** data repair should be version-controlled, validated, idempotent and dry-run-capable rather than arbitrary terminal mutation.

## ADR-224 — Every critical secret has rotation/revocation procedure
**Status:** Accepted

**Decision:** suspected compromise bypasses ordinary release cadence and triggers immediate security response.

## ADR-225 — Backup is not operationally accepted until restore is tested
**Status:** Accepted

**Decision:** provider backup status alone does not satisfy Pilot readiness.

## ADR-226 — Restore targets a new DB instance before cutover
**Status:** Accepted

**Decision:** recovered data is inspected/validated/reconciled without overwriting the last available primary blindly.

## ADR-227 — Provider reconciliation is mandatory after restore/significant outage
**Status:** Accepted

**Decision:** payments/billing/pending events/holds/automations are reconciled against external providers/canonical rules after recovery.

## ADR-228 — Exact RPO/RTO/SLO numbers are Stage-26 release configuration
**Status:** Accepted

**Decision:** values are mandatory before live Pilot but depend on concrete provider, Business expectations and cost rather than universal architecture constants.

## ADR-229 — Initial incident severity is SEV-1 / SEV-2 / SEV-3
**Status:** Accepted

**Decision:** severity is based on customer/security/canonical impact rather than raw stack-trace severity.

## ADR-230 — Incident response prioritizes harm containment and data preservation
**Status:** Accepted

**Decision:** stop dangerous effects/preserve durable state/restore essential service before deep root-cause analysis.

## ADR-231 — Pilot runbooks are version-controlled product artifacts
**Status:** Accepted

**Decision:** critical DB/worker/AI/channel/payment/storage/deploy/migration/security/recovery scenarios have documented Trigger→Safety→Recovery→Verify procedures.

## ADR-232 — First-Business cutover is progressive
**Status:** Accepted

**Decision:** manual channel path is verified before AI, then transactional tools, payments and automations are enabled in stages.

## ADR-233 — High-risk releases require targeted tests/evals and explicit recovery plan
**Status:** Accepted

**Decision:** DB/payment/scheduling/security/AI-tool/config changes receive stronger release gates than low-risk presentation changes.

## ADR-234 — Significant incidents must create preventive regression artifacts
**Status:** Accepted

**Decision:** post-incident follow-up should add tests/evals/constraints/alerts/runbook improvements where applicable.

## ADR-235 — 08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS is canonical production-operations document
**Status:** Accepted

**Decision:** Architecture Spec defines constraints, Development Roadmap defines build order, and the Runbook document defines production deployment/cutover/recovery procedures.

---

## ADR-236 — Russia is the primary market/data region until multi-region
**Status:** Accepted

RU is the first `MarketProfile`/HomeDataRegion; country-specific behavior stays outside Universal Core.

## ADR-237 — MarketProfile, DataResidencyPolicy and RegionalProviderBundle are explicit
**Status:** Accepted

Workspace placement/config resolves regional infrastructure/provider/compliance choices without duplicating country logic into every domain entity.

## ADR-238 — AI routing is region-qualified and provider-neutral
**Status:** Accepted — extended by ADR-259–261; branch selection remains policy-qualified

Supersedes the old “OpenAI first” assumption. ModelProfile is capability-oriented; ModelRouter additionally enforces data/provider eligibility and Eval approval.

## ADR-239 — Direct foreign API through VPN/proxy is forbidden as RU production foundation
**Status:** Accepted

Unofficial/unsupported access paths are classified `UNVERIFIED_PROXY` and cannot carry production Client traffic.

## ADR-240 — RU AI uses local-hosted and contracted-external lanes
**Status:** REVISED — superseded procurement/default strategy by ADR-259; data eligibility retained

`RU_LOCAL_HOSTED` is default where quality is sufficient; `CONTRACTED_EXTERNAL` may be used only for approved minimized/sanitized tasks under contract/legal/data policy.

## ADR-241 — Cloud.ru Foundation Models is the first RU enterprise gateway candidate
**Status:** REVISED — preferred gateway candidate superseded by ADR-259 (PolzaAI preferred)

Its OpenAI-compatible API and internal/external placement model fit the architecture; exact model IDs/upstream eligibility remain Eval/contract-dependent.

## ADR-242 — OpenAI remains a future-region adapter, not RU direct production provider
**Status:** REVISED — clarified by ADR-259/261; direct adapter is switchability scope, live route eligibility remains mandatory

OpenAI model families may be used directly in future supported markets or indirectly through an approved contracted gateway when policy permits.

## ADR-243 — RU Pilot infrastructure prefers Yandex Cloud without domain lock-in
**Status:** Accepted

Compute/Managed PostgreSQL/Object Storage/Lockbox/Registry/telemetry are provider bindings behind existing abstractions/IaC.

## ADR-244 — YooKassa is the first RU Client PaymentProvider candidate
**Status:** Accepted

Hosted checkout/payment to the Business merchant account is preferred; SaaS does not custody Client funds.

## ADR-245 — Payment and fiscalization are separate state/authority domains
**Status:** Accepted

Russian launch adds BusinessLegalProfile/FiscalizationProfile/FiscalReceipt/FiscalizationService/Adapter; PaymentTransaction does not prove receipt compliance and vice versa.

## ADR-246 — FISCALIZATION_READY is a RU Pilot readiness gate
**Status:** Accepted

The first Business cannot enable live payments until the applicable receipt/fiscalization responsibility/workflow is known and operational.

## ADR-247 — RU Pilot activation is capability-phased
**Status:** Accepted

Manual channel path → AI shadow → safe auto → scheduling → payment → automation, with relevant Golden Journey/Eval gates before each activation step.

## ADR-248 — Critical Pilot failures pause automation, not canonical/manual operation
**Status:** Accepted

Tenant/money/booking/takeover/high-risk failures trigger targeted AI/capability pause while preserving inbound/manual operations/reconciliation.

## ADR-249 — Expansion prioritizes repeatability before breadth
**Status:** Accepted

Several independent RU Tattoo Businesses on the same code/config model precede new industry/region breadth.

## ADR-250 — Second vertical should test a different WorkflowArchetype
**Status:** Accepted

A slot-based beauty IndustryPack is the preferred second vertical after repeatable Commercial RU Tattoo.

## ADR-251 — MAX/VK are RU channel expansion candidates, priority is evidence-driven
**Status:** Accepted

Each uses ChannelAdapter/Capabilities; actual order follows measured customer inquiry demand.

## ADR-252 — AI/media expansion follows data-risk-specific routing
**Status:** Accepted

Voice/transcription and image generation are post-Pilot; text-only generation may use external premium lanes under looser data exposure than raw Client image processing.

## ADR-253 — Provider/model/Industry/Channel capabilities have maturity lifecycles
**Status:** Accepted

No aggregator catalog/model/pack/channel change silently affects production; candidates move through explicit Eval/Pilot/Supported/Deprecated states.

## ADR-254 — Cross-tenant learning never propagates raw Business rules
**Status:** Accepted

Only sanitized/general product patterns may become IndustryPack candidates through review/evals/versioned release.

## ADR-255 — Foreign expansion is one MarketProfile at a time
**Status:** Accepted

Every market receives its own DataResidencyPolicy/RegionalProviderBundle/payment/fiscalization/localization/compliance/Eval package.

## ADR-256 — Workspace Home Data Region is authoritative
**Status:** Accepted

Business transactions remain in one home regional data plane/cell; region routing is trusted server-side placement metadata.

## ADR-257 — True multi-region uses regional Cells, not cross-region transactions
**Status:** Accepted

Global Control Plane is metadata-minimal; no synchronous cross-region business transactions or live joins across regional OLTP stores.

## ADR-258 — Every expansion passes Product/Architecture/Security/Ops/Eval/Economics/Rollback gates
**Status:** Accepted

Expansion is evidence-driven and may revise architecture through ADR only when production evidence shows a genuine universal need.

---

## ADR-259 — Two AI access branches; PolzaAI-preferred RU aggregator
**Status:** Accepted — v0.28

**Decision:** User-approved revision. RU_AGGREGATOR and DIRECT_PROVIDER share domain/tools/context; PolzaAI preferred first candidate, GPTunnel compared. Supersedes ADR-240/241 Cloud.ru-first/local-default preference, not provider/data safeguards. Direct branch uses official eligible APIs; actual processing location is independent of branch.

---

## ADR-260 — Task-specific model selection optimizes verified task economics
**Status:** Accepted — v0.28

**Decision:** Each branch maps logical task profiles to appropriate economical, conversational, complex, Vision, embedding and future image/audio models. Initial shortlist Spec §7.22 is EVAL_ONLY; models/routes require measured quality, latency, total cost and eligibility. No catalog auto-promotion.

---

## ADR-261 — Config-only AI branch switching with pinned runs
**Status:** Accepted — v0.28

**Decision:** AIProviderBranch/AIRoutingRevision activated atomically for new runs; no business-code/state rewrite. Selected aggregator and direct adapters are implementation scope. In-flight effects preserved, incompatible embeddings migrated separately; no unapproved automatic cross-branch/gateway fallback.

---

## ADR-262 — Owner chooses fixed, bounded formula or Owner Quote
**Status:** Accepted — v0.28

**Decision:** User-approved clarification of ADR-176. PricingMode FIXED/CONFIGURED_FORMULA/OWNER_QUOTE is per-service; formula supplied by master and evaluated deterministically in validated bounded rules. Owner price conveyed after structured decision; LLM never invents authoritative price.

---

## ADR-263 — Payment terms follow agreement and are independent of price mode
**Status:** Accepted — v0.28

**Decision:** User-approved expansion of ADR-178. NONE/FIXED_DEPOSIT/PERCENT_DEPOSIT/FULL_PREPAYMENT supported. First Tattoo master uses fixed deposit independent of scale, amount still open. Percentage/full require exact agreed base; no-deposit booking skips checkout without fake paid status.

---

## ADR-264 — Explicit accepted commercial snapshot binds fulfillment
**Status:** Accepted — v0.28

**Decision:** QuoteAcceptance binds Client to immutable offer/scope/terms; creates Order/next Session idempotently. PaymentRequest uses typed Order/Session/Quote/terms relations. Relevant changes require fresh agreement, preserving real money/history.

---

## ADR-265 — Duration examples assist; approved rule or Owner authorizes booking
**Status:** Accepted — v0.28

**Decision:** Price and duration authority independent. DurationCase→retrieval/estimate→owner review→versioned rule; no automatic per-master fine-tuning/self-publication. Missing calibrated rule uses OWNER_DEFINED. Exact master durations/coefficients/session limits remain OPEN-080/081.

---

## ADR-266 — Client-object authorization is required inside Workspace
**Status:** Accepted — v0.28

**Decision:** Extend tenant defense: customer tools verify trusted Client/Business/object relations, including private history/files/payment/appointment. Same-Workspace other-Client tests mandatory.

---

## ADR-267 — Takeover covers AI commands and send admission
**Status:** Accepted — v0.28

**Decision:** Control generation/serialized admission rejects stale AI mutations/sends. Deterministic reconciliation/manual operations continue. In-flight external sends are tracked separately and cannot be claimed recalled. Narrow kill switches distinguish runs/mutations/sends.

---

## ADR-268 — Reschedule atomically replaces its own occupancy
**Status:** Accepted — v0.28

**Decision:** Clarifies ADR-086: allow self-overlap while preserving competitors constraints/history; failed replacement restores old allocation. CalendarBlock shares occupancy conflict protocol; no silent appointment cancellation.

---

## ADR-269 — Payment authenticity is adapter-specific
**Status:** Accepted — v0.28

**Decision:** Provider-authoritative verified webhook/API remains required. YooKassa contract does not assume a universal signature; verify actual object/merchant/amount/currency/test mode and correlation. Technical repeats differ from two real successful payments.

---

## ADR-270 — Pilot gates and roadmap include late accepted requirements
**Status:** Accepted — v0.28

**Decision:** FISCALIZATION_READY blocks live RU payments and appears in checklists; local pilot Subscription/Entitlements precedes paid M15 billing; workflow/approval/Order/Session explicitly assigned. PRODUCTION_PILOT and COMMERCIAL_MVP horizons disambiguate old MVP lists.

---

## ADR-271 — Recovery must fence old runtime and recover newer deletion state
**Status:** Accepted — v0.28

**Decision:** Restore requires single active effect-producing generation, durable deletion state beyond rollback point and external-effect reconciliation before Outbox replay. Unknown effects/data remain paused/quarantined; exact validated mechanisms OPEN-084.

---

## ADR-272 — Owner waits and unavailable notification routes are visible outcomes
**Status:** Accepted — v0.28

**Decision:** Bounded reminders, current-state validation and explicit owner tasks prevent silent abandonment. Closed Telegram window is not send success; no Console bypass. Business timings and exceptions remain OPEN-082/083.

---

## ADR-273 — Business-intent idempotency spans AIRuns
**Status:** Accepted — v0.28

**Decision:** Successful technical tool recovery retained; critical commands also deduplicate by stable authoritative business intent across new runs. Distinct provider money is preserved; duplicate fulfillment and excess concurrent refunds prevented.

---

## ADR-274 — Pilot success measures owner workload and full inquiry coverage
**Status:** Accepted — v0.28

**Decision:** Add eligible/all-inquiry denominators, owner active time/interventions, waiting/delivery outcomes and total resolved-task cost. Small calibration sample/zero critical test failures is not proof of zero production failure probability.


---

## Исходный файл: 03_GLOSSARY.md

# AI Service Manager — Glossary

**Baseline:** v0.28  
**Дата:** 2026-09-09

Правило: один концепт должен иметь одно устойчивое имя. Если термин меняется, Glossary и ADR/Changelog обновляются вместе.

---

## Actor
Сущность, совершившая действие: Client, BusinessMember, AI Agent, System, External Provider.

## AI Agent
AI-компонент, который понимает ситуацию, выбирает разрешённые tools/actions и участвует в ведении клиента. Не имеет произвольного SQL и не выбирает Workspace. Формальная архитектура — Stage 8.

## AI Run

Legacy spelling of `AIRun`; use AIRun canonically. One logical task can include multiple provider calls and tool continuations.

## Appointment
Конкретный подтверждённый временной интервал для выполнения ServiceSession. Не то же самое, что ReservationHold.

## ApprovedConversationExample
Проверенный representative example коммуникации бизнеса, используемый для воспроизведения стиля/поведения.

## Assessment / ServiceAssessment
Оценка выполнимости, сложности, продолжительности или объёма ServiceRequest. Не Quote.

## AuditEvent
Историческая запись о значимом действии: actor, action, resource, timestamp и контекст. Не OutboxEvent.

## Business
Конкретный сервисный бизнес внутри Workspace. `Business != Workspace`.

## BusinessMember
Человек, участвующий в Business: владелец, мастер, администратор и т. п. Может существовать без UserAccount.

## Business Rule
Authoritative правило, влияющее на решение системы: минимальная цена, депозит, запрет услуги, возрастное ограничение и т. п. Отвечает на «что делать/что разрешено».

## Channel Adapter
Provider-specific компонент, переводящий Telegram/VK/MAX/Web events в универсальные внутренние события и обратно.

## ChannelCapabilities
Описание доступных действий конкретного ChannelConnection: reply, media, edit, delete, proactive messaging, reply window и т. п.

## ChannelConnection
Подключение конкретного внешнего канала к Business.

## ChannelRoute
Platform-level mapping внешнего route key к Workspace и ChannelConnection. Используется до создания WorkspaceContext.

## Client
Клиент конкретного Workspace/Business. Не является глобальной персоной между Workspace.

## ClientIdentity
Идентификатор Client во внешнем канале/контакте: Telegram user id, VK identity, email, phone и т. п.

## Client History / Client Memory
Персональный контекст конкретного Client внутри Workspace. Не Business Knowledge.

## CommunicationProfile
Структурированное описание стиля общения бизнеса/мастера: формальность, «ты/вы», длина ответа, emoji usage и т. п.

## Conversation
Долгоживущий диалог Client ↔ Business. Может содержать несколько ServiceRequest/ServiceOrder. Не является заказом.

## ConversationControl
Режим, определяющий, может ли AI автоматически отвечать. MVP: AI / HUMAN.

## Conversation Engine
Backend orchestration layer между normalized channel events и AI/business services. Отвечает за turns, context, routing, structured updates, concurrency/relevance и response coordination. Не LLM.

## Conversation Summary
Производное компактное описание старой части разговора для AI context. Не source of truth.

## ConversationTurn
Смысловой ход разговора, который может состоять из нескольких Messages/attachments.

## Escalation
Запрос участия человека в конкретной проблеме. Не обязательно означает full takeover.

## FileObject
Canonical metadata физического файла. Binary хранится в Object Storage.

## GeneratedAsset
AI-generated/edited визуальный или другой артефакт. Не PortfolioItem и не автоматически финальный technical artifact.

## HistoricalCase
Сжатое структурированное представление полезного прошлого кейса: проблема, ограничения, решение, причина, результат.

## InboxEvent
Сохранённое входящее внешнее событие для дедупликации и надёжной обработки.

## Industry Module
Модуль отраслевой специфики: Intake Schema, Workflow Definition, отраслевые rules/settings, tool availability, escalation policy. Формальная модель — Stage 9.

## Intake Schema
Схема данных, которые нужно собрать для конкретной Service/ServiceRevision.

## Knowledge
Информация для консультаций, объяснений и RAG. Не заменяет authoritative Business Rules/structured state.

## KnowledgeBuild
Версионируемый, проверенный и опубликованный набор знаний/конфигурации для production AI.

## KnowledgeCandidate
Извлечённое/предложенное знание или rule candidate, ещё не authoritative.

## KnowledgeChunk
Смысловой search unit KnowledgeItem для retrieval.

## KnowledgeItem
Нормализованная единица знания, созданная из одного или нескольких KnowledgeSource.

## KnowledgeSource
Сырой источник knowledge ingestion: документ, FAQ, переписки, manual note и т. п.

## Location
Место оказания услуги.

## Message
Одно входящее/исходящее сообщение канала. Несколько Message могут образовать ConversationTurn.

## Notification

Legacy generic label; use `NotificationIntent` for the canonical need and `NotificationDeliveryAttempt` for a concrete send attempt.

## NotificationRoute
Потенциальный transport/route доставки уведомления. Детали — Stage 14.

## Object Storage
Приватное blob/file хранилище binary assets.

## OutboxEvent
Надёжно сохранённое внутреннее событие для async/external обработки после database commit.

## PaymentRequest
Бизнесовое требование оплатить конкретную сумму.

## PaymentTransaction

Provider payment operation with stable provider identity and lifecycle (pending/succeeded/failed as normalized). A successful state is provider-authoritative money evidence; raw HTTP retries are not separate money movements. Refund is separate. PaymentSession is checkout; PaymentRequest is obligation.

## Platform Industry Knowledge
Проверенные общие знания платформы по отрасли. Хранятся отдельно от Workspace Knowledge.

## PortfolioItem
Реальная работа/пример бизнеса с файлами, metadata и search representation. Не GeneratedAsset.

## Portfolio Intelligence
Vision/metadata/search layer для понимания портфолио и поиска похожих реальных работ.

## Pricing Engine

Canonical code name `PricingEngine`: deterministic fixed/configured-formula calculation or structured Owner price boundary. Does not delegate authoritative arithmetic or arbitrary executable formulas to LLM.

## Quote
Коммерческое предложение Client. После отправки исторически не переписывается; новые условия создают новый Quote.

## QuoteLine
Отдельный компонент Quote: услуга, доплата, скидка и т. п.

## RAG
Retrieval-Augmented Generation. Получение релевантных знаний/кейсов/портфолио перед AI response. Не source of truth для hard business facts.

## ReservationHold
Временное удержание слота до выполнения условия. Не confirmed Appointment.

## Resource
Ограниченный ресурс для услуги: мастер, кабинет, оборудование и т. п.

## Service
Стабильная сущность каталога услуг.

## ServiceOrder
Согласованный заказ клиента. Может содержать одну или несколько ServiceSession.

## ServiceRequest
Структурированное описание того, что хочет Client. Не Conversation, Quote или Order.

## ServiceRevision
Immutable опубликованная версия конфигурации Service.

## ServiceSession
Логическая часть выполнения ServiceOrder. Может существовать без даты.

## Source of Truth
Authoritative место, откуда система получает окончательный факт. Например Appointment state из PostgreSQL, а не из старого текста.

## Structured State
Актуальные нормализованные бизнес-данные: ServiceRequest fields, Order, Appointment, Payment state и т. п. Имеют больший приоритет, чем memory/summary модели.

## Structured UserAction
Точное действие пользователя из кнопки/формы/другого deterministic UI signal. По возможности обрабатывается без LLM.

## Tenant
Техническое понятие изоляции клиента SaaS. В проекте tenant boundary называется Workspace; отдельный `tenant_id` не используется.

## UserAccount
Аккаунт пользователя SaaS. Может состоять в нескольких Workspace.

## Visual Design Service
Отдельный сервис генерации/редактирования визуальных концептов. Conversation Engine решает необходимость VisualRequest, сервис создаёт GeneratedAsset.

## VisualRequest
Запрос к Visual Design Service: purpose, instructions, source assets, constraints.

## Workflow Definition
Конфигурация последовательности/условий business process конкретной услуги/industry module. Не существует одного обязательного workflow для всех профессий.

## Workspace
Tenant/security boundary платформы. Все tenant-scoped данные принадлежат Workspace.

## WorkspaceContext
Server-side контекст business operation:
```text
workspace_id
actor
permissions
request/correlation id
```
Не формируется из свободного текста Client/LLM.

## WorkspaceMembership
Связь UserAccount с Workspace, содержащая role/permissions.

## AIProviderCall
Один физический вызов внешнего AI provider внутри AIRun. Хранит model/profile/usage/latency/error metadata.

## AIRun
Логическая AI-задача платформы. Может включать несколько AIProviderCall и tool continuations.

## ContextBuilder
Компонент, собирающий ограниченный trusted context для конкретной AI-задачи из structured state, rules, RAG, portfolio, summary и recent turns.

## EmbeddingProfile
Версионированная конфигурация embedding projection: provider, model, dimensions, distance metric и status.

## ModelGateway

Provider-neutral invocation boundary; uses a route resolved by ModelRouter and dispatches through an adapter. Official API compatibility does not imply identical model features.

## ModelProfile
Логический профиль AI-задачи, например `CONVERSATION_DEFAULT`, `FAST_EXTRACTION` или `IMAGE_GENERATION`. Не равен конкретному model ID.

## ModelRouter

Deterministic resolver of AIProviderBranch + AIRoutingRevision + ModelProfile into an eligible adapter/model, respecting task/risk/modality/workload, capabilities, Evals and data/provider policy.

## PromptBundle
Версионируемая сборка platform/task instructions и trusted context layers для конкретного AIRun.

## PromptRegistry
Реестр версий platform prompts/instructions.

## SafetyGateway
AI-layer boundary для moderation/safety signals до применения platform/industry/business policy.

## SchemaRegistry
Реестр versioned schemas для Structured Outputs и других machine-readable AI contracts.


## ActionPolicy
Политика автономности конкретного business action: `AUTO`, `REQUIRE_CONFIRMATION`, `ESCALATE` или `DISABLED`, с required permissions/evidence/limits.

## AgentBudget
Ограничения одного Agent execution: steps, tool calls, state mutations, deadline и при необходимости cost.

## AgentOutcome
Структурированный итог AgentRuntime, например SEND_RESPONSE, WAIT_FOR_CLIENT, WAIT_FOR_HUMAN, ESCALATED, FAILED.

## AgentRuntime
Application orchestration layer, который связывает ContextBuilder, ModelGateway, ToolSetResolver, PolicyEngine, bounded loop и ToolGateway.

## AIToolCall / ToolTrace
Запись о tool request/execution path внутри AIRun. Не равна AuditEvent.

## ApprovalRequest
Frozen privileged action, ожидающий подтверждения уполномоченного BusinessMember. После approval действие повторно валидируется перед исполнением.

## BusinessConfigurationRelease
Immutable manifest совместно опубликованных Service/Workflow/Rule/Knowledge/Communication/Autonomy revisions. Используется для atomic publish, reproducibility и rollback новых операций.

## ConfigurationDraft
Рабочая, непроизводственная конфигурация, создаваемая/изменяемая в onboarding до validation/approval/publish.

## ImportBatch
Набор загруженных onboarding sources одного происхождения/импорта с processing status.

## Industry Pack
Versioned platform template отрасли: service/intake/workflow defaults, terminology, portfolio schema, onboarding/autonomy/escalation templates. Не содержит конкретные цены и правила бизнеса.

## OnboardingAgent
Отдельный AI workflow для анализа бизнеса и подготовки configuration candidates/draft. Не является ConversationAgent и не публикует production конфигурацию самостоятельно.

## OnboardingQuestion
Dependency-aware вопрос владельцу, связанный с конкретным missing/conflicting/confirmation field и priority.

## OnboardingSession
Lifecycle процесса настройки бизнеса от source collection до publication.

## PolicyEngine
Server-side компонент, который принимает окончательное решение, разрешено ли конкретное tool/action в текущем контексте.

## ToolExecutionContext
Server-generated execution context tool call: Workspace, Business, actor, permissions, current domain refs, AIRun/correlation IDs.

## ToolGateway
Boundary между model tool request и application service: schema validation, policy, permissions, execution и structured result.

## ToolRegistry
Реестр versioned business tools/capabilities платформы.

## ToolSetResolver
Компонент, который выдаёт Agent минимальный allowed tool set по WorkflowStep, Service capabilities, permissions и policy.

## Workflow Archetype
Общий шаблон семейства бизнес-процессов, например Slot-Based, Event-Based, Custom Production или Recurring Session.

## WorkflowInstance
Runtime instance конкретной WorkflowRevision для ServiceRequest/Order process.

## WorkflowRevision
Immutable опубликованная версия WorkflowDefinition, используемая конкретным ServiceRevision/WorkflowInstance.

## WorkflowStepInstance
Runtime состояние отдельного шага WorkflowInstance. Не заменяет domain entity/state.

## ValidationIssue
Результат deterministic validation draft/release с severity ERROR/WARNING/INFO.


## AutomationDefinition / AutomationRevision
Versioned правило того, когда или при каком domain event/state timeout должна возникнуть автоматическая операция.

## AutomationInstance
Persistent runtime instance automation с due time/status/relevance.

## AvailabilityOffer
Набор server-generated вариантов времени, показанных Client. Ничего не резервирует сам по себе.

## AvailabilityRule
Повторяющееся правило рабочей доступности Resource.

## AvailabilityOverride
Разовое изменение стандартной доступности.

## CalendarBlock
Operational interval, блокирующий Resource: отпуск, личная занятость, maintenance и т. п.

## Delivery Horizon

Delivery scope distinct from decision status: PRODUCTION_PILOT, COMMERCIAL_MVP, CORE_POST_MVP, FUTURE_OPTIONAL. Legacy MVP labels are disambiguated by 06_MVP_SPEC and do not expand Pilot scope.

## NotificationDeliveryAttempt
Одна конкретная попытка доставить NotificationIntent через route/provider.

## NotificationIntent
Persisted channel-independent необходимость уведомить получателя о конкретном purpose/event.

## NotificationPolicyRevision
Versioned правила каналов, quiet hours, frequency caps, fallback и notification categories.

## PaymentProviderAdapter
Integration boundary между PaymentService и конкретным payment provider.

## PaymentProviderConnection
Подключённый merchant account Business у payment provider.

## PaymentSession
Provider checkout/link/session для выполнения PaymentRequest. Не является фактом оплаты.

## PaymentTermsRevision
Immutable правила того, когда и какую часть commercial amount нужно платить.

## PriceCalculation
Immutable внутренний результат PricingEngine по конкретным pricing inputs.

## PriceComponent
Internal component расчёта цены; не обязательно customer-visible QuoteLine.

## PricingPlan / PricingRevision
Versioned определение того, как рассчитывается стоимость Service.

## ResourceAllocation
Technical exclusive occupancy interval Resource, создаваемый Hold/Appointment и защищающий от overlap.

## SchedulingPolicyRevision
Immutable правила duration, buffers, booking horizon/start policy и resource requirements Service.

## ServiceResourceRequirement
Описание Resources/roles/capabilities, необходимых для выполнения Service.


## AIDataPolicy
Application policy, определяющая какие data classes и какой минимальный context могут передаваться внешнему AI provider для конкретного task/model profile.

## BillingInvoice
Normalized local representation/reference provider invoice для SaaS Subscription конкретного Workspace.

## DeadLetterItem
Persistent запись job/event, который исчерпал безопасные retries или признан permanent/poison failure и требует operational review/replay.

## EntitlementService
Server-side service, вычисляющий доступные Workspace capabilities/limits из PlanRevision, service mode, overrides и quota state.

## IdempotencyRecord
Persistent record stable operation key + request fingerprint + result reference для безопасного повторения side-effect command.

## PaymentMethodReference
Безопасная ссылка на tokenized payment method у SaaS billing provider; может хранить brand/last4/expiry display metadata, но не PAN/CVC.

## PlanEntitlement
Versioned capability/limit, предоставляемый SaaSPlanRevision.

## PlatformRoleAssignment
Platform-level role/permissions для Ops/Support/Admin; не является WorkspaceMembership.

## PrivacyNoticeRevision
Immutable/versioned privacy notice, который может referenced consent/acknowledgement records.

## PrivacyRequest
Запрос на privacy lifecycle action, например EXPORT/DELETE/RECTIFY/RESTRICT, применимый согласно рынку/политике.

## QuotaReservation
Persistent reservation части hard quota до запуска дорогой side-effect operation; consuming/release предотвращают concurrency overspend.

## RetentionPolicy
Политика lifecycle/retention по типу/классу данных, включая canonical data, raw imports, files, debug data и backups.

## SaaSPlan / SaaSPlanRevision
Stable SaaS plan identity и immutable commercial/entitlement revision.

## SecurityEvent
Security-oriented event (failed auth, denied access, webhook signature failure, support access, abuse signal), отделённый от business AuditEvent и technical logs.

## SupportAccessGrant
Time-bound, scope-limited, reasoned and audited разрешение platform support actor на доступ к конкретному Workspace без WorkspaceMembership/impersonation.

## UsageEvent
Immutable/idempotent normalized usage accounting entry, связанный с Workspace и source operation.

## UsageAggregate
Derived/rebuildable aggregation UsageEvents для UI/analytics/billing calculations.

## UsageMetricDefinition
Описание raw usage metric (tokens, provider cost, images, storage и т. п.).

## MeterDefinition
Правило преобразования raw UsageEvents в commercial/billable product unit.

## WorkspaceBillingAccount
SaaS billing identity/settings конкретного Workspace.

## WorkspaceServiceMode
Product access mode (`NORMAL`, `GRACE`, `LIMITED`, `SUSPENDED`), отделённый от provider billing state.

## Correlation ID
Идентификатор causal/request chain для tracing связанных операций; не является idempotency key.

## Causation ID
Ссылка на непосредственную причину event/action внутри causal chain.

## Retry
Автоматическое повторение execution attempt по retry policy.

## Replay
Намеренный повтор processing исходного persisted event через обычные guards/idempotency/state checks.

## UNKNOWN External Result
Состояние external side effect, когда из-за timeout/network ambiguity неизвестно, выполнил ли provider операцию; не эквивалентно FAILED.


## AIReleaseCandidate
Version-pinned candidate AI behavior bundle evaluated against ProductionBaseline before promotion.

## AIProviderPriceRevision
Versioned/effective provider pricing reference for historical internal AI cost estimation.

## AnalyticsFact
Derived business/product analytical fact from authoritative domain outcomes/events; not canonical business state.

## Cell
Future self-contained Workspace data-plane unit used for large-scale tenant placement/blast-radius isolation.

## CostGuard
Internal economic guard that can warn/throttle/block optional expensive workloads independently from quota/rate limiting.

## EvalCase
Versioned AI-evaluation scenario with structured state/context, allowed/forbidden outcomes and evaluator metadata.

## EvalCaseResult
Result of one EvalCase for a specific candidate/run, including outcome, tool trace, violations, cost and latency.

## EvalRun
Execution of an EvalSuiteRevision against pinned model/prompt/tool/schema/knowledge/config versions.

## EvalSuite / EvalSuiteRevision
Logical evaluation suite and immutable/versioned case/evaluator specification.

## EvaluatorDefinition
Deterministic, rule-based, model-judge or human evaluation logic.

## HumanReview
Human quality label/review linked to an eval result or production-derived candidate.

## ProductionBaseline
Current production AI/config behavior bundle used for regression comparison.

## SLI
Service Level Indicator — measured reliability/performance signal.

## SLO
Service Level Objective — target for an SLI; numeric values are deployment/SLA decisions.

## Telemetry
Noncanonical technical Metrics/Logs/Traces, distinct from AuditEvent/SecurityEvent/UsageEvent.

## Workload Class
Operational priority class: CRITICAL, INTERACTIVE, NORMAL or BULK.

## Workspace Placement

Trusted control-plane mapping of Workspace to Home Data Region; future Cells extend this placement. AI branch selection does not move canonical tenant data.

## Commercial MVP
Milestone after Production Pilot in which paid SaaS billing, repeatable onboarding, runbooks/support and stable first-vertical quality gates are ready for broader paying customers.

## Eligible Simple Conversation
Conversation/request that current Workflow/Autonomy Policy explicitly allows AI to resolve without mandatory human decision; used as denominator for autonomy metrics.

## Golden Journey
Canonical end-to-end scenario that must pass across domain state, AI behavior, security/reliability and external-effect boundaries before production release.

## MVP Autonomy Contract
Stage-23 action-by-action mapping of `AUTO / OWNER / ESCALATE / DISABLED` for the first production scope.

## Production Pilot
First real-Business rollout used to validate product value, safety, operations and unit economics before broader commercial launch.

## Production Readiness Gate
Independent gate such as DOMAIN_READY, AI_READY, SECURITY_READY, RELIABILITY_READY, BUSINESS_CONFIG_READY, OPERATIONS_READY, PRIVACY_READY; FISCALIZATION_READY additionally gates RU live payments.

## TattooIndustryPack v1
First production Industry Pack configuring Tattoo-specific onboarding, intake, workflow defaults, risk/escalation rules and terminology over the universal core.


## Development Milestone
Dependency-bounded implementation checkpoint with explicit capability scope and Definition of Done; not synonymous with a calendar sprint.

## Feature Freeze
Pilot-roadmap point after integrated Golden Journeys where new feature scope stops and only bugs, security/reliability, critical UX and eval fixes are accepted without a new scope decision.

## Pilot Release Candidate
Pinned deployable candidate for the first real Business containing application/schema/config/model/prompt/tool/knowledge/eval versions.

## PILOT_READY
Implementation completeness level meaning the capability meets Stage-23 pilot scope plus required security/reliability/telemetry/tests/UI/Ops obligations.

## SKELETON
Implementation completeness level where only interfaces/entity shape/basic scaffolding exist; not production-usable.

## EXPANSION_READY
Post-pilot completeness level supporting broader complexity beyond first MVP requirements.

## Technical Spike
Short bounded proof-of-capability used to validate a risky external/DB/AI assumption and produce a decision/test; not itself production implementation.

## Vertical Slice
End-to-end implementation increment spanning the persistence/domain/API/UI/integration/test behavior needed for one usable capability.

## Application Release
Immutable deployed application/container version, distinct from AI configuration and tenant BusinessConfigurationRelease.

## Break-Glass DB Access
Exceptional time-bound/audited engineering access to production data for emergency diagnosis/repair; not normal operations.

## Deployment Observation Window
Monitored period after production rollout during which critical health signals are actively checked before considering the release stable.

## Kill Switch
Narrow operational control that pauses a specific subsystem/capability (e.g. AI auto-send or new payment sessions) without unnecessarily disabling unrelated essential functions.

## Platform AI Configuration Release
Versioned platform mapping of model/prompt/tool/policy behavior that can be promoted/rolled back independently from application binary and Business configuration.

## ReleaseManifest
Deployment artifact describing exact application/container/schema/AI/platform/eval versions and source/CI provenance of a production release.

## Repair Command
Controlled, scoped, validated and preferably idempotent/dry-run-capable production data repair operation, used instead of ad-hoc SQL mutation where possible.

## SEV-1 / SEV-2 / SEV-3
Initial operational incident severity classes for critical impact, major degradation and limited/localized impact respectively.

## BusinessLegalProfile
Market-specific legal/tax classification of a Business used to select compliance/fiscalization policy without polluting universal service domain logic.

## Contracted External / CONTRACTED_EXTERNAL
Provider execution class in which the platform contracts with an approved gateway/aggregator but inference is performed by an external upstream model provider. Requires explicit data/legal/provider eligibility.

## DataResidencyPolicy
Policy defining where each data class may be stored/processed/transferred for a Workspace/HomeDataRegion and which external-processing paths are allowed.

## FiscalizationAdapter
Market/provider adapter that creates/queries required fiscal/tax receipt operations separately from PaymentProviderAdapter.

## FiscalizationProfile
Business/market configuration selecting receipt strategy such as MANUAL_OWNER, PROVIDER_INTEGRATED or EXTERNAL_FISCAL_PROVIDER.

## FiscalReceipt
Canonical normalized record of the required fiscal/tax receipt lifecycle; distinct from PaymentTransaction.

## FiscalizationService
Application service coordinating receipt obligations/status/providers without making PaymentService country-specific.

## Home Data Region
Authoritative regional data plane/cell in which a Workspace's canonical business transactions reside.

## MarketProfile
Market-specific defaults/capabilities/policy bundle (for example RU) covering locale/currency/compliance/provider eligibility without embedding market logic in Universal Core.

## ProviderExecutionClass
Trust/placement classification for model execution: RU_LOCAL_HOSTED, CONTRACTED_EXTERNAL, DIRECT_REGION_PROVIDER or UNVERIFIED_PROXY.

## RegionalProviderBundle
Versioned/default mapping of a Market/DataRegion to concrete infrastructure, AI, payment, fiscalization and observability provider adapters.

## RU_LOCAL_HOSTED
AI execution class where the selected model runs inside the approved Russian provider infrastructure/data perimeter.

## UNVERIFIED_PROXY
Unofficial/unsupported VPN/proxy/resale execution path with unclear provider/upstream eligibility; prohibited for production Client traffic.

## Maturity State
Lifecycle label for IndustryPack/Channel/AI provider/model capabilities such as EXPERIMENTAL/PILOT/SUPPORTED/DEPRECATED or EVAL_ONLY/CANARY/APPROVED/DISABLED.

## AIProviderBranch
Access-mode branch RU_AGGREGATOR or DIRECT_PROVIDER. Independent from actual processing-location ProviderExecutionClass and from Home Data Region.

## AIRoutingRevision
Immutable task-profile→adapter/model/parameters/capability/fallback mapping. Pinned per AIRun; atomically activated for new runs and independently rollbackable.

## PricingMode
Owner-selected FIXED, CONFIGURED_FORMULA or OWNER_QUOTE. Independent of duration authority and PaymentTerms.

## QuoteAcceptance
Auditable explicit Client acceptance bound to a specific immutable Quote, scope, price authority and PaymentTermsRevision. Not Owner approval or general conversational sentiment.

## DurationPolicyRevision
Versioned owner-approved duration strategy/rules linked from SchedulingPolicyRevision. FIXED / CONFIGURED_RULE / OWNER_DEFINED.

## DurationEstimate
Derived proposed duration with evidence/uncertainty; not bookable authority by itself.

## DurationCase
Owner-scoped labelled historical work with permitted image/attributes, actual or explicitly recalled duration, occupied-slot components, sessions and explanation. Used for reviewed candidates/case comparison.

## PaymentTerms mode
NONE / FIXED_DEPOSIT / PERCENT_DEPOSIT / FULL_PREPAYMENT for Pilot. NONE means no advance payment requirement, not free service. First master uses FIXED_DEPOSIT; amount remains configuration.

## COMPED
Explicit funding/commercial mode for a complimentary subscription, not a provider payment status. Pilot can use ACTIVE subscription + COMPED funding with normal Entitlements; TRIALING is a separate lifecycle state.

## ROUTE_UNAVAILABLE
Notification/send outcome when channel rights/window/route do not permit delivery. Owner-visible; not success and not unlimited transient retry.

## Control generation
Monotonic ConversationControl version used to reject stale AI runs/commands/sends after takeover. External effects already in flight remain separately tracked.

## FISCALIZATION_READY
Conditional RU readiness gate before real Client payment activation; verifies legal/tax profile and operational receipt obligation path. Not a payment-success flag.


---

## Исходный файл: 04_OPEN_QUESTIONS.md

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


---

## Исходный файл: 05_CHANGELOG.md

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
- Immutable container digest/source/CI provenance and `ReleaseManifest` locked.
- Application / AI Configuration / Business Configuration releases separated.
- Separate privileged migration identity and Expand→Migrate→Contract deployment model reinforced.
- Safe readiness/smoke/drain/observation workflow defined.
- Application/AI/config rollback paths separated from DB/data recovery.
- Narrow subsystem kill switches and Workspace AI pause required.
- No routine SSH/config drift/ad-hoc SQL; emergency break-glass/repair semantics defined.
- Secret rotation/compromise procedures locked.
- Managed backup/PITR plus actual tested restore made Pilot gate.
- Restore-to-new-instance + RLS/invariant/privacy/provider reconciliation defined.
- Numerical RPO/RTO/SLO required before Pilot but deferred to Stage 26 concrete provider/business.
- SEV-1/2/3 and incident lifecycle/priorities defined.
- Required Pilot runbook catalog (DB, queue, AI, Telegram, payments, storage, deployment, migration, DR, security, cost, DLQ, takeover, scheduling) locked.
- First-Business cutover made progressive: manual channel → AI → scheduling → payments → automations.
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
- Production Pilot is the first implementation objective; Commercial MVP follows pilot learning.
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
- Stage 25 is not designed in this baseline.

### Still deferred
- exact programming languages/frameworks/tooling;
- concrete engineering tickets and calendar estimates;
- concrete cloud/payment/observability providers;
- Stage 25 deployment/runbooks;
- exact first Business/jurisdiction;
- final pilot-calibrated non-critical AI thresholds.

---

## v0.23 — 2026-09-08

**Status:** Canonical baseline after accepting Stage 23 MVP Scope + Acceptance Criteria. Stage 24 Development Roadmap remains intentionally undesigned.

### Stage 23 — MVP Scope
- First production vertical fixed as Tattoo.
- Primary autonomous service fixed as New Tattoo Request.
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
- Added new canonical `06_MVP_SPEC.md`.
- `00_PROJECT_OVERVIEW.md` roadmap advanced through Stage 23.
- `01_ARCHITECTURE_SPEC.md` now contains locked Stage 23 architecture-level scope.
- ADR log extended through ADR-190.
- Open Questions updated: Tattoo/MVP boundary resolved; actual first Business/provider/jurisdiction/precise eval thresholds remain appropriately deferred.
- Stage 24 is not designed in this baseline.

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

### Stage 20 — Observability / AI Cost / Analytics
- Metrics/Logs/Traces separated from Audit/Security/Usage.
- OpenTelemetry-compatible instrumentation.
- Correlation/causation, queue lag and user-journey latency made first-class.
- AI cost attribution/reconciliation architecture and CostGuard added.
- Product analytics defined around domain/workflow outcomes.
- SLI/SLO and actionable alert philosophy added.

### Stage 21 — Scaling
- Scaling made metric-driven.
- Optimize/vertical/horizontal/workload-pool ladder precedes specialized infra/cells.
- Noisy-neighbor controls formalized.
- PostgreSQL Jobs/pgvector/PostgreSQL FTS remain defaults until measured triggers.
- Workspace defined as future Cell/shard placement unit.
- Microservice extraction requires concrete trigger.
- Backpressure/chunked bulk processing formalized.

### Stage 22 — Testing + AI Evals
- Software testing and AI Evals split into separate quality systems.
- Real PostgreSQL/RLS/concurrency/idempotency/recovery testing locked.
- EvalSuite/EvalCase/EvalRun/ProductionBaseline concepts introduced.
- Critical money/payment/scheduling/security/tool failures are hard release gates.
- RAG/injection/human-takeover/staleness/tool evals formalized.
- Production failures become sanitized regression cases where possible.
- Model/prompt/tool/schema/KnowledgeBuild changes require versioned release gates.
- Continuous learning explicitly does not mean live production self-modification.

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
- Observed usage/provider cost separated from commercial billable meters.
- QuotaService + QuotaReservation for expensive hard-quota operations.
- SaaS billing provider removed from critical path of Client runtime.

### Stage 16 — Business Console / Platform Operations
- `Master UI` renamed canonically to `Business Console`.
- Separate Business Console and Platform Operations security surfaces.
- Exception-first Action Center, Inbox, Calendar, Approvals/Escalations.
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
- Support access and emergency break-glass security semantics formalized.
- Incident response/vendor-subprocessor obligations added as production prerequisites.

### Stage 18 — Reliability / Idempotency / Recovery
- At-least-once + idempotent processing adopted instead of distributed exactly-once assumptions.
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
- Structured pricing strategies and price authority.
- Quote only from validated calculation/owner decision.

### Stage 12 — Scheduling
- Dynamic Availability Engine instead of persisted free-slot inventory.
- SchedulingPolicyRevision, Availability rules/overrides/blocks.
- AvailabilityOffer and ResourceAllocation.
- DB-level double-booking protection.
- Atomic Hold→Appointment conversion.
- Multi-session/recurring/event/onsite extension model.

### Stage 13 — Client Payments
- PaymentTermsRevision.
- PaymentRequest / PaymentSession / PaymentTransaction separation.
- PaymentProviderConnection/Adapter.
- Hosted checkout/tokenization; raw card data not stored.
- Direct Client→Business merchant money flow.
- Refund as separate movement.
- Provider-authoritative webhooks/idempotency/reconciliation.
- Late-payment safe handling.

### Stage 14 — Automations / Notifications
- AutomationDefinition/Revision + persistent AutomationInstance.
- Domain event / scheduled / state-timeout triggers.
- Relevance guard before execution/send.
- NotificationIntent separated from DeliveryAttempt.
- NotificationPolicyRevision, quiet hours/frequency caps.
- Template/hybrid transactional content.
- Human takeover suppresses stale follow-ups.

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

**Status:** Canonical baseline after accepting stages 8–10.

### Added — Stage 8 Agent / Tools / Autonomy

- `ConversationAgent` as the single primary customer-facing agent.
- `AgentRuntime`, `ToolRegistry`, `ToolSetResolver`, `ToolGateway`, `PolicyEngine`.
- `ToolExecutionContext` with server-inherited Workspace/Business/permissions.
- Narrow, typed, versioned tools instead of arbitrary SQL/HTTP/code capabilities.
- Autonomy modes: `AUTO / REQUIRE_CONFIRMATION / ESCALATE / DISABLED`.
- `ApprovalRequest` with frozen action + revalidation before execution.
- Evidence-based action requirements instead of AI self-confidence as authorization.
- Bounded agent loop, explicit stop outcomes and tool budgets.
- `AIToolCall/ToolTrace` separated from business `AuditEvent`.
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
- Quick Start, Assisted Import and Concierge onboarding modes.
- `ImportBatch` / normalization boundary.
- Service discovery, capability/workflow inference, rule/knowledge candidates.
- Conflict detection and adaptive dependency-aware questionnaire.
- Readiness gates per Service instead of a single completion percentage.
- `ConfigurationDraft`, deterministic validation and simulation/historical replay.
- `BusinessConfigurationRelease` as atomic immutable publish manifest.
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
- `AIRun` separate from `AIProviderCall`.
- Initial model-profile mapping: Terra default conversation, Luna cheap/background, Sol rare complex reasoning.
- Structured Outputs as machine-readable contract principle.
- Versioned prompts and output schemas.
- Profile-specific context budgets through ContextBuilder.
- Explicit separation of provider conversation state from canonical application memory.
- Interactive vs background AI workload classes.
- Versioned `EmbeddingProfile` and embedding projections separated from canonical KnowledgeChunk/Portfolio representations.
- AI cost/usage metering requirements per Workspace/task/profile.

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
- structured state выше LLM memory;
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


---

## Исходный файл: 06_MVP_SPEC.md

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
- style/subject/reference extraction;
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
- Approvals;
- Escalations;
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


---

## Исходный файл: 07_DEVELOPMENT_ROADMAP.md

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


---

## Исходный файл: 08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md

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


---

## Исходный файл: 09_IMPLEMENTATION_PLAN.md

# AI Service Manager — план реализации и работы по чатам

**Дата:** 2026-09-10  
**Основание:** Architecture baseline v0.28, ADR-001–274, MVP Spec и Development Roadmap.  
**Статус:** рабочая декомпозиция реализации; программная реализация этим документом не выполнена. Назначения чатов и очереди задач — предлагаемый способ организации работ.  
**Цель:** общий работающий продукт → проверенный Pilot Release Candidate → подключение первого тату-мастера → Commercial MVP.

## 1. Границы этого плана

Это исполнительный план поверх `07_DEVELOPMENT_ROADMAP.md`, а не замена архитектуры. При расхождении приоритет имеют `01_ARCHITECTURE_SPEC.md`, действующие ADR, `06_MVP_SPEC.md`, `07_DEVELOPMENT_ROADMAP.md` и `08_PRODUCTION_DEPLOYMENT_AND_RUNBOOKS.md` в их областях ответственности.

Рабочая версия — v0.28. Старые тексты v0.27 про OpenAI ModelGateway или обязательный Cloud.ru-first не использовать как действующее решение. Перед началом задачи чат проверяет baseline и актуальное состояние репозитория. Более новая согласованная версия имеет приоритет над этим планом.

Уточнение пользователя: сначала строится общий механизм, затем заполняется конфигурация реального мастера. Реальные цены, портфолио, сумма депозита и длительности не являются входным условием программирования универсального механизма. Они обязательны перед публикацией конфигурации и включением соответствующих операций для конкретного бизнеса. Указания «получить данные мастера до M6/M8» в OPEN-079 и roadmap следует применять к публикации его production-конфигурации, а не к началу разработки движков на синтетических данных. Это уточнение включить в следующий согласованный пакет архитектурной документации; данный файл сам не меняет статусы старых ADR.

При этом открыты и инженерные вопросы: стек, поля команд, SQL-ограничения, поведение внешних API, точные model IDs, измеренные задержки и восстановление. Закрываем их в точке использования; не ждём полного разрешения всех будущих вопросов до M0.

## 2. Что должно работать в первой версии

- Один общий multi-tenant backend: Workspace/Business, пользователи, права, изоляция данных.
- Telegram, текст и изображения; ручной ответ владельца и Human takeover/resume.
- Версионируемые услуги, правила, знания, стиль общения и портфолио; минимальный concierge import/review/publish.
- Один ConversationAgent и узкие проверяемые tools поверх обычных domain services.
- RU_AGGREGATOR, PolzaAI — первый кандидат; DIRECT_PROVIDER — официальные API. Общие профили задач, проверяемое переключение маршрутов. GPTunnel — кандидат для сравнения, а не обязательный третий adapter.
- FIXED / CONFIGURED_FORMULA / OWNER_QUOTE; независимый источник продолжительности; согласование Quote.
- Order/ServiceSession, расписание, Hold/Appointment, перенос и отмена.
- NONE / FIXED_DEPOSIT / PERCENT_DEPOSIT / FULL_PREPAYMENT; подтверждение денег через провайдера; возврат с разрешением владельца.
- Отдельный процесс фискализации: профиль, обязательство, статус, подтверждение, ошибки и задачи владельцу. Конкретный live-механизм зависит от правового профиля бизнеса.
- Напоминания и ожидание владельца; честный результат недоступности маршрута.
- Business Console и минимальная Platform Ops Console.
- Устойчивость к повторам, сбоям, устаревшим AI-ответам; наблюдаемость и проверенное восстановление.

В пилот не добавляем полноценную вторую отрасль, новые клиентские каналы, генерацию эскизов, голос, мобильные приложения, внешний календарь, массовую рассылку, многорегиональность или универсальный визуальный конструктор. Способность конфигурировать несколько процессов не равна готовности обслуживать все профессии без проверки.

## 3. Как проверяем гибкость без реального мастера

Создаём минимум четыре синтетических бизнеса/Workspace. Цифры и изображения — только тестовые, с явной маркировкой. Production-публикация тестовых данных запрещена обычной конфигурацией окружения.

| Fixture | Цена | Продолжительность | Предоплата | Что проверяет |
|---|---|---|---|---|
| Tattoo A | Фиксированная | Фиксированная | Фиксированный депозит | Простой полностью автоматический путь |
| Tattoo B | Ограниченная формула | Утверждённое правило | Процент от согласованной точной суммы | Формулы, единицы, округление |
| Tattoo C | Решение владельца | Решение владельца | Без предоплаты | Ожидание человека и независимый путь записи |
| Tattoo D | Фиксированная или формула | Решение владельца | Полная предоплата | Независимость цены, времени и оплаты |

Добавляем варианты RANGE без точной процентной базы, отсутствующих правил, смены прайса, разных часовых поясов, двух клиентов в одном Workspace и клиентов разных Workspace. Все четыре бизнеса используют один код без `if workspace_id == ...` и без изменения алгоритма под fixture.

Для проверки границы универсального Workflow допустим отдельный небольшой synthetic slot-based сценарий на уровне core-тестов. Он не считается выпуском второго IndustryPack и не расширяет acceptance scope пилота. Комбинации настроек проверяем выборочно по существенным инвариантам, не строим бессмысленный полный декартов набор всех опций.

## 4. Организация проекта

Один репозиторий содержит backend modular monolith, Business Console, Platform Ops, схемы/контракты, миграции, инфраструктуру, тесты и AI Evals. API, Worker и Scheduler могут запускаться отдельными процессами одного приложения. Разделение по чатам — распределение инженерной работы, не создание микросервисов.

Предлагаемые области внутри репозитория (точные каталоги фиксируются M0):

| Область | Содержание |
|---|---|
| backend | Domain/application services, adapters, API/Worker/Scheduler |
| frontend | Business Console и Platform Ops с разными правами доступа |
| contracts | API, команды, события и machine-readable schemas |
| migrations | Общая управляемая история изменения PostgreSQL |
| infra | Окружения, контейнеры, IaC, секретные ссылки и deploy |
| tests / evals | Программные проверки, synthetic fixtures, AI regression |
| docs | Архитектура, roadmap, текущие задачи, решения и эксплуатация |

На M0 создаём минимальный рабочий реестр задач (файл в репозитории либо доступный issue tracker), а также краткие правила для AI-исполнителей. Реестр содержит ID, цель, зависимости, ведущий чат, состояние, ветку/commit, проверку и следующий шаг. Не дублируем вручную несколько независимых реестров.

Состояния задач: TODO → IN_PROGRESS → REVIEW → INTEGRATED → VERIFIED; BLOCKED используется только с конкретной причиной. Это статусы выполнения, не LOCKED/OPEN/DEFERRED архитектуры.

## 5. Чаты и ответственность

| Код / название чата | Основная ответственность | Граница ответственности |
|---|---|---|
| C0 — Координация и интеграция | План, контракты между модулями, согласованные ADR, очередь миграций, интеграция и приёмка | Один согласованный рабочий результат; не отдельная реализация всех модулей |
| C1 — Backend и бизнесовые процессы | Auth/application logic, конфигурация/workflow, Request/Assessment/Quote/Order, Scheduling, automations | Определяет бизнесовые команды; работает с C2 над хранением |
| C2 — PostgreSQL и надёжность данных | RLS, tenant-safe FK, миграции, транзакции, allocations, Inbox/Outbox/Jobs, индексы и recovery invariants | Не проектирует всю будущую БД заранее; не меняет смысл бизнесовых переходов без C1/C7 |
| C3 — Telegram и Conversation Engine | Channel adapter, inbound/outbound, turns, управление разговором, delivery state | Не вычисляет цены и не подтверждает платежи |
| C4 — AI, знания и портфолио | ModelGateway/branches, AgentRuntime/tools integration, RAG/Vision/import analysis, schema outputs, стоимость | Не реализует критическую бизнесовую логику внутри prompt; использует команды C1/C7 |
| C5 — Интерфейс владельца и Platform Ops | Login, Inbox, Action Center, Calendar, review/publish, approvals, diagnostics | UI вызывает те же application services; не меняет БД напрямую |
| C6 — Облако, файлы и эксплуатация | Docker/CI/IaC, Yandex-preferred staging/production, ObjectStorage adapter, signed access, secrets, monitoring, backups/deploy | Не владеет логикой платежей и чеков; связывается с C2/C3/C4 по FileObject/contracts |
| C7 — Платежи, фискализация и SaaS billing | Client payments, PaymentTerms, YooKassa adapter, refund/reconciliation, fiscal obligations, позднее paid subscriptions | Деньги/чеки/подписка — разные состояния; не обходит Scheduling при подтверждении записи |
| C8 — Проверка качества и безопасности | Независимая проверка integration/E2E/RLS/recovery, AI Evals, release gate evidence | Тестирование начинается с M0; автор каждого модуля тоже пишет нужные тесты |

Не нужно запускать все девять чатов одновременно. Начинаем с C0, C1/C2 и по необходимости C6; C8 задаёт критерии первых проверок. Остальные подключаются по milestone. Если один человек последовательно переносит задания между чатами, это такой же допустимый способ работы.

Облачное хранилище и фискализация находятся в разных чатах: у них разные контракты и зависимости. Чат БД обслуживает текущую работающую функцию; он не выдаёт законченную «всю базу» за несколько этапов до backend.

## 6. Полная последовательность до пилота

Ведущий чат отвечает за сбор результата, остальные участвуют в своих границах. Каждый milestone включает минимальный нужный UI, тесты, авторизацию, Audit/telemetry и ошибки; M10/M12 завершают их, а не начинают с нуля.

| Этап | Ведущий / участие | Результат | Условие завершения |
|---|---|---|---|
| M0 — Старт инженерной работы | C0/C1; C2/C5/C6/C8 | Зафиксированный стек и структура репозитория, локальный запуск, контейнер, миграции, CI и fixtures | Чистое окружение запускается по инструкции; реальный PostgreSQL test и сборка проходят |
| M1 — Пользователи и tenant isolation | C1/C2; C5/C8 | Login/session, Workspace/Business/roles, RLS/FK/Audit; местное ядро Subscription/Entitlements | Владелец входит; Workspace A не читает/меняет B; runtime не обходит RLS; нет paid billing зависимости |
| M2 — Telegram и ручной Inbox | C3; C1/C2/C5/C6/C8 | Webhook→Inbox→Message, private images, Outbox, ручной ответ | Реальное тестовое сообщение попадает в верный Workspace; ответ доходит; дубликаты и restart безопасны |
| M3 — Управление разговором | C3; C1/C2/C5/C8 | Turn aggregation, ConversationState, control generation, takeover/resume, Escalation | HUMAN блокирует новые AI-команды/ответы; устаревший worker не действует; in-flight send виден |
| M4 — AI только с query tools | C4; C1/C3/C6/C8 | Gateway, две выбранные ветви/adapters, schemas, ContextBuilder, run traces и cost | Synthetic dialogue и разрешённые live API проверки проходят; смена ветви не меняет домен; нет mutation tools |
| M5 — Конфигурация, знания и Vision | C1/C4; C2/C5/C6/C8 | Services/Rules/Workflow revisions, draft/validation/release, RAG/Portfolio, DurationCase, synthetic TattooPack | Разные fixtures работают одним кодом; знание имеет источник; чужие данные не извлекаются; отсутствующие правила выявляются |
| M6 — Запрос, оценка и согласование | C1; C2/C4/C5/C8 | PricingEngine, approved Assessment, QuoteAcceptance, Order/Session, ApprovalRequest | Fixed/formula/Owner Quote проходят; AI не назначает деньги/время сам; повторное согласие не создаёт второй заказ |
| M7 — Календарь и запись | C1/C2; C4/C5/C8 | Rules/blocks/buffers, Offer/Hold/Allocation/Appointment, cancel/reschedule, NONE path | Один слот не отдаётся двум; перенос с самопересечением корректен; без предоплаты запись не требует fake payment |
| M8 — Платежи и фискальный процесс | C7; C1/C2/C4/C5/C6/C8 | Checkout, verified provider events, obligations/refunds/reconciliation, fiscal profile/receipt tasks | Sandbox подтверждает согласованный платёж и запись; late/duplicate/UNKNOWN безопасны; fiscal failure видим |
| M9 — Напоминания и ожидания | C1/C3; C2/C5/C7/C8 | Persistent automations, limits/quiet hours, owner waits, ROUTE_UNAVAILABLE | Отмена/ответ/takeover инвалидируют follow-up; restart не дублирует действие; недоставка видна |
| M10 — Операционная полнота UI | C5; C0/C1/C3/C4/C7/C8 | Полный минимальный Business Console/Ops для уже реализованных функций | Повседневную работу и разбор ошибок можно выполнить через UI/узкие команды без ad-hoc SQL |
| M11 — Сквозная сборка и feature freeze | C0/C8; все | Golden Journeys A–J и v0.28 variants | Все системы проходят цепочки на одном release candidate; новые функции откладываются |
| M12 — Готовность релиза | C0/C8/C6; все | Security/reliability/AI gates, restore drill, manifests/rollback/runbooks | Технические gates подтверждены; реальные business/privacy/fiscal gates применены перед соответствующим live-включением |

### M0: что решаем один раз в самом начале

1. Проверяем репозиторий/доступ. Если его ещё нет, создаём общий проект; не предполагаем автоматически общий диск между чатами.
2. Выбираем и фиксируем один backend язык/framework, frontend, query/ORM подход, миграции, runner тестов, package/build tooling. Сверяем актуальную поддержку PostgreSQL/RLS/pgvector/async/tool schemas. Этот план не выдаёт ещё не выбранный стек за LOCKED.
3. Фиксируем базу реализации: действующие инварианты v0.28 и scope, конкретный стек, открытые инженерные задачи с milestone. Architecture Freeze v1.0 может сохранять явно OPEN значения бизнеса и release configuration; freeze не утверждает production readiness.
4. Поднимаем API/Worker/Scheduler skeleton, PostgreSQL и frontend shell; секреты не входят в код.
5. Добавляем CI со сборкой, одной существенной интеграционной проверкой PostgreSQL и проверкой миграций. Контейнер должен воспроизводиться.
6. Создаём реестр задач, правила распределения файлов/миграций и synthetic fixtures A–D. Цены fixtures — тестовые данные, не production defaults.

### Разложение M1–M12 на выдаваемые задачи

| ID | Ограниченная задача | Ведущий | Зависимость |
|---|---|---|---|
| M1.1 | Tenant schema, DB роли, context/RLS и cross-tenant тесты | C2 | M0 |
| M1.2 | Auth/session/membership/application authorization и login UI | C1 + C5 | Контракт M1.1 |
| M1.3 | Местные Plan/Subscription/Entitlements и Audit | C1 | M1.1 |
| M2.1 | Нормализованные Channel events и durable Inbox/Outbox/Jobs kernel | C3 + C2 | M1 |
| M2.2 | ObjectStorage/FileObject контракт, private image path и авторизация выдачи | C6 + C3 | M1, контракт M2.1 |
| M2.3 | Telegram adapter, тестовое подключение, retry/UNKNOWN/capabilities | C3 | M2.1, M2.2 |
| M2.4 | Inbox и ручной ответ из Console, end-to-end демонстрация | C5 + C3 | M2.3 |
| M3.1 | Turns/versions/control generation/takeover/resume | C3 | M2 |
| M3.2 | Escalation и видимость ожидания/неопределённой отправки | C3 + C5 | M3.1 |
| M4.1 | Typed Gateway/profile/routing/run contracts и fake adapters | C4 | M3 |
| M4.2 | Выбранный агрегатор/direct adapter, synthetic API probe и переключение | C4 | M4.1; API-доступ для реальной проверки |
| M4.3 | Query-only Agent, schema validation, trace/cost и первая eval suite | C4 + C8 | M4.1–2 |
| M5.1 | Service/Rule/Workflow/Draft/Release и configuration validation | C1 | M4 contracts |
| M5.2 | Knowledge import/revisions/RAG и private Portfolio/Vision | C4 | M5.1, image path M2 |
| M5.3 | Review/publish UI, synthetic configurations и DurationCase ingestion | C5 + C1/C4 | M5.1–2 |
| M6.1 | Request/provenance и Assessment/Duration authority | C1 | M5 |
| M6.2 | Fixed/bounded-formula/Owner price + calculations | C1 | M6.1 |
| M6.3 | QuoteAcceptance/Order/Session/ApprovalRequest и owner action UI | C1 + C5 | M6.2 |
| M6.4 | Узкие mutation tools с policy/evidence/client-scope/idempotency | C4 + C1 | Проверенные M6.1–3 |
| M7.1 | Availability/blocks/buffers и DB overlap proof | C1 + C2 | M6 |
| M7.2 | Hold conversion, NONE booking, cancel/self-overlap reschedule | C1 + C2 | M7.1 |
| M7.3 | Calendar UI, scheduling tools и concurrent E2E | C5 + C4/C8 | M7.2 |
| M8.1 | PaymentTerms/typed obligation/checkout intent/provider adapter | C7 | M7; контракт согласования M6 |
| M8.2 | Callback verification/reconciliation/UNKNOWN/late/overpay/refund | C7 | M8.1 |
| M8.3 | Fiscal profile/obligation/evidence/deadline и manual/provider strategy | C7 | M8.1; live provider только после выбора профиля |
| M8.4 | Payment/fiscal UI и полный sandbox journey | C5 + C7/C8 | M8.2–3 |
| M9.1 | Persistent automation/relevance/schedule/invalidation | C1 + C2 | M8 |
| M9.2 | Notification delivery/closed window/owner waits/HUMAN policy | C3 + C1/C5 | M9.1 |
| M10.1 | Недостающие owner review/config/connection/usage функции | C5 | M1–M9 UI |
| M10.2 | SupportAccessGrant/Ops diagnostics/DLQ/replay и ограничения | C5 + C1/C2 | Диагностика из M1–M9 |
| M11.1 | Сквозные сценарии на общем commit, регрессии, feature freeze | C0 + C8 | M10 |
| M12.1 | Security/AI/cost/latency/concurrency release gates | C8 | M11 |
| M12.2 | Staging restore, deletion state, old-worker fencing, replay и rollback | C6 + C2/C7/C8 | M11; окружение/backup |
| M12.3 | ReleaseManifest, runbooks, operator alerts, Pilot RC | C0 + C6 | M12.1–2 |

У каждой строки перед началом появляется точный scope файлов и критерий проверки. Таблица — не разрешение запускать все строки одновременно. Например M4 fake tests не подтверждают работу настоящего API, а M8 simulator не подтверждает выпуск реального чека.

## 7. Ранние проверки внешних зависимостей

Данные конкретного мастера можно отложить; техническую совместимость внешнего API нельзя откладывать до финала.

| Когда | Что проверить | Что можно сделать без production-клиента |
|---|---|---|
| M0–M2 | Telegram connected bot, реальные права/события/ручные ответы | Собственный контролируемый test account/connection |
| M0–M2 | PostgreSQL extensions/RLS и private object access | Local PG, dev/staging cloud с тестовыми файлами |
| До серьёзного расширения M4–M5 | AI schemas/tools/Vision/embedding и latency/cost | Synthetic текст/разрешённые тестовые картинки и API-ключ |
| До большой интеграции M8 | YooKassa sandbox, event verification, checkout/retry | Test merchant/provider sandbox при наличии доступа |
| До реальных платежей | Фискальный профиль/ответственность/подтверждение и merchant eligibility | Общий механизм/симулятор заранее; actual live strategy после профиля бизнеса |
| До Pilot RC | Restore/rollback/старые workers и удаления после backup | Staging drill с тестовыми данными и внешними effect simulators |

При отсутствии ключей можно написать интерфейс и fake adapter, но статус «реальная интеграция проверена» остаётся BLOCKED конкретным доступом. Покупка тарифов, новые расходы и production-включение не подразумеваются выдачей задачи на код.

## 8. Что допускается делать параллельно

- В M0/M1: DB foundation, frontend shell, инфраструктурные заготовки и критерии тестирования после согласования стека/контрактов.
- В M2: storage adapter и Inbox UI относительно стабилизированного контракта сообщения; Telegram adapter после durable-event контракта.
- В M4/M5: AI adapter probes, configuration domain, review UI и synthetic eval corpus при согласованной форме данных.
- В M6/M7: UI относительно versioned API и тесты инвариантов; domain migrations идут через одну интеграционную очередь.
- В M8: payment UI и fiscal obligation model по согласованным контрактам; реальное автоматическое подтверждение Appointment ждёт стабильного M7.

Не строим всю БД, затем весь backend, затем весь AI и только потом соединяем. В каждом milestone собираем тонкий работающий сценарий через все нужные слои.

## 9. Передача работы между чатами

Чаты не считаются автоматически осведомлёнными о чужих сообщениях, локальных файлах или последних изменениях. Project sources помогают передавать архитектуру, но текущий код и миграции определяются конкретным repository commit.

Перед каждой задачей передаём:

1. ID задачи и её цель.
2. Baseline архитектуры и применимые ADR/разделы.
3. Репозиторий/branch/commit, от которого начинать; если доступа нет — точные нужные файлы/patch и явное ограничение.
4. Контракты зависимостей и уже выполненные задачи.
5. Разрешённую область файлов; общие entrypoints/миграции согласует C0.
6. Критерии результата и проверки.

Рабочая ветка/изолированный checkout на одну задачу. Если технически несколько чатов редактируют одно дерево, изменения сериализуются; нельзя одновременно менять одни файлы вслепую. Параллельные миграции не переименовываем и не применяем независимо: C2/C0 интегрируют их порядок и проверяют upgrade на общей ветке.

После задачи исполнитель возвращает patch/commit, изменения контрактов/миграций, команды и результаты проверок, ограничения, открытые решения и следующий шаг. C0 принимает результат, разрешает конфликты, запускает подходящий integration smoke и обновляет общий task register. Только после этого зависимый чат начинает работу от нового общего commit.

До интеграции не распространять результат как «готовую новую архитектуру». Новые domain decisions фиксируются через ADR; обычная реализация принятого контракта не требует повторного обсуждения каждого поля.

## 10. Готовый общий текст для специализированного чата

```text
Мы реализуем AI Service Manager по согласованному baseline v0.28 или более новой явно принятой версии.
Сначала прочитай 01_ARCHITECTURE_SPEC.md, применимые ADR из 02_ARCHITECTURE_DECISIONS.md,
06_MVP_SPEC.md, 07_DEVELOPMENT_ROADMAP.md и относящиеся к задаче пункты 04_OPEN_QUESTIONS.md.
09_IMPLEMENTATION_PLAN.md описывает распределение задач, но не отменяет каноническую архитектуру.

Твоя область: [C-код и название]. Текущая задача: [ID и цель].
Репозиторий и исходный commit: [указать]. Контракты/зависимости: [указать].
Область файлов: [указать]. Критерии результата: [указать].

Выполни ограниченную задачу до рабочего результата в общем проекте.
Используй synthetic business configurations, без данных конкретного мастера и без персональных code forks.
Цена, продолжительность, расписание и деньги определяются domain services, не свободным решением LLM.
Новые миграции и изменения общих контрактов явно перечисли для интеграции.
Не переписывай стек/принятые решения и не строй функции вне текущего milestone.
Если нет доступа к коду/ключам, явно скажи, что не проверено; не выдавай mock за live integration.

В конце верни commit/patch, что реализовано, как проверено, изменения контрактов/миграций,
оставшиеся ограничения и следующий шаг. Не объявляй задачу INTEGRATED до приёмки общей веткой.
```

### Дополнение для C0

```text
Ты координируешь реализацию. Веди один task register и общие контракты/миграции.
Выдавай небольшие задачи с ID, commit, зависимостями и критериями результата.
Проверяй совместимость результатов разных чатов и принимай их в общий проект.
Не меняй принятую архитектуру молча; открытые значения мастера не блокируют synthetic разработку.
```

### Первое задание для запуска проекта

```text
Начинаем M0 AI Service Manager. Основание — baseline v0.28 и 09_IMPLEMENTATION_PLAN.md.
Цель: общий запускаемый репозиторий с backend/frontend shells, PostgreSQL, миграциями,
Docker/локальным запуском и CI. Реальные данные мастера пока не нужны.
Сначала проверь наличие и доступ к репозиторию. Выбери и обоснуй один конкретный стек,
совместимый с PostgreSQL/RLS/pgvector, транзакциями, async jobs, typed schemas и тестами;
зафиксируй его как реализационное решение и создай инженерный каркас.
Подготовь правила работы по чатам, task register и первые задачи M1.1–M1.3.
Не создавай заранее таблицы всех будущих модулей. Проверка M0: чистый локальный запуск,
успешная миграция, существенный real-PostgreSQL integration test и воспроизводимая сборка.
Если репозитория/доступа нет, сначала подготовь локальную структуру и точную инструкцию подключения,
не утверждая, что общий репозиторий уже доступен другим чатам.
```

## 11. Общая Definition of Done

Задача считается готовой к интеграции, когда применимые к ней условия выполнены:

- Работает конкретный сценарий, а не только interface/class stub.
- Нет обхода tenant/Client authorization, policy и domain state.
- Существенные constraints/конкуренция/идемпотентность проверены там, где затрагиваются.
- Есть понятные failure states, Audit/Usage/telemetry без лишних данных.
- Миграции воспроизводимы и совместимы с релизным процессом.
- Пользователь/оператор видит необходимые действия/ошибки через минимальный UI.
- Нужные тесты/evals выполнены; не проверенные live зависимости перечислены отдельно.
- Контракт и task status обновлены; результат воспроизводим от указанного commit.

Объём тестов соразмерен риску. Денежные/tenant/scheduling/recovery изменения требуют сильных проверок; косметическое изменение UI не требует полного платного AI benchmark. Приёмка модуля не заменяет последующий E2E всей цепочки.

## 12. Pilot RC, подключение мастера и коммерческая версия

### Gate A — общий технический каркас (M0–M4)

Можно войти, изолированно принять сообщение/изображение, ответить вручную, управлять HUMAN/AI и выполнить ограниченный AI-run. Первый ощутимый продуктовый результат — M2: Telegram → Inbox → ручной ответ.

### Gate B — функциональный кандидат (M5–M11)

Несколько synthetic бизнесов на одном коде проходят: сообщение → знание/анализ → запрос → цена/решение владельца → согласование → время → предоплата или NONE → запись → уведомление. Здесь уже видна практическая гибкость конфигурации.

### Gate C — проверенный технический Pilot RC (M12)

Контейнер/schema/config/model/tool/eval revisions зафиксированы. Безопасность, устойчивость и restore/rollback подтверждены. Отсутствующие реальные BusinessConfig/Privacy/Fiscalization inputs остаются явно неподтверждёнными: технический RC не называется полностью готовым live Pilot, пока соответствующие условия не выполнены.

### Gate D — первый live Pilot

Теперь получаем реальные услуги, цены/формулу, сумму фиксированного депозита, часы/длительности/ограничения, разрешённое портфолио/знания, legal/fiscal profile и support expectations. Это отдельный BusinessConfigurationRelease, а не новая ветка программы под мастера.

Проверяем профиль на representative/synthetic сценариях, владелец утверждает конфигурацию. Подключение по runbook: manual Telegram → shadow/query AI → безопасные ответы → расписание → реальные платежи только при готовом fiscal gate → automations. Непроверенные возможности остаются выключены для этого бизнеса. При выявлении универсального пробела оформляем общую доработку, а не скрытый tenant-specific exception.

### M13–M16 — Commercial MVP

| Этап | Что делаем | Результат |
|---|---|---|
| M13 | Анализируем первые реальные диалоги, исправления, задержки владельца, стоимость; добавляем регрессии | Исправляем доказанные проблемы продукта |
| M14 | Повторяем onboarding нескольких независимых Tattoo Businesses, автоматизируем повторяемые шаги | Подключение без code fork и постоянной инженерной ручной работы |
| M15 | Включаем оплату SaaS владельцем: checkout, tokenized method, Subscription events, invoice, grace/service modes | Платная подписка отделена от денег клиентов мастера |
| M16 | Укрепляем support/deploy/onboarding/privacy/fiscal/economics; проверяем несколько paying Workspaces | Commercial RU Tattoo MVP |

Порядок M13–M16 соответствует действующему roadmap. Широкая отраслевая/канальная экспансия следует после доказанной повторяемости. Календарные сроки ставим после M0 и первых интегрированных задач, когда известны стек, доступы и фактическая скорость; milestone не равен одному чату или одному дню.

## 13. Что можно начать прямо сейчас

Начать C0 с приведённого задания M0. Следующая цель — M1, затем M2. Не ждать прайса/портфолио/суммы депозита первого мастера. Подготовка реальных аккаунтов API/cloud по мере необходимости идёт параллельно, без подмены неизвестных production-настроек тестовыми значениями.
