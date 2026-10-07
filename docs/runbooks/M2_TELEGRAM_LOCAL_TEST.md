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

### 0.2. Текущий порядок — accepted correction, owner recovery / 2026-10-06

Последний owner receipt: c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14/schema1;
original before PRESENT, after/rollback ABSENT, Telegram disabled/empty TG.
Independent C0 review accepted implementation0b7e24ee425ebb429bf87dfe382cbd3fab883028,
CI37385698548 all3 SUCCESS; C8-04/05 CLOSED. Полное evidence и ограничения — §0.6.15.
Единственный следующий owner шаг — выданный C0 checksum-guarded wrapper: exact
source checkout и штатные recover/preflight, preserving original baseline/private inputs.
Не повторять prepare/deploy/snapshot, app build/migrations/reset или automatic rollback.
Temporary source read access, если нужен, используется отдельно от ключа SSH на VM.
Accepted main22993f558c5e7e933c65e9c999933bd2e3ab41c4 прежний; PR24 Draft,
M2 IN_PROGRESS. Активация/discovery/setup/webhook/live A09/A11 остаются отдельным шагом.

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

## 0.6. TEST egress — R3 reviewed, actual CI/C8 pending / 2026-10-06 UTC

C0 scoped verdict — §0.6.22: R3 PASS, findings01/02/03 CLOSED в описанном scope.
Actual first R3 CI и ограниченная C0 foundation job capacity correction — §0.6.23.
C3-M2-ENV04-05 остаётся REVIEW до actual final integration CI и независимого C8.
R1/R2/R3 author evidence — §0.6.19; прежние C0 verdict/failed CI — §0.6.20–21.
Последний owner TLS receipt — §0.6.18. VM0b7e24ee/connect2, binding/ACK/receipts
сохраняются; source/image migration и owner-команды ещё не выданы.
Exact final SHA/CI/артефакты — единый receipt; status — TASK_REGISTER;
единственный активный этап и последующий C8 scope — M2_HANDOFF.

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

**После targeted C8 этот receipt дополнен §0.6.13: CHANGES_REQUESTED по04/05.**
Ниже implementation evidence и команды reviewed head; они ещё не разрешены для VM.

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

### 0.6.13. Targeted C0/C8 — CHANGES_REQUESTED по interruption/retry / 2026-10-06

**Owner issuance приостановлена; M2/ENV04 IN_PROGRESS.** Независимый targeted C8
новой mapping/recovery boundary выявил ровно два P2/E05 ниже. Прежние C8-01/02/03
CLOSED. Native mapping и ранее исполненные cases сохраняют положительное evidence;
VM остаётся в фактическом состоянии§0.6.11. Команды§0.6.12 пока не выдавать владельцу.

