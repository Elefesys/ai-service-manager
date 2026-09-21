# M2 — Telegram, изображения и ручная переписка

Дата подготовки: 2026-09-20. Ответственный за выдачу задач и интеграцию: C0.
Единственный источник статусов: [TASK_REGISTER](../TASK_REGISTER.md).
Этот файл — принятый план и единственная активная точка передачи M2.
Приёмка плана не является evidence выполненной реализации.

## Активное поручение C0 — M2.2-PRIVATE-IMAGES / 2026-09-21

**M1.1–M1.3 и M2.1 VERIFIED в принятых LOCAL/TEST границах.
M2.2 IN_PROGRESS: контракт и поручение выданы, реализация не принята.
M2.3/M2.4 TODO; весь M2 IN_PROGRESS.** Единственный текущий исполнитель — C6
с предметным участием C3 (media/provider) и C2 (DB/migration). M1/M2.1 не повторять.

Repository: `Elefesys/ai-service-manager`. Принятый actual main/base:
**`d3c849d4792f7af60f43eea0f0551659ee3cee5d`** — merge PR #18.
Ветка **`c6/m2-2-private-images`** → main. Продолжить её единственный Draft PR,
созданный C0; номер PR и стартовые head/tree/CI — в PR metadata и готовом поручении
C0. Сохранить первый coordination commit. Локальный synthetic commit из CI archive
не является accepted base. Не создавать параллельный PR/ветку или самостоятельный merge.
Единый технический контракт — [M2_CONTRACT §9](M2_CONTRACT.md#9-m22-private-images--принято-c0c2c3-2026-09-21),
принятый C0 после read-only C2/C3 CONTRACT PASS. Это не C8 review новой реализации.

### Принятый post-merge receipt M2.1

[PR #18](https://github.com/Elefesys/ai-service-manager/pull/18) MERGED пользователем.
Merge parents: `8e5f125d424c0ce613ed9e0c787392f11a49aeae` +
`e9d5b748f19bb7d9d67b014947de3fb29ffc481f`; actual main указан выше.
Tree **`f12aa90a3c3fb7fdfda84290315a3fd820816b4b`** совпадает с принятым final PR tree.
[Отдельный push/main CI 35596593891](https://github.com/Elefesys/ai-service-manager/actions/runs/35596593891)
**SUCCESS**, tested/head SHA = actual merge. Foundation/browser и оба clean-source
gate PASS. Артефакт `10636449171`, SHA-256
`732bfa41912436eba0db8256473585a646f68025f14c2b9c41d8a397c220d11e`:
source tree/recorded SHA/empty status проверены C0, канонические оригиналы сохранены.

192 backend non-integration, **259 real PostgreSQL**, 60 frontend и **15 прежних M1
browser journeys** PASS; migration cycles, generated contracts, reproducibility,
HTTP/worker/scheduler smoke PASS. Это execution на GitHub runner, не локальный Docker.
Реальный независимый **C8-M2.1-KERNEL PASS** покрывает reviewed routing/RLS/worker/
atomicity/UNKNOWN/recovery/Audit и четыре C0 compatibility fixes; его исторический
receipt сохранён ниже. Итоговый PR CI 35595693979 также SUCCESS.

C0 принимает **только M2.1 controlled LOCAL/TEST kernel**: применимые части
A01/A02/A06/A08/A12, внутренняя команда/Jobs/controlled effects A03/A04/A05.
Private binary storage, настоящий Telegram/webhook/rights, messaging HTTP/API/UI
и A11 не подтверждены этим run. M1 browser regression не является M2 E2E.

### Один конечный результат M2.2

Controlled image reference → Message + PENDING FileObject/FETCH Job → validated
private S3 object → READY → live OWNER signed GET. Реальные PostgreSQL и private
S3-compatible LOCAL/TEST сервис. Только внутренние provider/storage/owner boundaries,
без новых HTTP routes, Telegram, UI, owner upload, derivatives/CDN/multipart или M3.

Миграция **0006_private_images.py**, revision **0006 → 0005**, назначена C0/C2.
Применённые 0001–0005 не менять. C2 согласует DDL/functions/backfill и migration
checks; C3 — canonical media permit/provider stream и worker dispatch/recovery.
C6 выбирает конкретный SDK/LOCAL S3 image внутри разрешённого scope по реальной
совместимости и фиксирует version/digest; пользователь не выбирает SQL, поля или tests.

### Разрешённая дельта C6/C3/C2

| Пути | Точная разрешённая причина |
|---|---|
| `backend/src/asm/files/` | Только текущие FileObject capabilities, S3 client, controlled byte provider, validation, transfer/cleanup и внутренний owner read service |
| `backend/src/asm/messaging/{database,results,models,errors,adapter,worker}.py` | FETCH_IMAGE typed refs/explicit dispatch и существующий scheduler cleanup; сохранить SEND/OWNER/UNKNOWN semantics; без нового public command/API |
| `backend/src/asm/tenancy/database.py` | Узкий owner file-read capability через настоящий guarded unit; прежние auth/admission/SQLSTATE/pool guards сохраняются |
| `backend/src/asm/foundation.py` | Schema head 0006, narrow storage config/lifecycle и делегирование; не помещать file domain в entrypoint, не связывать auth/DB health с доступностью S3 без необходимости |
| `migrations/versions/0006_private_images.py` | Только согласованный §9 inventory/FKs/RLS/typed capabilities/FETCH branches и backfill; 0001–0005 immutable |
| `pyproject.toml`, `uv.lock` | Один S3 SDK и image decoder, необходимые typing/transitive dependencies; narrow pinned update, без общего refresh |
| `compose.yaml`, `compose.browser.yaml`, `infra/images.lock.env`, `infra/storage/` | Реальный private LOCAL/TEST S3, bootstrap/bucket credentials/health/persistence и test wiring; новая image pinned digest, прежние pins сохраняются |
| `infra/Dockerfile.backend`, `.dockerignore`, `.gitignore`, `.env.example` | Только необходимые build/runtime inputs, safe storage config/secret/temp exclusions; без секретов в build context, image или artifact |
| `scripts/init_local.py`, `scripts/pin_images.sh` | Добавить отсутствующие LOCAL storage secrets, не выводить/не заменять прежние .env/PG значения; pin только нового storage image без обновления старых digests |
| `scripts/ci.sh`, `scripts/check_backend.sh`, `scripts/test_browser.sh`, `scripts/check_browser_compose.py`, `.github/workflows/ci.yml` | Только необходимое additive real-S3 wiring/lifecycle/evidence; оба штатных scripts/jobs/clean-source и прежние checks остаются; сначала использовать Compose, не переписывать pipeline |
| `tests/test_m2_2_*.py`, `tests/fixtures/m2_2/` | Unit/real PostgreSQL+S3/integration/recovery/private access/migration tests; маленькие synthetic images, без пользовательских данных |
| `tests/test_m2_1_*.py`, `tests/test_postgres.py`, `tests/test_tenancy_postgres.py`, `tests/test_foundation.py`, `tests/test_browser_compose.py`, `tests/test_m1_3_c0_acceptance.py` | Только точные inventory/current revision/config expectations, новые FETCH jobs в прежних image fixtures и необходимый fixture cleanup FK-chain; каждую старую правку объяснить; assertions/guards не убирать и CASCADE не добавлять для обхода FK |
| `docs/tasks/M2_CONTRACT.md`, `docs/tasks/M2_HANDOFF.md`, `docs/TASK_REGISTER.md`, `docs/runbooks/M2_STORAGE_LOCAL_TEST.md` | Уточнения реализации/evidence и конкретный storage setup/troubleshooting; register/handoff остаются единственными статусами, runbook не является вторым поручением |

Общие файлы/зависимости выше явно согласованы C0 для этого среза; повторное разрешение
на рутинные необходимые изменения внутри этих причин не нужно. Применённые migration,
канонические originals, R4/billing, auth/tenancy frozen snapshots, frontend и generated
OpenAPI не менять. Новых HTTP schemas нет: прежний export check должен пройти без
перегенерации контракта ради drift. Если обнаружен иной настоящий scope conflict,
вернуть C0 точную причину и минимальную дельту, не перекладывать выбор на пользователя.

### Конечная проверка M2.2 по единой матрице

1. **A02/A04/A06/A07:** image Message/FileObject/FETCH атомарны, concurrent repeats
   дают один набор; явный FETCH branch; worker работает без human context и без
   открытой DB transaction при provider/S3 I/O. Text/SEND regression прежняя.
2. **A07:** exact original bytes/hash/metadata через real S3 и signed HTTP GET;
   JPEG/PNG/static WebP, 10 MiB/20M pixels/8192-side/one-frame validation. Проверить
   missing/malformed/truncated/animated/unsupported/oversized input и ложные headers.
   Anonymous GET/LIST/PUT denied; tampered и реально expired URL отвергаются.
3. **A08/A07:** live OWNER, revoked/downgraded membership, Workspace A/B и неверная
   связка Conversation/Message/FileObject внутри Workspace; PENDING/FAILED не выдаются.
   Signed GET TTL 60 s и возможность прежнего bearer grant до expiry после revoke
   проверяются отдельно. Нельзя выдать raw provider/bot URL или секреты в логах.
4. **A04/A07:** bounded retry/exhaustion; реальные crash после durable intent/PUT/
   READY commit, lost ACK и stale claim; новый READY нельзя перезаписать старым PUT.
   Проверить late PUT после первого cleanup DELETE, повторную очистку и её outage/
   lease reclaim; WINNER не удаляется. SEND UNKNOWN/no-resend остаётся доказанным.
5. **A12:** clean/repeated upgrade, переход с данными 0005 (text/image/disconnected
   image/billing/receipts/UNKNOWN) и согласованный TEST downgrade/re-upgrade;
   исходные Message/fingerprints и M1 сохраняются. Backfill без внешнего I/O.

Штатные **`sh scripts/ci.sh`**, **`sh scripts/test_browser.sh`**, оба clean-source gate,
contracts/migrations/reproducibility обязательны. PostgreSQL/S3 не заменять mock.
При отсутствии Docker локально использовать обычный GitHub runner; архив/логи
привязать к exact head/tested SHA/tree. При failure сначала определить дефект
реализации или теста; объяснить изменение принятой проверки, не удалять её ради CI.

C6 возвращает один PR, base/head/tree/tested SHA, changed paths, migration/SDK/image
version, tests/assertions→строки матрицы→run/results, sanitized operational notes и
оставшиеся blockers. Первый coordination commit сохранить; final SHA/CI фиксировать
в PR, без SHA-only doc chains. Не объявлять самостоятельно INTEGRATED/VERIFIED.
C0 затем проверит результат и организует **реальный независимый scoped C8 review**
private-file authorization/validation/worker/cleanup risks. C2/C3 CONTRACT PASS
не является этим review. После green final head/C0/C8 — пользовательский merge,
отдельный actual main CI; только затем поручение M2.3.

### Telegram smoke — текущая внешняя граница

Со слов пользователя готовы test bot, Business/Secretary Mode, Owner/Client accounts;
TG_BOT_TOKEN и отдельный TG_WEBHOOK_SECRET сохранены в менеджере паролей.
Секреты не получены и не требуются для M2.2. Runtime injection, connection binding/
rights, тестовый HTTPS endpoint и живой A11 ещё не проверены. C0/C6 дадут конкретную
безопасную инструкцию для тестового deployment при M2.3; tokens не присылать в чат/PR.
LOCAL/TEST storage не требует облачного аккаунта/оплаты. Платную инфраструктуру
предлагать только с конкретной ценой до подключения; отсутствие её не блокирует M2.2.

## 1. Исходная точка и результат

M1.1, M1.2 и M1.3 приняты в согласованных границах LOCAL/TEST.
Документы финальной приёмки M1 находятся в main после
[PR #16](https://github.com/Elefesys/ai-service-manager/pull/16):
`38bbb975c189ed445dc4b825ca189f3a80de9814`.
[Push/main CI 35513585580](https://github.com/Elefesys/ai-service-manager/actions/runs/35513585580)
— SUCCESS, оба clean-source gate пройдены. Это исходный snapshot подготовки
данного плана, а не неизменный base всех будущих задач. Перед выдачей каждой
зависимой задачи C0 назначает фактически принятый commit main.

**Продуктовый результат M2:** тестовый клиент пишет текст и присылает изображение
в Telegram-аккаунт бизнеса; владелец видит переписку и изображение в Console,
отвечает текстом, клиент получает ответ. Повторы событий и перезапуск worker
не теряют подтверждённые входящие сообщения; проблемы отправки видны владельцу.
Данные разных Workspace изолированы.

Ведущий transport — connected business bot / Profile Automation по ADR-020.
Подмена его standalone bot ради удобного smoke не закрывает этот сценарий.
Нативные сообщения владельца, правки, удаления и неподдерживаемые типы событий
получают явную семантику в контракте; их нельзя молча принять за новое сообщение клиента.

Не входят: AI, Turn/control-generation/takeover/resume M3, оценка тату/цены,
запись, платежи, SaaS checkout, дополнительные каналы и полный Ops-интерфейс.
Прайс, портфолио и депозит реального мастера не нужны.
Минимум UI — просмотр входящих текста/изображения и исходящий текст.
Отправка владельцем файлов и редактирование сообщений из Console не добавляются
автоматически: их необходимость C0 сверяет с принятым scope.

## 2. Источники и порядок решений

Прочитать `AGENTS.md`, [стек IMPL-001](../decisions/IMPL-001-stack.md),
[Spec](../architecture/01_ARCHITECTURE_SPEC.md) §§4, 17.5, 18, 19, 24.6,
[ADR](../architecture/02_ARCHITECTURE_DECISIONS.md) 019–021, 115, 121–128, 138–140,
[Roadmap M2](../architecture/07_DEVELOPMENT_ROADMAP.md),
[план M2.1–M2.4](../architecture/09_IMPLEMENTATION_PLAN.md)
и [OPEN-052/085](../architecture/04_OPEN_QUESTIONS.md).

Канонические файлы v0.28 и SOURCE_MANIFEST остаются исходным снимком.
Незаполненные детали реализации решает C0 в границах канона; не каждая такая
деталь требует согласования пользователя. Если обнаружено противоречие
принятому решению, сначала назвать конфликт и минимальное предлагаемое изменение.
Не превращать исторический запрет Jobs в M0/M1 в запрет реализации Jobs в M2.

Завести один `docs/tasks/M2_CONTRACT.md`: сначала достаточный контракт M2.1
и границы следующих частей, затем дополнять его только для очередного среза.
Не требуется заранее проектировать весь M2 или будущие milestones.
Решение должно объяснять, как оно обслуживает конкретный сценарий/инвариант.
Число таблиц, endpoint и тестов само по себе не является критерием качества.

## 3. Последовательность C0

| Шаг | Исполнитель / участие | Что сделать | Условие перехода |
|---|---|---|---|
| Подготовка | C0, предметная проверка C2/C3 | Проверить main/CI и этот docs PR; прочитать существующий код, определить минимальный контракт M2.1 и границы файлов; заранее запросить доступы для будущего живого smoke | Scope и критерии M2.1 согласованы, назначены точный base, ветка и одна текущая задача |
| M2.1 | C3 + C2; C1 для общей backend-границы | Нормализованные события; ChannelConnection/Route и необходимые Client/Identity/Conversation/Message; durable Inbox/Outbox/Jobs в PostgreSQL; синтетический adapter для проверки ядра | Реальная PostgreSQL проверяет ingestion, дедупликацию, tenant context, транзакции, lease/reclaim и отправку через контролируемый adapter; принятый main |
| M2.2 | C6 + C3; C2 для миграции, C1 для доступа | Минимальный ObjectStorage adapter, FileObject и загрузка изображения из provider file reference; приватный bucket, авторизованная выдача, ошибки и очистка временных/осиротевших данных | Рабочий storage path через реальный S3-совместимый сервис в тестовом окружении; изоляция и отказы проверены; принятый main |
| M2.3 | C3; C1 для Console API, C6 для подключения | Официальный Telegram adapter, verified webhook, привязка connection, capabilities, text/image normalization, отправка и UNKNOWN; минимальный API чтения переписки/изображения и ручного ответа | Adapter и API проверены; OpenAPI/generated contracts актуальны; тестовое подключение подтверждено либо явно отмечено внешним блокером |
| M2.4 | C5 + C3; C8 для независимой проверки рисков | Список диалогов, история, изображение, текстовый ответ, состояния доставки/подключения; browser journeys и полный живой сценарий | Все применимые критерии ниже закрыты; фактический main CI успешен; C0 принимает M2 и только затем выдаёт M3 |

Это последовательная очередь, а не поручение одновременно реализовать четыре
части. Внутри M2.1 допустимы небольшие DB/backend срезы по общему контракту.
Миграции выдаёт C0/C2 по одному после проверки текущего Alembic head; 0001–0004
уже применены и не переписываются. Номер следующей миграции не резервируется
навсегда в этом плане.

Раннюю проверку доступности Telegram-аккаунта/прав можно выполнить до реализации
adapter, не объявляя M2.3 выполненной. Недостающие внешние доступы не блокируют
ядро, storage tests с локальным сервисом и UI через тестовый adapter.
Но тестовый adapter не является доказательством работы Telegram.

## 4. Что решить перед реализацией соответствующей части

**M2.1 — доверие и надёжность.**
Описать идентификаторы и ключи дедупликации, связь provider/bot/connection/chat
с Workspace, порядок durable Inbox → acknowledge → обработка и атомарность
канонического состояния с Outbox. Дубли webhook и повторы ручной команды —
разные уровни идемпотентности. Для повторной команды нужны стабильный ключ,
fingerprint, прежний результат и конфликт при другом содержимом.

Webhook не имеет owner session: проверка provider envelope, ограниченная
до-tenant маршрутизация и обработка неизвестного connection должны быть
спроектированы явно. Worker использует доверенный контекст, полученный из
сохранённого задания и connection; не принимает Workspace из произвольного
payload как разрешение и не выдаёт себя за вымышленного Owner.
Не ослаблять RLS/runtime роли ради фоновых заданий.

Зафиксировать минимальные состояния Inbox/Outbox/Job, lease/claim token,
ограниченные retry/backoff, reclaim после падения и видимый terminal failure.
Внешний HTTP выполняется вне DB-транзакции. Просроченный worker не может
перезаписать результат нового владельца lease. Падение после возможной отправки,
но до записи результата рассматривается отдельно: повторный claim сам по себе
не даёт права повторить внешний эффект. Нужны отдельные тесты этой границы.

**M2.2 — файлы.**
В БД — metadata и связь с Message/Workspace, бинарные данные — private Object Storage.
Определить поддерживаемые image types, проверку содержимого/размера, пределы
скачивания, состояния pending/ready/error, обработку повторов и сирот.
Provider file reference не заменяет канонический файл. Не передавать браузеру
URL с bot token, не сохранять token/секреты в логах.
Временная выдача файла — только после актуальной авторизации связанной сущности.
Для signed URL явно задать короткий TTL и границу отзыва: уже выданная bearer-ссылка
может действовать до истечения TTL; нельзя обещать немедленный отзыв без механизма.
Нужные методы storage adapter реализовать реально; speculative multipart/CDN
и общую media-platform не строить.

**M2.3 — provider и API.**
Определить безопасную процедуру подтверждения связи аккаунта бизнеса с Workspace
(для теста допустима ограниченная документированная процедура настройки).
Не разрешать захват чужого connection по одному переданному ID.
Спроектировать webhook boundary отдельно от owner session/CSRF; не отключать
защиту Console глобально, чтобы Telegram смог обращаться к webhook.

Перед включением исходящих сообщений проверить активность connection, права
и применимые ограничения отправки; определить эффект отзыва прав между постановкой
в очередь и исполнением. Описать отражение нативного ответа владельца/echo,
правок/удалений/неподдерживаемого media без дублирования сообщений и циклов.
Задать минимальные owner routes/DTO/errors/pagination, authorization, CSRF,
идемпотентность и восстановление ответа после неоднозначного HTTP исхода.
Определить применимые permissions, service-mode/entitlement checks и Audit events,
сохранив инварианты M1. Расширение этих контрактов для M2 должно быть явным;
не подменять фиксированные TEST entitlement keys новым бизнесовым смыслом.

Telegram подтверждает принятие send-запроса, а не обязательно прочтение клиентом.
`UNKNOWN` не маскируется под `FAILED` или успешную доставку.
Без доказанной provider idempotency/reconciliation гарантии timeout/crash
не приводит к автоматической повторной отправке. Повтор по инициативе владельца
также требует понятного предупреждения о возможном дубле и принятой семантики;
кнопка retry не должна скрыто обещать exactly-once.

**M2.4 — один повседневный сценарий.**
Использовать существующую Console и принятый API SHA. Начать с простого обновления
списка/истории; WebSocket вводить только при доказанной необходимости.
Показать pending/error/UNKNOWN/route-unavailable доступным человеку языком,
а не техническими traceback. Повтор UI-запроса сохраняет идентичность того же
намерения. Для диагностики достаточно узких действий/команд и понятного статуса;
полный Action Center/Ops относится к следующим этапам.

## 5. Единая матрица приёмки M2

Это принятая C0 конечная матрица по канону, подтверждённая при выдаче
контракта M2.1. В evidence указывать фактический test/scenario и проверенный SHA/run,
а не только номера критериев или суммарное число tests.
Промежуточные срезы закрывают применимые строки, итог M2 — все строки.
Новые строки добавляются только с причиной и изменением scope, не ради числа.

| ID | Наблюдаемый результат | Основание / часть | Нужное evidence |
|---|---|---|---|
| M2-A01 | Поддельный webhook отклонён; неизвестный/чужой connection не получает доступ к Workspace | Spec §4, ADR-122; M2.1/3 | Негативные boundary/API и реальные DB проверки |
| M2-A02 | ACK только после durable Inbox; дубликат не создаёт второй Message; crash до обработки восстанавливается | ADR-121/122; M2.1 | PostgreSQL: commit/rollback, повтор webhook, restart/reclaim |
| M2-A03 | Каноническая мутация и Outbox атомарны; повтор команды возвращает прежний результат, иной payload конфликтует | ADR-123/124; M2.1/3 | Реальные транзакционные/конкурентные тесты через рабочий command path |
| M2-A04 | Lease/reclaim не теряет задание; stale worker не перезаписывает результат; retry ограничен, исчерпание видно | ADR-125/127; M2.1 | Worker + PostgreSQL с контролируемым adapter, без HTTP внутри бизнес-транзакции |
| M2-A05 | Неоднозначная отправка остаётся UNKNOWN и не вызывает blind resend, в том числе после crash | ADR-128; M2.1/3 | Fault injection вокруг внешней отправки и фиксации результата |
| M2-A06 | Текст/изображение принадлежат верному диалогу; echo/правки/удаления/unsupported events имеют явный результат | Spec §§4.6–4.9; M2.1/3 | Fixtures реального формата и adapter integration; provider ограничения отмечены |
| M2-A07 | Изображение сохранено приватно; незавершённая загрузка не выдаётся как готовая; ошибки/повторы обработаны | Spec §§17.5,19.4–5, ADR-138; M2.2 | БД + работающий S3-compatible сервис, проверка типа/размера/ошибок |
| M2-A08 | Workspace A не читает переписку/файл и не отправляет от B; отозванный доступ не выдаёт новый file URL/command | M1 invariants, Spec §17; все части | Runtime-role PostgreSQL и API negative tests, проверка TTL границ signed URL |
| M2-A09 | Отзыв connection/rights, закрытое окно и provider errors видны; отправка не обходит ограничения | ADR-020/021, OPEN-052; M2.3 | Детерминированные adapter tests плюс проверка фактических прав тестового аккаунта |
| M2-A10 | Owner видит текст/картинку, отвечает; refresh/retry не создаёт второй локальный intent | Roadmap M2, M2.4 | Browser journeys через реальный backend/БД/storage; тестовый Telegram adapter обозначен |
| M2-A11 | Реальный тестовый connected business bot принимает текст/картинку и отправляет ручной ответ из Console | Roadmap M2, M2.3/4 | Живой smoke на разрешённых тестовых аккаунтах; версия кода, дата, очищенные provider IDs/результат |
| M2-A12 | Миграции воспроизводимы, прежние инварианты M1 сохранены; интегрированный main проходит CI | Общая DoD плана §11 | Штатные CI/migration/contract/clean-source gates на фактическом main после интеграций |

Не заменять реальные DB tests SQLite/mocks или ad hoc SQL, обходящим проверяемую
production command. Тесты должны проверять поведение и нарушения инварианта.
При падении сохранять исходную ошибку, различать дефект теста и дефект реализации.
Изменять тест для нового принятого поведения можно с объяснением; удалять guard
ради зелёного CI нельзя. Старое точное перечисление таблиц требует осмысленного
дополнения inventory, а не бессрочного запрета новых таблиц.

Независимая проверка C8 соразмерна новому риску: routing/RLS, side effects/recovery,
private files и сквозной путь. Самопроверка C0 не называется независимой C8.
После исправления проверяется изменённая область и обязательный CI;
не начинать заново весь прошлый аудит без конкретного основания.

## 6. Работа с внешними доступами

Для живого smoke C0/C6 заранее дают пользователю короткую инструкцию:
тестовый Telegram bot с нужным режимом, отдельный аккаунт бизнеса и клиент,
подтверждённые права, безопасная настройка bot/webhook secrets и достижимый HTTPS
endpoint. Сообщения отправляются только в явно согласованные тестовые диалоги.
Не запрашивать token в переписке/PR; показать, куда его поместить в окружении/secret store.
Webhook secret — отдельное значение, не bot token.

Для разработки файлов достаточно private S3-compatible сервиса в LOCAL/TEST;
настройка реального облачного bucket/ключей требуется при выбранном внешнем smoke.
Покупка услуг/инфраструктуры отдельно согласуется после предложения конкретного
варианта и стоимости. Успех локального эмулятора не доказывает готовность облака.
Public HTTPS требует отдельного ограниченного тестового deployment/config решения
C6: текущий LOCAL/TEST Compose с loopback не является готовым интернет-развёртыванием.

На 2026-09-20 официальная [Bot API документация](https://core.telegram.org/bots/api)
описывает webhook secret header, права BusinessBotRights.can_reply и окно ответа
для активных личных чатов. Также проверить текущие события BusinessConnection,
лимиты getFile и доступность режима в конкретном аккаунте.
[Connected business bots](https://core.telegram.org/api/bots/connected-business-bots)
— дополнительный официальный источник. Проверка документации не заменяет
живой аккаунтный probe; его результат записать отдельно, OPEN-052 не закрывать навсегда.

Если доступ отсутствует, продолжать независимую реализацию. В реестре явно
указать блокер только соответствующей проверки. Можно принять LOCAL/TEST срезы,
но полное M2 не VERIFIED до M2-A11. Не создавать новую архитектуру или fake
production-параметры для обхода отсутствующего доступа.

## 7. Правила передачи и завершения

- Один актуальный task register и этот handoff; контракт хранит технические решения.
  История M1 не выдаёт новых задач. Не создавать несколько файлов «текущий статус».
- Каждая выдача: ID, цель, принятый full base SHA, ветка/PR, разрешённые области,
  конкретный результат и применимые строки матрицы. Общие файлы/миграции координирует C0.
- Рутинные решения реализации и исправления в выданном scope выполнять без
  повторных вопросов пользователю. Настоящий scope conflict описать до расширения.
- Сохраняется порядок ручного merge пользователем после C0 acceptance/зелёных
  обязательных checks. При запросе merge дать один URL PR и точное действие.
  Не просить слить Draft/непроверенную версию; Ready for review готовит C0.
- После каждого merge C0 проверяет фактический main и его CI. Следующий исполнитель
  получает этот принятый base, не PR head/virtual merge. Отсутствие ответа инструмента
  требует чтения состояния, а не повторного слепого merge.
- Source/hash/CI gates сохраняются; результаты фиксируются один раз в PR/evidence
  и в очередном содержательном обновлении реестра. Не делать бесконечную цепочку
  commits только ради записи SHA предыдущего документа.
- В каждом отчёте C0: что принято, текущий единственный следующий шаг, конкретный
  блокер/действие пользователя либо «действий пользователя сейчас нет».
  Не выдавать подготовленные инструкции за уже выполненную работу исполнителя.
- M2 закрывает C0 после полного сценария и матрицы. M3 выдаётся отдельной задачей;
  production, AI и платежи не становятся готовыми от закрытия M2.

## Исторические поручения — не текущие инструкции

Ниже сохранены прежние записи M2.1. Действуют только активный блок в начале
этого файла и актуальный TASK_REGISTER; повторные merge/старты по истории не нужны.

## История — M2.1 pre-merge поручение и receipts / 2026-09-21

**Исторический snapshot; не текущее поручение.** PR #18 уже MERGED и принят
по actual main CI в активном блоке выше. Старые merge/BLOCKED инструкции не выполнять.

**M2.1 REVIEW: pre-merge C0 PASS и независимый scoped C8 PASS.
M2.2–M2.4 TODO.** Перед merge обязателен green CI итогового head. M1 не повторять.
PR #17 MERGED; проверенный actual main/base:
**`8e5f125d424c0ce613ed9e0c787392f11a49aeae`**.
[Отдельный push/main CI 35522542861](https://github.com/Elefesys/ai-service-manager/actions/runs/35522542861)
SUCCESS; head/tested SHA=actual merge, tree `3e2a2519c949461856c9f3c5ca1d1ec33a180953`,
оба jobs/clean-source gates PASS. Post-merge receipt находится в [PR #17](https://github.com/Elefesys/ai-service-manager/pull/17).

Repository: `Elefesys/ai-service-manager`. Ветка: **`c3/m2-1-messaging-kernel`** → main.
Продолжать единственный [PR #18](https://github.com/Elefesys/ai-service-manager/pull/18)
этой ветки; итоговые head/tree/tested SHA и CI находятся в его C0 receipt. Первый
coordination commit сохранить. Main/base — SHA выше; локальные synthetic commits
из CI archive не являются GitHub base. Не начинать заново от старой M1 ветки.

Ведущий исполнитель **C3**, DB/migration часть согласована с **C2**. C0 принимает
контракт и интеграцию. Единый технический контракт: [M2_CONTRACT](M2_CONTRACT.md).
Он принят предметной сверкой C0/C2/C3. Реализация прошла C0 acceptance и
независимый scoped C8 review; интеграция в main ещё не выполнена.
Один работающий срез: controlled event → durable Inbox/Job → Message правильного
Workspace → owner manual text command → atomic receipt/Audit/Outbox/Job → controlled
send/recovery. Проверьте существующий код и контракт перед изменениями.

### Разрешённая дельта

| Область | Разрешение и причина |
|---|---|
| `backend/src/asm/messaging/` | Только используемые normalized models/validation/errors/policy, repository/DB capabilities, commands, worker/recovery и controlled adapter текущего kernel |
| `migrations/versions/0005_messaging_kernel.py` | Revision `0005`, down_revision `0004`; C0/C2 назначили этой ветке. Новые messaging tables/typed commands/RLS/constraints и описанная Audit compatibility |
| `backend/src/asm/foundation.py` | DATABASE_SCHEMA_REVISION=0005 и делегирование worker/scheduler реальному durable kernel; сохранить lifecycle/readiness/runtime role guards |
| `backend/src/asm/tenancy/database.py` | Только узкие messaging owner calls через существующий guarded unit и взаимное исключение owner/worker units; guards, auth admission и SQLSTATE mapping не ослаблять |
| `backend/src/asm/billing/models.py` | Один strict Audit variant MESSAGE_SEND_REQUESTED; прежние billing DTO/контракты сохраняются |
| `contracts/openapi.json`, `contracts/README.md` | Generated additive Audit schema/consumer note; новых messaging HTTP routes нет |
| `frontend/src/billing-api.ts`, `frontend/src/BillingPanel.tsx` | Только strict Audit type/parser и правильная подпись нового event; contact/recovery/navigation/layout без переработки |
| `frontend/src/billing-api.test.ts`, `frontend/src/BillingPanel.test.tsx` | Mixed Audit compatibility и неверные discriminators/payloads; прочие frontend изменения не выдаются |
| `tests/test_m2_1_*.py` | Существенные kernel/unit/real-PostgreSQL/recovery/migration/mixed Audit API проверки |
| `tests/test_tenancy_postgres.py`, `tests/test_m1_3_postgres.py`, `tests/test_foundation.py`, `tests/test_m1_3_http_contract.py` | Только объяснённые новые table/function/Audit inventory, текущий schema head и добавление нового strict Audit schema; прежние защитные кейсы сохраняются |
| `scripts/provision_local_auth.py`, `scripts/m1_3_browser_fixture.py` | C0 согласовал 2026-09-21: точное сравнение с `DATABASE_SCHEMA_REVISION`; LOCAL/TEST, DB/identity/password guards сохраняются |
| `tests/test_postgres.py` | C0 согласовал: ровно 10 новых messaging tables в закрытом inventory, `jobs_enabled=true`, `mode=controlled`; role/SIGTERM/shutdown assertions сохраняются |
| `tests/test_m1_3_c0_acceptance.py` | C0 согласовал: только `platform.messaging_command_receipts` в существующем TRUNCATE; TABLES/counters/assertions/FK/rollback не меняются, без CASCADE |
| `docs/tasks/M2_CONTRACT.md`, `docs/tasks/M2_HANDOFF.md`, `docs/TASK_REGISTER.md` | Реализационные уточнения и фактическое evidence; один register/active handoff |

Audit compatibility — необходимое сохранение работающего M1 consumer: его строгие
backend/frontend discriminators сейчас отвергают новые events. Разрешён ровно один
новый typed variant с tenant-safe Message FK, без generic payload и скрытого фильтра.
Это не выдача UI переписки M2.4. Точные SQL имена/индексы и модульное разбиение внутри
разрешённых областей C2/C3 выбирают самостоятельно по принятому контракту.

`0001`–`0004`, `app.current_workspace_id()`, frozen auth/tenancy snapshots,
R4 TEST catalog/EntitlementService semantics, authentication/CSRF/CORS, dependencies,
locks, CI/Compose/bootstrap, canonical originals и остальные frontend пути не менять.
Необходимую иную совместимую дельту сначала показать C0 с конкретной причиной;
не отправлять пользователю выбор SQL/полей. Нельзя отключать inventory/clean-source
или ослаблять guards ради CI. M2.1 не требует новых платных ресурсов или секретов.

### Конечные критерии M2.1-KERNEL

1. **A01/A02/A06, частично:** trusted source binding и immutable route определяют
   Workspace; durable Inbox+Job до accepted result; duplicate/conflicting event и
   другой event ID с прежним Message ID обработаны; image reference/ignored kinds
   имеют явный результат. Это kernel evidence, не real webhook verification.
2. **A03:** рабочая owner command, same-key replay/conflict и real concurrency;
   ровно один Message/receipt/Audit/Outbox/Job; rollback любого звена не оставляет
   частичного состояния. Python/DB fingerprints совпадают по конкретным bytes.
3. **A04/A05:** реальные worker/scheduler, lease/reclaim/backoff/bounds/DLQ;
   stale/malformed/expired/чужой claim не мутирует результат; adapter вызывается
   вне DB unit. Fault barriers до/после commit/start/effect/finalize подтверждают
   UNKNOWN без blind resend, safe NOT_SENT retry и late-result/commit-ACK recovery.
4. **A08, частично:** runtime-role OWNER против ADMIN/PROVIDER, разные Workspace,
   mismatched Client/Conversation/connection/job refs внутри одного Workspace,
   revoked OWNER/connection до begin_send, непротекающий user/worker XID/task/pool
   context. Worker не получает старый billing/Business доступ или общий SQL setter.
5. **A12, частично:** clean upgrade и upgrade с данными 0004, повтор upgrade,
   downgrade/re-upgrade в disposable TEST, old billing FK/check/receipt semantics,
   mixed Audit через существующий API и frontend consumer. Фактический main CI
   закрывается только после последующего пользовательского merge этого среза.

Штатные gates: **`sh scripts/ci.sh`**, **`sh scripts/test_browser.sh`** и оба
clean-source gate; generated contracts проверяются штатным export check.
Docker/real PostgreSQL обязателен для DB evidence. Если Docker отсутствует локально,
использовать обычный GitHub runner, получить logs/artifact и привязать результат к
head/tested SHA/tree. SQLite/mock не заменяют PostgreSQL. Новые тесты не подменяют
исходный failure: сначала установить, дефект теста это или поведения.

По результату C3 возвращает PR/head/tree и tested SHA, changed paths, миграцию,
контрактные уточнения, tests/assertions → строки матрицы → run/results, оставшиеся
ограничения и blockers. Не объявлять M2.1 INTEGRATED/VERIFIED или весь M2 завершённым.
C0 завершил review результата и отдельный независимый C8 review новых
routing/worker/RLS/side-effect risks — receipt ниже. После SUCCESS итогового head
C0 снимает Draft и даёт пользователю одну инструкцию обычного merge commit.
После merge — actual main CI, затем одна задача M2.2. Самостоятельный merge запрещён.

### Исторический receipt C0/C8 — M2.1 pre-merge / 2026-09-21

**C0 PASS; C8-M2.1-KERNEL PASS.** Блокирующих дефектов в принятой области не найдено.
Исходный C3 head `2c7ada9b8b9b13956a56bd13e0a4f9f5b4cb33ae`, tree
`5f2a53bfd43341d128a3a7d33bcfb478ace1d54b`, run 35593328892 проверены C0 по GitHub
и CI archive. Девять failures подтверждены traces: provisioning revision (1),
FK-dependent TRUNCATE (5), exact inventory (1), исторический Jobs shutdown flag (2).
Browser остановился на том же provisioning; второй script имел такой же guard.
C0 согласовал и применил только четыре перечисленные compatibility дельты.
Не ослаблены assertions, FK, SQLSTATE/auth/tenancy guards или штатный pipeline.

Проверенный implementation head: **`e772c2a92bb38cb0af869ef77ed36b2df9fcaf59`**;
tree **`0df5224f9a31e3e7820aa269236e5383fc2347d5`**.
[Полный CI 35594839363](https://github.com/Elefesys/ai-service-manager/actions/runs/35594839363)
**SUCCESS**. Tested virtual merge **`9ba971d07db647bec3fed1691ae888b4ce0e3a81`**
имеет parents accepted main + implementation head и тот же tree. Coordination
commit сохранён; GitHub compare: ahead 4, behind 0, merge-base = accepted main.
Artifact `10636510359`, SHA-256
`62a7c5169af38d960945aa4eaa51017764cb944822cf2f1a12b5546ec33ae719` проверен C0;
162 source files побайтно совпадают с reviewed tree; tested SHA точный, status пуст.

| Проверка | Фактический результат и граница |
|---|---|
| `sh scripts/ci.sh` | PASS: Ruff/format/strict mypy, 192 backend non-integration, 259 real PostgreSQL, clean/repeated/full downgrade/upgrade, generated contracts, wheel/frontend reproducibility, HTTP/worker/scheduler smoke |
| `sh scripts/test_browser.sh` | PASS: 60 frontend tests и 15 реальных прежних M1 browser journeys через API/PostgreSQL; это ещё не UI переписки |
| Clean-source | Оба штатных gate PASS; не подменены пустым recorded status |
| Scope/source | 34 изменённых paths после четырёх согласованных добавлений; `0001`–`0004`, frozen auth/tenancy, R4 billing logic, dependencies/locks/CI/Compose и 11 canonical originals сохранены |
| C0 review | Разрешённый kernel/Audit scope, принятый контракт, сохранность M1, существенные assertions и execution evidence сверены; исходные failures объяснены совместимостью, проверки не удалены |
| Независимый C8 | Отдельный read-only reviewer `c8_m21_kernel_review`, не автор C2/C3 и не C0 self-review: routing/dedupe, composite FK/FORCE RLS/grants, worker authority/XID/task/lease, live OWNER/atomic intent, UNKNOWN/late-result/finalize ACK и Audit compatibility; четыре C0-правки включены; PASS без blocker |

Критерии остаются M2-A01…A12 из единой матрицы ниже. Конкретная таблица
`tests/assertions → критерий` в сохранённом C3 receipt сверена C0/C8 и применяется
к успешному run выше: новые kernel tests после исходного C3 head не менялись.
Проверены реальные process crashes с внешним сохраняемым счётчиком, concurrency,
rollback каждого звена, stale/forged claims, revocation, bounded retry и отсутствие
DB connection при adapter call. PostgreSQL исполнен GitHub runner; локального
Docker и отдельного локального PostgreSQL rerun C8 нет. C8 прочитал execution logs;
привязку archive/tree отдельно проверил C0.

Граница приёмки: controlled LOCAL/TEST kernel. A01/A02/A06 — kernel routing,
durable ingestion и normalized image reference; A03/A04/A05 — внутренняя команда,
Jobs и controlled effects/recovery; A08 — kernel isolation; A12 — pre-merge
regressions/migrations. Реальная webhook verification/Telegram rights, private
binary storage/выдача, messaging HTTP/API, Conversation UI и M2-A11 не выполнены.
M1 browser regression не заменяет будущие journeys M2.4. M3 не выдан.

Этот commit согласованно обновляет только TASK_REGISTER/M2_HANDOFF. Финальный
head/tree/tested SHA и SUCCESS именно итогового head C0 дописывает в PR receipt
после CI, без следующего SHA-only documentation commit. Для документационной
дельты повтор полного C8 review не нужен: C8 явно подтвердил эту границу.
До green final-head gates PR не готовится к merge. После них — Ready for review,
пользовательский **Create a merge commit → Confirm merge**; затем C0 проверяет
actual merge/main push CI и принимает только M2.1. M2.2 пока не выдана.

### История — исполнение C3/C2 до решения C0, 2026-09-21

Следующая запись сохранена как историческая. Её BLOCKED/запрос scope exception
закрыты текущим receipt выше и больше не являются активным поручением.

[Draft PR #18](https://github.com/Elefesys/ai-service-manager/pull/18) продолжен от
`587531e71380a9a83549cba25c1b5c71c01d223c`; coordination commit и принятый base
сохранены. C2 подготовил migration `0005` (down_revision `0004`), typed SQL
capabilities, RLS/constraints, Audit FK и schema/cycle tests в отдельном checkout.
C3 добавил normalized codec, owner command/read, отдельный task/XID-bound worker
unit, реальные worker/scheduler и controlled adapter с сохраняемым TEST ledger.
C2 participation — авторство DB-части, не независимый C8 review.

Первый implementation run:
[CI 35592297034](https://github.com/Elefesys/ai-service-manager/actions/runs/35592297034),
head `7ef132fdc040eef5c6caf17d9c7aae3f40a46a58`,
tree `afc90a8673fc506fab996266401169fedc62efac`,
tested PR merge `ee6f051d772af0060a367d6967f8574e005087a7`.
Artifact `10635275472`, SHA-256
`dedaf48c017051ae14640104f9282b86678228edd3e5472729467b544f686e25`;
archive побайтно совпадает со всеми 162 файлами head, recorded worktree status пуст.
Это не заменяет два clean-source gates: оба пропущены после failures.

Runner выполнил штатные `sh scripts/ci.sh` и `sh scripts/test_browser.sh`:
192 backend non-integration PASS, 61 frontend PASS, PostgreSQL 241 PASS / 10 FAIL.
Один новый тест неправильно ловил ожидаемый DB отказ внутри уже aborted unit;
исправлено положение `pytest.raises` с сохранением обязательного rollback.
Другие 9 failures и browser provisioning относятся к четырём неразрешённым файлам
ниже. Дополнительно C2 закрыл обход canonical timestamp через raw SQL и добавил
8 cases; удалён случайный повтор одного нового frontend case (итоговый набор — 60).
Итоговые head/tree/tested SHA и повторный run фиксируются в PR receipt после push;
отдельного SHA-only commit не требуется.

| Критерий handoff | Конкретные tests/assertions нового kernel |
|---|---|
| A01/A02/A06, частично | `test_trusted_route_binding_and_concurrent_durable_event_dedupe`: source/route mismatch, concurrent identical event, exact conflict, durable Inbox+Job; `test_image_reference_message_projection_dedupe_and_identity_conflicts`: Message ID projection, image reference, client/conversation identity conflicts; ignored kinds имеют terminal receipt/result |
| A03 | `test_manual_fingerprints_replay_concurrent_atomic_intent`: Python/DB exact UTF-8 fingerprints, concurrent replay/conflict и один intent; `test_command_rollback_at_every_atomic_link`: failure на каждом Message/receipt/Audit/Outbox/Job откатывает все звенья; actor/body/key проверяются live |
| A04/A05 | `test_lease_reclaim_new_token_stale_claim_and_retry_age`, `test_safe_not_sent_jitter_and_exhaustion_count_every_call`: DB-clock lease, новый token, jitter, count/age bounds; durable UNKNOWN и terminal failure; `test_actual_process_crash_restart_durable_effect_ledger` + inbound/ingest boundaries: реальные os._exit/restart, внешние call/effect counters, ноль повторов после возможного эффекта |
| A04/A05, finalize | `test_lost_finalize_ack_reads_canonical_success_and_replays_exact_outcome`, `test_finalize_not_sent_ack_loss_and_changed_claim_exact_replay`: canonical saved result после commit ACK loss, не понижать SENT, старый claim после нового не принимается; cancellation/timeout/late finalize не возвращают dispatch в READY; adapter не держит DB unit |
| A08, частично | `test_owner_only_live_admission_replay_and_cross_workspace_reads`, revoke matrix и composite-ref tests: OWNER/ADMIN/PROVIDER, чужие Workspace и неверные связи внутри одного; forged claim/GUC, XID/task/autocommit/pool negative tests; runtime не читает control tables и не пишет app tables напрямую |
| A12, частично | `test_0004_data_survives_upgrade_repeat_downgrade_reupgrade`: существующие billing rows/receipt/Audit, repeated upgrade, downgrade/re-upgrade; schema inventory/RLS/FKs/checks; `test_mixed_billing_message_audit_http_cursor_and_strict_payload` + frontend parser/component: два прежних и один новый typed event, cursor, label, invalid discriminators/payload |

Первый run подтвердил 61 из 62 новых PostgreSQL cases; оставшийся case исправлен
как описано выше. Новый итоговый набор — 39 model + 70 PostgreSQL cases; execution
receipt повторного run в PR определяет их фактический результат. Это bounded
LOCAL/TEST evidence: Telegram/webhook, storage/FileObject, messaging HTTP/UI и M3
не реализованы и не проверялись. Credentials/secrets controlled adapter не нужны.

**Точный запрос C0: разрешить только следующие совместимые дельты.** Они пока
не применены, потому что отсутствуют в таблице разрешённых paths этого поручения.

| Path вне scope | Наблюдённая причина и минимальная предлагаемая правка |
|---|---|
| `scripts/provision_local_auth.py` | Сравнение schema с literal `0004` ломает auth migration/provisioning test и browser setup на назначенной `0005`. Импортировать `asm.foundation.DATABASE_SCHEMA_REVISION`, использовать его в точном сравнении и сообщении; environment/identity/password guards сохранить |
| `scripts/m1_3_browser_fixture.py` | Второй guard требует `0004`, поэтому заблокирует browser fixture после исправления provisioning. Сравнивать с той же общей текущей revision; остальные TEST/identity guards сохранить |
| `tests/test_postgres.py` | Один exact inventory test не допускает 10 назначенных messaging tables; два shutdown cases требуют историческое `jobs_enabled=false`. Добавить точные 10 имён в sorted inventory, ожидать `jobs_enabled=true` и `mode=controlled`; runtime role, SIGTERM/shutdown и остальные assertions сохранить |
| `tests/test_m1_3_c0_acceptance.py` | Пять initializer-conflict cases вызывают TRUNCATE Audit без новой referencing receipts table. В единственной команде использовать `",".join((*TABLES, "platform.messaging_command_receipts"))`. C2 подтвердил: глобальный TABLES, before/after counters и assertions не менять; CASCADE/отключение FK не нужны; transaction rollback всё восстанавливает |

Разрешённые изменения прежних tests имеют конкретную причину:
`test_foundation.py` — head `0005`; `test_tenancy_postgres.py` — ровно новые
messaging tables/capabilities в exact inventory; `test_m1_3_postgres.py` — две
новые generated typed Audit FK columns; `test_m1_3_http_contract.py` — additive
strict MessageSendAuditEvent. Frontend изменён только новым parser/component
case. Исходные защитные cases и общие SQLSTATE/auth/tenancy guards сохранены.
`0001`–`0004`, canonical originals, dependencies/locks/CI/Compose не изменены.

M2.1 BLOCKED на полной regression verification до этой C0 exception. После её
получения: применить ровно четыре дельты, повторить оба штатных scripts и оба
clean-source gates, затем C0 acceptance и независимый scoped C8 review реализации.
PR остаётся Draft; merge и M2.1 VERIFIED не объявляются.

### Внешний smoke — подготовка со слов пользователя

2026-09-21 пользователь подтвердил: test bot создан, Business/Secretary Mode включён,
Owner/Client accounts подготовлены; `TG_BOT_TOKEN` и отдельный `TG_WEBHOOK_SECRET`
сохранены в менеджере паролей. Значения не получены, не запрашиваются и не нужны C3
для M2.1. Это user-reported preparation, не проверенный connection/rights/live run.
Остались фактическая binding аккаунта/Workspace и rights probe, безопасная runtime
injection секретов, тестовый HTTPS endpoint/webhook и будущий полный journey.
Они не блокируют M2.1; конкретный C6 test runbook будет выдан перед подключением.

Ниже — принятая последовательность и общая матрица M2. Указанный далее initial
snapshot PR #16 исторический; актуальный base первой задачи находится выше.
