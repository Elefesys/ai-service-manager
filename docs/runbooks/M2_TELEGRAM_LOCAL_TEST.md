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

### 0.1. История выбора стенда и бюджета — 2026-09-24–2026-10-01

Этот раздел — snapshot планирования до создания VM; текущий host receipt — §0.4.9.

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
установлены**; **.ru ожидает проверки администратора/ЕСИА**. Публичный DNS проверен C0 2026-10-01 через Google DNS-over-HTTPS:
NS .com — ns1.timeweb.ru/ns2.timeweb.ru/ns3.timeweb.org/ns4.timeweb.org;
две будущие A-записи console/files пока NXDOMAIN. NS .ru — NXDOMAIN у этого
resolver, что не определяет внутренний статус ЕСИА/регистратора. TLS ещё не готов. Повторно покупать домены или вводить паспортные
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

Публичные cloud-цены перепроверены 2026-10-01 (ставки не изменились), корзина выбранной пары — 2026-09-27;
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

### 0.2. Текущий порядок — Docker29 mapping correction / 2026-10-05

Текущая owner VM уже на c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14; prepare/verify
PASS, deployment частичный, before PRESENT / after ABSENT. Relay/api/worker running,
Telegram disabled/empty TG. Preflight остановлен несовместимым IPv6 mapping на
Docker29.8.2. Current gate — §0.6.12 и активный M2_HANDOFF: correction C6 REVIEW,
затем full CI/targeted C8 и отдельное guarded recovery от C0. Владелец пока не
выполняет новые VM команды, не повторяет deploy/prepare/snapshot/rollback или
source-access/provisioning/secret entry. Accepted main22993f558c5e7e933c65e9c999933bd2e3ab41c4
не изменён; PR24 Draft, M2 IN_PROGRESS, discovery/setup/webhook/live A09/A11 впереди.

<details>
<summary>История — порядок сразу после интеграции host / 2026-10-02</summary>

### Исторический порядок после интеграции host — 2026-10-02

PR23 merged в22993f558c5e7e933c65e9c999933bd2e3ab41c4; push/main37016012805 SUCCESS.
ENV03 INTEGRATED/VERIFIED с явно записанными TEST ограничениями §0.4.9.
Единственный активный шаг — **M2-LIVE-A09-A11, §0.5**. Source приложения на VM
остаётся80e51c43e31541940f1ccf18b8281adf1a061748, потому что после него изменились
только три docs. Сейчас выполнить только fresh Console Owner §0.5.1; новые TG
secrets/billing/binding/webhook/sends ещё не запускать. Создание host/DNS/TLS не
повторять. .com остаётся единственным smoke origin; .ru отдельно от этой проверки.

</details>

<details>
<summary>История — последовательность подготовки до исполнения host</summary>

### Историческая последовательность C6 и действия владельца