Reviewed head **94a402f3cf7c9d5ad9cd5837cd3d91d738fcf684**, tree
**2a1b4952514e3ce6c56207478ed330ab0d507a7a**; accepted main/base
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**.
Tested merge **cd3e2f7255ec5815385397264c135a75ab850a97**: ordered parents base +
reviewed head, same tree. [CI37358453152](https://github.com/Elefesys/ai-service-manager/actions/runs/37358453152)
SUCCESS: foundation111926725973, browser111926725853, docker29-compatibility111926725451.
Все три actual checkout logs совпали; оба штатных scripts и clean-source gates
прошли.551 unit,390 PG/S3,111 frontend,27 browser,6 transport +2 E05.
[C6 full receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6001161023)
сохранён; его авторские ограничения не скрываются.

C0 независимо сверил refs/tree/ordered parents/12-path allowlist; C0 и независимый
C8 сверили225 Git blobs и executable modes. C8 прочитал canonical architecture,
helper/overlays/tests/CI и raw execution logs, затем воспроизвёл новые failures
unchanged Python helper functions с настоящими private filesystem transitions.
Внешние Docker/DB/source boundaries локальных probes были synthetic substitutes;
Docker локально отсутствует. Это не ещё один Docker/VM run. ZIP-byte и225 archived
blob verification остаются C6 attestation; C0/C8 ZIP bytes повторно не скачивали.

| ID / severity / criterion | Trigger → actual result → impact |
|---|---|
| C8-M2-ENV04-04 / P2 / E05 | Schema1 owner .env без enabled key. Legacy entry helper1597–1598 сохраняет исходный env hash в recovery-v1 (1392–1396), rollback1097–1105 сам добавляет enabled=false. Interruption после env write либо первого recreate → повтор EGRESS_BUNDLE_CHANGED в atomic_bundle1302–1304, runtime repair calls=0. Before/audit/staged unchanged, route/relay остаются, rollback.json отсутствует. |
| C8-M2-ENV04-05 / P2 / E05 | После schema2 manifest interruption внутри relay up1498–1511 оставляет старый relay stopped/missing до running replacement. Повтор recover1485 → attestation1459–1460 → compare_deployment1021 обращается к after['telegram-egress']; KeyError/CLI bounded STOP, repair calls=0, before unchanged, after/recovery receipt ABSENT. Та же предпосылка блокирует legacy rollback при relay outage и после stop до receipt. |

Existing unit phase=relay (tests/test_telegram_egress.py914–920) вызывает interruption
после успешного command, когда synthetic relay уже running. Real CI делает SIGKILL
после manifest и затем successful recreate. Эти tests сохраняются, но они не покрывают
остановку между stop/remove прежнего relay и запуском нового.

**Положительное evidence.** Exact Docker29.8.2/server8af9fe3/Compose5.5.1 old-mapping
failure реально воспроизведён. Исправленный native endpoint сохраняет api/worker/
operator, AF_UNSPEC/INET/INET6 flags0 и строгую проверку каждого адреса. Два verified
TLS listeners того же pinned Xray/fixed upstream, fail-closed обоих семейств, private
IPAM/internal bridge/default gateway подтверждены tests/CI. Fresh lifecycle и
выполненный interrupted recovery сохраняют actual caller asm_local DB identity,
Secure Console session, UNKNOWN/receipt,31 fingerprints и persistent counter1.
Обычные jobs/scripts/gates, client/config/pins/TLS/retries/deadlines прежние.

**Решение C0.** Полную recovery/rollback readiness не принимать. Единственная
доработка — M2-ENV-04-RECOVERY-RESUME в верхнем M2_HANDOFF. Сохранить исходные
before/audit; зафиксировать разрешённую собственную disable-first дельту и ожидаемые
relay transition states, чтобы повтор продолжал ту же операцию. Общие drift guards
не ослаблять; unknown/foreign state, inputs/DB/images/gateway остаются STOP.
Нельзя обойти findings новым baseline, ручной правкой state/env, удалением relay
checks либо отказом от explicit legacy rollback. Добавить реальные isolated
failure/resume cases на exact29 и штатном runner, затем full final-head CI и targeted
C8 только04/05/изменённых инвариантов. Allowlist и требуемые негативные cases — handoff.

Owner source/schema1/state, images, env/profile/TLS, DB/S3/volumes/Console identities
сохраняются. Нет новых VM команд, повторного prepare/deploy/snapshot, automatic
rollback, secrets/provisioning заново или Telegram activation/discovery/setup/send.
Actual deployment/live A09/A11, owner merge и отдельный push/main CI впереди.
PR Draft/open/not merged; production/M3 не выдаются. Этот coordination меняет только
четыре документа; exact head/tree/tested merge/CI — PR receipt, без SHA-only commit.

### 0.6.14. C6 REVIEW — guarded recovery/rollback resume / 2026-10-06

CI37367018261 attempt2 после восстановления Actions реально исполнил exact Docker29:
6 transport, fresh/recovery, recover-stopped/recover-missing и legacy-disable PASS.
Следующий legacy-stop остановился до своего held-state baseline: test controller
ожидал dual-family relay, но предыдущий legacy rollback оставил stopped IPv4-only
container. Узкая коррекция harness перед каждым независимым fixture восстанавливает
только disposable seed relay из fresh model и проверяет оба private endpoints до
создания UNKNOWN/session. Original before/audit предыдущих cases и DB rows не
перезаписываются; sealed-catalog guard,180s и все assertions сохранены.
Это fixture sequencing defect, не runner incident; legacy-stop PASS и полный
final-head CI после коррекции ещё ожидаются в едином PR24 receipt.


Owner issuance остаётся приостановлена до targeted C8/C0 по04/05. VM/schema1 на
c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 не изменялась. Новые helper команды ниже
подготовлены для отдельной выдачи C0, не являются выполненным deployment.

### Реализация C6 — interruption/resume correction, REVIEW

Продолжение от coordination **6fcec41b25676d657a64f443bd804760b7a20520**,
tree **f793c432338540ebdbef2d50b08c1a9833c42180**; parent reviewed94a402f3 сохранён.
Coordination CI37362669654 завершился FAILURE с тремя cancelled jobs и недоступными
logs; повтор этого head не запускался. Это не execution evidence новой реализации.

До изменения helper воспроизведены reviewed failures: после own disabled env write
и caller recreate — EGRESS_BUNDLE_CHANGED; stopped/missing relay — KeyError до repair.
Локальный probe использовал настоящие private filesystem transitions и заменённые
Docker/DB boundaries; он не выдаётся за реальный Docker run.

Исправление: private immutable rollback-intent хранит исходные и точно вычисленные
disabled bytes, original baseline/input hashes и operation-before. Immutable stage
receipts разрешают продолжать ту же disable-first/remove/stop операцию; исходный
recovery-v1 и deployment-before никогда не переписываются. Completed retry сверяет
receipt/actual state и не пересоздаёт callers. Восстановление после начала rollback
запрещено. Перед recreate сохраняется exact generation intent; stopped relay проверяется
через all-container inventory, отсутствие допускается только для attested recreate/stop.
Foreign image/tag/config/entrypoint/env/network/duplicate relay — STOP. Actual callers,
source/private paths, PG identity, HTTPS/emptyTG, gateway и unrelated containers сохраняют guards.

Focused unit89 PASS (прежние59 +30); shell/Python syntax, Ruff и diff checks PASS.
Реальная обязательная lane расширена четырьмя отдельными bounded E05 fixtures:
recover-stopped/recover-missing, legacy-disable/legacy-stop. Fault injection выполняет
настоящие Docker stop/remove или helper fsync/recreate boundaries, затем SIGKILL
в exact main; production fault flags отсутствуют. Это controlled recreate-gap,
не утверждение о случайном daemon crash. Старые fresh/recovery и шесть transport
cases сохраняются. Each held fixture180s, command/app deadlines и retries прежние.
У всех lifecycles same actual DB, Secure Console, UNKNOWN/receipt,31 fingerprints,
counter1, unchanged staged/audit/original before проверяются до PASS.

Final-head CI всех трёх jobs, обоих scripts и clean-source gates обязателен.
Точный результат исполнения/head/tree/tested merge+parents публикуется единым PR24
receipt; этот текст не объявляет ещё не выполненный CI успешным. Mapping и закрытые
C8-01/02/03 не менялись.04/05 закрывает только следующий targeted C8/C0.

| Finding / boundary | Точная regression / обязательное execution evidence |
|---|---|
| C8-04 own env delta | test_legacy_rollback_exact_disable_delta_resumes_each_interruption: env/callers/remove/stop/receipt; actual legacy-disable SIGKILL после fsync .env без enabled key и после первого caller recreate; retry/completed retry; original before/audit/staged bytes exact |
| C8-05 recreate gap | test_recovery_resumes_relay_recreate_gap_only_with_exact_intent; actual recover-stopped/recover-missing после schema2 manifest: real Docker stop/remove, SIGKILL, same-command retry → strict mapping/after/recovery receipt |
| C8-05 explicit rollback | actual legacy-stop: initial relay outage, SIGKILL после caller route removal, затем после stop до receipt, missing stopped container → retry; no false after, completed retry без recreate |
| Drift | runtime/staged/profile/baseline/intent/DB/image/gateway/unrelated unit negatives; existing real baseline/staged rejects; real foreign duplicate stopped relay/config-byte rejects; 31-table/actual DB guards прежние |
| E02–E04 и C8-01/02/03 | existing three-callers flags0/native mapping, TLS, readonly/media/private S3, send-loss→UNKNOWN→restart counter1; independent two-file HTTPS/emptyTG baseline и canonical outside-checkout state unchanged |
| E06 | три final-head jobs, оба штатных scripts и clean-source gates; exact runner versions/refs/artifact receipts в PR24 |

После отдельной приёмки C0 выбирает **одно** действие. Чистый exact checkout должен
совпадать с полным final head из принятого PR receipt; не повторять prepare/deploy/
snapshot и не переносить поля вручную. В private state ничего не удалять/не редактировать.

```sh
python3 scripts/prepare_telegram_egress.py recover \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --from-sha c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 \
  --accepted-sha "$accepted_final_head"
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Recovery interruption: повторить тот же recover с теми же refs. Explicit rollback
legacy schema1 — отдельная команда C0 (её retry использует те же аргументы):

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress \
  --from-sha c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14 \
  --accepted-sha "$accepted_final_head"
```

Для schema2, в том числе после publication manifest и recreate gap, explicit rollback:

```sh
python3 scripts/prepare_telegram_egress.py rollback \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

Rollback interruption: повторить только тот же rollback. Disabled inputs/stages
объясняются immutable intent, baseline не переснимается. Завершённый retry проверяет
существующий receipt без up. После начала rollback recover не является продолжением.
Любой unexpected drift — STOP и bounded error для C0; автоматического rollback,
activation/discovery/setup/webhook/send нет. Private runtime-before/disabled bytes
остаются только в owner state mode0600/0700, не входят в source/build/CI artifacts.
PR Draft, M2 IN_PROGRESS; live A09/A11, merge и main CI впереди.

### 0.6.15. Independent C0 acceptance — recovery/resume / 2026-10-06

**Независимая приёмка C0 — PASS; C8-M2-ENV04-04/05 CLOSED на указанном implementation.**
Проверку выполнил C0 отдельно от автора C6: source review, CI logs/artifacts и17
дополнительных локальных fault/retry/drift cases. Отдельный новый агент/чат C8 не
запускался; это независимый C0 verdict, не заявка на отдельный C8 execution.
Прежние C8-01/02/03 остаются CLOSED. M2 IN_PROGRESS, ENV04 REVIEW до owner recovery
и live acceptance; PR24 Draft, main не меняется, merge/production/M3 не выполнялись.

Accepted implementation **0b7e24ee425ebb429bf87dfe382cbd3fab883028**, tree
**14a4033b849c736235653a5a85ec9e5112bfe727**. Base/main
**22993f558c5e7e933c65e9c999933bd2e3ab41c4**. CI
[37385698548 attempt1](https://github.com/Elefesys/ai-service-manager/actions/runs/37385698548)
SUCCESS: foundation112018306287, browser112018306004, docker29-compatibility112018306249.
Actual checkout всех трёх logs **fdfbe35974fa548b722622132aa0edb3a30c9bf5**;
ordered parents base → accepted implementation, tree равен implementation.
Оба штатных scripts и clean-source gates выполнены; дополнительный Docker29 gate PASS.
581 unit,390 PG/S3,111 frontend,27 browser; на каждом Docker runner6 transport +6
lifecycles. Новый documentation coordination не заменяет этот tested implementation.

C0 самостоятельно скачал оба ZIP11379768145/11379612211: digest совпал с Actions;
в каждом source archive225 blobs/modes/inventory совпали с GitHub tree, tested-commit
совпадает с checkout, worktree-status пуст. Штатный Engine28.0.4/Compose2.38.2;
exact Engine29.8.2/server8af9fe3/Compose5.5.1. Все fresh/recovery/recover-stopped/
recover-missing/legacy-disable/legacy-stop выполнены. Before/after durable receipts
равны целиком,31 tables, actual api/worker DB identity во всех трёх фазах совпадает;
Secure Console session, UNKNOWN/receipt и wire counter1 сохранены. Held timeout180s
не повышен. Fixture sequencing исправлено до создания следующего held baseline.

| Finding | Основание закрытия |
|---|---|
| C8-04 / P2 / E05 | Immutable exact original/disabled dotenv intent и stage receipts; own disable write не меняет архивируемый baseline/hash. Real legacy-disable/legacy-stop interruptions/retries PASS на двух runners. C0 проверил retry после env/callers/remove/stop/pre-receipt, completed retry без recreate и byte-exact before/audit/staged. |
| C8-05 / P2 / E05 | Caller/DB preservation отделена от running relay. Stopped relay проходит строгую identity/config/network проверку; missing требует exact generation/stop intent. Real stopped/missing recovery PASS на двух runners; C0 также проверил explicit schema2 rollback из обоих gaps. Foreign relay/config и прочий drift остаются STOP. |

17 C0 checks:9 legacy interruption/retry variants (отсутствующий/preexisting false
ключ),4 stopped/missing × recover/explicit rollback,4 input/baseline/intent negatives.
Исполнялся неизменённый helper с настоящими private files/locks/atomic writes;
Docker/DB/source boundaries в этих17 checks — substitutes, не local Docker evidence.
Реальная Docker/PG evidence — проверенный Actions run выше. New VM execution нет.

Current operator source **c29aabd36f4e81ee2d4b835bd921fa2de1ae5b14**, schema1,
original deployment-before PRESENT, after/rollback ABSENT по последнему owner receipt.
C0-M2-ENV04-04 operational finding остаётся OPEN до успешного owner recover/preflight.
Следующий шаг: filled checksum-guarded wrapper переводит только clean existing
checkout на accepted implementation и вызывает штатные recover + preflight.
Проверить private inputs/TLS/images/disabled-emptyTG/unrelated runtime и original
before до/после; before не переснимать. Новых app build/migrations/init/reset/down-v,
prepare/deploy/snapshot, manual hosts, global DNS/IPv6/downgrade или автоматического
rollback нет. При interruption продолжать только те же refs и guarded helper;
при unexpected drift STOP. Telegram activation/discovery/setup/webhook/send не входят.

Для source fetch используется прежний отдельный read-only GitHub deploy key, только
если он ещё разрешён или владелец временно вновь разрешит его. После fetch — отозвать.
Это не SSH key входа на VM. Credentials/keys/profile не публиковать. Новых платных
ресурсов нет. Условный CI-resume завершён; успешный implementation CI не повторять.

The owner wrapper must use the tested implementation SHA, not this documentation
coordination. Its recover action may recreate only relay/api/worker; preflight includes
all three callers with AF_UNSPEC/AF_INET/AF_INET6 and flags0. Success proves local route
mapping/readiness/preservation only, not live Telegram connectivity or A09/A11.
No VM command has been run by C0 during this review. Any observed owner error gets its
own dated receipt before further action. Baseline/audit/runtime inputs remain private.

### 0.6.16. Owner recovery receipt и discovery / 2026-10-06

**Owner recovery + preflight PASS; C0-M2-ENV04-04 CLOSED по фактическому owner receipt.**
Владелец вернул `RECOVERY_RECEIPT_UTC=2026-10-06T07:58:54.204446+00:00`,
`RECOVERY_COMPLETE_PREFLIGHT_ONLY`, `SSH_EXIT=0`. Source exact
**0b7e24ee425ebb429bf87dfe382cbd3fab883028**, tree
**14a4033b849c736235653a5a85ec9e5112bfe727**. `TELEGRAM_EGRESS_RECOVER_PASS` и
`TELEGRAM_EGRESS_PREFLIGHT_PASS`; исходный baseline, private inputs/TLS и cached images
сохранены, Telegram runtime disabled с пустыми TG fields. Это owner execution;
прямого VM доступа у C0 нет. Mapping/recovery finding закрыт, live Telegram ещё не проверен.

Независимый C0 verdict на implementation остаётся PASS; C8-M2-ENV04-01/02/03/04/05
CLOSED в принятом scope. [Implementation CI37385698548](https://github.com/Elefesys/ai-service-manager/actions/runs/37385698548)
all3 SUCCESS; подробная проверка source/logs/artifacts — runbook§0.6.15 и единый receipt.
Documentation head e36a2c75d8ebb7071a6d1f88dab6fb20dfd7d297 также завершил
[CI37416231966](https://github.com/Elefesys/ai-service-manager/actions/runs/37416231966)
all3 SUCCESS: foundation112115338673, browser112115338704, docker29-compatibility112115338839.
Это не основание переводить VM с принятого implementation на новые docs commits.

**M2 IN_PROGRESS; ENV04 REVIEW до live acceptance; PR24 Draft/open, main unchanged.**
Единственный следующий owner шаг — однократный discovery через восстановленный TEST
egress, описанный ниже/в runbook§0.6.16. Setup/billing/binding/setWebhook, включение
api/worker и live A09/A11 выполняются отдельными шагами после его receipt. Успешные
recovery/preflight и implementation CI не повторять. Merge/production/M3 не выданы.
Временный GitHub deploy key `asm-telegram-test-env04` требуется отозвать после
успешного fetch; это отдельный source key, не SSH key входа на VM. Отзыв ещё не подтверждён.

### Единственное выданное действие — discovery

Файл `asm_telegram_discover_0b7e24ee.py`, 17825 bytes, SHA256
`a09d1016b13143f2b9175a946b11421adf98810bec3cacacf8d12fe02ec2ade0`. Файл и заполненный checksum-guarded PowerShell/SSH блок выдаёт C0 в чате.
Private secrets/IDs повторно вводить не нужно. Сохранённый staged Telegram flag может
быть false; временный Compose override меняет только `telegram-operator`: enabled=true
и image=тот же cached image ID. Полный resolved model сравнивается с исходным;
любое другое отличие STOP. `.env`, `.env.telegram`, helper, egress state/audit,
api/worker/scheduler и прочие существующие сервисы сохраняются до/после.

Wrapper держит штатный operation lock, проверяет exact source и recovery receipt,
вызывает штатные verify/model guards и использует accepted `compose_prefix` с
operator inputs. Единственная operator команда: `run --rm --no-deps --pull never -T
telegram-operator python scripts/provision_telegram_test.py --live --discover`.
Нового source fetch/build/pull/migrations/DB setup, restart, setWebhook или sends нет.
Local Docker config checks могут создать только штатные ephemeral verification
containers. Это C0 owner wrapper, не изменение helper/приложения.

`inspect_connection` сверяет ранее независимо подтверждённый Owner, bot и webhook.
При отсутствии сохранённого external ID и установленного webhook возможен ровно один
getUpdates: без offset/drop/pagination, с четырьмя allowed_updates; future update
subscription может измениться, поэтому provider state не объявляется неизменным.
Затем getBusinessConnection проверяет identity и возвращает actual rights.
Ноль/несколько candidates, foreign webhook/Owner или false rights — STOP без setup.

Approved synthetic contact `Synthetic Telegram test owner` и interval
**2026-10-02T00:00:00+00:00 → 2026-10-09T00:00:00+00:00** не пересчитываются:
wrapper сверяет staged значения и текущий UTC; expiry/drift STOP. Это ещё не DB billing state.

До provider вызова создаётся private attempt receipt
`/home/asmoperator/.local/state/asm-telegram-discovery-0b7e24ee.json` (mode600,
вне checkout/egress audit). После успеха он содержит проверенный external ID и rights,
source/staged/baseline hashes; ID/secret в stdout не выводятся. Existing attempt — STOP,
автоматического retry/polling нет. Временный override удаляется. После потери SSH или
STOP продолжать только по новому C0 действию, не удалять attempt receipt для повтора.

Ожидаемые markers: `TELEGRAM_SETUP_DISCOVERED`, `DISCOVERY_PRIVATE_RECEIPT_SAVED_PASS`,
`DISCOVERY_CONNECTION_ENABLED=true`, `DISCOVERY_CAN_REPLY=true`,
`DISCOVERY_PRIVATE_STATE_IMAGES_RUNTIME_UNCHANGED_PASS`, `DISCOVERY_COMPLETE_ONLY`,
`SSH_EXIT=0`. Это discovery, не inbound/private media/manual reply/Client receipt.
C0 проверил syntax и11 filesystem/orchestration cases (staged false/true, repeat,
interval/flag/model drift, wrong Owner, false rights, runtime/private drift, unresolved).
Docker/source/provider boundaries substituted; новый actual VM/live PASS не заявлен.

### 0.6.17. Confirmed Owner input correction / 2026-10-06

**Owner подтвердил перепутанные роли двух Telegram аккаунтов / 2026-10-06 20:02 +07.**
Первый аккаунт — владелец bot в BotFather; его можно использовать как test Client.
Второй — Business Owner,
к которому подключён @saasaimanagerbot. В staged expected Owner оказался numeric ID
первого аккаунта. Независимый ID второго предоставлен владельцем C0; значение остаётся
в private operator artifact/config, в публичных docs не публикуется. Скриншот второго
аккаунта показывает нужный bot, только выбранный test chat, включённые чтение/ответы;
это UI observation, не actual getBusinessConnection rights receipt.

Actual discovery на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** завершился
`TELEGRAM_SETUP_DISCOVERY_UNRESOLVED`, `SSH_EXIT=1`, при PASS всех source/recovery,
operator-only override, TEST interval и runtime/private preservation guards.
По source control flow успешно выполнены getWebhookInfo/getMe и один getUpdates через
permanent TEST route; distinct candidates для прежнего expected Owner не равно1.
Смена confirmed expected Owner исправляет известное input mismatch; наличие свежего
lifecycle события и actual connection rights ещё предстоит проверить.

Recovery/preflight PASS от2026-10-06T07:58:54.204446+00:00 остаётся действующим;
C0-M2-ENV04-04 CLOSED, C8-01/02/03/04/05 CLOSED в принятом scope. Original before/audit,
cached images и runtime Telegram disabled/empty сохраняются. **M2 IN_PROGRESS;
ENV04 REVIEW до live acceptance; PR24 Draft/open, main22993f55 unchanged.**
VM использует exact source0b7e24ee/tree14a4033b849c736235653a5a85ec9e5112bfe727;
новые docs commits на VM не переносить.

Implementation CI37385698548 all3 SUCCESS и его независимая C0 приёмка сохраняются.
Предыдущий docs-only7eb6250de53a2c1bcf61f852911aa10eecb66cb8:
[CI37434755147](https://github.com/Elefesys/ai-service-manager/actions/runs/37434755147)
browser112173734971 и docker29-compatibility112173735337 SUCCESS,
foundation112173735207 CANCELLED; all3 SUCCESS этому docs head не приписывается.
Merge/production/M3 не выданы. Отзыв временного source deploy key остаётся неподтверждённым.

### Текущее единственное owner действие — исправить expected Owner и проверить связь один раз

Файл `asm_telegram_owner_fix_0b7e24ee.py`, 24832 bytes,
SHA256 `13f8a1cb8b02f14f5718c17ddf8427e26b3c0ecfee9369727b5e7223caa91994`; checksum-guarded PowerShell stdin launcher выдаёт C0.
Разрешена атомарная замена только numeric value поля `ASM_TELEGRAM_EXPECTED_OWNER_ID`
в существующей private `.env.telegram` на независимо указанный ID второго аккаунта.
Bot/token/webhook secret, workspace/business IDs, HTTPS, contact и billing dates,
profile/TLS, runtime env, images и source неизменны. BotFather ownership не меняется;
Business bot не отключать/переподключать. Actual binding/setup ещё не выполнены;
непустой staged external connection ID требует STOP и отдельного review.

Wrapper держит прежний operation lock и проверяет exact source/recovery/runtime.
Original attempt `asm-telegram-discovery-0b7e24ee.json` сохраняется byte-exact.
Private correction intent `asm-telegram-owner-id-correction-0b7e24ee.json` связывает
его hash, source/baseline и exact staged before/after hashes; меняется только span
числового ID, quotes/CRLF/comments/прочие bytes сохраняются. Необъяснимый input drift,
дубликат key или чужой journal STOP. Intent позволяет распознать interruption до/после
atomic edit, до provider attempt; replay уже начатого provider attempt запрещён.
Оба файла лежат mode600 вне checkout и egress audit в `/home/asmoperator/.local/state`.
Original deployment/recovery archives не редактируются и не переснимаются; старый
recovery wrapper после intentional staged revision повторно не выдаётся.

После resolved model diff ровно по approved Owner выполняется одна accepted
`provision_telegram_test.py --live --discover` через прежний operator-only enabled=true
override и тот же cached image ID, `--no-deps --pull never`. Новый attempt/result —
`asm-telegram-discovery-owner2-0b7e24ee.json`, mode600. Existing new attempt — STOP;
старый файл не удаляется/не перезаписывается ради retry. При UNRESOLVED сохраняется
исправленный ID и безопасный terminal result; автоматического reconnect/polling нет.
Очередь без offset/drop/pagination; allowed_updates остаётся прежним набором четырёх
types. Provider subscription может измениться. IDs/provider payload в stdout не выводятся.

Новых build/pull/restarts/migrations, billing/binding/setWebhook, sends, source fetch
или automatic rollback нет. Contact/interval2026-10-02→2026-10-09 UTC проверяются
перед изменением и вызовом, не пересчитываются. Первоначальная C0 формулировка Owner
была неоднозначной; BotFather owner, Telegram Business Owner и Console UUID различены.

Ожидаются `OWNER_ID_CORRECTION_PASS`, `OWNER_ID_PRIOR_ATTEMPT_AND_RECOVERY_PRESERVED_PASS`,
`TELEGRAM_SETUP_DISCOVERED`, `DISCOVERY_CONNECTION_ENABLED=true`, `DISCOVERY_CAN_REPLY=true`,
`DISCOVERY_CORRECTED_INPUTS_STATE_IMAGES_RUNTIME_UNCHANGED_PASS`,
`DISCOVERY_COMPLETE_ONLY`, `SSH_EXIT=0`. Любой STOP вернуть C0, не повторять и не
удалять receipts. Успех поправки ID отдельно не считается discovery/live A09/A11 PASS.

C0 local validation:13 filesystem/orchestration cases,3 dotenv formatting variants,
5 immutable journal/interruption/tamper cases; full payload hash+compile через stdin
с LF/CRLF. Docker/source/provider boundaries substituted; actual VM edit/discovery
ещё не выполнены. Это исправление operator inputs, helper/app/API/DB контракт не менялся.

### 0.6.18. Verified TLS выше принятого connect budget / 2026-10-06

**Actual owner receipt 2026-10-06T18:10:05.409401+00:00, SSH_EXIT=0.**
Исправленный одноразовый token-free probe: DNS AF_UNSPEC/INET/INET6 PASS (7/0/0 ms),
TCP caller→relay IPv4 PASS (0 ms), ровно один verified TLS handshake PASS:
**TLSv1.3, 2523 ms, TLS_PASS_OVER_2S**. Лимит диагностического handshake был15 s;
в пределах2 s он не завершился, в пределах5 s завершился. Private inputs, все14
предшествующих receipts, images и существующий disabled runtime сохранены.

Это доказывает работоспособность TLS через выбранный маршрут в данной попытке и
наблюдённую задержку выше принятого connect=2 s. Не доказывает причину каждой прежней
ошибки, постоянную доступность Bot API или прохождение HTTP в общем5 s бюджете.
В этом probe не было HTTP, queue, DB или ACK. Прежний ACK остаётся NOT_ATTEMPTED,
его intent/result неизменны; retained=false означал неисполненную проверку.
Binding ранее committed (15:23:30Z), queue audit (15:44:48Z) увидел1 current +3
unmapped lifecycle events; свежая очередь после него не подтверждена.

Предыдущий probe17:58:12Z не выполнял DNS/TCP/TLS: C0 потерял @contextmanager при
сборке deadline, получил TypeError до resolver; это C0 artifact defect, не DNS
failure evidence. Исправленный embedded operator отличается ровно восстановленным
декоратором. Artifact111424 bytes, SHA256
`1cd0c50ecdc134778f912a4644b41f159f3d53df865df09759c64be6835049f0`.
Его once-only receipt сохранён; повторять исправленный или прежние scripts нельзя.
Подробные actual markers, ограничения local substituted tests и вся цепочка —
[единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

### Решение C0: узкая правка connect budget для code review

Наблюдаемое противоречие: доступный TLS путь занял2.523 s, тогда как M2_CONTRACT§10.6
и ENV04 runbook фиксируют connect≤2 s. C0 выдаёт **C3-M2-ENV04-05**: предложить и
проверить минимальную правку **connect2→5 s** в общем TelegramClient, без нового
env knob и без отдельного operator-only клиента. Это scope для изменения исходников
и review; текущий принятый контракт/VM остаются на2 s до приёмки новой реализации.

Pool2 s, read/write5 s, readonly5 s / send10 s / FETCH20 s wall deadlines,
lease30 s, pool≤4, TLS/hostname/SNI verification, fixed official origin,
trust_env=false, redirects/retries0 и UNKNOWN/no-resend semantics сохраняются.
Connect5 s не добавляется к общему deadline; общий deadline по-прежнему отменяет
операцию. При его срабатывании без доказанной wire phase нельзя объявлять send
definitely_unsent. Наблюдение2523 ms не обосновывает диагностические15 s в продукте.
Если целевые tests не проходят в этих границах, вернуть C0 evidence и предложение,
не повышать общие budgets и не менять маршрут самостоятельно.

Новая VM-команда сейчас не выдана. После reviewed patch и final-head CI требуется
независимый scoped C8; лишь затем C0 отдельно выдаёт C6 план перехода source/images
с сохранением recovery/binding/receipts, и owner получает готовый блок. Успех этой
диагностики не разрешает ACK replay, setWebhook, включение Telegram или live sends.

VM остаётся на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, cached images, Telegram disabled/empty.
Implementation CI37385698548 all3 SUCCESS относится к этому implementation.
Новая docs-only координация не является новым implementation/CI/live PASS.
**M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11; PR24 Draft/open.**
Прежние C0/C8 closures сохраняют свой scope. Merge/production/M3 не выданы.
Source deploy-key revocation остаётся неподтверждённым. Fixed COMPED TEST interval
2026-10-02T00Z→2026-10-09T00Z и committed request не пересчитываются.

### 0.6.19. C3-M2-ENV04-05 — R1/R2 history и R3 REVIEW / 2026-10-06 UTC

**Текущее исполнение: R3 возвращена на REVIEW; finding C0-M2-ENV04-05-03/P2
остаётся OPEN до verdict C0. Findings01/02 CLOSED на R2.** R3 evidence ниже.
Исторический receipt R2 до verdict C0: findings01/02 ещё OPEN,
local regression612 PASS/0 FAIL; actual integration gates/C8 тогда не выполнены.
Подробности R1/R2 сохранены ниже.
Это не разрешение интеграции/rollout и не новая owner/VM-команда.

#### История R1 — сохранённый failed candidate c009c854

Поручение прочитано на coordination
`62b018ccccffe87e97ebd34985886d472af583b1`, включая
[§0.6.18](https://github.com/Elefesys/ai-service-manager/blob/62b018ccccffe87e97ebd34985886d472af583b1/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md#0618-verified-tls-выше-принятого-connect-budget--2026-10-06).
Отдельный checkout/ветка `c3/m2-telegram-connect-budget` от
`9e165dd09f87663665e3dabae4f155e99e2639a6`, tree
`70c39e1dc2ef44050f743399198f444cb420023e`; восстановленный tree точно совпал.
Старые owner-команды этого base не являются действующей выдачей.
Coordination находится на3 docs commits впереди base; они не cherry-picked.

Production diff — ровно `connect=2` → `connect=5` в общем TelegramClient.
Pool2/read5/write5,4 connections, readonly5/send10/FETCH20 и lease30 неизменны;
TLS/hostname/SNI, official origin, trust_env=false, redirects/retries0 сохранены.
Наблюдение owner2523ms/18:10:05.409401Z остаётся отдельным
[историческим receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006),
не доказательством HTTP success или причины всех прежних failures.

**Результат кандидата не PASS: две cleanup regressions и strict source pin FAIL.**
Assertions не ослаблены, skip/xfail нет. TASK_REGISTER и active handoff вне allowlist
этой задачи, их disposition обновляет C0. Полные SHA/patch/commands передаются в C3
receipt без последующих SHA-only commits.

| Проверка | Фактическое local evidence / граница |
|---|---|
| Cold TLS old-fail/new-pass | На exact base client, временно восстановленном через `git show 9e165dd:backend/src/asm/telegram/client.py`, новый тест падает до HTTP на connect timeout; затем восстановлена ровно однострочная правка. Новый client: TLS3.008s, полный строгий getMe3.013s<5s, TCP1/HTTP1, official Host/SNI. Это настоящий loopback TCP/TLS, без Telegram/relay/MockTransport |
| Общие deadlines | Trickle каждые0.2s не продлевает readonly5/send10/image20; readonly/send включают TLS3s. Read-stall и send connect/read phase bounds5s, pool wait2s/4 real sockets, wrong hostname/untrusted CA, redirect/no retry проходят |
| Cleanup blocker | Stalled TLS + readonly outer timeout и explicit cancellation: `TCP_PEER_STILL_OPEN accepted=1 closed=0`, pool уже пуст. Независимый local probe с обычным HTTPX backend и только loopback address routing: timeout5.006s, `DEPENDENCY_TIMEOUT`, `definitely_unsent=False`; peer не закрыт после client.aclose() и диагностического GC. Настоящий socket/resource defect, не только assertion pool |
| Source guard blocker | Прежний `test_canonical_source_rejects_added_byte_without_normalization` падает `EGRESS_APP_SOURCE_CHANGED`: helper намеренно pin-ит старый client blob. С exact base client этот test PASS. Helper/test не изменены |
| Полный local non-integration runner | `uv run --frozen pytest -q -s -m 'not integration'`: 593 PASS,3 FAIL,393 deselected; FAIL — две новые cleanup проверки и прежний strict source guard. Integration deselection не PostgreSQL evidence |
| Static checks | `uv run --frozen ruff check backend tests scripts migrations`, `uv run --frozen ruff format --check --diff backend tests scripts migrations`, `uv run --frozen mypy backend/src`: PASS,51 typed source files |
| Штатные Docker commands | `sh scripts/ci.sh` и `sh scripts/test_browser.sh`: exit127, `docker: not found`. `sh scripts/test_telegram_egress.sh`: exit1 на прежнем `TEST_RUNNER_CHECKOUT_AND_NONROOT_REQUIRED`; local shell — root, guard не обходился. Actual Docker29/PG/S3/relay и workflow clean-source gates не выполнены |

Новый `tests/test_telegram_connect_budget.py` автоматически собирается существующим
pytest runner. TEST CA/leaf создаются одноразово тем же OpenSSL strict X.509 способом,
что в прежнем relay lane; никакого runtime trust/config change. Новый client на case,
один TCP attempt, задержка на accepted raw socket **до начала TLS handshake**, без
warmup. Доставка только на loopback заменена через TEST transport, сам HTTPX/httpcore
TCP/TLS I/O настоящий. Timeout tolerance по monotonic: −0.2/+1.0s, cleanup observation
≤2s отдельно от product budget; positive cold readonly обязан уложиться **строго<5s**.
Server teardown не считается успешным client cleanup.

Подготовлены дополнительные **не исполненные локально PG assertions**:
`test_real_http_accept_lost_response_process_restart_never_second_wire_call` сохраняет
прежние disconnect/before+after-finalize cases и добавляет trickle до10s, fsynced
wire1, DISPATCHING/UNKNOWN, настоящий второй process с NO_CLAIM, DEAD/attempt1 и
runtime pool0/pg_stat_activity без чужой активной business transaction во время HTTP.
`test_fetch_twenty_second_wall_includes_cold_tls_metadata_and_trickle` использует
существующий FetchTransfer20s/PG/S3 fixture, две cold TLS3s фазы внутри общего срока,
READY retry/attempt1 и отсутствие upload intent. Existing real-relay cases не удалены;
их единственная адаптация — exact timeout assertion connect2→5 вместе с cold regression.
Ни эти prepared assertions, ни прежний CI37385698548 не означают PASS нового candidate.

**Предложение C0 перед продолжением:** отдельно согласовать cancellation-safe cleanup
незавершённого TLS без изменения budgets/UNKNOWN и dependencies. Local locked
httpcore1.0.9 `AnyIOStream.start_tls` закрывает stream в `except Exception`, а
`asyncio.CancelledError` — BaseException; `AsyncHTTPConnection._connection` ещё не
создан. Это согласуется с observed leak. Требуется владение raw stream и гарантированное
закрытие при cancellation; `client.aclose()` после потери pool entry недостаточно.
Не заменять outer timeout на definitely_unsent, не добавлять retry/warmup/новый env knob.

Второй scope request — после review итоговых client bytes синхронизировать **один**
strict expected blob в `scripts/prepare_telegram_egress.py`, сохранив точное сравнение.
Для текущего однострочного candidate конкретный **не применённый** diff:

```diff
--- a/scripts/prepare_telegram_egress.py
+++ b/scripts/prepare_telegram_egress.py
@@
-    "backend/src/asm/telegram/client.py": "53800d23c718910dd338cadee6ba595510c95ff9",
+    "backend/src/asm/telegram/client.py": "abe2cfc61297397ffc313d287364741403ccf5bf",
```

После correction/review этот blob необходимо вычислить заново; не принимать оба
варианта и не обходить source guard. Далее C0: actual штатный GitHub runner + exact
Docker29 lane, checkout/source artifacts и все clean-source gates на final reviewed
integration SHA, независимый scoped C8; только затем отдельное поручение C6 rollout.

VM не изменялась: implementation0b7e24ee425ebb429bf87dfe382cbd3fab883028, binding
committed, ACK NOT_ATTEMPTED, прежние receipts сохранены. Нет deploy/rebuild/ACK/
setWebhook/включения Telegram/send. Live A09/A11 не выполнены; M2 IN_PROGRESS,
ENV04 REVIEW, integration PR24 Draft/open. Candidate не готов к интеграции/rollout.

#### R2 — cancellation-safe cleanup и final pin, 2026-10-06 UTC

Активное поручение прочитано на coordination
`e4f018af92d344429df4beb224262d0c87e985b3`. Продолжена та же ветка
`c3/m2-telegram-connect-budget` от full candidate
`c009c8540146d0a16d44fccf662d6e4d50fc53b1`, без reset/rebase; R1 и исходный
base9e165dd09f87663665e3dabae4f155e99e2639a6 сохранены в истории.
Не выполнены push/integration в c6/main, PR merge или действия на VM.

`_OwnedTCPBackend` оборачивает только backend собственного HTTPX transport.
`_OwnedTCPStream` удерживает raw TCP transport до завершения handshake. Любой
BaseException из start_tls вызывает nonblocking `asyncio.Transport.abort()` и
повторно поднимается. Здесь нет await/checkpoint, ожидания flush/peer/close_notify,
нового таймера, Task или GC. Повторная Task.cancel во время abort не может прервать
синхронный участок. FD закрывает стандартный следующий callback asyncio; tests
проверяют и peer EOF, и fileno=-1 **до** client.aclose/server teardown.
При успешном TLS ownership передаётся прежнему httpcore HTTP connection.
Общий client, чужие streams, read/write/pool limits, deadlines и retry policy прежние.

Private seams: HTTPX0.28.1 `AsyncHTTPTransport._pool._network_backend`,
httpcore1.0.9 `AnyIOStream._stream`, AnyIO4.15.1 asyncio `SocketStream._transport`.
Область — существующий asyncio runtime, не универсальный Trio/backend plugin.
Сторонний код/site-packages и зависимости не изменены. Factory и разрешённая TEST
инъекция готового AsyncHTTPTransport оборачиваются одинаково; тестовая подмена
CA/destination не заменяет production cleanup. Будущий dependency update должен
повторно проверить эти seams, а не считать private APIs стабильным контрактом.

Окончательный client blob: **525381357de76ea1c570fd864f8df5e9781a87e2**.
Единственная изменённая строка `scripts/prepare_telegram_egress.py`:

```diff
-    "backend/src/asm/telegram/client.py": "53800d23c718910dd338cadee6ba595510c95ff9",
+    "backend/src/asm/telegram/client.py": "525381357de76ea1c570fd864f8df5e9781a87e2",
```

Config blob, IMAGE, source/image/recovery/legacy/drift guards не менялись. Старый
R1 blob abe2cfc… не допускается. Исторический source fixture в test сжат только
для компактности; после decode проверяется exact Git blob R1 и base-connect2.
Эта fixture не является normalization/allowlist в production guard.

| R2 assertion / критерий | Local результат |
|---|---|
| `test_stalled_readonly_total_deadline_and_release`, `test_explicit_cancellation_closes_real_socket` | PASS для factory/injected transport и stalled TLS/response; GC выключен. Peer closed и FD=-1 до teardown; outer timeout5s не definitely_unsent, cancellation пробрасывается |
| `test_repeated_cancel_during_owned_abort_preserves_original_and_leaves_no_task` | PASS оба factory paths; повторные cancel вводятся observer-ом только на одном transport в момент настоящего production abort. Исходный CancelledError/message сохранён, cancelling=3, abort1, завершение<1s, TCP1/HTTP0, нет новых живых tasks; observer не исправляет cleanup |
| `test_cancel_isolated_from_parallel_request_and_same_client_can_send_next_readonly` | PASS оба paths: закрыт только отменённый TCP; параллельный TLS socket остаётся жив, valid getMe завершается; следующий getMe тем же незакрытым client успешен, pool slots/tasks освобождены, нет повтора отменённого запроса |
| Cold TLS old2/new5 | Exact base client в изолированном process/source staging: FAIL2.005s, TCP1/TLS0/HTTP0. R2: TLS3.008s, strict readonly3.011s<5s, TCP1/HTTP1. На каждый case новый client, no warmup/retry. Checkout не подменялся |
| Прежние phase/trickle/cert/redirect/pool cases | PASS: pool2/read5/write5,4 connections; readonly5/send10/image20, TLS3s внутри readonly/send; UNKNOWN/proven-unsent прежние; bad hostname/untrusted CA и redirect отвергаются |
| Exact source pin | Прежний added-byte test и4 новых variants PASS: final bytes принимаются, base-connect2/R1/extra-byte/CRLF отвергаются; чужой image pin также FAIL как требуется |
| Cached-image source probe | 4 variants PASS: выполняется настоящий сгенерированный Python/hash probe по реальным files. Docker execution/path **substituted**, не actual image/Docker evidence; старые/изменённые client bytes отвергнуты |
| Full local non-integration | `uv run --frozen pytest -q -s -m 'not integration'`: **612 PASS,0 FAIL,393 integration deselected**,81.47s. Изменённые fixtures/assertions не заменяли failures пропусками |
| Static/contracts | `uv run --frozen ruff check backend tests scripts migrations`; `uv run --frozen ruff format --check --diff backend tests scripts migrations`; `uv run --frozen mypy backend/src`; `uv run --frozen python scripts/export_contracts.py --check`: PASS |

Исполнение: Python3.13.15, OpenSSL3.5.8, httpx0.28.1/httpcore1.0.9/anyio4.15.1.
Существующие timing assertions не ослаблены: timeout −0.2/+1.0s, positive readonly
строго<5s; peer cleanup observation≤2s отдельно от operation budget. Изменение
прежних TLS fixtures добавило socket/production-wrapper assertions и GC-off cases;
в `test_telegram_egress.py` прежние guards/tests сохранены, добавлены только связанные
source/image regressions. R1 direct-wire/PG/relay assertions сохранены без изменений R2.

Локально Docker по-прежнему отсутствует, shell uid0; guards не обходились. Actual
PG/S3/direct-wire/relay/exact Docker29, workflow clean-source gates, full CI на final
reviewed integration SHA и независимый C8 остаются обязательными незакрытыми gates.
C0 организует runner после review исправленного patch. Финальные head/tree/parents,
local tested SHA, точные script exits, clean-source evidence и CI IDs при наличии —
в C3 receipt; отдельные SHA-only documentation commits не создаются.

VM остаётся на0b7e24ee425ebb429bf87dfe382cbd3fab883028/connect2; binding committed,
ACK NOT_ATTEMPTED, receipts и runtime сохранены. Live Telegram не выполнялся;
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11. Findings01/02 закрывает только C0.

#### R3 — точная классификация offline readonly, 2026-10-06 UTC

Поручение прочитано на coordination `c50bef85b6c474287d8d26521f51315fa9c695a3`.
R3 продолжает ту же отдельную ветку от R2
`41f74346b56009bda53fa637ed5adeb3fbb7c507`, сохраняя её единственным непосредственным
parent; без reset/rebase. TASK_REGISTER/active handoff ведёт C0.

Actual [CI37523378682](https://github.com/Elefesys/ai-service-manager/actions/runs/37523378682)
проверял integration candidate `ad724e68614c2942b73eaae41e6d8802d1663b84` через
merge `f6c2bd6f574831ced9996c042818240b668f9175`. Логи jobs112474140017/foundation
и112474139579/exact Docker29 подтверждают одинаковый FAIL прежней строки446:
offline `DEPENDENCY_TIMEOUT/False` против `assert definitely_unsent`;
каждая relay/PG lane5 PASS/1 FAIL,32.47s/37.70s. Browser112474140023 SUCCESS,
27 journeys PASS; foundation/Docker29 clean-source steps SKIPPED после failure.
Это evidence R2/integration failure, не успешная проверка R3.

Причина изменения старой assertion: она предполагала connect2 < readonly5.
При connect5 внутри outer5 общий timeout не доказывает wire phase. Теперь
единственный offline `get_me()` допускает ровно пары `DEPENDENCY_TIMEOUT/False`
и `DEPENDENCY_UNAVAILABLE/True` для доказанного connect-phase отказа. Elapsed и
пустой provider ledger не превращаются в доказательство definitely_unsent.
Проверяется elapsed≤6s: прежний outer5 плюс максимум1s scheduling tolerance.
До/после offline REQUEST count остаётся1 от hold_readonly; SEND_EFFECT отсутствует.
Сохранены обе семьи mapping/no fallback, TLS CA/hostname, auth/DB/private S3 и
readonly после recreate. После всех assertions существующий record_pass записывает
offline elapsed/code/flag; общий deadline и production classifier не менялись.

Добавлен один parametrized real TCP regression
`test_real_tcp_refusal_is_proven_unsent_before_readonly_deadline`: bound loopback
port без listen резервируется на весь вызов, исключая close/rebind race; kernel
отклоняет connect. Обе factory/injected конфигурации используют production wrapper,
официальный origin и прежние budgets. Ровно один application/TCP attempt;
точно `DEPENDENCY_UNAVAILABLE/True`, elapsed<5s, нет установленного stream или
занятого pool slot. Исключения/HTTP transport/timeouts не mocked.

Local команда `uv run --frozen pytest -q -s tests/test_telegram_connect_budget.py
-k 'real_tcp_refusal or stalled_readonly'`: **6 PASS**,19 deselected,21.45s.
Fast refusal0.002s/0.001s; существующие4 stalled TLS/response cases подтверждают
`DEPENDENCY_TIMEOUT/False`,4.8≤elapsed≤6s и peer close/FD=-1 до teardown без GC.
Старые assertions этих cases не менялись; skip/xfail/collector bypass не добавлены.
Полный non-integration suite/static/source checks на final R3 SHA и точные команды,
head/tree/parent публикуются в C3 receipt без SHA-only документационного коммита.

Client blob `525381357de76ea1c570fd864f8df5e9781a87e2`, helper/pins/контракт,
budgets/retries и production classification byte-exact R2. Direct-wire/relay
UNKNOWN→restart→wire count1 и остальные guards/assertions не изменены.
Локального Docker нет: actual PG/S3/relay/exact Docker29, штатные scripts и workflow
clean-source gates не подтверждены R3. После patch review C0 организует actual
final integration CI, затем независимый C8. Finding03 остаётся OPEN до verdict C0.
VM/binding/ACK/receipts прежние; owner/VM-команды, deploy/rebuild, activation,
setWebhook, live sends и merge не выполнялись. M2 IN_PROGRESS, ENV04 REVIEW.


### 0.6.20. C0 scoped R2 verdict и runner handoff / 2026-10-06 UTC

**C0 scoped verdict: PASS; C0-M2-ENV04-05-01/02 CLOSED.**
C3-M2-ENV04-05 остаётся **REVIEW** до actual final integration CI и независимого C8.
Закрытие двух конкретных defects не заменяет эти gates и не разрешает rollout.

R2: **41f74346b56009bda53fa637ed5adeb3fbb7c507**, tree
**9200aed964f22fc073341f2d448a5d82598d39cc**, единственный parent
**c009c8540146d0a16d44fccf662d6e4d50fc53b1**; исходный base
**9e165dd09f87663665e3dabae4f155e99e2639a6** сохранён. R2 меняет6 разрешённых
файлов, cumulative R1+R2 —8. Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**;
helper меняет только одну строку SOURCE/client pin. Config/IMAGE/dependencies/locks,
остальные guards и утверждённые budgets/classifications прежние.

C0 повторил **32 адресных case:32 PASS,76.57 s** на Python3.13.15,
httpx0.28.1/httpcore1.0.9/anyio4.15.1. Cold TLS3.008s, строгий readonly3.012s<5,
одна попытка. Проверены factory и injected transport, GC-off peer EOF/FD=-1 до
teardown, outer timeout, explicit/repeated cancellation с исходной отменой,
изоляция параллельного запроса и повторное использование client, phase/trickle/
cert/redirect/pool cases, final/old/tampered source и generated cached-image probe.
Четыре соответствующих code/test blobs сверены с R2 byte-exact; staging основан
на ранее принятом source. Это scoped local loopback TCP/TLS evidence, не полный
R2 checkout/full-suite rerun, actual image/Docker/PG/relay или независимый C8.
Git subprocess и Docker boundary в source/image unit cases substituted;
сам hash probe исполнялся по реальным bytes.

C3 сообщил на final R2:612 non-integration PASS/0 FAIL,393 deselected,
Ruff/format/mypy/contracts и source_check(final_SHA) PASS. Эти полные результаты
пока C3-reported; C0 проверяет actual runner отдельно. Locked private seams wrapper
допустимы в выданном asyncio scope; при обновлении зависимостей нужны повторные
regressions. В C0 scoped review новых blocking findings не найдено.

| Finding | Статус C0 | Основание |
|---|---|---|
| C0-M2-ENV04-05-01 / P2 | CLOSED на R2 | Только незавершённый TLS TCP transport abort, без await/tasks/GC; исходная отмена, соседний запрос и client сохранены;32-case subset PASS |
| C0-M2-ENV04-05-02 / P2 | CLOSED на R2 | Exact final blob закреплён одной строкой; final bytes PASS, base/R1/tampered/CRLF и несовместимый image-probe FAIL как требуется; guards сохранены |

### Единственный активный этап — C0 runner verification, затем scoped C8

Repository `Elefesys/ai-service-manager`, integration branch `c6/m2-telegram-live`,
Draft PR24. C0 собирает candidate от coordination
**e4f018af92d344429df4beb224262d0c87e985b3** с R2 как вторым parent.
R1/R2 ancestry сохраняется; текущие C0 coordination records не заменяются старой
копией из ветки C3. Assembly для CI не переводит задачу в INTEGRATED и не является
merge PR в main. Final head/tree/ordered parents, tested PR merge и run/job/artifact
IDs дописываются в единый receipt после исполнения, без SHA-only docs commit.

Code/test files берутся byte-exact из R2; C0 разрешённые coordination edits:
`docs/TASK_REGISTER.md`, `docs/tasks/M2_HANDOFF.md`,
`docs/tasks/M2_CONTRACT.md`, `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md`.
Workflows/Compose/locks/migrations не менять. Применимы AGENTS,
Spec§§18.2/18.8/18.10, ADR239, M2_CONTRACT§§10.5/10.6/10.12,
Implementation Plan M2; оригиналы по SOURCE_MANIFEST.

Обязательные actual gates: штатные `sh scripts/ci.sh`,
`sh scripts/test_browser.sh`, включённая relay lane и exact Docker29 job;
PG/S3/direct-wire/relay, UNKNOWN после effect/lost response→restart→wire count1,
нет business transaction на HTTP, source/image/recovery/legacy guards,
все workflow clean-source gates. Проверить tested merge parents/tree,
source archives/worktree status и sanitized relay/Docker29 artifacts.
Никаких skip/xfail/assertion weakening/root guard exception/manual bypass.

После SUCCESS именно final candidate — единственная следующая выдача C0→C8:
независимый scoped review cumulative R1/R2 и разрешения C0, production cleanup/
повторной cancellation/изоляции, exact pin, unchanged budgets/TLS/UNKNOWN,
реальных runner evidence и границ VM migration. Read-only evidence review;
новые implementation changes только отдельным finding C0.
C8 возвращает exact reviewed head/tree, findings/PASS и evidence limits.
Старый C8 verdict/CI37385698548 не переносится на новый implementation.
После CI+C8 C0 отдельно выдаёт C6 source/image/recovery migration plan; сейчас
никаких migration/VM действий. Historical owner blocks не выполнять.

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
не изменяются. До отдельного C0 поручения после CI/C8 нет owner commands,
source fetch/rebuild/deploy, ACK/setWebhook/activation/sends.
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11; PR24 Draft/open.
Merge main/production/M3 не выданы; source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

### 0.6.21. Actual R2 runner blocker и C3 R3 / 2026-10-06 UTC

**C0 verdict: CHANGES_REQUESTED по новому C0-M2-ENV04-05-03 / P2 (OPEN).**
C3-M2-ENV04-05 возвращена в **IN_PROGRESS** на ограниченную R3.
Findings01/02 остаются CLOSED на R2: actual runner failure не относится к cleanup
или exact source pin. Независимый C8 пока не выдаётся; rollout не принят.

R2 **41f74346b56009bda53fa637ed5adeb3fbb7c507** сохранена в integration candidate
**ad724e68614c2942b73eaae41e6d8802d1663b84**, tree
**50f13bafc84b48c3e941764b5297fa9bdb13a273**; ordered parents
**e4f018af92d344429df4beb224262d0c87e985b3**,
**41f74346b56009bda53fa637ed5adeb3fbb7c507**.
PR tested merge **f6c2bd6f574831ced9996c042818240b668f9175** имеет тот же tree и
ordered parents main22993f558c5e7e933c65e9c999933bd2e3ab41c4 +candidatead724e68.
Сборка candidate не была merge PR/main или rollout.

[Actual CI37523378682](https://github.com/Elefesys/ai-service-manager/actions/runs/37523378682):
foundation112474140017 **FAIL**, exact Docker29 112474139579 **FAIL**.
В обоих одна ошибка:
`tests/test_telegram_egress_postgres.py::TelegramEgressPostgresChecks::test_readonly_tls_mapping_and_auth_db_s3_survive_relay_failure`,
R2/integration line446: `assert offline.value.definitely_unsent`.
Actual `TelegramError(DEPENDENCY_TIMEOUT), definitely_unsent=False`.
Каждая real relay/PG lane: **5 PASS/1 FAIL** (32.47s /37.70s).
Browser112474140023 **SUCCESS:27 journeys PASS**, его workflow clean-source PASS.
Docker29 actual Engine29.8.2/8af9fe3, Compose5.5.1 подтверждены; old mapped-host
failure воспроизведён. Source/image prepare прошёл; полный relay/recovery receipt
не создан из-за failure на postgres_wire.

C0 проверил оба ZIP SHA256 и все226 archive file blobs/modes: exact candidate tree,
recorded tested commit совпадает, recorded worktree-status пуст. Artifact IDs
foundation11440544000 /Docker29 11441466330. Их workflow clean-source steps
**SKIPPED**, не PASS: отдельная C0 проверка пустого status не заменяет execution gate.
Остальные полные backend/PG/direct-wire gates не завершились после ранней relay
ошибки. Итог browser/run и точные artifact digests — в едином PR receipt.

Диагноз по source control flow: прежняя assertion предполагала connect2 < readonly5.
Теперь connect5 включён в тот же outer readonly5; в наблюдённой stopped-relay
попытке общий deadline не даёт доказательства wire phase. Консервативный
DEPENDENCY_TIMEOUT/false соответствует принятому контракту. Сетевой fast refusal
может дать доказанный ConnectError раньше deadline; нельзя закреплять результат
всех offline requests одним флагом. Причина конкретного сетевого молчания/hop не
устанавливалась и не нужна для исправления ошибочного ожидания теста.

| Finding | Статус C0 | Решение |
|---|---|---|
| C0-M2-ENV04-05-01 / P2 | CLOSED | R2 cleanup,32 адресных C0 cases PASS |
| C0-M2-ENV04-05-02 / P2 | CLOSED | Exact final pin/old-tampered guards PASS; runner prepare прошёл |
| C0-M2-ENV04-05-03 / P2 | OPEN | Relay offline readonly assertion требует proven-unsent даже после общего deadline; R3 уточняет contract-aware test, без изменения production semantics |

### Единственное активное поручение C0 → C3 — R3 relay deadline assertion

Repository `Elefesys/ai-service-manager`; прежняя ветка/отдельный checkout
`c3/m2-telegram-connect-budget`. Продолжать от полного
**41f74346b56009bda53fa637ed5adeb3fbb7c507**; сохранить R2 непосредственным
parent, без reset/rebase. Исходный base9e165dd09f87663665e3dabae4f155e99e2639a6
и R1 сохранены. Текущий coordination handoff — этот документ на integration branch.
C3 не push в c6/main и не запускает historical owner scripts.

Разрешены:
- `tests/test_telegram_egress_postgres.py`: только коррекция offline readonly
  ожидания в указанном case и связанные точные assertions/timing evidence.
- `tests/test_telegram_connect_budget.py`: при необходимости один адресный
  deterministic real TCP regression для доказанного fast connect failure, если
  существующих cases недостаточно для обеих ветвей классификации.
- `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md`: добавить R3 evidence с сохранением
  R1/R2 истории; никаких новых VM-команд. TASK_REGISTER/active handoff ведёт C0.

Client/helper/pins/production classification не менять: финальный client blob
525381357de76ea1c570fd864f8df5e9781a87e2 остаётся прежним. Контракт менять не надо.
Никаких новых budgets, retries, warmup, force definitely_unsent, скрытого retry,
skip/xfail/markers/collector bypass или ослабления остальных assertions.

Требования:
1. Для stopped-relay readonly допускаются только согласованные пары результата:
   `DEPENDENCY_TIMEOUT / definitely_unsent=False` при общем deadline либо
   `DEPENDENCY_UNAVAILABLE / definitely_unsent=True` при доказанном connect-phase
   отказе. Проверять пару, а не просто любой exception/любой bool. Нельзя
   делать timeout proven-unsent по знанию test fixture, elapsed или отсутствию
   provider HTTP в ledger; этих сведений у production classifier нет.
2. Проверить bounded offline вызов в неизменном outer5s, с прежним тестовым
   допуском максимум+1s. Отдельно сохранить deterministic проверки outer5→false
   и proven connect-phase→true на реальном TCP/TLS; никаких mock timeouts для
   доказательства wire boundary. Не требовать ненадёжного одинакового порядка
   двух равных5s timers на разных runners.
3. Сохранить ровно один новый offline application call, отсутствие нового wire
   REQUEST/effect (до/после тот же ledger count1 от первого hold_readonly),
   fixed mapping обоих семейств/no direct fallback, TLS hostname/CA checks,
   production cleanup path. Прежние API auth/DB/S3/health при stopped relay и
   успешный readonly после recreate должны фактически дойти до исполнения.
4. Не ослаблять direct-wire/relay effect→UNKNOWN→restart→wire count1,
   отсутствие business transaction при HTTP, durability/recovery/legacy guards.
   Connect5/pool2/read5/write5, wall5/10/20, lease30, pool4, TLS verify,
   official origin/trust_env=false/redirects0/retries0 прежние.
5. Local full non-integration/static checks на final R3 плюс адресные classification
   cases; отсутствие Docker фиксировать как limitation, guards не обходить.
   C0 соберёт новый final integration SHA и повторит actual штатный runner,
   exact Docker29 и browser/clean-source gates. Только после green final-head
   evidence — независимый scoped C8.

Возврат C0: head/tree/единственный parent, R3 patch/list files, точное объяснение
старой неверной assumption и новых assertions, команды/results/timings и отдельно
неисполненные gates. R3 возвращается REVIEW; finding03 остаётся OPEN до C0 verdict.
Применимы AGENTS, Spec§§18.2/18.8/18.10, ADR239, M2_CONTRACT§§10.5/10.6/10.12,
Implementation Plan M2; ранее выданный R2 scope не расширяется автоматически.

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
не изменяются. До отдельного C0 поручения после CI/C8 нет owner commands,
source fetch/rebuild/deploy, ACK/setWebhook/activation/sends.
M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11; PR24 Draft/open.
Merge main/production/M3 не выданы; source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

### 0.6.22. C0 R3 scoped verdict и final runner/C8 / 2026-10-06 UTC

**C0 scoped R3 verdict: PASS; C0-M2-ENV04-05-03 CLOSED на R3.**
Findings01/02 остаются CLOSED на R2. C3-M2-ENV04-05 остаётся **REVIEW** до
actual final integration CI и независимого scoped C8; rollout не принят.

R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8**, tree
**bd72edd3a9b01bb5053478f96d5089289e8f2b38**, единственный parent
**41f74346b56009bda53fa637ed5adeb3fbb7c507**. Три разрешённых файла:
два tests и runbook. Production client/helper/pins/контракт/dependencies/locks
byte-exact R2; client blob **525381357de76ea1c570fd864f8df5e9781a87e2**.
R1/R2/R3 ancestry и failed candidate/CI37523378682 сохраняются.

Исправленная offline assertion проверяет ровно две согласованные пары:
DEPENDENCY_TIMEOUT/False либо DEPENDENCY_UNAVAILABLE/True; elapsed≤6s,
один application call, до/после REQUEST count1, SEND_EFFECT отсутствует.
Mapping обоих семейств/no fallback, CA/hostname, auth/DB/private S3 и readonly
после recreate сохранены. Ошибка не классифицируется по знанию fixture или ledger.
Новый real TCP refusal удерживает bound loopback port без listen на весь вызов,
проходит factory/injected production wrapper и проверяет один connect attempt,
точную UNAVAILABLE/True, elapsed<5s, отсутствие stream/pool connections.

C0 отдельно повторил `uv run --frozen --offline pytest -q -s --tb=short
tests/test_telegram_connect_budget.py -k 'real_tcp_refusal or stalled_readonly'`:
**6 PASS,19 deselected,21.39s**, refusal0.001s в обоих factory paths.
Неизменённые4 stalled TLS/response cases подтвердили TIMEOUT/False,
bounded5s и peer EOF/FD=-1 до teardown. Все non-doc tracked blobs локального
staging сверены с R3; четыре docs отличаются, полного R3 Git checkout/clean-source
C0 этим запуском не заявляет. Это real local TCP/TLS, не actual relay/PG/Docker.
C3-reported final614 PASS/0 FAIL,393 deselected и static/source/clean checks
сохраняются как author evidence до actual runner.

### Текущий этап — C0 actual runner; следующая выдача C8

Repository `Elefesys/ai-service-manager`; integration branch
`c6/m2-telegram-live`, Draft PR24. C0 собирает final candidate с ordered parents:
coordination **c50bef85b6c474287d8d26521f51315fa9c695a3** и
R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8**. Два test blobs — exact R3;
C0 согласует только TASK_REGISTER/M2_HANDOFF/runbook для слияния evidence и handoff.
Другие code/config/contract/workflow/lock/migration blobs не менять.
Candidate assembly не является INTEGRATED/VERIFIED или merge PR/main.
Final head/tree/ordered parents, tested PR merge, actual run/jobs/artifacts и
gate results фиксируются в едином receipt после исполнения без SHA-only commit.

Нужны SUCCESS именно final candidate: штатные ci.sh/test_browser.sh,
real relay и exact Docker29, обычные PG/S3/direct-wire и source/image/recovery/
legacy cases, все workflow clean-source gates. В обоих relay reports проверить
offline_readonly_elapsed_seconds≤6 и согласованную code/flag пару, завершённые
auth/DB/private S3/recreate assertions, durable effect→UNKNOWN→restart→wire count1,
нет business transaction на HTTP. C0 проверяет exact tested source/ordered parents,
оба source archives/worktree status, digests и реальные job logs. Local/mocks,
C3 reports и старый SUCCESS не заменяют actual final-head execution.

**Только после C0-подтверждённого all-gates SUCCESS — единственное следующее
поручение C8-M2-CONNECT-BUDGET-R3 (независимый scoped review).**
C8 берёт точный final integration head из receipt, отдельный checkout; исходный
общий base **9e165dd09f87663665e3dabae4f155e99e2639a6** и chain R1/R2/R3 сохранены.
Read-only review source/evidence; временные независимые probes вне tracked tree.
Implementation/CI/config/VM changes не выданы; новый defect вернуть C0 finding.

Проверить cumulative client connect2→5, production TCP/TLS ownership/abort при
outer и повторной cancellation, отсутствие утечки/GC/task reliance, сохранение
исходной отмены, параллельного запроса и client reuse; factory/injected path одинаков.
Проверить strict final source/image pin и неизменные recovery/legacy/drift guards;
R3 precise error/flag pairs и wire/timing assertions, обе deterministic branches.
Budgets connect5/pool2/read5/write5, wall5/10/20, lease30, pool4, official origin,
TLS verify/SNI, trust_env=false, redirects/retries0 и UNKNOWN/no-resend сохраняются.
Private HTTPX0.28.1/httpcore1.0.9/AnyIO4.15.1 seams ограничены locked asyncio stack.
Проверить actual normal/Docker29/PG/S3/direct-wire/relay/browser и clean-source
evidence без переноса старого C8 verdict; ограничения live и migration сохранить.

Возврат C8: exact reviewed head/tree/base, PASS либо findings с severity/file/evidence,
собственные checks отдельно от прочитанных CI результатов, закрытые и оставшиеся
границы. C0 final acceptance — после CI+C8, C6 migration получает отдельный scope.
Канон: AGENTS, Spec§§18.2/18.8/18.10, ADR239, M2_CONTRACT§§10.5/10.6/10.12,
Implementation Plan M2, originals по SOURCE_MANIFEST.

VM сохраняется на **0b7e24ee425ebb429bf87dfe382cbd3fab883028** /
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, прежние cached images,
connect2, Telegram disabled/empty. Binding committed; ACK NOT_ATTEMPTED/replay-blocked.
Private receipts/inputs/runtime и fixed TEST interval2026-10-02→2026-10-09 UTC
сохраняются. Source/image/recovery migration — отдельное последующее поручение C6
после CI/C8; старые owner blocks не запускать. Сейчас нет VM fetch/rebuild/deploy,
ACK/setWebhook/activation/sends. M2 IN_PROGRESS, ENV04 REVIEW до actual A09/A11;
PR24 Draft/open, main merge/production/M3 не выданы. Source-key revocation не подтверждён.
[Единый receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006).

### 0.6.23. C0 foundation job capacity / 2026-10-06 UTC

### C0 CI capacity correction — actual run37527283930 / 2026-10-06 UTC

Первый R3 integration candidate **f6ba33a37b8f35070c2a2471f9e1b386297c049f**,
tree **5a92a9fd51d001fe4fe9ef81b996dbafc7b689b2**, tested merge
**ecfacbb77fe490cd33ec12237197cdd6809160da**: browser112487381755 SUCCESS/27 cases,
Docker29 112487380957 SUCCESS/6 relay +6 lifecycle cases/clean-source.
Foundation112487381312 CANCELLED примерно на25-minute job limit: start20:33:01Z,
cancellation20:58:16Z. До остановки actual normal runner выполнил все6 relay cases
и6 lifecycle cases, static checks и **614 non-integration PASS** за90.26s.
Обычный393-case PG/S3/direct-wire suite начат, не завершён; final smoke/clean-source
gate не выполнены. Failure assertion в доступном логе не зафиксирована; полный CI
SUCCESS не заявляется. Это не новый C3 code finding и не разрешение C8/rollout.

Оба relay reports: все12 assertions PASS, одинаковые before/after fingerprints31
таблицы во всех6 циклах, UNKNOWN/session/receipts/wire1 сохранены. Actual offline:
normal Docker28.0.4/Compose2.38.2 — TIMEOUT/False за5.005s;
exact Docker29.8.2/8af9fe3/Compose5.5.1 — TIMEOUT/False за5.006s.
Artifacts11443883177/11443418323, ZIP hashes/226 source files/modes, tested merge
и пустой recorded worktree status проверены C0. Foundation workflow clean-source
SKIPPED; это не заменяется отдельной проверкой status. Полные digests — receipt.

**C0 разрешает и вносит одну инфраструктурную строку:**
`.github/workflows/ci.yml`, только `jobs.foundation.timeout-minutes:25→35`.
Measured normal relay stage завершился20:54:17Z, unit stage20:56:08Z: лимит25min
оставлял менее2min15s для393 PG/S3/direct-wire cases и final smoke. Запас35min
позволяет исполнить полный последовательный gate. Browser/Docker29 budgets прежние.
Ни одна command/assertion/collector/dependency не меняется; clean-source и artifact
steps сохраняются, continue-on-error/skip/xfail не добавляются. Product deadlines
5/10/20s, phase limits и recovery operation bound180s неизменны.
Это C0 integration/CI capacity scope, не расширение production R3 или C6 VM scope.

Новый final candidate — один commit поверхf6ba33a3; production/test blobs exact R3.
Выполняется новый полный трёх-job CI на этом SHA; прежние PASS не переносятся
на новый head как его результаты. Только после всех actual gates — C8 по выданному
scoped handoff. Findings01/02/03 CLOSED; C3 REVIEW, M2 IN_PROGRESS/ENV04 REVIEW.

### 0.6.24. C8 PASS, C0 acceptance и подготовка connect5 migration / 2026-10-07 UTC

### Приёмка C0 после независимого C8

Accepted implementation head **14f794b650c935c47ab1e78474fda0d1df0a7277**, tree
**72b824d85091076a025998a71e564deab805b1cf**, parent **f6ba33a37b8f35070c2a2471f9e1b386297c049f**.
C3 R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8** и ancestry R1/R2 сохранены;
общий implementation base **9e165dd09f87663665e3dabae4f155e99e2639a6**.
Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**.

C0 принимает переданный владельцем независимый отчёт **C8-M2-CONNECT-BUDGET-R3 — PASS**:
122 scoped tests PASS/77.49s и две отдельные пробы штатного AutoBackend PASS;
checkout до/после чистый. C8 проверил cancellation/repeated cancellation,
закрытие socket без GC, parallel isolation/client reuse, budgets/TLS/classification
и strict source/image pin. Новых findings нет; 01/02/03 не переоткрываются.
Это собственные проверки C8 по его отчёту, а не дополнительные запуски C0.
Docker/PG/S3/browser C8 локально не запускал; соответствующее evidence — final CI.

[CI37531243359](https://github.com/Elefesys/ai-service-manager/actions/runs/37531243359)
на этом head — все три jobs и workflow clean-source gates SUCCESS:
foundation112500874202 — 614 unit +393 integration PASS, smoke PASS;
browser112500873790 — 27 journeys PASS;
docker29-compatibility112500874064 — exact Engine29.8.2/8af9fe3, Compose5.5.1.
Оба runner исполнили 6 relay +6 lifecycle cases. Actual tested merge
**e0735be7e3bde206dee35d813f53f6c4b6a17179** имеет тот же tree и ordered parents
main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** + accepted head.
C0 ранее сверил оба source archives/digests/226 file blobs/modes/status;
C8 независимо повторил эту сверку. В обоих relay reports TIMEOUT/False за5.006s;
все шесть before/after fingerprints31 таблицы равны, UNKNOWN/Console/receipts/wire1
и real interruption/legacy/drift guards сохранены.
Artifacts: foundation11445453916 SHA256
`eec9f1f5a005378467a03afb9004336b4185e878b97ad145d261e01bca35d198`;
Docker29 11445178285 SHA256
`5effc5734732747f92f27e55876c14f2b84eec84835c8eb9a81c4daa71106329`.
Единственная дополнительная workflow-правка C0 — foundation25→35;
остальные job limits, commands/assertions, product deadlines и recovery180s прежние.

**C3-M2-ENV04-05 — VERIFIED в code/runner scope, включён в integration branch PR24.**
C0 findings01/02/03 CLOSED; C8 task и C0 runner verification — VERIFIED.
Это приёмка проверенного implementation, без main merge или live acceptance.
Coordination commit этого поручения изменяет только четыре документа;
его production/test/workflow bytes совпадают с accepted head. Его собственный CI
фиксируется отдельно: SUCCESS37531243359 относится только к accepted head.

Новый active task **M2-ENV-04-CONNECT5-MIGRATION** выдан C6 на repository implementation
и disposable CI, согласно [M2_HANDOFF](../tasks/M2_HANDOFF.md). Старый owner `recover`
не применять для обновления на новый SHA: current v2 требует того же source_sha,
а прежний from_sha ограничен LEGACY_SHA. Требуется отдельный exact predecessor/
target image/state transition, с immutable migration intent, resume и explicit
rollback, сохраняя original before/audit/receipts и все canonical данные.

C6 может добавить только scoped migration helper/tests/CI jobs, перечисленные в handoff.
Новые migration jobs на normal/exact Docker29 отделены от прежних трёх; их лимиты
и assertions не ослабляются. Полный final candidate CI и новый scoped C8 migration
path обязательны перед owner execution. Target owner SHA определяется по принятому
результату этой задачи, а не по неподтверждённому branch tip.
### Состояние owner VM и граница этапа

Последний owner receipt: VM source **0b7e24ee425ebb429bf87dfe382cbd3fab883028**,
tree **14a4033b849c736235653a5a85ec9e5112bfe727**, завершённый `recovery-v2`,
прежние cached images/connect2, Telegram disabled и TG runtime fields empty.
Это последняя подтверждённая запись, не новая проверка VM.
Original deployment-before и recovery-v1 audit/recovery receipts сохраняются.
Binding уже committed2026-10-06T15:23:30.786130Z; повторное billing/setup не выдано.
ACK NOT_ATTEMPTED; прежняя попытка оборвалась на getWebhookInfo до ACK.
Автоматический replay не разрешён; после будущей миграции нужен свежий queue audit,
а не предположение о сохранности прежних четырёх событий.

Fixed TEST interval **2026-10-02T00:00:00Z → 2026-10-09T00:00:00Z** и committed
request не пересчитывать. Если интервал истёк до live-продолжения — STOP и отдельное
решение C0 о новом тестовом доступе, без изменения уже committed request.
Source-key revocation `asm-telegram-test-env04` не подтверждён; read-only source
access/его отзыв проверяются при будущем owner issuance, приватные ключи не передавать.

**M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11; PR24 Draft/open.**
Этим поручением выданы repository implementation и disposable CI проверки.
SSH/VM fetch/build/deploy/restart, real Telegram HTTP/queue/ACK, activation,
setWebhook, sends, billing/binding mutation, main merge, production и M3 не выданы.
Старые owner-command blocks не запускать. После migration REVIEW: C0 review,
actual final CI и scoped C8 изменённого migration path; затем отдельная выдача
owner migration, fresh readonly readiness/queue review и live A09/A11.

Разделы1–6 ниже — общая инструкция/история. Они не заменяют текущий active handoff
и не разрешают повторный fresh setup, billing/binding, старые ACK или live sends.

<details>
<summary>Архив точного C0 receipt до приёмки C8; прежний статус C8 next</summary>

## C0 — R3 scoped PASS; actual final CI SUCCESS; independent C8 next / 2026-10-06 UTC

**C0 findings 01/02 CLOSED on R2; 03 CLOSED on R3. C3-M2-ENV04-05 remains REVIEW pending independent C8.** C0 runner gates verified; this is not live acceptance.

### Exact final source

PR24 head **14f794b650c935c47ab1e78474fda0d1df0a7277**, tree **72b824d85091076a025998a71e564deab805b1cf**, sole parent **f6ba33a37b8f35070c2a2471f9e1b386297c049f**.
Actual tested PR merge **e0735be7e3bde206dee35d813f53f6c4b6a17179**, identical tree; ordered parents main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** + final head.
C3 R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8**, sole parent R2 **41f74346b56009bda53fa637ed5adeb3fbb7c507**; R1 c009c854 and original base **9e165dd09f87663665e3dabae4f155e99e2639a6** preserved in ancestry. No reset/rebase.

R3 changed only two tests and runbook. Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**, helper/pins/contract/dependencies/locks remain exact R2. C0 added three coordination docs and one CI line: **jobs.foundation.timeout-minutes 25→35**. All product/test bytes are exact R3. Browser/Docker29 limits, commands/assertions/collectors, product deadlines and recovery-operation 180s bounds unchanged; no skip/xfail/continue-on-error.

### C0 scoped review

03 CLOSED: offline case accepts only **TIMEOUT/False** or **UNAVAILABLE/True**, ≤6s, one application call, unchanged REQUEST count1/no SEND_EFFECT; mapping/TLS/auth/DB/private S3/recreate assertions retained. Production classification unchanged.
C0 targeted **6 PASS/21.39s**: real TCP refusal 0.001s for factory/injected paths, exact UNAVAILABLE/True and one attempt/no stream; four stalled TLS/response cases preserve TIMEOUT/False, bounded5s and pre-teardown peer EOF/FD=-1. All non-doc staging blobs match R3; four docs differ, so this was not a full clean Git checkout rerun.
Prior R2 scoped C0 **32 PASS/76.57s** and cold TLS3.008s/readonly3.012s remain evidence. Owned TCP abort, repeated cancellation, GC-off/no tasks, parallel isolation/client reuse and strict source/image rejection reviewed. Locked private seams require dependency-update regression.

### Actual final execution

[CI37531243359](https://github.com/Elefesys/ai-service-manager/actions/runs/37531243359) **SUCCESS** on the exact final head:

- foundation **112500874202 SUCCESS**: **614 unit PASS/89.67s +393 PG/S3/direct-wire integration PASS/377.29s**;6 relay+6 lifecycle, static/contracts/build/reproducibility and HTTP/frontend smoke PASS.
- browser **112500873790 SUCCESS**:111 frontend unit+27 real journeys.
- docker29-compatibility **112500874064 SUCCESS**:6 relay+6 lifecycle; Engine29.8.2/8af9fe3, Compose5.5.1; old mapping failure reproduced.

All three workflow clean-source gates SUCCESS. Checkout logs and both archives resolve to the exact tested merge/tree above; both recorded worktree-status files empty.
Normal runner: Docker28.0.4/Compose2.38.2. Both relay reports: **12 assertions PASS**, offline **DEPENDENCY_TIMEOUT/False, normal5.006s/Docker29 5.006s**. All six31-table before/after fingerprints equal; UNKNOWN/Console/receipts/wire1, real interruption/retry/legacy and drift guards preserved.

- foundation artifact **11445453916**, ZIP SHA256 `eec9f1f5a005378467a03afb9004336b4185e878b97ad145d261e01bca35d198`.
- docker29 artifact **11445178285**, ZIP SHA256 `5effc5734732747f92f27e55876c14f2b84eec84835c8eb9a81c4daa71106329`.

C0 verified artifact API digest against downloaded ZIP SHA256, every **226 source file** and mode against the final Git tree, tested commit/ordered parents/tree, and actual clean-source step outcomes.

### Preserved first-R3 partial run and CI capacity decision

First candidate **f6ba33a37b8f35070c2a2471f9e1b386297c049f**, tree **5a92a9fd51d001fe4fe9ef81b996dbafc7b689b2**, ordered parents c50bef85b6c474287d8d26521f51315fa9c695a3 + C3 R3; tested merge **ecfacbb77fe490cd33ec12237197cdd6809160da**.
[CI37527283930](https://github.com/Elefesys/ai-service-manager/actions/runs/37527283930): browser112487381755 SUCCESS/27 journeys; Docker29 112487380957 SUCCESS/6 relay+6 lifecycle cases; both clean-source PASS. Foundation112487381312 CANCELLED at the configured25min boundary (20:33:01Z→20:58:16Z): normal6 relay+6 lifecycle, static checks and614 unit PASS/90.26s; ordinary393-case suite interrupted, final smoke and workflow clean-source not executed. No recorded assertion failure; full CI SUCCESS was not claimed.
Both first-run relay reports:12 assertions PASS; all six31-table before/after fingerprints equal, UNKNOWN/Console/receipts/wire1 preserved. Offline TIMEOUT/False: normal5.005s, Docker295.006s.
Verified first-run artifacts: foundation11443883177 SHA256 **05360dc9504e5e1c9d472402bd228af215ab3d6faee897322378ddd6de06a555**; Docker29 11443418323 SHA256 **bc0fe8c1b22edba91b2137b261ee06030a28525fb096d1e915df5845216228b8**. Both226 source files/modes/tested source/status verified; empty status did not replace the skipped foundation workflow gate.
Normal relay finished20:54:17Z and unit suite20:56:08Z, leaving under2m15s for393 integrations/final smoke. C0 increased only foundation's total CI allowance to35min and reran all jobs on a new head. Historical R2 run37523378682 and failed offline assertion remain in runbook§0.6.21; earlier failures are not erased or relabeled.

### Next handoff and boundary

**C8-M2-CONNECT-BUDGET-R3** may now begin independent scoped review per active M2_HANDOFF: cumulative R1/R2/R3, the one-line C0 CI allowance, execution/source evidence and migration limits. No prior C8 verdict is transferred. C0 final acceptance follows C8; C6 VM migration receives separate scope.
**M2 IN_PROGRESS; ENV04 REVIEW until actual A09/A11; PR24 Draft/open.** VM0b7e24ee/connect2/cached images/TG disabled-empty, committed binding, ACK NOT_ATTEMPTED/replay-blocked, fixed TEST dates/private receipts preserved. No VM actions/ACK/setWebhook/sends/main merge/production/M3. Source-key revocation unconfirmed.

</details>

### 0.6.25. Connect5 migration — candidate protocol and owner draft

Scope: repository implementation and disposable CI only. The following owner draft
is **not an execution authorization**. C0 must first accept the exact candidate,
all nine CI jobs and a new scoped C8 verdict. Findings01/02/03 and prior recovery
acceptance remain closed; they do not verify this new path. Exact final head/tree,
tested merge/parents, job/artifact IDs and digests belong in the single PR24 receipt
`https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006`.

The source migration preserves the existing owner checkout at exact
`0b7e24ee425ebb429bf87dfe382cbd3fab883028` and its private files. Prepare a **separate**
clean candidate checkout at the C0-issued final SHA, with its private `.env` copied
byte-for-byte from the predecessor (0600, same operator owner; no symlink). All
profile/staged/state paths still refer to the existing canonical private files.
Do not copy private files into Git or build context. No reset/rebase or overwrite of
the old checkout is part of this operation. The active runtime source is recorded
in state and attested image bytes; the two control checkouts remain immutable.

Before issuance C0 must supply the exact current last operator receipt **and its
independently accepted SHA256**. Do not derive the expected pin from whatever file
happens to exist. The chain must include BINDING_COMMITTED and the Owner ID correction
journal, if present. Read-only inventory checks the completed recovery receipt,
original baseline/audit, all private inputs, exact old app/operator images, HTTPS,
local Unix Docker context, actual DB and unrelated containers. A cached old operator
image whose copied Git files differ from exact0b7 is a blocker for C0, not permission
to rebuild or change its receipt. No discovery or live Telegram probe is needed.

Save the following as an operator-owned 0600 POSIX script outside both checkouts.
C0 substitutes the four placeholders in a concrete issuance; paths must obey the
helper's safe-path rules. Run one requested action at a time, under the helper's
nonblocking operation lock. These commands print only fixed markers/errors.

```sh
#!/bin/sh
set -eu
umask 077
candidate='/home/asmoperator/C0_CANDIDATE_CHECKOUT'
target='C0_EXACT_FINAL_CANDIDATE_SHA'
receipt='/home/asmoperator/.local/state/C0_LAST_OPERATOR_RECEIPT.json'
receipt_sha='C0_INDEPENDENTLY_ACCEPTED_RECEIPT_SHA256'
predecessor='/home/asmoperator/asm-telegram-test'
state='/home/asmoperator/.local/state/asm-telegram-egress'
from='0b7e24ee425ebb429bf87dfe382cbd3fab883028'
action=${1:?C0-issued action required}
case "$action" in
  migration-attest|migration-prepare|migrate|migration-preflight|migration-resume|migration-rollback) ;;
  *) exit 2 ;;
