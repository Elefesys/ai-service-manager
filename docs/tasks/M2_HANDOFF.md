# M2 — Telegram, изображения и ручная переписка

Дата подготовки: 2026-09-20. Ответственный за выдачу задач и интеграцию: C0.
Единственный источник статусов: [TASK_REGISTER](../TASK_REGISTER.md).
Ниже одно активное поручение; свёрнутые разделы — историческое evidence.

## Активный handoff C0 → C6/C3 — M2-ENV-04-TELEGRAM-EGRESS / 2026-10-05

**IN_PROGRESS — ограниченная доработка после C0/C8 CHANGES_REQUESTED.** Единственная задача:
воспроизводимый opt-in egress только для существующего synthetic LOCAL/TEST Telegram.
Прямой outbound с VM timeout; temporary official-Xray route и exact-client getMe
фактически PASS. Opt-in route реализован в PR; на owner VM он ещё не развёрнут.
ADR239/production и scope M2 не пересматриваются.

### Repository, base и продолжение

- **Elefesys/ai-service-manager**, **c6/m2-telegram-live → main**, продолжать
  существующий **Draft PR24**, https://github.com/Elefesys/ai-service-manager/pull/24.
- Accepted implementation base **22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
  **c30415b48a08dabac6a59f1294843a0bd25ff353**. Actual main CI37016012805 SUCCESS.
- Сохранить первый coordination commit **e58c4a1a731ad238ccf9a79e6c478969642cd088**;
  продолжить от точного нового coordination head, указанного C0 в PR receipt/сообщении.
  Его дополнительный docs commit согласует этот handoff/register/runbook, не реализует
  route. Перед стартом сверить ancestry/base/head/tree и CI, без force-push/merge.
- Existing VM runtime **80e51c43e31541940f1ccf18b8281adf1a061748**, tree
  **88ed308b4c56114aa977dcf91204964d9b7348e5**. Не считать его новым PR head.
  Private env/profile/TLS и реальный Docker находятся только у владельца; доступа
  C6 к его cloud/SSH не предполагать. Реализация и CI от этого не блокируются.
- Читать AGENTS, register, runbook§0.6, M2_CONTRACT§§10–11, Spec§24.6/private files,
  ADR138/141/142/239/243 и Implementation Plan§§6–7. Frozen app/send semantics
  не перепроектировать. Existing client/config source bytes сверять с Git blobs.

### Активная ограниченная доработка C0 → C6

**Review verdict: CHANGES_REQUESTED. Task status: IN_PROGRESS.** Независимый scoped
C8 выполнен по готовой реализации, затем C0 сопоставил процедуру с фактическим VM
receipt. Доработка закрывает существующие E01/E05, без новых требований M2.

