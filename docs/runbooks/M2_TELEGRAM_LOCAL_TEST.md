# M2.3/M2.4 — Telegram и переписка Console в LOCAL/TEST

Контракт: [M2_CONTRACT §10](../tasks/M2_CONTRACT.md#10-m23-telegram-api--принято-c0c2c3c1-2026-09-21).
Статус ведётся только в [TASK_REGISTER](../TASK_REGISTER.md). Этот runbook готовит
внешнюю проверку A09/A11 через owner API и Console (раздел 5.1).
Наличие файла, deterministic tests или `SENT` не доказывает получение ответа клиентом.

## 0. Когда и кто готовит стенд

Этот шаг нужен **сейчас для завершения M2**, после принятия кода и отдельного main CI.
Implementation Plan §§6–7 и Roadmap M2 требуют реальную тестовую Telegram переписку.
Полный production rollout относится к последующей готовности релиза; здесь только
ограниченный test runtime с тестовыми Owner/Client.

C0 ведёт выбор и приёмку; C6 готовит/настраивает runtime, DNS/HTTPS и точные действия
оператора, C3 проверяет Telegram connection. Владельцу проекта не нужно самостоятельно
выбирать поля/env/SQL или собирать сценарий из нескольких документов. При отсутствии
доступа агента к host оператор выполняет предоставленные команды и возвращает
non-secret результаты; account/billing/DNS права и ввод секретов остаются у владельца.

Владелец подтвердил **подготовку всего с нуля**, предпочтение основного .ru и ещё
одного международного домена для будущего расширения. **Бюджет принят 2026-09-27**,
домены — `clientmanagerai.ru/.com`. **2026-09-30 принят smoke на .com**, как только
его работоспособность подтверждена; .ru остаётся будущим основным доменом.
Токены/passwords не запрашивать. Bot/Owner/Client и
два Telegram секрета уже подготовлены, повторять эту работу не нужно.

Следующие разделы предполагают готовые host/DNS/TLS. Их наличие в runbook — инструкция,
а не утверждение, что внешняя инфраструктура уже развёрнута. Exact accepted source и
статус внешней проверки берутся из единственного активного M2_HANDOFF/TASK_REGISTER.

### 0.1. Предложение стенда с нуля — 2026-09-24

**Вариант принят владельцем 2026-09-27; платный runtime ещё не создан.** Один Linux host в
Yandex Cloud, регион Россия, исходно zone `ru-central1-a`, Ubuntu24.04 LTS/x86_64,
обычная непрерываемая VM `standard-v3` Intel Ice Lake: **2 vCPU/100%,8 GiB RAM,
60 GiB network-ssd и один static public IPv4**. Это стартовая оценка для одного
тестового подключения и текущих Docker builds; достаточность на этом host ещё не
измерена. Параметры API/worker/PostgreSQL/MinIO берутся из принятого Compose.
Проверка builds/health/resources до подключения Telegram входит в работу C6.

История выбора 2026-09-27: managerai.ru/.com заняты; выбрана свободная при проверке
пара clientmanagerai.ru/.com, корзина 200 ₽ +1560 ₽ на первый год. Автоматически
добавленный Optimo исключён. Это историческая проверка корзины, не текущий статус.
По сообщению владельца и ответу поддержки 2026-09-30 **.com зарегистрирован, NS Timeweb
установлены**; **.ru ожидает проверки администратора/ЕСИА**. Независимая публичная
DNS/HTTPS-проверка пока не выполнена. Повторно покупать домены или вводить паспортные
данные в чат/PR не требуется; обращение Timeweb продолжает сам владелец.

**Принятая замена тестовых адресов от 2026-09-30:**

| Назначение | Прежний план | Новый принятый smoke hostname |
|---|---|---|
| Console/API/webhook, единственный auth origin | console.telegram-test.clientmanagerai.ru | console.telegram-test.clientmanagerai.com |
| Private signed files | files.telegram-test.clientmanagerai.ru | files.telegram-test.clientmanagerai.com |

Две A-записи направляются на один будущий static IPv4 после готовности host; HTTPS
обязателен. В примерах §2–6 `console.telegram-test.example.net` заменяется на
`console.telegram-test.clientmanagerai.com`, `files.telegram-test.example.net` — на
`files.telegram-test.clientmanagerai.com`. Runtime env, точный Origin/CSRF/CORS,
Storage public endpoint, TLS names и webhook URL согласуются с этой парой. Контракт
одного auth origin сохраняется: обе зоны одновременно не включать, wildcard/shared
cookie domain не добавлять. .ru остаётся предпочтительным будущим основным доменом;
перенос после smoke не выполняется автоматически. Это не смена Yandex RU/cloud ADR.

Публичные cloud-цены проверены 2026-09-24, корзина выбранной пары — 2026-09-27;
обычные свободные имена, без покупки у текущего владельца/премиум-цены. При изменении
имён или стоимости перед оплатой зафиксировать отличие; hosting/дополнения не приняты.

| Ресурс | Ставка | Расчёт |
|---|---|---|
| Yandex2×100% vCPU Intel Ice Lake | 1,24 ₽/vCPU·час | 1785,60 ₽/720 часов |
| Yandex8 GiB RAM | 0,33 ₽/GiB·час | 1900,80 ₽/720 часов |
| Yandex60 GiB network SSD | 0,0199 ₽/GiB·час | 859,68 ₽/720 часов |
| Один активный public IPv4 | 0,26352 ₽/час | 189,73 ₽/720 часов |
| **Runtime всего, с НДС** | **6,57752 ₽/час** | **4735,81 ₽/30 суток; 1105,02 ₽/7 суток** |
| Timeweb clientmanagerai.ru | 200 ₽ первый год | Текущее продление от399 ₽/год |
| Timeweb clientmanagerai.com | 1560 ₽ первый год, акция | Текущее продление от1810 ₽/год |
| **Два домена** | **1760 ₽ первый год** | **От2209 ₽/год по текущим ценам продления** |
| DNS Timeweb, тариф «Парковка»; Let's Encrypt | 0 ₽ | Отдельный hosting/платный SSL не требуется |

Итого первый месяц runtime + год двух доменов: **6495,81 ₽**. 31 день runtime —
4893,67 ₽. В расчёте исходящий трафик укладывается в первые100 GiB/месяц Yandex;
гранты/пробный период не вычитаются. Это плановая оценка, не фиксированный счёт или
автоматический spending cap. Первый период — 30 суток; C6 контролирует фактическое
потребление и возвращает владельцу дату/стоимость дальнейшего удержания стенда.
Остановка VM убирает compute charge, но SSD и зарезервированный IP продолжают
тарифицироваться; idle static IPv4 —0,6039 ₽/час. Не удалять durable dataset, volume
или pending updates ради прекращения оплаты без отдельного решения владельца.

Источники цен: [Yandex Compute, официальный опубликованный Markdown](https://github.com/yandex-cloud/docs/blob/master/md-docs/compute/pricing.md),
[Yandex VPC](https://yandex.cloud/ru/docs/vpc/pricing),
[домены Timeweb](https://timeweb.com/ru/services/domains/),
[бесплатный DNS без hosting](https://timeweb.com/ru/services/hosting/dns/),
[Let's Encrypt](https://letsencrypt.org/getting-started/).

Один host/PostgreSQL/MinIO сохраняет уже принятый disposable LOCAL/TEST профиль с
synthetic данными. Это не смена ADR137/138/142/143/243: production managed PostgreSQL,
private Object Storage и изоляция окружений остаются принятыми решениями. Подготовка
production/Pilot не добавляется к существующим A09/A11.

### 0.2. Последовательность C6 и действия владельца

1. **M2-ENV-02-STORAGE-IMAGES выдана C6; M2-ENV-01 recovery пока BLOCKED.**
   C0 принял диагноз C6 и явно разрешил новую упаковку двух exact official release
   binaries вместо недоступных identical OCI artifacts. Версии сохраняются; это
   новые image bytes с новой приёмкой. Девять разрешённых paths, binary SHA-256,
   signature key/provenance, runtime compatibility и DoD — в единственном активном
   [handoff](../tasks/M2_HANDOFF.md). CI36717840363 FAILURE подтверждён C0 по обоим
   logs; PG/S3/browser не исполнились, оба clean-source gates SKIPPED.
   C6 готовит два Dockerfile/input lock и отдельный branch-push build/verify/publish
   workflow; основной CI/Compose/private bootstrap/assertions сохраняются.
   Целевые packages: ghcr.io/elefesys/asm-minio и ghcr.io/elefesys/asm-mc.
   Первичный private push разрешён только job-scoped GITHUB_TOKEN; PAT не нужен.
   После готовности конкретных проверенных artifacts C0 даст владельцу URLs и одно
   действие Package settings → Change visibility → Public. Public package нельзя
   затем вернуть в private; до проверки состава такую операцию не выполнять.
   Сейчас действия владельца с registry не нужны. Private push не является
   восстановлением anonymous pull. GHCR container storage/traffic по официальным
   условиям на2026-09-30 бесплатны; Actions и существующие лимиты учитываются отдельно,
   billing/платные планы не менять.
   Затем — свежий anonymous pull обоих @sha256 без cache, два storage pins/refs,
   полный final-head CI обоими прежними scripts и clean-source gates, реальные
   PostgreSQL/S3/browser/private-file/UNKNOWN checks и независимый scoped C8.
   Head/tree/CI — в PR22 receipt без SHA-only commits. Нужный операторский шаг
   публичности блокирует только public pull/final gates: все независимые build/
   signature/runtime проверки C6 завершает до передачи. Registry task не зависит
   от домена, bot token или paid host. VM до C0 приёмки полного CI не создавать.
2. **Параллельно владелец продолжает существующий тикет Timeweb.** .com заявлен
   зарегистрированным, .ru ждёт сверки данных; повторная покупка не нужна. Для smoke
   достаточно работоспособного .com — ждать готовности .ru не требуется. Перед
   переключением live режима C6 проверяет публичное делегирование .com, фактические
   A-records обоих subdomains и доверенный TLS, а не только плашку панели регистратора.
   Когда C0 примет registry/CI recovery, выдаётся точный следующий account/billing/host
   шаг в Yandex Cloud; наличие доступа агента заранее не предполагается. Не просить
   пароли, паспортные данные или Telegram secrets в чат/PR.
3. **После C0 приёмки M2-ENV-01, C6 в разрешённом Yandex TEST folder:** создаёт
   ровно указанную VM/диск/IP после сверки итоговой цены. Настраивает non-root operator, SSH key admission, Docker
   Engine + Compose, синхронизацию времени. SSH22 — только с operator IP, HTTPS443 —
   публично; TCP80 нужен только для ACME HTTP-01. API8000/frontend8080 остаются loopback,
   PostgreSQL/MinIO9000/9001 не публикуются отдельными host ports. Исходящий HTTPS к
   Telegram, DNS, ACME и registry/dependency endpoints нужен для принятого build/runtime.
4. **C6 в DNS:** добавляет две A-записи выше на static IPv4, проверяет resolution снаружи.
   Не добавляет неподтверждённую AAAA-запись или wildcard. .com — единственная
   тестовая Console; .ru параллельно не включает. Точные записи предоставляются
   владельцу одной таблицей, если он вносит их сам.
5. **C6 на host:** выпускает бесплатный TLS для двух точных имён через host Certbot
   `certonly --standalone`/HTTP-01, настраивает renewal и проверяет dry-run. Использует
   прежние filenames/owner/modes §3; renewal deploy hook обновляет private копии и
   reload существующего ingress. Это настройка host, не новый image/plugin в репозитории.
   [Официальная процедура Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#standalone).
   Точные команды с выбранными именами выдаются в этом runbook до выполнения; их запуск
   и успешный TLS пока не заявлены. Если агент не имеет доступа, владелец получает один
   последовательный блок команд с non-secret ожидаемыми результатами.
6. **Далее §2–6 этого же runbook:** exact accepted implementation checkout, private
   secrets непосредственно от владельца, preflight/binding/setWebhook и Console live
   scenario. C6 возвращает sanitized runtime/DNS/TLS/billing receipt; C3 — фактические
   connection/rights/Client receipt. Только C0 принимает live A09/A11.

## 1. Конкретное окружение и предварительные условия

После выполнения §0.2 выбран один вариант: **доступный оператору Linux host с Docker
Compose, двумя DNS именами и публично доверенными TLS сертификатами**. На нём отдельный
Compose project `asm-telegram-test`; только тестовые bot/Owner/Client и новый
synthetic Workspace. Это изолированный LOCAL deployment (`asm_local`), не production.
Процедуры Python также проверяют отдельный TEST target `asm_test`, если оператор
предоставляет его явным окружением. Существующую browser TEST fixture не переиспользовать.

Нужны заранее:

- Один точный **принятый implementation SHA из PR receipt**, не coordination/base SHA.
  Отдельный checkout этого SHA и штатные успешные CI/gates на принятом head.
- Non-root operator account с разрешённым доступом к Docker. Свои
  `console.telegram-test.example.net` и `files.telegram-test.example.net`:
  заменить оба example имени во всех примерах ниже на свои. DNS обоих имён ведёт
  на выбранный host; TCP443 доступен браузеру и Telegram. Исходящий HTTPS к
  `api.telegram.org` доступен API/worker/operator. Часы host синхронизированы.
- Готовые certificate chains и private keys для обоих имён из §0.2. Принятый
  бюджет не является фактом выпуска TLS, регистрации DNS или создания runtime.
- Независимо подтверждённые expected bot numeric ID и **Owner user ID** из
  доверенного operator/account context. Первый попавшийся update/connection ID
  не является подтверждением Owner. Bot token и отдельный webhook secret уже
  находятся у оператора; передавать их в чат/password-manager connector не нужно.

Если host/DNS/TLS/runtime доступа нет, результат **LIVE BLOCKED: runtime/HTTPS**.
Это блокирует только внешний smoke; реализация и HTTP/PG/S3 tests продолжаются.
Обычный loopback Compose сам по себе не internet deployment. Платную альтернативу
можно рассматривать только после отдельного предложения конкретной стоимости.

## 2. Exact code и непосредственная инъекция секретов

В отдельном checkout оператор подставляет принятую 40-символьную SHA:

```sh
export ASM_TELEGRAM_ACCEPTED_SHA='<accepted-40-character-implementation-SHA>'
test "$(git rev-parse HEAD)" = "$ASM_TELEGRAM_ACCEPTED_SHA"
test -z "$(git status --porcelain --untracked-files=all)"
python3 scripts/init_local.py
umask 077
test -e .env.telegram || install -m 600 /dev/null .env.telegram
chmod 600 .env.telegram
mkdir -p .env.telegram.tls
chmod 700 .env.telegram.tls
```

Оператор редактирует `.env.telegram` локально своим editor и вставляет значения
из password manager непосредственно в этот файл. Не вводить секреты в аргументы,
shell history, `set -x`, `docker compose config` без `-q`, issue/PR, log или artifact.
`.env` и `.env.*` уже исключены и из Git, и из Docker build context; не ослаблять
эти правила. `init_local.py` сохраняет существующие LOCAL PG/S3 credentials.
Перед использованием `.env.telegram` должен быть обычным файлом владельца,
не symlink, с mode0600. Deployment secret store может дать те же runtime variables.
Secret values в Compose env file заключать в single quotes, чтобы `$` в пароле
не был interpolation; это файл Compose, не shell script. Перед первым запуском:

```sh
python3 - <<'PY'
import os
import stat
value = os.stat('.env.telegram', follow_symlinks=False)
if not (stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid()
        and stat.S_IMODE(value.st_mode) == 0o600):
    raise SystemExit('TELEGRAM_SECRET_FILE_NOT_PRIVATE')
print('TELEGRAM_SECRET_FILE_PRIVATE')
PY
```

Минимальное содержимое `.env.telegram` (пустые secret/ID поля заполнить локально):

```dotenv
ASM_TELEGRAM_ENABLED=true
TG_BOT_TOKEN=''
TG_WEBHOOK_SECRET=''
ASM_TELEGRAM_EXPECTED_BOT_ID=
ASM_TELEGRAM_WEBHOOK_URL=https://console.telegram-test.example.net/webhooks/telegram
ASM_TELEGRAM_CONSOLE_HOST=console.telegram-test.example.net
ASM_TELEGRAM_STORAGE_HOST=files.telegram-test.example.net
ASM_AUTH_ORIGINS='["https://console.telegram-test.example.net"]'
ASM_STORAGE_ENDPOINT=https://files.telegram-test.example.net
ASM_TELEGRAM_EXPECTED_OWNER_ID=
ASM_TELEGRAM_WORKSPACE_ID=
ASM_TELEGRAM_BUSINESS_ID=
ASM_TELEGRAM_CONNECTION_ID=
ASM_TELEGRAM_BILLING_CONTACT=Synthetic Telegram test owner
ASM_TELEGRAM_BILLING_FROM=2026-09-21T00:00:00+00:00
ASM_TELEGRAM_BILLING_UNTIL=2026-09-28T00:00:00+00:00
ASM_TELEGRAM_SMOKE_ORIGIN=https://console.telegram-test.example.net
ASM_TELEGRAM_SMOKE_LOGIN=telegram.test.owner
ASM_TELEGRAM_SMOKE_PASSWORD=''
ASM_TELEGRAM_SMOKE_CONNECTION_ID=
ASM_TELEGRAM_SMOKE_MARKER=
ASM_TELEGRAM_SMOKE_CONVERSATION_ID=
ASM_TELEGRAM_SMOKE_CLIENT_ID=
ASM_TELEGRAM_SMOKE_REPLY=
ASM_TELEGRAM_SMOKE_KEY=
ASM_TELEGRAM_SMOKE_APPROVAL=
```

Оператор выбирает **явный конечный текущий TEST interval**, меняя обе example даты
до первого setup; при exact repeat сохраняет их. Не подставлять новый `now()` при
каждом повторе. Old M1 `test` plan не обновляется: нужен Workspace **без billing**,
для которого provisioner создаёт фиксированный `test_messaging` revision1,
BOOLEAN `messaging.manual_send=true`, ESSENTIAL, ACTIVE+COMPED/NORMAL и Audit.

Compose читает файл напрямую; не выполнять `source .env.telegram`. Команда-функция
не содержит секретов и сохраняет один и тот же isolated project:

```sh
tgcompose() {
  docker compose --project-name asm-telegram-test \
    --env-file infra/images.lock.env --env-file .env --env-file .env.telegram "$@"
}
test "$(id -u)" -ne 0
export ASM_TELEGRAM_INGRESS_UID="$(id -u)"
export ASM_TELEGRAM_INGRESS_GID="$(id -g)"
tgcompose config -q
tgcompose --profile telegram-operator --profile telegram-smoke \
  build api worker scheduler frontend telegram-operator telegram-smoke
```

Build получает только прежние image pins; TG и owner secrets передаются через
`environment` соответствующих запущенных контейнеров. API/worker/scheduler имеют
только runtime DB identity; migrator credentials есть только у `migrate` и
`telegram-operator`. `telegram-smoke` получает owner API credentials и test IDs,
но не bot token, webhook secret, S3 credentials или migrator URL. `checks` не
получает Telegram secrets; обычный CI не запускает live scripts.

## 3. HTTPS, secure cookie и browser-reachable private storage

Оператор помещает готовые файлы в `.env.telegram.tls/`:
`console.fullchain.pem`, `console.key.pem`, `files.fullchain.pem`, `files.key.pem`.
Private keys принадлежат тому же non-root оператору, mode0600. Profile использует
уже pinned `nginx-unprivileged` `WEB_IMAGE`, ничего не скачивает для выпуска
сертификатов. Он запускается с переданными operator UID/GID, чтобы читать600 keys
в700 directory. Namespace-only sysctl разрешает этому непривилегированному процессу
слушать443 внутри контейнера; host sysctl и root privileges не меняются.
При каждом новом shell повторить non-secret UID/GID exports выше.
Создать локально `.env.telegram.ingress.conf`
mode0600 с заменёнными DNS именами:

```nginx
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
}
server {
    listen 443 ssl;
    server_name console.telegram-test.example.net;
    ssl_certificate /run/tls/console.fullchain.pem;
    ssl_certificate_key /run/tls/console.key.pem;
    access_log off;
    error_log /dev/null;
    client_max_body_size 256k;
    location / {
        proxy_pass http://frontend:8080;
        proxy_set_header Host console.telegram-test.example.net;
        proxy_request_buffering off;
    }
}
server {
    listen 443 ssl;
    server_name files.telegram-test.example.net;
    ssl_certificate /run/tls/files.fullchain.pem;
    ssl_certificate_key /run/tls/files.key.pem;
    access_log off;
    error_log /dev/null;
    client_max_body_size 11m;
    location / {
        proxy_pass http://storage:9000;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header Connection "";
        proxy_request_buffering off;
    }
}
```

`proxy_pass` к S3 не содержит URI suffix: исходные **Host, path и query** остаются
неизменными. Backend/worker подписывают именно `https://files.…`, браузер открывает
тот же URL. Compose network aliases направляют эти же DNS имена на TLS ingress
из контейнеров без замены hostname после подписи и без зависимости от NAT hairpin.
Private bucket policy продолжает запрещать anonymous доступ. DB и S3 admin9001
не публикуются; profile публикует только HTTPS443. Обычные API8000/frontend8080
остаются привязаны к loopback, как прежде.

```sh
tgcompose --profile telegram-live up -d --build api worker scheduler frontend telegram-ingress
tgcompose exec telegram-ingress nginx -t
```

Frontend передаёт **только exact `/webhooks/telegram`** на API; другие `/webhooks/…`
дают404. API выполняет собственные secret/header/body/read guards, ACK после commit.
Default `ASM_TELEGRAM_ENABLED=false` оставляет этот endpoint недоступным.

Единственный auth origin — exact `https://console.…` без path/trailing slash.
Это включает `__Host-asm_session; Secure; HttpOnly; SameSite=lax; Path=/` без Domain.
Не смешивать HTTPS с прежними HTTP origins и не включать proxy-header trust:
существующий frontend→API Host `api:8000` уже предусмотрен auth boundary. Открыть
Console по этому HTTPS имени, а не по loopback. CORS allowlist не расширяется.

## 4. Fresh Workspace, независимая binding и setWebhook после commit

Создать fresh synthetic owner/Workspace/Business **один раз**; пароль вводится
через terminal, не через argv. Никакого billing на этом шаге:

```sh
tgcompose run --rm telegram-operator \
  python scripts/provision_local_auth.py --login telegram.test.owner
```

Сохранить выведенные `workspace_id`, `business_id` в `.env.telegram`, а пароль —
непосредственно в `ASM_TELEGRAM_SMOKE_PASSWORD`. Подтвердить правильную пару
Workspace/Business у оператора. Повтор auth provision не нужен: UNIQUE login
отказывает без частичного создания. Официальное подключение test bot к согласованному
Owner должно уже существовать. Режим Business/Secretary сам по себе не доказывает rights.

Если external connection ID неизвестен, сначала read-only discovery:

```sh
tgcompose run --rm telegram-operator \
  python scripts/provision_telegram_test.py --live --discover
```

Процедура вызывает `getWebhookInfo` и `getMe`, проверяет expected bot ID и отсутствие
чужого webhook. Только когда webhook пуст, выполняется **один bounded getUpdates**:
без offset, negative offset, pagination, ACK или drop. Candidate выбирается только
по независимо подтверждённому Owner ID; несколько разных candidates → отказ.
После выбора `getBusinessConnection` повторно проверяет exact connection и Owner.
Вывод содержит только candidate ID, bot/Owner ID и наблюдённые flags. Записать
`external_connection_id` как `ASM_TELEGRAM_CONNECTION_ID` до следующего шага.
Это позволяет восстановить setup даже после принятого setWebhook с потерянным ответом.

Если ID уже дан оператором, discovery не нужен, но нормальный setup всё равно
выполнит `getMe/getWebhookInfo/getBusinessConnection` и проверит approved Owner:
ID сам по себе не даёт права binding. После установки webhook getUpdates не вызывается.
Чужой webhook не заменяется; его decommission не является частью этой процедуры.

```sh
tgcompose run --rm telegram-operator \
  python scripts/provision_telegram_test.py --live
```

Одна short `asm_migrator` transaction вызывает только reviewed capabilities
`initialize_local_messaging_billing` и `initialize_telegram_connection`, проверяя
DB role и revision0007. Business/Workspace, immutable Owner и route проверяются
в DB. Billing и binding коммитятся вместе; drift/partial/old billing/rebind конфликт
откатывает обе части. Exact repeat — NOOP, история не переносится.

**Только после успешного DB commit** выполняется `setWebhook`: exact HTTPS URL,
отдельный `secret_token`, allowed_updates ровно `business_connection`,
`business_message`, `edited_business_message`, `deleted_business_messages`,
`max_connections=1`, `drop_pending_updates=false`. Script не отправляет сообщения.
Вывод `connection_id` — внутренний UUID; записать в `ASM_TELEGRAM_SMOKE_CONNECTION_ID`.
`is_enabled/can_reply` — фактическое наблюдение, не обещание открытого24h window.

При `TELEGRAM_SETUP_COMMITTED_WEBHOOK_UNCONFIRMED` повторить **тот же setup** с теми же
IDs/contact/interval. DB exact repeat NOOP, setWebhook восстанавливается; не удалять
webhook и не очищать pending updates. Если exact собственный webhook уже установлен,
а connection ID не сохранён, script откажет `CONNECTION_REQUIRED`: восстановить
проверенный ID из operator setup record, не использовать polling/drop для обхода.

## 5. Явный live smoke только согласованного диалога

1. В `.env.telegram` задать уникальный `ASM_TELEGRAM_SMOKE_MARKER`, например случайный
   UUID с префиксом `m23-test-`. **Согласованный Client** отправляет Owner один TEXT
   ровно с этим marker и одну Telegram **photo** с точно таким же caption. Отправка
   как document не подходит. Wait до обработки worker/private FETCH.
2. Запустить только чтение; без conversation/client IDs будут показаны внутренние
   candidate IDs выбранного connection. Произвольный candidate не утверждается автоматически:

```sh
tgcompose run --rm telegram-smoke python scripts/smoke_telegram_test.py --live
```

3. Оператор независимо подтверждает test dialog и записывает его canonical
   `ASM_TELEGRAM_SMOKE_CONVERSATION_ID` и `ASM_TELEGRAM_SMOKE_CLIENT_ID`. Повторная
   read-only команда проверяет connection/business/client relation, точные TEXT
   и photo marker, READY manifest, authenticated read-grant и реальный HTTPS GET
   по исходному signed host/path. Signed URL/cookies/password/text не печатаются.
4. **До отправки** сохранить exact reply text и постоянный idempotency key в том же
   файле, например `ASM_TELEGRAM_SMOKE_KEY=m23-test-reply-<unique-UUID>`. Установить
   `ASM_TELEGRAM_SMOKE_APPROVAL=approved-test-dialog` только после этого согласования.

```sh
tgcompose run --rm telegram-smoke \
  python scripts/smoke_telegram_test.py --live --send-approved-reply
```

Script делает один intention POST `{text}` с прежними cookie/Origin/CSRF и exact
Idempotency-Key, затем bounded reads delivery. Provider напрямую script не вызывает.
Без `--live` network запрещён; без дополнительного send flag новая отправка не
выполняется. Нет auto-send при обычном Compose/CI. `SENT` значит Telegram принял
ответ; Client отдельно подтверждает фактическое получение. UNKNOWN/PENDING/FAILED
не выдаются за успех. Чтение и выдача private grant не зависят от active subscription.

При потере owner POST response **не менять** actor/Workspace/conversation/text/key.
Повтор с исходными значениями распознаёт REPLAY; UNKNOWN не отправляется повторно.
Не создавать новый key ради восстановления. History показывает canonical delivery;
отдельного resend/retry route нет. При rights/window/product запрете новый intent
отклоняется; worker ещё раз проверяет права вне DB перед DISPATCHING.

Browser check обязателен отдельно от container GET. Войти через HTTPS Console,
открыть DevTools и выполнить пример со своими canonical UUID. Он не печатает
подписанный URL или CSRF и не требует S3 CORS для отображения `<img>`:

```javascript
void (async () => {
  const workspace = "<workspace UUID>";
  const conversation = "<approved conversation UUID>";
  const message = "<inbound photo message UUID from owner history>";
  const file = "<READY file UUID from owner history>";
  const session = await fetch("/api/v1/auth/session", {credentials: "same-origin"}).then(r => r.json());
  const path = `/api/v1/workspaces/${workspace}/conversations/${conversation}/messages/${message}/files/${file}/read-grant`;
  const response = await fetch(path, {
    method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": session.csrf_token},
    body: "{}"
  });
  if (!response.ok) throw new Error("TELEGRAM_IMAGE_GRANT_FAILED");
  const grant = await response.json();
  const image = new Image();
  image.onload = () => console.info("TELEGRAM_IMAGE_BROWSER_PASS");
  image.onerror = () => console.info("TELEGRAM_IMAGE_BROWSER_FAILED");
  document.body.append(image);
  image.src = grant.url;
})();
```

Получить photo/file IDs можно authenticated GET history в том же браузере, не
копируя secrets/URL в отчёт. Grant живёт60s; hostname/port/path/query после подписи
не переписывать. После revoke новые grants запрещены, старый bearer URL может
работать до expiry. Telegram original — выбранный PhotoSize, не исходник до
обработки платформой. Нативное сообщение Owner отдельно проверить как durable
ignored event без новой client Message; изменение/revoke rights — как observed
state/отказ нового send, без обещаний по одному флагу Business Mode.

### 5.1. Client text+photo → Owner Console → manual reply → Client receipt

Этот ручной сценарий выполняется оператором **после отдельного разрешения внешних
отправок** в согласованном тестовом диалоге. Текущее поручение M2.4 не разрешает
live sends или расходы. Подготовленные bot/accounts/secrets не заменяют доступный
runtime, DNS и TLS: пока этих условий нет, **live A09/A11 BLOCKED**. CONTROLLED
browser suite ниже проверяет другой, явно ограниченный уровень evidence.

1. На host из разделов 1–4 проверить точный принятый M2.4 implementation SHA и
   чистый checkout; запустить прежний TLS stack и проверить health. Эти команды
   не посылают сообщения Client:

   ```sh
   test "$(git rev-parse HEAD)" = "$ASM_TELEGRAM_ACCEPTED_SHA"
   test -z "$(git status --porcelain --untracked-files=all)"
   git rev-parse HEAD
   date -u +%Y-%m-%dT%H:%M:%SZ
   tgcompose --profile telegram-live up -d --build api worker scheduler frontend telegram-ingress
   tgcompose exec telegram-ingress nginx -t
   ```

   Записать SHA/date и ранее подтверждённые bot/Owner/binding/rights в очищенный
   receipt. Не запускать API send smoke из раздела 5 параллельно этому UI сценарию:
   здесь единственное новое намерение создаёт Owner в Console.
2. Согласованный Client отправляет Owner **новый уникальный текстовый marker** и
   одну Telegram photo с таким же caption. Использовать только synthetic content,
   photo не document. Не считать прежние marker/messages результатом этого запуска.
3. Owner входит в существующую Console по её HTTPS имени и выбирает согласованный
   Workspace. В панели «Переписка» явно обновляет connections/список диалогов,
   выбирает нужный диалог, обновляет историю и находит оба новых сообщения.
   Если нужная строка вне первой страницы, использует загрузку следующей страницы.
   Проверяет полный текст, переносы и правильный Workspace/connection/client relation.
   Observed connection state и время наблюдения не обещают доступного окна/rights.
4. После обработки FETCH изображение имеет READY. Owner открывает его отдельным
   действием в панели: настоящий current-owner grant и браузерный HTTPS GET должны
   показать private photo. Не копировать signed URL в адресную строку, отчёт или
   storage; host/path/query не менять. PENDING/FAILED не засчитывать как image PASS.
   При expiry использовать явную новую выдачу через API, не повторять старую ссылку.
5. Owner вводит один согласованный новый текст ответа и явно отправляет его.
   Принятый202 означает durable intention; сразу после него не заявлять доставку.
   После работы worker Owner обновляет историю. PENDING — очередь, DISPATCHING —
   отправка начата, SENT — **канал принял**. FAILED/UNKNOWN не являются получением
   клиентом; у UNKNOWN нет resend. Client отдельно проверяет получение **этого**
   ответа в Telegram и сообщает результат оператору. Только это подтверждение
   закрывает live Client-receipt часть A11.
6. После подтверждённого202 ошибка чтения исправляется обновлением истории;
   повторного POST для этого намерения нет. Если HTTP результат исходного POST
   неизвестен, сохраняются actor/Workspace/conversation/exact text/key в памяти
   этой страницы: выполнить предложенное session/CSRF recovery и только явный
   повтор исходного намерения в том же контексте. Не менять key или текст ради
   recovery. Hard reload утрачивает это memory-only намерение и выполняет чтения;
   он ничего не отправляет и не доказывает rollback. UNKNOWN остаётся конечным
   неизвестным результатом и после restart/refresh.
7. Проверить явное обновление и переход между страницами без дублей, отсутствие
   прежнего текста/изображения после смены Workspace/logout, доступ к form/image
   controls с клавиатуры и на узком экране. Это UI наблюдения этого запуска;
   полномочия всё равно проверяет сервер. Уже выданный grant может жить до60s,
   а скачанное изображение не отзывается задним числом.

Очищенный receipt содержит SHA/date, среду и согласованный внутренний dialog ID,
результаты text/photo/READY/private browser GET, принятие намерения и последнее
delivery state, **отдельное подтверждение Client**, актуальные observed rights и
ограничения. Не включать текст сообщений, пароли, cookies/CSRF/idempotency key,
provider/signed URLs, raw network export или скриншоты с private content.
Если Client не подтвердил получение, A11 не PASS даже при SENT в Console.

Автоматический CONTROLLED уровень воспроизводится в отдельном disposable checkout:

```sh
sh scripts/ci.sh
sh scripts/test_browser.sh
test -z "$(git status --porcelain --untracked-files=all)"
```

Browser script поднимает PostgreSQL `asm_test` и private MinIO в tmpfs, создаёт
fresh identities через migrator, затем отдельным `browser-runtime` с **только
asm_runtime и runtime S3 credentials** исполняет canonical ingest/Worker/FetchTransfer.
API подписывает loopback `http://127.0.0.1:9000`, runner пишет через `http://storage:9000`;
signed URL не переписывается. CALL/EFFECT counters живут в private temporary files
между заменами runner. Штатный запуск включает прежние M1 и новые messaging journeys,
а cleanup удаляет disposable project/files. Настоящие API/PostgreSQL/MinIO/браузер
здесь используются с CONTROLLED внешним adapter/provider; это **не live Telegram**.

## 6. Evidence и остановка

В sanitized receipt записать exact `git rev-parse HEAD`, UTC дату, LOCAL project,
getMe/Owner match, getWebhookInfo own URL match/pending count без URL token,
observed enabled/can_reply, внутренние IDs, TEXT+photo/private browser GET,
manual API/Console ACCEPTED/REPLAY и delivery, подтверждение Client, native/rights outcome.
Не прикладывать `.env*`, private keys, Compose rendered model, raw payloads,
password/cookie/CSRF, provider URLs или signed URLs. Runbook/tests не являются live evidence.

Локально выполняются обычные `sh scripts/ci.sh` и `sh scripts/test_browser.sh` на
final SHA. В этом срезе `tests/test_m2_3_setup.py` проверяет порядок probe→commit→
setWebhook, no-offset discovery, target/owner/bot/webhook conflicts, atomic wrapper,
secret-safe refusal, opt-in/no-resend и signed-origin checks с injected clients.
Это deterministic evidence, **не real PostgreSQL/Telegram/TLS или browser evidence**;
DB capability integration и полный HTTP/PG/S3 путь проверяются отдельными M2.3 tests.

Остановка сохраняет durable DB/storage и pending Telegram updates:

```sh
tgcompose --profile telegram-live stop telegram-ingress api worker scheduler frontend
```

Во время остановки Telegram может повторять webhook. Не вызывать deleteWebhook,
drop_pending_updates, getUpdates с offset или `down -v` как cleanup. Возобновление
того же проекта и exact binding позволяет продолжить; неизвестные routes503 не
подавляются массовым drop. Удаление disposable dataset — отдельное явное действие
в FK-порядке; downgrade0007 с Telegram rows отказывает до destructive изменений.
Этот runbook не создаёт production backup/restore или завершённый Console A11.