esac
cd "$candidate"
exec python3 scripts/prepare_telegram_egress.py "$action" \
  --state-dir "$state" --accepted-sha "$target" --from-sha "$from" \
  --predecessor-checkout "$predecessor" \
  --operator-receipt "$receipt" --operator-receipt-sha256 "$receipt_sha"
```

Order after a future scoped issuance: `migration-attest`, then
`migration-prepare` (600s including clean-source builds), then `migrate`, then
`migration-preflight` (each ≤180s). Preparation writes only private migration audit
and distinct images/tags; it does not recreate runtime. An interrupted preparation
may repeat after its archived inputs agree. An interrupted runtime operation uses
`migration-resume` with the same target/state/intent; never delete the journal or
manually edit `state.source_sha`. A completed `migrate` rechecks without recreating.

The immutable `migration-v3` bundle contains original byte archives, preparation,
old/new image IDs and rollback reachability, the source/tree intent, per-service
intent/result/done records and the final receipt. API/worker change; operator runs
from the new development image. Scheduler keeps its original ID/image, as do the
other unrelated services. State v3 retains recovery-v2 routes and binds the target
and intent hash. PASS requires equal actual DB identity and 31-table fingerprints;
Console/binding/private originals/UNKNOWN and original audit must remain intact.

Explicit rollback, only when issued: run `migration-rollback` from the candidate
controller. It restores the old images and exact old v2 state, preserving both new
audit and original receipts. Retry this same command after interruption or completion;
no automatic rollback occurs. Then use the preserved predecessor checkout for the
original read-only preflight:

```sh
cd /home/asmoperator/asm-telegram-test
python3 scripts/prepare_telegram_egress.py preflight \
  --state-dir /home/asmoperator/.local/state/asm-telegram-egress
