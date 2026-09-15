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
