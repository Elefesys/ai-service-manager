# M4 Polza runtime: plan / enable / disable

> **R2 исправление C0-M4-LIVE-OP-01 передано на review C0; live HOLD.**
> [M4_TEST_OPERATOR_R2.zip](https://chatgpt.com/library?file_id=libfile_17bbc3cc501c8191b7fc84bceb0654e2&account_id=personal)
> охватывает session/worker/watch общим cleanup, независимо пытается закрыть
> ту же сессию и остановить проверенные TEST worker/receiver; primary и cleanup
> outcomes разделены, stop подтверждается либо остаётся UNKNOWN. 40 offline
> controls PASS; actual PG/VM/live NOT_RUN. SIGKILL/host loss не гарантируют finally,
> disable/stop не отзывают уже допущенный HTTP. R1/C0 evidence сохранены.
> Владельцу пока не запускать mutating commands; [receipt/границы](../tasks/M4_HANDOFF.md).
> Accepted application source и будущий owner допуск не изменены.

Этот путь остаётся **EVAL_ONLY**, default OFF. Эта реализация и CI не разрешают
живой запуск. В C3-M4.3-POLZA-RUNTIME-R1: model POST / catalog GET / history GET /
Telegram send = **0 / 0 / 0 / 0**, VM/deploy = 0. Ниже — процедура для будущего
отдельно согласованного теста владельца.

Один маршрут: `RU_AGGREGATOR / polza / PROVIDER`, `openai/gpt-6-luna`, request
selector `openai/flex`, `https://polza.ai/api/v1/chat/completions`. Наблюдаемая
family — OpenAI; variant flex не объявляется наблюдённым. Prompt
`conversation_v2`, schema `conversation_result_v1`, строгий существующий envelope.
Нет fallback, Vision, web search, RAG или бизнесовых write tools.

## Подготовка и пределы

Будущий smoke: **10 минут, максимум 4 model POST, 10 RUB**, не более2 POST и1
READ за run; до8 ограниченных history GET за сессию, catalog GET из runtime=0.
До4 ответов Telegram, UNKNOWN не пересылается. Тариф должен давать резерв
одного вызова ×4 ≤10 RUB. Все резервы сохраняются консервативно, включая
завершённые и UNKNOWN; повторный enable и restart их не освобождают.
Run ≤120s, включая history; input≤32768 tokens/24576 bytes,
output≤512 tokens/32768 bytes. Лимит RUB — admission ceiling по проверенному
тарифу и резервам, не обещание отозвать уже начатое списание провайдера.

Нужны один выделенный синтетический TEST Workspace, client, conversation,
Telegram connection/chat и ожидаемый bot ID. `asm_test`/`TEST` — дополнительное
условие, не допуск. Владелец должен заранее подтвердить отсутствие реальных
клиентских данных; DB дополнительно отвергает иной scope и нетекстовые сообщения.
Прежние owner/native reconciliation, Resume, права и observation barrier нужны
на прежних границах. Секреты и настройки держать вне checkout/build context,
в абсолютных приватных файлах владельца процесса (0600, директория0700).

До enable подготовить **новый** проверенный `RuntimeRoute` JSON (контракт
`asm.ai.polza.RuntimeRoute`) с текущим каталогом/тарифом, SHA256 записи каталога,
датой проверки не старше24h, review evidence и mapping OpenAI. Старые paid
probe refs, offline PASS и остаток150RUB не заменяют этот review. Не копировать
`OFFLINE MOCK ONLY` из тестов в операторскую конфигурацию.

Пример формирования приватной конфигурации после заполнения реальных тестовых
ID; review не является файлом с ключом:

```python
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from asm.ai.polza import RuntimeRoute, fingerprint
from asm.ai.runtime_settings import RuntimeSettings, private_bytes

review = RuntimeRoute.model_validate_json(private_bytes(Path('/private/polza-review.json'), 30000))
now = datetime.now(UTC)
config = RuntimeSettings(
    session_id=uuid4(), workspace_id=UUID(os.environ['PILOT_WORKSPACE_ID']),
    client_id=UUID(os.environ['PILOT_CLIENT_ID']),
    conversation_id=UUID(os.environ['PILOT_CONVERSATION_ID']),
    connection_id=UUID(os.environ['PILOT_CONNECTION_ID']),
    chat_id=os.environ['PILOT_CHAT_ID'], bot_identity=os.environ['PILOT_BOT_ID'],
    data_profile='SYNTHETIC_TEXT_V1', starts_at=now,
    expires_at=now+timedelta(minutes=10), max_calls=4, max_rub=Decimal('10'),
    review=review, review_sha256=fingerprint(review.model_dump(mode='json')),
)
fd = os.open('/private/polza-runtime.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(config.model_dump_json())
```

## Plan без credentials и сети

```sh
python scripts/m4_runtime_pilot.py plan --config /private/polza-runtime.json
```

Plan валидирует конфигурацию и выводит пределы; не читает API key/DB credentials,
не подключается к БД и не вызывает HTTP. Он не включает worker или сессию.

## Enable — только после отдельного разрешения владельца

Приватные `polza.key` и `migrator.url` создаются оператором вне Git. Первый —
только API key, второй — существующий `postgresql+psycopg://asm_migrator:…/asm_test`.
Telegram token/webhook configuration остаётся существующей явно включённой
операторской настройкой. Не помещать секреты в команды, trace или evidence.

```sh
python scripts/m4_runtime_pilot.py enable --config /private/polza-runtime.json \
  --key-file /private/polza.key --database-file /private/migrator.url
```

Enable проверяет ключ локально, сохраняет точный допуск через migrator capability
и сверяет current0016 profile. Runtime role не может создать/изменить сессию.
Сам enable не делает model/Telegram HTTP. Для существующего worker задать:

```sh
export ASM_ENVIRONMENT=TEST
export ASM_POLZA_RUNTIME_CONFIG=/private/polza-runtime.json
export ASM_POLZA_RUNTIME_KEY_FILE=/private/polza.key
python -m asm.foundation worker
```

Worker должен получить приватные файлы существующим операторским способом.
Это не инструкция менять VM/infra в текущей выдаче. API/scheduler не включают
provider по этим переменным. Отсутствие полной конфигурации оставляет AI OFF
или приводит к явному отказу запуска; наличие ключа само по себе не включает AI.

## Disable и STOP

```sh
python scripts/m4_runtime_pilot.py disable --session SESSION_UUID \
  --database-file /private/migrator.url
```

Disable запрещает новые model/send admission. Уже допущенный HTTP нельзя
объявлять отозванным. Затем остановить worker и убрать обе переменные. Сессию
после disable повторно не включать: запись и её расход остаются для проверки.
Новую сессию нельзя использовать как автоматический reset бюджета.

STOP при expiry, исчерпании calls/RUB, неизвестном результате/расходе, ошибке
schema/history/provider, изменении контекста/прав/native state или несоответствии
scope. Зафиксировать run/call/Outbox статус без ключа, сырого HTTP и текста
диалога; UNKNOWN держит резерв. Повторные команды и restart не регенерируют
вызванный run и не пересылают UNKNOWN Telegram. Цены, запись и платёж не
подтверждаются моделью; недостаток данных передаётся владельцу.

## Миграция и cutover

0016 additive: приватная `ai_provider_sessions`, nullable FK
`ai_deliveries.provider_session_id`, узкие provider capabilities и отдельный
точный current0016 verifier. 0001–0015 неизменны. Historical0013/0014 сохранены,
synthetic0015 composition работает на новой схеме с прежним mock-only send.

Старый binary с exact0015 readiness **не совместим с0016**: требуется отдельный
drain/migrate/start cutover по ADR-132/216/217, без заявления rolling coexistence.
Неиспользованная0016 откатывается до0015; после создания session downgrade
закрыт (`AI_PROVIDER_DURABLE_DATA`), история не удаляется ради rollback. Этот
runbook не выполняет deployment/cutover. Приёмка C0 и owner merge — отдельно.

## C6 executable package — REVIEW / 2026-11-06

[M4_TEST_OPERATOR_R1.zip](https://chatgpt.com/library?file_id=libfile_680ff1db569c819199fe65be1d2929d9&account_id=personal) —50981bytes,
SHA256 bbebbf134935b7f5046cbe64ae07aab0f87d6bfb23d7f6a13724f9b23c0c9e4c.
16entries/manifest/CRC PASS. Instruction015af6d9; accepted build29dc1608/treeb70eb034.
Пакет находится на review C0; **пока не выполнять его mutating команды на ВМ**.
README содержит точные executable commands/private inputs и границы. Полный
receipt — CURRENT M4_HANDOFF; task status — REVIEW в едином register.

Реализован полный отдельный Compose, без merge lists с LOCAL: persistent
TEST/asm_test/0016, отдельные SHA tags, loopback18000/18080 и один auth origin.
Operator имеет readonly полный accepted checkout/frozen deps; runtime не
получает migrator URL. `plan/check` отделены от `prepare/cutover/bind/policy/
receive/configure/enable/disable/return`. Приёмник/opaque relay byte-identical;
новые TEST adapters имеют свои hashes. Старые helpers остаются прежними.

Future sequence: private targeted capture → prepare/AI OFF → PC SSH route →
old empty queue/ACK fence → binding+MATERIAL+native → TEST receive → synthetic
TEXT и owner reconciliation/Resume → fresh≤24h reviewed route/key → configure →
finite enable/user smoke → disable/verified return. Enable foreground watchdog
закрывает admission к expiry/наблюдённому UNKNOWN. Disable доступен из второго
SSH окна. Неизвестный ACK/send/partial stage запрещает автоматический возврат;
старый consumer не запускается поверх второго dedupe ledger. Обе группы
volumes/история/holds сохранены. При исходно пустом webhook и отсутствии
poller return восстанавливает это неактивное состояние, не придумывает receiver.

23 bounded controls,Python3.13 import/CLI/source/native profile,actual Compose
parser для полных OFF/AI models и actual PowerShell parser PASS. Actual Docker
engine/PG/Windows SSH/Happ/VM/external smoke и account/route review NOT_RUN.
Новых remote/live/paid действий нет. C0 review предшествует одному owner
допуску; ниже сохранён исторический source plan, не отдельная команда запуска.

## История C6 — source plan и owner inventory / 2026-11-06

**Owner preflight принят C0. Продолжается реализация private TEST operator
package по CURRENT HANDOFF; прежний docs-only scope расширен для этой адаптации.
Ниже source plan с наблюдениями ВМ; executable package и live допуск ещё не приняты.**
Accepted code/build: `29dc16084f0ee0d01e5f96e7226995480e189a22`,
tree `b70eb0348577c812f4f587d995c724e3c0e989e4`.
Instructions: `a170da0975bcd0d73b0f3372fb8ec4a9cecc0956`.
Docs preparation branch не является build/native fingerprint source.

### Что установлено, что ещё нужно

| Проверено по accepted source/историческим файлам | Следствие для оператора |
|---|---|
| `compose.yaml` задаёт LOCAL/asm_local, общие `asm-backend:local`/`asm-frontend:local`, фиксированные localhost ports | Отдельный project, persistent volumes, image tags и private override; не запускать обычный compose поверх M3 |
| `postgres-test` использует временное хранилище | Для live истории брать отдельный persistent PostgreSQL, не CI test service |
| Runtime требует TEST/asm_test/0016, storage environment тоже TEST | Environment/DSN/healthcheck/storage проверить согласованно, старую БД не переименовывать |
| `infra/Dockerfile.backend` runtime не содержит `scripts/`; development не содержит всего Git/Console checkout | Operator команды выполнять через development dependencies с полным accepted checkout, отдельно от runtime |
| `scripts/provision_telegram_test.py --live` после commit вызывает `setWebhook` | Не запускать эту команду как незаметную подготовку polling. В private wrapper использовать существующие `inspect_connection` с заданным external ID и `commit_binding`, без discovery/getUpdates и setWebhook |
| Архивные `asm_telegram_pc_dev.py`/`asm_telegram_pc_session.py`/`scripts/telegram_polling_recovery.py` проверяют старые receipts/source/контейнеры | Нужна узкая привязка PC route и единственного receiver к новому project; прежние receipts не редактировать, guards не отключать |
| Архивный `asm_m3_policy_enable.py` R4 привязан к LOCAL/asm_local/0013 | Новый private TEST intent и current0016/source proof для той же узкой MATERIAL операции; затем существующий native check/commit/current |
| `native-policy-profile` и `provision_telegram_test.py --native-policy` в accepted code уже поддерживают current0016 | Новая migration/API/GRANT или изменение native policy контракта не требуется |

Точный blocker **TEST_OPERATOR_ADAPTATION_REQUIRED**: перечисленные private
helpers нельзя переносить сменой строки schema или снятием проверки hashes.
Минимальная дельта — отдельный private compose override и один ограниченный
wrapper, переиспользующий existing binding/native/receiver/runtime команды;
в нём новый TEST intent, accepted source/component/image proof, MATERIAL lock
and recheck, один bot consumer, остановка/возврат с сохранением обоих DB scopes.
Product/DDL/dependencies/pins/CI не менять. Это не задание на новую платформу.

Владелец выполнил `asm_m4_live_preflight.py`06.11.2026 в13:25:26UTC:
SSH0,8containers running, API200; actual READ ONLY SQL показал LOCAL/asm_local/
schema0013, MATERIAL1/nativeON1, один binding, один разговор с nontext и нулевые
текущие окна subscription/NORMAL service mode. Это внутренние ASM windows;
агрегаты не доказывают точные даты истечения или оплату облака/Polza.
Checkout clean5c074beb/treecb47cccd; image/source pairing всё ещё NOT_PROVEN.
API/worker token-free Telegram TIMEOUT; причина/состояние Happ не проверены.
Owner evidence не является прямым SSH исполнением C6; mutations NONE.
Предложенные18000/18080 были свободны, resume/polling/PC-dev hashes совпали с
reviewed constants. Policy helper отсутствует в проверенном home path; это не
отменяет committed MATERIAL/native состояние. Новый TEST scope ещё не создан.

[Полный owner receipt](https://chatgpt.com/library?file_id=libfile_c713f00b60048191991da601d6e841fb&account_id=personal)
сохраняет supplied output и границы проверки. Общее чтение ВМ повторять не нужно.
Применён один owner preflight с Windows
launcher: Docker inspect, bounded READ ONLY SQL/ROLLBACK, local readiness,
token-free Telegram HTTPS, только наличие/mode credentials и hashes старых
helpers. Он не запускает/импортирует helpers, не создаёт файлы на ВМ, не вызывает
bot API/getUpdates/provider, не меняет services/DB. Разрешено обычное чтение
через owner SSH; нового согласования на эту проверку не требуется.
Образные IDs и checkout SHA — наблюдения, не доказательство их соответствия.
Preflight не доказывает отсутствие host receiver или remote webhook; это ещё
один обязательный fence перед переключением. Не выдавать его за полный0016 audit.

### Конкретный предлагаемый cutover после готового пакета и одного owner допуска

1. Сохранить private snapshot старого project: source/tree, image/container IDs,
   mounts/volumes, environment-file digests, действующий transport/receiver mode,
   binding, queue/ack state, конфигурацию ingress и прежние receipts. Текущий
   snapshot сначала сверить с owner preflight. Не изменять оригиналы.
2. Подготовить отдельный `asm-m4-live-test` из accepted code, а не docs branch;
   новые named volumes, новые credentials, новые versioned backend/frontend
   tags. Предложены только loopback `18000` API / `18080` Console, занятость
   перепроверить перед созданием. Runtime/Storage TEST, DB `asm_test`, runtime
   role `asm_runtime`; migrator только в отдельном operator. Новый публичный
   домен не нужен: Console через owner SSH local forward и exact auth origin.
   Старые DB/storage/receipts остаются на месте. Не переиспользовать `:local` tags.
3. После разрешённого create/migrate проверить ровно schema0016/current profile,
   source/component/image соответствие, private mounts по UID и readiness с
   AI OFF. Раздельные private копии key/config должны принадлежать читающему
   процессу: runtime UID10001; operator UID определяется фактически. Не выдавать
   runtime migrator URL. Отсутствие ключа в old worker не доказывает его отсутствие
   на ПК. В новом worker обе `ASM_POLZA_RUNTIME_*` пока отсутствуют.
4. Создать новый synthetic Owner/Workspace существующим
   `scripts/provision_local_auth.py` и fresh billing/binding через existing
   capabilities. Существующие тестовые Telegram Owner/Client аккаунты допустимы;
   старые messages/photo/receipts не копировать и не очищать. Точные новые IDs
   сохраняются только в private intent. Нужны текущие согласованные окна, не даты M3.
5. Для того же bot сначала приостановить тестовые сообщения, подтвердить
   обработку старой очереди/ACK и отсутствие UNKNOWN, остановить старый receiver
   и старые Telegram writers (API/worker/scheduler); DB/storage оставить.
   Проверить отсутствие второго host/container poller и webhook consumer.
   Непустая/непроверенная очередь или неизвестный ACK — STOP. `drop_pending_updates`
   не использовать. Новому receiver передать только новую API origin и те же
   ожидаемые bot identity/secret; pending old traffic нельзя считать новым TEXT scope.
6. Через новую согласованную PC/Happ route проверить callers, затем включить
   единственный новый polling receiver. При необходимости удаления прежнего
   webhook это явный шаг cutover с `drop_pending_updates=false`, после fence.
   Прежний PC helper с автоматическим восстановлением старого consumer не
   запускать поверх новой схемы. Сначала marker TEXT с AI OFF создаёт новый
   conversation/client, затем exact private scope фиксируется для сессии.
7. В том же новом binding: узкая MATERIAL false→true с сохранением M3 lock order,
   identity/product/binding recheck и UNKNOWN semantics; затем штатный native
   OFF_UNUSED/P0→ON/P1 с actual current source/drain proof. Ни изменение старого
   binding, ни декларация `drain_confirmed=true` без проверки не допустимы.
   Owner подтверждает актуальный native context, сохраняет reconciliation,
   отдельно выполняет Resume; observation barrier/currentness должны пропустить
   новую попытку. Не обходить эти условия прямыми UPDATE conversation state.

Все эти изменяющие шаги **NOT_RUN**. Current wrapper/override с private inputs
ещё не выдан как runnable cutover. Basic preflight получен; остаётся operator delta;
после этого C0 представляет владельцу одну точную операцию, не серию разрешений.

### Account/route и команды, которые уже существуют

Fresh account/route review **NOT_RUN**: в этом исполнении catalog GET=0,
key-metadata GET=0; секрет не запрашивался. Разрешённые по необходимости один
catalog GET и один key/limit GET выполняются существующим путём с private key,
без повторения исторического paid probe CLI. Новый RuntimeRoute должен пройти
полный validator: catalog fingerprint, capabilities, rates/fees, token/output
bounds, OpenAI mapping и проверка свежести≤24h. Старую дату нельзя заменить
новой без проверки. Flex остаётся NOT_OBSERVED; ledger не является балансом счёта.

Только после готовности scope/review и owner допуска сформировать новый десяти-
минутный config по примеру выше. Ниже точные existing CLI, выполняемые внутри
отдельного operator environment с accepted checkout/dependencies; абсолютные
private paths заполняет wrapper, а не владелец в публичном сообщении:

```sh
# Current source profile: no policy commit by this command.
python scripts/prepare_telegram_egress.py native-policy-profile \
  --state-dir "$ASM_PRIVATE" \
  --accepted-sha 29dc16084f0ee0d01e5f96e7226995480e189a22 \
  --accepted-tree b70eb0348577c812f4f587d995c724e3c0e989e4
# Prepared TEST request/approval/receipt and migration URL are private environment inputs.
python scripts/provision_telegram_test.py --native-policy check
python scripts/provision_telegram_test.py --native-policy commit
python scripts/provision_telegram_test.py --native-policy current
python scripts/m4_runtime_pilot.py plan --config "$ASM_PRIVATE/polza-runtime.json"
python scripts/m4_runtime_pilot.py enable --config "$ASM_PRIVATE/polza-runtime.json" \
  --key-file "$ASM_PRIVATE/polza.key" --database-file "$ASM_PRIVATE/migrator.url"
# Wrapper starts exactly one TEST worker, not an extra copy beside the existing worker.
# Its runtime-only environment includes ASM_ENVIRONMENT=TEST and both private Polza paths.
python -m asm.foundation worker
# Separate operator terminal; SESSION_UUID is read from the saved private intent.
python scripts/m4_runtime_pilot.py disable --session "$ASM_SESSION_UUID" \
  --database-file "$ASM_PRIVATE/migrator.url"
```

Не передавать весь operator environment worker: последняя worker команда
выполняется в runtime container, без migrator credentials. Operator команды
`commit`, `enable`, `disable` здесь только план, в текущей подготовке не вызывались.

### Smoke и возврат

В новом scope владелец сначала подтверждает синтетический факт:
«Тестовая консультация проходит онлайн». Цена/свободное время не задаются.
После reconciliation и отдельного Resume два предлагаемых client TEXT:

- «Как проходит тестовая консультация?» — ответ опирается на подтверждённый факт.
- «Сколько стоит и можно записаться завтра на 15:00?» — уточнение/передача владельцу,
  без выдуманной цены и подтверждённой записи.

Общие пределы прежние:10мин/4POST/10RUB внутри150;2POST/1READ на run,
8historyGET/сессию/4автоответа. READ отмечать только по actual evidence; новых
POST ради READ нет. Проверить оба Telegram участника и Console, durable run/call/
usage/cost, Outbox/send outcomes, отсутствие дублей. UNKNOWN/error/expiry — STOP,
disable, сохранение holds; не refresh/re-enable/restart ради повторной генерации.

Возврат начинается с disable новой сессии, остановки нового AI worker и receiver,
проверки in-flight/queue/ACK. Сохранить новый0016 volume, receipts, cost/UNKNOWN
history и private intent. При unresolved send/ACK не восстанавливать старого
Telegram consumer автоматически: новая БД не разделяет dedupe ledger со старой.
Старую Console можно вернуть на её неизменённые source/images/DB, но Telegram
writers/receiver возобновлять только после разрешённого однозначного fence;
одновременно ни два poller, ни poller+webhook. Незавершённый fence означает
безопасную паузу доставки, не успешный rollback. Никаких `down -v`, удаления
session/holds, downgrade использованной0016 или восстановления старой БД поверх новой.