```

After rollback, a forward migration stops on the retained rollback intent. C0 must
decide a new operation; do not remove the completed bundle. Foreign/dirty source,
missing/tampered receipt/archive/input, any unexpected image/tag/container/config/
network/DB change, nonlocal Docker, enabled/nonempty runtime or a deadline is STOP.
Keep evidence, do not send/ACK/rebind, and return the fixed error to C0.

For a future PowerShell/SSH issuance, transmit a saved literal script as stdin or
upload that script, rather than nesting `python3 -c` inside remote quoting. The
disposable lane checks PowerShell literal stdin → a local SSH argv shim → `sh -s`
with exact SHA/action/path round trips. It never invokes SSH or contacts an owner.
The final remote command is one argument (`sh -s -- migration-resume`, or the
C0-issued saved script path followed by its one approved action),
and PowerShell `$LASTEXITCODE` must be checked. Credentials/host selection and the
actual owner transport remain a separate C0 issuance, not part of these tests.

Disposable commands (dedicated fresh GitHub runner only):

```sh
sh scripts/test_telegram_egress_migration.sh intent
sh scripts/test_telegram_egress_migration.sh image
sh scripts/test_telegram_egress_migration.sh state
```

Each command runs on its own runner/shard, on normal Docker and exact
Engine29.8.2/server8af9fe3/Compose5.5.1. It builds exact old bytes, completes old
v1→v2 recovery with the old executable helper, holds a real committed binding,
COMPED/Console session/private image and UNKNOWN/wire1, and SIGKILLs the real
candidate at the selected forward and rollback boundary. Resume, completed retry,
real drift negatives and old-source rollback preflight run while the fixture stays
held ≤180s. No fake old-source/image check substitutes for that fixture.
`migration-*.json` records source/tree, old/new image maps, preserved hashes,
runtime identities, interruptions, timings and equal before/after fingerprints.
Separate artifacts include logs, quoting proof, tested commit, source archive and
empty worktree status. All original foundation/browser/Docker29 commands and clean
gates still run on the final candidate. No local Docker result or owner/live result
is implied by focused unit tests or by this runbook.

<details>
<summary>Historical C0 coordination receipt prefix, preserved before C6 migration REVIEW (2026-10-07 07:46:03Z)</summary>

## C0 — C8 PASS принят; C6 connect5 migration preparation выдана / 2026-10-07 UTC

**C3-M2-ENV04-05 VERIFIED в code/runner scope; C8-M2-CONNECT-BUDGET-R3 VERIFIED.**
C0 findings01/02 CLOSED на R2,03 CLOSED на R3. M2 IN_PROGRESS; ENV04 REVIEW до actual A09/A11.

### Принятый implementation и независимый verdict

Head **14f794b650c935c47ab1e78474fda0d1df0a7277**, tree **72b824d85091076a025998a71e564deab805b1cf**, sole parent **f6ba33a37b8f35070c2a2471f9e1b386297c049f**.
C3 R3 **3f0453904cefc8bd33b8fedd2095eb8c1a6089d8**; исходный base **9e165dd09f87663665e3dabae4f155e99e2639a6**. R1/R2/R3 ancestry сохранена.
Client blob **525381357de76ea1c570fd864f8df5e9781a87e2**.

C0 принимает переданный владельцем независимый C8 PASS: **122 scoped tests/77.49s +2 штатных AutoBackend probes PASS**, clean checkout до/после, новых findings нет. Cancellation/repeated cancellation, no-GC socket cleanup, parallel isolation/client reuse, budgets/TLS/classification и strict source/image pin проверены C8. C8 не запускал local Docker/PG/S3/browser; эти результаты подтверждены final CI. Собственные C8 проверки отделены от C0 execution.

[Accepted CI37531243359](https://github.com/Elefesys/ai-service-manager/actions/runs/37531243359) — **all3 SUCCESS** на accepted head:
foundation112500874202 — 614 unit +393 integration, smoke PASS;
browser112500873790 — 27 journeys PASS;
docker29-compatibility112500874064 — exact Engine29.8.2/8af9fe3, Compose5.5.1.
На normal Docker28.0.4/Compose2.38.2 и exact Docker29 исполнены все6 relay +6 lifecycle cases; все3 workflow clean-source gates PASS.
Tested merge **e0735be7e3bde206dee35d813f53f6c4b6a17179**, тот же tree; ordered parents main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** + accepted head.
C0 и независимо C8 сверили digests обоих archives,226 file blobs/modes, tested source/tree/parents и empty status.
Artifacts: foundation **11445453916**, SHA256 `eec9f1f5a005378467a03afb9004336b4185e878b97ad145d261e01bca35d198`; Docker29 **11445178285**, SHA256 `5effc5734732747f92f27e55876c14f2b84eec84835c8eb9a81c4daa71106329`.
Оба reports: TIMEOUT/False за5.006s,12 assertions PASS, шесть равных before/after31-table fingerprints, UNKNOWN/Console/receipts/wire1 сохранены.
C0 workflow change только foundation25→35; другие job limits/commands/assertions, product deadlines и recovery180s прежние.

### Coordination и единственное активное поручение C6

Coordination head **fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00**, tree **49fcbc2fbc92501314eb193a8ca2bfdeb5011535**, sole parent **14f794b650c935c47ab1e78474fda0d1df0a7277**.
Изменены только TASK_REGISTER, M2_HANDOFF, M2_CONTRACT dispositions и runbook§0.6.24. Все остальные **222/226 file blobs/modes**, включая client/helper/tests/workflow/locks, exact accepted base; remote tree и локальные document hashes сверены.
[Coordination CI37588932214](https://github.com/Elefesys/ai-service-manager/actions/runs/37588932214) — **IN_PROGRESS** на момент записи. Это отдельный run для documentation commit; accepted SUCCESS выше не переименован в его результат.

**M2-ENV-04-CONNECT5-MIGRATION — IN_PROGRESS, поручение выдано C6.**
[Единственный active handoff](https://github.com/Elefesys/ai-service-manager/blob/fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00/docs/tasks/M2_HANDOFF.md).
C6 продолжает PR24/branch c6/m2-telegram-live в отдельном checkout от coordination head, сохраняет его parent, без reset/rebase/force-push.
Выданы repository implementation, scoped tests и отдельные migration CI jobs на normal/exact Docker29. Требуется explicit completed-v2 source/image/state transition: exact predecessor attestation, новые pinned app/operator images, immutable intent, interruption/resume, completed retry без recreate и explicit rollback. Прежние gates/limits/guards и original baseline/receipts сохраняются.
Default recover допускает v2 только на том же source_sha и прежнюю v1→v2 from LEGACY_SHA; ручной state patch или ослабление pin запрещены.
Возврат C6 — REVIEW с exact final head/tree/parents, actual всех старых+новых jobs/artifacts и подготовленным owner draft. Далее C0 review и scoped C8 нового migration path, затем отдельная owner execution выдача.

### Owner/live boundary и сохранённая история

Последний owner receipt остаётся **0b7e24ee425ebb429bf87dfe382cbd3fab883028** / tree **14a4033b849c736235653a5a85ec9e5112bfe727**, recovery-v2, cached images/connect2/TG disabled-empty.
Binding committed, ACK NOT_ATTEMPTED/replay-blocked; private inputs/old receipts/DB сохраняются. Frozen TEST interval2026-10-02T00Z→2026-10-09T00Z не пересчитывается; source-key revocation не подтверждён.
VM/SSH/source fetch/rebuild/deploy/restart, Telegram HTTP/queue/ACK, activation/setWebhook/sends, billing/binding writes, main merge/production/M3 этим preparatory поручением не выданы. PR24 Draft/open, main22993f55 прежний.

Полный прежний C0 prefix receipt, включая first-R3 cancelled CI и точные hashes его archives, сохранён byte-for-byte в архивном block [runbook§0.6.24](https://github.com/Elefesys/ai-service-manager/blob/fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md). Исторический tail этого единого receipt ниже сохранён без изменений.

</details>

### 0.6.26. C0 migration review и scoped C8 issuance / 2026-10-07 UTC

**C0-M2-ENV-04-CONNECT5-MIGRATION — PASS в repository/CI scope.**
Новых блокирующих findings при source/evidence review не обнаружено. Это допуск
к независимому C8; migration task остаётся REVIEW до его verdict. Findings01/02/03
по connect5 client остаются CLOSED; новый migration path прежним C8 не покрыт.

Проверенный implementation head **3f65be7a60a1271247d04f23cbe0b151f82d65a1**,
tree **5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797**, sole parent
**374bee801baaf8a70955750be57577d5875b82bf**. Accepted base
**14f794b650c935c47ab1e78474fda0d1df0a7277**; coordination
**fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00** сохранён sole parent первого
implementation commit **5ea00119ddcee8508435246116a8a2d4b8970b0b**.
История линейная. Client blob **525381357de76ea1c570fd864f8df5e9781a87e2** прежний.
От coordination изменены ровно восемь разрешённых C6 файлов; domain/client/locks/
Compose/canonical originals и три прежних CI jobs не изменены.

[CI37607152590](https://github.com/Elefesys/ai-service-manager/actions/runs/37607152590)
— все **9 jobs и clean-source gates SUCCESS**. Tested merge
**88656774720f22a778b5421abc2ae820e4a9d285** имеет тот же tree; ordered parents:
main **22993f558c5e7e933c65e9c999933bd2e3ab41c4**, затем implementation head.
Logs подтверждают 661 unit, 393 integration, 111 frontend и 27 browser PASS.
Прежние 6 relay +6 lifecycle cases прошли на обоих Docker runners; шесть новых
migration shards покрывают intent/image/state interruption в обоих направлениях.

**Собственная проверка C0:** прочитаны code/contract/runbook delta; свежие refs,
jobs/logs; скачаны все восемь ZIP, проверены их SHA256 против GitHub digests.
В каждом архиве 228 Git blobs/modes, PAX source commit, tested-commit и пустой
worktree-status сверены с exact tree. Общий source.tar.gz SHA256
`03b4283d916f8a1d73a7417b4b9919ddbf0195a84a0f294542a6365bd3bfe8f9`.
C0 отдельно разобрал все шесть migration JSON: равные fingerprints31 таблицы и
DB identity, UNKNOWN/wire1, Console session, private original HTTPS200/anonymous403,
28 сохранённых файлов, before/after image maps, неизменный unrelated runtime,
SIGKILL/resume/explicit rollback и completed retry без recreate. Held durations
90.163–175.735s, все ≤180s. Оба прежних relay reports: TIMEOUT/False за5.005/5.006s,
все12 assertions PASS. Это независимая сверка actual CI evidence; новые локальные
Docker/PG/S3/browser/unit suites C0 не запускал и отдельный C8 не подменял.

Текущий C0 coordination меняет только четыре документа. Его code/test/workflow
bytes равны проверенному implementation; новый SHA не является tested target
CI37607152590. C8 проверяет exact **3f65be7a60a1271247d04f23cbe0b151f82d65a1**;
актуальное поручение читает из этого документационного descendant. Новый
coordination CI учитывается отдельно и не заменяет уже проверенное evidence.

| Задача | Статус | Следующий результат |
|---|---|---|
| C3-M2-ENV04-05 / C8-M2-CONNECT-BUDGET-R3 | VERIFIED | Принятый client scope, findings01/02/03 CLOSED |
| M2-ENV-04-CONNECT5-MIGRATION | REVIEW | C0 source/CI PASS; требуется независимый C8 |
| C8-M2-CONNECT5-MIGRATION | TODO, выдано | Scoped verdict на exact3f65be7a |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Owner migration и actual A09/A11 ещё не выполнены |

**Owner applicability не подтверждена этим CI.** Последний owner receipt:
exact0b7e24ee425ebb429bf87dfe382cbd3fab883028/tree14a4033b849c736235653a5a85ec9e5112bfe727,
completed recovery-v2, cached connect2 images, TG disabled/empty, binding committed,
ACK NOT_ATTEMPTED. После C8 C0 выдаёт сначала read-only attestation реальной
receipt DAG и старых image bytes. Несовпадение cached operator с exact predecessor
— STOP для C0, без rebuild, правки старого receipt или нового baseline.
Независимый pin последнего owner receipt и реальные image IDs ещё нужны.
Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z и committed request не меняются;
source-key revocation asm-telegram-test-env04 пока не подтверждён.

PR24 Draft/open, main прежний. Owner VM/SSH, live Telegram/queue/ACK/activation/
setWebhook/sends/billing mutation/merge не выданы этим review. После scoped C8:
отдельная owner выдача, migration/preflight, свежий readonly network/connection/
queue review и только затем actual A09/A11. Старый queue snapshot не актуализирован.


| Migration shard | Held seconds | C0 report check |
|---|---:|---|
| docker29-image | 175.735 | PASS |
| docker29-intent | 134.864 | PASS |
| docker29-state | 99.993 | PASS |
| normal-image | 162.278 | PASS |
| normal-intent | 90.163 | PASS |
| normal-state | 164.84 | PASS |

Поручение C8 — current M2_HANDOFF. C0 проверил source/evidence, отдельный reviewer
ещё не исполнил это поручение. Green CI не разрешает owner rollout автоматически.

<details>
<summary>Архив C6 receipt prefix — сохранён дословно перед C0 verdict</summary>

## C6 — M2-ENV-04-CONNECT5-MIGRATION — REVIEW (2026-10-07)

Repository/disposable scope; PR24 Draft. Next: C0 + new scoped C8. Findings01/02/03 CLOSED.

**Exact refs.** Accepted base `14f794b650c935c47ab1e78474fda0d1df0a7277`; coordination `fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00`, tree `49fcbc2fbc92501314eb193a8ca2bfdeb5011535`, sole parent accepted base. First implementation `5ea00119ddcee8508435246116a8a2d4b8970b0b` has sole parent coordination. Final head `3f65be7a60a1271247d04f23cbe0b151f82d65a1`, tree `5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797`, sole parent `374bee801baaf8a70955750be57577d5875b82bf`. No reset/rebase/force-push. Tested PR merge `88656774720f22a778b5421abc2ae820e4a9d285`: same tree; ordered parents main `22993f558c5e7e933c65e9c999933bd2e3ab41c4` + final head.

**Eight changed files from coordination:** `scripts/prepare_telegram_egress.py`, `scripts/test_telegram_egress.sh`, `scripts/test_telegram_egress_migration.sh`, `tests/test_telegram_egress_postgres.py`, `tests/test_telegram_egress_migration.py`, `.github/workflows/ci.yml` (additive jobs only), `docs/tasks/M2_CONTRACT.md` (§10.12), `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` (§0.6.25). Canonical sources, locks/compose/client unchanged; client blob `525381357de76ea1c570fd864f8df5e9781a87e2`. TASK_REGISTER/HANDOFF unchanged.

**Contract.** Exact predecessor `0b7e24ee425ebb429bf87dfe382cbd3fab883028` / tree `14a4033b849c736235653a5a85ec9e5112bfe727`, completed recovery-v2/connect2. Explicit private `migration-v3` immutable intent/archive pins from/to source/tree, original v2/audit/input hashes, independently pinned last operator receipt and before/after image map. Distinct runtime/development builds: exact tracked source/frozen pins, no private inputs; old images retained. Only api/worker recreated; disposable operator uses new development image. Scheduler/frontend/PG/S3/ingress/relay remain unchanged. State v3 binds target and intent; Telegram remains disabled/empty, private inputs and canonical data preserved. Strict guards retained; Env maps preserve all keys/values, reject duplicates. Runtime checked before/after effects.

`migration-attest → migration-prepare → migrate → migration-preflight`; interruption uses `migration-resume`; completed retry re-attests without recreate. Explicit `migration-rollback` resumes independently, restores old images and byte-exact v2 state, retains all audit, then old-source preflight PASS. No auto rollback/rebaseline. Runtime≤180s; preparation≤600s; held fixture180s; new jobs≤25min unchanged.

**Final CI:** [run37607152590](https://github.com/Elefesys/ai-service-manager/actions/runs/37607152590), attempt1, all9 SUCCESS and all clean-source gates SUCCESS.
661 unit +393 integration +111 frontend +27 browser PASS; lint/format/contracts/smoke PASS. Old connect probes: DEPENDENCY_TIMEOUT/False, 5.005/5.006s.

| Job | ID | Held migration s |
|---|---:|---:|
| foundation |112745314005|—|
| browser |112745313998|—|
| docker29-compatibility |112745313656|—|
| normal intent |112745314166|90.163|
| normal image |112745314141|162.278|
| normal state |112745314164|164.840|
| Docker29 intent |112745313885|134.864|
| Docker29 image |112745314143|175.735|
| Docker29 state |112745313917|99.993|

Actual commands: `sh scripts/ci.sh`; `sh scripts/test_browser.sh`; default `sh scripts/test_telegram_egress.sh` (both old6+6); `sh scripts/test_telegram_egress_migration.sh intent`, `image`, `state` on normal and exact Engine29.8.2/8af9fe3 + Compose5.5.1. Old-source recovery; real SIGKILL forward/rollback at all3 boundaries, resume/retry/drift STOP verified. Equal31-table fingerprints, binding/COMPED/Console, authenticated private original200/anonymous403, UNKNOWN/attempt1/wire1; hashes of28 preserved files unchanged. Local Python3.12 syntax/stdlib probes only; full tests ran in CI.

**Artifacts:** ZIP SHA256 below. All8 downloaded and independently checked: tested merge, empty status, every228 Git blobs/modes equal final tree. Common source.tar.gz SHA256 `03b4283d916f8a1d73a7417b4b9919ddbf0195a84a0f294542a6365bd3bfe8f9`. Disposable image IDs/proofs and hashes: `migration-{fault}.json` (`before_images`, `after_images`, `image_proofs`); owner IDs pending.

| Artifact | ID | ZIP SHA256 |
|---|---:|---|
|docker29-image|11476000216|`a0903f5c3eafb625e248f646bd752364f5756b0469c910720af3f44a773479f1`|
|docker29-intent|11475995076|`046237671f2fcc60af2f1c2a6b89055893420eea0e557faa51e15d1a4e0a0b6e`|
|normal-state|11475597739|`6005354d16f299d5fbf6a29b9829db483d09947ba2310adb4a5a8f30f1d07d10`|
|normal-image|11475159251|`c802d360b4327d872b47f9d79c6fdae0fb0fbb6ba64e0deec3c21102b593ac75`|
|docker29-state|11475148980|`283d2d24ad5789bd7181c95fa7aa3548d892a62f8cd9783232c07bfa0fb71050`|
|normal-intent|11474739648|`909865e9c30ca8351f083d447eb202f5d471ff1f5a1737d9e24951226f791f68`|
|docker29-compatibility|11476210989|`e6614c337273620b0d7a6f919e73fa6637f452a4ee0965cd1b5df7afff8b29ae`|
|foundation|11477965466|`1d115c4497da087addd72f165f0038ca795f422d05fe3e0d72a8c04011e60a1d`|

Prior failed runs remain evidence: 37600133325 fixture adapter; 37600915991/37601699017 Env order; 37602453024/37603467061 held180s exhaustion; 37604597954 all migration PASS but formatter gate failed. Fixed with semantic Env comparison, bounded concurrent read-only probes and exact formatter output; deadlines/assertions preserved.

**Owner draft:** [runbook §0.6.25](https://github.com/Elefesys/ai-service-manager/blob/3f65be7a60a1271247d04f23cbe0b151f82d65a1/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md#0625-connect5-migration--candidate-protocol-and-owner-draft) has inventory, exact CLI flags, separate old/candidate checkouts, prepare/resume/rollback/STOP instructions. C0 must issue paths and independent last-receipt SHA pin. POSIX/PowerShell literal stdin/local SSH-argv shim PASS, network_calls0; actual SSH transport untested. No VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing mutation/merge performed. Old queue snapshot is not refreshed. C0 prefix archived verbatim in runbook; retained evidence unchanged below.

</details>

### 0.6.27. C8-MIG-01 — rollback audit drift, C0 confirmation and C6-R2 / 2026-10-07 UTC

**C8-M2-CONNECT5-MIGRATION — CHANGES_REQUESTED. C0 принимает C8-MIG-01/P2.**
Migration остаётся REVIEW; owner migration не выдаётся до исправления, final CI
и targeted C8. Прежний C0 source/CI PASS дополнен новым подтверждённым blocker:
успешные CI scenarios остаются действительным evidence, но не закрывают audit drift.
Connect5 client findings01/02/03 и прежняя recovery acceptance не переоткрываются.

Проверенный code head **3f65be7a60a1271247d04f23cbe0b151f82d65a1**, tree
**5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797**, diff base
**fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00**. Текущий до этой coordination
docs-only head **e332989485dccba52c090c855f93a536b462c91b**, tree
**424edb39f7f2cbd183269f4c7dee924fb4ddb90d**; остальные224/228 blobs/modes равны
reviewed implementation. Helper blob **c5d91d930eb164d116b25564592f038ae425b83d**.

| Finding | Причина и наблюдаемый результат | Исправление / gate |
|---|---|---|
| C8-MIG-01 / P2 / OPEN | migration_results выбирает только текущее направление (lines2810–2818); migration_switch проверяет completion только выбранного направления (2890–2912). Изменённый forward-complete.database_sha256 допускает rollback двух images и новый preservation:PASS. После rollback удалённый/повреждённый forward-api-result не мешает повторному success. | Проверять существующий forward audit до первого rollback effect, закреплять inventory/hashes в immutable rollback intent, проверять на resume/retry; каждый done требует сохранённый result независимо от направления. Valid partial rollback сохраняется. |

**Собственный C0 reproducer:** Python3.12.14, exact helper blob выше; настоящие
migration_switch/migration_results/migration_manifest/migration_stage и private
file I/O. Docker/DB/prepared observations заменены repository fixture, без network.
Все три дефектных варианта воспроизведены: первый допускает2 simulated recreates,
оба completed retry возвращают success/0 new effects при нарушенном forward audit.
Два control cases: valid partial forward→rollback PASS/один rollback recreate;
actual-database observation drift → EGRESS_MIGRATION_CANONICAL_DATA_DRIFT до effects.
Это не actual Docker/PG execution и не доказательство потери БД или Telegram resend.
Проблема — ложное подтверждение целостности журнала и ненадёжное основание recovery.

По переданному владельцем C8 report:144 repository scoped PASS; дополнительные
22 PASS/3 FAIL воспроизводят один finding. C8 проверил чистый exact checkout и
самостоятельно сверил9 jobs,8 archives/228 blobs/modes,6 migration и2 relay reports.
Это C8-reported execution; C0 не заявляет прочтение отдельного C8 evidence.zip.
C0 собственный reproducer изложен в runbook§0.6.27.

Implementation CI37607152590 остаётся SUCCESS; отдельный docs CI37621480704 наe332
теперь также **all9 jobs/clean-source SUCCESS**, что C0 проверил свежим API read.
Ни один из них не содержит новых audit-tamper regressions и не закрывает C8-MIG-01.
Новый coordination commit меняет только четыре документа; его CI учитывается
отдельно. После code fix нужен actual final-head CI и targeted C8 по finding.

| Задача | Статус | Следующее действие |
|---|---|---|
| C8-MIG-01 | OPEN | Ограниченное исправление C6, затем targeted C8/C0 closure |
| M2-ENV-04-CONNECT5-MIGRATION | REVIEW | CHANGES_REQUESTED по одному P2 |
| C6-M2-CONNECT5-MIGRATION-R2 | TODO, выдано | Единственное active поручение в M2_HANDOFF |
| C8-M2-CONNECT5-MIGRATION | REVIEW | Первый review завершён; повтор после исправления |
| C3 client scope / findings01/02/03 | VERIFIED / CLOSED | Без новой code delta и без переоткрытия |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual owner migration/A09/A11 ещё впереди |

Последняя подтверждённая VM остаётся exact0b7e24ee/recovery-v2/connect2,
TG disabled/empty, binding committed, ACK NOT_ATTEMPTED. Никакой automatic replay.
Соответствие cached owner images exact predecessor и independently pinned receipt
DAG ещё не аттестовано; CI построил disposable old images заново. Этот отдельный
owner prerequisite не закрывается исправлением C8-MIG-01. Fixed TEST interval
2026-10-02T00Z→2026-10-09T00Z и committed request не изменяются.
PR24 Draft/open; VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/
main merge/production/M3 этим поручением не выданы.

Минимальные repository regressions на существующей migration_machine fixture:

```python
def test_forward_complete_tamper_requires_stop(migration_machine):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    path = m.bundle / "forward-complete.json"
    receipt = json.loads(path.read_bytes())
    receipt["database_sha256"] = "0" * 64
    e.write_private(path, e.encoded(receipt))
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects
    assert not (m.bundle / "rollback-complete.json").exists()