Проверен implementation head **3fffdda5d5e3f866cf2f25c30bc9e619091de081**,
tree **6ffff63ac85097ab63e53538213bde9cde70edc6**. Tested merge
**160a9f41de201308e92121fc05f996006af92894** имеет ordered parents
accepted base22993f558c5e7e933c65e9c999933bd2e3ab41c4 + указанный implementation head;
его tree совпадает. [CI37281699500](https://github.com/Elefesys/ai-service-manager/actions/runs/37281699500)
SUCCESS: оба штатных scripts и clean-source gates,526 unit/390 PostgreSQL-S3/
111 frontend/27 browser и6+1 relay cases. Это фактический successful run,
но его E05 fixture не доказывает сохранность БД пересоздаваемых callers.

| Finding | Дефект и обязательный результат |
|---|---|
| C8-M2-ENV04-01, P2, E05 | На VM api/worker disabled и TG fields пустые; существующий .env.telegram уже содержит staged token/secret/bot ID/webhook URL. snapshot сравнивает все эти model fields с running containers и выдаёт EGRESS_RUNNING_ENVIRONMENT_DRIFT до deploy. Исправить disabled deployment для этого реального исходного состояния: текущие caller env и disabled/no-secret граница сохраняются, staged operator inputs не переписываются. Их последующее применение к runtime — только отдельный C0 live-шаг. Общие проверки env/image/process/mount/gateway не ослаблять и не заменять исключением всех TG fields. |
| C8-M2-ENV04-02, P2, E05 | Held UNKNOWN/session/receipt и hashes читаются из postgres-test/asm_test, но перед exact CLI api/worker пересоздаются через base Compose на postgres/asm_local. Проверять данные именно той БД, к которой подключены пересоздаваемые callers: автоматический identity assertion до и после deploy/rollback, существующие UNKNOWN/receipt/Console state, отсутствие второго wire send. Реальный isolated Docker/PG, без правок owner VM, base Compose, приложения или frozen tests. |
| C8-M2-ENV04-03, P2, E01 | Path.absolute()+lexical is_relative_to допускает outside/../checkout/private-state и запись приватного config внутрь checkout. До mkdir/config write/image call доказать каноническую границу каталога, сохранив no-symlink/owner/mode guards. Проверить .. alias внутрь checkout, отсутствие writes при отказе и нормальный outside path; никакой нормализации source bytes. |

Один fix cycle в том же PR24/ветке, без reset/force-push и повторной реализации E02–E04.
Разрешённая дельта этой доработки: scripts/prepare_telegram_egress.py,
scripts/test_telegram_egress.sh, tests/test_telegram_egress.py,
tests/test_telegram_egress_postgres.py, при необходимости существующие два
infra/telegram-egress/compose*.yaml; согласованный register/handoff/runbook и только
необходимое уточнение operational M2_CONTRACT. Прежние запреты и pin сохраняются.
Новую общую framework/config architecture или возможности будущих этапов не вводить.

Сначала воспроизвести каждый defect на reviewed bytes; затем добавить точные
regressions. Новый Docker lane обязан начинаться с disabled/empty running TG fields
и отдельно staged synthetic inputs, а E05 обязан assert same actual DB identity.
Полные scripts/final-head CI/source gates сохранить. C0/C8 повторно проверят только
эти corrections и затронутые boundaries; прежний successful E04 не обнуляется.
Возврат C6 — REVIEW с exact refs/CI/assertions/limits в том же Draft PR. Owner не
выполняет deployment/discovery/setup/send; не повторяет Console provisioning или
secret entry. C0 выдаст операторский блок только после закрытия трёх findings.

### Уже доказано и сохранено

2026-10-05 12:50+07 владелец исполнил artifact
**cc799386a922eaca78376a7acc0a2687a8465f2e32a8558643b7de5421174ba1**: actual fixed
relay config, exact API image source, token-free verified TLS, отказ при выключенном
relay с неизменным hosts mapping, single getMe ID/is_bot/username, unchanged app/env,
cleanup и SSH_EXIT0 — PASS. Это не постоянный route, Business rights, webhook,
real send/media или A09/A11 PASS. Telegram в работающем приложении остаётся disabled.
Console login/provisioning и private secret entry уже завершены, не повторять.

Официальный cached Xray26.9.9 linux/amd64:
**ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b**.
Publisher/config source reviewed at **52a412d9e2f5c2a5142b1b4e2ab3771dacb8b120**.
Это publisher metadata/source evidence, не reproducible rebuild/signature claim.
Приватный вход — существующий mode600 profile.json в mode700 operator-owned каталоге
вне checkout; provider values/UUID/endpoints не копировать в Git/CI/reports.

### Разрешённая дельта C6

Старый allowlist из трёх docs **явно расширен C0 из-за доказанного outbound blocker**:

- `infra/telegram-egress/compose.yaml` — новый opt-in overlay, base compose не менять;
- `infra/telegram-egress/image.lock.env` — только указанный официальный Xray digest;
- `infra/telegram-egress/compose.test.yaml` — isolated controlled runner topology;
- `scripts/prepare_telegram_egress.py` — bounded private config/overlay preparation;
- `scripts/test_telegram_egress.sh` — реальные Docker/transport boundary checks;
- `scripts/ci.sh` — только обязательный additive вызов новой проверки, существующие
  команды, failure propagation и cleanup/source gates сохранить;
- `tests/test_telegram_egress.py`, `tests/test_telegram_egress_postgres.py` — новые
  существенные config/isolation/recovery проверки; synthetic fixtures внутри них;
- `tests/test_m2_3_wire_postgres.py` — только минимальное переиспользование/параметризация
  реального wire fixture, прежние cases/assertions не удалять и не заменять mocks;
- `docs/TASK_REGISTER.md`, `docs/tasks/M2_HANDOFF.md`,
  `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md`, `docs/tasks/M2_CONTRACT.md` — согласованный
  receipt и короткое operational extension без изменения domain/API contracts.

Не создавать файл лишь потому, что он разрешён. Иное изменение требует конкретного
blocker и ограниченного решения C0 до edits. **Запрещены** app/frontend changes,
`compose.yaml`, `.github/workflows/*`, существующие image/dependency locks, auth/tenancy,
grants, API snapshots и миграции0001–0007. Новые dependencies/paid resources, general
proxy product, TUN/host route, production/AI/M3 не входят в задачу. CI не использует
реальные profile/token/webhook secret или Telegram account и не делает external sends.

### Принятый минимальный контракт

1. **Opt-in.** Отдельный overlay; без него обычный запуск прежний. Relay non-root,
   read-only/cap-drop/no-new-privileges/resource bounds, private configRO; только
   opaque TCP к `api.telegram.org:443` через выбранный connection. Default deny,
   без freedom/direct/failover, HTTP retries, sniffed target override, TLS termination,
   host ports/network, Docker socket или широкого импортирования desktop routes.
   Сохранить выбранные VLESS/TCP/REALITY/Vision/fingerprint параметры. Ни TG token,
   ни DB/S3 credentials relay не получает. Генератор не source/exec чужой JSON/env.
2. **Route.** Callers ровно `api`, `worker`, `telegram-operator`: explicit hosts mapping
   official name → устойчивый private relay IPv4, сохраняемый при stop/recreate.
   Отсутствие relay не включает public A/AAAA/direct fallback. C6 сам выбирает и
   проверяет IPAM на пересечения с существующими Docker networks/host routes;
   технический выбор IP/SQL/config не передавать владельцу. Не менять app network,
   её default gateway, PostgreSQL/S3/ingress/private signed-GET paths. Отказ relay
   не ломает обычные API DB readiness/auth. Scheduler Telegram methods не вызывает
   в текущем коде: его route не добавлять; S3 cleanup/recovery сохраняются.
3. **Transport.** Existing official origin, verified TLS/SNI/hostname, trust_env=False,
   redirects/retries0, connect/pool2s, read/write5s и общие operation budgets неизменны.
   Worker route покрывает getFile **и** последующий `/file/bot...` GET; byte/format/
   redirect limits и private image publication сохраняются. Это не HTTPS_PROXY
   настройка: accepted client её игнорирует. Route health не заменяет actual permissions.
4. **Durability.** Relay ничего не знает об Outbox/receipts и не повторяет HTTP.
   До HTTP доказанный connection failure сохраняет accepted definitely-unsent
   handling; после возможной записи/эффекта — canonical UNKNOWN, без второго send.
   Не менять leases/claim limits/429/exhaustion/finalize recovery ради сети.
5. **Operation/rollback.** Подготовить одну точную deploy/preflight/rollback процедуру
   для C0. Все последующие команды используют один и тот же resolved overlay/config;
   нельзя случайно пересоздать enabled callers plain Compose без mapping. При rollback
   сначала disable Telegram, затем убрать route; preserve PG/S3 volumes, pending/
   DISPATCHING/UNKNOWN, receipts, Console identities и connection/billing dates.
   No down-v/reset/rebind/drop; никакой live setup/send в implementation turn.

### Критерии результата — каждый связан с фактическим evidence

| ID | Обязательное доказательство |
|---|---|
| E01 | Canonical Git blob/pinned image identity; private owner/mode/no-symlink checks, bounded minimal config; no credentials in artifacts/logs/build context; offline pinned-binary config test |
| E02 | Real Docker resolved overlay: opt-in only; no public relay port; same static mapping after stop/recreate; all A/AAAA resolutions restricted; relay unavailable → bounded failure, no direct fallback; PG/S3/auth/readiness remain available |
| E03 | Actual controlled relay carries accepted readonly **and media** request paths; recoverable readonly/media interruption recovers under existing policy; no redirect/size/TLS relaxation; TEST fixture hooks/CA never enter live config |
| E04 | **Новый relay действительно на wire path**: accepted effect → lost response/relay failure → durable UNKNOWN → worker/relay restart → persistent wire counter remains1. Real PostgreSQL + real sockets; старый direct-wire PASS в одиночку недостаточен. Не проводить destructive fault injection на owner VM |
| E05 | Prepared deploy/preflight/rollback records affected container/image IDs and necessary caller recreation; unrelated services, durable state/volumes/secrets and tested fixed mapping are preserved. Telegram remains disabled until отдельное C0 operator instruction. Owner не выбирает fields/ports/tests |
| E06 | Полные `sh scripts/ci.sh` и `sh scripts/test_browser.sh`, прежние tests/migrations/contracts/reproducibility/smoke и оба clean-source gates PASS на final head. Mapping E01–E05→commands/assertions/run/logs; actual scoped C8 новой boundary после реализации, не C3/self-review |

Synthetic CI проверяет реальный relay/transport с тестовым peer/получателем;
доступность частной подписки и real Telegram не выдавать за CI evidence. В CI нет
реальных секретов/клиентов; legitimate TEST-only origin/CA hooks только внутри fixture,
не новый параметр production client. Минимальные meaningful cases, не план на количество.
При failures установить причину в fixture/test/implementation и объяснить изменения;
не убирать защиту ради зелёного CI.

**C3 plan review фактически выполнен 2026-10-05:** контракт допустим при этих границах;
по GitHub runtime80e51c4 проверены consumers/scheduler, media и conservative UNKNOWN.
Это не C8 и не review готовой реализации. C0 назначит независимый scoped C8 после
готового diff/evidence E01–E06; только затем выдаст владельцу deployment block.

### C6 implementation receipt — ENV04 (до C0/C8 findings)

Ниже сохранён исходный implementation receipt. Его E05 acceptance ограничена
находками выше; actual CI SUCCESS и пройденные E02–E04 не отменяются.

Начало реализации — exact coordination **dbfba47a3d92bcee258f5ab490384f496e16a217**,
tree **8a0ac1988f8479f72d882bca53ed53c1ea63c216**, CI37270554509 SUCCESS. Первый
coordinatione58c4a1 и вся последующая история сохранены; force-push/merge не было.

Изменены ровно12 разрешённых paths: три `infra/telegram-egress/{compose.yaml,
compose.test.yaml,image.lock.env}`, `scripts/{prepare_telegram_egress.py,
test_telegram_egress.sh,ci.sh}`, два новых `tests/test_telegram_egress{,_postgres}.py`
и четыре текущих документа register/handoff/runbook/contract. Старый direct-wire
test импортируется без edits. App/frontend/base Compose/workflows/старые pins,
dependencies, API contracts и migrations0001–0007 byte-unchanged.

Private /28 выбирается с проверкой Docker/host routes; нижняя половина резервируется
для fixed endpoints, dynamic allocation — верхняя /29. Callers сохраняют обычный
gateway и получают official-host IPv4/IPv4-mapped IPv6; scheduler не меняется.
Generated relay имеет только fixed dokodemo-door и один выбранный VLESS connection,
default blackhole, без target sniffing/fallback/HTTP retries/TLS termination.
Profile600/parent700 и generated state вне checkout; pinned binary проверяет config
с network none. Canonical client/config проверяются как exact Git blobs в checkout
и actual application/operator images. Два publisher VOLUME закрыты read-only tmpfs.

E05 использует настоящий CLI deploy/preflight/rollback и private container/image/
mount/env-hash receipts. Fixtures удерживают canonical UNKNOWN, Console auth session
и command receipt; read-only snapshot сравнивает все строки app/platform до/после,
включая IDs/dates/fingerprints. Runtime выключается до снятия mapping. Операторская
процедура подготовлена в runbook§0.6.4; выдаёт её владельцу только C0 после scoped C8.

Диагноз промежуточных failures зафиксирован без удаления старых проверок:

- Точное поле pinned binary — `Password (PublicKey)`; parser исправлен по publisher
  source. Реальный Compose представляет пустую network mapping как `{}`; проверка
  модели согласована с этим output, static-IP reservation добавлена явно.
- One-shot storage bootstrap выполняется до exit0 отдельно от health/running wait.
- Xray26.9.9 запрещает private VLESS target по умолчанию. Только synthetic peer
  допускает exact fixture /32/TCP443; actual relay не получает freedom/исключение.
- CI37277576724: browser PASS, foundation6 new failures. Cause — synthetic CA без
  keyUsage при default Python3.13 VERIFY_X509_STRICT; exact OpenSSL strict probe
  воспроизвёл error92. Добавлены корректные RFC5280 extensions и строгая precheck;
  wrong-host требует code62. Client trust/тайм-ауты/защитные assertions не ослаблены.
- CI37279250778 на506be1a: все6 relay/PG/S3 wire cases PASS, browser PASS; E05
  остановился. Старый driver потерял bounded stdout code: точная причина того exit
  ретроспективно не доказана. Исправлена сохранность code/stage без private data.
- C3 нашёл отдельную доказанную нестабильность: Moby `GetMountPoints()` строит список
  из Go map без порядка. Snapshot теперь сортирует полные Type/Name/Source/Destination/
  RW records, сохраняя все mounts и assertions. Regression допускает перестановку,
  но по-прежнему отвергает изменение каждого поля. Это не разрешение volume drift.

**Implementation CI37279935914 — SUCCESS** на
**4c2dc7deffe1b115cdd32a321bd1c89a5d3f6e3b**, tree
**f10c64c68a122994ce0fd58dc9b918e6867d71b9**. Tested virtual merge:
**0e91a57a6611b1a4c610b21f692b7724e666abf0**, то же tree, ordered parents — accepted
main22993f5 и implementation4c2dc7d. Реально выполнены6 wire cases и1 held-state
rollback case, deploy/preflight/rollback CLI markers,525 unit/390 прежних PostgreSQL-S3/
111 frontend/27 browser, migration/contract/reproducibility/smoke и оба clean-source
gates. [Run](https://github.com/Elefesys/ai-service-manager/actions/runs/37279935914).
После этого добавлена указанная mount-order regression (34 новых unit PASS locally)
и согласованы четыре документа. **Их final head требует отдельного полного CI**;
его exact receipt закрепляется в PR24 до передачи C0. Старый successful SHA не
выдаётся за tested SHA итогового diff; SHA-only commits для receipt не создаются.

Mapping E01–E06 к конкретным assertions/commands — runbook§0.6.5; final head/tree,
tested virtual merge/parents, run и artifact receipt закрепляются в PR24. Новые
runtime secrets/config/key files не входят в source/build/reports. CI использует
только synthetic fixtures на обычном GitHub runner; локального Docker нет.
C3 участвовал в контракте и новых transport tests, это не независимый C8.

### Передача и дальнейшая последовательность

C6 возвращает в том же Draft PR24: preserved ancestry, final head/tree/parent,
actually tested merge SHA/tree/parents, точные changed paths, один receipt E01–E06,
commands/CI links и честные ограничения. При отсутствии Docker locally — CI runner,
не mock вместо реальной проверки; zip bytes не заявлять без сверки. Register/handoff/
runbook/operational contract обновить одним согласованным изменением; никаких SHA-only
commits. C6 самостоятельно не merge, не activate runtime, не пишет владельцу за C0.

После C0/C8 и final CI — один operator deploy/preflight шаг с disabled runtime,
затем существующие discovery→saved external connection ID→atomic setup/webhook→UI
text/photo/manual reply→Client receipt. Ранее созданные Console/секреты не повторять.
До первого setup проверить expiry TEST billing interval; после попытки preserveexact.
Потом итоговый receipt, обычный merge владельцем и отдельный actual main CI.
**ENV04 implementation acceptance не означает M2 VERIFIED; M3 не выдан.**


<details>
<summary>История — первое live поручение / 2026-10-02</summary>

## Исторический handoff C0 → C6/C3 — M2-LIVE-A09-A11 / 2026-10-02

**IN_PROGRESS; одна последовательная live-задача.** ENV03 интегрирован/VERIFIED
только как TEST host с выключенным Telegram. Теперь требуется реальный согласованный
Client text+photo → Owner Console/private image → manual reply → Client receipt.
Это оставшаяся внешняя проверка принятого M2, не новая реализация или production.
Сейчас выдан только первый шаг §0.5.1: Console identity. Остальные команды C0/C6
дают после фактического результата предыдущего, без повторного выбора полей владельцем.

### Repository, точный base и границы изменений

- Repository **Elefesys/ai-service-manager**, branch **c6/m2-telegram-live → main**,
  отдельный Draft PR задачи. Точный номер/coordination head/tree/CI — PR receipt;
  первый coordination commit сохранять, без SHA-only commits.
- Accepted base/main **22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
  **c30415b48a08dabac6a59f1294843a0bd25ff353** — actual PR23 merge.
  Ordered parents80e51c43e31541940f1ccf18b8281adf1a061748 +
  902e9f1d51235f1441ce4378a4d3a909adefea74.
  [Separate push/main37016012805](https://github.com/Elefesys/ai-service-manager/actions/runs/37016012805)
  SUCCESS: foundation110866924584/browser110866924421 checkout actual merge;
  492 unit/390 PostgreSQL-S3/111 frontend/27 browser, оба scripts/source gates.
- Existing runtime on VM остаётся **80e51c43e31541940f1ccf18b8281adf1a061748**,
  tree **88ed308b4c56114aa977dcf91204964d9b7348e5**. C0 сравнил80e→22993f5:
  только TASK_REGISTER/M2_HANDOFF/runbook. Поэтому не fetch/redeploy/rebuild app
  ради документации; exact runtime в каждом live receipt указывать честно.
- Repository allowlist ровно три docs: **docs/TASK_REGISTER.md**,
  **docs/tasks/M2_HANDOFF.md**, **docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md**.
  Runtime private env/TLS/операционные команды не коммитить. App/Compose/locks/pins/
  CI/tests/assertions/contracts/миграции0001–0007 не менять без конкретного blocker
  и ограниченного решения C0. Applied migrations не переписывать.
- Прочитать AGENTS; этот active block; runbook§0.5 и§§2–5.1; M2_CONTRACT§§10–11;
  Spec§24.6/private files/auth/recovery, ADR138/141/142/243, Implementation Plan§§6–7.
  Переданные11оригиналов совпали с current SOURCE_MANIFEST поSHA256. M1 задания
  не повторять; production managed DB/storage и M12 restore gates сохраняются.

### Конечное поручение и разделение ответственности

1. **C6/C0:** первый блок §0.5.1 проверяет текущий source/config/readiness и создаёт
   только fresh Console login **telegram.test.owner**, Workspace/Business/OWNER
   через существующий provisioner. До него собрать только существующий development
   image telegram-operator. Пароль вводится дважды скрыто; TG=false и без TG secrets.
   Не применять init/reset, не пересоздавать API/PG/S3. UNIQUE collision/потерянный
   ответ — STOP и read-only восстановление IDs по exact login, не новая учётка.
2. **C3 + владелец:** независимо подтвердить numeric Telegram Owner ID из официального
   account export и выбранный test bot из BotFather; это не UUID Console и не первый
   business_connection update. Связать bot с подготовленным test Owner через official
   Business/Secretary controls, только согласованный test dialog и необходимые rights.
3. **C6/C0:** один готовый private-entry блок для прежней .env.telegram после identity
   receipt; owner непосредственно вводит token/webhook secret на VM. Прежние DB/S3/TLS
   credentials не менять; не печатать secrets, token URLs или raw provider responses.
   Fixed synthetic billing contact **Synthetic Telegram test owner** и interval
   **2026-10-02T00:00:00+00:00 → 2026-10-09T00:00:00+00:00**. Это config для будущего
   первого setup, ещё не DB state; при задержке до expiry C0 уточняет interval до
   первого commit. После первой попытки exact даты/contact сохранять на retries.
4. **C3/C6:** accepted getMe/getWebhookInfo → optional bounded discovery только без
   webhook → exact getBusinessConnection/Owner verification. Сохранить external
   connection ID **до** setup; нельзя ACK/drop/offset/paginate очередь или заменить
   чужой webhook. getUpdates не ACK очередь, но allowed_updates может изменить
   provider subscription; не называть его полностью свободным от side effects.
5. **C3/C6:** существующий setup атомарно коммитит typed billing/binding, затем
   setWebhook. Проверить actual configuration/health/is_enabled/can_reply; READY
   сам по себе не доказывает права/свежее окно. При COMMITTED_WEBHOOK_UNCONFIRMED
   восстанавливать exact setup с сохранёнными IDs/dates, без reset/rebind/drop.
6. **Владелец/test Client под руководством C0:** свежий synthetic text+Telegram photo
   в диалог **с Owner**, правильный Console Workspace, READY private image через
   реальный браузер, один ручной ответ из Console, отдельное подтверждение Client.
   API send smoke не запускать параллельно UI: единственное намерение создаёт Owner.
   UNKNOWN/timeout/потеря202 — существующий exact-intention recovery, не новый key.
7. **C0:** собрать очищенный dated receipt и закрыть только доказанные A09/A11;
   согласованно обновить три docs, final-head CI, обычный merge владельцем и actual
   main CI. M2 VERIFIED только после всех принятых частей и фактического Client receipt.

### Матрица результата и границы проверки

| Критерий | Уже подтверждено | Осталось фактически исполнить |
|---|---|---|
| A12 | Actual main37016012805 SUCCESS; C8-HOST PASS; неизменённые code/CI и миграции | Final receipt PR и после его интеграции separate main CI |
| A09 external | Детерминированные rights/window/errors tests и accepted UNKNOWN recovery | Approved Owner/bot/connection, actual rights и webhook; ограничения доступа видны, нет обхода |
| A11 | Controlled Console journeys и trusted host/HTTPS prerequisites | Реальные text/photo→правильный Workspace/Console→private browser image→manual reply→Client receipt |
| A07/A08/A10 live path | DB/S3/API/browser isolation/recovery tests сохранены | Signed image в браузере этого host, правильный actor/Workspace/dialog и наблюдаемый delivery |
| A02/A04/A05 | Existing real PostgreSQL/crash/wire-call tests PASS | Сохранять durable state и не вводить слепой resend; destructive live fault injection не добавлять |

C3 выполнил source/official-doc identity+setup review, C6 — source/первый terminal
block review, C0 — syntax/состав/refs. Это не новый C8 и не live execution. Новый
scoped C8 назначать при конкретной новой границе или найденном defect; прежний
C8-HOST не расширять на будущую binding/переписку автоматически.

### Действие владельца сейчас и неизменные ограничения

В PowerShell подключиться прежним SSH key к **asmoperator@89.169.141.53**; на VM
исполнить **один блок §0.5.1**. Новый пароль24–32ASCII хранить в password manager,
не вводить пароль Telegram или token. Вернуть только JSON с3UUID и marker либо
очищенную ошибку. C0 не имеет SSH доступа и не может выполнить этот ввод за владельца.
Новых покупок, секретов в чате, ручного выбора SQL/env/полей и повторного mergePR23 нет.

Boot auto_delete=true и отсутствие backup/restore PASS остаются явными TEST
ограничениями. Удаление VM/disk/volumes/reset/down-v не разрешено; budget reviewNov1
не удаляет ресурсы автоматически. M2 IN_PROGRESS; AI/M3/takeover/запись/цены/платежи
не входят в задачу. Архивы ниже — история, не текущие инструкции.

</details>

<details>
<summary>История — приёмка host до merge PR23 / 2026-10-02</summary>

## Исторический handoff C0 — M2-ENV-03-TEST-HOST: приёмка / 2026-10-02

**REVIEW: один внешний TEST host исполнен владельцем; TG disabled.** Не повторять
старый onboarding, создание VM/ключей/env, init/reset или уже выполненные probes без
конкретной причины. Текущая работа C0 — принять фактическое evidence и исправления
процедуры через scoped C8, проверить final-head CI PR23 и подготовить обычный merge
владельцем. Доступа C0/C6 к личному облаку/SSH нет; выводы оператора не выдаются за
прямые проверки агента. M2 IN_PROGRESS; live A09/A11 ещё не исполнены.

### Точные refs, scope и состояние интеграции

- Repository **Elefesys/ai-service-manager**, **c6/m2-test-host → main**,
  [PR #23](https://github.com/Elefesys/ai-service-manager/pull/23).
- Accepted base/main/runtime **80e51c43e31541940f1ccf18b8281adf1a061748**,
  tree **88ed308b4c56114aa977dcf91204964d9b7348e5**.
  [Отдельный push/main CI36825583134](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
  SUCCESS:492 unit/390 PostgreSQL-S3/111 frontend/27 browser; оба штатных scripts и
  clean-source gates. Эти counts относятся к тому run, не к ручным host checks.
- Сохранён первый coordination **1f42a617ed64bc6fd4dd573cd5c721d22a7bf256**,
  tree **1b5188bed8de7fd0be98097eb9f7b4dbd6a86b0a**; промежуточный procedure head
  **61a96f1842071614ce338da88a359775d61bcfdb** имеет CI36836569381 SUCCESS.
  История не переписывается. Exact final head/tree/tested checkout, актуальный C8
  и CI — в PR receipt; не делать коммит ради SHA собственного docs commit.
- Ровно три разрешённых paths: **docs/TASK_REGISTER.md**,
  **docs/tasks/M2_HANDOFF.md**, **docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md**.
  Runtime/app/Compose/pins/зависимости/CI/assertions/contracts/миграции не изменяются.
  PR23 не обновляет приложение на VM и не требует повторной сборки из-за docs.
- Применимые документы: AGENTS, Spec M2/environment/private files/auth/recovery,
  ADR138/141/142/243, IMPL-001, M2_CONTRACT §§9–11, Implementation Plan §§6–7,
  Production Runbooks §§1–3. Production managed DB/storage и restore gates сохранены.

### Фактический результат и точные границы

Единственный подробный receipt и исправленная процедура —
[runbook §0.4.9](../runbooks/M2_TELEGRAM_LOCAL_TEST.md#049-фактическое-исполнение-и-решения-c0--2026-10-02).

| Критерий host | Фактическая проверка / граница |
|---|---|
| Source/входы | Accepted SHA/tree и clean source повторно PASS после renewal; старые pins; temporary read-only deploy key удалён владельцем; private env/TLS modes сохранены |
| TEST ресурсы | VM fhm53804pjetng9i46h2 RUNNING, created2026-10-02T04:57:26Z; согласованные2vCPU/8GiB/60GiB; idle memory/disk без OOM, NTPyes; не load/SLA test |
| Сеть | SoleSG:22 от31.135.48.89/32,80/443 public; static89.169.141.53. С ПК22/443 доступны,5432/8000/8080/9000/9001 недоступны. Отдельный deny22 с другого IP не исполнен |
| DNS/TLS/renewal | Два exact .com A/hostnames; CA/SAN/expiry PASS, unknown-SNI exact alert; Certbot dry-run + copy/reload + повторный HTTPS PASS; timer NEXT подтверждён |
| Compose/private storage | migrate/storage-init exit0; STORAGE_PRIVATE_BOOTSTRAP_PASS; семь running/OOMfalse; HTTPS health200; anonymous bucket403 AccessDenied внутри/снаружи |
| Telegram boundary | cfg.disabled и TG secrets empty, LOCAL/exact origin/endpoint assertions; webhook503 UNAVAILABLE/no-store и other404. Никаких provision/binding/setWebhook/sends |
| UI граница | Login screen открыт с trusted TLS; authenticated Console, signed image и Client delivery ещё не проверены |
| Review/CI | Новый scoped C8 готового config/receipt и final-head CI обязательны; старый static PASS не заменяет их. Hash/scope/результат — PR receipt |

### Явные исправления и ограничение сохранности TEST state

Причины host-сбоев установлены; protective assertions не убраны:
cloud-init26.1 exact datasource schema warning не очищен/не перезапущен;
исходный umask077 сделал tracked bootstrap нечитаемым для postgres — права только
Git-tracked файлов исправлены, прежний DB container/volume сохранён и bootstrap
выполнен после empty-state guard. Непривилегированные app images пересобраны из тех
же source bytes; исходные pins не менялись. Исправлены stdin у команд без входа и
Windows PowerShell explicit TLS1.2; причина исходного SystemDefault сбоя не доказана.

**Решение C0, явно меняющее ошибочную host-инструкцию:** boot disk actual
**auto_delete=true**. Standalone VM deletion-protection и in-place boot flag setter
в проверенных интерфейсах отсутствуют; provider Terraform требует replacement.
Для уже работающего синтетического TEST сохранить VM как есть, без нового ресурса/
расхода/миграции ради переключателя. Это принятие известного риска, а не утверждение
disk protection/backup: удаление VM удалит DB/files. IP protection отдельно PASS.
Удаление/recreate/detach диска, down-v/reset сейчас не разрешены. Перед будущей
заменой C0 готовит отдельное сохранение/проверку восстановления состояния; после
потери state effects остаются выключены до Inbox/Outbox/provider reconciliation,
UNKNOWN не resend. Production требования и M12 restore drill не отменяются.

Стоимость прежней конфигурации **4735,81₽/30 суток** подтверждена Console estimate,
не фиксированным счётом. Контроль расходов **2026-11-01** после VM creationOct2;
ранее зарезервированный IP и неинвентаризированные прежние snapshots могут
тарифицироваться отдельно. Snapshot schedule INACTIVE — owner receipt. Никакой
автоматический spending cap/reminder/auto-delete этим документом не настроен.

### Единственная ближайшая последовательность

1. C0 завершает независимый **C8-M2-ENV-03-HOST** именно этих изменений/evidence;
   сохраняет ограничения и устраняет конкретные blockers, если найдены. Предыдущий
   C8-PROCEDURE Oct1 и отдельный PG-RECOVERY Oct2 — разные ограниченные reviews.
2. Один согласованный docs commit в существующий PR23; финальный CI после него,
   exact tested tree/checkout и checks в PR receipt. До PASS не снимать Draft.
3. После PASS C0 даёт владельцу прямую ссылку и действие **обычный merge commit PR23**;
   самостоятельно merge не выполняет. После сообщения о merge проверяет actual
   main commit/tree и отдельный push/main CI; только тогда ENV03 INTEGRATED/VERIFIED.
4. От принятого actual main C0 выдаёт одно готовое ограниченное C3/C6 поручение
   **M2-LIVE-A09-A11**: private secret entry, preflight/binding/rights, Client text+image
   → нужный Workspace/Owner Console/private image → manual reply → получение Client.
   Пока не запускать §4–6, provision_telegram_test/setWebhook, не создавать Owner/billing
   и не включать TG. Не запрашивать токены/пароли в чате/PR.

Это prerequisite A07/A08/A09/A11/A12, не новая продуктовая матрица. M2 остаётся
IN_PROGRESS до фактического Client scenario и успешного main CI. M1 и принятый
M2.1–M2.4 code не переделывать; M3 не выдан. От владельца сейчас новые host-команды
не требуются. История ниже не является текущими инструкциями.

</details>

<details>
<summary>История — поручение подготовки до actual host / 2026-10-01</summary>

## Исторический handoff C0 → C6 — M2-ENV-03-TEST-HOST / 2026-10-01

**IN_PROGRESS: процедура подготовлена; ожидается исполнение на одном внешнем TEST host.**
2026-10-01 владелец подтвердил активный billing и созданный folder asm-telegram-test.
Это owner receipt; доступа к личному cloud account/SSH у C0/C6 нет. Точная процедура
находится в runbook §0.4; исполнение VM/DNS/TLS ещё не подтверждено. Telegram
connection и реальные sends не входят в этот шаг. M2 IN_PROGRESS;
live A09/A11 пока BLOCKED runtime/DNS/TLS.

### Подтверждённая интеграция и точный base

- Repository **Elefesys/ai-service-manager**, новая отдельная ветка
  **c6/m2-test-host → main**, [Draft PR #23](https://github.com/Elefesys/ai-service-manager/pull/23). PR #22 уже merged.
- Accepted base / actual main **80e51c43e31541940f1ccf18b8281adf1a061748**,
  tree **88ed308b4c56114aa977dcf91204964d9b7348e5**.
- Actual merge PR22 имеет ordered parents
  **96d9f09dd16d8b6ab019ac76a9c72ce910d81191** +
  **925952086b8ec83f2648b84094f546ec458cfde4**; tree равен принятому final PR tree.
- [Push/main CI36825583134, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
  **SUCCESS**: foundation110250425002/browser110250424676 checkout именно actual
  merge. 492 unit/390 PostgreSQL-S3/111 frontend/27 browser; оба scripts/clean-source
  gates, migrations/contracts/reproducibility/HTTP smoke PASS. Final PR CI36824246755
  также SUCCESS. Registry/storage задачи INTEGRATED и VERIFIED в LOCAL/TEST scope.
- C8-M2-ENV-02 действительно выполнен и PASS для packaging/anonymous bytes/pins/
  полного CI. Новых implementation bytes при merge нет; повтор этого review не нужен.
- Сохранённый первый coordination commit **1f42a617ed64bc6fd4dd573cd5c721d22a7bf256**,
  tree **1b5188bed8de7fd0be98097eb9f7b4dbd6a86b0a**; его CI36830564375 SUCCESS.
  Exact final head/tree/CI этого дополнения записываются в PR receipt;
  не добавлять docs commit только для собственной SHA.
  Runtime разворачивается с принятого **80e51c43e31541940f1ccf18b8281adf1a061748**;
  последующие docs-only commits не являются новой реализацией приложения.

### Прочитать и сохранить решения

AGENTS; текущий TASK_REGISTER; этот блок; runbook M2_TELEGRAM_LOCAL_TEST §§0–3;
M2_CONTRACT §§9–11; IMPL-001; применимые Spec environment/private files/auth,
ADR138/141/142/243; Production Deployment/Runbooks §§1–3 и Implementation Plan
§§6–7. Прочитать текущие Compose, init_local.py, Dockerfiles, ingress config,
Telegram settings и provisioners, прежде чем выдавать исполняемые команды.
Исторические поручения ниже не выдаются повторно. Production managed DB/Object
Storage остаются принятым будущим deployment contract; один TEST host их не заменяет.

Сохраняется принятая конфигурация: Yandex RU, **ru-central1-a**, Ubuntu24.04 LTS
x86_64, non-preemptible **standard-v3/2vCPU100%/8GiB**, **60GiB network-ssd**,
**один static public IPv4**, отдельный folder **asm-telegram-test**. Оценка с НДС
**4735,81 ₽/30 суток** подтверждена по официальным rates 2026-10-01. Дополнительные
платные managed services/LB/NAT/Cloud DNS/backups/marketplace/SSL не включать.
Если точная конфигурация недоступна или цена изменилась существенно, вернуть C0
конкретную альтернативу/стоимость до подключения; обычные решения внутри scope — C6.

Два единственных hostname: **console.telegram-test.clientmanagerai.com**
(Console/API/webhook/auth origin) и **files.telegram-test.clientmanagerai.com**
(private signed files). .com NS Timeweb подтверждены публичным resolver2026-10-01;
обе A-записи пока NXDOMAIN. .ru NS NXDOMAIN у проверенного resolver — не вывод о
внутренней проверке регистратора. .ru остаётся предпочтительным будущим основным
доменом; ждать его для smoke и включать две auth-зоны параллельно не нужно.

### Scope C6 и разрешённые изменения

1. Подготовить в существующем runbook один последовательный набор точных действий
   для нового host, выбранных SSH/network/DNS/TLS parameters и безопасного source
   delivery из private repo. Не передавать владельцу выбор полей/env/SQL или сборку
   команд из нескольких документов. Не предполагать установленный доступ агента.
2. После доступности account/billing исполнить через разрешённый доступ либо дать
   владельцу готовые команды с ожидаемым non-secret выводом: isolated folder/network/
   subnet/security group, VM/disk/staticIP, non-root asmoperator/SSH key, Docker+
   Compose и time sync. SSH22 только operator IPv4/32;443 public;80 только ACME.
   Default all-open SSH/RDP group не прикреплять. API8000/frontend8080 loopback;
   PostgreSQL5432/MinIO9000/9001 извне недоступны.
3. Две точные A-записи на этот IP, без wildcard/неподтверждённого AAAA; бесплатно
   выпустить trusted TLS для двух имён, renewal dry-run + deploy hook копирования
   сертификатов с600/700 modes и reload существующего nginx ingress. Порты/renewal
   должны согласовываться: если80 закрыт, hook безопасно открывает/закрывает его
   на challenge; иначе80 слушает только standalone Certbot во время challenge.
4. Exact accepted checkout, init_local без замены существующих credentials, прежние
   image digests и Compose project **asm-telegram-test**. Это **ASM_ENVIRONMENT=LOCAL**,
   asm_local/private local bucket на отдельном TEST host; не переименовывать profile
   ad hoc. **ASM_TELEGRAM_ENABLED=false**, TG secrets на данном шаге не нужны.
   Проверить build/health/resources и private endpoint без live binding или отправок.
5. Передать C0 sanitized receipt и фактические ограничения. Внешние public network,
   auth-origin, TLS/secrets/private-file границы требуют нового короткого scoped C8
   по готовой процедуре/config/evidence; C0 организует его, когда есть что проверить.
   Предыдущее storage review и self-check C6 за такой review не выдаются.

Разрешённые repository paths ровно три: **docs/TASK_REGISTER.md**,
**docs/tasks/M2_HANDOFF.md**, **docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md**.
Task/status/receipt — согласованно; commands — в runbook. Runtime local files
(.env*, TLS, ingress, host service/renewal config) не коммитить и не включать в build
context. Application/Compose/locks/pins/workflows/tests/contracts/миграции0001–0007
сохраняются. Если обнаружен конкретный code/config defect, вернуть reproducer C0
для ограниченного решения, не обходить guard и не расширять allowlist самостоятельно.
Не пересобирать public storage artifacts, не менять package/repo visibility.

### Конечные критерии результата и границы evidence

| Результат | Требуемая фактическая проверка |
|---|---|
| Exact source/входы | 40-character runtime SHA80e51c4, clean source, pinned images; версия Docker/Compose/Ubuntu/architecture; нет secret/build-context drift |
| Один согласованный TEST host | Config VM/disk/IP/zone и фактическая оценка; clock sync; build/health без OOM/disk exhaustion; лимит/дата следующего решения о расходах |
| Сетевая граница | Снаружи TLS443 работает; запрещённые DB/S3/API/frontend ports недоступны; SSH ограничен operator/32; неизвестный SNI отклонён; фактический security group без default-wide ingress |
| DNS/TLS | Оба exact A → один staticIP; trusted chain/SAN и срок; renewal dry-run/deploy reload; нет wildcard/второго auth origin |
| Existing Compose/private files | migrate/storage-init exit0, STORAGE_PRIVATE_BOOTSTRAP_PASS; HTTPS /health/ready →200 status:ok/component:database; worker/scheduler/frontend running; anonymous HTTPS listing asm-private-local →403 AccessDenied; signed-object/auth/browser проверки ещё не объявлять исполненными |
| Side-effect boundary | Внутри API итоговый marker подтверждает Telegram disabled и отсутствие TG secrets без вывода значений; POST /webhooks/telegram →503 UNAVAILABLE/no-store, другой /webhooks/* →404; provision_telegram_test/setWebhook/smoke send не запускались |
| Review/регрессия | Scoped C8 новых внешних границ после конкретного config; для repository delta final-head CI и clean-source gates; host check не подменён hosted CI |

Это prerequisite существующих A07/A08/A09/A11/A12, а не новая матрица требований.
При готовом host реальные connection/rights и Client text+photo → Console → manual
reply → Client выдаются следующим коротким поручением C3/C6. UNKNOWN никогда не
повторять слепо. Не запускать общий CI script на persistent live Compose project,
не использовать down -v/reset и не терять durable state ради проверки.

### Подготовленная процедура, следующий шаг владельца и возврат C6

Account/billing/folder завершены **по подтверждению владельца 2026-10-01**;
повторять onboarding не нужно. Следующая работа — существующий runbook §0.4:
локальный SSH key, operator IPv4/32, одна ограниченная сеть/VM в выбранном folder,
затем проверенный source/DNS/TLS и pre-live readiness. C6 выбирает конкретные
технические поля и команды; владелец выполняет их в своём личном кабинете/терминале.
Причина owner execution — отсутствие cloud/SSH подключения у агента. Повторного
согласования той же конфигурации/бюджета нет. Факт покупки/создания ресурса и каждый
PASS утверждаются только после результата оператора или независимой внешней проверки.

**C8-M2-ENV-03-PROCEDURE — независимый scoped PASS, 2026-10-01.**
Проверен точный runbook SHA-256
**96d2c128b9d51c9665a7d03d4fed1f239340c910eaa345f8afbf53f968314066**:
ресурсы/сеть/SSH, exact source и read-only deploy key, secrets/build context,
TG-disabled до запуска, TLS/renewal, private bucket, внешние ports и сохранение state.
После review добавлены и независимо перечитаны prestart shell-override guard,
HTTPS probe внутри API через принятые network aliases, строгий SAN/unknown-SNI alert,
внешние PowerShell health/private403/ports assertions; лишний HOME override убран.
C6/C0/C8 проверили syntax: **11 Bash blocks + renewal hook**, **6 Python heredocs**;
PowerShell прочитан статически. P0/P1/P2 blockers процедуры не осталось.
Это review команд и existing source80e51c4, **не** Yandex/Windows/host execution.
Runtime/DNS/TLS, authenticated browser/signed files и live A09/A11 пока не проверены.
Обязательный CI итогового documentation head записывается в PR receipt после его
завершения; он не подменяет actual host acceptance и не требует SHA-only commit.

Процедура и прежние §2–6 различают pre-live TG=false и последующий live setup.
До приёмки host не вызывать setWebhook/provision_telegram_test/smoke send. C0
принимает factual host receipt, затем выдаёт connection/rights/live A09/A11.
Если консоль/команда отказывает или результат неоднозначен, сохранить non-secret
ошибку и проверить actual ресурсы; не повторять paid create/менять параметры/удалять
состояние вслепую. Runtime/Telegram secrets и private SSH keys не присылать.

C6 возвращает PR/head/tree/parent/base ancestry, полный changed-path list, exact
commands и реальные результаты по таблице, scoped review status, runtime SHA и
sanitized host/DNS/TLS/cost receipt. Невыполненные проверки назвать BLOCKED, без
заявлений о ready host/live Telegram. PR оставить Draft до приёмки C0, не merge.
Это один активный handoff; архивы ниже не текущие команды.

</details>

<details>
<summary>История — приёмка PR #22 до actual merge / 2026-10-01</summary>

## Исторический handoff C0 — M2-ENV-01/02: приёмка и интеграция PR #22 / 2026-10-01

**M2-ENV-01-REGISTRY / M2-ENV-02-STORAGE-IMAGES — REVIEW.** C0 и независимый scoped
C8 приняли ограниченное исправление LOCAL/TEST storage provisioning. Полный CI на
implementation head восстановлен. Merge ещё не выполнен; final-head CI после
последнего документационного изменения проверяется отдельно и записывается в PR.
Весь M2 IN_PROGRESS; live A09/A11 BLOCKED внешними runtime/DNS/TLS. M3 не выдан.

### Точная версия и единственный следующий шаг

- Repository **Elefesys/ai-service-manager**, **c6/m2-live-smoke → main**, [PR #22](https://github.com/Elefesys/ai-service-manager/pull/22).
- Accepted main/base **96d9f09dd16d8b6ab019ac76a9c72ce910d81191**, tree
  **28de72ca6737cbe18bb4856a1636f70fae1131ee**; отдельный исторический main CI35706123814 SUCCESS.
- Первый coordination **914e2894f98330d62e1cc57ca5da5c62662d6960** и вся история сохранены.
  Старт упаковки **1450dfeefeead337ca8a8a670d339e085adfe323**; перед public access
  head **4f6180be1496aceb1a0ee292ce39790bd42bf81a**.
- Принятый implementation head **809d44c77b45d86b54750969db5b4a3ec411e0e3**, tree **42a17e82cae204a1f4a8d3f3bc3dcd798fc03cc8**; только две строки
  в каждом из infra/images.lock.env / scripts/pin_images.sh относительно 4f618…;
  Git modes обоих файлов **100644** сохранены.
- [обычный CI 36823298856, attempt 1](https://github.com/Elefesys/ai-service-manager/actions/runs/36823298856) **SUCCESS**. Фактический checkout/ordered parents/tree проверены C0/C8 и
  записаны в receipt PR. После него меняются согласованно только TASK_REGISTER,
  этот handoff и runbook; exact final head/tree/final CI ведутся в PR receipt,
  без цепочки коммитов ради SHA предыдущего документационного коммита.
- После сообщения C0 о SUCCESS именно последнего head пользователь выбирает
  **Merge pull request → Create a merge commit → Confirm merge**
  (Draft предварительно снимает C0). Squash/rebase не использовать. C0 самостоятельно
  не сливает PR. Затем C0 проверяет actual merge commit/tree и отдельный push/main CI.

### Что принято и что осталось неизменным

Решение C0 2026-09-30 о новой упаковке двух exact official binaries сохранено:
новые OCI bytes принимаются по собственному evidence; идентичность старым
недоступным Quay images не заявляется. Оба прежних MinIO/mc releases неизменны.
Применимы IMPL-001, Spec private storage/immutable inputs/LOCAL-TEST, ADR138/141/142,
Implementation Plan §§6–7 и M2_CONTRACT §§9–11. Production storage/cloud ADR не менялись.

Полная дельта PR — ровно девять разрешённых paths:

| Paths | Принятая дельта |
|---|---|
| infra/storage/Minio.Dockerfile; infra/storage/Mc.Dockerfile | Пакетирование exact подписанных binaries на pinned curl/CA/sh base |
| infra/storage/inputs.lock.json | Единственный immutable lock binaries/signatures/key/source/licenses/base/build tools |
| .github/workflows/storage-images.yml | Изолированные build/verify/publish jobs; pinned actions, временный token только publisher |
| infra/images.lock.env; scripts/pin_images.sh | Только две storage refs/pins на точные public GHCR digests; прочие pins и guard существующих значений сохранены |
| docs/TASK_REGISTER.md; docs/tasks/M2_HANDOFF.md; docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md | Один актуальный статус/handoff, evidence и воспроизведение; прежние инструкции отделены как история |

Приложение/frontend/API/contracts, миграции 0001–0007, основной CI/Compose/bootstrap,
tests/assertions и прочие dependencies byte-identical принятому scope. Новых
workflow/build/publish после открытия packages не выполнялось; storage workflow
не срабатывает на два pins или документацию.

### Public artifacts: полные bytes и отдельный runtime gate

Владелец подтвердил Public обоих packages 2026-10-01. C0 проверил anonymous manifest
GET; C6 в новом пустом Linux/x86_64 каталоге скачал **95 747 170 bytes**: оба manifest,
оба config и все шесть layers. HTTP200, descriptor SHA/size, platform/source labels,
uncompressed diffIDs и семь added files каждого image (bytes/modes/UID/GID, без
дополнительных files/symlinks) совпали с build/publish receipts. C0 и C8 независимо
пересчитали сохранённые blobs; C8 дополнительно проверил allowlist tar members.
Команда C6: `python verify_public_images.py`, завершена 2026-10-01T06:08:02Z;
local receipt SHA-256 **07992f7085ad9826503870ed0984ad469ebbe9d761fb13134ae553f5c1eba211**. Это byte/access evidence, не Docker execution.

**Явное решение C0 2026-10-01 о порядке:** локально Docker отсутствует. Полный
anonymous OCI download и hash verification выполнены до двух pins; fresh Docker
pull/runtime — затем в неизменном обычном CI на новых hosted runners без storage
login/cache restore. Обязательный gate до приёмки/merge сохранён; HTTP download
его не подменяет. C8 принял это разделение evidence. Повторная сборка или новый
workflow только ради probe не нужны.

| Image | Принятый immutable linux/amd64 ref | Config SHA-256 |
|---|---|---|
| MinIO | ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa | b7bb806bee433a13f30a01509f324cfc5c764e4a07b11353aa423eda2e995c1d |
| mc | ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4 | 85c9b02133dbec707e92450e93ca5a98e139423839b02946583bdd9ddd2cf2f6 |

Image source **f74c240febd963c79408e80600c29d7739e08867**; одиночные linux/amd64 manifests,
не OCI index, embedded attestations отсутствуют. Provenance — отдельные bound receipts.
Binary hashes: MinIO **7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f**
(110989496 bytes); mc **7a03ba39e158708a9e88f1bf5c346c6651b15c784e4b2c7150b5b5f282f43c28**
(29208728 bytes). Source/license/minisig/key/base/tools сохранены в historical build receipt ниже;
registry layer digests/diffIDs — в receipt PR #22. Exact input lock остался прежним.

### Фактическая проверка и независимый C8

[обычный CI 36823298856, attempt 1](https://github.com/Elefesys/ai-service-manager/actions/runs/36823298856): **sh scripts/ci.sh** и **sh scripts/test_browser.sh**, оба source gates,
canonical/migration cycles/contracts/reproducibility/HTTP smoke PASS.
**492 unit / 390 PostgreSQL-S3 / 111 frontend / 27 browser** — справочные counts,
а основание приёмки — следующие инварианты и исполнение соответствующего suite:

| Критерий | Конкретное evidence |
|---|---|
| Подлинность и воспроизводимость packaging | Storage run36734267078: полный vendor hash/minisig + tampered negative; два no-cache builds, exact config/layers/archive hashes; bound receipts до publish |
| Публично доступны только принятые image bytes | C0 pre-public review четырёх версий; C6 anonymous download всех final blobs; C0/C8 повторный hash/diffID/added-files audit; private repo не открывался |
| Private storage, A07/A08 | test_m2_2_storage_postgres: signed GET exact bytes/hash/MIME/private-no-store; anonymous GET/PUT/list/tamper403; Workspace/relation/OWNER, revoke/TTL; checksum rejection/conditional PUT |
| Durable recovery, A06/A08 | test_m2_2_recovery_postgres: реальные process crashes, late PUT/cleanup winner/fencing; M2.1 и M2.3 real-wire cases: UNKNOWN после потерянного ACK, ровно один сохранённый call, без resend |
| Совместимость runtime | Обычный CI реально скачал GHCR images; bootstrap/health/version/private S3 PASS. Storage run36734267078 дополнительно проверил SIGTERM/exit0, неизменные Mounts и сохранение exact data после restart без удаления volume |
| Console regression в CONTROLLED scope | 27 browser journeys: private image + unsigned403, exact reply, committed202 recovery без дубля, UNKNOWN после replacement worker с одним call, isolation/revocation и прежние M1 journeys |

**C8-M2-ENV-02 — независимый scoped PASS:** reviewer самостоятельно прочитал четыре
packaging файла, official input/key metadata, Git objects/delta, logs/receipts;
проверил минимальные permissions, allowlist/context isolation, artifact/source/config/
package binding, все anonymous OCI blobs, два pins и фактический полный CI.
Блокирующих findings нет. C6 self-check и прежний M2.4 C8 этим review не подменялись.
Локальный Docker/PostgreSQL rerun C0/C8 и загрузка большого 96MB build ZIP не заявляются;
runtime evidence получено с GitHub runner. Полные OCI bytes скачаны отдельно, small
receipt ZIPs проверены побайтно. Final source artifact/checkout границы — в PR receipt.

### Конечный остаток M2

1. Пользовательский merge PR #22 после final-head CI; C0 подтверждает actual merge
   и отдельный push/main CI. Только после этого M2-ENV задачи INTEGRATED/VERIFIED.
2. Ограниченный Yandex RU TEST host по принятому бюджету, два .com hostnames,
   DNS/TLS и безопасная инъекция уже подготовленных секретов; точное следующее
   поручение C6 выдаётся от подтверждённого нового main.
3. Реальные A09/A11: connection/rights и Client text+photo → правильный Workspace/
   Owner Console/private image → ручной ответ → фактическое получение Client.

Bot/Owner/Client и TG_BOT_TOKEN/TG_WEBHOOK_SECRET в менеджере паролей уже готовы.
Токены в чат/PR не передавать. Платный host/DNS/TLS/webhook/live sends здесь не
настраивались. CONTROLLED/SENT/зелёный CI не закрывают live Telegram и весь M2.

</details>

<details>
<summary>История — исходный M2-ENV-02 и private-public access gate / 2026-09-30</summary>

## Исторический handoff C0 → C6 — M2-ENV-02-STORAGE-IMAGES / 2026-09-30

**Private artifacts готовы; IN_PROGRESS / ACCESS gate public visibility. Registry recovery BLOCKED.**
M2.4 code/UI VERIFIED только LOCAL/TEST; весь M2 IN_PROGRESS, внешние A09/A11
BLOCKED runtime/DNS/TLS. M3 не выдан. Это продолжение устранения provisioning
blocker M2-ENV-01-REGISTRY внутри M2-LIVE-A09-A11, а не новая продуктовая часть.

### Решение C0 и точный старт

Диагноз C6 принят: доступный подтверждённый источник прежних OCI artifacts не
найден; повторять одинаковые reruns или ждать домена для решения registry не нужно.
**C0 явно заменяет прежнее условие «только идентичные OCI bytes» разрешением новой
упаковки двух exact official release binaries.** Версии MinIO/mc сохраняются,
новые OCI config/layers/digests принимаются только по новому evidence и scoped C8.
Это не восстановление byte identity старых images и не обновление storage продукта.
IMPL-001/production storage ADR и бизнес-контракты M2 остаются без изменений.

- Repository **Elefesys/ai-service-manager**, та же **c6/m2-live-smoke → main**,
  [Draft PR #22](https://github.com/Elefesys/ai-service-manager/pull/22).
- Accepted implementation base / actual main:
  **96d9f09dd16d8b6ab019ac76a9c72ce910d81191**,
  tree **28de72ca6737cbe18bb4856a1636f70fae1131ee**.
  [Отдельный main CI35706123814](https://github.com/Elefesys/ai-service-manager/actions/runs/35706123814)
  исторически SUCCESS; он не заменяет текущий failing CI.
- Сохранить первый coordination **914e2894f98330d62e1cc57ca5da5c62662d6960** и всю
  последующую историю. Непосредственный parent этого задания:
  **6159a64cfb08c853dac4ff51c415e32c083e735f**,
  tree **bf1ae81a65c7b1695a6f413f92a2c0cd49399593**.
  **Exact старт — 1450dfeefeead337ca8a8a670d339e085adfe323**,
  tree **7f5ff73b4c2f6bb5c952ac2b1c1dab87b2725325**, содержит этот handoff.
  Вся история сохранена; force-push/новый PR не нужны.
- C0 прочитал оба job logs [CI36717840363, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36717840363):
  foundation109895106793 и browser109895107151 FAILURE на MinIO pull unauthorized.
  Checkout **349b84b9a942d21e0d4db92f84b2cd2e15d21b20** — virtual merge;
  Git object подтвердил ordered parents accepted main +6159a64… и тот же tree.
  Canonical/frontend111/Compose PASS; PG/S3/browser/UNKNOWN не исполнились;
  оба clean-source gates SKIPPED. Диагноз не означает, что проверки восстановлены.
  C0 также сверил hashes/sizes с official GitHub release API; повторное скачивание
  binary bytes C0 в этом review не заявляет. Полный download/hash — evidence C6.

### Читать перед реализацией

AGENTS; текущий TASK_REGISTER; этот активный блок; IMPL-001; M2_CONTRACT §§9–11;
runbook M2_TELEGRAM_LOCAL_TEST §§0–1; images.lock.env, pin_images.sh, Compose,
infra/storage/bootstrap.sh, оба штатных scripts и основной ci.yml. Применимые
Spec/ADR — immutable inputs/private storage/LOCAL-TEST, Implementation Plan §§6–7.
Исторические M1/M2 поручения ниже не являются повторно выданными задачами.

### Единственный разрешённый результат и 9 paths

Два project-owned **linux/amd64** image с проверенными vendor binaries, совместимые
с существующими Compose/health/bootstrap semantics; затем anonymous immutable pull
и полный CI. C6 самостоятельно выбирает минимальный официальный base с нужными
tools и фиксирует реально проверенный digest. Выбор base внутри этих условий —
реализация C6, не вопрос к пользователю. Переход на другой MinIO/mc release не разрешён.

| Path | Разрешённая дельта |
|---|---|
| infra/storage/Minio.Dockerfile | Новая упаковка принятого MinIO binary; необходимые curl/CA/shell/runtime metadata |
| infra/storage/Mc.Dockerfile | Новая упаковка принятого mc binary; shell/CA/bootstrap tools |
| infra/storage/inputs.lock.json | Единственный lock этих build inputs: releases, URLs, bytes/SHA-256, signatures/key provenance, pinned bases/tools, upstream source/licenses |
| .github/workflows/storage-images.yml | Отдельные build/verify и ограниченный GHCR publish jobs, receipts; не заменяет основной CI |
| infra/images.lock.env | Только STORAGE_IMAGE и STORAGE_ADMIN_IMAGE после фактического подтверждения новых artifacts |
| scripts/pin_images.sh | Только две storage source refs; immutable resolution, запрет обновлять существующие pins сохраняются |
| docs/TASK_REGISTER.md | Текущий статус, результат/границы; история сохраняется |
| docs/tasks/M2_HANDOFF.md | Один активный handoff и конкретный receipt |
| docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md | Воспроизводимые build/pull/operator действия, без секретов |

Новые shared lock/workflow paths согласованы C0 этим поручением. Не требуется ещё
одно согласование тех же девяти paths. Основной ci.yml, Compose, storage bootstrap,
ci.sh/test_browser.sh, application/frontend/contracts, migrations0001–0007, прочие
pins/dependencies и tests/assertions не меняются. Не добавлять mock/skip/xfail,
continue-on-error или обходы registry auth/network. Конкретный новый blocker вне
перечня возвращать C0 с минимальной дельтой; не останавливать независимые проверки.

### Проверяемые inputs и runtime contract

| Binary / official GitHub Release | Bytes | SHA-256 |
|---|---:|---|
| minio.linux-amd64.RELEASE.2025-09-07T16-13-09Z | 110989496 | 7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f |
| mc.linux-amd64.RELEASE.2025-02-15T10-36-16Z | 29208728 | 7a03ba39e158708a9e88f1bf5c346c6651b15c784e4b2c7150b5b5f282f43c28 |

Exact URLs и прежние OCI pins сохранены в историческом receipt C6 ниже. Для build
повторно проверить полные bytes/SHA-256 до исполнения. Verify оба minisig с ключом
из официального MinIO release Dockerfile:
**RWTx5Zr1tiHQLwG9keckT0c45M3AGeHD6IvimQHpyRywVWGbP1aVSGav**.
Зафиксировать exact upstream commit/key provenance и signature asset hashes в lock.
Не доверять ключу, впервые найденному только рядом с неизвестным mirror. Проверяющий
tool тоже имеет pinned input; mismatch/missing signature — явный blocker, не
автоматический переход к одному --version.

Base и все дополнительные build inputs фиксируются digest/hash. Не переносить
mutable latest, unpinned apt/apk/go install из upstream Dockerfile. Предпочесть base
с уже нужными curl/CA/sh, чтобы не строить отдельную цепочку package dependencies.
Сохранить LICENSE/CREDITS/соответствующие source references и необходимые материалы
распространения; не представлять project image официальным image MinIO.
В public content могут попадать только проверенные vendor inputs и минимальная
упаковка: не копировать private repository root, приложение, docs, .git или env.
Build context собрать из явного allowlist; секреты не передавать в image/build args.

Необходимые реальные проверки: minio/mc --version; server command/arguments;
curl health endpoint; sh /bootstrap.sh с mc/cat/rm; CA trust; /data и /tmp/config
permissions; exit/signals. Совместимость volume/data и restart проверяется без
удаления данных ради PASS. Не добавлять самопроизвольный minio update или mc update.
Новый image должен обслуживать принятый S3/private policy без изменения bootstrap.

Сохранить mapping: exact inputs → build source SHA → binary hashes внутри image →
platform manifest/config/layers и registry digest. Отдельно обозначить OCI index,
linux/amd64 manifest и attestation metadata. Rebuild из тех же locked inputs нужен
как проверка воспроизводимости; если меняется только служебная attestation, показать
это отдельно. Одинаковое --version не заменяет проверку bytes или объяснение
различающихся runtime config/layers.

### Публикация до merge: рабочая последовательность без PAT

Целевые packages: **ghcr.io/elefesys/asm-minio** и **ghcr.io/elefesys/asm-mc**.
Проверить отсутствие конфликта с уже существующими packages; ничего чужого не
перезаписывать. Использовать уникальные tags от build input/source SHA, не latest;
в runtime сохраняются только полные @sha256 refs.

1. Новый workflow запускается по **push в точную c6/m2-live-smoke** с paths filter
   четырёх новых build файлов. Для сопровождения после интеграции допустим
   workflow_dispatch только для main, с проверкой ref; никаких schedules/PR-target/
   arbitrary ref inputs. Не полагаться на первый workflow_dispatch до merge:
   GitHub документирует зависимость от default branch. Push в branch допускает
   проверку нового workflow до интеграции.
2. Build/verify job имеет только contents:read, checkout persist-credentials:false,
   actions pinned по полным commit SHA. Нет пользовательских secrets/PAT, общего
   Docker login и shared runner. Безопасный build receipt включает image archive
   hashes, input lock, manifest и точный source SHA; source gates не обходятся.
3. C0 разрешает **первичную публикацию двух новых private GHCR packages** этим
   workflow через временный **GITHUB_TOKEN**, только отдельному publish job с
   contents:read/packages:write. Guard проверяет exact repository, разрешённый
   event/ref, успешный verify job и соответствие проверенных image artifacts.
   В publish job не исполнять непроверенный скачанный код; не давать contents:write,
   PAT, production secrets, pull_request_target или общий packages:write workflow.
   Token не попадает в build context, logs или artifacts. Основной CI остаётся read-only.
4. **Успешный private push ещё не означает recovery.** Сначала подготовить оба
   packages, exact digests и проверяемое содержимое. Перед открытием public C0
   проверяет состав и выдаёт владельцу одно конкретное действие с URL обоих packages:
   Package settings → Change visibility → Public. GitHub предупреждает, что вернуть
   public package в private нельзя; поэтому согласование этой операции проводится
   для готовых проверенных artifacts, не для абстрактного будущего результата.
   Видимость самого private repository не менять. Конкретные packages готовы:
   C0 проверяет receipt ниже и организует действие владельца.
5. До public visibility C6 завершает все доступные build/signature/provenance/runtime
   проверки и возвращает конкретный ACCESS blocker, если нужен оператор. Не просить
   token в чате и не подменять anonymous pull логином в основном CI. Pins переключать
   только после подтверждения публичного доступа к обоим новым digest.
6. После открытия public проверить pull обоих immutable refs на свежем disposable
   linux/amd64 runner с пустым Docker auth config и без image cache. Зафиксировать
   downloaded digest/config/layers и binary hashes. Обновить только две refs/pins,
   затем выполнить оба прежних scripts/gates на final head. Если C0/C8 исправляет
   recipe/image bytes, пересобрать, перепроверить pins и итоговый CI.

Это один этап с возможным внешним шагом видимости, не новая функция продукта.
[GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
подтверждает default-private/GITHUB_TOKEN/anonymous public pulls;
[workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
— push/dispatch. По [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
на 2026-09-30 хранение/трафик GHCR container images бесплатны; Actions minutes/artifacts
имеют отдельные условия. Использовать существующие repo runner/лимиты; billing,
spending limits и платные сервисы не подключать/не повышать. Private публикация
подтверждена исполнением в receipt ниже; public anonymous pull ещё не подтверждён.

### Конечная приёмка C0 и новый независимый scoped C8

- Проверены оба signature/hash, pinned inputs, безопасный состав и реальный
  build/publish/pull по exact SHA; новый OCI artifact не выдан за исходный.
- На одном final head SUCCESS **sh scripts/ci.sh**, **sh scripts/test_browser.sh**,
  оба clean-source gates, canonical/migrations/contracts/reproducibility/smoke.
  Реально исполнились PostgreSQL/S3/private images и browser, включая изоляцию,
  anonymous deny/signed GET, interrupted upload/recovery, SEND UNKNOWN/no-resend,
  persisted call counter и прежнюю M1/M2 regression. Число tests — справка;
  конкретные assertions и исполнение обязательны.
- C0 организует **реальный независимый C8** по изменённым Dockerfiles/input lock,
  workflow permissions/provenance, двум pins и сохранности private-storage/recovery
  checks. Старый M2.4 C8 не покрывает новые image bytes. C6 self-review не называть C8.
  Повторять targeted review только по конкретным исправлениям или незакрытому риску.
- Exact final head/tree/tested checkout, ordered parents/tree comparison, commands,
  changed paths и фактические результаты — в одном PR receipt. ZIP byte check только
  если реально выполнен. Документы обновить согласованно; SHA-only commit не нужен.
- PR22 остаётся Draft до C0 приёмки; merge выполняет пользователь. После actual merge
  отдельно проверить push/main CI. M2-ENV-01 считается восстановленным только после
  полной проверки, M2/A09/A11 от этого VERIFIED не становятся.

После этой приёмки — прежняя M2-LIVE-A09-A11: ограниченный Yandex TEST host, проверка
.com DNS/TLS, реальный Client text+photo → Workspace/Console/private image → manual
reply → Client receipt. Бюджет принят ранее; VM сейчас не создавать. Согласованы
console.telegram-test.clientmanagerai.com и files.telegram-test.clientmanagerai.com;
.ru остаётся будущим основным доменом. Ни домены, ни Telegram secrets для этой задачи
не нужны. Live sends/production и M3 не добавлены.

### Receipt C6 — private artifacts готовы; ACCESS gate / 2026-09-30

**M2-ENV-02 IN_PROGRESS; M2-ENV-01 BLOCKED до anonymous pull и полного final-head CI.**
Оба artifacts опубликованы private; независимые build/signature/runtime проверки
завершены. Сейчас C0 может проверить конкретный состав и организовать public
visibility владельцем. C6 видимость packages/repository не менял. C8 не проводился.

| Ref / выполнение | Exact value |
|---|---|
| Accepted base/main | 96d9f09dd16d8b6ab019ac76a9c72ce910d81191 |
| Сохранённый первый coordination | 914e2894f98330d62e1cc57ca5da5c62662d6960 |
| Exact task start | 1450dfeefeead337ca8a8a670d339e085adfe323 |
| Build / фактически tested source SHA | f74c240febd963c79408e80600c29d7739e08867 |
| Tested source tree | 3e742d07440bcd2e4516922d5698ed1aee735db0 |
| Storage workflow | [36734267078, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36734267078), push точной c6/m2-live-smoke, SUCCESS |
| Jobs | verify109951705630 SUCCESS; publish109956285144 SUCCESS |

Это прямой checkout build SHA, не PR virtual merge. Последующий commit только
трёх документов фиксирует этот результат; его exact final head/tree и проверка
ancestry указаны в PR22 receipt без SHA-only цепочки. Вся история сохраняется.

#### Packages, digests и состав для C0

Оба packages принадлежат User Elefesys; repository ID1369650588. Visibility
проверена до и после финального push: private. Tag обоих финальных образов:
source-f74c240febd963c79408e80600c29d7739e08867.

| Образ | Package URL / ID | Immutable linux/amd64 ref |
|---|---|---|
| MinIO | [asm-minio](https://github.com/users/Elefesys/packages/container/package/asm-minio), ID15482993 | ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa |
| mc | [asm-mc](https://github.com/users/Elefesys/packages/container/package/asm-mc), ID15484077 | ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4 |

Это **новые OCI artifacts**, не старые Quay bytes. Registry возвращает одиночные
Docker V2 platform manifests linux/amd64; OCI index и embedded attestation
отсутствуют. Provenance/verification сохранены отдельными receipts.
Registry manifest/config сверены с проверенным загруженным image; fresh anonymous
pull всех layers пока не выполнен и не подразумевается private push.

| Образ | Image config digest | SHA-256 каждого из двух независимо построенных Docker archives |
|---|---|---|
| MinIO | sha256:b7bb806bee433a13f30a01509f324cfc5c764e4a07b11353aa423eda2e995c1d | 320c55ca2ff8c05f80f38262f0ed233bc9dd8d2ddd65d78e933d818f73deff40 |
| mc | sha256:85c9b02133dbec707e92450e93ca5a98e139423839b02946583bdd9ddd2cf2f6 | 9ac91013b51c188691dd290ce543e3749647e30f2445e0cc6c2cea659f9db450 |

Проверены два независимых no-cache builders: полные config (включая history),
layers, allowlist files и **полные archive bytes** совпали. SOURCE_DATE_EPOCH1790726400.
Dockerfiles не содержат RUN/install. Context каждого build состоит ровно из
Dockerfile, binary, LICENSE, CREDITS, source.tar.gz, binary.minisig, NOTICE,
inputs.lock.json. Added layer — только /usr/local/bin/minio либо mc и шесть
vendor/provenance файлов /usr/share/licenses/asm-minio либо asm-mc.
Base содержит curl/CA/sh; app/private docs/.git/env/secrets отсутствуют в этих
contexts, image additions и storage-workflow artifacts. Source label раскрывает
только URL этого repository и source SHA. USER0:0 сохранён для совместимости с
существующими volumes; это не новое изменение runtime privileges приложения.

Предыдущие private source tags сохранены: MinIO source-d2f192febb4e5cbbfd4b56e1f2d77cf31c42c529
manifest sha256:57de2e9db9536d6ec4e0977ba1850a2fb270e711ed7641b3dbf149366fe92503;
mc source-302242245a37975c6a8c1410ac3d6cb972d1d14b
manifest sha256:7b9fd93fe007f7b257ae7d437b119b87a989aa873a0501655d16796baafabe58.
Их Dockerfiles/locked vendor inputs те же; отличаются source metadata.
C0 проверяет package целиком перед public, не только финальный tag.
Partial receipt11106091457 из run36732619535 документирует первые packages.

#### Проверенные inputs и receipts

Оба полных binary hashes/sizes из таблицы C0 выше повторно подтверждены **до
исполнения**, minisign0.12 проверил оба minisig; tampered-byte negative отклонён.
Binary hashes внутри обоих образов совпали с теми же полными SHA-256.
MinIO source commit07c3a429bfed433e49018cb0f78a52145d4bedeb;
mc source commit383560b1c3d6912042e8c8c275bb78e83e67ef2b.
Ключ из official MinIO Dockerfile.release exact commit07c3…:
SHA-256 provenance-файла749dd8f1b5eaa04408999c3d0c2fa148b70de5b33239b604c4a9e9cd86f2cdee.
MinIO minisig SHA-256d71cf680e1de21ae4a71d8d6ff2c80d6f8b07cbe8a9e00e157ef40be213fd47f;
mc minisig SHA-25640f432ba89f9bca5c4bd5398a0669eb4d23eb142ff2c35c8b86ae894cbc95edb.
Все exact official URLs, sizes, SHA-256, source/licenses и tools зафиксированы в
infra/storage/inputs.lock.json, SHA-256
7d583ff59bda9f880f71522954e415bc9976979b03f458aca606d234774a1c51.

Base — official curlimages/curl8.19.0, linux/amd64
sha256:a2e4c1ef9b660f8ca90b2b725768e0ceade4fc1e52b5859a8d3e6c93db2dc47c;
index sha256:c03110c736db81bbe1be0296f1f1608c81b954b01626bdfb0a8f84e5bd00ff3c.
BuildKit0.25.0 pinned platform
sha256:939060f02be6f297aa8038d1ada85e8c7c031f4c364c6456bd9adf43a20f3b5e;
Buildx0.29.1 binary SHA-256
7d2d7d6d4680aa349614965aaa33ccec43f1a9a21e908a5ce4cb6adfa5ad5141.
Minisign0.12 archive SHA-256
9a599b48ba6eb7b1e80f12f36b94ceca7c00b7a5173c95c3efc88d9822957e73,
extracted executable SHA-256
2c74dffcc1c9a5ee55957c60971998ace2b89f22585631594ec2152c588af8db.
Actions также pinned полными commit SHA; остальные project dependencies не менялись.

| Artifact из final storage run | ID / размер | ZIP SHA-256 |
|---|---|---|
| storage-images-f74c240febd963c79408e80600c29d7739e08867-1 |11107176489 /96523927 bytes|9fcb573012a1907a70bcc3ad2b7b893677e6ddb49a977a6442f6336e94bac644|
| storage-publish-f74c240febd963c79408e80600c29d7739e08867-1 |11106623061 /3040 bytes|224a19ac249afe93515395c7c8c384ca62a8ff24cd61000e120470816d36cf41|

Первый ZIP содержит только minio.tar, mc.tar, inputs.lock.json, receipt.json.
Publisher скачал его по exact artifact ID, подтвердил download digest, verify-receipt
SHA/source SHA/lock/archive/config binding. C6 локально повторно проверил **полные
bytes второго ZIP**, оба JSON и их взаимную связь; первый большой ZIP повторно
локально не скачан. Retention7days, до2026-10-07; ссылки/логи не заменяют bytes.
receipt.json SHA-2568e315f18e4187f780e4c8125666f1775d13ea3dfac1892b972260b38ba2ffc39;
publish-receipt.json SHA-256e06e40fccdce27b6f30fe5c2f364791c34889868167a4b23d019c64c5c182650.

#### Реальное исполнение, assertions и исправленные дефекты нового workflow

На fresh ubuntu-24.04 runner выполнена прежняя команда:
`STORAGE_IMAGE=asm-minio:verified STORAGE_ADMIN_IMAGE=asm-mc:verified sh scripts/ci.sh`.
Использован штатный environment override Compose; сами script/Compose/lock не
изменены. **492 unit,390 real PostgreSQL/S3,111 frontend PASS**, canonical/contracts,
migration cycles/reproducibility/HTTP smoke PASS. После foundation и дополнительного
storage runtime probe `test -z "$(git status --porcelain --untracked-files=all)"` PASS.

- tests/test_m2_2_storage_postgres.py: original_roundtrip_validated_manifest_and_private_signed_http
  проверяет exact bytes/hash/MIME/dimensions через real signed GET и anonymous deny;
  live_owner_relation_workspace_role_and_failed_file_negatives проверяет exact
  relations/Workspace/live OWNER, PENDING/FAILED; revoke_denies_new_grant_existing_bearer_expires_at_real_s3
  проверяет revoke новой ссылки и реальное истечение прежней; checksum/conditional PUT
  и runtime privilege boundaries сохранены.
- tests/test_m2_2_db_postgres.py, test_m2_2_recovery_postgres.py,
  test_m2_2_media.py и test_m2_2_migrations.py исполнены прежним suite: atomic
  rollback/concurrent dedupe, invalid/truncated/animated/limits, retry/exhaustion,
  crashes/lost finalize ACK/stale claims, late PUT/repeated cleanup/winner safety,
  upgrade/downgrade/re-upgrade. Это проверка принятой реализации на новых образах.
- tests/test_m2_1_postgres.py и M2.3 real-wire/DB/API cases сохранены и исполнены
  прежним suite: SEND crash/UNKNOWN/no-resend, tenant isolation и live authority/
  product revocation. M1 regressions также включены; live Telegram не выполнялся.
- Дополнительный runtime probe: exact minio/mc versions и binary SHA, CA HTTPS,
  sh/cat/rm и tmp permissions; неизменный sh bootstrap; доступ внутри workspace prefix,
  отказ PUT вне prefix, HTTP403 anonymous GET; SIGTERM/exit0, одинаковые volume
  Mounts до/после restart, повтор bootstrap и сохранение exact bytes после restart.

Ранние красные runs выявили дефекты **нового** workflow, не старых tests:
runner-local env paths; недетерминированный EXPOSE history в BuildKit0.24.0
(перешли на pinned0.25.0 с upstream fix); пропущенный stdin -i у mc pipe.
Strict config/history/layer/byte assertions сохранены.
Пробный browser run36727812609 остановлен BROWSER_COMPOSE_PROJECT_INVALID:
script требует свой project и безусловно reload прежних Quay pins.
Защитный guard/script не менялся; полный browser остаётся обязательным после public
pull/pin switch. Packaging SUCCESS не означает browser PASS.

Первичный private push создал разрешённые package IDs, но новый publisher ошибочно
ожидал package.repository.id в GitHub API. Ответы не предоставляют repository
metadata даже при корректном OCI source label и успешном GITHUB_TOKEN push.
Это не установленный auth failure и не основание просить PAT/Connect repository.
Run36732619535 сохранил partial receipt и независимо подготовил оба packages.
Исправление на final SHA закрепило **наблюдённые immutable package IDs**15482993/
15484077: exact name/type/owner проверяются; если repository metadata присутствует,
ID обязан совпасть с1369650588. Missing/recreated package, иной owner/name/type,
source label mismatch, tag/config collision или visibility drift отказывают.
Только отдельный publish job получает contents:read/packages:write; verified
artifact binding сохранён, image code в publish не исполняется; token удаляется
logout/cleanup, не попадает в build/log/artifact. Все errors завершают job failure.

Обычный CI на том же source [36734280555](https://github.com/Elefesys/ai-service-manager/actions/runs/36734280555)
остаётся FAILURE: foundation109951736395 storage-test-init и browser109951736980
storage вернули unauthorized со старыми pins; оба source gates SKIPPED.
Actual checkout5d51adbcba492b0d07736cf646cca8fdb8682794 имеет ordered parents
96d9f09dd16d8b6ab019ac76a9c72ce910d81191 + f74c240febd963c79408e80600c29d7739e08867,
tree3e742d07440bcd2e4516922d5698ed1aee735db0, равен source tree.
Full final-head CI/browser/оба gates и fresh anonymous pull пока **не выполнены
успешно**. Это сохранённый registry gate, не снятый ради зелёного статуса.

#### Дельта и следующий шаг C0

Изменены семь из девяти разрешённых paths: два Dockerfile, inputs.lock.json,
storage-images.yml и три текущих документа. infra/images.lock.env и pin_images.sh
пока byte-identical; основной CI/Compose/bootstrap/app/migrations/tests/assertions
и прочие dependencies не менялись.

C0 проверяет оба packages/receipts/состав, затем организует владельцу действие
**Package settings → Change visibility → Public** для двух точных URLs выше.
Repository остаётся private; новых credentials/Connect repository не требуется.
После подтверждения C6 выполняет на fresh runner anonymous immutable pulls без
cache/auth, сверяет config/layers и in-image binary hashes, переключает только две
storage pins/refs и запускает оба прежних scripts/оба source gates на одном final
head. Команды и порядок — runbook§0.3. При изменении image bytes нужны новые build/
receipts/pins. Независимый scoped C8 организует C0; self-check C6 его не заменяет.
PR остаётся Draft/open, merge/VERIFIED не объявлены; M2 IN_PROGRESS, live A09/A11
BLOCKED, M3 не выдан. VM/DNS/TLS/Telegram secrets/live sends не выполнялись.

</details>

<details>
<summary>История — M2-ENV-01: диагноз C6 принят; прежний scope заменён M2-ENV-02 / 2026-09-30</summary>

Этот блок сохранён как evidence; его запреты на rebuild/publish и прежние поручения
не переопределяют активное решение C0 выше.

## Исторический handoff C0 → C6 — M2-ENV-01-REGISTRY / 2026-09-30

**M2.4 code/UI INTEGRATED / VERIFIED LOCAL/TEST; весь M2 IN_PROGRESS.**
Задача — восстановить доступность принятых storage images и штатный CI, не ожидая
доменов. Это устранение blocker родительской M2-LIVE-A09-A11. **Диагноз C6 готов для
C0 REVIEW; задача BLOCKED:** доступный same-content OCI source не подтверждён,
полный CI не восстановлен. Pins и implementation bytes не изменены; rebuild и
публикация новых images не выполнялись. M3/AI/новые функции не выданы.

### Repository, base, ветка и evidence старта

- Repository **Elefesys/ai-service-manager**; продолжать **c6/m2-live-smoke → main**,
  существующий [Draft PR #22](https://github.com/Elefesys/ai-service-manager/pull/22).
- Принятый implementation base / actual main:
  **96d9f09dd16d8b6ab019ac76a9c72ce910d81191**,
  tree **28de72ca6737cbe18bb4856a1636f70fae1131ee**.
  PR21 merged; ordered parents **ffc437f125aa6af4dcf1c61a035a0d5df517e062** +
  **770e7db905732b3ed2a25a1d9a2c31bcd89a161b**. Implementation bytes не менялись.
- [Отдельный push/main CI35706123814](https://github.com/Elefesys/ai-service-manager/actions/runs/35706123814)
  SUCCESS:492 unit,390 PostgreSQL/S3,111 frontend,27 browser; оба scripts/gates,
  canonical/migrations/contracts/reproducibility/smoke PASS. C0 прочитал оба actual
  main checkout logs; C8-M2.4-01/02/03 CLOSED сохраняются для прежних implementation bytes.
  Это историческая приёмка, не green CI текущего PR head. ZIP bytes не проверены.
- Сохранить первый coordination **914e2894f98330d62e1cc57ca5da5c62662d6960** и всю
  последующую историю. Непосредственный parent этого задания:
  **90fcdd968b00442d805839c8a205b673502fa122**,
  tree **59b95121b494e487fdb8d53087d7d26cb6927adf**.
  Exact стартовый coordination head указан в сообщении передачи C0 и PR receipt;
  начать от него, не откатываться на parent/старую ветку M2.2 и не force-push.
- [CI36308372607, attempts1/2](https://github.com/Elefesys/ai-service-manager/actions/runs/36308372607)
  FAILURE: `storage-test` (MinIO server) и `storage-init` (mc) получили `unauthorized`
  при pull из Quay. C0 прочитал logs attempts1/2; attempt2 jobs108589635786/108589635665.
  Checkout **ce62ff7eaf640d580cef44d53a8648255e9c9d28**, parents accepted main +
  parent задания; tree идентичен parent tree. Canonical/frontend111/Compose model
  прошли; PG/S3/browser и clean-source gates не завершены. Не заявлять их PASS.

### Читать перед работой

AGENTS; актуальный register и этот активный handoff; `docs/decisions/IMPL-001-stack.md`;
M2_CONTRACT §§9–11 и runbook M2_TELEGRAM_LOCAL_TEST §§0–1; `infra/images.lock.env`,
`scripts/pin_images.sh`, `compose.yaml`, `scripts/ci.sh`, `scripts/test_browser.sh`,
`.github/workflows/ci.yml`; применимые Spec/ADR private storage, immutable inputs и
LOCAL/TEST границы; Implementation Plan §§6–7. Исторические M1 задания не исполнять.

### Что установлено и что нужно диагностировать

Принятые release inputs в `scripts/pin_images.sh`:

- MinIO `RELEASE.2025-09-07T16-13-09Z`, pin
  `quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.
- mc `RELEASE.2025-02-15T10-36-16Z`, pin
  `quay.io/minio/mc@sha256:9ae9ed28d04f7c36ee6b84c36b2c0168f1be28350d54344c3e5088a631f4c603`.

Отказ доступа воспроизведён на двух CI attempts. Причина ответа registry не установлена:
не считать доказанными удаление образа, общий outage, необходимость логина или смены
версии. Сначала проверить исходные refs свежим anonymous pull/manifest inspection на
чистом runner с обычным разрешённым сетевым доступом. Network/auth ограничения не обходить.
Различать отсутствие объекта, отказ registry/token service, network failure и cache.
Не ждать домена, bot token, cloud account или пользовательского Docker для этого шага.

### Результат диагностики C6 / 2026-09-30 UTC

Старт сохранён: head **0b417f581831bcd0c3c938b447f1e05510077ec6**, tree
**9cc294ee718f4e1c89ebbd6c2ae2f18e2a4eb0c7**. История от первого coordination не
переписывалась. В [CI36715183155 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36715183155/attempts/1)
browser109886245494 и foundation109886245605 отказали на pull. C6 запросил обычный
rerun failed jobs: [attempt2](https://github.com/Elefesys/ai-service-manager/actions/runs/36715183155/attempts/2),
browser109889123888 и foundation109889127360, новые GitHub-hosted ubuntu-24.04
linux/amd64 runners, runner image20260920.314.1. Workflow не содержит Docker cache
restore или registry login. В обоих checkout logs исполнен virtual merge
**60073eaf5738f1f29c6ffb98e6db796d3098f28f**, ordered parents accepted main + стартовый
head, tree идентичен стартовому. В12:39UTC mc pull снова получил `unauthorized`;
предыдущий attempt также показывал отказ server pull. Успешного полного pull нет.

`sh scripts/ci.sh` и `sh scripts/test_browser.sh` действительно запущены штатным
workflow и завершились FAILURE при provisioning storage. Canonical import,
frontend111 и Compose model checks прошли; PostgreSQL/S3/private-file/изоляция/
UNKNOWN-no-resend и browser cases в этих attempts не исполнились. Оба штатных
clean-source steps **SKIPPED** после failure, не PASS. Исторический main SUCCESS выше
не подменяет текущий результат. Final documentation head/tree, actual checkout,
ordered parents, tree comparison и CI приведены в PR receipt без SHA-only commit.

Дополнительно из среды C6 выполнены обычные HTTPS GET, без credentials и обходов.
Они не выдаются за runner pull. Для каждого exact digest использован registry v2
manifest GET с Docker/OCI Accept, затем стандартный anonymous Bearer token exchange
по `WWW-Authenticate` и повтор GET. Tokens оставались в памяти, не логировались.

| Endpoint / оба сохранённых digest | Наблюдаемый ответ |
|---|---|
| quay.io/v2/minio/{minio,mc}/manifests/sha256:… | Initial401; anonymous token200, granted actions пусты; повтор manifest401 UNAUTHORIZED |
| registry-1.docker.io/v2/minio/{minio,mc}/manifests/sha256:… | Initial401; anonymous token200 без pull grant; повтор401 authentication required |
| hub.docker.com/v2/repositories/minio/{minio,mc}/ и exact release tags |404 object not found |
| mirror.gcr.io/v2/minio/{minio,mc}/manifests/sha256:… |404 MANIFEST_UNKNOWN |
| dl.min.io/{server/minio,client/mc}/release/linux-amd64/archive/{binary}.{accepted-release}.sha256sum |410 Gone; upstream сообщает об архивировании community проектов и прекращении раздачи этих файлов |

Initial401 сам по себе — штатный auth challenge. Подтверждённый технический blocker:
после anonymous exchange registry не предоставляет pull authority для обоих
repository names. По этим ответам нельзя отличить private/deleted/disabled repo,
доказать общий outage либо обещать исправление через credentials. Сообщение410
от download site — отдельное upstream evidence, не доказанная причина Quay policy.
Публичный Google cache не дал manifests; его содержимое также не имеет гарантии
удержания ([Google documentation](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images)).
Недоступность всех возможных mirrors не утверждается; допустимый доступный источник
с проверяемой идентичностью linux/amd64 index/manifest/config/layers не найден.

Provenance исходных refs подтверждён publisher scripts в принятых release tags:
[MinIO docker-buildx.sh](https://github.com/minio/minio/blob/RELEASE.2025-09-07T16-13-09Z/docker-buildx.sh)
и [mc docker-buildx.sh](https://github.com/minio/mc/blob/RELEASE.2025-02-15T10-36-16Z/docker-buildx.sh)
публикуют соответствующие artifacts в Docker Hub и Quay. Из-за отказа доступа
исходные OCI manifests/config/layers заново не прочитаны; новые pins не придуманы.
Совпадение release tag или binary digest с OCI digest не заявляется.

### Конкретное предложение C0 — ещё не разрешённый rebuild

Официальные GitHub Releases сохраняют **оба принятых linux/amd64 binary**. C6
полностью скачал их обычным HTTPS GET (200), посчитал SHA-256 по bytes и сравнил
с `digest` официального release-asset API; binaries не запускались и не публиковались.

| Official release asset | Размер, bytes | Проверенный binary SHA-256 |
|---|---|---|
| [minio.linux-amd64.RELEASE.2025-09-07T16-13-09Z](https://github.com/minio/minio/releases/download/RELEASE.2025-09-07T16-13-09Z/minio.linux-amd64.RELEASE.2025-09-07T16-13-09Z) |110989496|7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f|
| [mc.linux-amd64.RELEASE.2025-02-15T10-36-16Z](https://github.com/minio/mc/releases/download/RELEASE.2025-02-15T10-36-16Z/mc.linux-amd64.RELEASE.2025-02-15T10-36-16Z) |29208728|7a03ba39e158708a9e88f1bf5c346c6651b15c784e4b2c7150b5b5f282f43c28|

Это **binary SHA-256, не OCI pins и не доказательство прежних runtime bytes**.
Release API также перечисляет minisig/checksum assets; подписи в этой диагностике
не проверялись. Существующие upstream Dockerfile.release зависят от недоступных
download endpoints и mutable base inputs, поэтому простая повторная сборка не
воспроизводит принятые OCI artifacts.

Минимальное предлагаемое отдельное поручение: упаковать эти два exact binary в
project-owned linux/amd64 images с digest-pinned base/дополнительными tools, проверкой
hash/signature и сохранением нужных Compose entrypoint/healthcheck/shell semantics.
Предлагаемые новые paths: `infra/storage/Minio.Dockerfile`,
`infra/storage/Mc.Dockerfile`, `infra/storage/inputs.lock.json` и отдельный
`.github/workflows/storage-images.yml` для ограниченного build/provenance/publish.
После разрешённой публикации в публичные GHCR packages проекта — заменить только
две исходные ссылки и два pins в уже разрешённых файлах; прежний основной workflow,
Compose и assertions сохранять. GITHUB_TOKEN с job-scoped packages:write, доступность
public packages и отсутствие оплаты требуют решения/проверки C0; credential не
создавался. Scope включает новые OCI bytes и независимый C8, затем uncached pull и
полный штатный CI на одном head. Новые base digests ещё не выбраны/приняты.

Это предложение упаковки, а не компиляции нового MinIO release, смены версии или
подмены S3 тестов. Пока C0 не расширит scope из пяти paths, выполнять его нельзя.
Если C0 располагает официальным доступным архивом точных OCI objects, сначала
проверить их index→linux/amd64 manifest→config/layers hashes: такой перенос может
обойтись исходным scope без rebuild. Новые credentials не считать решением без
подтверждения upstream. До решения C0 pins остаются прежними, PR Draft, merge запрещён.

Для повторного uncached pull на disposable linux/amd64 runner (без Docker config
с credentials; команды не удаляют чужой локальный cache):

```sh
set -eu
. infra/images.lock.env
for ref in "$STORAGE_IMAGE" "$STORAGE_ADMIN_IMAGE"; do
  if docker image inspect "$ref" >/dev/null 2>&1; then
    echo 'Use a fresh disposable runner: image is already cached' >&2
    exit 1
  fi
done
docker pull --platform linux/amd64 "$STORAGE_IMAGE"
docker pull --platform linux/amd64 "$STORAGE_ADMIN_IMAGE"
docker buildx imagetools inspect "$STORAGE_IMAGE"
docker buildx imagetools inspect "$STORAGE_ADMIN_IMAGE"
sh scripts/ci.sh
test -z "$(git status --porcelain --untracked-files=all)"
sh scripts/test_browser.sh
test -z "$(git status --porcelain --untracked-files=all)"
```

Это диагностические команды для чистого runner, не изменение штатных scripts.
Фактический attempt2 запускал прежний workflow с двумя указанными scripts;
отдельные inspect команды выше ещё не исполнялись на runner. HTTP probes выполняли
`GET /v2/<repo>/manifests/<exact digest>` и anonymous token exchange, а не `--version`.
Полный recovery DoD ниже остаётся невыполненным; оба clean-source gates нужно
подтвердить после реального восстановления storage, без skip/xfail/ослаблений.

### Точный разрешённый scope C0

Этот блок **явно заменяет прежний полный запрет изменения storage pins** только для
данного blocker. Продуктовые контракты, версии и остальная инфраструктура сохраняются.

1. `infra/images.lock.env` — только **STORAGE_IMAGE** и **STORAGE_ADMIN_IMAGE**.
2. `scripts/pin_images.sh` — только две соответствующие исходные ссылки; сохранить
   exact release versions, immutable resolution и правило не обновлять уже принятые pins.
   Не запускать массовое обновление пяти остальных pins.
3. `docs/TASK_REGISTER.md`, `docs/tasks/M2_HANDOFF.md`,
   `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` — диагноз, provenance, точные команды,
   результат и границы evidence, одно согласованное итоговое обновление.

Если нужен перенос источника: допускается официальный публичный registry/mirror с
доказанным происхождением **тех же release artifacts**. Сохранять `@sha256`; проверить
index/platform manifest, config и layer identities для принятого linux/amd64.
Одинаковый tag/вывод `--version` сам по себе не доказывает одинаковые bytes. Разницу
между index digest и platform manifest не выдавать за изменение runtime. Для иной
платформы не заявлять проверку без исполнения. Не использовать случайные community
rebuilds, непроверенный proxy/cache или pin от другого release.

Если исходный доступ восстановился и свежий полный CI проходит без изменения images,
зафиксировать no-change recovery; не создавать fix ради коммита и не выдумывать причину.
Если тех же artifacts нет либо нужны rebuild/version change/new registry credentials,
вернуть C0 конкретный диагноз и минимальную proposed delta с источниками. Такой выбор
не делегирован автоматически, но не блокирует остальные доступные read-only проверки.

Не менять backend/frontend/API/DTO/generated contracts, auth/CORS/RLS, private ACL,
S3 bootstrap policy, applied0001–0007, остальные dependencies/pins, Compose/workflows,
`scripts/ci.sh`, `scripts/test_browser.sh` и существующие tests/assertions. Не добавлять
skip/xfail, `latest`, `continue-on-error`, registry login или более широкие credentials.
Обоснованный обнаруженный blocker вне этих пяти paths сначала вернуть C0.

### Конечные критерии результата

- Диагноз опирается на точные refs, команды и sanitized registry/runner evidence;
  различает observed error и подтверждённую причину. Secrets/auth tokens не логировать.
- Оба final immutable refs реально скачаны на чистом linux/amd64 runner без заранее
  загруженного локального image. Проверены digest/provenance и MinIO/mc versions.
  Обычный pull, использовавший локальный image cache, недостаточен для recovery evidence.
- На одном final head полностью прошли **sh scripts/ci.sh** и
  **sh scripts/test_browser.sh**, оба clean-source gates, migrations/contracts/
  reproducibility/smoke. PG/S3 действительно исполняются; private access, signed GET,
  CORS/isolation, interrupted upload/recovery, SEND UNKNOWN/no-resend и M1 regression
  сохраняются. Количество cases — справка, не замена assertions/evidence.
- Final-head SHA, tree, actually checked-out virtual merge, ordered parents и tree
  comparison подтверждены logs/Git objects. Если ZIP bytes недоступны, это указать.
- Единственный register/активный handoff/runbook обновлены согласованно. Не делать
  коммит только ради записи предыдущего documentation SHA; refs/CI — в PR receipt.
- Вернуть C0 REVIEW, список paths/delta, причину выбранного fix/no-change, exact refs,
  команды/CI/results и ограничения. Не merge и не объявлять M2/A09/A11 VERIFIED.

Если изменены источники/pins, C0 организует **реальный scoped C8** по provenance,
воспроизводимости и сохранности private-storage checks перед приёмкой. Это новая
граница review; прежний C8 PASS не покрывает новые image bytes автоматически.
Для подтверждённого no-change recovery отдельный повтор C8 без нового риска не нужен.

### Зафиксированное решение о доменах и следующий шаг после приёмки

Владелец 2026-09-30 согласовал **smoke на .com после подтверждения работоспособности**:
`console.telegram-test.clientmanagerai.com` + `files.telegram-test.clientmanagerai.com`.
Это явное изменение прежних .ru smoke endpoints, с одним Console/API/webhook origin
и отдельным private-files hostname. Вторую Console/region/shared-cookie domain или
CORS wildcard не создавать; .ru остаётся будущим основным доменом по предпочтению
владельца. Автоматическая смена .com → .ru в эту задачу не входит.

По сообщению владельца/ответу поддержки: .com зарегистрирован, NS Timeweb прописаны;
.ru ждёт проверки администратора. Публичные DNS/HTTPS C0 не проверены. Не копировать
личные данные из обращения, не повторять регистрацию и не просить TG secrets.
Бюджет принят; в **M2-ENV-01** не создавать платный runtime, не менять DNS/TLS/webhook
и не отправлять Telegram. После C0 приёмки CI выдаётся следующий шаг существующей
M2-LIVE-A09-A11: host/preflight → проверенные .com DNS/TLS → реальный Client text+photo
→ правильный Workspace/Owner Console/private image → manual reply → Client receipt.
CONTROLLED/202/SENT не заменяют live evidence; A09/A11 остаются BLOCKED, M3 не выдан.


</details>

<details>
<summary>История: приёмка M2.4 до merge — не текущие инструкции</summary>

## История — pre-merge handoff C0 → пользователь — M2.4-CONSOLE к merge / 2026-09-22

**C0 и независимый scoped C8 приняли исправленный code/UI LOCAL/TEST.**
M2.4-CONSOLE/M2.4 пока REVIEW: merge ещё не выполнен, отдельный main CI не проверен.
Весь M2 IN_PROGRESS; внешний live A09/A11 BLOCKED runtime/DNS/TLS. M3 не выдан.
Старые задания ниже — история, их не выполнять повторно.

### Единственное следующее действие и точный source

[PR #21](https://github.com/Elefesys/ai-service-manager/pull/21), **c5/m2-4-console** → main.
После полного SUCCESS итогового head и снятия Draft пользователь выбирает **Create a
merge commit → Confirm merge**. Не squash/rebase: первый coordination и review history
сохраняются. Вернуть C0 «слито» или ссылку на merge commit. C0 самостоятельно не сливает.

| Ref | Exact SHA |
|---|---|
| Accepted main / implementation base | ffc437f125aa6af4dcf1c61a035a0d5df517e062 |
| Первый сохранённый coordination | 76d44a7e0559f470b3de07c97a4b61581e7e00a8 |
| Проверенный C5 REVIEW head / parent исправления | 1323648d4cd889bc35dcfcf9291fb918412c8d86 |
| Исправленный implementation head | 842b9ee3300fcea06fbb1394c13a01faae21493b |
| Implementation tree | f1dd4f5c9442febd192f3a81061634117aa3d7fe |
| Tested virtual merge | 17713ebd43c69273f12ee2961fed8c1d8dd79c6b |

Ordered tested parents: accepted base + исправленный implementation; tree совпадает.
[CI35703839157, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/35703839157):
**SUCCESS:492 unit,390 PostgreSQL/S3,111 frontend,27 browser; оба штатных scripts и clean-source gates, canonical/migrations/contracts/reproducibility/smoke PASS**. Оба jobs должны checkout ровно tested merge выше; реальные
PG/S3/browser results получены GitHub runner, локального Docker нет.

Этот финальный acceptance update меняет только register/handoff/contract.
Его собственный head/tree/tested merge, CI/jobs/source gates после последней дельты
находятся **в верхнем PR receipt**. Перед Ready/merge C0 обязан проверить их повторно.
Не создавать дополнительный документационный commit ради SHA этого документа.
C0 сверил213 исходных blobs/modes C5 head и frozen области; ZIP bytes не проверены.

### Независимый review и разрешённая коррекция

C8 реально выполнен тремя отдельными read-only reviewers: recovery/Console isolation;
strict consumer/private-image/privacy diagnostics; finite TEST harness/execution evidence.
Harness и основной consumer получили PASS. Три P2 findings воспроизведены, исправлены
C0 в том же PR и закрыты отдельным targeted C8:

| Finding | Причина и минимальное исправление | Regression / evidence |
|---|---|---|
| C8-M2.4-01 CLOSED | Старый pagination GET поглощал fresh GET после202 и освобождал composer. History и send сериализованы; только read с уже confirmed intent закрывает recovery | Component `blocks pagination during POST…`; real pagination journey задерживает настоящий committed202, pagination disabled, затем fresh first-page GET и PENDING; один command |
| C8-M2.4-02 CLOSED | Billing403 скрывал только Billing, сохраняя Messaging private view. Общий context-scoped denial скрывает обе owner-панели, компоненты остаются mounted | Оба направления denial, pending body/key, late202 и явное session recovery в component; real OWNER downgrade обнаружен Billing и скрывает Audit/contact/history/image, raw grant/history/send403 сохранены |
| C8-M2.4-03 CLOSED | Playwright visibility failure включал private img.src в preview/call log. Boolean/number probes под bounded safeDiagnostic | Visibility и naturalWidth23, no-cookie/auth/CSRF/referrer, unsigned403 сохранены;6 diagnostic cases и7 независимых installed Playwright/Node/JSDOM probes без URL/signature в error/stack |

C8 recovery независимо исполнил11 targeted component checks; checked component diff
SHA-256 **cc3ef1d78904c0e7373f755e71294b5461feea625e783b050f5254912e2c1a8c**,
C0 привязал идентичные bytes к implementation head выше. Privacy re-review проверил
именно исправленные helpers, не Chromium failure run. Полный CI — отдельное evidence.

C0 разрешил **frontend/src/BillingPanel.tsx** только как интеграционный callback общей
live OWNER authority. Итого24 changed paths; остальные23 — прежний разрешённый scope.
Runtime backend/API/migrations0001–0007/grants/OpenAPI/R4/auth/tenancy/base Compose/
workflows/dependencies/image pins/канон не менялись. Исходные15 M1 browser journeys
сохранены. Browser pagination дополнен намеренной записью только после assertions
нулевых POST при чтении; denial journey меняет источник обнаружения на Billing,
не убирая grant/history/send403. Это проверки принятого поведения, не ослабление gates.

### Приёмка по прежней матрице A01–A12

| Критерии | Принятое evidence и граница |
|---|---|
| A01/A02/A04/A06/A09 | Принятые M2.1–M2.3 transport/DB/HTTP/lease/receipt тесты сохранены,390 PG/S3 regression; это не внешний Telegram smoke |
| A03/A05/A10 | Реальная потеря committed202 → auth/CSRF → exact replay с одним набором Message/receipt/Audit/Outbox/Job; valid202+GET failure только читает; UNKNOWN после замены runner сохраняет CALL1/EFFECT1 без resend |
| A06/A07/A10 | Inbound text и private image через реальный Worker/FetchTransfer/MinIO, naturalWidth23 и header/unsigned403 guards; manual text exact → PENDING → Worker → SENT; SENT не доставка клиенту |
| A08/A10 | Foreign Workspace403/mismatched refs404, live OWNER downgrade и общий denial, late history/grant/401/403 guards, скрытие private views; исходные scopes/keys не переносятся |
| A09/A10 | Реальные product restrictions409, editable draft, доступная история; connection/file/delivery states и оба503; observation не authority |
| A10/A12 | Limit25/cursor/null, replacement проекций, refresh/reload без writes, устранённая pagination/202 гонка; Unicode/plain text, keyboard/narrow и27 browser запусков с прежними15 M1 |
| A11 | **BLOCKED внешней инфраструктурой**. CONTROLLED browser не закрывает Client text+photo → Console → manual reply → настоящий Client receipt |
| A12 | Полные scripts/clean-source/migration/contracts/reproducibility/smoke на implementation и итоговом head; отдельный actual main CI проверяется только после пользовательского merge |

### Конечный остаток M2

1. Пользовательский обычный merge PR21 после final-head SUCCESS.
2. C0 проверяет actual merge parents/tree и отдельный push/main CI; фиксирует только
   M2.4-CONSOLE code/UI LOCAL/TEST, без объявления всего M2 VERIFIED.
3. Единственный внешний шаг — разрешённый live A09/A11 по готовому
   [runbook](../runbooks/M2_TELEGRAM_LOCAL_TEST.md), включая §5.1 Console journey.
   Bot/Owner/Client готовы, TG_BOT_TOKEN/TG_WEBHOOK_SECRET уже в password manager.
   Нужны доступный Linux/Docker host, два DNS имени и TLS; секреты вводятся оператором
   напрямую в private .env.telegram/secret store, не в чат/PR. C0/C6 ведут runtime setup;
   платные ресурсы только после отдельного предложения точной стоимости.
4. После фактического Client receipt, сохранения изоляции/rights, полного evidence
   A01–A12 и успешного main CI C0 может завершить M2. M3 автоматически не выдаётся.

Новых функций/миграций и повторной реализации M1–M2.3 в этом handoff нет.

</details>

<details>
<summary>История: передача C5 в REVIEW — не текущие инструкции</summary>

## История — передача C5 → C0 — M2.4-CONSOLE REVIEW / 2026-09-22

**M2.4-CONSOLE и M2.4 REVIEW. PR #21 остаётся Draft/open/not merged.**
M1 и принятые M2.1–M2.3 LOCAL/TEST receipts сохраняются. Весь M2 IN_PROGRESS;
live A09/A11 BLOCKED только внешними runtime/DNS/TLS. C5 не объявляет UI или M2 VERIFIED.
Следующее действие — приёмка C0 и независимый scoped C8 нового UI/recovery/private-image
среза; прежний C8 M2.3 его не заменяет. Затем user merge и отдельный actual main CI.

### Exact source и выполненные проверки

Repository **Elefesys/ai-service-manager**, тот же
[Draft PR #21](https://github.com/Elefesys/ai-service-manager/pull/21), ветка
**c5/m2-4-console** → main. Accepted base **ffc437f125aa6af4dcf1c61a035a0d5df517e062**.
Первый coordination **76d44a7e0559f470b3de07c97a4b61581e7e00a8** сохранён;
его parent — accepted base, tree **f416c7f8a3230d7b4bb5b8edfa9ec53cc6ff8139**.

Implementation **cd2cce43acf2556d49e865e198a717acdc67dc96**, parent — coordination,
tree **de2b4b708791f3c55f815d947b00fa13e4888a64**. Реальный
[CI 35694903440, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/35694903440)
**SUCCESS**: foundation106639523049 и browser106639523244. Оба checkout logs указывают
**05344240fffd5d67340db1db292fd3fb00fb3f29**; ordered parents accepted base + implementation,
tree совпадает с implementation tree. **492 unit,390 PostgreSQL/S3,107 frontend,27 browser PASS**.
Оба штатных scripts/clean-source gates, canonical imports, migrations, contracts,
reproducibility и HTTP/frontend smoke PASS. Это фактический implementation receipt.

Текущее изменение согласует register/handoff/contract одним REVIEW update.
Его собственные final head/parent/tree, tested SHA/parents/tree и **повторный полный CI
после последней дельты** находятся в итоговом PR receipt; SHA-only follow-up не нужен.
Локально сверены все204 исходных blob/modes с coordination tree; Docker отсутствует,
реальные PostgreSQL/S3/browser результаты получены GitHub runner. Локальные unit,
frontend/typecheck/build, Ruff/mypy PASS. Локальные синтетические Git parents не
выдаются за remote ancestry. Проверка байтов artifact ZIP не заявляется.

### Что реализовано и что сохранено

Один page-lifetime MessagingPanel рядом с прежним BillingPanel. OWNER gate —
membership.role без изменения frozen permissions. Connections/диалоги/история
используют strict consumer принятого OpenAPI, fixed limit25 и opaque cursor;
refresh сбрасывает страницы, новые проекции заменяют старые delivery/file fields.
Exact text без trim/NFC/UTF16 maxLength; plain text rendering и keyboard/narrow UI.

Actor/Workspace/conversation/body/key заморожены в одном memory-only intent.
Неоднозначный POST допускает только явный исходный replay после session/CSRF recovery.
Valid202 сохраняет receipt; последующая ошибка GET не создаёт новый POST.
UNKNOWN terminal/no-resend; SENT означает принятие каналом. Hard reload только читает.
Generation/selection/sequence guards проверяются до success/error/401/403 handling;
старые ответы не меняют новый контекст/сессию. После denial защищённые данные скрыты.

Private image открывается отдельным current-owner grant. Исходный signed URL не
переписывается, не логируется и не сохраняется; img использует anonymous CORS и
no-referrer. Context/denial/expiry удаляют удерживаемый URL, новый grant только явно.
TEST MinIO private/tmpfs; exact Console CORS origin, loopback signer и internal
runtime origin. Backend API/0001–0007/grants/R4/tenancy/OpenAPI/base Compose/workflows/
locks/pins/canonical sources не изменены. Новых endpoints/dependencies нет.

C3 реально реализовал isolated TEST provisioning/counters и runtime runner;
C6 — TEST Compose/guards/runbook. Их отдельные checkout patches интегрированы
последовательно в этом PR. Это соавторы, не независимый C8. Finite migrator actions
не записывают canonical Message/File READY/receipt/Audit/Outbox/Job ради PASS.
Runtime имеет только asm_runtime/S3 и использует прежние ingest/Worker/FetchTransfer;
93 входящих события прошли настоящий kernel, private изображения — MinIO.

### Assertions → существующие M2-A01…A12

| Критерии | Фактическая проверка и граница |
|---|---|
| A01/A02/A04/A06/A09 | Прежние390 PostgreSQL/S3 и принятые transport/HTTP/lease/receipt tests сохранены; webhook/Telegram runtime не менялся. CONTROLLED browser не подменяет live rights |
| A03/A10 | messaging.spec: route.fetch выполняет настоящий POST/commit202, браузер теряет ответ; затем401/login, настоящий rotate→CSRF403→session recovery и exact replay202. Body/key и исходные receipt/message/accepted_at совпадают; Message/receipt/Audit/Outbox/Job каждый +1 |
| A05/A10 | UNKNOWN через настоящий Worker/CONTROLLED с CALL=1/EFFECT=1; новый runner recover, same-key receipt и reload сохраняют UNKNOWN и counters. Resend отсутствует. Отдельный valid202+GET failure: всего1 POST, далее только чтения |
| A06/A07/A10 | Реальные inbound text, PENDING/FAILED/READY file, private grant→MinIO image naturalWidth23; browser image без Cookie/Authorization/CSRF/Referer, unsigned object GET403. Manual text exact→PENDING→Worker→SENT, без обещания Client receipt |
| A08/A10 | Authenticated foreign Workspace GET/send/grant403, mismatched refs404, OWNER downgrade запрещает новый grant/history/send без DB delta; прежний grant имеет TTL boundary. Real delayed GET/grant не возвращают данные после Workspace switch; component late401/403 не меняют новую сессию |
| A09/A10 | Connection INACTIVE и SUSPENDED product restriction дают real409 NOT_ALLOWED, editable draft и доступные history/private image; permanent worker refusal→FAILED. Component coverage всех5 connection,3 file,5 delivery states и двух503; observation не authority |
| A10 | Более25 connections/conversations/history, exact opaque cursor/null, ID dedupe и replacement projection, fresh refresh/reload без POST. Component scalar/UTF8/NUL/surrogate/Python-whitespace, strict DTO/enums/relations/IDs/timestamps/decimal strings, safe rendering, double submit, grant expiry/URL scheme |
| A10/A12 | 27 browser:15 прежних auth/Business/Billing/Audit/Ops +12 новых messaging запусков, включая Chromium narrow/keyboard. Положительный CORS POST202 и negative preflight400 без второго command; source gates PASS |
| A11 | BLOCKED live: runtime/DNS/TLS отсутствуют. Existing runbook расширен Client text+photo→Owner Console/private image→manual reply→Client receipt. Ни CONTROLLED, ни SENT не закрывают A11 |
| A12 | sh scripts/ci.sh + sh scripts/test_browser.sh PASS на implementation и обязательный повтор на final head в PR receipt; actual main CI остаётся действием C0 после merge |

### Старые fixtures/tests и конкретные ограничения

Все прежние assertions сохранены. App.test дополнительно изолирует MessagingPanel,
чтобы сохранить точные M1.2 auth request counts; полноценный Console login/focus/recovery/
reload/Ops проверяется новым MessagingPanel.test. Старые auth.spec/billing.spec и
BillingPanel/c0-review tests не менялись. provision_browser_test только добавляет
fresh messaging identities/Workspaces/test_messaging; прежние billing presets не repin.
Compose model fixture расширен storage/runtime полями, старые14 guard cases сохранены;
добавлены35 отрицательных/positive guard cases. Diagnostic tests расширены redact
message/key/signed URL; unsafe causes не печатаются. Локальные первоначальные ошибки
были TypeScript test option `exact` и форматирование двух новых guard edits: исправлены
тестовый вызов/format, без удаления проверки поведения. Первый published CI зелёный.

Вне разрешённых paths implementation blockers не обнаружены; backend-дельта не нужна.
Live blocker: доступный Linux/Docker host, два DNS имени и TLS. Bot/accounts/secrets
у пользователя готовы; секреты не запрашивались, внешних Telegram sends/расходов нет.
Оператор выполняет live runbook только после отдельной авторизации. Это не стопор
независимой UI реализации и не основание снимать Draft/объявлять M2 VERIFIED.

</details>

<details>
<summary>История: исходное поручение C0 → C5 — не текущая задача</summary>

## История — старт C0 → C5 M2.4-CONSOLE / 2026-09-21

**M1.1–M1.3, M2.1/M2.2 VERIFIED LOCAL/TEST. M2.3 code/API интегрирован и
VERIFIED в LOCAL/TEST после PR #20 и отдельного push/main CI. Live Telegram
A09/A11 BLOCKED: внешнее runtime/DNS/TLS. M2.4 IN_PROGRESS — выдача единственной
задачи C5, UI ещё не реализован; весь M2 IN_PROGRESS. M3 не выдан.**

Это единственное текущее поручение. История ниже не отменяет его. Repository:
**Elefesys/ai-service-manager**; ветка **c5/m2-4-console** → main. Продолжить один
подготовленный C0 Draft PR этой ветки; номер, стартовые head/tree/tested SHA и CI
указаны в PR receipt/готовом сообщении C0. **Первый coordination commit сохранить.**
Никакого отдельного docs merge и параллельного implementation PR не требуется.

### Принятый base и завершённая интеграция M2.3

Implementation base / actual main **`ffc437f125aa6af4dcf1c61a035a0d5df517e062`**;
tree **`0ed75735d6c9d9b7d35fac13dbfb6cc3b6ede814`**. Actual merge PR #20 имеет parents
`a321bdd58856fb41bccb5749b4212349832e623c` +
`2aece2df399a722ba6d978977527c3b92eb0adf6`, tree совпадает с принятым final tree.
[Push/main CI 35649907678](https://github.com/Elefesys/ai-service-manager/actions/runs/35649907678)
**SUCCESS**, attempt1: оба checkout logs указывают именно actual merge SHA;
421 unit,390 real PostgreSQL/S3,60 frontend,15 прежних browser PASS, оба source gates
и штатные scripts/canonical/migrations/contracts/reproducibility/smoke PASS.

Независимый scoped C8 M2.3 выполнен реально: transport/webhook/media/setup PASS;
DB/API обнаружили C8-M2.3-01, ограниченное исправление C2 прошло независимый targeted
PASS/CLOSED и полный CI. Итоговый PR CI35648702138 SUCCESS. Code/API принято;
этот receipt не является C8 review будущего UI или live Telegram evidence.
Локального Docker нет, PostgreSQL/S3/browser execution подтверждён GitHub runner.
Git objects/checkout logs проверены; загрузка ZIP C0 ранее получила403, новая
локальная проверка байтов ZIP не заявляется.

C1 выполнил read-only проверку consumer-контракта по реальным HTTP/models/service,
§10, App/BillingPanel: **CONTRACT PASS**. Уточнения по Owner role,202/recovery,
connection observations, Unicode и private grants включены в §11. Backend-дельта
не требуется. Это предметное согласование, не review ещё отсутствующей реализации.

### Задача и обязательное чтение

**ID M2.4-CONSOLE. Ведущий C5**, C3 участвует только в TEST event/worker harness,
C6 — browser Compose/runbook, C1 — совместимость принятого API; авторы сериализуют
общие edits в том же PR. C2 нужен только при выявленном конкретном DB-дефекте:
миграций в этом задании нет, применённые0001–0007 неизменны. C0 принимает scope;
независимый C8 назначается после implementation, не подменяется предметной консультацией.

Сначала проверить refs/ancestry и прочитать AGENTS, этот активный блок, TASK_REGISTER,
[M2_CONTRACT §§10–11](M2_CONTRACT.md), contracts/openapi.json и contracts/README.md,
App.tsx, BillingPanel.tsx, api.ts, billing-api.ts, существующие browser tests/fixture/
Compose guards, messaging/http.py/http_models.py и tests/test_m2_3_* как accepted evidence.
Применимы Spec §§4,17.5,18,19,24.6, ADR-019–021/115/121–128/138–140,
MVP Console (только функции M2), Roadmap M2, Implementation Plan M2.4 и общая DoD.
Канон приложений импортирован в docs/architecture; не заменять его пересказом.

Результат: одна панель переписки существующей Console. Owner видит список connections/
диалогов, историю текста/изображения, пишет manual text и различает queued/sending/
accepted-by-channel/failed/unknown. Обновление вручную и load-more достаточны.
Private image выдаётся через current-owner read-grant; HTTP recovery сохраняет
прежние actor/Workspace/conversation/text/key. Все подробные решения — §11 контракта.
Сохранить предыдущие auth/Business/Billing/Audit/Ops mechanisms. Не добавлять AI,
takeover/resume, цены, запись, платежи, outbound media, edit/delete, новые API или Ops.

### Разрешённые пути и точный смысл дельты

| Paths | Разрешение C0 |
|---|---|
| frontend/src/messaging-api.ts; messaging-api.test.ts; MessagingPanel.tsx; MessagingPanel.test.tsx; messaging-fixtures.test-helper.ts | Новый узкий typed consumer, одна панель, component/parser fixtures/tests по §11 |
| frontend/src/App.tsx; App.test.tsx; style.css | Additive mounting/page-lifetime context wiring и responsive styling; auth/recovery/Ops semantics сохраняются |
| frontend/e2e/messaging.spec.ts | Новые реальные browser journeys через API/PG/S3 и явно CONTROLLED worker |
| frontend/e2e/safe-diagnostic.ts; frontend/src/safe-diagnostic.test.ts | Только finite messaging diagnostic codes/проверка redaction; не печатать body/URL/secret |
| frontend/e2e/auth.spec.ts; frontend/e2e/billing.spec.ts | Только если новый panel делает старые selectors неоднозначными: scoped selectors с сохранением действий и assertions; объяснить каждую дельту |
| scripts/m2_4_browser_fixture.py; scripts/m2_4_browser_worker.py; tests/test_m2_4_browser_fixture.py | Finite TEST seed/counters/state changes отдельно от runtime ingest/Worker/FetchTransfer; guards и private diagnostics |
| scripts/provision_browser_test.py | Additive fresh messaging fixtures/результат; существующие M1 billing presets сохраняются |
| compose.browser.yaml; scripts/test_browser.sh | Только private TEST MinIO/browser origin, browser-profile runtime runner и штатный запуск новых fixtures/journeys/cleanup (§11.6) |
| scripts/check_browser_compose.py; tests/test_browser_compose.py | Сохранить прежние guards, проверить новые runtime/storage TEST ограничения; не удалять проверки |
| docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md | Добавить executable/manual Console live journey к существующему setup; честно отделить внешний blocker |
| docs/TASK_REGISTER.md; docs/tasks/M2_HANDOFF.md; docs/tasks/M2_CONTRACT.md | Одно согласованное обновление результатов/уточнений; один active handoff, история сохранена |

В таблице относительные frontend names после первого prefix относятся к frontend/src/.
Backend runtime, migrations, grants, frozen auth/tenancy/R4, contracts/openapi.json,
base compose.yaml, workflows, manifests/lockfiles/images и canonical sources вне
этого scope. Новые зависимости не нужны. Конкретный blocker в этих областях вернуть
C0 с минимальной предлагаемой дельтой; не обходить защиту тестом и не расширять silently.
Уже перечисленные TEST harness paths разрешены: повторного согласования не требуют.

### Ключевые consumer решения — не переизобретать API

- Owner gate по membership.role; frozen permissions не содержит messaging:*.
- Три коллекции limit25/cursor, send202 с {text}/Idempotency-Key, grant200 с{};
  обычные GET200. Два503 и строгие DTO читаются по принятому контракту.
- Не вычислять entitlement из пяти billing TEST keys. Stale connection observation
  не блокирует навсегда явный «Проверить и отправить»: POST refresh и worker authority.
- Single page-memory intention; panel не unmount при recovery. Смена контекста скрывает
  data/URLs и отвергает late responses. Same-key recovery возможен только для того же
  actor/Workspace/conversation;202 ведёт к GET, UNKNOWN не создаёт retry/resend.
- Text exact Unicode, не trim/NFC, не native UTF16 maxLength как scalar limit.
- Private READY image открывается по явному current-owner grant, URL не переписывать,
  не логировать/сохранять. Expiry/denial — явный новый grant, без фонового цикла.
- TEST runtime/PG/S3 путь настоящий; только внешний adapter/provider CONTROLLED.
  No production test endpoints и no direct canonical fixture writes ради PASS.

### Конечные проверки и границы evidence

Это детализация существующих строк M2-A01…A12, не новая acceptance matrix.

| Проверка | Фактическое evidence C5 |
|---|---|
| A10 + A06/A07: повседневный сценарий | Browser login → нужный Workspace/conversation → text и реальный private image → ручной POST → существующий worker → обновлённый delivery. 202 не рисуется как доставлено; anonymous S3 GET не раскрывает object |
| A10: страницы и обновления | More-than-one-page fixture; opaque cursor/end/null, без duplicate rows; fresh refresh/reload делает GET, не POST. Смена диалога/Workspace с задержанным ответом не возвращает прежние данные |
| A03/A10: потеря ответа | Playwright route.fetch исполняет настоящий POST/commit, затем теряется ответ браузеру; восстановить session/CSRF и тот же key/body. Exact receipt/message сохранены; counts Message/receipt/Audit/Outbox/Job увеличились ровно один раз |
| A05/A10: UNKNOWN | Настоящий Worker с CONTROLLED UNKNOWN и сохраняемым CALL/EFFECT counter; replacement runner/recovery/UI refresh/same-key receipt не вызывают второй adapter call. UNKNOWN не имеет resend action |
| A07/A08: private/authority | Image pending/error/ready; real grant+GET; cross-Workspace/mismatched refs/OWNER revoke запрещают новый grant/send/history. Уже выданная ссылка имеет прежнюю TTL границу; late grant не открывает image после context change |
| A09/A10: состояния и отказы | Component/parser coverage всех connection/file/delivery states и двух503; real API/browser NOT_ALLOWED/revocation, история доступна при product restriction; cached status не authority. Actual Telegram rights остаются live проверкой |
| A10/A12: UI и регрессия | keyboard/narrow, double submit, Unicode astral/NUL/surrogate/whitespace, safe text rendering; прежние auth/logout/Business/Billing/Audit/Ops journeys и guards сохранены |
| A11: внешний Console smoke | Только при реально доступном runtime: разрешённый Client text+photo → Owner Console/private image → reply → Client подтверждает получение; exact SHA/date и очищенный receipt. Без доступа — BLOCKED, не fake PASS |
| A12: штатные gates | sh scripts/ci.sh; sh scripts/test_browser.sh; оба clean-source gate; canonical imports, migrations, contracts, reproducibility/smoke на одном итоговом head. После merge отдельный main CI проверяет C0 |

Автор пишет нужные тесты; C0/C8 проверяют поведение, не количество. При падении
сначала установить причину, сохранить исходный failure и объяснить исправление
теста принятым поведением. Не заменять real PostgreSQL/S3 SQLite/mocks; component
mocks допускаются в своей явно обозначенной границе. Full real TCP Telegram send-loss
из M2.3 остаётся в регрессии; повторно проектировать его для браузера не требуется.

### Возврат C5 → C0

Оставить PR **Draft/open/not merged**, статус REVIEW. Вернуть одним receipt:
accepted base, сохранённый coordination, final head/parent/tree, actually tested
SHA и его parents/tree, ссылки/attempt/jobs CI, все changed paths, commands/results,
tests/assertions→A-criteria, причины старых test/fixture deltas, ограничения Docker/
artifact/live evidence и следующий шаг. Browser mock, CONTROLLED и настоящий Telegram
не смешивать. ZIP bytes заявлять только после фактической загрузки/сверки.

Одним обновлением привести register/active handoff/contract в REVIEW; не создавать
цепочку SHA-only commits. После последней дельты проверить именно итоговый head.
C5 не объявляет M2.4/M2 VERIFIED, не снимает Draft и не сливает PR самостоятельно.
C0 назначит независимый scoped C8 по реализации и подготовит user merge после PASS.

### Что остаётся от пользователя для live Telegram

Bot с Business/Secretary Mode, Owner/Client и секреты уже подготовлены. Подключать
password manager к чату не нужно. Нужен доступный Linux host/Docker, два DNS имени
для Console/private files и TLS; пока их нет, A09/A11 live BLOCKED. Секреты помещаются
непосредственно в operator-owned0600 .env.telegram/secret store на runtime по runbook,
не в чат/PR. C0/C6 подготовят конкретное deployment действие; платная инфраструктура
только после предложения точной стоимости и разрешения. Это не блокирует C5.

</details>

<details>
<summary>История: приёмка M2.3 до фактического merge — не текущие инструкции</summary>

## История — handoff C0: M2.3 code/API, приёмка до merge / 2026-09-21

**M1.1–M1.3, M2.1 и M2.2 VERIFIED LOCAL/TEST. M2.3 REVIEW: code/API принят
C0 и независимым scoped C8 после исправления C8-M2.3-01. Merge/main CI впереди.
Live Telegram BLOCKED: внешнее runtime/DNS/TLS. M2.4 TODO; весь M2 IN_PROGRESS.**
История ниже сохраняет прежние поручения и не переопределяет этот активный блок.

Repository **Elefesys/ai-service-manager**; тот же
[PR #20](https://github.com/Elefesys/ai-service-manager/pull/20), ветка
**`c3/m2-3-telegram-api`** → main. Accepted base/main
**`a321bdd58856fb41bccb5749b4212349832e623c`**; первый coordination
**`5347e3de498752be2834573eadfb39d59dc51bcb`** сохранён.
Технический контракт — [M2_CONTRACT §10](M2_CONTRACT.md#10-m23-telegram-api--принято-c0c2c3c1-2026-09-21).

### Что принято C0

Code/API LOCAL/TEST: официальный business text/photo webhook с durable receipt/Inbox/
Jobs; trusted operator binding; private image pipeline; пять authenticated owner
routes; manual text intention/Outbox/send с UNKNOWN/no-resend; generated OpenAPI,
recovery notes и исполнимый TEST runbook. Это готовность к интеграции кода, не evidence
живого Telegram или Console A11.

C0 проверил52 changed paths и все204 source blobs/modes исходного implementation
head `439eb3228a681dd1558ab98ebe232d4a266d9874`, tree
`c4c308b2a4073ce2eaae7e6b0f5bd2f3778a3da1`; parents/coordination ancestry/оба checkout
logs и [CI35632000530](https://github.com/Elefesys/ai-service-manager/actions/runs/35632000530)
SUCCESS. Все11 приложенных canonical sources совпали побайтно. Сохранены47 выбранных
frozen/accepted files, включая0001–0006, frontend/workflows/CI scripts и private
validation/storage/transfer. Прежние OpenAPI paths/schemas структурно неизменны;
lock package blocks неизменны кроме root metadata для httpx0.28.1 runtime promotion.

Миграция0007→0006 соответствует принятому inventory: две platform tables, typed
capabilities, provider/window/retry/probe metadata; runtime без общего DML. Новый
product key использует настоящий EntitlementService, прежние пять TEST decisions
GET billing и sealed catalog сохраняются. Дополнительного scope нет.

### Независимый scoped C8 и единственное исправление

| Область | Реально выполненный review и результат |
|---|---|
| Transport/webhook/media/setup | Независимый read-only C8 PASS: auth-before-parse, durable ACK, numeric/opaque IDs, fixed origin/TLS/bytes/time, secret-safe transport, send UNKNOWN, trusted bootstrap, private signed origin.84 targeted unit/setup PASS; дополнительный реальный TCP send-loss probe дал UNKNOWN/1 wire call, encoded JSON отвергнут до decoder, missing secret403 до receive |
| DB/worker | Независимый review RLS/grants/FK, authoritative fingerprints/dedupe, claims/CAS, product, replay/recovery/429 и migration cycles. Найден единственный P2 C8-M2.3-01; прочие blockers отсутствуют |
| Owner API/auth/product/recovery | Независимый review пяти routes, DTO/errors/cursor, двух auth UOW без network под DB admission, replay-before-CAS, isolation/private grant и frozen contracts. Подтверждён тот же C8-M2.3-01; других blockers нет |
| Targeted closure | Независимые DB/API reviewers проверили точный narrow fix и новые PG assertions, затем exact-head runner evidence. **C8-M2.3-01 PASS / CLOSED** |

Причина C8-M2.3-01: billing timestamp снимался до получения account lock, а reply
window проверялось до potentially blocking billing guard. Принятый contact writer
мог удерживать FOR NO KEY UPDATE, пока истекали subscription/mode/window; valid
worker lease не устраняла эту гонку. Аналогичный порядок был в canonical owner SQL.

C2 изменил только `migrations/versions/0007_telegram_api.py` и
`tests/test_m2_3_db_postgres.py`: billing time теперь после всех billing locks;
финальный Telegram window/observation guard повторяется после billing перед новым
owner intent и worker DISPATCHING. Ранние denials/replay/structural precedence,
frozen R4 snapshot, lock_timeout2s и lease30s сохранены.

| Новые реальные PostgreSQL cases | Assertions |
|---|---|
| `test_worker_denies_expiry_during_billing_lock_without_adapter_call[subscription/mode/window]` | Отдельный asm_runtime observer подтверждает ожидание account UPDATE через pg_blocking_pids и свежий activity snapshot; TEST boundary ставится в будущем после подтверждённого wait; pg_sleep_until ждёт DB deadline. Release после expiry при действующей lease → FAILED/NOT_ALLOWED, attempt_id/last_attempt_id NULL, send не вызван, wire ledger отсутствует |
| `test_owner_denies_expiry_during_billing_lock_without_intention[subscription/mode/window]` | Тот же подтверждённый lock crossing; canonical request даёт именно P2001/NOT_ALLOWED. Нет outbound Message/receipt/Audit/Outbox/Job, последующий worker ничего не отправляет. Lock timeout/раннее завершение фоновой задачи не считаются PASS |

Прочие assertions→A01–A09/A12 сохранены в исторической передаче C3 ниже и в tests.
Количество локальных повторов/C8 probes не прибавляется к числу cases одного CI.

### Проверенная версия исправления и final-head gate

Implementation fix **`0ffd9e2146fe5fda1db22152b6feaa1737fc9151`**; parent —
исходный439eb3228a681dd1558ab98ebe232d4a266d9874; tree
**`90079c2c8874b6456b1710aef2538467513f018a`**.
Tested virtual merge **`bd40f1e70e540e896a305cd5324d31d93b7e865f`** имеет parents
accepted base + fix head, его tree совпадает.
[CI35647402496](https://github.com/Elefesys/ai-service-manager/actions/runs/35647402496)
**SUCCESS**:421 unit,390 real PostgreSQL/S3,60 frontend,15 прежних M1 browser.
Исполнены оба scripts/clean-source gates, canonical import/migrations/contracts/
reproducibility/smoke. Сохранены реальные TCP crash/restart UNKNOWN/1 wire call
и private signed GET сценарии. Локально C0 повторил421 unit; Docker отсутствует,
PostgreSQL/S3 execution относится к GitHub runner.

C0 сверил Git objects/blobs и логи; локальная загрузка исходного ZIP получила403,
поэтому C0 не повторяет от своего имени byte-verification ZIP из отчёта C3.
Artifact metadata и точный final receipt находятся в PR.

Это одно согласованное документационное обновление после review/fix. Собственные
final head/tree/tested SHA и CI этого обновления записываются в PR receipt, без
следующего коммита ради SHA документа. C0 проверяет оба checks именно final head,
после SUCCESS снимает Draft и предлагает пользователю обычный **merge commit**.
Самостоятельный merge запрещён. После сообщения пользователя C0 проверяет actual
merge parents/tree и отдельный push/main CI; только затем выдаёт C5 M2.4.

### Открыта только соответствующая внешняя проверка подключения

Bot с Business/Secretary Mode, Owner/Client и два секрета подготовлены пользователем.
Live getMe/getBusinessConnection/getWebhookInfo, actual rights/binding, внешний HTTPS,
browser-reachable private signed GET и получение reply Client ещё **не проверены**.
[TEST runbook](../runbooks/M2_TELEGRAM_LOCAL_TEST.md) рассчитан на доступный оператору
Linux host/Docker, два DNS имени и действительные TLS certificates; окружение ещё
не предоставлено/не развёрнуто. Секреты передаются непосредственно в защищённый
runtime file/secret store, не в чат/PR. Расходы и внешние отправки не выполнялись;
платный вариант требует предложения конкретной стоимости до подключения.

Недостающий доступ блокирует live smoke. Принятие code/API не закрывает эту проверку,
M2.4 или весь M2. Следующее зависимое поручение C5 готовит минимальную переписку
в существующей Console и реальные browser journeys после API/main acceptance.
Весь M2 требует Client text+photo→Console→manual reply→Client A11; M3 не выдаётся.


</details>

<details>
<summary>История: принятое поручение и исходная передача реализации C3 — не текущие инструкции</summary>

## История — выдача и первоначальная передача M2.3 в REVIEW / 2026-09-21

**M1.1–M1.3, M2.1 и M2.2 VERIFIED в принятых LOCAL/TEST границах.
M2.3 передан в REVIEW: Telegram/owner API реализованы в том же Draft PR #20;
приёмка C0 и независимый scoped C8 ещё впереди. M2.4 TODO; весь M2 IN_PROGRESS.** История ниже не является текущим
поручением. Ведущий **C3**; C2 — миграция/DB, C1 — owner API/product policy,
C6 — необходимая TEST конфигурация/операционный runbook. C8 выполняется независимо
после реализации, предметное согласование C2/C3/C1 его не заменяет.

Repository **Elefesys/ai-service-manager**. Exact accepted implementation base/main:
**`a321bdd58856fb41bccb5749b4212349832e623c`**. Ветка
**`c3/m2-3-telegram-api`** → main; продолжить единственный Draft PR, подготовленный
C0. Его номер, стартовые coordination head/tree и CI находятся в PR metadata и
готовом поручении C0. **Первый coordination commit сохранить.** Локальный synthetic
commit из source checkout не является accepted base. Не создавать параллельный PR
и не выполнять самостоятельный merge.

### Подтверждённая приёмка M2.2 после merge

[PR #19](https://github.com/Elefesys/ai-service-manager/pull/19) MERGED пользователем.
Merge parents `d3c849d4792f7af60f43eea0f0551659ee3cee5d` +
`1e460ea58c7d9ceb48152cdd49a651b66ad625b7`; actual main выше. Tree
**`8221b88b481378d49a185e29e95e3d20ea119c0c`** = accepted final PR tree.
[Отдельный push/main CI 35611528733, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/35611528733)
**SUCCESS**; head/tested SHA в обоих checkout logs = actual merge. Foundation/browser,
оба scripts/clean-source gates, canonical import, migrations/contracts/reproducibility/
smoke PASS: 288 unit, **305 real PostgreSQL/S3**, 60 frontend, 15 прежних M1 browser.
Artifact10644182993, GitHub SHA-256
`d3d4769abd230af57735a10dd641acb532adae4e9c6dac3b22b3880c645c2b83`;
ZIP побайтно не проверен. Source tree/Git SHA/checkout и исполненные gates проверены.

Независимый scoped C8 private-files/recovery и targeted **C8-M2.2-01 PASS** относятся
к принятому коду; WebP preflight исправлен до native allocation. Финальный PR CI
35610084640 также SUCCESS. C0 принимает **M2.2 controlled LOCAL/TEST private images**,
применимые A07/A08 и A02/A04/A06/A12, а не настоящий Telegram/API/UI/Console A11.
Не повторять M1 или проектирование M2.1/2; их regression и guards сохранить.

### Один конечный результат M2.3

Реальный официальный Telegram business adapter: verified webhook → durable shared
Telegram receipt + прежний Inbox/Jobs → правильный Workspace/Message → photo через
принятый private S3 → authenticated owner API → ручной TEXT intention → Outbox →
одна Telegram send attempt с честным UNKNOWN. Публичный owner API готов для C5,
generated contracts и recovery notes соответствуют фактическому поведению.

Технические решения — только [M2_CONTRACT §10](M2_CONTRACT.md#10-m23-telegram-api--принято-c0c2c3c1-2026-09-21).
C0 прочитал существующий код/канон и принял его после read-only C2/C3/C1 CONTRACT PASS.
Во время review явно уточнены opaque provider IDs и отдельный one-UOW CONTROLLED
public path; это не введение нового требования под видом старого. Миграция
**0007_telegram_api.py, revision0007, predecessor0006** назначена C0/C2.

Главные зафиксированные границы:

- Доверенная operator-only binding предварительно подтверждённого Workspace/Business/
  Telegram Owner, getMe/getBusinessConnection; connection ID сам по себе не authority.
  Setup discovery не ACK/drop pending updates; setWebhook только после DB commit.
- Один общий Telegram receipt без raw payload/второй очереди. ACK после durable commit;
  known duplicate возвращает прежний результат, unknown business route503 без tenant
  writes. Numeric и opaque IDs различаются; native/echo/edit/delete/unsupported durable
  и не создают новую client Message. Входящее изображение — photo, не image-document;
  original означает выбранный provider file, не исходник до обработки Telegram.
- Snapshot rights с generation+observation-version CAS; old response не восстанавливает
  разрешение. DB24h window из нового поддержанного входящего, duplicate не продлевает.
  Worker всегда делает readonly preflight вне DB перед DISPATCHING. Timeout/неясный
  send →UNKNOWN/no-resend;429 уважает retry_after при прежних5claims/15min.
- Ровно пять owner routes §10.8. Cookie/Origin/CSRF/liveOWNER, строгие DTO/cursor,
  exact append-only text/key/replay. TELEGRAM POST имеет две последовательные short
  UOW с provider refresh между ними; replay проверяется до новых gates. CONTROLLED
  public LOCAL/TEST POST — одна UOW без Telegram HTTP, с тем же product gate.
- Product key messaging.manual_send BOOLEAN/ESSENTIAL, настоящий EntitlementService;
  fresh-only test_messaging plan, старые TEST catalog/keys/GETbilling не меняются.
  Read/history/grants и durable inbound/FETCH не блокируются subscription.
- HTTPX0.28.1 только narrow runtime promotion; фиксированный Telegram origin, no hidden
  retries/redirects, bounded bytes/time/pool, secret-safe logs; provider stream использует
  неизменённые M2.2 validation/fencing/cleanup. Никаких AI/M3/цен/платежей.

### Разрешённые области C3/C2/C1/C6

| Пути | Точная разрешённая дельта / владелец |
|---|---|
| `backend/src/asm/telegram/` | C3: только §10 config/client/webhook/normalization/adapter/provider/provisioning helpers; без будущего универсального SDK |
| `backend/src/asm/messaging/` | C3/C1: TELEGRAM alongside CONTROLLED, typed ingress/probe/dispatch/429 и ровно пять owner HTTP/DTO/repository/cursor routes; прежние fingerprints, atomicity/replay/UNKNOWN сохраняются |
| `backend/src/asm/tenancy/database.py` | C1/C2: narrow typed owner helpers/cursor/receipt/observation seams в настоящем guarded UOW, без общего SQL/DML API |
| `backend/src/asm/billing/service.py` | C1: evaluate known product capability через тот же validator/precedence, прежний GET billing/TEST set неизменен; без новой billing feature beyond manual_send |
| `backend/src/asm/files/{models,provider,service}.py` | C3/C1: provider literal/dispatch и grant в текущем owner UOW. Validation/storage/transfer/cleanup и SQL file capabilities не переоткрывать |
| `backend/src/asm/auth/http.py` | C1: только exact POST messages body64KiB вместо4KiB; старые paths/body/auth/session/Origin/CSRF/CORS guards сохраняются |
| `backend/src/asm/foundation.py` | C3/C1: schema revision0007, small delegated Telegram/API lifecycle/config/wiring, default CONTROLLED; не помещать domain SQL/transport в entrypoint |
| `migrations/versions/0007_telegram_api.py` | C2: §10 two-table inventory/provider CHECKs/window/typed capabilities/policy/429/read/provisioner; downgrade refusal без уничтожения Telegram history. 0001–0006 immutable |
| `pyproject.toml`, `uv.lock` | Только httpx0.28.1 dev→runtime с необходимой root metadata, без package versions/hashes refresh/new SDK |
| `.env.example`, `compose.yaml`, `infra/nginx.conf` | C6/C3: optional server-owned Telegram env и exact webhook forwarding/setup; disabled default и прежние LOCAL services/loopback isolation сохранены. Не публиковать DB/S3 admin или выбирать paid hosting |
| `scripts/provision_telegram_test.py`, `scripts/smoke_telegram_test.py` | C3/C6/C2: одна исполнимая bounded LOCAL/TEST setup/binding и явно включаемый live check; no token CLI/logs, no pending drop/ad-hoc SQL, no automatic send в обычном CI |
| `scripts/provision_local_auth.py`, `scripts/m1_3_browser_fixture.py`, `scripts/provision_browser_test.py`, `scripts/check_browser_compose.py` | Только необходимая current-revision/config compatibility, если реально нужна; старые TEST guards/assertions не ослаблять, каждую дельту объяснить |
| `contracts/openapi.json`, `contracts/README.md` | C1: generated additive routes/DTO и готовые consumer/recovery notes; frozen auth/tenancy/R4 wire snapshots сохраняются |
| `tests/test_m2_3_*.py`, `tests/fixtures/telegram/` | C3/C2/C1: finite parser/network/HTTP/PG/S3/recovery/migration tests §10, synthetic fixtures без пользовательских данных |
| `tests/test_auth_contract.py`, `tests/test_foundation.py`, `tests/test_postgres.py`, `tests/test_tenancy_postgres.py`, `tests/test_m2_1_*.py`, `tests/test_m2_2_*.py`, `tests/test_m1_3_c0_acceptance.py`, `tests/test_browser_compose.py` | Только additive schema/head/inventory и FK-ordered fixture cleanup/config expectation; прежние guards/UNKNOWN/file/privacy assertions сохраняются, объяснить каждое изменение |
| `docs/tasks/M2_CONTRACT.md`, `docs/tasks/M2_HANDOFF.md`, `docs/TASK_REGISTER.md`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` | Один контракт/реестр/активный handoff и один конкретный operational runbook/evidence; история отделена от текущих инструкций |

Рутинные необходимые изменения этих paths по указанным причинам уже разрешены C0;
не останавливать работу повторным запросом. Миграции ведёт C2 последовательно;
SQL имена/реализацию выбирают C2/C3 по принятому контракту, не пользователь.
Frontend, applied migrations, canonical originals/SOURCE_MANIFEST, R4 и новые billing
routes/plan edits не изменять. Existing CI/workflows/scripts/gates не требуют redesign;
local HTTP fault server живёт внутри tests. Иной конкретный конфликт вернуть C0 с
минимальной дельтой/причиной до расширения, не скрывать его под изменением test.

### Конечные критерии и evidence

| Строки единой матрицы | Обязательная фактическая проверка |
|---|---|
| A01/A02 | Реальный HTTP webhook + runtime PostgreSQL: secret missing/wrong/duplicate, unknown/cross-bot/owner/Workspace binding; duplicate/concurrent/hash conflict; receipt/Inbox/Job rollback каждого звена; ACK только после commit, lost ACK/restart без дубля |
| A06/A07 | Telegram-shaped text/photo/native/echo/edit/delete/unsupported/out-of-order fixtures; sender isolation, exact projection, media group correlation. getFile fixed host/hostile path/redirect/bytes/time/secret failures; настоящее photo→PostgreSQL/private S3→owner HTTP grant→signed GET |
| A03/A08 | Все пять routes через auth/CSRF/Origin: cross-Workspace и false same-Workspace relation, revoked/downgraded OWNER. Exact text/key/fingerprint/concurrent replay/conflict/atomic Audit-Outbox rollback, потеря HTTP response после commit и один intention; новыйkey не recovery |
| A04/A05/A09 | Worker с реальным PostgreSQL и локальным HTTP server: server принял send и потерял ответ →UNKNOWN; restart не делает второй wire call. Lifecycle/refresh CAS race, owner/plan/rights revoke до dispatch, exact24h/future-date/duplicate boundary;429 durable minimum delay/exhaustion/finalize ACK replay |
| A03/A08/A09 | Настоящий EntitlementService/SQL parity: missing/false/inactive/modes/structural503, replay после plan/route restriction; history/grants/inbound сохраняются. Fresh TEST provisioning exactrepeat/conflict/concurrency и старый R4 catalog unchanged |
| A12 | Strict DTO/errors/cursors и exact64KiBroute/old4KiB; current schema/inventories; clean/0006-data/repeated upgrade, downgrade refusal сохранил данные, явный TEST cycle. Full M1/M2.1/M2.2 regressions, generated contracts, reproducibility, оба clean-source gates |
| Внешняя часть A09/A11 | Отдельно фактические getMe/getBusinessConnection/getWebhookInfo, тестовая binding/rights/HTTPS; client text+photo→owner API/private GET→ручной API reply→client. Exact code SHA/date/sanitized outcome. Это ещё не Console A11/M2.4 |

Штатные **sh scripts/ci.sh** и **sh scripts/test_browser.sh** обязательны на final head.
PostgreSQL/S3 не заменять collection/mocks; MockTransport не доказывает ambiguous
wire-send recovery. При отсутствии local Docker — обычный GitHub runner, точные
checkout SHA/tree/run и исполнившиеся gates. При failure сначала установить test
или implementation defect; не убирать защиту ради green CI. Existing15browser —
M1 regression, новые messaging browser journeys выдаются C5 только после API acceptance.

C3 возвращает один PR в REVIEW: accepted base, preserved coordination, final head/
tree/tested merge+parents, changed paths, migration/dependency/contract deltas,
конкретные tests/assertions→матрица→run/results, ограничения/OPEN/внешние blockers.
Первый coordination commit сохранить. Final SHA/CI в PR receipt, без цепочки SHA-only
doc commits. Не объявлять самостоятельно INTEGRATED/VERIFIED и не сливать PR.
C0 принимает scope/результат и организует реальный независимый scoped C8 Telegram/API
trust/effect review; затем пользовательский merge и отдельный actual main CI.

### Передача реализации C3/C2/C1/C6 в REVIEW

[Draft PR #20](https://github.com/Elefesys/ai-service-manager/pull/20) содержит код,
миграцию 0007→0006, generated OpenAPI, consumer notes и
[исполняемый TEST runbook](../runbooks/M2_TELEGRAM_LOCAL_TEST.md). Coordination commit
`5347e3de498752be2834573eadfb39d59dc51bcb` сохранён; accepted base выше не менялся.
Точный final head/tree, tested virtual merge и parents, фактические CI/assertion
результаты и полный список paths — **PR receipt**. SHA-only commits не нужны.
Следующее действие — C0 acceptance и независимый scoped C8 Telegram/API review.

| Критерий | Исполнимая проверка и проверяемый результат |
|---|---|
| A01/A02/A06 | `test_m2_3_transport.py` и `test_m2_3_db_postgres.py`: strict numeric/opaque projection и DB fingerprint; шесть concurrent duplicates → один receipt/Inbox/Job; conflict; cross-bot/unknown binding/чужой Owner без writes; native/echo/edit/delete/unsupported → явные terminal receipts без Message/Job |
| A01/A02 | `test_m2_3_wire_postgres.py::test_real_tcp_webhook_never_acknowledges_before_durable_commit`: настоящий TCP HTTP request остаётся без ACK, пока barrier держит commit; другая PG connection не видит receipt; после commit HTTP200 и durable row. HTTP rollback/ACK-loss tests и DB fail-trigger каждого receipt/Inbox/Job звена |
| A03/A08 | `test_m2_3_api_postgres.py`: ровно пять routes, точные DTO/text/key; concurrent receipt replay → один intention/Audit/Outbox/Job; fail-trigger каждого звена → ноль частичных rows; response loss → тот же receipt; все routes требуют live session/OWNER; forged tenant/relation/cursor отвергаются |
| A03/A09 | `test_m2_3_api_telegram_postgres.py`: два настоящих auth units с refresh между ними и без занятого pool; replay выигрывает до stale CAS/новых restrictions; lifecycle invalidation →503 без намерения; OWNER/product revoke между units; bounded failure observation сохраняется |
| A04/A05/A09 | `test_real_http_accept_lost_response_process_restart_never_second_wire_call`: настоящий локальный сервер принимает sendMessage и теряет response; отдельный worker process падает до/после finalize commit; durable wire ledger=1 после replacement worker/recovery, delivery UNKNOWN, второго wire call нет |
| A04/A09 | DB tests `test_observation_cas_fences_invalidation_and_concurrent_refresh`, `test_old_begin_and_unprobed_claim_cannot_bypass_telegram_preflight`, `test_dispatch_rechecks_current_authority_business_billing_and_window`: generation/version/claim fences, live authority и exact24h denial; future date clamp и duplicate не продлевают окно |
| A04/A05 | `test_429_finalized_delay_is_durable_replay_and_horizon_exhausts`: due не раньше retry_after, canonical finalize replay сохраняет due, changed delay отклонён, пересечение15min → DEAD/RETRY_EXHAUSTED; прежние M2.1 five-claim/backoff/crash/UNKNOWN tests продолжают выполняться |
| A07/A08 | `test_real_telegram_photo_http_pg_s3_owner_grant_and_signed_get`: реальные getFile/photo HTTP → прежний validator/fencing → PG/private S3 → authenticated grant → реальные signed GET bytes; TTL60, anonymous403, forged relation404, без DB unit на provider I/O. Hostile paths/encoded bodies отклоняются до чтения |
| A03/A08/A09 | `test_m2_3_policy.py`, API/DB policy cases: настоящий EntitlementService и SQL dispatch parity, missing/false/inactive/modes/structural503, чтение/grants без product gate. Fresh setup exact repeat/conflict/concurrency и старый TEST catalog неизменны |
| A12 | `test_m2_3_schema_postgres.py`: ровно две новые FORCE RLS таблицы, нет runtime DML; composite FK/immutable owner; 0006 rows/FileObject winner/UNKNOWN/billing сохраняются при upgrade/repeat/downgrade/reupgrade; Telegram history →55000 до первой mutation. Штатные full CI/browser, contracts/reproducibility, оба clean-source gates |

Необходимые изменения прежних tests объясняются принятой additive дельтой:

- `test_auth_contract.py`: inventory дополнен ровно пятью owner routes; frozen auth
  seven-endpoint snapshot неизменен. `test_foundation.py`: current head0007 при
  неизменном frozen tenancy0003.
- `test_m2_1_models.py`: отрицательный provider-вектор использует неподдерживаемое
  имя, поскольку TELEGRAM теперь принят. Остальные validation vectors сохранены.
- `test_m2_1_postgres.py`: scoped fixture cleanup удаляет новые receipt/state до
  старой FK-цепочки; tenantless rows удаляются только для fixture bot identities.
- `test_m2_2_migrations.py`: сравнение исходных0005 rows исключает только additive
  nullable metadata0006/0007. Отдельный0007 migration test проверяет сохранность
  FileObject winner, UNKNOWN и billing; privacy/recovery assertions сохранены.
- `test_postgres.py` и `test_tenancy_postgres.py`: точные table/function inventories
  расширены на принятые две таблицы и typed capabilities, без общих SQL/DML прав.

**Live Telegram: BLOCKED — внешнее runtime/DNS/TLS окружение не предоставлено.**
Bot token/webhook secret не запрашивались и не использовались. Реальные getMe/
getBusinessConnection/getWebhookInfo, browser HTTPS signed GET и получение Client
ответа должны быть записаны отдельно оператором по runbook. Обычный CI проверяет
локальный HTTP fault server, настоящие PostgreSQL/S3 и прежний M1 browser; не доказывает
внешний Telegram или Console A11. C5 начинает после принятого merge/actual main CI.

### Что подготовить для live Telegram, не блокируя независимый код

Пользователь уже подготовил test bot с Business/Secretary Mode, Owner/Client и
TG_BOT_TOKEN/TG_WEBHOOK_SECRET в password manager. Повторно токены не запрашивать;
подключать password manager к чату не надо. В runbook дать один конкретный порядок:

- Exact accepted code, fresh TEST Workspace/Business и independently approved Owner ID;
  operator setup разрешён только LOCAL/TEST, не rebind по чужому connection ID.
- Секреты оператор помещает непосредственно в ignored runtime secret file, например
  `.env.telegram` mode0600, или deployment secret store; никогда в чат/PR/артефакт.
- C6 готовит тестовый HTTPS endpoint, exact Console Host/Origin+secure cookies,
  worker/scheduler/private DB/S3. Signed GET должен открываться браузером: HTTPS
  signing endpoint с неизменёнными host/path, а не подмена internal MinIO hostname.
- Явно включаемый smoke отправляет только в согласованный тестовый диалог; cleanup
  не сбрасывает pending updates. Зафиксировать действительные права/наблюдения,
  не обещать их по одному флагу Business Mode или публичной документации.

Внешний TEST deployment ещё не выбран/не запущен, текущий loopback Compose не
является интернет-окружением. Расходы не разрешены; paid вариант сначала требует
конкретной стоимости. Недостающий runtime/HTTPS доступ блокирует только live check,
не adapter/API/DB/S3 tests. C0 может отдельно принять code/API с явным внешним blocker;
C5 — только после интеграции API/main CI. M2 целиком требует всех четырёх частей и
настоящего Client text+photo→Console→ручной reply→Client сценария A11; до этого M3 не выдаётся.


</details>

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

## История — M2.2 pre-merge передача C0 / 2026-09-21

**M2.2 REVIEW, не INTEGRATED/VERIFIED; M2.3/M2.4 TODO; весь M2 IN_PROGRESS.**
M1.1–M1.3 и M2.1 приняты в LOCAL/TEST. Повторно не выполнять исторические поручения.
Repository `Elefesys/ai-service-manager`; единственный
[PR #19](https://github.com/Elefesys/ai-service-manager/pull/19), ветка
**`c6/m2-2-private-images`** → main. Accepted actual base
**`d3c849d4792f7af60f43eea0f0551659ee3cee5d`**, tree
`f12aa90a3c3fb7fdfda84290315a3fd820816b4b`;
[отдельный main CI 35596593891](https://github.com/Elefesys/ai-service-manager/actions/runs/35596593891)
SUCCESS. Coordination commit `c4ad360e482f47a30e6f0756a13e6ce1cf68def4` сохранён.
Ни параллельного PR, ни самостоятельного merge, ни поручения M2.3 сейчас нет.

### Результат C0 review и ограниченный fix

C0 сверил все 37 изменённых paths исходного implementation head
`5d72557a1058906e0040d5f410968f769986f2e8`, tree
`9d250238368d6f8b6087c1f34b87a18832791397`. Проверенный virtual merge
`b69257dc2dc2c2f8acb77158466bd1242cc6cf34` имеет parents accepted base + этот head
и то же дерево. [CI 35605713463](https://github.com/Elefesys/ai-service-manager/actions/runs/35605713463)
SUCCESS: 220 non-integration, 303 PostgreSQL/S3, 60 frontend, 15 прежних M1 browser;
оба штатных scripts/clean-source gates, migration cycles/contracts/reproducibility/
smoke PASS. ZIP download получил 403 / Cloudflare 1010: C0 не утверждает побайтную
проверку ZIP. Вместо этого проверены Git blob SHA всех изменённых файлов и полное
реконструированное дерево, checkout logs и исполненные clean-source gates.

Scope соответствует [M2_CONTRACT §9](M2_CONTRACT.md#9-m22-private-images--принято-c0c2c3-2026-09-21):
controlled provider → atomic Message/FileObject/FETCH → validated original в private
S3 → READY → внутренний live OWNER signed GET. Canonical DB relations/FORCE RLS,
worker trust/lease/XID/task, composite READY/WINNER FK, per-attempt keys, lost ACK,
late PUT/tombstone cleanup, no-I/O-with-DB-transaction, migration/backfill и сохранение
SEND UNKNOWN проверены. Старые fixtures адаптированы по фактической новой схеме,
без удаления guards; точные причины и tests→матрица сохранены в истории ниже.
0006→0005 согласована C2; 0001–0005, canonical originals, auth/tenancy/R4,
OpenAPI/frontend, старые package blocks и пять image pins не изменены.

Реальный независимый C8 review private-file authorization/validation/worker/cleanup
нашёл **один blocker C8-M2.2-01, P2**. До fix WebP native decoder создавал canvas
внутри Image.open до наших side/pixel checks. Безопасный subprocess probe с cap
384 MiB показал: 5000×4001 увеличивал виртуальное адресное пространство до возврата
INVALID_INPUT; 8192² получал native allocation error под cap. Фактический OOM или
рост resident memory до этих величин не заявлялись. Исходный green CI этого риска
не доказывал: прежний preallocation test использовал PNG/Image.load.

C0 поручил C3 только три существующих path: `backend/src/asm/files/validation.py`,
`tests/test_m2_2_media.py`, `tests/test_m2_2_recovery_postgres.py`. Fix проверяет
bounded RIFF/chunk/VP8/VP8L/VP8X headers, canvas/bitstream dimensions и отсутствие
animation **до Image.open**. Затем сохраняются verify, полный decode, original
hash/bytes и все прежние лимиты/форматы. Миграции, dependencies/locks и CI не менялись.
**Независимый targeted C8-M2.2-01 PASS: blocker закрыт по reviewed source.**
C0 code/scope review PASS; готовность к merge требует итогового полного CI.
C8 отдельно выполнил 96 media tests и исходный safe subprocess probe на pinned
Python 3.13.15 / Pillow 12.3.0 / libwebp 1.6.0: 5000×4001 и 8192² отвергаются
с native_calls=0; контрольный 1×1 проходит настоящий decoder. Patch SHA-256
`b60264b29374c1f96a9de45bfc191e4119e16ee91032bbae179854dd61b428bd` проверен.
Это независимый review дельты, не авторский CONTRACT PASS; новых blockers нет.
Прежний scoped C8 review остальных private-file/DB/recovery областей остаётся
действительным. Два новых PostgreSQL cases C8 прочитал, но локально не исполнял.

| Применимый критерий | Дополнительная проверка C8-M2.2-01 и граница evidence |
|---|---|
| A07 validation | `test_webp_oversize_is_rejected_before_native_canvas`, `test_webp_canvas_and_bitstream_cannot_disagree`, `test_webp_malformed_structure_is_rejected_before_native_canvas`, `test_real_animated_webp_is_rejected_before_native_canvas`: native constructor не вызывается для oversized/contradictory/structurally malformed/animated headers |
| A07 сохранение контракта | `test_webp_lossy_lossless_extended_originals_reach_real_decoder`, `test_webp_exact_side_and_pixel_boundaries_can_decode`: настоящий lossy/lossless/extended/alpha/metadata decode, original hash и точные лимиты; `test_bounded_webp_headers_do_not_replace_full_pixel_validation`: complete safe headers не пропускают отсутствующие compressed pixels |
| A04/A07 worker | Два новых `test_invalid_input_is_terminal_before_storage[webp_pixels/webp_canvas]`: реальный DB Job DEAD/FileObject FAILED с INVALID_INPUT, attempt_count=1, никакого PUT/retry, Message сохранён. Их исполнение требуется в итоговом штатном PostgreSQL/S3 CI, local unit результат не заменяет этот gate |

Локально в pinned Python 3.13.15 / Pillow 12.3.0 / libwebp 1.6.0: 96 media unit,
288 всех non-integration PASS; Ruff/check/format и strict mypy 40 backend files PASS.
Ранний новый negative VP8L test ошибочно считал uniform stream с изменёнными dimensions
невалидным. Исправлены bytes fixture: убраны compressed pixels при сохранённых
complete headers. Assertion INVALID_INPUT сохранён; защитные проверки не ослаблены.

C0 явно принимает реализационное упрощение §9.4: bounded RAM originals вместо
private temporary disk file. Input cap 10 MiB не является total process-memory cap;
decoder allocations имеют отдельные dimension/concurrency guards. Один decoder
slot и два S3 slots удерживаются до реального завершения, включая cancellation;
каноническое постоянное хранение — только S3. Это не отмена WebP blocker и не новый scope.

### Конечные gates и следующее действие

Этот единый substantive fix/receipt commit обновляет register/handoff/contract,
сохраняя историю. Свой будущий SHA и результат ещё не исполненного final CI он
не выдумывает. **C0 ведёт один final receipt в PR #19**: exact head/tree/tested merge
и его parents, полный CI именно итогового head, фактические C8 finding/closure и
границы artifact evidence. Повторный документационный commit ради записи SHA
предыдущего не нужен. Никакой Ready/merge по одному старому green run.

1. C0 завершает targeted C8 по изменённой области и проверяет итоговые foundation/
   browser jobs, оба scripts/clean-source gates и реальные PostgreSQL/S3 cases.
   После всех PASS снимает Draft и даёт пользователю ссылку на обычный merge commit.
2. Пользователь сливает только готовый PR #19 через **Create a merge commit**.
   C0 проверяет actual merge commit/tree/parents и отдельный **push/main CI**.
3. Только после этого C0 принимает M2.2 в LOCAL/TEST и выдаёт одну M2.3 от точного
   принятого main. Ни API, ни UI, ни живой Telegram этим review не приняты.

Граница A07/A08 и применимых A02/A04/A06/A12 — controlled provider + настоящий
private LOCAL/TEST S3 + внутренний owner service. 15 browser journeys — прежняя
M1 regression; A01/A09/A10/A11 для Telegram/API/UI остаются следующим частям.
Миграция 0006 и SDK/image pins — в [runbook](../runbooks/M2_STORAGE_LOCAL_TEST.md).
Новых paid/cloud ресурсов, owner upload/derivatives/CDN, AI или M3 не добавлено.

### Telegram smoke — внешняя подготовка

По сообщению пользователя готовы test bot с Business/Secretary Mode и Owner/Client;
TG_BOT_TOKEN и отдельный TG_WEBHOOK_SECRET находятся в менеджере паролей. Секреты
не нужны для M2.2 и не передаются в чат/PR. Binding/rights, runtime injection,
тестовый HTTPS endpoint и живой A11 пока не проверены. Конкретное безопасное
поручение C0/C6 для deployment выдаётся в M2.3; платные ресурсы требуют предложения
с точной ценой до подключения. Отсутствие внешнего доступа не блокирует private-S3 CI.


## История — поручение и передача C6/C2/C3 M2.2 до C0 review / 2026-09-21

**M1.1–M1.3 и M2.1 VERIFIED в принятых LOCAL/TEST границах.
M2.2 REVIEW: реализация и runner evidence переданы, C0/C8 ещё не приняли.
M2.3/M2.4 TODO; весь M2 IN_PROGRESS.** Реализацию подготовил C6
с предметным участием C3 (media/provider) и C2 (DB/migration); следующий gate —
C0 и независимый scoped C8 review. M1/M2.1 не повторять.

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

### Передача C6 с участием C2/C3 — M2.2 implementation

Продолжен [Draft PR #19](https://github.com/Elefesys/ai-service-manager/pull/19),
coordination commit `c4ad360e482f47a30e6f0756a13e6ce1cf68def4` сохранён. C2 реализовал
0006, DB capabilities/backfill/constraints и DB migration tests; C3 — controlled
provider, decoder, FETCH/cleanup, worker dispatch и crash/late-PUT tests; C6 —
private S3, owner service, config/lifecycle/Compose, signed HTTP tests и общие gates.
Это участие авторов, не независимый C8 review.

Реализован полный controlled путь §9. SDK `boto3==1.43.98`, decoder
`pillow==12.3.0`, typing `boto3-stubs[s3]==1.43.98`; все прежние external package
blocks/hashes в lock сохранены. Два новых MinIO image pins — официальный Quay registry;
пять прежних pins сохранены. Настройка и ограничения —
[M2_STORAGE_LOCAL_TEST](../runbooks/M2_STORAGE_LOCAL_TEST.md).

[Implementation CI 35604791065](https://github.com/Elefesys/ai-service-manager/actions/runs/35604791065)
**SUCCESS** на обычном GitHub Linux runner: 220 non-integration, **303 real
PostgreSQL/S3** (259 прежних + 44 новых), 60 frontend и 15 прежних M1 browser
cases PASS. `sh scripts/ci.sh`, `sh scripts/test_browser.sh`, оба clean-source
gate, clean/repeated/full downgrade/upgrade и 0005-data cycle, generated contracts,
wheel/frontend reproducibility и HTTP/worker/scheduler smoke PASS. Новых unit cases
28. Локально Docker отсутствует; mock/collection не используются как DB/S3 evidence.

Итоговая дельта после этого run: данный implementation receipt/runbook и сохранение
полных прежних package blocks в narrow lock (versions/hashes не меняются). Точные
final head/tree/tested SHA, CI URL и artifact digest фиксируются в PR receipt после
проверки итогового commit; отдельного SHA-only документационного коммита не нужно.

| Критерий | Конкретные tests/assertions M2.2 |
|---|---|
| A02/A04/A06/A07 | `test_image_planning_rollback_is_one_transaction`, `test_concurrent_image_projection_dedupe_retains_bytes_and_fingerprint`: откат Message/FileObject/FETCH вместе; concurrent exact replay оставляет один набор, original bytes/projection hash неизменны. `test_source_is_canonical_despite_forged_claim_fields_and_disconnect`: source только из DB relations, caller Workspace/connection/file fields не дают полномочий |
| A07 validation | `test_m2_2_media.py`: JPEG/PNG/static WebP, original hash/EXIF/dimensions; malformed/unsupported, truncated container/pixels, animated PNG/WebP, CRC, actual byte cap, exact side/pixel limits и oversized dimensions до pixel allocation. False provider metadata игнорируется; URL остаётся opaque reference. `test_invalid_input_is_terminal_before_storage`: пять DB/worker cases без PUT |
| A07 private storage | `test_original_roundtrip_validated_manifest_and_private_signed_http` (JPEG/PNG/WebP): actual MIME/size/hash/dimensions, S3 checksum, exact original bytes через signed HTTP GET; PENDING denied, TTL ровно 60 s, UUID filename/private-no-store, anonymous GET/LIST/PUT и tampered signature denied. `test_s3_checksum_conditional_put_and_runtime_privilege_boundaries`: server-side checksum mismatch, conditional overwrite, чужой bucket/admin/outside prefix denied |
| A08/A07 read | `test_live_owner_relation_workspace_role_and_failed_file_negatives`, `test_exact_owner_relation_live_role_revoke_and_disconnect`: Workspace A/B, неверные Conversation/Message/FileObject внутри Workspace, ADMIN/PROVIDER/revoke/downgrade, PENDING/FAILED denied; другой собственный диалог и disconnected history разрешены. `test_revoke_denies_new_grant_existing_bearer_expires_at_real_s3`: прежняя bearer URL работает после revoke, новая не выдаётся, после реальных 60 s S3 отвергает прежнюю |
| A08 DB/worker boundary | `test_file_physical_rls_and_capability_privileges`, `test_raw_manifest_validation_cannot_be_bypassed`, `test_typed_message_job_file_foreign_keys_reject_forged_relations`, `test_file_fetch_transaction_xid_and_claim_lease_guards`, `test_file_guards_reject_cross_task_and_owner_worker_nesting`: FORCE RLS/grants, composite FK, strict raw JSON, fake/stale claims, XID/task/owner-worker guards. `test_fetch_roundtrip_no_provider_or_s3_io_with_held_transaction`: реальные provider/S3 calls без занятой DB connection |
| A04/A07 recovery | `test_prepare_intent_replay_manifest_binding_and_fenced_finalize_ack`, `test_lost_finalize_ack_reads_winner_without_repeat_provider_or_put`, `test_lost_prepare_ack_never_authorizes_put_and_retries_new_key`: exact canonical winner после ACK loss, ни повторного PUT, ни PUT без подтверждённого prepare. `test_actual_process_death_intent_put_ready_and_restart`: настоящий дочерний process exit после intent/PUT/READY. Retry/exhaustion tests: пять claims/новых keys, Message сохраняется, FileObject FAILED/Job DEAD, все orphan intents ABANDONED |
| A04/A07 cleanup | `test_late_put_after_first_delete_remains_durably_cleanable` (до/после нового READY), `test_cancelled_worker_sync_put_arrives_after_cleanup_and_new_ready`: реальный поздний PUT, включая sync boto3 после cancellation, tombstone остаётся, повторный DELETE убирает только старый key. `test_cleanup_outage_reclaim_stale_token_and_winner_safety`, `test_retry_new_key_stale_finalize_and_durable_cleanup_reclaim`, immutability test: outage/reclaim/stale token, bounded retry, winner и manifest неизменны |
| A12 и сохранённые A02/A04/A06/A08 | `test_0005_exact_data_backfill_repeat_and_test_downgrade_reupgrade`: text/image/disconnected image, fallback correlation, exact Message IDs/content/fingerprints, billing/receipts/UNKNOWN; repeat upgrade и disposable TEST downgrade/re-upgrade без external I/O. Все прежние M1/M2.1 SEND UNKNOWN/crash/no-resend, tenancy/auth/billing, contracts и browser checks остаются в полном suite |

Совместимые изменения старых проверок сохраняют их защитные assertions:

| Старый path | Причина изменения |
|---|---|
| `tests/test_foundation.py` | Current database revision теперь 0006; frozen schema revision 0003 остаётся прежней |
| `tests/test_postgres.py` | Exact closed inventory дополняется ровно `app.file_objects` и `platform.file_object_uploads` |
| `tests/test_tenancy_postgres.py` | Exact table/function inventory включает новые file capabilities и закрытые helpers; прежние RLS/grants/SQLSTATE assertions сохранены |
| `tests/test_m2_1_postgres.py` | Image fixture теперь создаёт FETCH Job; явно завершает его INVALID_INPUT при отсутствии registered bytes и проверяет один file/job. Ordered fixture teardown удаляет uploads → receipts/jobs → files → прежнюю цепь в одной transaction, без CASCADE/отключения FK; прежние projection/fingerprint/assertions сохранены |

Первый runner 35603278055 остановился до backend/DB/S3 checks на недоступном
Docker Hub `minio/mc`; browser job и его clean-source PASS. Исправлена только
registry ссылка новых storage images на официальный Quay, прежние pins не тронуты.
Это инфраструктурный failure до исполнения новых tests, не доказательство их PASS.

Run 35603841495 подтвердил оба Quay digests, 220 unit и 301/303 real PostgreSQL/S3
cases, 60 frontend и 15 browser PASS. Два новых test defects исправлены без изменения
production capabilities: membership downgrade ожидает owner row lock (проверяется
через реальную blocked DB session, затем новый ADMIN/revoked read denied); pinned
MinIO возвращает `XAmzContentChecksumMismatch`, поэтому test требует именно этот
код/HTTP 400 и отсутствующий объект, а не AWS `BadDigest`. Отказы, fencing и прежние
assertions не удалены. После подтверждения pins временный lookup release tags убран;
обычный CI снова использует только закреплённые digests.

Ограничения: controlled synthetic provider, LOCAL/TEST S3, внутренний owner service.
Нет Telegram/webhook, owner HTTP/OpenAPI/UI, paid infrastructure или M3. Новые
private object grants не являются M2.3/4 E2E; 15 M1 browser journeys — regression.
C0 acceptance, независимый scoped C8 review, merge и actual main CI ещё предстоят;
PR остаётся Draft, M2.2 не INTEGRATED/VERIFIED, M2.3 не начинается.

### Telegram smoke — текущая внешняя граница

Со слов пользователя готовы test bot, Business/Secretary Mode, Owner/Client accounts;
TG_BOT_TOKEN и отдельный TG_WEBHOOK_SECRET сохранены в менеджере паролей.
Секреты не получены и не требуются для M2.2. Runtime injection, connection binding/
rights, тестовый HTTPS endpoint и живой A11 ещё не проверены. C0/C6 дадут конкретную
безопасную инструкцию для тестового deployment при M2.3; tokens не присылать в чат/PR.
LOCAL/TEST storage не требует облачного аккаунта/оплаты. Платную инфраструктуру
предлагать только с конкретной ценой до подключения; отсутствие её не блокирует M2.2.


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
