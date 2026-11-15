# M5 — настройки бизнеса, знания, Vision и портфолио

Дата: 2026-11-12. Ведущий: C0. Статус исполнения — только в
[TASK_REGISTER](../TASK_REGISTER.md). Решение по объёму:
[IMPL-005](../decisions/IMPL-005-m5-pilot-knowledge.md) — ACCEPTED / LOCKED C0.

## CURRENT — M5.2C → C4 / IN_PROGRESS / 2026-11-15

Единственная активная задача **C4-M5.2C-VISION-PORTFOLIO-R1**.
Ведущий C4; C1 — owner API/domain, C2 — схема/RLS/миграция, C5 — минимальный UI.
Участие последовательно в рамках одной ветки и одного PR, без параллельной записи
общих файлов. C6 HOLD; отдельные operator/VM задачи не выданы. C3/M5.2D и M5.3
не начинать. Этот блок заменяет завершённое поручение M5.2B.

### Результат для пользователя

Приложение анализирует доступное изображение из текущего разговора и отделяет
наблюдаемые признаки от неизвестного. Мастер загружает собственные работы в
приватное портфолио, проверяет описание и разрешение показа, публикует и отзывает.
По клиентскому референсу он видит небольшой набор подходящих подтверждённых работ
с причинами сходства и источниками. Это необходимая часть принятого Tattoo-пилота;
отложить её можно только с явным исключением Vision/подбора из результата M5.

Клиентское фото, inspiration и работа мастера не смешиваются. Цена, подтверждённая
длительность и допустимость заказа из сходства не выводятся. Отправка изображения
клиенту остаётся отдельной M5.2D; этот срез её не реализует и не заявляет.

### Repository, base и проверенная зависимость

- Repository: `Elefesys/ai-service-manager`; существующая branch
  `c4/m5-2c-vision-portfolio-r1`; integration target `main`.
- **Accepted application base: `70804866f6838f77c12bd281febae47887559d75`.**
  Tree: `a6ee68b5a6b0cd2091b4cecc89614bada4db2585`.