1. **M2-ENV-01/02 интегрированы и VERIFIED.** PR22 merged пользователем,
   actual main **80e51c43e31541940f1ccf18b8281adf1a061748**, tree
   **88ed308b4c56114aa977dcf91204964d9b7348e5** равен принятому final PR tree.
   [Отдельный push/main CI36825583134, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
   SUCCESS: оба jobs checkout actual merge;492 unit/390 PG-S3/111 frontend/27 browser,
   оба штатных scripts/source gates. C8 packaging/pins PASS до merge; новых bytes нет.
   Public packages/две refs приняты; повторный publish/PAT не нужен. Следующий
   **M2-ENV-03-TEST-HOST**, exact scope — активный M2_HANDOFF; первая подготовка §0.4.
2. **.com NS уже подтверждены публично; host/A-records/TLS ещё отсутствуют.**
   .ru продолжает свой отдельный регистрационный путь; ждать его для .com smoke
   не нужно. Account/billing/folder подтверждены владельцем2026-10-01; следующий
   шаг — локальный SSH key/operator IP §0.4.1. Доступ к его
   аккаунту у агента не предполагается; пароли/паспортные данные/ключи в чат не нужны.
   Перед live C6 отдельно проверит оба A и trusted TLS, а не плашку панели Timeweb.
3. **После доступности account/billing и подготовки точной процедуры C6:** C6 в разрешённом Yandex TEST folder создаёт
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
6. **После отдельной приёмки host C0 — live §2–6 этого же runbook:** exact accepted implementation checkout, private
   secrets непосредственно от владельца, preflight/binding/setWebhook и Console live
   scenario. C6 возвращает sanitized runtime/DNS/TLS/billing receipt; C3 — фактические
   connection/rights/Client receipt. Только C0 принимает live A09/A11.

</details>

## 0.3. Принятые storage artifacts и воспроизведение / 2026-10-01

Оба packages **Public** по действию владельца; private repository остаётся private.
Anonymous manifest/config/all-layer HTTP download подтверждён 2026-10-01; новый
Docker pull и реальный runtime подтверждены отдельно [обычный CI 36823298856, attempt 1](https://github.com/Elefesys/ai-service-manager/actions/runs/36823298856). CI на implementation
head **809d44c77b45d86b54750969db5b4a3ec411e0e3**, tree **42a17e82cae204a1f4a8d3f3bc3dcd798fc03cc8**, SUCCESS. Последнее изменение трёх
документов прошло отдельный final PR CI36824246755. PR #22 уже merged;
actual main **80e51c43e31541940f1ccf18b8281adf1a061748**, tree
**88ed308b4c56114aa977dcf91204964d9b7348e5**, [push/main36825583134](https://github.com/Elefesys/ai-service-manager/actions/runs/36825583134)
SUCCESS, оба source gates PASS. Текущий статус — VERIFIED после интеграции;
полная pre-merge история сохранена в [PR #22](https://github.com/Elefesys/ai-service-manager/pull/22).

| Package | Принятый immutable linux/amd64 ref |
|---|---|
| asm-minio /15482993 | ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa |
| asm-mc /15484077 | ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4 |

Build source **f74c240febd963c79408e80600c29d7739e08867**;
[storage run36734267078](https://github.com/Elefesys/ai-service-manager/actions/runs/36734267078)
SUCCESS: exact vendor hash/minisig/negative, два byte-identical no-cache builds,
реальные PG/S3/private policy/CA/shell/SIGTERM и data-preserving volume restart.
Новые OCI artifacts не идентичны прежним Quay bytes; MinIO/mc releases сохранены.
Исходники, лицензии, подписи/key provenance и build tools закреплены в
infra/storage/inputs.lock.json. App/private docs/.git/env/secrets в image не входят.
OCI source label содержит repo URL и build SHA; source content private repo не публикуется.

**Разделение evidence C0:** локально Docker отсутствовал. Поэтому сначала C6
полностью скачал все public OCI blobs без credentials/cache, затем переключены два
pins, после этого неизменный CI на свежих hosted runners выполнил Docker pull и
все runtime checks. Runtime gate сохранён до acceptance/merge; HTTP download не
выдаётся за запуск Docker. Receipt SHA-256 **07992f7085ad9826503870ed0984ad469ebbe9d761fb13134ae553f5c1eba211**; 95 747 170 bytes,
оба manifest/config, все шесть layers, exact compressed hashes/sizes/diffIDs,
seven-file allowlist каждого image и оба binary hash/size PASS. C0/C8 отдельно
пересчитали сохранённые bytes. Новых rebuild/publish/workflow изменений не было.

При необходимости воспроизвести pull на новом disposable linux/amd64 host
(это диагностическая инструкция, не дополнительный незакрытый gate):

~~~sh
set -eu
storage_pull_config="$(mktemp -d)"
trap 'rm -rf "$storage_pull_config"' EXIT
export DOCKER_CONFIG="$storage_pull_config"
minio_ref='ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa'
mc_ref='ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4'
if docker image inspect "$minio_ref" >/dev/null 2>&1; then exit 1; fi
if docker image inspect "$mc_ref" >/dev/null 2>&1; then exit 1; fi
docker pull --platform linux/amd64 "$minio_ref"
docker pull --platform linux/amd64 "$mc_ref"
docker image inspect --format '{{.Id}} {{json .RepoDigests}} {{json .RootFS.Layers}}' "$minio_ref" "$mc_ref"
docker run --rm --entrypoint sha256sum "$minio_ref" /usr/local/bin/minio
docker run --rm --entrypoint sha256sum "$mc_ref" /usr/local/bin/mc
~~~

Expected config digests: MinIO
sha256:b7bb806bee433a13f30a01509f324cfc5c764e4a07b11353aa423eda2e995c1d;
mc sha256:85c9b02133dbec707e92450e93ca5a98e139423839b02946583bdd9ddd2cf2f6.
Binary SHA-256: MinIO
7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f;
mc 7a03ba39e158708a9e88f1bf5c346c6651b15c784e4b2c7150b5b5f282f43c28.
Full layer descriptors/diffIDs — receipt PR #22; mismatch
является blocker. Старые pins не возвращать и версии не обновлять автоматически.

Обычная проверка остаётся прежней: в отдельных jobs `sh scripts/ci.sh` и
`sh scripts/test_browser.sh`, после каждого
`test -z "$(git status --porcelain --untracked-files=all)"`.
Основной CI/Compose/bootstrap/assertions сохранены; новый scoped C8 выполнен.
Storage workflow по-прежнему имеет только contents:read в build и временный
packages:write в изолированном publisher; images повторно не публиковались.
Source/ref bindings и полная история разрешённых packaging изменений — в handoff.
VM/DNS/TLS — текущая ограниченная задача C6; webhook/live Telegram — после приёмки host. Все внешние проверки ещё не исполнены.

<details>
<summary>История — прежний public access gate до действия владельца и CI</summary>

## 0.3. Проверенные storage artifacts и public access gate / 2026-09-30

Build/test source **f74c240febd963c79408e80600c29d7739e08867**, tree
**3e742d07440bcd2e4516922d5698ed1aee735db0**;
[run36734267078 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/36734267078)
verify109951705630 и publish109956285144 SUCCESS. Exact final documentation
head/tree — в [Draft PR22 receipt](https://github.com/Elefesys/ai-service-manager/pull/22).
Новые OCI bytes не идентичны прежним Quay artifacts; releases не обновлены.

| Package / ID | Final immutable linux/amd64 ref |
|---|---|
| [asm-minio](https://github.com/users/Elefesys/packages/container/package/asm-minio) /15482993 | ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa |
| [asm-mc](https://github.com/users/Elefesys/packages/container/package/asm-mc) /15484077 | ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4 |

Visibility обоих — **private**, подтверждена pre/post push; anonymous pull receipt
пока отсутствует. Tag source-f74c240febd963c79408e80600c29d7739e08867.
Manifest → config → layers, binary hashes, two-build archive hashes и старые private
tags перечислены в активном handoff. C0 проверяет package целиком перед открытием.

В images входят pinned official curlimages/curl8.19.0 base, exact signed vendor
binary и vendor LICENSE/CREDITS/source/minisig/NOTICE/input lock. Build contexts
созданы по allowlist, приложение/private docs/.git/env/secrets не копируются.
MinIO RELEASE.2025-09-07T16-13-09Z binary SHA-256
7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f;
mc RELEASE.2025-02-15T10-36-16Z binary SHA-256
7a03ba39e158708a9e88f1bf5c346c6651b15c784e4b2c7150b5b5f282f43c28.
Exact source/key provenance, minisign0.12, Buildx0.29.1, BuildKit0.25.0 и полный
input lock — infra/storage/inputs.lock.json. Полные hashes и minisig проверены до
execution; in-image binary hashes совпали; полный второй build byte-identical.

Storage workflow автоматически срабатывает до merge по push четырёх build files
в точную c6/m2-live-smoke; workflow_dispatch main предусмотрен только после
интеграции. Основной CI не заменён. Build имеет contents:read; отдельный publisher
contents:read/packages:write и только временный GITHUB_TOKEN, без исполнения image
code. Artifact11107176489 содержит два Docker archives/input lock/verify receipt;
artifact11106623061 — verify/publish receipts, ZIP SHA-256
224a19ac249afe93515395c7c8c384ca62a8ff24cd61000e120470816d36cf41.
Второй ZIP полностью скачан/проверен C6; первый скачан и проверен publisher.
Retention7days до2026-10-07. Состав/хеши JSON и archives — в handoff.

**Шаг владельца после проверки C0:** в settings **каждого из двух packages выше**
Change visibility → Public. Эта операция необратима по правилам GHCR; private
repository не открывать. C6 не выполнял её. Никаких PAT, новых secrets или Connect
repository для уже успешно опубликованных packages не требуется.

После подтверждения C6 на **новом disposable linux/amd64 GitHub runner**, без
cache restore и без registry login, выполняет следующие команды (пока не исполнены):

~~~sh
set -eu
storage_pull_config="$(mktemp -d)"
trap 'rm -rf "$storage_pull_config"' EXIT
export DOCKER_CONFIG="$storage_pull_config"
minio_ref='ghcr.io/elefesys/asm-minio@sha256:c6c3b418f4b7bbea2f07c4095fc6e59d38ed538a33486f19bb9450a63a6a2efa'
mc_ref='ghcr.io/elefesys/asm-mc@sha256:4da81d17279b9fcdaeee8967c0de4f5d9c7fd589f8022b66e2766b9ac4fe5ce4'
if docker image inspect "$minio_ref" >/dev/null 2>&1; then exit 1; fi
if docker image inspect "$mc_ref" >/dev/null 2>&1; then exit 1; fi
docker pull --platform linux/amd64 "$minio_ref"
docker pull --platform linux/amd64 "$mc_ref"
docker image inspect --format '{{.Id}} {{json .RepoDigests}} {{json .RootFS.Layers}}' "$minio_ref" "$mc_ref"
docker run --rm --entrypoint sha256sum "$minio_ref" /usr/local/bin/minio
docker run --rm --entrypoint sha256sum "$mc_ref" /usr/local/bin/mc
~~~

Полные config/layers сравнить с verify receipt; binary hashes — с lock выше.
Пустой Docker auth config и отсутствие обоих images обязательны, cache-only
результат не принимается. Expected configs: MinIO
sha256:b7bb806bee433a13f30a01509f324cfc5c764e4a07b11353aa423eda2e995c1d;
mc sha256:85c9b02133dbec707e92450e93ca5a98e139423839b02946583bdd9ddd2cf2f6.
Зафиксировать fresh-run pull receipt; затем обновить только STORAGE_IMAGE/
STORAGE_ADMIN_IMAGE в infra/images.lock.env и две storage refs pin_images.sh.
Если меняются recipe/image bytes, нужны новые build/digests/review.

На одном новом final head обычный CI выполняет в своих прежних изолированных jobs:

~~~sh
sh scripts/ci.sh
test -z "$(git status --porcelain --untracked-files=all)"
~~~

~~~sh
sh scripts/test_browser.sh
test -z "$(git status --porcelain --untracked-files=all)"
~~~

Сейчас ci.sh с local-image environment override уже PASS на build SHA, включая
реальные private files/isolation/recovery/UNKNOWN. test_browser.sh reload committed
Quay pins и сохраняет project guard; обход/редактирование script не допускаются.
Полные browser/обычный final-head CI/оба gates остаются обязательными после смены
pins. Обычный CI36734280555 на build SHA FAILURE со старым unauthorized; оба gates
SKIPPED. M2-ENV-01 не закрывать до полного восстановления; C0 организует scoped C8.
VM/DNS/TLS/webhook и live Telegram начинают только по следующему handoff.

</details>

## 0.4. TEST host: процедура и actual receipt / 2026-10-02

**Владелец подтвердил active billing и folder `asm-telegram-test` 2026-10-01.**
Accepted runtime **80e51c43e31541940f1ccf18b8281adf1a061748**, tree
**88ed308b4c56114aa977dcf91204964d9b7348e5**, push/main36825583134 SUCCESS.
Задача M2-ENV-03-TEST-HOST: `c6/m2-test-host`, [Draft PR23](https://github.com/Elefesys/ai-service-manager/pull/23),
сохранить coordination **1f42a617ed64bc6fd4dd573cd5c721d22a7bf256**.
Прежняя account-инструкция выполнена; история сохранена в Git.

**Процедура исполнена владельцем 2026-10-02; результаты и отклонения — §0.4.9.**
Шаги создания ниже сохранены для воспроизведения и анализа, не для повторного
запуска на действующем host. Текущее поручение — верхний активный M2_HANDOFF.
Исправления umask/stdin/PowerShell внесены в текст; это не повторное исполнение
всех команд и не изменение уже установленного renewal hook.
Основной путь: Yandex Console → локальный Windows PowerShell/SSH → Bash на VM.
Доступ агента к account/SSH не предполагается; владелец исполняет готовые шаги.
Бюджет уже принят. Ошибка/existing resource — остановить блок и вернуть C6 marker,
не повторять создание и не перезаписывать существующее. Этот §0.4 приоритетнее
live примеров §2–6: Telegram остаётся выключенным.

### 0.4.1. Первый шаг владельца — локальный SSH key и operator IPv4

В обычном **Windows PowerShell на своём компьютере**:

```powershell
$ErrorActionPreference = 'Stop'
Get-Command ssh.exe, ssh-keygen.exe | Out-Null
$asmKey = Join-Path $env:USERPROFILE '.ssh\asm-telegram-test'
if ((Test-Path $asmKey) -or (Test-Path "$asmKey.pub")) {
    throw 'ASM_KEY_EXISTS: не перезаписывать; сообщить C6'
}
New-Item -ItemType Directory -Force (Split-Path $asmKey) | Out-Null
ssh-keygen.exe -t ed25519 -a 64 -C 'asm-telegram-test-owner' -f $asmKey
if ($LASTEXITCODE -ne 0) { throw 'ASM_KEY_GENERATION_FAILED' }
$asmOperatorIPv4 = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=json').ip
if ([System.Net.IPAddress]::Parse($asmOperatorIPv4).AddressFamily -ne
    [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'IPV4_REQUIRED' }
"SSH_KEY_READY; OPERATOR_CIDR=$asmOperatorIPv4/32"
```

На запрос passphrase задать парольную фразу, сохранить её в своём password manager.
Файл **без `.pub` — private**, никуда не отправлять. `.pub` позднее загружается
непосредственно Yandex. Вернуть C0 только marker и `OPERATOR_CIDR=…/32`.
Если OpenSSH Client отсутствует — вернуть эту ошибку, C6 даст штатную установку.
IP нужен с устройства оператора, не Cloud Shell/VM. Сеть/VPN до SSH не менять;
при смене IP заменить только разрешённый `/32`, не открывать22 для всех.

### 0.4.2. Точные ресурсы в Yandex Console

Выбрать **folder `asm-telegram-test`**. До платных IP/VM готовы key, operator `/32`
и выбранный folder. Создать последовательно через Virtual Private Cloud:

| Раздел | Поля |
|---|---|
| Облачные сети → Создать | `asm-telegram-test-net`; «Создать подсети» выключено |
| Подсети → Создать | `asm-telegram-test-a`; сеть выше; `ru-central1-a`; CIDR `10.73.0.0/24`; DHCP default; без route table/NAT |
| Группы безопасности → Создать | `asm-telegram-test-sg`; сеть выше; только четыре правила ниже |
| Публичные IP → Зарезервировать | `ru-central1-a`; защита от удаления включена; DDoS-опция выключена; без Cloud DNS; записать один IPv4 |

| Направление | Протокол / порт | CIDR | Назначение |
|---|---|---|---|
| Входящий | TCP22 | `OPERATOR_CIDR` из §0.4.1 | Только SSH оператора |
| Входящий | TCP443 | `0.0.0.0/0` | HTTPS |
| Входящий | TCP80 | `0.0.0.0/0` | Временный Certbot HTTP-01 listener |
| Исходящий | Любой / все | `0.0.0.0/0` | DNS/NTP, packages/registry/GitHub, ACME, будущий Telegram |

Не прикреплять default SG: разрешения групп суммируются; пустое поле выбирает default.
Никаких inbound5432/8000/8080/9000/9001/RDP/self-all. На80 приложение не запускается;
между challenges порт не слушается. Outbound proxy/firewall design сейчас не вводится.

Compute Cloud → Виртуальные машины → Создать:

| Поле | Значение |
|---|---|
| Имя / зона | `asm-telegram-test-vm` / `ru-central1-a` |
| Образ | Официальный Yandex Ubuntu24.04 LTS **x86_64/amd64**, без платного ПО; записать actual image ID |
| Своя конфигурация | Intel Ice Lake `standard-v3`,2vCPU,100%,8GiB; обычная **непрерываемая** |
| Boot disk | `asm-telegram-test-boot`, `network-ssd`,60GiB; Console default auto_delete=true, явное ограничение текущего TEST — ниже и §0.4.9 |
| Сеть / подсеть | `asm-telegram-test-net` / `asm-telegram-test-a`; internalIPv4 автоматически |
| PublicIP | «Список» → ранее зарезервированный staticIPv4, не «Автоматически» |
| Security groups | Только `asm-telegram-test-sg` |
| Доступ | SSH-ключ, логин **asmoperator**, ключ `asm-telegram-test-owner` → загрузить свой файл `.pub` |
| Дополнительно | Без service account, Cloud Backup, KMS, ускоренной сети и дополнительных дисков |

**Исправление C0 от 2026-10-02:** первоначальные указания включить защиту удаления
отдельной VM и отключить auto-delete boot disk через Console были ошибочными.
[Instance.Get](https://yandex.cloud/en/docs/compute/api-ref/Instance/get) не имеет
instance deletion-protection, [CLI update](https://yandex.cloud/en/docs/compute/cli-ref/instance/update)
и [Instance.Update](https://yandex.cloud/en/docs/compute/api-ref/Instance/update)
не содержат boot setter. В официальном [Terraform provider source](https://github.com/yandex-cloud/terraform-provider-yandex/blob/master/yandex/resource_yandex_compute_instance.go)
boot_disk.auto_delete имеет ForceNew=true. Общее описание Disks об изменении
параметра не подтверждает безопасную in-place команду для boot disk.

Actual read-only CLI на VM fhm53804pjetng9i46h2 показал **auto_delete=true**.
Решение C0 для этого уже подготовленного синтетического TEST — сохранить работающий
host и явно принять это ограничение, без пересоздания/отсоединения/новой VM или
платного backup. Это **не** защита данных: удаление VM удалит DB/files. IP deletion
protection относится только к адресу. Никакое удаление VM/boot/volumes сейчас не
разрешено; перед будущей заменой требуется отдельный план сохранения/проверки
состояния. При потере DB effects выключены до reconciliation; UNKNOWN не повторять.
Новая VM не создаётся этим решением; production managed DB/files и backup/restore
gates сохранены. Отсутствующий UI checkbox не является ошибкой владельца.

Перед созданием сверить поля и оценку: около **4735,81₽/30 суток** за compute+SSD+IP,
без грантов/доменов, в уже принятом бюджете. Существенное расхождение цены или иной
SKU вернуть C0 до подключения. Оплата начинается с создания. Зафиксировать дату
начала и следующую проверку расходов через30суток; никакого автоматического удаления.

После RUNNING: карточка VM → **Последовательный порт → Исходные данные** → найти
cloud-init **ED25519 host fingerprint** `SHA256:…`. Это ключ сервера, не пользователя.
В локальном PowerShell:

```powershell
$asmPublicIPv4 = Read-Host 'Публичный IPv4 из карточки VM'
if ([System.Net.IPAddress]::Parse($asmPublicIPv4).AddressFamily -ne
    [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'IPV4_REQUIRED' }
$asmKey = Join-Path $env:USERPROFILE '.ssh\asm-telegram-test'
ssh.exe -o IdentitiesOnly=yes -o HostKeyAlgorithms=ssh-ed25519 `
    -i $asmKey "asmoperator@$asmPublicIPv4"
```

На первом запросе `yes` только после совпадения server fingerprint; затем passphrase.
При отсутствии fingerprint в cloud-init — C6 проверяет доверенный источник; не
отключать host-key verification. Timeout: сверить operatorIP/SG, не расширять CIDR.
Changed host key: выяснить причину, не удалять known_hosts вслепую.

### 0.4.3. Ubuntu/Docker — Bash в SSH как asmoperator

```bash
set -euo pipefail
test "$(id -un)" = asmoperator
test "$(id -u)" -ne 0
sudo cloud-init status --wait
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(dpkg --print-architecture)" = amd64
sudo timedatectl set-ntp true
timedatectl show -p NTPSynchronized --value
nproc
free -h
df -h /
```

Если cloud-init возвращает nonzero, остановить установку и передать только
`cloud-init status --long` и `cloud-init schema --system`, без user-data/секретов.
`|| true`, clean/rerun cloud-init и blanket игнорирование warning не разрешены.
Для данного host C0 отдельно проверил единственный datasource warning (§0.4.9);
это не общее разрешение игнорировать любые ошибки следующей VM.

Ожидаются `yes`,2CPU, около8GiB RAM и согласованный диск. Если NTP ещё `no`, дождаться
синхронизации, повторить read-only проверку. Затем официальный Docker apt repository:

```bash
set -euo pipefail
if command -v docker >/dev/null || test -e /etc/apt/sources.list.d/docker.sources; then
  echo EXISTING_DOCKER_REQUIRES_C6_CHECK; exit 1
fi
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 openssl snapd
sudo install -d -m 0755 /etc/apt/keyrings
sudo curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod 0644 /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker asmoperator
exit
```

Войти снова предыдущей SSH командой. `docker info >/dev/null`, `docker version`,
`docker compose version` должны работать без sudo; версии сохранить в receipt.
Группа docker даёт administrative возможности на этом TEST host; других пользователей
в неё не добавлять. SG — внешняя граница, UFW не подменяет контроль Docker ports.

### 0.4.4. Exact private source без write PAT

На VM создать временный **read-only deploy key**, отдельно от ключа входа:

```bash
set -euo pipefail
umask 077
test ! -e "$HOME/.ssh/asm_source_readonly"
test ! -e "$HOME/.ssh/asm_source_readonly.pub"
ssh-keygen -t ed25519 -a 64 -C asm-telegram-test-source -f "$HOME/.ssh/asm_source_readonly"
cat "$HOME/.ssh/asm_source_readonly.pub"
```

Задать passphrase. В браузере private repository → **Settings → Deploy keys → Add**,
title `asm-telegram-test-source`, вставить только показанный public key;
**Allow write access не включать**. Затем в SSH, с pinned official GitHub host key:

```bash
set -euo pipefail
umask 077
test ! -e "$HOME/asm-telegram-test"
test ! -e "$HOME/.ssh/asm_github_known_hosts"
printf '%s\n' 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' > "$HOME/.ssh/asm_github_known_hosts"
export GIT_SSH_COMMAND='ssh -i /home/asmoperator/.ssh/asm_source_readonly -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/home/asmoperator/.ssh/asm_github_known_hosts -o HostKeyAlgorithms=ssh-ed25519'
git init "$HOME/asm-telegram-test"
cd "$HOME/asm-telegram-test"
git config core.autocrlf false
git remote add origin git@github.com:Elefesys/ai-service-manager.git
git fetch --depth=1 origin 80e51c43e31541940f1ccf18b8281adf1a061748
(umask 022; git checkout --detach 80e51c43e31541940f1ccf18b8281adf1a061748)
test "$(stat -c %a .)" = 700
test "$(stat -c %a .git)" = 700
test "$(stat -c %a infra/postgres/bootstrap.sh)" = 644
test "$(stat -c %a infra/storage/bootstrap.sh)" = 644
test "$(git rev-parse HEAD)" = 80e51c43e31541940f1ccf18b8281adf1a061748
test "$(git rev-parse HEAD^{tree})" = 88ed308b4c56114aa977dcf91204964d9b7348e5
test -z "$(git status --porcelain --untracked-files=all)"
printf '%s\n' EXACT_SOURCE_PASS
unset GIT_SSH_COMMAND
```

Исправление umask: private checkout root/.git создаются при077; только checkout
Git-tracked source выполняется с022, иначе container UID не прочитает bind/COPY.
Секреты создаются позднее с077/600/700; рекурсивный chmod всего проекта запрещён.
На существующем host не повторять checkout; выполненная guarded recovery — §0.4.9.

После `EXACT_SOURCE_PASS` владелец удаляет **этот deploy key из GitHub Settings**;
build использует локальный checkout и публичные pinned images. Private key остаётся
вне repo/context; отзыв GitHub доступа важнее удаления локального файла. Ключ входа
на VM сохраняется. Неудачный fetch не повод reset/reclone стенда: C6 разбирает ошибку.

### 0.4.5. Pre-live файлы, DNS и TLS

На VM в отдельном checkout:

```bash
set -euo pipefail
cd /home/asmoperator/asm-telegram-test
umask 077
python3 scripts/init_local.py
python3 - <<'PYENV'
import os
from pathlib import Path
import stat
value = Path('.env').lstat()
assert stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid()
assert stat.S_IMODE(value.st_mode) == 0o600
body = '''ASM_TELEGRAM_ENABLED=false
ASM_TELEGRAM_CONSOLE_HOST=console.telegram-test.clientmanagerai.com
ASM_TELEGRAM_STORAGE_HOST=files.telegram-test.clientmanagerai.com
ASM_AUTH_ORIGINS='["https://console.telegram-test.clientmanagerai.com"]'
ASM_STORAGE_ENDPOINT=https://files.telegram-test.clientmanagerai.com
'''
fd = os.open('.env.telegram', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(body)
os.mkdir('.env.telegram.tls', 0o700)
print('PRELIVE_FILES_CREATED')
PYENV
```

Existing files сохраняются: не повторять этот create block. `init_local.py` сохраняет
прежние DB/S3 passwords. `.env*` игнорируются Git и Docker. TG/owner secrets сейчас
не нужны. Не делать `source .env*`, `set -x`, full `docker compose config`, `env`,
`printenv` или full `docker inspect`. Рабочая функция **для каждого нового SSH shell**:

```bash
cd /home/asmoperator/asm-telegram-test
export ASM_TELEGRAM_INGRESS_UID="$(id -u)"
export ASM_TELEGRAM_INGRESS_GID="$(id -g)"
tgcompose() {
  docker compose --project-name asm-telegram-test \
    --env-file infra/images.lock.env --env-file .env --env-file .env.telegram "$@"
}
tgcompose config -q
```

Timeweb → Домены → `clientmanagerai.com` → DNS:

| Type | Имя относительно clientmanagerai.com | Значение | TTL |
|---|---|---|---|
| A | `console.telegram-test` | staticIPv4 VM | 600s либо ближайшее доступное |
| A | `files.telegram-test` | **Тот же** staticIPv4 | То же |

Не менять NS/MX/apex, не добавлять wildcard/AAAA/parking/proxy. При существующей
конфликтующей записи сначала C6. Из локального PowerShell:

```powershell
Resolve-DnsName console.telegram-test.clientmanagerai.com -Type A -Server 1.1.1.1
Resolve-DnsName files.telegram-test.clientmanagerai.com -Type A -Server 1.1.1.1
Resolve-DnsName console.telegram-test.clientmanagerai.com -Type A -Server 8.8.8.8
Resolve-DnsName files.telegram-test.clientmanagerai.com -Type A -Server 8.8.8.8
```

Ожидается ровно один выбранный IPv4. Resolver timeout проверяется C6 через другой
public resolver/DoH, это не доказательство ошибки домена. TLS — после совпадения A.
Один бесплатный SAN certificate на два имени, host Certbot Snap. В SSH:

```bash
set -euo pipefail
if command -v certbot >/dev/null || snap list certbot >/dev/null 2>&1; then
  echo EXISTING_CERTBOT_REQUIRES_C6_CHECK; exit 1
fi
sudo snap install --classic certbot
sudo /snap/bin/certbot --version
sudo ss -ltnp 'sport = :80'
```

`ss` должен показать только header, без listener. Затем:

```bash
sudo /snap/bin/certbot certonly --standalone --preferred-challenges http \
  --cert-name asm-telegram-test \
  -d console.telegram-test.clientmanagerai.com \
  -d files.telegram-test.clientmanagerai.com
```

E-mail и условия Let's Encrypt вводятся непосредственно в terminal; в receipt e-mail
не нужен. При ошибке challenge C6 проверяет DNS/80; не повторять production issuance
сериями. Certbot временно слушает80, ingress443 при последующем renewal не останавливается.

Root-owned deploy hook: active cert → прежние четыре600 файла в operator700 directory,
затем nginx validation/reload существующего контейнера. Никаких новых repo scripts:

```bash
set -euo pipefail
test ! -e /usr/local/sbin/asm-telegram-cert-deploy
sudo tee /usr/local/sbin/asm-telegram-cert-deploy >/dev/null <<'HOOK'
#!/bin/bash
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
asm_app=/home/asmoperator/asm-telegram-test
asm_tls="$asm_app/.env.telegram.tls"
asm_lineage=/etc/letsencrypt/live/asm-telegram-test
test "${RENEWED_LINEAGE:-$asm_lineage}" = "$asm_lineage"
asm_uid=$(id -u asmoperator)
asm_gid=$(id -g asmoperator)
for asm_dir in /home/asmoperator "$asm_app" "$asm_tls"; do
  test -d "$asm_dir" && test ! -L "$asm_dir"
  test "$(stat -c %u "$asm_dir")" = "$asm_uid"
done
test "$(stat -c %a "$asm_tls")" = 700
for asm_name in console files; do
  for asm_kind in fullchain key; do
    asm_source=fullchain.pem
    if test "$asm_kind" = key; then asm_source=privkey.pem; fi
    asm_dest="$asm_tls/$asm_name.$asm_kind.pem"
    test ! -L "$asm_dest"
    asm_tmp=$(mktemp "$asm_tls/.renew.XXXXXXXX")
    install -o "$asm_uid" -g "$asm_gid" -m 0600 "$asm_lineage/$asm_source" "$asm_tmp"
    mv -fT "$asm_tmp" "$asm_dest"
  done
done
asm_compose() {
  runuser -u asmoperator -- env \
    ASM_TELEGRAM_INGRESS_UID="$asm_uid" ASM_TELEGRAM_INGRESS_GID="$asm_gid" \
    /usr/bin/docker compose --project-name asm-telegram-test \
    --project-directory "$asm_app" -f "$asm_app/compose.yaml" \
    --env-file "$asm_app/infra/images.lock.env" --env-file "$asm_app/.env" \
    --env-file "$asm_app/.env.telegram" --profile telegram-live "$@"
}
if test -n "$(asm_compose ps --status running -q telegram-ingress)"; then
  asm_compose exec -T telegram-ingress nginx -t
  asm_compose exec -T telegram-ingress nginx -s reload
  printf '%s\n' TLS_COPIED_AND_RELOADED
else
  printf '%s\n' TLS_COPIED_INGRESS_NOT_RUNNING
fi
HOOK
sudo chmod 0755 /usr/local/sbin/asm-telegram-cert-deploy
sudo chown root:root /usr/local/sbin/asm-telegram-cert-deploy
sudo install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
test ! -e /etc/letsencrypt/renewal-hooks/deploy/asm-telegram-test
sudo ln -s /usr/local/sbin/asm-telegram-cert-deploy /etc/letsencrypt/renewal-hooks/deploy/asm-telegram-test
sudo /usr/local/sbin/asm-telegram-cert-deploy </dev/null
```

На первом bootstrap ожидается `TLS_COPIED_INGRESS_NOT_RUNNING`. Hook не меняет
source/env и не запускает app. Key material/temporary files никогда не печатает.

### 0.4.6. Exact ingress и запуск

В SSH с function `tgcompose` из §0.4.5:

```bash
set -euo pipefail
cd /home/asmoperator/asm-telegram-test
umask 077
set -o noclobber
cat > .env.telegram.ingress.conf <<'NGINX'
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
}
server {
    listen 443 ssl;
    server_name console.telegram-test.clientmanagerai.com;
    ssl_certificate /run/tls/console.fullchain.pem;
    ssl_certificate_key /run/tls/console.key.pem;
    access_log off;
    error_log /dev/null;
    client_max_body_size 256k;
    location / {
        proxy_pass http://frontend:8080;
        proxy_set_header Host console.telegram-test.clientmanagerai.com;
        proxy_request_buffering off;
    }
}
server {
    listen 443 ssl;
    server_name files.telegram-test.clientmanagerai.com;
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
NGINX
set +o noclobber
python3 - <<'PYPRIV'
import os
from pathlib import Path
import stat
for name in ('.env', '.env.telegram', '.env.telegram.ingress.conf',
             '.env.telegram.tls/console.fullchain.pem', '.env.telegram.tls/console.key.pem',
             '.env.telegram.tls/files.fullchain.pem', '.env.telegram.tls/files.key.pem'):
    value = Path(name).lstat()
    assert stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid()
    assert stat.S_IMODE(value.st_mode) == 0o600
value = Path('.env.telegram.tls').lstat()
assert stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid()
assert stat.S_IMODE(value.st_mode) == 0o700
print('RUNTIME_FILES_PRIVATE_PASS')
PYPRIV
python3 - <<'PYINPUTS'
import os
inputs = (
    'ASM_TELEGRAM_ENABLED', 'TG_BOT_TOKEN', 'TG_WEBHOOK_SECRET',
    'ASM_TELEGRAM_EXPECTED_BOT_ID', 'ASM_TELEGRAM_WEBHOOK_URL',
    'ASM_TELEGRAM_CONSOLE_HOST', 'ASM_TELEGRAM_STORAGE_HOST',
    'ASM_AUTH_ORIGINS', 'ASM_STORAGE_ENDPOINT',
)
for name in inputs:
    if name in os.environ:
        raise SystemExit('EXPORTED_RUNTIME_INPUT_REQUIRES_C6_CHECK: ' + name)
print('PRELIVE_ENVFILE_PRECEDENCE_PASS')
PYINPUTS
tgcompose config -q
tgcompose build api worker scheduler frontend
tgcompose --profile telegram-live up -d --no-build api worker scheduler frontend telegram-ingress
tgcompose exec -T telegram-ingress nginx -t </dev/null
```

Guard до запуска исключает shell overrides над `.env.telegram`, не выводя их значения;
он допускает необходимые INGRESS_UID/GID и ACCEPTED_SHA. При его отказе C6 проверяет
указанное имя, сохраняет нужное private значение и очищает только конфликтующий
export; не запускать stack поверх отказавшего guard.
Не менять image refs, Compose, `ASM_ENVIRONMENT=LOCAL`, asm_local/private local bucket.
Общий CI/browser script на persistent project **не запускать**: его disposable
teardown не подходит сохраняемым volumes. TG остаётся false даже с profile telegram-live:
название profile включает только TLS service, не разрешает webhook/bot execution.

### 0.4.7. Readiness и возврат C0

На VM, с тем же `tgcompose`. При передаче блока через `bash <<'MARKER'`
команды без входных данных получают `</dev/null`: `compose exec -T` отключает TTY,
но по умолчанию всё ещё читает stdin. Python-блоки ниже получают собственный heredoc.
Отсутствие финального marker не считать успехом всего блока.

```bash
set -euo pipefail
tgcompose ps -a
for asm_service in migrate storage-init; do
  asm_container=$(tgcompose ps -a -q "$asm_service")
  test -n "$asm_container"
  test "$(docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' "$asm_container")" = exited:0
done
tgcompose logs --no-color storage-init | grep -F STORAGE_PRIVATE_BOOTSTRAP_PASS
for asm_service in api worker scheduler frontend postgres storage telegram-ingress; do
  asm_container=$(tgcompose --profile telegram-live ps -q "$asm_service")
  test -n "$asm_container"
  test "$(docker inspect --format '{{.State.Running}}:{{.State.OOMKilled}}' "$asm_container")" = true:false
done
tgcompose exec -T api python - <<'PYOFF'
import os
from asm.telegram.config import TelegramSettings
cfg = TelegramSettings()
assert not cfg.enabled and not cfg.token.get_secret_value() and not cfg.webhook_secret.get_secret_value()
assert os.environ['ASM_ENVIRONMENT'] == 'LOCAL'
assert os.environ['ASM_AUTH_ORIGINS'] == '["https://console.telegram-test.clientmanagerai.com"]'
assert os.environ['ASM_STORAGE_ENDPOINT'] == 'https://files.telegram-test.clientmanagerai.com'
print('TELEGRAM_DISABLED_NO_SECRETS_EXACT_ORIGIN_PASS')
PYOFF
tgcompose exec -T api python - <<'PYHTTPS'
import json
import urllib.error
import urllib.request
base = 'https://console.telegram-test.clientmanagerai.com'
with urllib.request.urlopen(base + '/health/ready', timeout=15) as response:
    assert response.status == 200
    assert json.load(response) == {'status': 'ok', 'component': 'database'}
for path, status in [('/webhooks/telegram', 503), ('/webhooks/other', 404)]:
    request = urllib.request.Request(base + path, data=b'{}', headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        assert error.code == status
        if status == 503:
            assert error.headers.get('Cache-Control') == 'no-store'
            assert json.load(error) == {'error': {'code': 'UNAVAILABLE'}}
    else:
        raise AssertionError('WEBHOOK_UNEXPECTED_SUCCESS')
try:
    urllib.request.urlopen('https://files.telegram-test.clientmanagerai.com/asm-private-local?list-type=2', timeout=15)
except urllib.error.HTTPError as error:
    assert error.code == 403 and b'<Code>AccessDenied</Code>' in error.read()
else:
    raise AssertionError('BUCKET_PUBLIC')
print('HTTPS_READY_WEBHOOK_DISABLED_PRIVATE_BUCKET_PASS')
PYHTTPS
tgcompose exec -T api python - <<'PYTLS'
import json
import socket
import ssl
expected = {'console.telegram-test.clientmanagerai.com',
            'files.telegram-test.clientmanagerai.com'}
context = ssl.create_default_context()
for host in sorted(expected):
    with socket.create_connection((host, 443), timeout=15) as connection:
        with context.wrap_socket(connection, server_hostname=host) as secured:
            certificate = secured.getpeercert()
    names = {value for kind, value in certificate['subjectAltName'] if kind == 'DNS'}
    assert names == expected
    issuer = ', '.join(f'{key}={value}' for group in certificate['issuer'] for key, value in group)
    print(json.dumps({'host': host, 'SAN': sorted(names),
                      'issuer': issuer, 'notAfter': certificate['notAfter']}))
# Disable hostname matching only in this negative SNI probe; keep CA trust.
# A certificate-name mismatch or TCP failure must not count as SNI rejection.
negative = ssl.create_default_context()
negative.check_hostname = False
try:
    with socket.create_connection(('telegram-ingress', 443), timeout=15) as connection:
        with negative.wrap_socket(connection, server_hostname='unexpected.telegram-test.invalid'):
            raise AssertionError('UNKNOWN_SNI_ACCEPTED')
except ssl.SSLError as error:
    assert error.reason == 'TLSV1_UNRECOGNIZED_NAME', error.reason
print('TRUSTED_TLS_SAN_UNKNOWN_SNI_PASS')
PYTLS
sudo /snap/bin/certbot renew --cert-name asm-telegram-test --dry-run --run-deploy-hooks --non-interactive </dev/null
systemctl list-timers --all --no-pager | grep certbot
free -h
df -h /
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
test -z "$(git status --porcelain --untracked-files=all)"
```

HTTPS/TLS probes внутри API используют принятые network aliases и тот же TLS endpoint,
что signed-file provider, без предположения о NAT hairpin на собственный publicIP.
Внешний путь проверяется отдельно с устройства оператора ниже.
Dry-run success и `TLS_COPIED_AND_RELOADED` обязательны; test renew использует current
active certificate, не staging cert. У timer должен быть будущий **NEXT**; при его
отсутствии C6 чинит renewal. Повторить HTTPS block после reload. `free/df/stats` дают
фактические ресурсы; OOM, build/exit error или недостаток диска не обходить.

Из **локального PowerShell**, вне VM, с `$asmPublicIPv4`:

```powershell
$ErrorActionPreference = 'Stop'
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
$asmHealth = Invoke-RestMethod 'https://console.telegram-test.clientmanagerai.com/health/ready' -UseBasicParsing -TimeoutSec 15
if ($asmHealth.status -ne 'ok' -or $asmHealth.component -ne 'database') {
    throw 'EXTERNAL_READY_MISMATCH'
}
'EXTERNAL_HTTPS_READY_PASS'
$asmRequest = [System.Net.HttpWebRequest]::Create('https://files.telegram-test.clientmanagerai.com/asm-private-local?list-type=2')
$asmRequest.Method = 'GET'
$asmRequest.Timeout = 15000
$asmRequest.ReadWriteTimeout = 15000
try {
    $asmResponse = $asmRequest.GetResponse()
    $asmResponse.Close()
    throw 'EXTERNAL_PRIVATE_BUCKET_UNEXPECTED_SUCCESS'
} catch [System.Net.WebException] {
    $asmResponse = $_.Exception.Response
    if ($null -eq $asmResponse) { throw 'EXTERNAL_PRIVATE_BUCKET_NO_HTTP_RESPONSE' }
    $asmReader = New-Object System.IO.StreamReader($asmResponse.GetResponseStream())
    try {
        $asmBody = $asmReader.ReadToEnd()
        if ([int]$asmResponse.StatusCode -ne 403 -or $asmBody -notmatch '<Code>AccessDenied</Code>') {
            throw 'EXTERNAL_PRIVATE_BUCKET_DENIAL_MISMATCH'
        }
    } finally {
        $asmReader.Dispose()
        $asmResponse.Close()
    }
    'EXTERNAL_PRIVATE_BUCKET_DENIED_PASS'
}
foreach ($asmPort in @(22, 443, 5432, 8000, 8080, 9000, 9001)) {
    $asmTcp = New-Object System.Net.Sockets.TcpClient
    try {
        $asmConnect = $asmTcp.ConnectAsync($asmPublicIPv4, $asmPort)
        $asmOpen = $asmConnect.Wait(4000) -and $asmTcp.Connected
    } catch { $asmOpen = $false }
    finally { $asmTcp.Dispose() }
    "TCP $asmPort open=$asmOpen"
    if ($asmOpen -ne ($asmPort -in @(22, 443))) { throw "PORT_EXPOSURE_MISMATCH_$asmPort" }
}
```

Windows PowerShell5.1: explicit TLS1.2 меняет только протокол этой сессии,
проверка цепочки/hostname остаётся штатной. SystemDefault failure сам по себе не
доказывает использование TLS1.0; не отключать certificate validation.

Из operator сети22/443=True, остальные=False. Это **не** внешний deny22 от другого IP:
C6 сверяет soleSG/`/32` в Console и по доступности независимый deny probe.
Открыть Console браузером: trusted TLS/exacthostname/login screen, пока без credentials.
C6 фиксирует выведенные оба SAN/issuer/notAfter, exact unknownSNI alert, A и оба private bucket deny.
Signed file/authenticated cookie/journeys остаются следующему live шагу.

После reboot автозапуск app не заявляется. Войти по тому же SSH, повторить function/
UID/GID §0.4.5, затем `tgcompose --profile telegram-live up -d --no-build api worker scheduler frontend telegram-ingress`
и readiness. Existing volumes сохраняются; `down -v`, init/reset/rebuild/смена secrets
и слепой resend не нужны. Production systemd/IaC/SLA в эту задачу не добавляются.

Receipt C0: VM/zone/imageID/resources/soleSG rules/staticIP; время начала и контроль
расходов через30суток; sourceSHA/tree, Docker/Compose versions, markers/exit/health,
private modes, DNS/SAN/expiry/renewal, externalports/browserlogin и ограничения.
Не присылать `.env`, privatekeys, полные inspect/metadata/logs, signedURLs и личные
account/billing сведения. Host checks должны быть фактически исполнены; commands
и hostedCI не доказывают готовность этого host.

**Историческая граница ENV03 (теперь закрыт):** до его приёмки не создавать Owner/billing/live binding, не запускать
`provision_telegram_test`, `setWebhook`, smoke sends и не вставлять TG secrets.
C8-HOST и приёмка выполнены в PR23; текущее продолжение A09/A11 — §0.5.

### 0.4.8. Первичные источники процедуры

Сверены2026-10-01: [Yandex network](https://yandex.cloud/ru/docs/vpc/operations/network-create),
[subnet](https://yandex.cloud/ru/docs/vpc/operations/subnet-create),
[SG](https://yandex.cloud/ru/docs/vpc/operations/security-group-create),
[staticIP](https://yandex.cloud/ru/docs/vpc/operations/get-static-ip),
[VM](https://yandex.cloud/ru/docs/compute/operations/vm-create/create-linux-vm),
[serial output](https://yandex.cloud/ru/docs/compute/operations/vm-info/get-serial-port-output),
[Microsoft SSH keys](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement),
[ipify IPv4](https://www.ipify.org/), [Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
[Docker operator group](https://docs.docker.com/engine/install/linux-postinstall/),
[GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys),
[GitHub host key](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints),
[Certbot Snap](https://certbot.eff.org/instructions?ws=other&os=snap),
[Certbot hooks/dry-run](https://eff-certbot.readthedocs.io/en/stable/using.html),
[Let's Encrypt HTTP-01](https://letsencrypt.org/docs/challenge-types/).
Syntax/документационная сверка не являются исполнением на Windows/Yandex/VM.

### 0.4.9. Фактическое исполнение и решения C0 — 2026-10-02

**ENV03 INTEGRATED/VERIFIED после PR23/mainCI37016012805.** Приёмка только pre-live
TEST host; далее сохранён фактический receipt до merge. Финальные PR23 head/review/CI
находятся в merged PR, а текущее поручение — §0.5. Ниже фактические очищенные выводы
и screenshots владельца, проверенные C0. Агент не входил в облако/SSH и не заявляет
независимое исполнение команд на VM. Обновление только трёх docs в PR23; source
runtime/Compose/pins/tests и TG-disabled граница сохранены. Final C8/hash/scope и
CI последнего docs head — в PR receipt; прежний static review не заменяет итоговый.

| Объект | Наблюдение |
|---|---|
| Runtime source | HEAD80e51c43e31541940f1ccf18b8281adf1a061748; tree88ed308b4c56114aa977dcf91204964d9b7348e5; EXACT_SOURCE_PASS и повторный EXACT_SOURCE_STILL_CLEAN_PASS |
| VM | asm-telegram-test-vm / fhm53804pjetng9i46h2; RUNNING; created2026-10-02T04:57:26Z; ru-central1-a; non-preemptible standard-v3,2vCPU100%,8GiB,60GiB network-ssd |
| OS/image | Ubuntu24.04 amd64; official free ubuntu-2404-lts-oslogin-v20260928; description Ubuntu24.04 lts with oslogin v20260925040407. Source image ID виден в owner CLI screenshot; из неоднозначного OCR в команды не перенесён. OS Login по карточке выключен; имя образа этого не опровергает |
| SSH/network | asmoperator, groups asmoperator/docker/google-sudoers; host ED25519 SHA256:wzX5xwbgPVPm9BkcmUFAjqa4cIP6wslSd4J0K23LO+A; private10.73.0.26; sole asm-telegram-test-sg; inbound22=31.135.48.89/32,80/443=0.0.0.0/0, outbound all; serial console off |
| Public IP | Один static89.169.141.53, in use, deletion protection=true; DDoS option off. Это не VM/disk protection |
| Boot state | asm-telegram-test-boot; auto_delete=true подтверждён Cloud Shell instance get+disk get. Safe setter не найден; явное TEST disposition §0.4.2. Не считать false/backup PASS |
| Versions | Docker Engine/Client29.8.2, API1.56/min1.40; containerd2.3.6,runc1.5.1,docker-init0.19.0; Compose5.5.1; Certbot5.8.0; cloud-init26.1-0ubuntu1~24.04.1 |
| DNS/TLS | console.telegram-test.clientmanagerai.com и files.telegram-test.clientmanagerai.com →89.169.141.53; exact two SAN; trusted Let's Encrypt YE2; expiry2026-12-31T07:42:21Z; no second origin |
| Cert storage/renewal | /etc/letsencrypt/live/asm-telegram-test; private operator copies0600 in0700 directory; root-owned deploy hook. Dry-run --run-deploy-hooks success, TLS_COPIED_AND_RELOADED; nginx syntax/reload success. Timer NEXT был2026-10-02T22:18Z; повторный HTTPS PASS |
| Cost | Console estimate4735,81₽/30суток, тот же принятый scope. Review date2026-11-01; не cap/autodelete. IP создан раньше VM. Snapshot schedule INACTIVE по владельцу; прежние snapshots/их charges отдельно не инвентаризированы |

**Исполненные checks и их границы:**

| Команда/assertion | Фактический результат |
|---|---|
| git rev-parse HEAD/tree + git status --porcelain; timedatectl | Exact accepted bytes/tree, source clean, NTPyes; повторено после renewal |
| guarded source/PG recovery и rebuild прежних Dockerfiles | TRACKED_SOURCE_PERMISSIONS_PASS; EMPTY_ASM_BOOTSTRAP_STATE_PASS; PG_BOOTSTRAP_RECOVERY_PASS; BACKEND_SOURCE_READABLE_PASS; FRONTEND_SOURCE_READABLE_PASS; POSTGRES_CONTAINER_AND_VOLUME_PRESERVED_PASS |
| Compose inspect restricted fields + storage-init log marker | migrate/storage-init exited:0, private bootstrap PASS; api/worker/scheduler/frontend/postgres/storage/ingress running:true/OOMfalse; api/PG/storage healthy |
| API TelegramSettings/env assertions без вывода значений | cfg.enabled=false, TG token/secret empty; ASM_ENVIRONMENT=LOCAL; exact console origin + files endpoint; TELEGRAM_DISABLED_NO_SECRETS_EXACT_ORIGIN_PASS |
| urllib HTTPS probes inside API network aliases | health200 exact status:ok/component:database; Telegram webhook503 exact UNAVAILABLE/no-store; other webhook404; private bucket403+AccessDenied; HTTPS_READY_WEBHOOK_DISABLED_PRIVATE_BUCKET_PASS |
| ssl.create_default_context + two SAN + specific unknown-SNI error | TRUSTED_TLS_SAN_UNKNOWN_SNI_PASS; CA trust retained, unexpected hostname получил TLSV1_UNRECOGNIZED_NAME. Это реальный ingress через внутренний alias; внешний путь проверен отдельно |
| Certbot renew --cert-name asm-telegram-test --dry-run --run-deploy-hooks --non-interactive с закрытым stdin; nginx -t/reload | All simulated renewals succeeded; копии active certificate перезагружены, staging certificate не установлен. Строки nginx в hook stderr сами по себе не failure |
| Windows PowerShell5.1.26100.9444, explicit TLS1.2; ready/private bucket/TCP | EXTERNAL_HTTPS_READY_PASS, EXTERNAL_PRIVATE_BUCKET_DENIED_PASS, EXTERNAL_HOST_CHECKS_PASS;22/443 openTrue;5432/8000/8080/9000/9001 openFalse |
| Browser console URL | Trusted HTTPS/login page без TLS interstitial; login не выполнялся, auth/signed file journey не заявлен |
| post-renewal exact source/NTP/TG/HTTPS + free/df/stats | POST_RENEWAL_HOST_CHECKS_PASS;7.8Gi total/1.1Gi used/6.7Gi available, swap0; disk58G/5.7G used/52G available. Idle TEST snapshot, не нагрузочная оценка |

**Разбор и исправления выполненной процедуры:**

1. `cloud-init status` вернул2, done/degraded, errors пуст, единственный warning
   schema: datasource additional property. `cloud-init schema --system` подтвердил
   этот user-data issue, network-config valid; C0 сверил конкретное datasource
   Ec2/strict_id:false и отсутствие иных errors перед продолжением Docker install.
   Warning остаётся; cloud-init clean/rerun и изменения network/SSH/user-data не
   выполнялись. Это ограниченное решение для наблюдённого warning, не ignore-all.
2. Первый checkout под umask077 дал tracked bootstrap0600. PG initdb+CREATE DATABASE
   успели выполниться, затем OS user postgres получил Permission denied при source
   неизменённого bootstrap; Exit1/OOMfalse. Это ошибка host-процедуры, не миграций.
   C0 и отдельный C8 проверили bounded recovery: exact HEAD/tree/clean/private modes;
   только tracked regular files→644/755 и их dirs→755 при root/.git700/env600/TLS700;
   тот же container/volume; отсутствие asm roles/schemas/user relations до bootstrap;
   исходный bootstrap в транзакции ON_ERROR_STOP и postchecks roles/extensions/TCP
   auth/timeouts. Все три recovery markers PASS. Reset/down-v не применялись.
3. App images rebuilt после исправления файлов из тех же accepted bytes/locks;
   source readability проверена как non-root backend10001 и frontend nginx. PG
   container+mounts сохранены. Будущий checkout теперь ограничивает umask022 только
   tracked files внутри private root; chmod секретов/всего проекта запрещён.
4. Первый составной startup block закончился после nginx-t без конечных checks.
   `compose exec -T` по умолчанию читает stdin и может забрать остаток внешнего
   `bash <<...`; поведение child reader воспроизведено локально. Это объяснение
   совместимо с наблюдением, точный Docker stdin trace не снимался. Исправленная
   readiness с `</dev/null` для no-input commands исполнена целиком, все markers
   получены. Certbot dry-run также noninteractive/closed stdin. Установленный hook
   не переписывался; его вызов с закрытым stdin и reload фактически проверены.
5. PowerShell SystemDefault сначала дал unexpected error on send. Явный TLS1.2
   дал PASS без bypass CA/hostname. Конкретная первопричина SystemDefault не
   установлена; утверждать, что Windows использовал TLS1.0, нельзя.
6. Cloud protection instructions исправлены явно §0.4.2: boot auto_delete=true —
   фактическое ограничение принятого TEST, не скрытый PASS. До будущего удаления/
   замены требуется отдельный preservation plan; после потери state никаких
   слепых replay/новых ключей вместо recovery. Пересоздание текущего host не нужно.

**Review boundary:** C8-M2-ENV-03-PROCEDURE Oct1 проверял статически исходный runbook
hash96d2c128b9d51c9665a7d03d4fed1f239340c910eaa345f8afbf53f968314066;
C8-PG-RECOVERY Oct2 — конкретный recovery script
hashfbd57c1e508d8d6afee18a7468ab045fc37ae3b095124ef75ea7bf4dfe623267.
Новый C8-M2-ENV-03-HOST проверяет готовые изменения и фактический operator receipt;
его статус/hash находятся в PR23. Не выдавать прошлый static PASS за actual host review.
SSH deny с независимого IP, backup/restore, restart автозапуск, нагрузка, authenticated
Console/signed image и live A09/A11 не исполнены этим receipt. После reboot действует
ручной state-preserving start §0.4.7; background autopilot/production SLA не заявлен.

Исторические host gates C8/final-head CI/mergePR23/mainCI выполнены. Продолжение
выдаётся последовательно по §0.5; этот receipt сам по себе не разрешает пропустить
identity/setup gates и не объявляет M2 завершённым. M3 не выдан.

<details>
<summary>История — первые live инструкции; выполненное не повторять</summary>

## 0.5. Исторический первый live-шаг после принятого host — 2026-10-02

**M2-LIVE-A09-A11 IN_PROGRESS.** Accepted task base/main
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**, tree
**c30415b48a08dabac6a59f1294843a0bd25ff353**. PR23 actual merge имеет parents
80e51c43e31541940f1ccf18b8281adf1a061748 +902e9f1d51235f1441ce4378a4d3a909adefea74;
[push/main37016012805](https://github.com/Elefesys/ai-service-manager/actions/runs/37016012805)
SUCCESS, оба checkout именно22993f5,492 unit/390 PostgreSQL-S3/111 frontend/27 browser,
оба scripts/clean-source gates. Tree равен reviewed PR; C8-HOST PASS не повторяется.
11 переданных канонических файлов совпали с SOURCE_MANIFEST. Новый branch
**c6/m2-telegram-live** сохраняет только три docs и первый coordination commit.

Работающий checkout остаётся **80e51c43e31541940f1ccf18b8281adf1a061748**,
tree **88ed308b4c56114aa977dcf91204964d9b7348e5**. Git80e→22993f5 показал только
три docs: приложение/Compose/pins/provisioners/миграции одинаковы. Не fetching/
пересоздавать приложения ради документации, не заявлять runtime22993f5. Текущая
граница задаётся этим разделом и активным handoff; generic §2–5 не выполнять одним
заходом и не заменять их placeholder значения самостоятельно.

### 0.5.1. Первый шаг — владелец Console без Telegram

На Windows подключиться по прежнему SSH key к asmoperator@89.169.141.53.
Следующий блок запускается **в SSH Bash**, где prompt asmoperator@asm-telegram-test-vm.
В password manager создать новый пароль Console24–32ASCII символа. Это новая веб-
учётная запись **telegram.test.owner**, не Telegram login/password и не bot token.
На два скрытых terminal prompt вставить один и тот же пароль; символы не отображаются.

Блок проверяет exact source/clean и pre-live config; собирает только existing
telegram-operator development target, которого ранее не требовалось на host.
API/worker/frontend/PG/storage не пересобирает/не рестартует. Одноразовый tooling
container имеет DB identity asm_migrator; runtime identity не расширяется. В image
development OS root, но без host mounts/privileged flags; это прежний accepted
operator service. Пароль передаётся только его terminal getpass, не argv/env/files.

```bash
bash <<'ASM_OWNER_CREATE'
set -euo pipefail
trap 'printf "OWNER_SETUP_STOP: строка %s. Не повторять создание; передать C0 только эту ошибку.\n" "$LINENO" >&2' ERR
cd /home/asmoperator/asm-telegram-test

test "$(id -un)" = asmoperator
test "$(git rev-parse HEAD)" = 80e51c43e31541940f1ccf18b8281adf1a061748
test "$(git rev-parse 'HEAD^{tree}')" = 88ed308b4c56114aa977dcf91204964d9b7348e5
test -z "$(git status --porcelain --untracked-files=all)"
test -t 0 </dev/tty

export ASM_TELEGRAM_INGRESS_UID="$(id -u)"
export ASM_TELEGRAM_INGRESS_GID="$(id -g)"
tgcompose() {
  docker compose --project-name asm-telegram-test \
    --env-file infra/images.lock.env --env-file .env --env-file .env.telegram "$@"
}

tgcompose exec -T api python - <<'PYOWNER_PREFLIGHT'
import json
import os
import sys
import urllib.request

from asm.foundation import DATABASE_SCHEMA_REVISION
from asm.telegram.config import TelegramSettings

try:
    cfg = TelegramSettings()
    assert not cfg.enabled and not cfg.token.get_secret_value() and not cfg.webhook_secret.get_secret_value()
    assert os.environ['ASM_ENVIRONMENT'] == 'LOCAL'
    assert os.environ['ASM_AUTH_ORIGINS'] == '["https://console.telegram-test.clientmanagerai.com"]'
    assert os.environ['ASM_STORAGE_ENDPOINT'] == 'https://files.telegram-test.clientmanagerai.com'
    assert DATABASE_SCHEMA_REVISION == '0007'
    with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=10) as response:
        assert response.status == 200
        assert json.load(response) == {'status': 'ok', 'component': 'database'}
except Exception:
    print('OWNER_PREFLIGHT_FAILED: no secret values printed', file=sys.stderr)
    raise SystemExit(1)
print('OWNER_PREFLIGHT_PASS: accepted runtime, schema, Telegram disabled')
PYOWNER_PREFLIGHT

tgcompose --profile telegram-operator build telegram-operator </dev/null
tgcompose --profile telegram-operator run --rm --no-deps telegram-operator \
  python scripts/provision_local_auth.py --login telegram.test.owner </dev/tty
printf '%s\n' CONSOLE_OWNER_PROVISIONED_PASS
ASM_OWNER_CREATE
```

Вернуть C0 только JSON с **user_account_id/workspace_id/business_id** и
**CONSOLE_OWNER_PROVISIONED_PASS** либо очищенную ошибку. Пароль сохранить локально.
Фактическое выполнение, DB inserts и login ещё не подтверждены. До этого шага нет
Owner/billing/binding; после успеха будут только fresh account/OWNER/Workspace/
synthetic Business. TG=false, secrets отсутствуют, webhook/sends не включаются.

Build использует существующий Dockerfile/locks/exclusions, без новых dependencies
или pins. `/dev/null` закрывает build stdin; `</dev/tty` у interactive run сохраняет
getpass даже внутри внешнего heredoc. Не добавлять `-T` к password run. C6/C0
проверили Bash syntax/Python AST; это не фактический Docker/getpass/DB receipt.

Если error/UNIQUE collision/SSH disconnect или marker не получен — не повторять
create, не менять login/password, не удалять account/Workspace. UNIQUE откатывает
все пять вставок при collision, но потеря вывода после commit не доказывает rollback.
C0 выполнит/даст bounded read-only lookup exact login для восстановления3UUID и
проверки единственной OWNER/Workspace/Business связи. SQL владельцу выбирать не нужно.

### 0.5.2. Конечный порядок следующих шагов — команды выдаются после receipt

1. Войти в HTTPS Console с созданным login и подтвердить правильный Workspace.
2. Получить независимый numeric Telegram Owner ID в официальном Telegram Desktop
   выбранного test Owner: Settings → Advanced → Export Telegram data → только
   Account information, Machine-readable JSON. Локально взять
   `result.json` → `personal_information.user_id`; полный экспорт не передавать и
   не копировать на VM. [Официальная схема](https://core.telegram.org/import-export).
   Если Telegram задержит экспорт, соблюдать ограничение; не брать ID первого
   входящего события вместо подтверждённого аккаунта. Console UUID — другое поле.
3. Проверить выбранного test bot у официального BotFather; token остаётся private.
   Numeric prefix выбранного token задаёт expected bot ID в принятом config; getMe
   проверяет ID/is_bot, но не can_connect_to_business. Связать bot с test Owner через
   official Business/Secretary controls, только тестовый диалог/необходимые rights.
4. C0/C6 выдаёт один private-entry блок с точными IDs/именами для существующей
   .env.telegram, сохраняя DB/S3/TLS secrets. Synthetic contact фиксирован:
   **Synthetic Telegram test owner**, interval
   **2026-10-02T00:00:00+00:00 → 2026-10-09T00:00:00+00:00**. Это ещё не DB state;
   до первого commit должен оставаться действующим, иначе C0 уточняет его явно.
   После первой попытки даты/contact не пересчитывать при retries. Старые примеры
   сентября не выполнять; продление/новые тарифы не добавляются.
5. Existing discovery проверяет bot/Owner/webhook, не ACK/drop очередь, не задаёт
   offset/negative offset/pagination; getUpdates permitted только без webhook.
   `allowed_updates` может изменить future subscription — это не обещание полной
   неизменности provider state. Candidate external ID сохранить перед setup.
   Ноль/несколько candidates — STOP; старый lifecycle мог истечь после24h, не угадывать.
6. Existing atomic billing/binding setup → setWebhook **после** DB commit, exact URL,
   четыре update types, max_connections1/drop_pending_updatesfalse. Сохранить
   internal connection UUID отдельно. READY не гарантирует is_enabled/can_reply:
   проверить оба actual flags и текущую доступность; closed window не обходить.
   COMMITTED_WEBHOOK_UNCONFIRMED восстанавливать с теми же IDs/dates, без rebind/reset.
7. Единственный UI-сценарий §5.1: Client пишет **Owner**, не standalone bot, свежий
   synthetic text и Telegram photo; Owner видит правильный Workspace, открывает
   READY private image, один раз отвечает из Console; Client подтверждает получение.
   API send smoke параллельно не запускать. UNKNOWN/неоднозначный202 — только
   принятый exact-intention recovery, не новый key/слепой resend. SENT не Client receipt.

C3 source/official-doc contract review и C6 first-step review выполнены2026-10-02;
новый C8/live PASS этим не заявляется. Existing code tests закрывают свой scope,
реальные A09/A11 ещё впереди. Новый scoped C8 нужен при конкретном изменении/риске,
не для повторного ревью неизменённого host. После live receipt C0 обновляет три docs,
проверяет final-head CI, владелец merge, C0 actual main CI; до этого M2 IN_PROGRESS.
Production/M3, новые платные ресурсы, backup/restore drill не добавляются.

</details>

## 0.6. Текущий шаг — постоянный TEST egress после getMe PASS / 2026-10-05

**M2-ENV-04-TELEGRAM-EGRESS подготовлен к REVIEW в существующем Draft PR24.** Владелец
пока не меняет VM и не повторяет старые terminal blocks. Точное поручение, allowlist
и E01–E06 — единственный активный M2_HANDOFF. Один authoritative статус — TASK_REGISTER.
Бот подтверждён через temporary route; opt-in implementation имеет synthetic Docker
evidence, но owner deployment и независимая приёмка C0/C8 ещё не выполнены.

### 0.6.1. Датированный фактический receipt и границы

Accepted repository base/main22993f558c5e7e933c65e9c999933bd2e3ab41c4 с отдельным
push/main37016012805 SUCCESS. Сохранён coordinatione58c4a1a731ad238ccf9a79e6c478969642cd088.
VM остаётся checkout/runtime80e51c43e31541940f1ccf18b8281adf1a061748,
tree88ed308b4c56114aa977dcf91204964d9b7348e5. Все execution receipts ниже предоставлены
владельцем; C0 не имеет прямого SSH/cloud доступа.

- Console Owner login и3UUID созданы/подтверждены; повторный provisioner не запускать.
  Сообщение BILLING_STATE_MISSING соответствует этапу до atomic billing setup.
- Telegram Owner identity получена независимо; выбранный bot @saasaimanagerbot
  подключён через Business/Secretary UI для тестового диалога. Private token/secret
  сохранены mode600 на VM при persisted/runtime Telegram disabled; повторный ввод
  не нужен. getMe сам не проверяет Business rights/окно ответа.
- Direct VM/container IPv4 TCP443 к Telegram timeout; GHCR control успешен. SG/route/
  OUTPUT diagnosis не нашла deny в проверенной области; provider ticket FS471775
  сообщил внешнюю фильтрацию. Точный hop/механизм самостоятельно не установлен.
- Temporary token-free route artifact43a11b23f7472394def9e2fee57b38a9d1a0aebaa6fb60b5ea06b14506d157e7
  фактически PASS: curl0, HTTP302, CONNECT200, TLS verification0, total0.195588s;
  official pinned image/config/loopback/cleanup PASS. Это public HTTPS reachability.
- **2026-10-05 12:50:51+07:** corrected artifact
  **cc799386a922eaca78376a7acc0a2687a8465f2e32a8558643b7de5421174ba1**,
  23076bytes, фактически вернул exact runtime/source/private inputs/runtime-off PASS;
  fixed relay config/private network/no published ports PASS;
  **EXACT_IMAGE_TOKEN_FREE_TLS_PASS**, **EXACT_MAPPING_CLOSED_RELAY_PASS**,
  **EXACT_CLIENT_BOT_IDENTITY_PASS** после ровно одного getMe;
  **APPLICATION_AND_PRIVATE_INPUTS_UNCHANGED_PASS**, **IDENTITY_PROBE_CLEANUP_PASS**,
  **TG_BOT_IDENTITY_VIA_TEMP_RELAY_PASS**, SSH_EXIT0. Strict numeric expected ID,
  is_bot=True и username проверялись accepted client request path. Profile parameters
  сохранены; runtime services не включались, temporary network/containers удалены.

Не исполнены discovery/actual connection rights, billing/binding/setWebhook,
живые inbound/private media/manual reply/Client receipt. Permanent route и A09/A11
не подтверждены. Нового C8 PASS нет; предыдущие C3 reviews относятся к процедуре.

### 0.6.2. Исправление reference-byte проверки без ослабления guard

Предыдущий artifact323dbe7180fc0b7e41a257d0ef6a7ff69d79fb42ba8c039c738281bf344e0d41
остановился в IMPORT_AND_SOURCE **до** HTTP/getMe, с unchanged/cleanup PASS. Причина
подготовки C0: локальные reference copies имели лишний завершающий LF. Это ошибка
operator artifact, не доказательство дефекта приложения/токена/сети. Исправление:
canonical bytes из принятого tree, точные Git blob/size и SHA256; затем отдельные
source/UID/env stages. Никакой strip/нормализации/второго допустимого hash/обхода.

| Файл | Canonical Git blob | Bytes | SHA256 |
|---|---|---:|---|
| client.py | 53800d23c718910dd338cadee6ba595510c95ff9 | 14251 | 2a9995fb09b89f3787a0bcf48f7b643278148c231623b612e880bb7b30ffd496 |
| config.py | 31cba499681270d708cdb55e7c8e44202c07b4b7 | 2218 | 0a3a7dde5a458778f67fd484c15147ba668073e3497ef44377dc0a5a4686122a |

C0 сверил tree→blob через GitHub, C3 независимо bytes→blob/size/hash и diff. Обращение
только ограниченной правки восстановило точный старый artifact hash: остальные
guards/TLS/single getMe/cleanup byte-identical. Targeted C3 PASS, host/embedded syntax
и canonical accept/added-byte reject PASS; затем операторский execution выше PASS.
Не использовать прежние padded copies для нового reference hashing.

### 0.6.3. Ограниченное решение C0 и следующий порядок

Нужен **opt-in TEST overlay**, не правка TelegramClient и не общий VPN продукта.
Official Xray26.9.9 linux/amd64 pin:
`ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b`.
PRIVATE profile вне checkout остаётся у владельца. No credentials/endpoints/UUID
в Git/CI/artifacts. Принятые параметры VLESS/TCP/REALITY/Vision/fingerprint сохраняются.
Publisher source review не является подписанной/воспроизводимой сборкой.

Callers — api/worker/telegram-operator; fixed private IPv4 mapping official
api.telegram.org:443, без fallback при остановке/recreate relay. Scheduler route
не нужен: его ветка — durable recovery и S3 cleanup. Worker getFile и последующий
file GET покрываются одним fixed official origin. TLS/SNI/verify, timeouts, retries0,
redirects0, auth/RLS/permissions и private storage invariants остаются прежними.

Реальные controlled Docker/PG tests должны провести запрос через новый relay,
включая возможный effect/lost response→UNKNOWN→restart→wire count1. Старые direct-wire
tests сохраняются, но не заменяют evidence новой boundary. Synthetic fixture CA/hooks
допустимы только в TEST; реальные Telegram secrets/подписка не нужны CI. API/DB
readiness/auth должны оставаться доступны при отказе relay. Rollback сначала disable
Telegram, затем remove route; pending/DISPATCHING/UNKNOWN/receipts/PG/S3 сохранять.

После готовой реализации C0/C3 review, полный final-head CI и **новый scoped C8**.
Затем C0 даст владельцу один готовый deployment/preflight блок; пока commands не
выданы. После него существующие discovery и запись verified external ID, проверка
актуальности первого TEST billing interval, atomic setup/webhook и§5.1 Console journey.
Старый business_connection event мог истечь: по результату bounded discovery C0
даст конкретный UI шаг; не polling/drop/rebind наугад. После первой setup попытки
IDs/contact/dates неизменны при recovery. Даты2026-10-02→2026-10-09 пока только config.

ADR239 не меняется: данный synthetic TEST route не допускает production Client data.
Новых платных ресурсов/AI/M3, reset/down-v или production rollout нет. Успех getMe и
будущая приёмка ENV04 по отдельности не означают VERIFIED всего M2.

### 0.6.4. Подготовленная ENV04 процедура для выдачи C0

**C0/C8 2026-10-05: CHANGES_REQUESTED — эту версию не выполнять на owner VM.**
Ниже сохранён исторический reviewed artifact C6. Исправленная процедура — §0.6.7,
пока REVIEW; выдаёт её только C0 после targeted C8. Findings/границы старого evidence
сохранены в §0.6.6; одно текущее поручение — активный M2_HANDOFF.

Это review artifact, **не команда владельцу выполнить deployment сейчас**. После
scoped C8 и final CI C0 выдаёт один блок с принятым полным `ENV04_ACCEPTED_SHA` и
ранее подтверждённым абсолютным `ENV04_PROFILE` (существующий приватный profile).
Ни endpoint/UUID/profile contents, ни token/webhook secret не присылаются в PR.
Оператор не выбирает subnet/IP/SQL или новые параметры подключения. Рабочая копия
должна быть на принятом SHA; существующие app/operator images сохраняются, их
canonical client/config blobs проверяются внутри image без сети. Pull только Xray.

```sh
set -eu
cd /home/asmoperator/asm-telegram-test
test "$(git rev-parse HEAD)" = "$ENV04_ACCEPTED_SHA"
docker pull --platform linux/amd64 ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b
python3 scripts/prepare_telegram_egress.py prepare \
  --accepted-sha "$ENV04_ACCEPTED_SHA" --profile "$ENV04_PROFILE" \
  --telegram-env /home/asmoperator/asm-telegram-test/.env.telegram \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --project asm-telegram-test
python3 scripts/prepare_telegram_egress.py verify \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py deploy \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Блок выполняется с `set -eu`, от существующего non-root operator, без shell tracing.
`prepare` требует clean exact checkout, profile600/parent700, owner/no-symlinks,
JSON≤64KiB и единственный VLESS/TCP(or raw)/REALITY/Vision connection. Остальные
desktop DNS/inbounds/routes не импортируются. Автоматически выбирается свободная
private /28 с проверкой Docker IPAM и всех host IPv4 routes. State/config/route.env
создаются атомарно с600 в700 вне checkout; повторная подготовка сохраняет mapping,
любое противоречие прекращает выполнение. Config проверяет **закреплённый binary
с `--network none`**. Profile/env не source/exec; relay не получает TG/DB/S3 env.

`deploy` требует persisted **и runtime Telegram=false**. Сохраняет private
`deployment-before.json`/`deployment-after.json`: container/image IDs, mounts,
networks, hashes environment/process без самих значений. Поднимает только relay
и пересоздаёт api/worker из тех же images с прежними env/default gateway. Проверяет
три callers, включая одноразовый operator: AF_UNSPEC/AF_INET/AF_INET6 разрешают
только сохранённый relay IP; ordinary DB readiness доступна. Scheduler/PG/S3/frontend/
ingress не пересоздаются. Нет provider HTTP/getMe/setup/send; этот preflight не
утверждает доступность подписки, права Telegram или получение сообщения.
Mount records сравниваются в canonical order: порядок Docker inspect не является
изменением volume. Type/Name/Source/Destination/RW и число записей сохраняются;
изменение любого из этих полей по-прежнему останавливает процедуру.

Ожидаемые terminal markers: `TELEGRAM_EGRESS_PREPARE_PASS`, `...VERIFY_PASS`,
`...DEPLOY_PASS`, `...PREFLIGHT_PASS`. При bounded `EGRESS_*` error не менять flags,
pins или state вручную: вернуть C0 код и stage, не содержимое private inputs.
Файлы state содержат приватный config: целиком не архивировать/публиковать.

Последующее C0-разрешённое включение callers и operator идут только через
`prepare_telegram_egress.py compose --state-dir ... -- <exact allowed command>`.
Wrapper фиксирует project/env/overlay, повторно проверяет source/config/image/IPAM
и допускает только явные grammars `ps -q`, recreate api/worker, существующий
provisioner `--live [--discover]`; новых HTTP методов или обхода guards нет.
Историческая plain-Compose функция ниже для enabled callers больше не применяется.
Включение runtime/discovery/setup/webhook всё ещё требует отдельной выдачи C0.

Для C0-разрешённого rollback используется одна команда:

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Она атомарно меняет **только** `ASM_TELEGRAM_ENABLED=false` в существующем private env,
пересоздаёт api/worker сначала **с** mapping и проверяет disabled runtime; затем
пересоздаёт их без overlay и останавливает relay. Offline relay не блокирует disable.
`rollback.json` фиксирует IDs/mounts и сохранность прочих containers/images/env.
PG/S3 volumes, Console identities, pending/DISPATCHING/UNKNOWN, command receipts,
connection/billing dates и private state сохраняются. Нет down-v/reset/drop/rebind.
Если любой шаг прервался — не включать Telegram; повторить тот же rollback после
устранения указанной локальной ошибки. Новый private state/subnet для retry не создавать.

### 0.6.5. Воспроизводимое synthetic evidence ENV04

Таблица ниже — submitted C6 evidence, сохранённое как история. Фактический CI
SUCCESS подтверждён C0/C8, но E01/E05 acceptance ограничена finding03 и findings01–02
соответственно; актуальный review verdict — §0.6.6. E02–E04 остаются подтверждёнными.

`sh scripts/ci.sh` дополнен обязательным `sh scripts/test_telegram_egress.sh` после
сборки штатных images, до прежних backend/PG/S3 checks. Standalone lane требует
уже собранных штатных images
и локального `.env`, созданного прежним `init_local.py`; workflow не изменён.
Временный700 каталог вне build context содержит только свежие synthetic profile,
REALITY keys, CA/cert и wire/control files. Контейнеры не получают Docker socket.
Host driver допускает ровно stop/recreate собственного relay и сохраняет его IP.
Real relay использует тот же generated config/image; TEST peer перенаправляет только
fixed official domain:443 в private TLS recipient, с default deny. TLS CA injection
находится только в test fixture; live config/client trust store не меняются.
Xray26.9.9 имеет default private-destination block после VLESS: только TEST peer
получает явный `finalRules` allow для exact recipient /32/TCP443. Live relay не
получает freedom или такого исключения. Это восстановление synthetic topology,
не отключение TLS/hostname/deadline либо защитных assertions приложения.
Synthetic CA содержит critical basicConstraints/keyUsage, leaf — SAN/serverAuth и
key identifiers; `openssl verify -x509_strict -purpose sslserver -verify_hostname`
проверяет цепочку до topology. Python3.13 default VERIFY_X509_STRICT не отключается.
Wrong-host case требует именно X.509 code62; ошибка CA не может заменить hostname
negative. При failure публикуются только stage/exception class и счётчики событий,
без exception messages, URL/body/config/env или private key bytes.

| ID | Конкретные assertions и команда |
|---|---|
| E01 | 34 новых unit cases: strict JSON/connection fields, modes/owner/symlink, canonical-byte addition rejection, collision/stable IPAM, wrapper argv/rollback/redaction, mount order/field guards; pinned binary version/config test с network none, runtime Git blobs |
| E02 | Real resolved base/overlay comparison; exact caller mapping all address families before/after stop/recreate; no relay ports/writable anonymous volumes; bounded unavailable; actual API auth/DB и private S3 доступны при stopped relay |
| E03 | `TelegramEgressPostgresChecks`: wire peer/SNI/Host assertions; readonly recovery; partial download→тот же FETCH/File→READY, exact JPEG hash/bytes/private GET60/anonymous403; wrong CA/hostname, redirect и actual10MiB+1 reject |
| E04 | Два real worker process crashes: finalize before/after commit, fsynced effect→relay stop/lost response→UNKNOWN→new worker PID/relay ID→NO_CLAIM; durable job DEAD/attempt1 и повторно прочитанный wire counter1 |
| E05 | `--durable-receipt before/after`: fixtures удерживают real UNKNOWN, Console session и command receipt во время exact deploy/preflight/rollback; read-only hashes/counts всех app/platform таблиц равны, wire counter1; IDs/mounts/env preserved |
| E06 | Полные обычные `ci.sh`/`test_browser.sh`, прежние assertions и оба clean-source gates на final PR head; exact run/head/tree/tested merge закрепляются в PR receipt |

Новый lane выбирает свои два класса явным pytest collector; обычная integration
suite без relay topology сохраняет все прежние cases. Это не skip/xfail: CI всегда
запускает шесть wire cases и один held-state rollback case. Non-secret evidence —
`reports/telegram-egress.json` в прежнем verification artifact; приватные fixture
keys/config/env туда не копируются. Local Docker отсутствует, реальное исполнение —
GitHub runner. Synthetic результат не является owner deployment или live A09/A11.
Implementation run37279935914 SUCCESS:6+1 новых real cases,525 прежних+новых unit,
390 прежних PG/S3,111 frontend,27 browser, оба scripts/source gates. Последующая
mount-order regression увеличивает unit total на1; final head/tree/tested SHA и
его обязательный полный CI — PR24 receipt, отдельно от этого implementation run.


### 0.6.6. C0 и независимый scoped C8 — CHANGES_REQUESTED / 2026-10-05

Проверен implementation head **3fffdda5d5e3f866cf2f25c30bc9e619091de081**,
tree **6ffff63ac85097ab63e53538213bde9cde70edc6**. Tested merge
**160a9f41de201308e92121fc05f996006af92894** имеет ordered parents
accepted base22993f558c5e7e933c65e9c999933bd2e3ab41c4 + указанный implementation head;
его tree совпадает. [CI37281699500](https://github.com/Elefesys/ai-service-manager/actions/runs/37281699500)
SUCCESS: оба штатных scripts и clean-source gates,526 unit/390 PostgreSQL-S3/
111 frontend/27 browser и6+1 relay cases. Это фактический successful run,
но его E05 fixture не доказывает сохранность БД пересоздаваемых callers.

Review выполнен отдельным C8, не автором C3: новая network/operator boundary,
generator/Compose, private path/env safety, E01–E06 mapping, реальная цепочка E04,
deploy/rollback и оба CI logs. C0 независимо сверил Git tree/ordered parents,
12 разрешённых changed paths, canonical source bytes и соответствие принятому
VM receipt. Старые application/API/SQL/CI assertions не изменены. Новых dependencies
или миграций нет. Данные конкретного мастера/production не использовались.

| ID / priority | Reviewed source и воспроизведение | Закрытие |
|---|---|---|
| C8-M2-ENV04-01 / P2 | prepare_telegram_egress.py snapshot, lines659–664: модель из staged .env.telegram содержит TG values, фактические api/worker — disabled/empty. Actual snapshot с synthetic inspect/model прекращается EGRESS_RUNNING_ENVIRONMENT_DRIFT. Процедура§0.6.4 не содержит согласованного перехода между этими состояниями. | Disabled/no-secret runtime сохраняется; staged inputs неизменны; explicit later C0 activation. Реальный Docker regression исходной комбинации; другие env/mount/image/gateway guards сохранены. |
| C8-M2-ENV04-02 / P2 | test_telegram_egress.sh246 вызывает base recreate api/worker → postgres/asm_local; compose.test.yaml и durable_snapshot используют postgres-test/asm_test. Равные hashes31 таблиц относятся к отдельной БД. | Runtime callers и before/after proof используют одну фактическую БД; обязательный identity assertion, реальные UNKNOWN/receipt/session и wire counter1 через exact CLI deploy/rollback. |
| C8-M2-ENV04-03 / P2 | prepare_telegram_egress.py444–449: Path.absolute() оставляет ..; lexical is_relative_to(ROOT) пропускает outside/../checkout/private-state. C8 воспроизвёл реальную запись config/state внутрь disposable checkout при substituted external checks. | Каноническая граница до effects и no-symlink/owner/mode сохранены; adversarial path regression доказывает отсутствие записи/вызовов при отказе. |

Граница локальных reproductions: actual Python guard/write code с synthetic inputs
и substituted Docker/source/image checks; это не локальный Docker или owner VM run.
Реальные Docker/PostgreSQL/S3/wire результаты взяты из final GitHub runner logs;
C0/C8 не скачивали повторно ZIP и не заявляют собственную проверку всех224 ZIP files.
C6 ZIP receipt сохранён отдельно в PR. Scoped C8 **выполнен / CHANGES_REQUESTED**,
не PASS и не полный security audit всего продукта.

Сохраняются E02–E04: actual fixed relay, strict TLS, bounded interrupted readonly/
media recovery, два real worker crash сценария, durable UNKNOWN и fsynced count1
после новых worker PID/relay ID. Находки не разрешают новый proxy product, M3,
изменение source-byte hashes, retry policy, тайм-аутов или снятие защитных assertions.
Единственный следующий шаг — ограниченное исправление C6 в текущем PR24 по активному
handoff; затем exact-head full CI и targeted C8 по трём находкам. PR остаётся Draft,
owner VM/внешний Telegram не меняются, M2 IN_PROGRESS. Это не приёмка ENV04/M2.

### 0.6.7. История — C6 correction REVIEW до targeted C8

**C0/C8: эта версия не принята для owner deployment.** Одна оставшаяся 01/P2
и текущая доработка — §0.6.8. Ниже сохранён submitted artifact, не действующая
инструкция владельцу. Закрытие02/03 не отменяется.

Продолжение от **7a9eca3d2e1509b029d1ef0ba2f2c0d2d590ce7c**, tree
**1da0e2da06269457e91de1752fe224f93681b8ba**, CI37285033299 SUCCESS. История сохранена.
Это исправленный artifact для C0/targeted C8, **не инструкция владельцу запускать
deployment сейчас**. §0.6.4 больше не является текущей процедурой. M2 IN_PROGRESS,
PR24 Draft; VM/live Telegram и существующие private inputs C6 не меняет.

| Finding / criteria | Regression и новое доказательство |
|---|---|
| C8-M2-ENV04-01 / E05 | `test_staged_inputs_do_not_enter_disabled_runtime_model_or_relax_drift`: на reviewed code EGRESS_RUNNING_ENVIRONMENT_DRIFT; после fix default Compose читает текущий runtime `.env`, explicit operator отдельно читает staged file. Все четыре TG fields, DB/storage env по-прежнему сравниваются строго; любое изменение отклоняется. Mandatory Docker lane начинает с disabled/empty callers и заполненного synthetic staged env, сверяет это до/после deploy/rollback, staged bytes неизменны. |
| C8-M2-ENV04-02 / E05 | `durable_local`, `durable_snapshot`, `test_deploy_rollback_preserves_console_unknown_receipts_and_wire_counter`: fresh isolated project/volume и empty domain state, exact postgres/asm_local endpoints. SQL identity из actual api и worker (database/OID/server address/port/postmaster start) совпадает с harness до/после CLI. Реальная отдельная asm_test отвергается; удерживаются UNKNOWN, receipt и Console session, повторный HTTP session/business GET с тем же cookie после rollback; все app/platform rows и persistent counter1 неизменны. |
| C8-M2-ENV04-03 / E01 | `test_prepare_rejects_canonical_checkout_state_before_any_effect` воспроизводит прямой путь и outside/../checkout/private-state, доказывает отсутствие writes и source/Docker/image calls при отказе. `test_prepare_canonical_outside_path_and_symlink_alias_guard`: правильный outside path проходит с canonical output; symlink/../ alias отклоняется до resolve. Owner/mode/no-symlink проверки сохранены. |

E02–E04 cases, их assertions, pinned Xray/TLS/official origin, application/client
source blobs, operation budgets/retries0 и UNKNOWN recovery не изменены. Дополнительный
SQL identity check не заменяет fingerprint: проверяются и actual target, и содержимое.
Six transport cases остаются на asm_test со старыми строгими guards. Отдельный E05
LOCAL harness имеет собственные более узкие fresh-project/endpoint/empty-state guards;
обычные asm_test fixtures не получают исключений для LOCAL. Worker останавливается
только на время synthetic seed/effect, затем реальные disabled API/worker проходят
exact CLI deploy/preflight/rollback; приложение/Compose base не патчатся.

Локально Docker отсутствует. Reproductions C8-01/03 выполнены actual Python guards
с substituted external checks: это не owner VM или Docker receipt. После fix38 unit
cases PASS; обязательный runner выполняет `sh scripts/ci.sh` (включая семь real relay
cases), `sh scripts/test_browser.sh` и оба clean-source gates. Exact final head/tree/
tested merge, CI outcomes и проверенный artifact находятся в PR24 receipt, чтобы
не создавать SHA-only commits. Перед выдачей C0 требует successful final run и targeted
C8 по этим трём corrections; данный текст не объявляет их независимую приёмку.

CI37288745538 на первом correction headdff90aec: шесть E02–E04 PASS, E05 setup
остановлен до seed/deploy. Диагноз — PostgreSQL inet::text отдаёт address/32, старый
fixture parser ожидал bare IP. Использован ip_interface с обязательными private IP
и полной host mask (/32 либо /128); raw SQL identity и equality assertions прежние.
Это исправление test defect, не ослабление network guard; final CI обязателен заново.

После приёмки C0 выдаёт следующий единый блок с полным принятым `ENV04_ACCEPTED_SHA`
и уже известным absolute `ENV04_PROFILE`. Не вводить secrets повторно, не копировать
staged inputs в runtime. Текущий `.env` должен разрешаться в фактические disabled
callers с пустыми TG fields; вся остальная env/image/process/mount/gateway identity
строго проверяется. При drift остановиться с bounded error и вернуть C0 только код.

```sh
set -eu
cd /home/asmoperator/asm-telegram-test
test "$(git rev-parse HEAD)" = "$ENV04_ACCEPTED_SHA"
docker pull --platform linux/amd64 ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b
python3 scripts/prepare_telegram_egress.py prepare \
  --accepted-sha "$ENV04_ACCEPTED_SHA" --profile "$ENV04_PROFILE" \
  --telegram-env /home/asmoperator/asm-telegram-test/.env.telegram \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --project asm-telegram-test
python3 scripts/prepare_telegram_egress.py verify \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py deploy \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Ожидаемые markers: `TELEGRAM_EGRESS_PREPARE_PASS`, `...VERIFY_PASS`, `...DEPLOY_PASS`,
`...PREFLIGHT_PASS`. Private state700/config600 находятся canonical вне checkout;
публиковать их содержимое нельзя. Deploy сохраняет текущий runtime env, только
добавляет fixed mapping и relay. Preflight проверяет mapping трёх callers и обычную
DB readiness, не делает Telegram HTTP и не доказывает доступность подписки/rights.
Staged `.env.telegram` не попадает в runtime containers. Только явно выданный
one-shot operator wrapper читает этот файл; данный блок не вызывает operator/live.
Будущая активация runtime — отдельный согласованный C0 шаг: обычный wrapper recreate
сам не импортирует staged inputs. Ни discovery/setup/webhook, ни send здесь нет.

Для отдельно разрешённого C0 rollback:

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Сначала атомарно фиксируется `ASM_TELEGRAM_ENABLED=false` в фактическом runtime
`.env`; если default field отсутствовал, добавляется только он. Прочие bytes
сохраняются; staged `.env.telegram` не переписывается. API/worker пересоздаются с
mapping и проверенным disabled env, затем без mapping; обе стадии ждут readiness
в прежнем command budget. Relay останавливается. Его outage не блокирует rollback.
Private receipt сверяет прежние images/mounts/process/env (кроме disabled flag),
actual DB identity и unrelated containers. Нет down-v/reset/rebind/drop. PG/S3
volumes, UNKNOWN/receipt/Console и staged inputs сохраняются. При ошибке не включать
Telegram: вернуть C0 bounded code, после исправления повторить тот же rollback.

### 0.6.8. C0 + независимый targeted C8 — закрыты02/03, остаток01 / 2026-10-05

**CHANGES_REQUESTED. M2-ENV-04 — IN_PROGRESS.** Это результат реального targeted
review готовых corrections. Один оставшийся blocker01/P2/E05; не новая задача M2.
§§0.6.4/0.6.7 — исторические непринимаемые deployment artifacts. Owner на VM
сейчас ничего не меняет. Единственное активное поручение находится в M2_HANDOFF.

Проверен implementation head **2536a1aa2b41792fff381c4d222906e2ff9ad23c**,
tree **2efe2c9df60dd9118b24adbfa6e8b76cd98bfebd**. Tested merge
**8bb3f34e2ee122b033102a40eb53b2696a9bb70e** имеет ordered parents
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** + указанный implementation head,
его tree совпадает. [CI37289340867, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37289340867)
SUCCESS: оба штатных scripts и clean-source gates, 530 unit, 390 PostgreSQL/S3,
111 frontend, 27 browser и 6+1 relay cases. Foundation job111695793211 и browser
job111695792866 действительно checkout этот tested merge.

| Finding | Targeted C0/C8 disposition |
|---|---|
| C8-M2-ENV04-01 / P2 / E05 | **OPEN, одна оставшаяся доработка.** Staged TG fields больше не входят в disabled runtime, но исключён весь .env.telegram, содержащий также действующие HTTPS ASM_AUTH_ORIGINS и ASM_STORAGE_ENDPOINT. Принятый pre-live recipe сохраняет их именно там; .env из init_local.py содержит только PG/S3 credentials. Поэтому model возвращается к localhost/http defaults, snapshot отказывает EGRESS_RUNNING_ENVIRONMENT_DRIFT до up. |
| C8-M2-ENV04-02 / E05 | **CLOSED на reviewed head.** Реальные API/worker SQL identities совпадают с isolated postgres/asm_local harness до/после exact deploy/preflight/rollback; отдельная asm_test отвергается. UNKNOWN, command receipt, та же HTTP Console session, fingerprints 31 таблицы и wire counter=1 сохранены. |
| C8-M2-ENV04-03 / E01 | **CLOSED на reviewed head.** Canonical destination проверяется до calls/mkdir/write; direct checkout и .. aliases отклоняются без effects. Symlink/.. не скрывается resolve; approved outside path проходит. Owner/mode/no-symlink guards сохранены. |

**Диагноз01.** В exact `scripts/init_local.py` создаются только семь PG/S3 credential
keys. Принятая §0.4.5 записывает Console HTTPS `ASM_AUTH_ORIGINS` и files HTTPS
`ASM_STORAGE_ENDPOINT` в `.env.telegram`, запускает callers с обоими env files и
проверяет эти non-default значения в actual API. Recorded host/readiness PASS
подтверждает результат. Private staging procedure сохраняла `.env` неизменным,
добавляла TG fields в тот же `.env.telegram`, не пересоздавая disabled runtime.
Current `compose_prefix` (reviewed lines545–561) исключает staged file целиком;
base defaults возвращаются в модель. `snapshot`677–683, вызванный `deploy`862,
останавливает операцию до первого up. Clean environment также удаляет shell ASM
overrides, поэтому экспорт переменных не является решением.

C8 независимо вызвал настоящие исправленные deploy/snapshot с synthetic model/
inspect, прочитав defaults exact Compose. Telegram=false и четыре TG поля пусты
в обеих сторонах; различаются только две указанные HTTPS настройки. Получен
EGRESS_RUNNING_ENVIRONMENT_DRIFT, caller up отсутствует. Это локальная control-flow
reproduction с заменёнными внешними Docker boundaries, не VM/PG run. Actual private
bytes owner .env не читались. Дефект доказан для состояния принятой процедуры;
незаявленное ручное дублирование ключей нельзя считать обязательным prerequisite.

**Принимаемое исправление01:** сохранить уже действующие origin/endpoint в узкой
private runtime-модели, отделённой от staged TG inputs. Разрешён runtime overlay
вне checkout с этими двумя проверенными values. Не переписывать исходные private
файлы, не просить owner переносить поля и не обходить drift guard. Runtime остаётся
disabled/empty TG; explicit operator читает staged inputs только по отдельной команде
C0. Это явно исправляет неполное условие correction «runtime только .env», не
меняет app/domain contracts. Rollback disable-first, сохранность прочих bytes,
images/mounts/gateway/DB identity и durable data обязательны.

Real Docker regression начинает с принятого распределения env files и actual callers
с HTTPS values до работы исправленного generator. Тот же exact deploy/preflight/
rollback обязан сохранить origin/endpoint, пустые TG fields, staged bytes и весь
уже доказанный E05 state. Проверки непредвиденного drift не удалять. Закрытые02/03
сохранить; повторный C8 только01/затронутая boundary после full final-head CI.

**Фактическое закрытие02:** actual API/worker выполняют read-only SQL своей connection
identity; fresh isolated LOCAL harness работает с той же postgres/asm_local, runtime
и migrator проверяют совпадение. Отдельная настоящая asm_test отвергается. Held
UNKNOWN/receipt/Console cookie,31 table fingerprints и fsynced wire counter1 проходят
точные CLI deploy/preflight/rollback. Проверены source и исполненные6+1 runner cases.
**Фактическое закрытие03:** C8 дополнительно исполнил canonical-path refusal и positive
outside case локально; direct checkout/.. отклонены до calls/writes, symlink/.. не
маскируется. Canonical output, owner/mode/no-symlink checks сохраняются.

C8 сверил26 source blobs с fresh Git tree и прочитал оба CI logs. C0 независимо
проверил refs/ordered parents/tree, восемь correction paths и те же execution logs.
ZIP artifact C0/C8 повторно не скачивали: C6 byte-verification остаётся его receipt.
На owner VM не запускались Docker/SSH/Telegram/activation или новые проверки.
Настоящие Docker/PG/S3 и sockets исполнены GitHub runner; локальные reproductions
не выданы за них. E02–E04 evidence и TLS/timeouts/UNKNOWN assertions сохраняются.
PR24 Draft; no merge/VERIFIED, M2 IN_PROGRESS. После исправления C0 выдаст готовый
owner block; секреты, profile и старые успешные шаги повторять не нужно.

### 0.6.9. C6 — correction остатка01/P2/E05, REVIEW / 2026-10-05

**После partial deployment на owner VM этот first-deploy block не повторять.**
Текущий operational gate/recovery task — §0.6.11; ниже сохранён принятый synthetic receipt.

Историческая передача C6 сохранена ниже; финальный C0/C8 PASS и текущий owner
шаг — §0.6.10. Подготовленный deploy/rollback artifact принят в synthetic scope,
но исполняется только отдельным готовым блоком C0 с exact accepted SHA после
source-access шага. PR24 Draft, M2 IN_PROGRESS; actual VM deployment ещё не выполнен.

Accepted base22993f558c5e7e933c65e9c999933bd2e3ab41c4; exact старт после C0
6296f26f76c944b18a53feaba46a2b975eca247a, tree3e1cbecb95d9220bfcc4ade5fb0907737eb1cedc,
CI37292611679 SUCCESS. История/первый coordination сохранены. Final head/tree/tested
merge+ordered parents, оба scripts/clean gates, runner jobs и artifact digest
фиксируются одним PR24 receipt без SHA-only commits.

| Assertion | Correction/evidence |
|---|---|
| C8-01 / E05 inputs | Regression сначала получила EGRESS_RUNNING_ENVIRONMENT_DRIFT на reviewed code. Теперь штатный Compose config читает два accepted input files без source/eval; private runtime.json содержит только origin/endpoint для api/worker, не credentials/TG. Hash/re-derivation и полный actual drift guard обязательны. |
| E05 independent baseline | `.env` имеет ровно семь исходных PG/S3 keys; отдельный файл содержит действующие HTTPS settings. Docker запускает callers до generator, затем TG fields stage без recreate. Exact prepare/deploy/preflight/rollback не создаёт baseline исправленной моделью. Staged bytes сохранены, `.env` меняется только на enabled=false при rollback. |
| E05 / closed02 | До/после actual callers HTTPS/disabled/empty TG и тот же SQL identity; прежние UNKNOWN/receipt,31 table fingerprints/fsynced counter1. Та же Console session теперь через проверенный TLS и Secure cookie; private S3 anonymous403 через HTTPS. Закрытые identity guards не перепроектированы. |
| E01 / closed03 | Canonical outside-checkout, owner700/file600/no-symlink и отказ до effects сохранены. Runtime overlay также private, вне build/artifacts. |
| E02–E04 | Прежние шесть real wire cases/relay controls, official origin/TLS/budgets/retries0 и UNKNOWN/no-resend неизменны. HTTP auth defaults шести asm_test cases указаны явно, чтобы HTTPS operational model E05 не меняла их исходную fixture. |
| E06 | Локально39 targeted unit, Ruff/syntax и actual Compose config resolution PASS; Docker локально отсутствует. Полные scripts, PostgreSQL/S3/browser и оба clean gates исполняются GitHub runner, результаты/границы — final PR receipt. |

Необходимая HTTPS fixture добавлена только в compose.test.yaml: существующий
WEB_IMAGE digest, non-root/read-only/cap-drop, три точных private RO mounts,
private network aliases, без host ports. Её TLS leaf проверяется по TEST CA/hostname;
CA и fixture hooks не входят в live config. Application/base Compose/workflows/
pins/migrations/dependencies и защитные assertions не меняются.

**Порядок для отдельной выдачи C0 после targeted C8.** C0 подставляет принятый final
ENV04_ACCEPTED_SHA и уже имеющийся ENV04_PROFILE; owner не вводит повторно secrets
и не переносит поля. Рабочий checkout должен соответствовать этому SHA; actual
application image/source blobs и disabled callers проверяются helper. `.env` и
`.env.telegram` сохраняют принятое распределение. State path ниже canonical вне
checkout, parent/private files принадлежат оператору с прежними700/600. Не
переносить старый state вручную: несовпадение preparation inputs — bounded отказ
для C0. Содержимое config/runtime/env/inspect не публиковать.

```sh
set -eu
cd /home/asmoperator/asm-telegram-test
test "$(git rev-parse HEAD)" = "$ENV04_ACCEPTED_SHA"
docker pull --platform linux/amd64 ghcr.io/xtls/xray-core@sha256:9a17fb7fcda36f80d041fc1f12f1d661d3f7c502572b2a6f2e4432534789a20b
python3 scripts/prepare_telegram_egress.py prepare \
  --accepted-sha "$ENV04_ACCEPTED_SHA" --profile "$ENV04_PROFILE" \
  --telegram-env /home/asmoperator/asm-telegram-test/.env.telegram \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --project asm-telegram-test
python3 scripts/prepare_telegram_egress.py verify \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py deploy \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Ожидаемые markers: `TELEGRAM_EGRESS_PREPARE_PASS`, `...VERIFY_PASS`, `...DEPLOY_PASS`,
`...PREFLIGHT_PASS`. Private state700/config600 находятся canonical вне checkout;
публиковать их содержимое нельзя. Private runtime.json600 содержит ровно две non-TG HTTPS настройки accepted inputs;
при verify они заново выводятся из исходных files и сверяются по hash.
Deploy сохраняет текущий runtime env, только
добавляет fixed mapping и relay. Preflight проверяет mapping трёх callers и обычную
DB readiness, не делает Telegram HTTP и не доказывает доступность подписки/rights.
Из staged `.env.telegram` в api/worker входят только прежние ASM_AUTH_ORIGINS и
ASM_STORAGE_ENDPOINT через runtime.json; четыре TG fields не импортируются.
Никакого ручного переноса полей владельцем нет. Только явно выданный
one-shot operator wrapper читает этот файл; данный блок не вызывает operator/live.
Будущая активация runtime — отдельный согласованный C0 шаг: обычный wrapper recreate
сам не импортирует staged inputs. Ни discovery/setup/webhook, ни send здесь нет.

Для отдельно разрешённого C0 rollback:

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Сначала атомарно фиксируется `ASM_TELEGRAM_ENABLED=false` в фактическом runtime
`.env`; если default field отсутствовал, добавляется только он. Прочие bytes
сохраняются; staged `.env.telegram` не переписывается. API/worker пересоздаются с
mapping и проверенным disabled env, затем без mapping с тем же HTTPS runtime.json; обе стадии ждут readiness
в прежнем command budget. Relay останавливается. Его outage не блокирует rollback.
Private receipt сверяет прежние images/mounts/process/env (кроме disabled flag),
actual DB identity и unrelated containers. Нет down-v/reset/rebind/drop. PG/S3
volumes, UNKNOWN/receipt/Console и staged inputs сохраняются. При ошибке не включать
Telegram: вернуть C0 bounded code, после исправления повторить тот же rollback.

<details>
<summary>История — C0/C8 code acceptance и source access, выполненный до Docker29 failure</summary>

### 0.6.10. C0 приёмка / targeted C8 PASS; owner source access / 2026-10-05

Accepted implementation head **d57ae07f10cd603910876068da444829b326bdab**,
tree **bc8b10fe8be27c237e0b62665068c0ef9e14ece5**. Tested virtual merge
**91720ac87671166e3a066b9301fe29a6762b05fb**: ordered parents accepted base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4** + implementation head; tree совпадает.
[CI37297119410, attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37297119410)
**SUCCESS**:531 unit,390 PostgreSQL/S3,111 frontend,27 browser,6+1 relay/E05;
оба штатных scripts и clean-source gates. Foundation111720865066 и browser111720864815
checkout exact tested merge. [C6 full receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-5992911966).

**C0 ACCEPTED / независимый targeted C8 PASS. Все C8-M2-ENV04-01/02/03 CLOSED.**
Последний review выполнен по01 и изменённым runtime-overlay/baseline/HTTPS/rollback
boundaries, не по всему будущему продукту. C8 независимо сверил26 Git blobs,
оба execution logs и выполнил local substituted boundary checks. HTTPS/empty TG
сохраняются; изменения9 runtime fields, двух operational inputs и runtime.json
отвергаются прежними guards.11 AST boundaries подтверждают сохранение закрытых
02/03 и E02–E04. C0 сверил fresh GitHub refs/девять paths/CI и принял результат.

Real Docker baseline использует прежний двухфайловый recipe до prepare, затем
stage TG без recreate. Exact CLI сохраняет два HTTPS values, disabled/empty TG,
private input bytes и ту же actual БД callers. Secure Console session, UNKNOWN/
receipt, fingerprints31 таблицы и persistent counter1 проходят deploy/rollback.
Guard обходов и ослабления TLS/timeouts/UNKNOWN нет; приложение/root Compose/
workflows/pins/dependencies/migrations неизменны. Zip verification остаётся receipt
C6: C0/C8 ZIP bytes повторно не скачивали. Local C8 substitutes не называются Docker
execution; реальная Docker/PG/S3/TLS проверка исполнена GitHub runner.

| Критерий | Приёмка и граница |
|---|---|
| C8-01 / E05 | CLOSED: accepted split env files → private two-field runtime overlay, независимый old-recipe baseline до prepare, strict drift/hash/re-derivation, exact Docker CLI и HTTPS/Secure session preservation. |
| C8-02 / E05 | Ранее CLOSED сохраняется: same actual caller DB, UNKNOWN/receipt/Console session/31 table fingerprints/counter1 до/после. |
| C8-03 / E01 | Ранее CLOSED сохраняется: canonical outside-checkout guard до effects, owner/mode/no-symlink и private runtime.json. |
| E02–E04 | Прежние real mapping/readonly/media/TLS и relay effect→loss→UNKNOWN/restart/no-resend cases прошли; исходные transport semantics не менялись. |
| E06 | Exact-source full CI/оба scripts/clean gates и реальный независимый C8 PASS; это controlled LOCAL/TEST evidence. |
| Owner VM / live A09/A11 | НЕ ИСПОЛНЕНО: нового permanent route, discovery/setup/webhook/send ещё нет. Temporary getMe и прежний host/Console уже PASS. |

**Сейчас выполняется только подготовка source access.** VM checkout остаётся
80e51c43e31541940f1ccf18b8281adf1a061748; предыдущий GitHub read-only key отозван.
Accepted deployment source будет указан полным SHA после текущего docs-only
coordination и его CI; эта запись не выдаётся за actual VM receipt.

Владелец открывает обычную SSH-сессию `asmoperator@asm-telegram-test-vm` с ранее
разрешённого operator IP (Happ выключен). Следующий блок читает только public key
и его fingerprint; если оба source-key файла отсутствуют, создаёт отдельную пару
с passphrase. Passphrase сохраняется в менеджере паролей и вводится только на VM.
Существующие key files не перезаписываются. Это отдельный source key, не ключ входа.

```bash
bash <<'ASM_SOURCE_ACCESS'
set -euo pipefail
trap 'printf "SOURCE_ACCESS_STOP: line %s\n" "$LINENO" >&2' ERR
test "$(id -un)" = asmoperator
umask 077
asmKey=/home/asmoperator/.ssh/asm_source_readonly
test -d /home/asmoperator/.ssh
test ! -L /home/asmoperator/.ssh
test "$(stat -c '%u:%a' /home/asmoperator/.ssh)" = "$(id -u):700"
test ! -L "$asmKey" && test ! -L "$asmKey.pub"
if [ ! -e "$asmKey" ] && [ ! -e "$asmKey.pub" ]; then
  ssh-keygen -t ed25519 -a 64 -C asm-telegram-test-source -f "$asmKey" </dev/tty
fi
test -f "$asmKey" && test ! -L "$asmKey"
test -f "$asmKey.pub" && test ! -L "$asmKey.pub"
test "$(stat -c '%u:%a' "$asmKey")" = "$(id -u):600"
ssh-keygen -lf "$asmKey.pub"
cat "$asmKey.pub"
printf '%s\n' SOURCE_READONLY_KEY_READY
ASM_SOURCE_ACCESS
```

После SOURCE_READONLY_KEY_READY скопировать только строку `ssh-ed25519 ...` в
https://github.com/Elefesys/ai-service-manager/settings/keys → Add deploy key.
Title: `asm-telegram-test-env04`; **Allow write access оставить выключенным**.
Подтвердить Add key, вернуть C0 только **SOURCE_ACCESS_ADDED**. Public key не нужно
присылать в чат; private key/token/env/profile тем более не передавать. При STOP
не перезаписывать ключи, вернуть bounded marker. C0 не предполагает, что доступ
уже восстановлен. После exact fetch ключ снова отзывается в GitHub.

**Следующая подготовленная последовательность C0:** guarded fetch immutable accepted
SHA из этого repository с прежним pinned GitHub known_hosts; проверить target tree,
clean current80e51c4 checkout, private inputs и app image IDs; checkout при umask022
только tracked files внутри existing private root. Без reset/clean/reclone/build/
migrations/down-v. Затем accepted §0.6.9 prepare/verify/deploy/preflight с реальными
известными profile/env/state paths, Telegram disabled, без operator/live HTTP.
Прежние env/profile/TLS, volumes и Console identities сохраняются; helper проверяет
actual DB/env/image/mount/gateway. Выдать владельцу один заполненный блок после
SOURCE_ACCESS_ADDED; не заставлять вручную собирать значения из разных документов.

Review PASS не выдаёт автоматического права на discovery/setup/webhook/send или
удаление/сброс TEST host. Rollback только по отдельному конкретному решению C0;
accepted disable-first/retained HTTPS/UNKNOWN rules прежние. Actual route receipt,
потом live A09/A11, merge владельцем и отдельный main CI остаются конечным остатком.
M2-ENV-04 REVIEW, M2 IN_PROGRESS; INTEGRATED/VERIFIED и M3 не объявлены.

</details>

### 0.6.11. Owner partial deployment — Docker29 IPv6 mapping failure / 2026-10-05

**Текущий gate:** C0-M2-ENV04-04, P2 / E02,E05; ENV04 IN_PROGRESS,
ограниченная correction M2-ENV-04-DOCKER29-MAPPING выдана C6. До final CI и targeted
C8 новой mapping/recovery boundary владелец не выполняет новые команды VM.
Это operational finding C0, прежние C8-01/02/03 CLOSED и их CI evidence сохраняются.
M2 IN_PROGRESS, PR24 Draft/open/not merged; live A09/A11 не выполнены.

**Source и применение.** Владелец подтвердил SOURCE_ACCESS_ADDED. Первая попытка
fetch остановилась до checkout; последующие isolated-agent diagnostics подтвердили
unlock/key-pair/repository read. Точную причину первого отказа/passphrase ошибку
ретроспективно не заявляем. Следующая попытка получила SOURCE_FETCH_VERIFIED_PASS,
SOURCE_EXACT_CHECKOUT_PASS, HEAD **c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14**,
tree **2994f5f259321f1a13639107a28dbcac52e1c403**; temporary SSH agent cleanup PASS.
Это actual VM checkout, в отличие от прежнего tested merge
d286d72cf9b6b0ee1089283ba4bbe4aeab230fe8 (CI37300041270 SUCCESS).
TELEGRAM_EGRESS_PREPARE_PASS и VERIFY_PASS получены. Deploy завершился
EGRESS_COMMAND_FAILED / ENV04_STOP_STAGE=DEPLOY / HELPER_DEPLOY_FAILED;
DEPLOY_PASS/PREFLIGHT_PASS отсутствуют. После этого deploy не повторялся.

Временный GitHub deploy key **asm-telegram-test-env04** должен быть отозван после
успешного fetch; SOURCE_KEY_REVOCATION_REQUIRED и напоминание переданы. Отдельного
owner подтверждения отзыва пока нет. Ключ входа на VM сохраняется; новых secrets нет.

| Фактическое состояние после остановки | Evidence владельца |
|---|---|
| Private state | `/home/asmoperator/.local/state/asm-telegram-egress`; original deployment-before.json PRESENT, deployment-after.json/rollback.json ABSENT |
| api/worker | Running; api healthy; restart count0; новые container IDs, те же images. ASM_TELEGRAM_ENABLED=false, четыре TG fields пустые |
| Relay | telegram-egress running, restart count0; отдельной healthcheck нет, это не Telegram connectivity PASS |
| Unrelated runtime | frontend/postgres/scheduler/storage/telegram-ingress running, прежние IDs/images; postgres/storage healthy. migrate/storage-init exited0 |
| Pre-deploy reads | Accepted verify/snapshot/operator image checks PASS; private files/runtime unchanged; diagnostic SSH_EXIT=0 |
| Original preservation comparison | Accepted compare_deployment с прежним before и actual snapshot PASS: caller images/env/process/mounts/default gateway/actual SQL DB identity и unrelated containers |
| Preflight stop | caller_probe/api/DNS → AssertionError: UNSPEC MATCH, INET MATCH, INET6 MISMATCH. Worker/operator/readiness после этой точки не запускались; SSH_EXIT=1 |
| Cleanup | Только собственные temporary offline probes удалены; DIAG_PROBE_CONTAINERS_CLEANUP_PASS; private files/runtime unchanged |

Последующая **read-only mapping diagnostic** выполнила только чтения существующих
api/worker, host и Compose model. Контейнеры не создавались/не пересоздавались,
DB queries/Telegram HTTP не выполнялись. MAP_DIAGNOSTIC_COMPLETE_NO_CHANGES,
MAP_PRIVATE_FILES_AND_RUNTIME_UNCHANGED_PASS и SSH_EXIT=0 получены.

| Layer / параметр | api и worker |
|---|---|
| Engine / Compose | Engine29.8.2, API1.56, server GitCommit8af9fe3, client7fc2dff, Go1.26.8; Compose5.5.1 |
| Kernel / app image runtime | Host6.8.0-142-generic; Python3.13.15, glibc2.36 |
| IPv6 flags | Host и оба callers: all/default/lo disable_ipv6=0; default и egress networks EnableIPv6=false |
| Model extra_hosts | EXPECTED_IPV4=1, EXPECTED_MAPPED=1, прочие0 |
| Docker HostConfig.ExtraHosts | EXPECTED_IPV4=1, EXPECTED_MAPPED=1, прочие0 |
| Actual /etc/hosts | EXPECTED_IPV4=2, EXPECTED_MAPPED=0, прочие0 |
| NSS / resolver | files→dns, action blocks0, unknown modules0; единственный nameserver Docker127.0.0.11 |
| AF_UNSPEC / AF_INET, flags=0 | Два expected IPv4, все прочие0 |
| AF_INET6, flags=0 | Один посторонний native IPv6, expected mapped0 |
| Отдельный AF_INET6/AI_V4MAPPED | Два expected mapped; **диагностическая проба, не замена строгого preflight** |

**Установленная причина.** Reported Engine GitCommit разрешён в exact
**8af9fe3a36bab3e039862a2ab1cef1880c9b4d03**. C0 прочитал
[daemon/container_operations.go](https://github.com/moby/moby/blob/8af9fe3a36bab3e039862a2ab1cef1880c9b4d03/daemon/container_operations.go)
(Git blob7f9d30595de0e34c6f0b0f44d366b4e63821bdb8),
sandbox_options.go (ba05582dec2702e9cfc0a80c08078052ff4dd08d) и
etchosts/etchosts.go (436e788db136f3058f01169d6567c4f142282160).
Engine передаёт OptionExtraHost(host, ipAddr.Unmap()), поэтому mapped IPv6
преобразуется в IPv4 до записи hosts. Это согласуется с фактической границей
HostConfig→hosts на обоих callers; отсутствие host IPv6 или ошибка Compose model
не объясняют наблюдение. [Go Addr.Unmap](https://pkg.go.dev/net/netip#Addr.Unmap)
определяет именно это преобразование. Не утверждаем, что C0 запускал Docker
локально или проверял пакет/binary provenance VM сверх предоставленного receipt.

**Продолжение:** полный task/allowlist/регрессии — единственный активный M2_HANDOFF.
Нужны real Docker29 reproduction/fix, строгий mapping всех трёх callers и guarded
recovery от текущего state. Повторный deploy или snapshot перезапишет before
текущими container IDs: так продолжать нельзя. Original before должен сохраниться
byte-identical; новый deployment-after/PASS только после actual строгих проверок.
Допускается проверенный helper transition generated state, без wipe/rebaseline,
ручной правки hosts, global DNS/IPv6 и downgrade Docker на owner host.

Private env/profile/TLS, HTTPS two-field overlay и staged TG остаются прежними.
Прежние comparisons не считаются новой проверкой всех domain rows, Console login
или live delivery на VM. Rollback/активация/discovery/setup/webhook/send не выданы;
никакого automatic retry, app build/init/migrations/reset/down-v. После correction,
full CI и независимого targeted C8 C0 отдельно выдаёт filled owner recovery block;
до первого setup заново проверит срок подготовленного TEST billing interval.

### 0.6.12. C6 Docker29 correction — REVIEW и подготовленный recovery

**Статус REVIEW, до независимого targeted C8/C0 owner issuance.** §0.6.11 остаётся
фактическим состоянием VM. C6 не выполнял VM/live commands. Closed C8-01/02/03,
accepted app/images/HTTPS/staged-input/DB/TLS/deadlines/UNKNOWN границы сохраняются.
Exact final head/tree/tested merge/ordered parents и run/jobs — единый C6 receipt PR24;
source archives и оба clean-source gates должны соответствовать этому же final head.

**Реальная исходная regression:** CI37351449973 / job111903261317 SUCCESS,
head45f2af639afc791a5ff1c0613d18b90108066b9a,
tested merge0d2bd888cd396389dcecfdf05f3064d992cee107. До изменения mapping real
Docker29.8.2/server8af9fe3/API1.56/Go1.26.8 + Compose5.5.1 воспроизвёл отказ всех
трёх callers: HostConfig сохраняет mapped; hosts содержит два private IPv4;
AF_INET6 flags0 получает synthetic2001:db8::91. Public DNS/Telegram не использованы.
Runner kernel6.17.0-1022-azure, Python3.13.15/glibc2.36; это не owner kernel6.8.
Artifact11362024418 SHA256
`4bca452a1c57844f9f93af9eb27a36c0d45c2c903f56b70136a0a06089dea363`
содержит bounded model/HostConfig/hosts/resolver/versions и source/tested-SHA.

Mandatory disposable-runner lane устанавливает official Docker CE/CLI
`5:29.8.2-1~ubuntu.24.04~noble` из signed download.docker.com APT, проверяет signing
fingerprint `9DC858229FC7DD38854AE2D88D81803C0EBFCD88` и actual version/server commit.
Official Compose5.5.1 linux-x86_64 SHA256
`db1889184726840f75c4f9c001048430d4f25b3be3cb084d3ddd762bc0aed576` проверяется до install.
Эта установка относится только к disposable CI runner; на VM daemon не меняется.
CI37350175798 остановился на setup APT source mismatch; CI37350872633 на nullable
host/none IPAM inventory. Это дефекты нового harness, не доказательство mapping fix;
защитные assertions сохранены. После их исправления старый отказ воспроизведён.

**Исправление.** Второй native ULA listener pinned Xray обслуживает тот же fixed
upstream443 через прежний selected connection. Три callers получают IPv4 и native
IPv6 endpoints relay. Новая internal IPv6-only bridge имеет bounded /64 из
fd42:6173:6d00::/48, gateway::1/static relay::2 и upper /65 для dynamic allocations.
Проверяются collisions с Docker IPAM и host routes, собственные network identity и
reservation. Default gateway, root Compose, приложение, client/config blobs, pins,
TLS/SNI/Host, deadlines/retries0 и permissions/media не меняются. Host/DNS/sysctl
patches, mapped normalization и fallback отсутствуют.

| Boundary | Точные assertions / execution |
|---|---|
| E01 | `test_native_ipv6_inbound_keeps_exact_fixed_upstream_and_selected_connection`, `test_ipv6_ipam_collision_identity_and_static_reservation`; private owner/mode/no-symlink и canonical outside-checkout прежние |
| E02 | `docker29_probe.py`: old failure на exact Engine; `mapping_evidence` + `caller_probe`: model/HostConfig/hosts, все addresses и три flags0 families на api/worker/operator; `both_relay_families` подтверждает TLS и fail-closed IPv4/IPv6 после stop/recreate |
| E03/E04 | Прежние шесть real PG/TLS wire cases; readonly/media, effect→response loss/relay stop→UNKNOWN→restart; persistent counter1, bad TLS, permissions/media/private S3 сохранены |
| E05 fresh | Exact prepare/deploy/preflight/rollback на независимом двухфайловом HTTPS baseline; actual caller asm_local, Secure Console session, UNKNOWN/receipt,31 fingerprints/counter1 |
| E05 partial recovery | Old schema1/c29 + frozen old overlay + already-recreated callers; original before PRESENT/after ABSENT; exact CLI SIGKILL после manifest, повтор с baseline/staged drift STOP, resume без перезаписи before; completed retry без recreate; explicit rollback и те же durable checks |
| E05 interruption guards | `test_partial_recovery_interruptions_resume_without_rebaseline_or_false_success`: audit/generation/manifest/relay/callers/probe/after; `test_partial_recovery_drift_stops_before_runtime_mutation`: source/before/staged/DB/image/gateway; operation lock и immutable bundle |
| E06 | Unchanged `sh scripts/ci.sh`, `sh scripts/test_browser.sh`, оба clean-source gates + обязательная Docker29 lane; один final-head receipt PR24 |

Local focused59 PASS — только unit checks. Реальные execution reports должны показать
шесть transport cases + два отдельных E05 lifecycles; для каждого прежний held
180-second deadline сохраняется. Console/UNKNOWN rows создаются в actual caller DB,
не в соседней asm_test. Reports не содержат private profiles/env/keys. Ограничения:
synthetic peer/CA, не Telegram API; owner TLS/provider/live counters ещё не проверены.

CI37355302621 подтвердил native mapping, шесть transport cases и fresh lifecycle
на Docker29 и штатном runner; browser PASS. Следующий E05 case остановился на
empty-DB guard: первый case законно оставляет SEALED billing catalog. Fixture теперь
сохраняет неизменный исходный empty guard для fresh, затем требует exact fingerprint
всех31 таблицы после scoped cleanup и перед recovery. Три созданные catalog rows
сохраняются byte-for-byte; другие domain/auth rows обязаны отсутствовать. Catalog
не удаляется, trigger не отключается, тайм-аут180s и durable assertions прежние.

CI37356534441: foundation111920229766 и browser111920229503 SUCCESS. Оба штатных
scripts/clean gates,551 unit,390 PG/S3,111 frontend,27 browser,6 transport + fresh E05
и recovery E05 PASS. Exact recovery SIGKILL/resume и две drift rejections, повтор без
recreate и explicit rollback прошли; held recovery157s при неизменном180s. Это real
обычный runner; compatibility job111920229489 отдельно остановился на startup старой
DNS fixture до проверки mapping. Её fixed DNS .3 пересекался с dynamic IPAM pool;
теперь lower /29 зарезервирован, фактические caller addresses обязаны быть upper /29.
Исторический stderr был отброшен, конкретный прежний Docker response неизвестен;
добавлена bounded диагностика. Final-head full CI с исправленной fixture — PR24 receipt.

**Guarded state transition.** Root legacy config.json/route.env/runtime.json и
original deployment-before.json сохраняются byte-identical. Recovery-v1 хранит их
private immutable audit, старый manifest, frozen old overlay и input hashes;
recovery-v2 — новую config/route/runtime/state generation. После fsync/rename
единственный root state.json атомарно выбирает generation. Exclusive private lock
исключает concurrent mutations. Resume строго проверяет archive/current input hashes,
source/schema/image/model/actual DB/env/process/gateway и disabled callers. After/receipt
появляются только после strict mapping/readiness/preservation. Completed retry даёт
тот же receipt без recreate. Interrupted unpublished `.generation-*` не используются;
автоматическое удаление private audit и rollback отсутствуют. `prepare`, `deploy`
или `snapshot` не заменяют original before из partial state.

**Подготовленные команды (C0 заполняет exact accepted head после C8).** Это спецификация
helper invocation для последующей отдельной выдачи, не разрешение выполнять сейчас.
Prerequisites: exact clean checkout принятого нового SHA, прежний state directory700,
private files600 и прежние source/profile/env/images/disabled runtime. Никаких prepare,
app build/init/migrations/down-v/reset. Не подставлять tested virtual merge вместо PR head.

```sh
# C0 задаёт полный принятый NEW_SHA из final receipt после targeted C8.
: "${NEW_SHA:?C0 must supply the exact accepted implementation head}"
test "$(git rev-parse HEAD)" = "$NEW_SHA" || exit 1
python3 scripts/prepare_telegram_egress.py recover \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --from-sha c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 \
  --accepted-sha "$NEW_SHA"
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Expected markers: RECOVER_PASS и PREFLIGHT_PASS с префиксом TELEGRAM_EGRESS_. При
bounded STOP сохранить state/audit/original before; C0 разбирает drift. После
interruption тот же exact `recover` является явным resume, без repeated deploy/snapshot.
Никакого автоматического rollback. Если C0 отдельно выбирает rollback для schema2
(в том числе после interruption уже опубликованного manifest):

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Для ещё не опубликованного schema2 (исходный schema1/c29) отдельный explicit rollback:

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --from-sha c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 \
  --accepted-sha "$NEW_SHA"
```

Оба rollback сначала сохраняют Telegram=false при mapping, потом снимают route
api/worker и останавливают relay. Новые/старые private bridges и stopped relay
сохраняются как bounded inactive resources; application endpoints на них отсутствуют,
никаких ports наружу. Owner env/profile/staged inputs, volumes, before/after/audit/
durable receipts не удаляются. Recovery после recorded rollback даёт STOP. Следующая
активация/discovery/setup/webhook/send — только отдельный C0 шаг после приёмки.

## 1. Конкретное окружение и предварительные условия

После выполнения §0.2 выбран один вариант: **доступный оператору Linux host с Docker
Compose, двумя DNS именами и публично доверенными TLS сертификатами**. На нём отдельный
Compose project `asm-telegram-test`; только тестовые bot/Owner/Client и новый
synthetic Workspace. Это изолированный LOCAL deployment (`asm_local`), не production.
Процедуры Python также проверяют отдельный TEST target `asm_test`, если оператор
предоставляет его явным окружением. Существующую browser TEST fixture не переиспользовать.

Нужны заранее:

- Один точный **принятый runtime SHA из активного handoff**:
  **80e51c43e31541940f1ccf18b8281adf1a061748**, сохранённый чистый checkout на VM.
  Current main после PR23 — **22993f558c5e7e933c65e9c999933bd2e3ab41c4**;
  сравнение показало только три docs. Accepted base и runtime различаются явно
  по §0.5; приложение ради документации повторно не разворачивать.
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

**Live шаг после приёмки host. Для M2-ENV-03 брать pre-live env из §0.4 и остановиться до §4.**

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
ASM_TELEGRAM_BILLING_FROM=2026-10-02T00:00:00+00:00
ASM_TELEGRAM_BILLING_UNTIL=2026-10-09T00:00:00+00:00
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

Перед live setup C6 задаёт **явный конечный текущий TEST interval**, заменяет обе
example даты в готовой инструкции и фиксирует их один раз; оператор не выбирает
billing policy. При exact repeat даты сохраняются. Не подставлять новый `now()` при
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
отправок** в согласованном тестовом диалоге. Code-only поручение M2.4 само по себе не разрешало live sends. Текущий
разрешённый оператору шаг задаётся активным M2_HANDOFF/§0.5, без новых расходов. Подготовленные bot/accounts/secrets не заменяют доступный
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
