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

Legacy spelling of `AIRun`; use `AIRun` canonically. One logical task can include multiple provider calls and tool continuations.

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
Подключённый transport/account/token route для конкретного Business.

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
Запрос на visual operation с purpose/inputs/constraints, без business-state authority.

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
Запись о tool request/execution path AI; не равна AuditEvent.

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
Отдельный AI workflow для анализа бизнеса и подготовки configuration candidates/draft. Не является ConversationAgent и не публикует production configuration самостоятельно.

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
Компонент, который выдаёт Agent минимальный allowed tool set по WorkflowStep, Service capabilities, actor permissions и policy.

## Workflow Archetype
Общий шаблон семейства бизнес-процессов, например Slot-Based, Custom Consultative, Event-Based, Onsite, Custom Production, Recurring Session и Project Delivery.

## WorkflowInstance
Runtime instance конкретной WorkflowRevision для ServiceRequest/Order process.

## WorkflowRevision
Immutable опубликованная версия WorkflowDefinition, используемая конкретной ServiceRevision/WorkflowInstance.

## WorkflowStepInstance
Runtime состояние отдельного шага WorkflowInstance. Не заменяет domain entity/state.

## ValidationIssue
Результат deterministic validation draft/release с severity ERROR/WARNING/INFO.


## AutomationDefinition / AutomationRevision
Versioned правило того, когда или при каком domain event/state timeout должна возникать автоматическая операция.

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
Persistent reservation части hard quota до запуска дорогой side-effect operation; consuming/release предотвращает concurrency overspend.

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
Описание raw metric (tokens, provider cost, images, storage и т. п.).

## MeterDefinition
Правило преобразования raw usage в commercial/billable product unit.

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
Internal economic guard that can warn/throttle/block optional expensive work but cannot lower safety-critical quality.

## EvalCase
Versioned AI-evaluation scenario with structured state/context, allowed/forbidden outcomes, expected tool behavior and risk labels.

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
Implementation completeness level supporting broader post-MVP complexity beyond first pilot.

## Technical Spike
Short bounded proof-of-capability used to validate a risky external/DB/AI assumption and produce a decision/test/constraint; not itself production implementation.

## Vertical Slice
End-to-end implementation increment spanning the persistence/domain/API/UI/integration/test behavior needed for one usable capability.

## Application Release
Immutable deployed application/container version, distinct from AI configuration and tenant BusinessConfigurationRelease.

## Break-Glass DB Access
Exceptional time-bound/audited engineering access to production data for emergency diagnosis/repair; not normal operations.

## Deployment Observation Window
Monitored period after rollout during which critical health signals are actively checked before considering release stable.

## Kill Switch
Narrow operational control that pauses a specific subsystem/capability (e.g. AI auto-send or new payment sessions) without unnecessarily disabling unrelated essential functions.

## Platform AI Configuration Release
Versioned platform mapping of model/prompt/tool/policy behavior that can be promoted/rolled back independently from application binary and Business configuration.

## ReleaseManifest
Deployment artifact describing exact application/container/schema/AI/platform/eval versions and source/CI provenance of a production release.

## Repair Command
Controlled, scoped, validated and preferably idempotent/dry-run-capable production data repair operation, used instead of ad-hoc SQL mutation.

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
