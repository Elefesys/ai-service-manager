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

### 0.2. Последовательность C6 и действия владельца

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

## 0.4. TEST host: последовательность без Telegram / 2026-10-01

**Владелец подтвердил active billing и folder `asm-telegram-test` 2026-10-01.**
Accepted runtime **80e51c43e31541940f1ccf18b8281adf1a061748**, tree
**88ed308b4c56114aa977dcf91204964d9b7348e5**, push/main36825583134 SUCCESS.
Задача M2-ENV-03-TEST-HOST: `c6/m2-test-host`, [Draft PR23](https://github.com/Elefesys/ai-service-manager/pull/23),
сохранить coordination **1f42a617ed64bc6fd4dd573cd5c721d22a7bf256**.
Прежняя account-инструкция выполнена; история сохранена в Git.

**Процедура подготовлена; исполнение на Yandex/host пока не подтверждено.**
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
| Boot disk | `asm-telegram-test-boot`, `network-ssd`,60GiB; не удалять вместе с VM |
| Сеть / подсеть | `asm-telegram-test-net` / `asm-telegram-test-a`; internalIPv4 автоматически |
| PublicIP | «Список» → ранее зарезервированный staticIPv4, не «Автоматически» |
| Security groups | Только `asm-telegram-test-sg` |
| Доступ | SSH-ключ, логин **asmoperator**, ключ `asm-telegram-test-owner` → загрузить свой файл `.pub` |
| Дополнительно | Защита удаления VM включена; без service account, Cloud Backup, KMS, ускоренной сети и дополнительных дисков |

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
git checkout --detach 80e51c43e31541940f1ccf18b8281adf1a061748
test "$(git rev-parse HEAD)" = 80e51c43e31541940f1ccf18b8281adf1a061748
test "$(git rev-parse HEAD^{tree})" = 88ed308b4c56114aa977dcf91204964d9b7348e5
test -z "$(git status --porcelain --untracked-files=all)"
printf '%s\n' EXACT_SOURCE_PASS
unset GIT_SSH_COMMAND
```

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
sudo /usr/local/sbin/asm-telegram-cert-deploy
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
tgcompose exec -T telegram-ingress nginx -t
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

На VM, с тем же `tgcompose`:

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
sudo /snap/bin/certbot renew --cert-name asm-telegram-test --dry-run --run-deploy-hooks
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
$asmHealth = Invoke-RestMethod 'https://console.telegram-test.clientmanagerai.com/health/ready'
if ($asmHealth.status -ne 'ok' -or $asmHealth.component -ne 'database') {
    throw 'EXTERNAL_READY_MISMATCH'
}
'EXTERNAL_HTTPS_READY_PASS'
$asmRequest = [System.Net.HttpWebRequest]::Create('https://files.telegram-test.clientmanagerai.com/asm-private-local?list-type=2')
$asmRequest.Method = 'GET'
$asmRequest.Timeout = 15000
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

**STOP до §4**: не создавать Owner/billing/live binding, не запускать
`provision_telegram_test`, `setWebhook`, smoke sends и не вставлять TG secrets.
C0 организует scoped C8 новых внешних границ и приёмку host, затем отдельно A09/A11.

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

## 1. Конкретное окружение и предварительные условия

После выполнения §0.2 выбран один вариант: **доступный оператору Linux host с Docker
Compose, двумя DNS именами и публично доверенными TLS сертификатами**. На нём отдельный
Compose project `asm-telegram-test`; только тестовые bot/Owner/Client и новый
synthetic Workspace. Это изолированный LOCAL deployment (`asm_local`), не production.
Процедуры Python также проверяют отдельный TEST target `asm_test`, если оператор
предоставляет его явным окружением. Существующую browser TEST fixture не переиспользовать.

Нужны заранее:

- Один точный **принятый runtime SHA из активного handoff**: сейчас actual main
  **80e51c43e31541940f1ccf18b8281adf1a061748** после merge PR22 и отдельного main CI.
  Отдельный clean checkout; будущий docs-only coordination commit не заменяет
  эту проверенную версию приложения.
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