- PR49/M5.2B merged. Tree совпадает с принятым C0 final head
  `3a82973cde8696330238fc33043d4d43731bb670`.
  [Review C0](https://github.com/Elefesys/ai-service-manager/pull/49#pullrequestreview-5909754499)
  закрывает оба publication finding.
  [Post-merge CI43693059853](https://github.com/Elefesys/ai-service-manager/actions/runs/43693059853):
  push/main, attempt1, **12/12 SUCCESS**, все jobs completed.
  Повторять этот CI, аудит M4 или capability probe M5.2A без новой причины не нужно.
- C0 сохранил эту выдачу одним docs-only commit поверх accepted base в указанной
  ветке. Exact assignment SHA/tree — из закреплённой ссылки C0 и Git; сохранить
  commit в ancestry. Assignment не является реализацией или новым CI PASS.
- Читать AGENTS, этот CURRENT, IMPL-005, применимые границы IMPL-004;
  Spec §2.11.1/3.10–3.11/6.12/6.14–6.15/7.12 и
  ADR-030–034/051/052/075/076/148/174/175/260/261/265–267.
  Одиннадцать project sources сверены с SOURCE_MANIFEST; исходники не пересмотрены.

### Установленные границы кода и короткий контракт

В accepted main image metadata/read permits связаны с message/conversation;
это не owner upload capability. `Message` остаётся text-only, ContextBuilder
не заявляет прочитанные pixels. Capability probe — отдельный synthetic CLI,
его нельзя включить как application service. M5.2B EmbeddingClient допускает
только DISABLED/CONTROLLED MockTransport; live Vision/embedding runtime этим
заданием не включается. Эти ограничения требуют узкого нового контракта,
а не изменения старых DTO/допусков задним числом.

До SQL/основной реализации C4/C1/C2 фиксируют короткий контракт здесь или в PR:
asset/version/analysis/portfolio revision/build, owner команды и ошибки,
trusted client-media binding, read DTO, invalidation и numeric limits.
C2 подтверждает слот миграции и минимальный набор таблиц/capabilities;
физическая схема заранее не объявляется принятым архитектурным решением.
Отдельный planning PR и универсальный media/job registry не нужны.

1. **Owner upload и private bytes.** Отдельный bounded owner upload/review
   с текущими session/OWNER/CSRF/Origin, idempotency и expected version.
   Сервер выдаёт узкую capability, storage key не выбирает клиент/LLM.
   Переиспользовать private storage и full-decode validator: JPEG/PNG/WebP,
   single frame, до10 MiB, сторона≤8192, pixels≤20M; не расширять лимиты.
   Авторизовать чтение preview/анализа до выдачи данных. Не создавать фиктивные
   Telegram messages/conversations/clients; не превращать inbound permit в
   blanket owner/service access. Нет public buckets, remote URL import или
   model-supplied URL fetch. Upload/finalize/retry/crash и cleanup своих
   незавершённых объектов имеют durable outcome, без удаления чужих/принятых.
2. **Vision operation.** Версионированный server-issued permit закрепляет
   Workspace/Business и для клиентского референса Client/conversation/message,
   file/content hash/version, профиль/preprocessing и текущие guards.
   Не более одного доступного current image на операцию; выбор и пропуски
   детерминированы и видимы. Проверяется именно decoded pixel input, caption
   не заменяет изображение. Новый synthetic image profile — явный opt-in,
   EVAL_ONLY; старый text-only admission не предоставляет image access.
   Logical route соответствует M5.2A: Polza/OpenAI/`openai/gpt-4o-mini`,
   PNG256×256/detail low, с описанными EXIF/resize/metadata правилами.
   Исходные bytes сохраняются private; derivative имеет свой hash/version.
   Production data/route approval отсутствует. DISABLED/0 provider HTTP по
   умолчанию; CONTROLLED wire проверяется только через injected MockTransport.
   Не импортировать probe CLI/его approval state в application runtime.
3. **Analysis и достоверность.** Новый strict versioned Vision result:
   предмет/стиль/наблюдаемые детали/неопределённость и provenance.
   Не выводить сантиметры без масштаба, деньги, время, медицинскую пригодность,
   право выполнить заказ или авторство работы. Инструкции в картинке/описании
   остаются данными. Unavailable/unsupported/timeout/invalid/UNKNOWN — явные
   результаты, без ложного «я рассмотрел фото». Удалённая/заменённая версия
   инвалидирует analysis, search projection и зависимый ещё не отправленный
   ответ. `MEDIA_REPLACED_UNAVAILABLE` сохраняется; refetch не добавляется.
4. **Portfolio и публикация.** Canonical item/revision отдельно от AI analysis
   и text embedding projection. Явные MY_WORK / CLIENT_REFERENCE / INSPIRATION,
   происхождение, owner confirmation, разрешение показа и service/атрибуты.
   Клиентский reference не копируется в общую базу и не становится MY_WORK
   через AI classification либо удобный переключатель. Для клиентского
   Portfolio evidence допустимы только подтверждённые MY_WORK с явным показом.
   Vision suggestions — draft до owner review. Подготовленный совместимый набор
   включается в immutable active release атомарно; error/UNKNOWN сохраняет
   предыдущий набор. Все legacy configuration/knowledge publish/rollback paths
   либо явно сохраняют выбранные допустимые наборы, либо получают закрытый отказ;
   незаметное отключение knowledge или portfolio после reload запрещено.
   После последнего revoke/delete доступна явная публикация пустого portfolio
   без фиктивного материала и без нового Vision/embedding расхода.
5. **Подбор и scopes.** Наблюдения/описание референса → bounded text query →
   structured/service filters + keyword + exact pgvector с действующим
   `polza_openai_text_embedding3small_1536_cosine_v1`.
   Profile/dimensions/preprocessing query и index должны совпадать.
   Начальный максимум8 nondeleted portfolio items/Business и top3 results;
   прочие bytes/tokens/deadline/cost limits закрепить в коротком контракте до кода.
   PORTFOLIO отделён от BUSINESS_KNOWLEDGE и private CLIENT_HISTORY.
   Trusted Business/Client берётся из server binding, не из model argument.
   Общие разрешённые работы бизнеса доступны его клиентам; личные references
   другого Client недоступны даже внутри Workspace. Возврат ограничен
   item/revision/analysis refs, подтверждёнными признаками и причиной сходства,
   без storage keys, credentials и служебных URLs; EMPTY допустим.
6. **Runtime/currentness.** Новый versioned context/read/prompt path использует
   analysis и разрешённые portfolio evidence; существующие saved runs/DTO/prompt
   остаются совместимыми. Владелец видит анализ и найденные работы для выбранного
   разрешённого разговора в обычном UI. Не реализовывать только standalone demo.
   Новый анализ, read, MODEL/FOLLOWUP, CANDIDATE/COMMIT/SEND проверяют media version,
   portfolio publication/permission и прежние fences. HUMAN/Resume, OWNER
   reconciliation, observation barrier, Telegram rights и UNKNOWN/no-resend
   сохранены. Publication/revoke/send admission имеют согласованную сериализацию;
   DB locks не держатся через storage/provider HTTP. Уже начатый внешний эффект
   не объявляется отозванным. Не добавлять sendPhoto или обход через manual send;
   текст ответа не утверждает, что изображение уже показано клиенту.
7. **Finite accounting/restart.** Conversation budget остаётся до2 text calls/
   1 READ; отдельно максимум1 Vision POST/новый analysis и1 embedding QUERY POST
   на запрос подбора. Existing knowledge и portfolio query должны разделять
   конечный бюджет операции, без скрытого удвоения. Indexing имеет конечный plan,
   тот же embedding profile и явные reservations. До внешнего действия —
   durable reservation/intent; outcome/accounting после него фиксируется и при
   потере currentness, apply требует свежего допуска. UNKNOWN не повторяется
   после restart, смены request key или нового AIRun для того же analysis.
   Нет незаметных retries/fallback. Старые holds/receipts не изменяются.
   Общие6144 business/8192 context bytes и runtime gate budgets не увеличивать.
8. **Минимальный owner UI.** Загрузить/увидеть private preview и происхождение,
   увидеть анализ либо понятный unavailable, исправить draft, подтвердить
   MY_WORK/show permission, publish/revoke/delete и просмотреть matches.
   Ежедневные действия не требуют SQL/ручного JSON. Preview/publish сами не
   запускают скрытые model calls; действие анализа обозначено отдельно.
   Нет отдельного кабинета, bulk import или нового dashboard.

### Короткий контракт C4/C1/C2 — до SQL / 2026-11-15

Согласован ограниченный LOCAL/TEST контракт. C2 проверил Git-цепочку0001–0020,
отсутствие0021 и неизменность applied исходников; слот0021←0020 свободен.
Это source evidence, не выполненная миграция или новое архитектурное решение.

| Область | Контракт |
|---|---|
| Private source | Owner Asset/immutable Version содержит один server-issued upload intent; origin MY_WORK/INSPIRATION неизменен. Client reference — отдельный binding реальных Client/conversation/message/current file, не owner asset и не кандидат promotion в MY_WORK. Storage keys/tickets наружу не выдаются. |
| Upload | JSON init/finalize/abandon и один canonical PUT bytes по asset/version/intent. JPEG/PNG/WebP,10MiB/8192/20M и прежний full decode; максимум8 nondeleted assets/items и2 pending uploads/Business, intent120s, operation45s. Lost ACK — HEAD/GET того же key/hash, без повторного uncertain PUT. Cleanup сохраняет tombstone для late PUT; accepted-asset purge получает отдельный fresh owner delete permit, не staging cleanup. |
| Vision | Новый vision_result_v1 и новый EXIF-orient/white-letterbox/RGB PNG256/strip-metadata profile. Subject/style/details/uncertainty остаются derived data; scale UNKNOWN, без authority над price/time/eligibility/authorship. Один POST на source/version/hash/profile identity; key/run/session/generation не входят в identity и не обходят UNKNOWN. Completion/accounting отдельно от fresh apply. |
| Finite admission | Новый узкий portfolio_ai_sessions anchor, не registry: exact synthetic EVAL_ONLY profile, Business/server actor либо real conversation, ≤900s/4 calls/10RUB. Vision/query/index/v5 text суммируются под row lock; UNKNOWN сохраняет hold. Vision≤30s/512 output tokens/65536 response bytes/393216 wire/262144 derivative bytes, reserve≤3.89RUB. Старый text-only session не даёт image доступа. DISABLED/0 provider HTTP default; CONTROLLED только exact injected MockTransport. |
| Portfolio/search | Canonical Item/Revision отделены от analysis и build projection. Shared evidence — только confirmed MY_WORK/show_permission. Text projection≤512 UTF-8 bytes/item; один INDEX batch≤8, ≤1 POST/3 HTTP/.08RUB. Весь serialized wire≤8192 проверяется до reservation; controls кроме TAB/LF запрещены, escaping overflow даёт WIRE_LIMIT без скрытого второго batch. Top3; visible analysis≤1024 и matches≤2048 bytes. |
| Composite publish | Явно выбранные READY KB build/version и Portfolio build/version, включая empty; KB null только если прежней KB связи нет. Один immutable release/atomic activation. Legacy config/knowledge publish/rollback при current/target Portfolio link получают PORTFOLIO_BUILD_REQUIRED/409 после старого successful receipt replay. Revoke/delete/replacement немедленно исключают dependent reads/unsent effects; empty publish не резервирует AI calls. |
| Runtime v5 | Новые versioned context/read/prompt, старые DTO/runs закрыты. Один server query≤1024 UTF-8 из current text и exact applied image observations; один1536/cosine vector отдельно используется в BUSINESS_KNOWLEDGE и PORTFOLIO. Старый eager v4 QUERY не запускается дополнительно. ≤2 text calls/1 READ, общие business6144/context8192 и прежние run deadlines/cost budgets сохранены. Все MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND fences проверяют media/portfolio pins. |

Новые client-reference MODEL/semantic операции сохраняют AI-mode/Resume/barrier
guards. Manual MODEL при HUMAN остаётся OPEN и этим контрактом не включается;
owner может авторизованно просмотреть доступный derived draft без нового POST.
Owner asset analysis без conversation имеет отдельный OWNER permit. Actor не
выбирается DTO. Физическую схему C2 реализует только под эти операции, без fake
Job/AIRun/messages и без универсальных media/job/provider registries.

### Решение C0 — upload HTTP boundary / ACCEPTED FOR IMPLEMENTATION / 2026-11-15

Запрос C4 из `9bd32fbd2bb7bb27a0dca84334bd3e2d0039a567` принят.
Короткий контракт выше согласован C0 для реализации в пределах M5.2C;
это не приёмка ещё не предъявленного кода, migration или PG/S3/browser evidence.
Application base `70804866f6838f77c12bd281febae47887559d75` и исходный assignment
`031af2b091d40800c103d182d135f0677e4fca53` сохраняются.
Exact continuation base — `9bd32fbd2bb7bb27a0dca84334bd3e2d0039a567`,
tree `c9de945f45669183094ba48489c93ecfa837e3f4`; сохранить в ancestry.

**Дополнительно разрешён только `backend/src/asm/auth/http.py`** для streaming
admission одного owner-upload маршрута и необходимого CORS PUT.
C0 сверил исходник: все mutation paths сейчас требуют application/json до чтения
body; затем действуют4096B (manual send65536B), шестизначная проверка
Content-Length и предварительное чтение всего body с timeout3s.
Поэтому raw image получает415 независимо от достижения4096B. Также существующий
CORSMiddleware допускает только GET/POST/PATCH: без PUT браузерный preflight
новой загрузки не пройдёт. Это транспортная зависимость принятого private
owner upload, а не новая продуктовая функция или изменение auth architecture.

Границы разрешённой поправки:

1. Streaming branch применяется только к PUT с полным canonical route
   `/api/v1/workspaces/{w}/businesses/{b}/portfolio/assets/{a}/versions/{v}/uploads/{u}/content`.
   Все UUID и согласованность raw/decoded path проверяются; соседний путь,
   другой method, suffix/trailing slash и encoded alias не получают это исключение.
   Старые auth/JSON/manual-send paths сохраняют свои лимиты и deadlines.
2. Host/Origin/header/rate и no-store/nosniff остаются в общем boundary.
   До первого чтения upload body endpoint обязан проверить session cookie,
   CSRF, текущий OWNER и server-issued intent со всеми Workspace/Business/
   asset/version/upload связями и сроком. Route match сам доступа не даёт.
   Затем отпустить DB transaction; body/storage HTTP не удерживают DB lock.
   Перед finalize/apply вновь проверить действующие полномочия и intent.
3. Только JPEG/PNG/WebP и identity encoding. Отдельно проверяются допустимая
   объявленная длина и суммарные фактические bytes≤10MiB; старый six-digit guard
   нельзя оставить блокирующим разрешённый upload или расширить глобально.
   Duplicate/malformed/mismatched Content-Length, overflow без Content-Length,
   invalid encoding, disconnect и slow chunks имеют bounded terminal outcome.
   Общий receive deadline15s не сбрасывается на каждом chunk; запрос не
   буферизуется дважды. MIME не заменяет прежний full-decode validator.
4. В существующем CORS разрешить PUT с прежними exact origins, credentials и
   headers; без wildcard, нового public route или отдельного CORS механизма.
   Предварительный OPTIONS не читает image body и не выдаёт upload authority.
   Обычный запрос по-прежнему проходит cookie/CSRF/OWNER/intent guards.
5. В source admission добавить только этот дополнительный production path
   для текущей M5.2C ветки/assignment/continuation, без глобального allowlist.
   Новые проверки размещаются в уже разрешённых `tests/test_m5_portfolio*.py`
   и существующем M5.2C browser scope; остальные auth файлы не открываются.

До общего PR/CI показать целевые проверки: canonical PUT с настоящим PNG>4096B
доходит до правильного handler; неправильные authority/CSRF/OWNER/intent дают
отказ до body receive; exact/overflow/mismatched lengths, chunked input,
timeout/disconnect и неканонические пути не обходят ограничения.
Отдельно сохранить старые auth4096/manual-send65536 и Host/Origin/rate/cookie/CSRF
регрессии. Browser evidence должно включать allowed-origin OPTIONS→PUT и
отказ чужому origin, затем actual owner API/PG/private S3 upload/finalize.
Незавершённый/поздний PUT сохраняет прежний cleanup/tombstone контракт.

Заявленные C4 для вне-Git поправки76 UNIT PASS, mypy/Ruff — авторский отчёт:
C0 этот патч не получил и его76 проверок не повторял. Он не подменяет проверку
закоммиченного кандидата и сценария браузера. После целевых проверок — один
штатный full CI кандидата, без отдельного docs-only PR.
Новых paid/provider/VM/client-data допусков нет; M5.2C остаётся единственной
IN_PROGRESS задачей. C4 может продолжить SQL/основную реализацию и upload fix.

### Миграция и разрешённые paths

Фактический head **0020**; applied0001–0020 immutable. Для этого среза C0 выделяет
единственный слот **0021←0020**, файл `migrations/versions/0021_vision_portfolio.py`.
C2 перед SQL проверяет текущий head и отсутствие конкурирующего использования.
При конфликте обратиться C0, не переименовывать/переписывать применённое.

Разрешены только необходимые для указанного результата изменения:

- Новый `backend/src/asm/portfolio/`:
  `__init__.py`, `models.py`, `errors.py`, `validation.py`, `permissions.py`,
  `repository.py`, `service.py`, `http.py`, `storage.py`, `search.py`.
  Не создавать пустые слои ради списка.
- Новые `backend/src/asm/ai/vision.py`, `vision_contracts.py`, `portfolio.py`,
  `prompts/vision_v1.txt`, `schemas/vision_result_v1.json`,
  `prompts/conversation_v5.txt`; `schemas/conversation_result_v2.json` только
  при необходимом versioned изменении, без заготовки photo send.
- `backend/src/asm/ai/{knowledge,contracts,context,agent,database,fake,gateway,runtime,runtime_contracts,runtime_settings,provider_runtime,settings,polza}.py`;
  `backend/src/asm/files/{models,database,service,storage,validation}.py` —
  ограниченный reuse/новые permits, старые inbound guards не ослаблять.
  `backend/src/asm/files/config.py` — только отдельный operator-owned presign
  endpoint по решению C0 о checkpoint ниже; без нового storage backend.
- `backend/src/asm/knowledge/{models,errors,validation,repository,service,http,embeddings}.py`;
  `backend/src/asm/configuration/{models,errors,validation,repository,service,http}.py`
  — только publication/rollback composition и повторное использование поиска.
- `backend/src/asm/auth/http.py` — только canonical portfolio PUT streaming
  и необходимый CORS PUT по принятому выше решению C0; остальные auth paths,
  лимиты и security guards сохраняются.
- `backend/src/asm/foundation.py`, `backend/src/asm/tenancy/database.py`,
  `backend/src/asm/messaging/{database,worker,results,errors}.py` —
  wiring/versioned guarded path; `contracts/openapi.json`;
  `migrations/versions/0021_vision_portfolio.py`.
- UI: `frontend/src/{PortfolioPanel.tsx,PortfolioPanel.test.tsx,portfolio-api.ts,portfolio-api.test.ts,portfolio-fixtures.test-helper.ts}`;
  `frontend/src/{ConfigurationPanel.tsx,ConfigurationPanel.test.tsx,configuration-api.ts,configuration-api.test.ts,configuration-fixtures.test-helper.ts,App.tsx,App.test.tsx,style.css}`;
  `frontend/e2e/{portfolio.spec.ts,configuration.spec.ts}`;
  `frontend/src/{MessagingPanel.tsx,MessagingPanel.test.tsx}` — только привязка
  ReferencePortfolio к существующему selected conversation и её регрессии
  по решению C0 ниже; без переноса владения selection/control.
- Новые `tests/test_m5_vision*.py`, `tests/test_m5_portfolio*.py`,
  `tests/m5_portfolio_fixtures.py`, `tests/fixtures/m5_portfolio/`;
  существующие `tests/test_m5_configuration*.py`, `tests/test_m5_knowledge*.py`
  и `tests/m5_{configuration,knowledge,knowledge_search}_fixtures.py`;
  `tests/test_m2_2_media.py`, `tests/test_m2_2_storage_postgres.py`;
  `tests/test_m4_{context,agent,gateway,runtime_database,runtime_migrations,runtime_postgres,schema_postgres,polza_runtime,polza_runtime_postgres,delivery,delivery_postgres,reply_rights,reply_rights_postgres}.py`
  — только соответствующие сценарии нового контракта/сохранение старых guards.
- Source admission/current-schema compatibility, только по impact list:
  `scripts/m4_runtime_db.py`, `tests/test_m4_runtime_db_runner.py`,
  `scripts/native_context_db_catalog.py`, `tests/generic_pg_schema.py`,
  `tests/test_{postgres,tenancy_postgres,foundation,auth_contract,native_context_db_runner}.py`;
  `tests/test_m2_3_{db_postgres,schema_postgres,setup}.py`,
  `tests/test_m3_1_{guards_migrations,native_context_postgres,native_context_runtime_postgres}.py`,
  `tests/test_m3_2_escalations_migrations.py` — только current schema/profile guards;
  `tests/test_m1_3_c0_acceptance.py` только актуальный transactional TRUNCATE
  list без CASCADE/ослабления assertions;
  `backend/src/asm/telegram/provisioning.py`,
  `scripts/m2_4_browser_fixture.py`, `scripts/m2_4_browser_worker.py`,
  `tests/test_m2_4_browser_fixture.py`, `scripts/prepare_telegram_egress.py`,
  `scripts/test_telegram_egress.sh`, `tests/test_telegram_egress_migration.py`.
  Это не разрешение менять Telegram/native behavior или исторические expected.
- `tests/test_telegram_egress_postgres.py` — только revision/count в
  `current_durable_fingerprint` по решению C0 после первого CI ниже;
  historical canonical_fingerprint и Telegram/durable semantics не менять.
- `compose.browser.yaml`, `scripts/check_browser_compose.py`,
  `tests/test_browser_compose.py` — только согласованная topology внутреннего
  S3 endpoint и browser presign endpoint, с exact guards/negative checks.
  CI workflows, image pins и остальные deploy/compose paths не открываются.
- `docs/tasks/M5_HANDOFF.md`: короткий согласованный контракт/возврат в этом
  CURRENT. AGENTS, README, TASK_REGISTER, IMPL-005 из C0 assignment сохранить.

Новые зависимости/lockfiles, workflows/deploy, probe PR48/его fixtures и
original architecture не входят. Запрещены будущие DurationCase/intake/Quote/
booking/payment tables, workflow engine, multimodal index/ANN, генерация,
bulk import и реальная отправка фото. Дополнительный path/существенный контракт
сначала обосновать C0, продолжая независимую разрешённую работу.

### Source admission и приёмка

До Draft PR/первого CI добавить и проверить узкий M5.2C admission в существующем
runner: указанные base/tree, assignment ancestry/документы, эта ветка и будущий
main merge, точный список реализованных разрешённых файлов. Сохранить старые
branches/отказы, checks clean source/attempt и бюджеты. Проверить actual Git
pins/diff и positive/negative admission cases. Docs-only assignment не открывать
отдельным заведомо красным PR; C4 открывает один PR с работающим срезом.

Готовность — K04–K08/K11/K12 в границах этой задачи; K09 относится к M5.2D:

- Actual PostgreSQL + private S3: upload/finalize/authorized preview, interrupted
  upload/replay/cleanup, full-decode/size/type limits, object/hash/version
  mismatch и cross-tenant/business/client отказ. Нет fake Telegram rows,
  public object доступа или утечки URL/keys в DTO/logs.
- Controlled Vision wire содержит derivative реальных fixture pixels с точной
  версией; caption-only не проходит за Vision. Invalid/refusal/oversized/timeout/
  UNKNOWN, unavailable/replaced/deleted image, injection, отсутствие scale/time/
  price/business authority и запрет автоматического MY_WORK.
- Actual PG/pgvector: только published confirmed MY_WORK/showable, совместимый
  профиль, bounded matching/EMPTY, isolation; draft/revoked/deleted/reference/
  inspiration недопустимы как клиентское Portfolio evidence.
- Actual PG/API и real browser: upload → review/edit/confirm → publish →
  reference analysis/matches видны мастеру → revoke/delete. После reload и
  изменения настроек не теряются прежние knowledge/portfolio связи; после
  отзыва последнего item явный empty publish без новых model reservations.
  Failed build сохраняет active; rollback не воскрешает удалённые данные.
- Конкурентные media replacement/revoke/publish/owner revocation/HUMAN на
  границах MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND блокируют stale reads/эффекты;
  accounting completion не теряется, uncertain вызов не повторяется при restart.
- Upgrade с чистой БД и с0020, current catalog/profile compatibility, старые
  invariants и text-only sessions сохранены. Default DISABLED —0 provider HTTP.
- Сначала целевые проверки по этим рискам, затем штатный full CI final candidate.
  Fake/MockTransport доказывает механику, не качество модели. Existing M5.2A
  real synthetic receipt сохраняется только как capability evidence выбранного
  route/samples; новый application Vision E2E/качество тату не заявляются.
  Если для semantic acceptance нужен новый real smoke — отдельно процедура,
  route/data/запросы/предел расходов и допуск владельца; до него code LOCAL/TEST
  можно принимать отдельно, соответствующий real criterion остаётся открытым.

Возврат: один PR, final head/tree и сохранённый assignment; краткий контракт C2/
миграция; фактические команды/сценарии/results и ограничения; один следующий шаг.
C0 review → отдельное owner merge → post-merge CI. ВМ, real provider GET/POST,
новый ключ и реальные клиентские данные не разрешены. C6 HOLD; старые
UNKNOWN/holds, receiver ACK/fence и полный live HUMAN/Resume сохраняются отдельно.

### Решение C0 — checkpoint и завершение M5.2C / 2026-11-15

**ACCEPTED FOR IMPLEMENTATION; задача остаётся IN_PROGRESS.**
Checkpoint сохранён: `93174249527c055f3a975ba097a8646b2d14f450`,
tree `bad38d145fcf368f5b98c9f609e872722d418258`.
Это exact implementation continuation base; новый C0 docs commit поверх него
также сохранить в ancestry. Ветка прежняя: `c4/m5-2c-vision-portfolio-r1`.
Application main остаётся `70804866f6838f77c12bd281febae47887559d75`;
assignment031af2b и принятое upload-boundary решение a34834e сохраняются.

C4 сообщил: actual PG38 runtime +18 owner API +11 SQL PASS; fresh/reverse/
populated0020→0021 и старые receipts PASS; unit669, mypy107 files, frontend485,
3 controlled browser journeys PASS. Это авторский checkpoint, не независимая
приёмка C0. Вне-Git render-slot patch и его App27+Messaging35 также не приняты
как evidence закоммиченного кандидата. Actual private S3/browser — NOT_RUN;
локальный MinIO, по отчёту C4, остановился с `netlinkrib: operation not permitted`.
PR, full CI и merge на этом checkpoint не запускались.

**1. Selected conversation — дополнительный write-set принят.**
Разрешены `frontend/src/MessagingPanel.tsx` и его `MessagingPanel.test.tsx`.
Существующий MessagingPanel остаётся владельцем selection; узкий optional
render slot передаёт App доверенный selected row: Business/Client/Conversation
в текущем Workspace, read refresh и доступность новых действий. Использовать
уже подготовленный ReferencePortfolio. Отдельный selector, ввод UUID и
глобально выбранный Business вместо selected.business_id не допускаются.
Session/workspace/OWNER loss, смена conversation и поздние ответы очищают или
отсекают прежние сведения; mount/selection/refresh выполняют только GET.
Новые analysis/matches запускаются явной кнопкой, только при текущем AI context,
без HUMAN, pending control/reconciliation/manual intent и известных blockers.
UNKNOWN не повторяется автоматически. Server guards остаются окончательной
проверкой; UI не выводит разрешение из текста/наличия изображения.
Целевые App/Messaging/ReferencePortfolio проверки: exact context binding,
переключение двух диалогов/Workspace, stale response, OWNER loss/HUMAN/pending,
ноль POST при mount/refresh и сохранение manual-send/control UNKNOWN semantics.

**2. Найден обязательный transport fix для actual browser S3.**
В checkpoint `compose.browser.yaml` задаёт API `ASM_STORAGE_ENDPOINT=
http://127.0.0.1:9000`: он подходит для signed URL браузеру, но server PUT/
HEAD/GET обращаются к loopback самого API container. S3ObjectStorage использует
один этот endpoint для I/O и presign. Перенос теста в CI сам эту зависимость
не исправляет; простой переход на `http://storage:9000` сломает прежние
browser signed GET. C0 принимает узкое разделение адресов:
`ASM_STORAGE_ENDPOINT` — server I/O; optional `ASM_STORAGE_PRESIGN_ENDPOINT`
— только локальное формирование signed GET, по умолчанию тот же endpoint.
Оба задаёт оператор, оба проходят прежний origin validator; одинаковые
bucket/region/explicit credentials, без runtime URL input/discovery/fallback.
Подпись создаётся для конечного browser origin; готовый подписанный URL
нельзя переписывать. Presign не делает network I/O. TTL60, private bucket,
authorization, no-store, transaction-free I/O и отсутствие SDK retries сохраняются.
Browser TEST: I/O `http://storage:9000`, presign `http://127.0.0.1:9000`.
Дополнительно разрешены files/config.py, compose.browser.yaml,
scripts/check_browser_compose.py и tests/test_browser_compose.py в указанной
границе; files/storage.py и media/storage tests уже входят в write-set.
Проверить fallback к прежней конфигурации, invalid origin, отсутствие presign
network calls и прежний signed inbound image browser flow. Exact topology
checker обновить вместе с отрицательными тестами; security checks не убирать.
Это transport dependency accepted private storage (Spec17.5/19.4, ADR-115),
без изменения архитектурного доступа к файлам или новой инфраструктуры.

**3. Actual S3/browser — выполнение в первом штатном CI разрешено.**
C0 сверил existing foundation-core: checks зависит от storage-test-init и
получает private storage-test/asm-private-test; generic integration selection
не исключает tests/test_m5_portfolio_storage_postgres.py. Все9 подготовленных
actual-S3 проверок должны попасть в collection и завершиться PASS без skip.
Existing browser job также поднимает PostgreSQL/API/private MinIO.
Локальный NOT_RUN допустим до PR именно для этих environment-dependent gates;
это уточняет прежнее требование показать actual S3/browser до общего CI.
Не менять image pins/workflows, не расширять глобальные allowlists, не
повторять неизменённый локальный запуск MinIO ради дополнительного подтверждения.

До PR закончить UI wiring/transport fix и целевые доступные проверки.
В portfolio.spec.ts добавить actual browser→API→PG→S3 journey: синтетический
PNG>4096B, upload/finalize/private preview, owner review/reload/revoke;
без route.fulfill для проверяемых API/S3 операций. Показать настоящий
allowed-origin OPTIONS→PUT, отказ чужому origin и сохранение прежнего
inbound signed GET. Default DISABLED даёт0 provider HTTP; не включать paid
route ради browser fixture. Nonempty index/composite publish/semantic flow
доказываются отдельно actual PG/S3 с controlled provider и browser UI cases;
явно различать эти evidence, не называть подставленные HTTP ответы actual E2E.
Проверки actual S3/browser остаются OPEN до успешного CI этого кандидата;
9 S3 API tests не заменяют unmocked browser journey.

Обновить только M5.2C source admission для новых разрешённых paths и этой
continuation; прежние migration/source/security gates не ослаблять.
Затем открыть один Draft PR в main и выполнить первый штатный full CI final
candidate. При падении отделить code defect от runner/storage startup failure;
не менять expected, не подменять S3 fake и не повторять зелёные неизменённые
прогоны. Вернуть один результат: PR, final head/tree, команды/CI, PASS/NOT_RUN
по actual PG/S3/browser и оставшиеся findings. C0 review и отдельное разрешение
владельца на merge обязательны. Новых provider/VM/client-data допусков нет;
C6 HOLD, M5.2D не начинать. Следующий исполнитель — C4 в той же ветке.

### Возврат C4 — первый full CI и два запроса C0 / 2026-11-15

**IN_PROGRESS; приёмка actual S3/browser остаётся OPEN.** Один Draft
[PR50](https://github.com/Elefesys/ai-service-manager/pull/50) открыт в main7080486.
Проверенный CI head `aa31a88db7e8650d33a688c848c514285e31bd86`,
tree `d93f8ec529ecd603528681abe2adcc32c10b00f8`, parent114a027;
checkpoint9317424 и все принятые assignments сохранены в ancestry.
[Первый штатный full CI43730073008](https://github.com/Elefesys/ai-service-manager/actions/runs/43730073008),
attempt1, завершился **FAILURE: 7 PASS / 4 FAIL / 1 SKIPPED**.
Повторный CI на неизменённом source не запускался.

- PASS: native-context-db и все6 connect5 migration lanes
  (normal/docker29 × intent/image/state).
- foundation-durable и docker29-compatibility остановились в одном current
  prerequisite: `current_durable_fingerprint` ожидает0020/59, установлен0021/68.
  foundation пропущена через needs; все9 новых actual S3 API cases **NOT_RUN**.
- m4-runtime-db выполнил все160 cases:127 PASS/33 FAIL. Из них32 падают при
  provider admission: новая схема сохраняет вызов исторического0020 verifier;
  ещё1 current application readiness использует историческую knowledge fixture0020.
- Browser:66 PASS/3 FAIL, skip нет; API/PG/private MinIO healthy, startup ошибки
  отсутствуют. Старый inbound private-image/signed-GET journey PASS. Два новых
  actual S3 journeys дошли через настоящий PNG>4096B upload/finalize до private
  preview HTTP200, затем остановились на `nosniff, nosniff` вместо одного
  `nosniff`. Проверки последующего hash/decode/review/reload/revoke и actual
  browser OPTIONS→PUT/foreign-origin ещё **NOT_REACHED**, не PASS.
  Третье падение — прежний escalation login/CSRF startup barrier: новый GET
  референса начинался до initial history и сразу отменялся после её завершения.

**Разрешённые исправления подготовлены и проверены отдельно от CI.**
Code checkpoint
[`5dcf7f180edb511b71150a69f3f9a04cef1e96c3`](https://github.com/Elefesys/ai-service-manager/commit/5dcf7f180edb511b71150a69f3f9a04cef1e96c3),
tree `ead22a4b2422599487b89a69e9b13dc1b7a4015c`, parentaa31a88.
Это сохранённый review commit; PR branch ref пока остаётся aa31a88 до решения
двух запросов ниже, чтобы не запускать заведомо красный второй full CI.

1. Только в новой0021 добавлена13-я replacement:
   `ai_provider_session(jsonb,boolean)` обращается к `portfolio_schema_profile()`.
   Exact0020 definition сохранена в ORIGINAL для downgrade. Старый operator DTO,
   text-only profiles, session_user/asm_test/identity/budget/currentness guards
   и все applied0001–0020 неизменны; новый paid/Vision route не открыт.
   Независимый actual PG catalog289 functions/68 tables/1001 columns PASS;
   profile `da169523db6ecaf26b566e52c7457fbb8785ff0921fefe71d24f006fc9ec87aa`,
   body `df2ab97e8fe09ead37d2dd16f70526f4f47073eaed3314686ceb319e7773d06b`;
   nonfunction hash остаётся `dcc311ce3d0b978428f63ca27b69dbe8bc621b485d4f67bcae9a1964d08f4ac9`.
2. Только current application knowledge case получает отдельную function fixture
   с upgrade0021 и точным finally downgrade0020. Остальные historical knowledge
   cases остаются на0020. Этот уже разрешённый `test_m5_knowledge_runtime_postgres.py`
   добавлен в конечный M5.2C source admission.
3. Selected-conversation render slot ждёт initial history; затем один reference
   GET без немедленной отмены. Новые AI действия также блокируются на время
   чтения истории. Владение selection и server authority сохранены; старый
   escalation browser test/его assertions не менялись.

Фактические целевые команды: pytest `tests/test_m4_polza_runtime_postgres.py`
**41 PASS/142.70s**, `tests/test_m5_knowledge_runtime_postgres.py`
**11 PASS/52.77s**, `tests/test_m5_portfolio_migrations.py` **4 PASS/1.23s**;
`tests/test_m4_runtime_db_runner.py -k 'portfolio or m5'`
**259 PASS/42.45s**. App/Messaging/Portfolio Vitest **91 PASS/7.29s**,
TypeScript и Ruff PASS. Actual fresh0021 / exact0020 reverse / populated0020→0021
и byte-exact старый receipt replay PASS. PG source metadata для локальных
targeted tests явно constructed LOCAL, не GitHub CI; все данные синтетические,
owned PG остановлены. Full CI этого fix checkpoint **NOT_RUN**.

**Запрос1 — дополнительный current-compatibility path, REQUESTED на возврате;
ACCEPTED C0 решением ниже.**
Нужен только `tests/test_telegram_egress_postgres.py`, отсутствующий в текущем
write-set, и его точечный admission. Не применён следующий двухстрочный патч:

```diff
 async def current_durable_fingerprint(connection):
-    revision = "0020"
+    revision = "0021"
 ...
-    assert len(tables) == 59, "E05_CURRENT_NATIVE_TABLES"
+    assert len(tables) == 68, "E05_CURRENT_NATIVE_TABLES"
```

Вне-Git proposal на actual PG воспроизвёл отказ исходника и получил полный
read-only fingerprint68 таблиц, точное равенство повторного чтения; отсутствие
каждой из9 новых таблиц и лишняя таблица отвергнуты. Historical
`canonical_fingerprint`0009–0012 byte-identical. Полный Docker/Xray/S3 durable
lane этим локальным proof не заменён. Другие Telegram paths/semantics не нужны.

**Запрос2 — исправить новое browser assertion, REQUESTED на возврате;
ACCEPTED C0 решением ниже.**
`infra/nginx.conf:6` уже в main708 добавляет `X-Content-Type-Options: nosniff`;
AuthBoundary добавляет такой же header. Новая проверка ошибочно требует один
токен от ответа через оба слоя. Не меняя production/deploy и не ослабляя backend
API assertion одного header, предлагается в уже разрешённом portfolio.spec.ts
проверять точные два edge токена:

```typescript
expect(fetched.headers()['x-content-type-options'].split(',').map(v => v.trim()))
  .toEqual(['nosniff', 'nosniff']);
```

Патч не применён: решение114a запрещает менять expected после падения.
Не требуется менять nginx/AuthBoundary, MIME, no-store, private access, transport
или подставлять ответы actual S3. После решения C0 — C4 применяет только
согласованные поправки в той же ветке/PR50, проверяет их и запускает следующий
штатный full CI изменённого кандидата. Merge/VM/provider/client-data не выполнялись.

### Решение C0 — два запроса после первого CI / 2026-11-15

**Оба запроса ACCEPTED FOR IMPLEMENTATION. M5.2C остаётся IN_PROGRESS;
PR50 Draft; actual S3/browser OPEN.** Новой функции или изменения архитектуры нет.
Exact continuation base — `da3007ae464d505f2d7c98b57f0f88836709d87d`,
tree `cc433bed24cab28e641ddb72c2f09431bcf32f26`, с code fix
`5dcf7f180edb511b71150a69f3f9a04cef1e96c3` в ancestry.
Сохранить этот C0 docs commit поверх review base. PR branch остаётся
`aa31a88db7e8650d33a688c848c514285e31bd86` до готового исправленного кандидата:
docs-only push в открытый PR запустил бы заведомо незавершённый CI.
Продолжает C4, та же ветка и тот же PR50; main7080486 не изменяется.

C0 независимо сверил jobs/логи и распакованные artifacts CI43730073008/attempt1:
7 SUCCESS /4 FAILURE /1 SKIPPED; durable отказ на0021≠0020;
runtime JUnit160/33 failures/0 skips; browser66 PASS/3 FAIL.
Browser startup завершился успешно; новые actual journeys действительно
дошли до preview200 и остановились на header assertion; последующие проверки
не выполнены. Artifact ZIP hashes совпали с опубликованными job digests.
Локальные PASS для fix5dcf7f1 остаются авторским evidence, не новым full CI.

1. **Current fingerprint:** разрешены ровно две указанные строки в
   `tests/test_telegram_egress_postgres.py::current_durable_fingerprint`:
   revision0021 и count68 вместо0020/59. C0 сопоставил actual CI nonfunction
   catalog с `SCHEMA_TABLES["0021"]`: точное равенство68 таблиц, ровно9 новых
   относительно0020. Существующий `schema_inventory` проверяет полное равенство
   набора, а fingerprint читает все строки каждой таблицы, включая новые.
   Эти проверки сохранить; не заменять их одним count, subset или dynamic
   current head. Historical0009–0012 `canonical_fingerprint`, applied0001–0020,
   before/after multiset comparison, receipts, wire counters, UNKNOWN и
   cleanup/rollback assertions неизменны. В уже разрешённых
   scripts/m4_runtime_db.py / tests/test_m4_runtime_db_runner.py открыть только
   этот дополнительный M5.2C path; никаких общих исключений для Telegram tests.
   Зафиксировать targeted positive68 и отрицательные missing/extra inventory
   checks. Полные normal/docker29 durable lanes обязательны в следующем CI.

2. **Browser edge assertion:** разрешён предложенный exact split/trim и
   `toEqual(['nosniff', 'nosniff'])` только в новом actual portfolio browser
   preview case. C0 подтвердил: nginx.conf byte-identical main7080486 добавляет
   один header; AuthBoundary также добавлял один ещё в main. CI browser log
   показывает их объединение. Это исправление неверного ожидания нового теста
   для существующего API→nginx пути, не общий допуск менять expected после FAIL.
   Backend/direct-API assertion одного nosniff, production headers/nginx,
   MIME/no-store/private authorization, hash/decode и остальные journey checks
   сохранить; `includes('nosniff')`, optional header или произвольное число
   токенов не заменяют exact assertion.
   [Fetch §3.6](https://fetch.spec.whatwg.org/#x-content-type-options-header)
   определяет действие nosniff по первому разделённому значению; проверка двух
   известных edge headers не означает принятия их как нового canonical API
   формата и не требует production/deploy поправки в этом срезе.

C0 также проверил ограниченность подготовленных fixes: provider replacement
меняет только вызов verifier knowledge_search→portfolio; ORIGINAL совпадает
с реально устанавливаемым REPLACEMENTS0020. Profile hashes должны проверяться
по установленному catalog; нельзя копировать expected лишь по результату FAIL.
Current knowledge fixture изолирует upgrade0021 и finally downgrade0020;
остальные historical cases не переводить массово. Render-slot fix и новый
App regression сохраняют existing escalation assertions. Эти исправления
сохранить вместе с двумя принятыми поправками в одном кандидате.

Следующее действие C4: локально продолжить от этого C0 commit, применить две
поправки/admission, выполнить только затронутые целевые проверки и один push
готового кандидата в существующий PR50. Затем следующий штатный full CI:
все12 jobs, включая normal/docker29 durable, runtime,9 actual S3 API cases
без skip и unmocked desktop/narrow journeys полностью до review/reload/revoke/
delete/OPTIONS→PUT/foreign-origin; старый inbound signed GET и escalation
login/CSRF recovery также должны PASS. Новый failed gate разбирать по его
собственной причине; ранний PASS не заменяет ещё не достигнутые assertions.
Вернуть PR/final head/tree/CI и ограничения. Merge требует отдельного разрешения
владельца после C0 review. Paid/provider/VM/client-data, C6 и M5.2D не открыты.

### Возврат C4 — принятые поправки выполнены, foundation unit gate OPEN

**IN_PROGRESS; PR50 Draft.** Решение cecb92c сохранено в ancestry и выполнено:
exact0021/68 fingerprint с прежним full inventory/multiset, exact два edge
nosniff и narrow admission. Затронутые проверки87 PASS/18.41s; actual read-only
PG68 таблиц/1303 строки, повторный fingerprint exact equal,9 omissions/extra
отвергнуты. Historical0009–0012 helper и applied0001–0020 неизменны.

Один готовый push в PR50:
head `4f0973b13c5177c7c613a77ee9f954c5e145f858`,
tree `3248684c2c4d76672b9627250e5c14605b7abc4a`, parentcecb92c.
[CI43734534033](https://github.com/Elefesys/ai-service-manager/actions/runs/43734534033)
проверил merge `80d6cc884d9b0a1a0287fd101999d6ef181d14b7` с тем же tree;
архив438 файлов совпал с actual candidate bytes/Git executable bits.
Main7080486, protected4 bytes/modes, image pins/workflows не изменены.

- Attempt1:10 SUCCESS/2 FAILURE. Native, runtime160/160 и все6 connect5 lanes
  PASS. Normal и Docker29 durable прошли все6 lifecycle routes, без прежнего
  раннего schema отказа; ZIP digests сверены.
- Browser attempt1:65 PASS, затем общий phase600s/exit124; assertion failures
  нет, последние4 narrow cases не достигнуты. На63 общих PASS cases медиана
  времени была1.34× первого CI; источник замедления не установлен.
  Только этот failed job повторён один раз на том же SHA/бюджете: attempt2
  **69 PASS/505.964s**. Desktop+narrow actual private S3 upload/finalize/private
  preview hash/decode/review/reload/revoke/delete/OPTIONS→PUT/foreign-origin
  выполнены целиком. Legacy inbound signed GET и escalation login/CSRF PASS.
  Остальные jobs/полный прогон не повторялись; первый timeout сохранён.
- Foundation attempt1: **4401 PASS/14 FAIL**,1281 integration cases deselected
  на unit-этапе,161 subtests PASS. Проверки PostgreSQL/S3 core вследствие этого
  **NOT_RUN**, включая все9 actual S3 API cases и38 новых v5 PG cases.
  Browser PASS не заменяет этот OPEN gate. Runner/storage startup failures нет.

Все14 unit failures разобраны, а не только первый:

| Причина | Cases | Действие |
|---|---:|---|
| Старый CORS exact methods исключает принятый PUT; PUT ожидает400 | 4 | Запрос нового unit path ниже; production CORS не меняется |
| M4 delivery/reply-rights current tests читают0020 verifier вместо0021 | 2 | Исправлены в уже разрешённых files; previous0020 и historical profiles сохранены отдельно |
| Общие имена новых Portfolio ErrorResponse/CommandResponse/CommandResult вытесняют canonical auth/config OpenAPI names | 1 | Исправлен production DTO namespace; старые тестовые assertions сохранены |
| Egress current-unit seams всё ещё задают0020/59 и233 functions/832 columns | 6 | Запрос нового unit path ниже; historical material0007/0012 не менять |
| Probe test с deadline80ms: known_call_count0 вместо1 | 1 | Отдельные4 deadline variants локально PASS/1.04s; причина CI failure не закрыта, probe source/лимиты/expected не менялись |

**Разрешённые fixes сохранены для review**, без нового заведомо красного push:
[`1c075904d88b98fbf4f133d83e63391f5dc5002b`](https://github.com/Elefesys/ai-service-manager/commit/1c075904d88b98fbf4f133d83e63391f5dc5002b),
tree `b10e9db7694c033dcaddbad7a70a20409b1fca2c`, parent4f0973b.
Только новые portfolio classes получили Portfolio-prefixed names; Python import
aliases и JSON bodies сохранены. Generated contract обновлён; canonical
ErrorResponse/CommandResponse/CommandResult побайтово совпали с main7080486,
namespace collisions отсутствуют, все refs разрешаются. Current M4 unit guards
читают source0021/289/68/1001 и установленный pin da1695/df2ab9; source0020
сохраняется отдельным historical comparator. SQL/profile pins не менялись.
Команды pytest configuration/delivery/reply-rights/portfolio-unit:103 PASS/16.56s;
auth-contract1 PASS/2.26s; M5.2C admission75 PASS/16.68s; Ruff/mypy PASS.
Full CI этого review checkpoint NOT_RUN; PR branch остаётся4f0973b.

**Запрос C0 — ровно два дополнительных unit paths / REQUESTED.**
Оба отсутствуют в write-set; production/code fixes без них не устраняют10
детерминированных unit failures. Вне-Git proposals подготовлены, но НЕ ПРИМЕНЕНЫ:

1. `tests/test_m1_3_http_contract.py`: в существующем preflight test заменить
   только PUT/content-type status400→200 и добавить PUT в exact allowed-methods
   set. Это отражает уже принятое a34834e transport решение. Credentials,
   exact origins/headers, foreign-origin/DELETE/if-match/x-forged-actor отказы
   и остальные billing/schema tests сохранить.
2. `tests/test_telegram_egress.py`: только current-unit block1935–2296.
   Все11 его0020 markers/seams →0021; два current profile counts233/59→289/68,
   total columns832→1001, full row-read count59→68. Включены native-host
   component fingerprint и mock revision, чтобы negative cases достигали
   проверяемого corruption guard. Historical0007/0012 source/defaults/guards,
   wrong-database/read-only, multiset hashing, before/after/UNKNOWN/Console и
   missing/extra/same-count negative assertions сохранить; не вводить dynamic
   head/subset/count-only checks. Production egress/Docker lanes не менять.

В отдельном unit process обе proposed test modules дали **174 PASS/9.58s**;
original checkout bytes до/после совпали. Это только UNAPPLIED unit proposal
proof, не actual PG/S3/CI и не разрешение C0. При принятии открыть ровно эти два
M5.2C admission paths и перенести adjacent-Telegram refusal на иной вне scope
path; общие allowlists не расширять. Решение о deadline-test timing оставить
явным: один локальный PASS не объявляет CI failure исправленным.

Следующий шаг — C0 решение по двум bounded unit paths, затем C4 в том же
PR50 применяет только принятое, проверяет затронутые tests и запускает новый
штатный CI изменённого кандидата до всех12 gates/9 S3 API без skips.
Merge/VM/paid/provider/client-data не выполнялись; C6 HOLD, M5.2D не начата.

## 1. Проверяемый результат всего этапа

Владелец может завести услуги и подтверждённые знания, проверить изменения и
опубликовать их. Клиент задаёт вопрос и присылает доступное фото. AI отвечает
по опубликованным сведениям, последовательно уточняет недостающее, подбирает
подходящую настоящую работу и готовит мастеру описание запроса с источниками.
Сложный/неподдерживаемый случай поступает в существующий Action Center.

M5 не считает индивидуальную цену, не определяет подтверждённое время сеанса,
не выставляет предложение/депозит, не бронирует и не принимает оплату. Результат
intake — предварительная информация с происхождением, не M6 ServiceRequest,
Assessment или одобренный заказ. LLM не получает mutation tools.

Первый полезный результат появляется уже после M5.1B: изменённый владельцем FAQ
доходит до ответа тестового AI, draft не виден, старое правило после публикации
не используется. Не ждать окончания всех функций M5 ради этого сценария.

## 2. Объём пилота и границы

Входят:

- компактные Service/Intake/Rule/Communication settings, draft → validation →
  owner preview/publish, immutable active release, rollback;
- curated FAQ/источники и поиск с происхождением; один text embedding profile,
  PostgreSQL exact search, ограниченная загрузка в context/read tools;
- анализ текущих private images, owner upload/review настоящих работ,
  подбор Portfolio и одна разрешённая работа в ответе клиенту;
- DurationCase как подтверждённые примеры для мастера;
- synthetic TattooPack: NEW_TATTOO, COVER_UP и OTHER_COMPLEX с owner handoff;
- минимальный интерфейс для повседневного просмотра, подтверждения и публикации.

Не входят: universal workflow builder/engine, массовый импорт чатов/PDF/сайтов,
OnboardingAgent, автоматическое обучение, генерация эскизов, отдельная vector DB,
новый provider marketplace, scheduling/pricing/payment engines, новый канал,
отдельный ops dashboard, автономный облачный маршрут и production rollout.
Это явно принятые уточнения IMPL-005; исходный baseline сохраняется в истории.

Concierge import допустим через небольшой проверяемый CLI/API и тот же domain
service. Владелец не должен править SQL/JSON вручную для review/publish/отзыва.
Нельзя называть internal-only portfolio готовым клиентским показом изображения.

## 3. Очередь реализации

Порядок по умолчанию последовательный; одна активная выдача с одним ведущим.
Каждый кодовый срез — отдельный небольшой PR, конкретный продуктовый результат
и ограниченная проверка. C0 может разделить большой срез по реально найденной
границе, но не создавать новую сетку задач заранее.

| Порядок / ID | Ведущий; участие | Зависимости | Результат |
|---|---|---|---|
| M5.0 — приёмка плана | C0 | Этот пакет и CI кандидата | IMPL-005 принят; после разрешённой интеграции фиксируются base и единственная выдача M5.1A; application runtime не меняется |
| M5.1A — конфигурация и публикация | C1; C2 | M5.0 | В БД можно безопасно подготовить, проверить и опубликовать небольшой набор услуг/правил/FAQ |
| M5.1B — ответ по опубликованным знаниям | C4; C1/C3, C2 для БД, затем C5 | M5.1A | Опубликованный FAQ читается M4 runtime; owner видит preview и публикует через простой UI |
| M5.2A — ограниченная проверка modalities | C4; C6 только при необходимости | M5.1B; допуск нужен только для paid probe | Выбран конкретный пригодный Vision/embedding route либо описан точный блокер |
| M5.2B — знания и семантический поиск | C4; C1/C2 | M5.1B, embedding контракт M5.2A | Источники/ревизии/index build; keyword + exact vector retrieval с источниками |
| M5.2C — Vision и private portfolio | C4; C1/C2/C5, C6 для storage | M5.2A/B | Фото анализируется, подтверждённые работы загружаются, релевантные примеры видны мастеру |
| M5.2D — показать одну работу клиенту | C3; C4/C5/C8 | M5.2C | Одно разрешённое фото с caption проходит штатные delivery guards и UNKNOWN recovery |
| M5.3A — intake и DurationCase | C1; C4/C5 | M5.2C; клиентский показ использует M5.2D | Предварительное описание заказа, похожие кейсы и owner handoff без выдуманных условий |
| M5.3B — сборка и приёмка | C0/C8; исполнители по findings | Все предыдущие | Сквозные сценарии на одном кандидате; честная граница LOCAL/TEST и live; передача M6 |

Связь со старым планом 09: M5.1A/B уточняют M5.1; M5.2A–D разбивают прежнюю
чрезмерно крупную M5.2; M5.3A/B закрывают M5.3. UI появляется внутри срезов,
а не откладывается целиком на последний день. Роли в таблице — ответственность,
не распоряжение запускать несколько чатов над общими файлами одновременно.

### M5.1A — маленькая опубликованная конфигурация

**Польза:** правила мастера впервые становятся проверяемыми данными приложения.

Сначала C1/C2 фиксируют здесь короткий контракт: объекты и связь с Business,
минимальные поля, команды/ошибки, owner permissions, активная версия и инвалидация.
После этого реализуют bounded domain module, PostgreSQL/RLS и owner API:

- service name/description/active, intake template, понятные ограничения услуги;
- независимый выбор price/duration/deposit modes; неизвестное явно обозначено;
  M5 не исполняет формулу и не создаёт обязательства M6–M8;
- несколько вручную подтверждённых FAQ с источником, стиль общения без prompt editor;
- edit draft с expected version; validate ERROR/WARNING; inspect/preview;
  publish и rollback с idempotency, owner audit и atomic active pointer;
- release содержит только готовые материалы; не смешивает части двух публикаций.

Стартовать с двух маленьких synthetic конфигураций, без данных реального мастера.
Отсутствие цены/времени допустимо для консультации с owner handoff; невалидный
режим/ссылка/противоречивое структурированное правило блокируют publish.
Нет полного Rule DSL, семантического «детектора любых противоречий» и workflow graph.

**Приёмка:** actual PostgreSQL: draft невидим клиентскому чтению, publish атомарен,
повтор не создаёт второй release, конкурентный edit получает конфликт, revoked
owner не публикует, Workspace A не получает B, rollback не возвращает старую
activation version. UI и model calls пока не требуются для DB/API acceptance.

### M5.1B — первый полезный ответ и минимальный UI

**Польза:** AI знает ответы конкретного бизнеса, владелец понимает, что опубликовано.

- Дополнить ContextBuilder/authority/read boundary небольшой service card и
  bounded FAQ projection. Для малого набора начать с structured/keyword selection;
  не ждать embeddings, но и не выдавать этот срез за весь готовый RAG.
- Привязать run и результат к release/build/activation; применять инвалидацию
  IMPL-005 на MODEL/READ/FOLLOWUP/CANDIDATE/COMMIT/SEND, сохраняя все M3/M4 guards.
- Явно версионировать изменённые prompt/schema/DTO; старые сохранённые runs не
  переписывать. `read_context` и text-only DTO нельзя ослабить без новой версии.
- C5 последовательно добавляет простой раздел услуг/FAQ: draft/active, ошибки,
  preview, publish/rollback. Live preview не должен скрыто тратить API бюджет:
  deterministic preview показывает выбранные факты, paid generation — отдельный
  явно обозначенный opt-in. Preview не отправляется клиенту.
- Пустой источник, конфликт или неизвестная политика → уточнение/handoff.
  Источник сохраняется в trace/owner view; внутренние UUID не сыплются в текст клиенту.

**Приёмка:** actual API/PG + fake runtime + реальный browser:
владелец меняет правило, публикует, новый ответ использует его; draft не утёк;
publication перед MODEL/FOLLOWUP блокирует новый вызов со старым контекстом,
между read и send блокирует старый ответ; HUMAN/revocation работают.
Fake E2E не называется live LLM/Telegram проверкой.

### M5.2A — проверить Vision и embeddings до большой реализации

**Польза:** заранее узнать, какой реальный маршрут обслужит изображения и поиск.

Не повторять рынок агрегаторов и все M4 probes. Сначала проверить применимость
текущего Polza маршрута по актуальным capabilities и условиям; подтвердить schema,
image transport/preprocessing, embedding dimension/model, finite costs/deadlines.
Выбрать один Vision и один text embedding профиль; это могут быть разные модели
в принятой ветви. Не строить routing UI или автоматический fallback.

Подготовить короткий synthetic набор: обычная/неоднозначная/неподходящая картинка,
проверка запрета вывода масштаба, один релевантный/нерелевантный текстовый поиск;
негативные transport/schema cases выполнять локально. До paid вызова дать владельцу
конкретный маршрут, число запросов, ограничение суммы и процедуру выключения.
Старый M4 бюджет/ключ/допуск не считать новым разрешением. Реальные клиентские
изображения не использовать. Результат хранится коротким receipt в PR.

Отсутствие live допуска блокирует только real-route acceptance: работа с fake,
данными и контрактами продолжается. Нельзя имитировать embedding случайным
вектором и объявлять качество поиска доказанным. M5.2A закрывается с подтверждённым
capability result; при недоступности route C0 явно меняет задачу, а не ставит PASS.

### M5.2B — знания с источниками и управляемый поиск

**Польза:** отвечать по материалам мастера, даже если вопрос сформулирован иначе.

- Bounded текст/Markdown/структурированный concierge input; без URL crawler,
  PDF/OCR/import archives. Source → подтверждённые sections/items → chunks/index.
- Author/source/version/service/category/effective state; critical rule хранится
  структурированно или ссылается на него, не становится истиной из похожего FAQ.
- Подготовка нового KnowledgeBuild отдельно от active; error/unknown не меняет
  опубликованный набор. Publish включает готовый совместимый build.
- Один embedding profile, exact pgvector + metadata/full-text ranking. Размерность
  и профиль query/index совпадают; смена профиля требует rebuild, не смешения векторов.
- Минимальные READ results: разрешённые источники, фрагменты, причина релевантности,
  empty/conflict. Приватная история клиента не индексируется как общая Knowledge.
- Revocation/delete исключают source и derived chunks/cache из новых reads;
  хранить необходимую безопасную provenance, не бесконечные копии удалённого текста.

**Приёмка:** actual PG retrieval под runtime role, query/index mismatch;
общие опубликованные знания Business доступны его клиентам, личные данные другого
Client и недоступные Business/Workspace изолированы; draft/revoked/expired source,
failed build с сохранением active, injection content и корректный empty result.
Качество оценивается по источникам/полезности ответа, не побуквенно по реплике модели.

### M5.2C — фото и собственные работы

**Польза:** понять присланный референс и показать мастеру подходящие работы.

- Добавить явную image capability, новый разрешённый synthetic data profile и
  bounded Vision operation. Caption не выдаётся за просмотр пикселей.
- Reuse private storage/validation; owner asset upload/review — отдельный узкий
  permit, без фиктивного inbound Telegram message. Никаких public buckets.
- Vision result связан с точной доступной file/content version и профилем:
  subject/style/наблюдаемые детали/неопределённость. Чужой файл, удаление/замена,
  неподдерживаемый формат и лимит дают честный unavailable, не старую картинку.
- Portfolio item: MY_WORK / CLIENT_REFERENCE / INSPIRATION, подтверждение автора,
  разрешение клиентского показа, описание/атрибуты/service и активная версия.
  Vision suggestions подтверждает владелец перед публикацией.
- Поиск client reference → наблюдаемые признаки/описание → text embedding +
  filters → небольшой набор реальных релевантных PortfolioItem. Similarity не
  доказывает eligibility/цену/время; разрешён пустой результат.
- Owner UI: загрузить, посмотреть анализ/источник, исправить, подтвердить/отозвать.
  Analysis/build повторы не делают бесконтрольные paid calls; outcome хранится.

**Приёмка:** actual private S3 + PG/owner API, version invalidation и isolation,
несанкционированный тип/размер/URL, read auth перед выдачей, unknown cost/timeout,
restart, IMAGE unavailable; контроль, что reference не стал MY_WORK. Для смыслового
Vision PASS нужен отдельный разрешённый real API receipt, не только fake assertions.

### M5.2D — одна работа в ответе клиенту

**Польза:** клиент видит реальный пример, а не только сообщение «я нашёл похожее».

В текущем коде нет `sendPhoto`; не предполагать его готовым. C3 проектирует
небольшой typed portfolio selection + server-validated send intent. Модель
предлагает только выданный в текущем read PortfolioItem, не storage key/URL.
Проверить Telegram business capability для выбранного действия; сохранить права,
лимиты caption/media, текущую конфигурацию и разрешение показа перед send.

Один ответ — одно фото с caption либо обычный text reply; без отдельного text +
photo двойного эффекта, albums и новой очереди. Повтор и restart используют receipt;
возможный effect с потерянным ответом остаётся UNKNOWN/no-resend. Владелец видит
состояние в текущем Inbox. Отзыв работы до send блокирует отправку; уже начатая
отправка не объявляется отозванной. Новый content type должен проходить старые
control/rights/native/claim gates, а не обходить их через ручной send.

**Приёмка:** actual PG + controlled wire counter, stop/restart/UNKNOWN,
takeover/config change/withdrawal и cross-client isolation. Synthetic picture в
TEST явно обозначена тестовой, не «реальной работой мастера». Live Telegram smoke
только после отдельного допуска и закрытия относящегося к нему receiver ограничения.
Если C0/владелец отложит этот срез, фиксируется конкретный неполный UX M5.

### M5.3A — описание запроса мастеру и примеры длительности

**Польза:** мастер получает собранную информацию и примеры вместо чтения всей переписки.

- Tattoo template: идея, расположение, примерный размер со слов клиента, стиль,
  доступные референсы. Спрашивать последовательно только недостающее, принимать
  исправление клиентом; нет обязательной длинной анкеты для любого сообщения.
- Предварительная intake projection: значение + source message/file version +
  observed/client-stated/owner-confirmed/unknown. Вывести из текущих разрешённых
  данных и хранить/пересобирать с provenance; это не второе authoritative CRM ядро.
  Не создавать преждевременно M6 ServiceRequest/Assessment/Order таблицы.
- Ограниченные deterministic transitions template: уточнить, получить owner
  решение, завершить сбор. COVER_UP/OTHER_COMPLEX и отсутствие правила → existing
  escalation; в Action Center компактный summary со ссылками и открытым вопросом.
  Выполнение owner request не обещается до принятого результата runtime.
- DurationCase: разрешённая работа/описание, реальные размеры при наличии,
  исполнитель, working/occupied time, подготовка/перерывы, сессии и объяснение.
  Unknown не заполняется AI. Найти похожие случаи и показать мастеру различия;
  не выводить часы из размера картинки и не назначать клиенту длительность.
- Небольшая owner форма/concierge import и просмотр примеров; без fine-tuning,
  duration predictor, automatic rule publication и медицинских интервалов.

**Приёмка:** два разных бизнеса одним кодом; исправленный/удалённый источник
обновляет projection; known facts не спрашиваются заново; сложный запрос получает
одну актуальную escalation; подтверждённое время прошлого кейса не становится
обещанием новому клиенту. HUMAN и последующий Resume не теряют границы M3.

### M5.3B — завершение этапа

C8 проверяет весь интегрируемый scope по матрице ниже, уделяя внимание source
authority, private media и конкуренции publish/send. Авторские тесты остаются
обязанностью исполнителя. Targeted review одного fix не выдаётся за review всего M5.

Один финальный candidate → штатный полный CI → C0 acceptance → отдельный merge
допуск → фактический push/main CI. Не менять существующие gates ради зелёного
результата. Если CI сам запускается для docs PR, учитывать его один раз, без
ручного rerun неизменённых исходников. После приёмки — одна запись в реестре,
обновление CURRENT и передача M6 с release/intake/source contracts и ограничениями.

Отдельно перечислить, какие реальные Vision/embedding/Telegram проверки выполнены,
какие требуют владельца. LOCAL/TEST VERIFIED не равен готовности реального бизнеса.
При непроверенном реальном Vision route честный статус соответствующего среза —
REVIEW/BLOCKED по точной причине, а не автоматическое VERIFIED всего функционала.

## 4. Одна приёмочная матрица

| ID | Сценарий / обязательный результат | Доказательство |
|---|---|---|
| K01 | Draft изолирован; publish/rollback атомарны; edit/publish replay и конфликт корректны | PG + owner API |
| K02 | Один вопрос даёт разные подтверждённые ответы у разных бизнесов; нет if workspace_id | Runtime + fixtures |
| K03 | Missing/conflicting knowledge → уточнение/handoff; trace содержит реальные sources | Runtime/eval |
| K04 | Publish/revoke во время run не выпускает старый ещё не отправленный ответ; UNKNOWN не повторяется | PG race + wire/restart |
| K05 | Общие опубликованные знания/разрешённое портфолио Business доступны его клиентам; личные данные другого Client и недоступные Business/Workspace изолированы в search/context/media | PG runtime-role + API |
| K06 | Compatible embedding build; failed rebuild не ломает active; semantic relevance и empty result | PG + разрешённый real embedding receipt |
| K07 | Vision читает реальные доступные pixels; не угадывает scale/time/price; injection не управляет tools | Media tests + real synthetic Vision probe |
| K08 | MY_WORK подтверждён; reference не становится портфолио; withdrawn asset не показывается | PG/S3 + UI |
| K09 | Один разрешённый portfolio photo reply, guards/UNKNOWN/restart/no-resend; состояние видно | Controlled wire + browser; live отдельно |
| K10 | Intake исправляем/прослеживаем; COVER_UP handoff; case duration не обещается клиенту | Runtime/eval + browser |
| K11 | Владелец review/publish/revoke без SQL; draft ошибки понятны | Real browser |
| K12 | HUMAN/Resume/currentness и старые source gates сохранены; all features одного accepted candidate | Штатный CI + scoped C8/C0 |

Исполнитель связывает соответствующие строки с конкретными assertions и результатом
в PR; не создаёт ещё несколько независимых matrices/реестров. Число тестов не gate.
Fixtures: два изолированных Workspace и минимум два Client внутри одного; варианты
A fixed/fixed/fixed deposit, B configured formula/rule/percent, C owner/owner/NONE,
D mixed/full payment. В M5 проверяются настройки и честные ограничения, не работа
ещё отсутствующего pricing/payment engine. Не нужен полный декартов перебор.

## 5. Правила выдачи и инженерные ограничения

В каждом задании C0 указывает ID, продуктовый результат, полный base SHA, branch,
одного ведущего, exact write-set, dependency, критерии и что оставлено за границей.
Не выдавать весь этот документ C1/C4 как одно задание «реализовать M5».

M5.1A/B и M5.2A/B интегрированы; текущие paths и source admission задаёт только
CURRENT выше. Допуски предыдущих PR не разрешают автоматически будущие изменения
приложения. Current migration0020; слот0021←0020 выделен только M5.2C с проверкой
C2 до SQL. Новые номера не резервировать цепочкой.

Не менять applied0001–0020, роли/гранты всех старых модулей, исторические schema
checks, native context или `.github/workflows` ради удобства новой функции.
Если additive migration требует current catalog/profile compatibility, перечислить
конкретные затронутые guards/fixtures и доказать изменение. Проблема тестового
harness/locale отделяется от production SQL. Не подгонять expected к неверному
поведению и не разносить огромную test refactor работу по продуктовым задачам.

Сначала targeted unit/actualPG по риску, затем один штатный full CI кандидата.
Повтор запуска — только новое исправление/конкретная причина. Не добавлять новые
универсальные test runners, classifiers, trace registries, очереди или fallback
ради гипотетических будущих случаев. При тупике остановить расширение задачи,
указать cause/evidence/наименьший fix либо предложить явный DEFERRED.

Возврат исполнителя: PR, head, изменённые операции/миграция, относящиеся K-строки,
команды и реальные результаты, ограничения, один следующий шаг. Исторические
артефакты не перепечатывать в CURRENT. Один актуальный статус и краткая выдача;
логи/большие подробности остаются в PR/CI. Никаких auto-merge/VM/paid действий по
факту назначения задачи разработки.

## 6. Действия владельца

Сейчас достаточно передать C4 закреплённую ссылку на CURRENT M5.2C.
PR #45–#49 уже интегрированы. Разработка LOCAL/TEST идёт без нового paid/VM
допуска и без реальных материалов мастера. Новый PR открывает C4 после
подготовки работающего сценария и source admission.

Позже — только конкретное действие по готовому результату:
1. Если понадобится дополнительный real synthetic smoke — отдельные route,
   точные запросы, предел расходов и процедура остановки перед допуском владельца.
   Принятый M5.2A probe заново не запускать.
2. VM/Telegram smoke — отдельный допуск и проверка относящихся к нему receiver
   ограничений; прежние команды не переиспользовать вслепую.
3. Перед реальным бизнесом — подтверждение правил, прав на материалы и data route.
4. Merge нового PR — отдельное действие владельца после C0 review/CI.

## 7. Передача M6

M6 получает принятые service/intake/rule/release identifiers, source provenance,
private Portfolio/DurationCase access и предварительные факты разговора.
Он создаёт ServiceRequest/Assessment, утверждение цены/времени, QuoteAcceptance,
Order/Session и owner decision, не заменяя их результатом Vision или похожим кейсом.
Все OPEN live ограничения переносятся отдельным коротким списком.
