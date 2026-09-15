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