@pytest.mark.parametrize("corrupt", [False, True])
def test_completed_rollback_keeps_forward_result(migration_machine, corrupt):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    e.migration_switch(m.args, m.directory, reverse=True)
    path = m.bundle / "forward-api-result.json"
    if corrupt:
        e.write_private(path, b"not-json\n")
    else:
        path.unlink()
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects
```

На reviewed helper эти три negative assertions FAIL: ожидаемого EgressError нет.
C0 воспроизвёл эквивалентные операции отдельной Python stdlib probe, исполняя
исходную repository fixture с подставленными external observations и настоящие
file/audit guards. SHA Git blob helper c5d91d930eb164d116b25564592f038ae425b83d
проверен перед execution. Команда C0: `python mig01_probe.py`, Python3.12.14.
Результат: три C8_MIG_01_REPRODUCED, VALID_PARTIAL_ROLLBACK_PASS,
EXPECTED_STOP на DB observation drift. Exit0 у reproducer означает успешное
воспроизведение дефекта, а не passing acceptance. Никакого Docker/PG/VM/network.

Логика причины: после rollback-intent per-service result selector переключается
на rollback-*; forward completion вообще не читается при direction=rollback.
Allowlist migration_saved допускает имена новых audit files, но не закрепляет их
содержимое. Новый fix должен связывать оба направления и сохранить valid partial
recovery; ослабление проверки для испорченного журнала недопустимо.

<details>
<summary>Архив предыдущего C0 receipt prefix — дословно, до C8-MIG-01</summary>

## C0 — M2-ENV-04-CONNECT5-MIGRATION: source/CI PASS; scoped C8 issued (2026-10-07)

**C0 verdict: PASS in repository/CI scope; no new blocking findings.** Migration remains REVIEW pending independent **C8-M2-CONNECT5-MIGRATION**. Existing client findings01/02/03 CLOSED. M2 IN_PROGRESS; ENV04 REVIEW until actual A09/A11.

**Exact reviewed implementation:** head `3f65be7a60a1271247d04f23cbe0b151f82d65a1`, tree `5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797`, sole parent `374bee801baaf8a70955750be57577d5875b82bf`. Accepted client base `14f794b650c935c47ab1e78474fda0d1df0a7277`; coordination `fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00` remains sole parent of first implementation5ea00119ddcee8508435246116a8a2d4b8970b0b. Linear history retained; exactly8 allowed C6 files changed. Client blob `525381357de76ea1c570fd864f8df5e9781a87e2`; client/locks/Compose/canonical originals and prior3 CI jobs unchanged.

**Actual [CI37607152590](https://github.com/Elefesys/ai-service-manager/actions/runs/37607152590): all9 jobs and clean-source gates SUCCESS.** Tested merge `88656774720f22a778b5421abc2ae820e4a9d285`, same implementation tree; ordered parents main `22993f558c5e7e933c65e9c999933bd2e3ab41c4` + reviewed head. Logs confirm661 unit/393 integration/111 frontend/27 browser. Foundation112745314005; browser112745313998; Docker29compat112745313656. Migration normal intent/image/state:112745314166/112745314141/112745314164; Docker29:112745313885/112745314143/112745313917.

**C0 independent verification:** source/contract/runbook review, fresh refs/jobs/logs; all8 ZIP downloads/digests, every228 Git blobs/modes, tested merge/PAX/status checked. Common source.tar.gz SHA256 `03b4283d916f8a1d73a7417b4b9919ddbf0195a84a0f294542a6365bd3bfe8f9`. All6 migration JSON independently parsed: equal31-table fingerprints/actual DB identity, binding/COMPED/Console/private original200/anonymous403, UNKNOWN/wire1,28 preserved files, exact image maps/unrelated runtime, SIGKILL forward+rollback/resume, completed retry without recreate. Held normal90.163/162.278/164.840s; Docker29 134.864/175.735/99.993s; all≤180s. Prior6+6 cases on both runners retain TIMEOUT/False at5.005/5.006s. No new local Docker/PG/S3/browser/unit execution by C0; CI execution is distinguished from C0 evidence review.

**Coordination:** [`e332989485dccba52c090c855f93a536b462c91b`](https://github.com/Elefesys/ai-service-manager/commit/e332989485dccba52c090c855f93a536b462c91b), tree `424edb39f7f2cbd183269f4c7dee924fb4ddb90d`, sole parent reviewed implementation. Exactly four documents updated; other224/228 blobs/modes unchanged. [Coordination CI37621480704](https://github.com/Elefesys/ai-service-manager/actions/runs/37621480704) IN_PROGRESS when recorded; its result is separate. CI37607152590 is not attributed to this new SHA. C8 reviews exact3f65be7a, reads its [active handoff](https://github.com/Elefesys/ai-service-manager/blob/e332989485dccba52c090c855f93a536b462c91b/docs/tasks/M2_HANDOFF.md) from coordination. C8 has not yet executed this new review.

**Evidence preservation:** complete previous C6 receipt prefix, including all8 artifact IDs/SHA256, prior failed runs and owner draft limits, archived verbatim in [runbook§0.6.26](https://github.com/Elefesys/ai-service-manager/blob/e332989485dccba52c090c855f93a536b462c91b/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md#0626-c0-migration-review-и-scoped-c8-issuance--2026-10-07-utc). Historical receipt tail below unchanged. Owner protocol remains §0.6.25; accepted client/recovery evidence retained.

**Owner applicability remains unconfirmed.** Last owner state: exact0b7e24ee/tree14a4033b, completed recovery-v2, cached connect2 images, TG disabled/empty; binding committed; ACK NOT_ATTEMPTED/no automatic replay. After C8, C0 first issues read-only attestation of actual old images and pinned receipt DAG; independently accepted last receipt SHA and owner image IDs are still needed. Old-image byte mismatch is STOP, not permission to rebuild/rebaseline/alter receipts. Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z unchanged; source-key revocation unconfirmed.

PR24 Draft/open; main unchanged. No owner VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing writes/merge executed or issued by this review. Next: independent scoped C8 verdict, separate owner issuance, migration/preflight, fresh readonly readiness/queue observations, then actual A09/A11.

</details>

### 0.6.28. C6-M2-CONNECT5-MIGRATION-R2 — audit binding REVIEW

Scope: only C8-MIG-01/P2. Coordination `34835c260f737abbbe02a689f842b28fad50f323`
(tree `d6f065344f021fa9b78b635260b739b93327524e`) is the immediate parent of
the first fix commit; reviewed implementation3f65 and both C0 coordination commits
remain in ancestry. Final head/tree, exact CI IDs/digests and final results belong
in the single PR24 receipt, without a SHA-only follow-up commit. Finding stays OPEN
until targeted C8/C0 verdict; client findings01/02/03 remain CLOSED.

The helper now validates both historical directions before rollback effects and
before success publication. Stage order, exact result shape, done→result, source/
state/database/intent bindings and historical completion snapshots are mandatory.
Rollback intent schema2 fixes the exact forward filename/SHA256 inventory and the
validated forward runtime snapshot. Resumed or completed rollback compares forward
results to that frozen history, while rollback results still match actual runtime.
No damaged record is regenerated, no expected hash is refreshed on retry, and an
older rollback intent without this binding fails closed. The original v2 baseline,
forward records and operator/private files remain unchanged. Owner has no issued
migration operation yet; an existing incompatible bundle is a C0 STOP, not an
invitation to remove or upgrade its audit.

Regression mapping (all in `tests/test_telegram_egress_migration.py`):

| C8-MIG-01 requirement | Tests / assertions |
|---|---|
| Three exact repro + worker analogues | `test_forward_complete_tamper_requires_stop`; `test_completed_rollback_keeps_forward_result` for missing/corrupt api/worker results |
| Drift before first effect, interrupted and completed retry | `test_forward_result_drift_stops_rollback_at_every_phase`; no new effects, state/audit writes |
| Both directions' done/result and completion bindings | `test_done_requires_result_in_both_directions`; `test_completion_requires_exact_database_state_and_intent`; `test_audit_stage_binding_and_order_before_effects` |
| Immutable inventory, exact bytes and historical snapshot | `test_rollback_intent_pins_exact_forward_inventory` includes parse-equivalent changed bytes, removal, new completion and unknown file; `test_rollback_intent_schema_and_historical_binding`; `test_rollback_requires_exact_original_intent` |
| Partial forward and interrupted rollback remain valid | `test_valid_partial_forward_rollback_preserves_pinned_audit` at12 boundaries, three retries; `test_interrupted_rollback_results_keep_both_directions`; `test_pending_forward_caller_can_be_rolled_back` |
| Drift between effects / before PASS | `test_rollback_checks_forward_audit_after_each_effect`; `test_rollback_rechecks_forward_audit_before_success` |

Own pre-fix reproduction: five selected assertions failed on the reviewed helper
(the three original api cases plus worker missing/corrupt). After the fix, local
Python3.12.14/pytest9.0.2 executed251 scoped tests PASS (154 migration +97 existing
egress guards); Ruff0.16.7 lint/format PASS. Only external Docker/DB observations are
substituted in these unit fixtures; real private file I/O/helper state transitions
execute. Local environment lacks pytest-asyncio, producing one config warning;
these synchronous scoped tests do not require it. This is not local Docker evidence.

Exact commands from the candidate checkout, using the separate scratch test venv:

```sh
python -m pytest -q tests/test_telegram_egress_migration.py tests/test_telegram_egress.py
ruff check scripts/prepare_telegram_egress.py tests/test_telegram_egress_migration.py
ruff format --check scripts/prepare_telegram_egress.py tests/test_telegram_egress_migration.py
git diff --check
```

Final-head CI must execute unchanged `sh scripts/ci.sh`, `sh scripts/test_browser.sh`,
both old6+6 lanes and the six normal/exact Docker29 migration scenarios. Existing
actual SIGKILL/resume/rollback/retry cases now exercise schema2; their reports add
`rollback_audit_binding` with the seven exact forward hashes, immutable rollback
intent hash and equality after resume/completed retry. No extra Docker invocation,
deadline increase, runner/workflow change or weakened existing assertion is needed.
All nine jobs and clean-source gates must be SUCCESS before the final REVIEW receipt.

Owner runbook remains §0.6.25. VM/SSH/live Telegram/queue/ACK/activation/setWebhook/
sends/billing/merge were not performed. Exact cached owner images and independent
receipt-DAG attestation remain a separate future issuance. The prior queue snapshot
is not refreshed; no owner readiness or finding closure is claimed here.

<details>
<summary>Archived C0 receipt prefix — verbatim before the R2 return</summary>

## C0 — CHANGES_REQUESTED: C8-MIG-01/P2 OPEN; scoped C6-R2 issued (2026-10-07)

**C0 accepts and independently reproduces C8-MIG-01.** Migration remains REVIEW; owner execution blocked pending fix/final CI/targeted C8. Prior C0 source/CI PASS is superseded for this audit-preservation risk. Accepted client findings01/02/03 stay CLOSED; M2 IN_PROGRESS/ENV04 REVIEW.

**Reviewed code:** head `3f65be7a60a1271247d04f23cbe0b151f82d65a1`, tree `5e4d0c741a2dcf9967c9c1502bc97ca6a78c9797`; diff base `fbe13a24c8407ab94c1c4a997d4a3b50d7e41f00`. Helper blob `c5d91d930eb164d116b25564592f038ae425b83d`.

**Finding.** prepare_telegram_egress.py2810–2818 selects only the active direction's service result;2890–2912 checks only that direction's completion. Corrupt forward-complete.database_sha256 is ignored before rollback, which recreates both callers and writes preservation:PASS. After completed rollback, missing/corrupt forward-api-result permits successful retry. No DB loss or Telegram resend demonstrated.

**Own C0 reproduction:** Python3.12.14, exact helper blob verified, real migration/audit/private file guards; repository fixture simulates Docker/DB/prepared observations. Three reproduced violations: corrupted forward completion permits2 simulated recreates; deleted and malformed forward result each permits successful completed retry/0 new effects. Controls: valid partial forward rollback PASS (only api switched back); changed DB observation rejected EGRESS_MIGRATION_CANONICAL_DATA_DRIFT before effects. No local Docker/PG/VM/network execution. Repro details/snippets: runbook§0.6.27.

**C8-reported evidence:** clean exact checkout;144 repository scoped PASS;22 supplemental PASS/3 FAIL, all one finding. Independently reviewed9 jobs/8 ZIP digests/228 blobs+modes/6 migration+2 relay reports. C0 did not read the separate C8 evidence.zip; own reproduction confirms the report.

**CI remains evidence, not finding closure:** implementation37607152590 all9 SUCCESS. Previous documentation CI37621480704 on `e332989485dccba52c090c855f93a536b462c91b` now all9 jobs/clean-source SUCCESS, freshly verified by C0. Neither contains the new cross-direction audit regressions.

**Only active task: C6-M2-CONNECT5-MIGRATION-R2.** [Full handoff](https://github.com/Elefesys/ai-service-manager/blob/34835c260f737abbbe02a689f842b28fad50f323/docs/tasks/M2_HANDOFF.md). Check existing forward audit before rollback effects; pin its inventory/hashes in immutable rollback intent and recheck at resume/completed retry; every done requires its retained result in both directions. Preserve legitimate partial rollback, prior audit bytes, no repeated effects and all strict guards/bounds. Allowed files: helper, migration/egress unit tests, contract§10.12.1 and runbook only. No client/workflow/runner/Compose/lock/domain changes. Final actual9-job CI and targeted C8/C0 closure required; finding remains OPEN.

**Start C6 from coordination `34835c260f737abbbe02a689f842b28fad50f323`**, tree `d6f065344f021fa9b78b635260b739b93327524e`, sole parent `e332989485dccba52c090c855f93a536b462c91b`; retain it as first fix commit parent. Exactly4 docs changed,224/228 other blobs/modes unchanged; no reset/rebase/force-push. [Coordination CI37626628260](https://github.com/Elefesys/ai-service-manager/actions/runs/37626628260) IN_PROGRESS when recorded, separate from prior verified runs.

Previous C0 prefix archived verbatim in [runbook§0.6.27](https://github.com/Elefesys/ai-service-manager/blob/34835c260f737abbbe02a689f842b28fad50f323/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md); C6 full evidence remains in§0.6.26. Historical tail below preserved unchanged.

Owner applicability remains separate: actual cached old image bytes and independently pinned receipt DAG still unconfirmed; disposable CI rebuilt old images. Last owner state exact0b7e24ee/recovery-v2/connect2/TG disabled-empty; binding committed, ACK NOT_ATTEMPTED/no replay. Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z unchanged. PR24 Draft/open; no owner VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing writes/main merge/production/M3 issued or executed.

</details>


### 0.6.29. C0 R2 audit-fix review и targeted C8 / 2026-10-07 UTC

**C0 scoped R2 review — PASS; новых blockers не выявлено.** C6 передал готовый
результат; ожидание статуса REVIEW является передачей на приёмку, не незавершённой
реализацией. **C8-MIG-01/P2 остаётся OPEN до targeted C8/C0 verdict.** Migration
остаётся REVIEW; прежние client findings01/02/03 CLOSED. Owner execution не выдана.

R2 implementation head **f1c7aca724778e41671f2754bb85885507c4f14d**, tree
**4f28480ef1458141422a14514473c05f49193fe6**, sole parent coordination/base
**34835c260f737abbbe02a689f842b28fad50f323**. Это единственный fix commit.
Helper blob **00c347cde45e3c1a683330c6ee196815ef0a1e36**; client blob
**525381357de76ea1c570fd864f8df5e9781a87e2** прежний. Изменены четыре разрешённых
файла: helper, migration tests, contract§10.12.1, runbook§0.6.28. Workflow/runners/
Compose/locks/domain/DB schema/180s и600s bounds не изменены; ancestry сохранена.

Исправление проверяет оба направления audit, done→result и исторические
completion source/state/database/intent bindings. Immutable rollback-intent schema2
закрепляет exact forward inventory/byte hashes и проверенный historical runtime.
Resume/retry не переснимают pin; missing/changed/additional evidence и старый
unbound rollback intent дают STOP. Historical forward IDs не приравниваются
к новым rollback IDs; допустимые partial/result-done/state-completion gaps сохранены.

**Собственная проверка C0:** source/contract/test delta; прежние три repro на R2
теперь дают ожидаемый отказ без новых effects: COMPLETED_DRIFT,
SERVICE_RESULT_REQUIRED, INVALID_JSON. Ещё два controls PASS: valid partial
rollback (один нужный recreate) и CANONICAL_DATA_DRIFT до effects. Итого5 targeted
PASS, Python3.12.14, exact helper blob; реальные файловые guards/private I/O,
Docker/DB/prepared observations заменены repository fixture. C0 не запускал
новые локальные Docker/PG/browser/full suites; исходный extracted source сверён
по blobs/modes, это не заявление о новом полном Git checkout.

[Final CI37629816347](https://github.com/Elefesys/ai-service-manager/actions/runs/37629816347)
— все9 jobs и clean-source gates SUCCESS; logs768 unit/393 integration/111 frontend/
27 browser PASS. Tested merge **ebf1ec21f59eb8f887c779c3e55bf878eb15add5**, тот же
tree; ordered parents main **22993f558c5e7e933c65e9c999933bd2e3ab41c4** +R2 head.
C0 скачал все8 ZIP, сверил GitHub digests и228 Git blobs/modes каждого source
archive, tested commit/PAX и пустой worktree status. Общий source.tar.gz SHA256
`e78b0a27ea62bcd6e574e43de8e9ae73dee67ef2f077169d826a86664765b394`.
Все6 migration reports: schema2,7 закреплённых forward hashes равны final receipts,
rollback-intent hash совпадает, unchanged-after-resume/retry true. Fingerprints31
таблицы/private original200/403/Console/UNKNOWN/wire1/28 original files сохранены;
held104.530–168.047s≤180s. Оба прежних6+6 reports PASS, readonly TIMEOUT/False5.005s.
Полные job/artifact IDs и hashes сохранены в C6 receipt archive runbook§0.6.29.

C6-reported local251 scoped PASS и исходные5 failing regressions сохраняются как
author evidence; собственный дополнительный execution C0 описан отдельно выше.
Предыдущий docs CI37626628260 на34835 CANCELLED; final R2 all9 SUCCESS относится
к новому полному code candidate. Текущий C0 coordination меняет только четыре
документа, остальные224/228 blobs/modes exact R2; его CI учитывается отдельно.
Targeted C8 проверяет exact **f1c7aca724778e41671f2754bb85885507c4f14d**.

| Задача | Статус | Следующее действие |
|---|---|---|
| C6-M2-CONNECT5-MIGRATION-R2 | REVIEW | Исполнение завершено, C0 source/CI PASS |
| C8-MIG-01 | OPEN | Targeted C8 R2, затем closure C0 |
| C8-M2-CONNECT5-MIGRATION-R2 | TODO, выдано | Единственное активное поручение |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Owner migration и actual A09/A11 впереди |

Состояние owner VM здесь не проверялось: последнее exact0b7e24ee/recovery-v2/
connect2/TG disabled-empty, binding committed, ACK NOT_ATTEMPTED. Cached owner
images и independently pinned receipt DAG ещё требуют отдельной аттестации;
disposable CI не подтверждает их соответствие. Fixed TEST interval
2026-10-02T00Z→2026-10-09T00Z не пересчитывается. PR24 Draft/open; main прежний.
VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/merge не выданы.


C0 применил прежний standalone `mig01_probe.py` к exact R2 helper, заменив
expected vulnerable success на обязательный STOP/0 новых effects; два controls
оставлены прежними. Команда: `python c0_targeted_probe.py`, Python3.12.14,5 PASS.
Исторический rollback-complete в negative retry сохраняется как ранее созданный
audit; текущий вызов завершается EgressError, нового success/PASS не публикует.
Отдельно разобраны JSON всех6 schema2 reports:7 forward pins совпадают с final
receipts_sha256 и rollback-intent hash, unchanged-after-resume/retry true.

<details>
<summary>Архив C6-R2 receipt prefix — дословно до C0 targeted review</summary>

## C6 → C0 — C6-M2-CONNECT5-MIGRATION-R2 — REVIEW (2026-10-07)

**C8-MIG-01/P2 remains OPEN** pending targeted C8/C0 verdict. Client findings01/02/03 CLOSED. PR24 Draft; repository/disposable scope.

**Exact refs:** coordination/base `34835c260f737abbbe02a689f842b28fad50f323`, tree `d6f065344f021fa9b78b635260b739b93327524e`, sole parent `e332989485dccba52c090c855f93a536b462c91b`. First/final fix head `f1c7aca724778e41671f2754bb85885507c4f14d`, tree `4f28480ef1458141422a14514473c05f49193fe6`, sole parent coordination. No reset/rebase/force-push. Actual tested merge `ebf1ec21f59eb8f887c779c3e55bf878eb15add5`: same tree, ordered parents main `22993f558c5e7e933c65e9c999933bd2e3ab41c4` + final head.

**Four changed files:** `scripts/prepare_telegram_egress.py`, `tests/test_telegram_egress_migration.py`, `docs/tasks/M2_CONTRACT.md` (§10.12.1), `docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md` (§0.6.28). Client blob `525381357de76ea1c570fd864f8df5e9781a87e2` unchanged. Workflow/runners/Compose/locks/domain/DB schema and budgets unchanged; TASK_REGISTER/HANDOFF untouched; all 11 canonical source hashes PASS.

**Audit change:** validate both historical directions before rollback effects and before success: strict shapes/order, done→result, source/state/database/intent bindings and historical completion. New immutable `rollback-intent.json` schema2 has exactly `version`, `stage`, `intent_sha256`, `forward_audit_sha256` (exact filename/byte-hash inventory), `forward_runtime` (validated snapshot before rollback). Resume/retry retain inventory; forward results bind historical snapshot, rollback results actual runtime. Missing/changed/additional evidence or older unbound intents STOP; no re-pinning/reconstruction. Valid partial forward, result/done and state/completion gaps remain rollbackable; repeated rollback does not recreate completed services. Original/private/audit bytes remain intact.

**Regression → finding:** `test_forward_complete_tamper_requires_stop` covers original bad DB hash before effects; `test_completed_rollback_keeps_forward_result` covers missing/corrupt results for api AND worker. Matrix covers before/interrupted/completed rollback; both directions' done/result, source/state/DB/intent consistency, exact bytes/inventory, snapshot and inter-effect/pre-PASS drift. 12 partial boundaries, missing/stopped pending callers, repeated resume/retry, byte preservation PASS. Full named mapping: [runbook §0.6.28](https://github.com/Elefesys/ai-service-manager/blob/f1c7aca724778e41671f2754bb85885507c4f14d/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md#0628-c6-m2-connect5-migration-r2--audit-binding-review).

**Own local execution:** Python3.12.14, pytest9.0.2, Ruff0.16.7 in separate scratch venv. Before fix: 5 selected expected STOP tests FAIL (three original repro + worker analogues). Final head: `python -m pytest -q tests/test_telegram_egress_migration.py tests/test_telegram_egress.py` → 251 PASS/9.21s (154+97); `ruff check` and `ruff format --check` on both changed Python files PASS; `git diff --check`/AST/clean checkout PASS. One local asyncio_mode config warning; all scoped cases synchronous. Units execute helper/private I/O; Docker/DB observations substituted.

**Actual final CI:** [run37629816347](https://github.com/Elefesys/ai-service-manager/actions/runs/37629816347), attempt1, all 9 jobs and clean-source gates SUCCESS. 768 unit +393 integration +111 frontend +27 browser PASS; lint/format/contracts/smoke PASS.

| Job | Job ID | Artifact ID | ZIP SHA256 | Held s |
|---|---:|---:|---|---:|
|foundation|112821325574|11486882927|`7217f45c83b48696aad516744305ea1abda5756d8689f721deede5b0b3038f8c`|—|
|browser|112821325497|—|—|—|
|docker29-compatibility|112821325120|11487625781|`0fbe8e2b0fd24f0136bb26f1028215944333a8b29d46746abeca28b79c18c206`|—|
|normal intent|112821325727|11485953289|`9ebb5be3fc1d91708756382f0df5b56be206a1e0d4a9c2a5b90950f9915a4112`|104.530|
|normal image|112821325699|11486122195|`3b338a7ac2e15f784bbe36f6c75368b56abc5a1f3d11b8e7fece987690943248`|167.678|
|normal state|112821325715|11485409614|`08427ed85b36a2e87f8c9853556034e112e656e4c334dae07d8a5bca21e3e57d`|107.859|
|docker29 intent|112821325857|11485549529|`066064cfb985a46da8529d3a98a1e50cc7a38ea86824e53afd04f6cb2eb0e906`|168.047|
|docker29 image|112821325798|11486535142|`45ed85b90634b66a6baa9d31089035f33ca43011270c97712c38f612127b246e`|164.711|
|docker29 state|112821325554|11485953286|`edcefba2dab0bd6f7d89834721acac842a122fe1eaa2cda915707b18c670b4f7`|107.274|

Commands: unchanged `sh scripts/ci.sh`, `sh scripts/test_browser.sh`, both default `sh scripts/test_telegram_egress.sh` old6+6 lanes; `sh scripts/test_telegram_egress_migration.sh intent`, `sh scripts/test_telegram_egress_migration.sh image`, `sh scripts/test_telegram_egress_migration.sh state` on normal and exact Engine29.8.2/8af9fe3, Compose5.5.1. Six real SIGKILL/resume/rollback/completed retries exercised schema2. Held 104.530–168.047s; 180/600s budgets unchanged. Both old connect probes: DEPENDENCY_TIMEOUT/False at 5.005s.

**Artifacts:** all 8 downloaded; ZIP digests, tested SHA, empty worktree status and 228 Git blobs/modes checked against final tree. Common source.tar.gz SHA256 `e78b0a27ea62bcd6e574e43de8e9ae73dee67ef2f077169d826a86664765b394`. Every migration report's `rollback_audit_binding` version2 has 7 forward file hashes equal final `receipts_sha256`, matching rollback-intent hash, unchanged-after-resume/retry true. Equal31-table before/after fingerprints, binding/COMPED/Console/private original200/403, UNKNOWN/wire1 and 28 preserved files verified.

**Limits/next:** REVIEW only; C0 review → targeted C8/C0 closure. Owner runbook§0.6.25 remains a draft; cached owner images and independently pinned receipt DAG are not yet attested. No VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/merge performed. Prior queue snapshot not refreshed. C0 prefix archived verbatim in runbook§0.6.28; retained evidence follows unchanged.

</details>

### 0.6.30. C8-MIG-01 closure и C0-MIG-OWNER-01 receipt compatibility / 2026-10-07 UTC

**C0 принимает независимый C8 PASS и закрывает C8-MIG-01/P2 на R2.**
Exact implementation **f1c7aca724778e41671f2754bb85885507c4f14d**, tree
**4f28480ef1458141422a14514473c05f49193fe6**, sole parent/base
**34835c260f737abbbe02a689f842b28fad50f323**. Helper blob
**00c347cde45e3c1a683330c6ee196815ef0a1e36**, client blob
**525381357de76ea1c570fd864f8df5e9781a87e2**. C6-R2 и targeted C8 завершены;
их проверенный scope VERIFIED. Прежние client findings01/02/03 CLOSED.

Независимый C8 сообщает отдельный чистый checkout,154 migration tests PASS,
три исходных repro без изменения assertions PASS и50 дополнительных probes PASS.
Файловые guards настоящие, Docker/DB/runtime observations — fixture. Это execution
C8, не повторный execution C0. Названный C8 evidence ZIP в этой передаче не
предоставлен как доступный файл; C0 принимает переданный verdict с указанными
границами и своим прежним5-probe/source/CI evidence. CI37629816347 — все9 jobs и
clean-source SUCCESS; C0 ранее независимо сверил8 ZIP digests/228 blobs+modes,
6 schema2 migration reports и2 relay reports. Эти results относятся exact R2.

**Новый отдельный finding C0-MIG-OWNER-01/P2 — OPEN.** При подготовке owner
attestation C0 сопоставил reader с ранее выданным owner script. В сохранённой
цепочке предусмотрен `asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json`.
Обе проверки basename в `migration_receipts` (R2 lines1956 и1977) допускают
только `[a-z0-9-]+\.json` и отклоняют этот законный исторический узел с
`EGRESS_MIGRATION_RECEIPT_PATH`. Обычный `.json` control принимается; вариант
с exact issued `.intent.json` отклоняется при тех же остальных условиях и
правильных hashes. C0 воспроизвёл это на exact helper с настоящими private files,
Python3.12.14, без Docker/DB/SSH/network и без изменения fixture files reader-ом.
Это STOP до runtime effects, не потеря данных и не повтор Telegram send.
Actual содержимое owner VM и images по-прежнему не наблюдалось.

Finding не переоткрывает исправленный cross-direction audit. Требуется узкая
совместимость имён сохранённого DAG, без переименования/перезаписи старых receipts,
исключения intent из inventory или переснятия hashes. Exact полный basename,
same-parent, no-symlink, private mode/owner, byte hashes и independent root pin
сохраняются. Поручение C6 и воспроизводимый probe — M2_HANDOFF/runbook§0.6.30.

**Отдельный CI incident:** docs-only head
**dcf32ca02c4222e3267ed4e794c817345ae71357** / tree
**499342f9a26a74640b079d2fa277767d89f65834**, parent exact R2, изменил только4 docs;
остальные224/228 blobs+modes прежние. CI37640492805 attempt1:8 jobs SUCCESS,
browser26 PASS/1 FAIL на `frontend/e2e/billing.spec.ts:57` (пагинация Audit,
ожидание enabled для исчезнувшей кнопки последней страницы). C0 запросил ровно
один rerun browser job112857823029. Job112868124234:27 PASS/clean-source SUCCESS;
attempt2 completed SUCCESS, все9 jobs/clean-source SUCCESS. Исторический failure
не удалён. Лог и статический код согласуются с гонкой между response headers,
завершением render и проверкой count/enabled; детерминированный UI repro ещё
не выполнялся. **C0-CI-AUDIT-01/P3 OPEN, C5 TODO (не выдано)** — разобрать
синхронизацию теста до merge. Ни тест, ни timeout/assertions не изменены.

| Задача / finding | Статус | Следующее действие |
|---|---|---|
| C6-M2-CONNECT5-MIGRATION-R2 / targeted C8-R2 | VERIFIED в проверенном scope | Завершено, полный review не повторять |
| C8-MIG-01/P2 | CLOSED | Cross-direction audit подтверждён C0+C8 |
| C0-MIG-OWNER-01/P2 | OPEN | Совместимость существующего `.intent.json` receipt |
| C6-M2-OWNER-RECEIPT-COMPAT | TODO, выдано | Единственное активное implementation поручение |
| C0-CI-AUDIT-01/P3 | OPEN, C5 TODO | Отдельный browser test incident, не scope C6 |
| Owner migration execution | BLOCKED | Receipt compatibility, затем actual image/DAG attestation |
| M2 / ENV04 | IN_PROGRESS / REVIEW | Actual owner migration и A09/A11 впереди |

Последнее owner evidence остаётся exact0b7e24ee/recovery-v2/connect2/TG disabled-empty,
binding committed, ACK NOT_ATTEMPTED. Independent last-receipt SHA pin и соответствие
cached images predecessor ещё не получены. CI images строились заново и не являются
owner attestation. Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z не меняется;
source-key revocation не подтверждена. PR24 Draft/open, main прежний.
Новый C0 coordination меняет только4 документа; его CI учитывается отдельно от
двух указанных green runs. VM/SSH/live Telegram/queue/ACK/activation/setWebhook/
sends/billing mutation/main merge в этой передаче не выполнялись и не выданы.


#### Issued owner format evidence (no live VM inspection)

C0 inspected the previously issued local owner script
`asm_telegram_tls_budget_fixed_0b7e24ee.py`, SHA256
`1cd0c50ecdc134778f912a4644b41f159f3d53df865df09759c64be6835049f0`.
The prior owner log reports successful completion at2026-10-06T18:10:05.409401Z.
Relevant non-sensitive statements in that script:

```python
ACK_INTENT = STATE.parent / 'asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json'
# not_attempted_ack_evidence validates both saved objects, then preserves both:
evidence[ACK_INTENT], evidence[ACK_RECEIPT] = intent_raw, result_raw
# Later diagnostic receipts preserve every predecessor under its actual basename:
'prior_receipts_sha256': {p.name: digest(raw) for p, raw in evidence.items()}
```

The last operation has14 predecessors plus its own receipt (15 nodes total).
These are issued basenames, not a claim that current VM bytes/hashes were read:

```text
asm-telegram-discovery-0b7e24ee.json
asm-telegram-owner-id-correction-0b7e24ee.json
asm-telegram-discovery-owner2-0b7e24ee.json
asm-telegram-queue-diagnostic-owner2-0b7e24ee.json
asm-telegram-discovery-fresh-owner2-0b7e24ee.json
asm-telegram-binding-owner2-0b7e24ee.json
asm-telegram-connection-diagnostic-owner2-0b7e24ee.json
asm-telegram-binding-after-diagnostic-owner2-0b7e24ee.json
asm-telegram-queue-routes-owner2-0b7e24ee.json
asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json
asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.json
asm-telegram-ack-dependency-diagnostic-owner2-0b7e24ee.json
asm-telegram-egress-segments-owner2-0b7e24ee.json
asm-telegram-tls-budget-owner2-0b7e24ee.json
asm-telegram-tls-budget-fixed-owner2-0b7e24ee.json
```

The persisted ACK state is NOT_ATTEMPTED. Its intent is retained audit evidence,
not authorization to ACK now. The compatibility fix must include and verify the
intent exactly; ignoring it or renaming old files would break the pinned chain.

#### C0 filesystem reproduction on exact accepted R2

C0 executed `python c0_owner_receipt_probe.py`, Python3.12.14. Real private file
guards/read/hash/JSON code, synthetic non-secret contents, no mocks of that reader,
no external calls. The ordinary suffix is accepted; the exact issued intent suffix
fails solely on path validation, before any file/runtime effects. Files before/after
equal. This proves the reader incompatibility; it is not owner attestation.

The portable form below was derived only by pointing the helper at the current
checkout and removing the local result-file write. Save the script outside a clean
exactf1c7aca checkout and run it with that checkout as cwd. The exact helper blob
assertion intentionally pins the defective base. C6's regression must instead
require acceptance of the valid historical name and fail on that base.

```python
"""Exercise the exact R2 receipt reader against the issued owner filename.

Synthetic private receipts, real file guards; no Docker, DB, SSH, or network.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path.cwd()
HELPER = ROOT / "scripts/prepare_telegram_egress.py"
raw = HELPER.read_bytes()
blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
assert blob == "00c347cde45e3c1a683330c6ee196815ef0a1e36"
spec = importlib.util.spec_from_file_location("owner_receipt_probe_helper", HELPER)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def write(path, value):
    data = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(data)
    path.chmod(0o600)
    return data


results = []
with tempfile.TemporaryDirectory(prefix="owner-receipt-probe-") as temporary:
    directory = Path(temporary)
    directory.chmod(0o700)
    baseline = write(directory / "deployment-before.json", {"synthetic": "baseline"})
    staged = write(directory / "staged.json", {"synthetic": "staged"})
    common = {
        "source_sha": e.MIGRATION_FROM,
        "source_tree": e.MIGRATION_FROM_TREE,
        "original_before_sha256": e.sha(baseline),
    }
    binding = directory / "asm-telegram-binding-after-diagnostic-owner2-0b7e24ee.json"
    write(binding, dict(common, status="BINDING_COMMITTED", preservation_pass=True))
    last = directory / "asm-telegram-tls-budget-fixed-owner2-0b7e24ee.json"

    for name, expected in (
        ("asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.json", "ACCEPTED"),
        ("asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json", "EGRESS_MIGRATION_RECEIPT_PATH"),
    ):
        parent = directory / name
        write(parent, dict(common, status="OWNER_APPROVED_PREFIX_INTENT"))
        body = dict(
            common,
            status="DIAGNOSTIC_COMPLETE",
            preservation_pass=True,
            staged_sha256=e.sha(staged),
            operator_image_id="sha256:" + "1" * 64,
            prior_receipts_sha256={
                binding.name: e.sha(binding.read_bytes()),
                parent.name: e.sha(parent.read_bytes()),
            },
        )
        last_bytes = write(last, body)
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        try:
            files, image = e.migration_receipts(
                last, e.sha(last_bytes), {"telegram_env": str(directory / "staged.json")}, directory
            )
            assert len(files) == 3
            assert image == body["operator_image_id"]
            outcome = "ACCEPTED"
        except e.EgressError as error:
            outcome = str(error)
        assert outcome == expected, (name, outcome)
        assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
        results.append({"parent_name": name, "outcome": outcome, "files_unchanged": True})

report = {
    "head": "f1c7aca724778e41671f2754bb85885507c4f14d",
    "helper_blob": blob,
    "python": sys.version.split()[0],
    "results": results,
    "external_calls": 0,
    "limitations": "Synthetic contents; actual owner filename from previously issued script. No live receipt/image attestation.",
}
print(json.dumps(report, indent=2))
```

Observed C0 result:

```json
{
  "head": "f1c7aca724778e41671f2754bb85885507c4f14d",
  "helper_blob": "00c347cde45e3c1a683330c6ee196815ef0a1e36",
  "python": "3.12.14",
  "results": [
    {
      "parent_name": "asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.json",
      "outcome": "ACCEPTED",
      "files_unchanged": true
    },
    {
      "parent_name": "asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json",
      "outcome": "EGRESS_MIGRATION_RECEIPT_PATH",
      "files_unchanged": true
    }
  ],
  "external_calls": 0,
  "limitations": "Synthetic contents; actual owner filename from previously issued script. No live receipt/image attestation."
}
```

#### Distinct browser CI incident, preserved

Docs-only CI37640492805 attempt1 browser job112857823029 failed after26 passes:
at `frontend/e2e/billing.spec.ts:57`, `toBeEnabled` waited for5s while the last
page's Load more button changed from disabled to absent. `waitForResponse` at
line56 precedes the UI's completed body/render update; `BillingPanel.tsx` removes
that button when next_cursor is null. This is consistent with a test race; no
deterministic delayed-response UI reproduction was performed by C0 this turn.

C0 requested one rerun of that job only, no source changes. Browser job112868124234
passed27 tests in3.1min plus clean-source; run attempt2 completed SUCCESS with all9
jobs/clean-source gates. The first failure remains evidence. C0-CI-AUDIT-01/P3 is
OPEN for separate C5 follow-up before merge; no timeout/retry/assertion weakening
is authorized or included in the current C6 receipt-compatibility task.

<details>
<summary>Архив предыдущего C0 receipt prefix — дословно до C8 closure</summary>

## C0 — R2 source/CI review PASS; targeted C8-MIG-01 review issued (2026-10-07)

**C6 implementation is complete and handed off. C0 scoped R2 verdict: PASS; no new blockers found. C8-MIG-01/P2 remains OPEN pending targeted C8/C0 verdict.** Migration REVIEW; previous client findings01/02/03 CLOSED; M2 IN_PROGRESS/ENV04 REVIEW. REVIEW is the acceptance handoff, not unfinished C6 implementation.

**Exact R2:** head `f1c7aca724778e41671f2754bb85885507c4f14d`, tree `4f28480ef1458141422a14514473c05f49193fe6`, sole parent/base `34835c260f737abbbe02a689f842b28fad50f323`. One fix commit, no reset/rebase. Four allowed files: helper, migration tests, contract§10.12.1, runbook§0.6.28. Helper blob `00c347cde45e3c1a683330c6ee196815ef0a1e36`; client blob `525381357de76ea1c570fd864f8df5e9781a87e2` unchanged. Workflow/runners/Compose/locks/domain/DB schema/180s+600s budgets unchanged.

**Fix reviewed:** both audit directions and done→result; historical completion source/state/database/intent binding; schema2 rollback intent pins exact forward inventory/byte hashes and validated historical runtime. Resume/completed retry reject missing/changed/added audit and unbound old intents, without re-pinning. Valid partial/result-done/state-completion gaps retained; no repeated completed recreates.

**Own C0 execution:** repeated3 prior defect repro on exact R2 helper: expected COMPLETED_DRIFT/SERVICE_RESULT_REQUIRED/INVALID_JSON, zero new simulated effects. Controls: valid partial rollback PASS (one needed recreate), DB observation drift STOP before effects. Total5 targeted PASS, Python3.12.14, actual private file/audit guards with repository fixtures for Docker/DB/prepared observations. No new local Docker/PG/browser/full-suite execution or claim of a fresh full Git checkout. Historical completion files remain prior evidence; failed retry does not publish a new PASS.

**Actual [CI37629816347](https://github.com/Elefesys/ai-service-manager/actions/runs/37629816347): all9 jobs and clean-source gates SUCCESS.** Logs verified768 unit/393 integration/111 frontend/27 browser. Tested merge `ebf1ec21f59eb8f887c779c3e55bf878eb15add5`, same tree; ordered parents main `22993f558c5e7e933c65e9c999933bd2e3ab41c4` +R2. C0 downloaded all8 ZIP and checked digests/every228 Git blobs+modes/PAX/tested SHA/empty status. Common source.tar.gz SHA256 `e78b0a27ea62bcd6e574e43de8e9ae73dee67ef2f077169d826a86664765b394`. All6 migration schema2 reports:7 forward hashes equal final receipt hashes, matching rollback-intent hash, unchanged-after-resume/retry=true; equal31-table fingerprints, binding/COMPED/Console/private original200/403, UNKNOWN/wire1 and28 preserved files. Held104.530–168.047s≤180s. Both old6+6 reports PASS; TIMEOUT/False5.005s. C6 local251 tests remain author evidence separately.

**Coordination:** `dcf32ca02c4222e3267ed4e794c817345ae71357`, tree `499342f9a26a74640b079d2fa277767d89f65834`, sole parent R2. Exactly4 docs changed; other224/228 blobs/modes unchanged. [Coordination CI37640492805](https://github.com/Elefesys/ai-service-manager/actions/runs/37640492805) IN_PROGRESS when recorded; separate from final implementation SUCCESS. Previous docs CI37626628260 was CANCELLED; R2 final candidate completed all9 jobs.

**Only active task: C8-M2-CONNECT5-MIGRATION-R2.** [Targeted handoff](https://github.com/Elefesys/ai-service-manager/blob/dcf32ca02c4222e3267ed4e794c817345ae71357/docs/tasks/M2_HANDOFF.md). Review exactf1c7aca7, read current handoff from docs coordination. Repeat original repro plus audit inventory/history/partial rollback risks; distinguish own probes from CI evidence. No need to rerun all green jobs without a new risk. C8 has not yet executed the R2 review.

Complete C6-R2 prefix (all job/artifact IDs/digests, named regression mapping and limits) archived verbatim in [runbook§0.6.29](https://github.com/Elefesys/ai-service-manager/blob/dcf32ca02c4222e3267ed4e794c817345ae71357/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md). Historical tail below unchanged.

Owner applicability remains unconfirmed: actual cached old images and independently pinned receipt DAG require separate attestation after C8. Last VM exact0b7e24ee/recovery-v2/connect2/TG disabled-empty; binding committed; ACK NOT_ATTEMPTED/no automatic replay. Fixed TEST interval2026-10-02T00Z→2026-10-09T00Z unchanged. PR24 Draft/open, main unchanged. No owner VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing/main merge/production issued or executed.



</details>

### 0.6.31. C6-M2-OWNER-RECEIPT-COMPAT — bounded compatibility candidate

Base/sole parent for this fix: **c015e7ad9796f17243bb205bbf9d239a9f12a2e4**,
tree **ec28a77ba76248a28b0698fe220071ecf9438fad**. Separate checkout; no reset,
rebase or force-push. Exactly four allowed files change: receipt basename validation
in the helper, migration tests/disposable fixture, contract §10.12.1 and this runbook.
C8-MIG-01 and client01/02/03 stay CLOSED; C0-MIG-OWNER-01 remains OPEN for one
focused C0/C8 verdict after the completed REVIEW handoff.

Both basename checks now accept only `[a-z0-9-]+(?:\\.intent)?\\.json`. Existing
receipts retain their actual names and bytes; their full hashes remain in the DAG
and immutable archive. No source/image/runtime/audit-schema/client/Compose/workflow/
lock/deadline/domain change. Root hash is still supplied independently, never healed
from current runtime. The prior owner procedure in §0.6.25 remains a draft, not a
new authorization. The fifteen names in §0.6.30 are tested with synthetic contents;
no actual owner receipt or cached image was read.

| C0-MIG-OWNER-01 boundary | New regression / evidence |
|---|---|
| Exact historical intent; parent and current/root checks | `test_historical_owner_intent_preserves_complete_receipt_dag`: all15 nodes, legacy links, exact inventory/bytes/modes; both positive assertions fail on base and pass after fix |
| Every ancestor remains required | `test_owner_receipt_dag_requires_every_original_byte`: tamper/missing for each of15 nodes,30 cases, zero writes/external calls |
| Strict basename boundary | `test_owner_receipt_rejects_unsafe_parent_names` and `test_owner_receipt_rejects_unsafe_current_names`: traversal, absolute parent key, separators, unexpected/repeated suffix, empty/dotted names |
| Pins/private/source bindings remain strict | `test_owner_receipt_retains_hash_and_private_guards` and `test_owner_receipt_retains_source_baseline_and_staged_bindings`: independent pin, intent/legacy-edge hashes, symlink/mode/size, source/tree/baseline/staged/preservation |
| Real migration archive/resume/rollback path | Existing six disposable lanes add the exact historical intent plus a new pinned root; original28 files retained unchanged, total30; full six-node fixture DAG and both extra archive hashes asserted before/after operation |

Red-first own execution on unchanged base helper: Python3.12.14/pytest9.0.2,
`python -m pytest -q tests/test_telegram_egress_migration.py -k historical_owner_intent`
→ **2 FAIL**, both `EGRESS_MIGRATION_RECEIPT_PATH`, at distinct original basename
checks (1956/1977). Those positive assertions remain unchanged on the fix.
Initial focused green was52 PASS; ten additional current-name/source-binding cases
bring the new focused coverage to62. Final own scoped execution on Python3.13.15,
frozen dependencies / pytest9.1.1: **313 PASS in10.69s** (216 migration +97 existing
egress; includes the62 new cases). Ruff0.16.7 all-scope lint/format PASS,117 files;
mypy1.20.2 PASS/51 backend files; offline OpenAPI contract check PASS. Canonical11
originals match SOURCE_MANIFEST. No local Docker executable is installed.

Exact local commands (checkout `m2-owner-receipt-compat`; venv outside source):

```sh
UV_PROJECT_ENVIRONMENT=/workspace/scratch/9d916d2c3a86/compat-check-env uv sync --frozen --python 3.13 --group dev
/workspace/scratch/9d916d2c3a86/compat-check-env/bin/python -m pytest -q tests/test_telegram_egress_migration.py tests/test_telegram_egress.py
/workspace/scratch/9d916d2c3a86/compat-check-env/bin/ruff check backend tests scripts migrations
/workspace/scratch/9d916d2c3a86/compat-check-env/bin/ruff format --check --diff backend tests scripts migrations
/workspace/scratch/9d916d2c3a86/compat-check-env/bin/mypy backend/src
/workspace/scratch/9d916d2c3a86/compat-check-env/bin/python scripts/export_contracts.py --check
git diff --check
```

Final exact-SHA evidence is published once in the [single PR24 receipt](https://github.com/Elefesys/ai-service-manager/pull/24#issuecomment-6002169006),
including head/tree/parent, all9 CI jobs, clean-source gates,8 ZIP digests/modes/source
archives and six migration/two relay reports. This pre-publication source document
does not assert CI success in advance. Mandatory actual CI commands remain
`sh scripts/ci.sh`, `sh scripts/test_browser.sh`, the existing Docker29 compatibility
lane and `sh scripts/test_telegram_egress_migration.sh intent|image|state` on normal
and exact Docker29. All prior6+6 assertions/31-table hashes/Console/private originals/
UNKNOWN wire1 and schema2 rollback bindings remain required, under the same180/600s
bounds. New `owner_receipt_compat` report data binds the intent/root/DAG hashes and
preserved original28 plus two additive files; synthetic CI evidence is separate
from actual owner attestation. C0-CI-AUDIT-01 is C5 scope; no browser retry or test
relaxation is implied if that incident repeats.

VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing mutation/merge
were not performed. Cached owner image bytes and independently accepted last-receipt
pin still require a separate C0 issuance. No old receipt rename/rewrite, ACK replay,
new baseline or extension of the fixed TEST interval is authorized by this fix.

<details>
<summary>Archived C0 receipt prefix — verbatim before the compatibility return</summary>

## C0 — C8-MIG-01 CLOSED; owner receipt compatibility fix issued (2026-10-07)

**C0 accepts the independent C8 R2 PASS and closes C8-MIG-01/P2 on exact R2.** C6-R2 and targeted C8 are complete/VERIFIED in their checked scope; client findings01/02/03 remain CLOSED. M2 IN_PROGRESS/ENV04 REVIEW. Actual owner migration remains blocked by the distinct compatibility finding below and pending owner image/receipt attestation.

**Accepted audit fix:** head `f1c7aca724778e41671f2754bb85885507c4f14d`, tree `4f28480ef1458141422a14514473c05f49193fe6`, sole parent/base `34835c260f737abbbe02a689f842b28fad50f323`. Helper blob `00c347cde45e3c1a683330c6ee196815ef0a1e36`; client blob `525381357de76ea1c570fd864f8df5e9781a87e2`. Cross-direction audit/inventory/hash/done→result fix accepted.

**Independent C8 report:** clean separate checkout;154 migration tests PASS, original3 repro unchanged PASS,50 additional probes PASS. Real file guards; Docker/DB/runtime observations fixture. C8 independently verified CI37629816347/all9 jobs/clean-source,8 ZIP digests/228 blobs+modes,6 schema2 migration+2 relay reports. This is C8-reported execution, alongside prior C0 own5 targeted probes and independent CI/artifact verification; the named C8 ZIP was not attached as an accessible file in this handoff. Full R2 evidence retained in runbook§0.6.29.

**NEW C0-MIG-OWNER-01/P2 OPEN:** R2 `migration_receipts` lines1956/1977 allow only `[a-z0-9-]+\.json`. The previously issued owner script retains `asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json` and pins it in later diagnostics' `prior_receipts_sha256`. C0 inspected that issued script (SHA256 `1cd0c50ecdc134778f912a4644b41f159f3d53df865df09759c64be6835049f0`) and reproduced the filename incompatibility using the exact R2 helper, Python3.12.14 and actual private-file guards: ordinary basename ACCEPTED; exact issued intent basename → EGRESS_MIGRATION_RECEIPT_PATH; correct hashes, unchanged files, zero external calls. Synthetic contents; no current VM receipt/image observation. This is a fail-closed compatibility STOP before runtime effects, not a reopened C8 audit finding or data loss.

**C6-M2-OWNER-RECEIPT-COMPAT issued:** narrow basename compatibility in helper, regressions and actual disposable migration receipt fixture, contract/runbook evidence. Four allowed files; preserve independent root pin, exact inventory/hashes, same-parent/no-symlink/private guards, schema2, source/client pins and180/600s bounds. No renaming/dropping/rewriting old receipts. Reproducer and15 issued DAG basenames are in [runbook§0.6.30](https://github.com/Elefesys/ai-service-manager/blob/c015e7ad9796f17243bb205bbf9d239a9f12a2e4/docs/runbooks/M2_TELEGRAM_LOCAL_TEST.md); [canonical C6 handoff](https://github.com/Elefesys/ai-service-manager/blob/c015e7ad9796f17243bb205bbf9d239a9f12a2e4/docs/tasks/M2_HANDOFF.md). First implementation commit sole parent must be this full coordination SHA.

**Separate browser incident:** docs head `dcf32ca02c4222e3267ed4e794c817345ae71357`, CI37640492805 attempt1:8 jobs SUCCESS, browser26 PASS/1 FAIL at billing.spec.ts:57 (Load more count/enabled vs last-page render). C0 requested one browser-only rerun. Job112868124234:27 PASS/clean-source; attempt2 all9 jobs/clean-source SUCCESS. Original failed job112857823029 preserved. Likely test synchronization race, deterministic UI repro not executed. C0-CI-AUDIT-01/P3 OPEN, separate C5 TODO before merge, not issued/not C6 scope. No test/assertion/budget changes.

**This coordination:** `c015e7ad9796f17243bb205bbf9d239a9f12a2e4`, tree `ec28a77ba76248a28b0698fe220071ecf9438fad`, sole parent `dcf32ca02c4222e3267ed4e794c817345ae71357`. Only4 docs changed;224/228 blobs+modes unchanged. CI37645313754 IN_PROGRESS at publication, no inherited PASS claim. Main `22993f558c5e7e933c65e9c999933bd2e3ab41c4` unchanged; PR24 Draft/open.

**Owner boundary:** last known0b7e24ee/recovery-v2/connect2, Telegram disabled/empty, binding committed, ACK NOT_ATTEMPTED/no automatic replay. Actual cached image bytes and independently accepted last-receipt SHA remain unconfirmed. Fixed TEST interval ends2026-10-09T00Z; no extension/rebaseline/rebuild is implied. No VM/SSH/live Telegram/queue/ACK/activation/setWebhook/sends/billing mutation/rollout/main merge issued or performed.

Previous C0 prefix archived verbatim in runbook§0.6.30. Historical receipt tail below preserved unchanged.

</details>

## 1. Конкретное окружение и предварительные условия

После выполнения §0.2 выбран один вариант: **доступный оператору Linux host с Docker
Compose, двумя DNS именами и публично доверенными TLS сертификатами**. На нём отдельный
Compose project `asm-telegram-test`; только тестовые bot/Owner/Client и новый
synthetic Workspace. Это изолированный LOCAL deployment (`asm_local`), не production.
Процедуры Python также проверяют отдельный TEST target `asm_test`, если оператор
предоставляет его явным окружением. Существующую browser TEST fixture не переиспользовать.

Нужны заранее:

- Точный принятый source SHA из активного handoff после recovery —
  **0b7e24ee425ebb429bf87dfe382cbd3fab883028**, tree14a4033b849c736235653a5a85ec9e5112bfe727.
  Cached app images сохранены из принятого host receipt; rebuild не выполнялся.
  Current main после PR23 — **22993f558c5e7e933c65e9c999933bd2e3ab41c4**.
  VM не переводить на documentation heads. Предыдущий80e51c43 — история§0.5.
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
