# M4 — подключение ИИ к текущему контексту

Дата подготовки: 2026-10-28. Ведущий: C0; основной исполнитель: C4.
**План принят C0 и интегрирован в PR #37. Реализация — по CURRENT реестра.**
Единственный статус исполнения — [TASK_REGISTER](../TASK_REGISTER.md).
Решение по scope: [IMPL-004](../decisions/IMPL-004-m4-pilot-ai.md).
Выбор API: [исследование 24 сервисов](../research/M4_AI_PROVIDER_REVIEW_2026-10-28.md).

## Текущая выдача — C5-M4.1-CI-RECOVERY-R1 / 2026-10-29

**Результат и польза:** устранить конкретное падение восстановления уже принятого
решения владельца после потери HTTP-ответа, повторного входа и ротации сессии.
Это разблокирует интеграцию Gateway и M4.2, сохранив один business effect.
Задача включает причинное воспроизведение и минимальное исправление, а не отдельный
этап общей диагностики или повышение timeout.

### Уточнение C0 — воспроизведение в GitHub Actions / 2026-10-29

C5 [вернул blocker](https://github.com/Elefesys/ai-service-manager/pull/38#issuecomment-6478249644):
Docker отсутствует **в локальной среде исполнителя**. GitHub Actions browser job
на ubuntu-24.04 уже выполняет scripts/test_browser.sh с настоящими Docker Compose,
API/PostgreSQL и synthetic private env, создаваемыми самим harness.
Локальное отсутствие Docker не блокирует подготовку теста и не требует VM владельца.

C0 исправляет порядок этой же задачи; write-set и итоговые критерии сохраняются:
1. **Сейчас C5 продолжает подготовку:** в разрешённом failing case добавить
   bounded payload-free observer причинных protected reads и необходимые управляемые
   точки воспроизведения. Runtime не менять до evidence. Сохранить реальный
   committed200/login/rotate/CSRF/replay путь и все исходные assertions.
   Локально выполнить typecheck и diff check; Docker-dependent E2E честно NOT RUN.
   Уже выполненные неизменённые unit suites повторять не требуется.
2. C5 возвращает **диагностический candidate** C0: full SHA, минимальный diff,
   какие конкретные события он различает, команды/результаты. Для этого возврата
   предварительный локальный Docker PASS больше не требуется.
3. C0 проверяет дельту и выполняет один expected-head/force=false FF существующего
   PR38 на изменённый candidate. Это запускает штатный GitHub Actions, где Docker
   доступен. Workflow сейчас запускает весь набор jobs; browser выполняет реальное
   воспроизведение. Отдельный runner/workflow или включение VM не нужны.
   Это разрешённый запуск для нового диагностического кода, не blind rerun
   неизменённого FAIL. Прежний attempt1 остаётся FAILURE.
4. По фактическим событиям C5 в той же задаче исправляет подтверждённую причину;
   после review C0 конечный candidate проходит полный штатный CI.
   Если диагностический run не выявил причину, один PASS не закрывает finding:
   определить недостающий факт и следующую минимальную управляемую проверку,
   не повторять неизменённый прогон в надежде получить нужный результат.

C5 HOLD из blocker receipt ниже снят **для этой подготовки**; реальное E2E
ещё не выполнено, исправление и новый CI пока не заявлены. C4/M4.2 остаются HOLD.
C5 не двигает c4/main и не открывает дополнительный PR; передачу в CI делает C0.

### Решение C0 по возврату C4

[PR #38](https://github.com/Elefesys/ai-service-manager/pull/38), candidate
**31537848de7bcfb5732622b9361cfaba41c1105b**, tree **aa265f68c3fec9e3b7128d9a800e6e5cf5574f25**.
C0 прочитал весь новый Gateway/DTO/fake/prompt/schema и оба test files:
существенных source замечаний в выданном contract scope не обнаружено.
C4 изменил ровно 10 разрешённых paths относительно seed2107f918…; CURRENT-строка
и короткий receipt — единственные его doc changes. Это C0 review, не C8 acceptance.

[CI 40740338709](https://github.com/Elefesys/ai-service-manager/actions/runs/40740338709),
attempt1, exact candidate: **COMPLETED / FAILURE — 10 SUCCESS / 1 FAILURE**.
Foundation: **2286 ordinary +155 subtests**, **804 PG PASS**, Ruff/mypy PASS.
Browser: **398 frontend unit PASS; 53 browser PASS / 1 FAIL**.
M4.1 остаётся BLOCKED на полном CI; не INTEGRATED/VERIFIED. C4 HOLD.
Новая выдача ниже — единственная активная; M4.2 и остальные чаты HOLD.

**Единственная подтверждённая группа сбоя:** existing recovery test в
frontend/e2e/messaging.spec.ts:298, ожидание retry button на строке353.
[Browser job122999902003](https://github.com/Elefesys/ai-service-manager/actions/runs/40740338709/job/122999902003).
Commit resolve=200, ответ ABORTED; session=401 после clearCookies;
login/detail/rotate=200. Перед первым retry: login_present=true,
detail_present=false, retry_present=false; resolve_requests=1, retry_clicked=false.
Cleanup=false зарегистрирован после закрытия страницы по timeout и не является
доказанной отдельной первопричиной.

Из source: после login читаются несколько панелей; готовая escalation detail
не доказывает завершения остальных GET. Текущий SESSION_REQUIRED от Business/
Billing/Escalations/Messaging вызывает invalidateAuth/очистку protected state.
Какой именно request/response вызвал возврат в anonymous, старый диагностический
observer не записал. Гонка GET с внешней ротацией — проверяемая гипотеза,
не установленный root cause и не основание назвать падение случайным.

### База, ветка и зависимости

Repository: **Elefesys/ai-service-manager**.
Принятый actual main: **1cb3b6e168276d77faa3f11f33f8ecd0408ce406**.
Точная repair base: **31537848de7bcfb5732622b9361cfaba41c1105b** (текущий PR38 candidate).
Ветка C5: **c5/m4-1-ci-recovery-r1**. C0 добавляет одним docs-only commit
эту выдачу поверх repair base; точный стартовый head в передаче C0.
C5 продолжает подготовленную ветку в отдельном checkout и сохраняет Gateway/C0 docs.
Candidate допустим как база этого ремонта, но не объявлен принятым main.
PR38/c4 branch удерживается до проверенного C0 диагностического candidate,
затем до конечного repair candidate согласно уточнению GitHub Actions выше.

Зависимости: accepted M3 recovery/authorization/UNKNOWN semantics, IMPL-004,
данный CI receipt. Применимы ADR-024/026/180/267 и существующие session/CSRF
contracts. Не повторять аудит M3, provider research или исправный backend CI.

### Точный write-set C5

1. **frontend/e2e/messaging.spec.ts** — только failing recovery case и необходимые
   локальные helpers этого case. Bounded payload-free diagnosis и детерминированный
   порядок реальных auth/read/rotate/resolve событий.
2. **frontend/src/App.tsx** — условно: только если воспроизведение докажет
   runtime defect текущего auth recovery/invalidation. Сначала причинное evidence,
   затем минимальное исправление в том же задании; отдельное разрешение на эту
   уже указанную дельту не требуется.
3. **frontend/src/App.test.tsx** — regression/negative controls для фактического
   изменения App.tsx. Если исправление только в синхронизации теста, этот path
   менять ради количества тестов не требуется.
4. **docs/TASK_REGISTER.md** — только строка C5-M4.1-CI-RECOVERY-R1 в CURRENT.
5. **docs/tasks/M4_HANDOFF.md** — короткий C5 receipt под этой выдачей.

Остальные panels/API/backend/SQL, Gateway, manifests/locks, CI workflows,
playwright.config.ts и scripts/test_browser.sh не меняются. Если причинное
evidence требует другого path, вернуть C0 конкретную ошибку/файл/минимальную дельту,
не менять общую auth policy предположением. Нет VM/paid API или новых migrations.

### Выполнение и критерии

- Воспроизвести смену auth state целевым тестом и идентифицировать причинный read:
  порядок request/response относительно login/rotate, безопасный класс пути,
  method/status, ограниченные phase/boolean/UI markers. Не логировать raw URL/IDs,
  cookies, CSRF, idempotency-key, bodies, частный текст или signed URLs.
  Нужен конечный локальный observer данного case, не общий recorder/framework.
- Разделить две причины: неконтролируемая ротация до завершения текущих auth reads
  в harness либо дефект обработки устаревшего ответа в runtime. Исправить доказанную
  причину. Готовность кнопки не подменяет завершение причинного read.
  Ожидания основаны на конкретных событиях/границах, не sleep/networkidle/большем
  timeout. Нельзя игнорировать настоящий current 401 или подменять успешный JSON.
- Сохранить смысл полного сценария: первая команда реально COMMITTED200,
  клиент теряет ответ; реальный login возвращает доступ; после rotate исходный
  retry получает CSRF403; recovery позволяет явный повтор **тех же bytes/key**;
  ответ REPLAY совпадает с первым, в PG ровно одно решение. Нет автоматического
  mutation retry, client send или Resume. Отрицательный реальный logout/revoke
  по-прежнему скрывает protected данные и не возрождает чужое/старое намерение.
- Если App меняется, regression до исправления падает по целевой причине,
  после проходит; проверить и актуальный отказ, и запоздалый ответ.
  Если меняется только harness, показать, что контролируемый порядок устраняет
  именно воспроизведённую гонку, а все исходные business/auth assertions сохранены.
- При доступном Docker targeted команда использует существующий locked Node24
  environment и реальный browser/API/PG harness после обычного setup/private env:
  `npm --prefix frontend run test:e2e -- --project=chromium-desktop e2e/messaging.spec.ts --grep "^Escalation committed200 loss"`.
  Setup/private files остаются вне Git; тест без env/реальной БД не evidence.
  При изменении App: `npm --prefix frontend test -- src/App.test.tsx`.
  Без локального Docker действует уточнение GitHub Actions выше: typecheck и
  диагностический candidate сначала; реальный E2E проверяется в CI.
  Релевантные auth/recovery/revoke cases входят в окончательную проверку.
- После диагностического возврата и исправления готовый итог вернуть C0: полный head и base, changed paths, точный root cause
  или оставшийся конкретный blocker, команды/фактические результаты, сохранённые
  инварианты. C0 проверяет candidate и переносит его в существующий PR38 для
  **одного штатного полного CI**. Не открывать дублирующий implementation PR,
  не двигать c4/main и не перезапускать неизменённый CI.
  При новом падении разобрать все известные группы; прежний FAIL не переписать
  задним числом как PASS. Авторский review не считать независимым C8.

После каждого возврата C5 — HOLD до получения результата C0/CI; текущий
blocker-return уже разобран, подготовка возобновлена уточнением выше. M4.2 выдаётся только после устранения blocker и приёмки
M4.1 по текущей общей базе. Единственная матрица A01–A08 ниже не меняется.

### C5 diagnostic candidate — C5-M4.1-CI-RECOVERY-R1 / 2026-10-29

**REVIEW / C5 HOLD для C0/Actions**, base1449e9f9e1a70db4e5ea0f9b95d291e11cf50594.
Изменены только failing case/local formatter в messaging.spec.ts и разрешённые
два docs места. R4-журнал: до160 событий/32KiB, закрытые классы путей,
request ordinals, method/status/phase и boolean UI; печатается при PASS и FAIL.
Исходный committed200/login/CSRF403/exact replay/one-decision путь сохранён.
После его assertions один реальный Business GET на reload удерживается до
внешней rotation: captured credentials сначала проверяются реальным session200,
затем исходный GET должен получить настоящий SESSION_REQUIRED401 и скрыть UI.
Это управляемая проверка гипотезы, не идентификация исторического причинного GET.
Runtime/остальные tests/guards неизменны; typecheck/diff и локальные проверки
privacy/bounds/classification/assertion retention PASS. Real browser/API/PG
**NOT RUN**; прежний CI FAIL и отсутствие доказанного исправления сохраняются.
Следующий шаг — review C0 и один FF PR38 для штатного Actions по уточнению выше.
Полные SHA/команды/границы — в возврате C5 в PR38; неизменённые unit suites не повторены.

### C5 receipt — C5-M4.1-CI-RECOVERY-R1 / 2026-10-29

**BLOCKED / C5 HOLD, исправление не заявлено.** Проверены seed
96e74c489d76d41a9df8f007f84ef2e0581a1398, его sole parent repair base и ancestry
принятого main. В текущей среде нет Docker CLI/daemon socket; capabilities=0,
`unshare -Ur true` получает Operation not permitted. Штатный real browser/API/PG
setup и целевой recovery case не выполнены; причинный read не установлен.
После frozen `npm ci --ignore-scripts --no-audit --no-fund`: typecheck и 180 tests
в App/EscalationsPanel/escalation-api/BillingPanel/MessagingPanel PASS
(Node24.22.1, npm11.9.0). Это только unit/consumer evidence, не воспроизведение CI.
Code/tests/locks/Gateway сохранены; изменены только эта запись и строка CURRENT.
Для продолжения нужен существующий Docker-capable harness с private env и
причинным target из выдачи; расширение write-set не требуется. Полные команды,
SHA и пределы результата — в возврате C5 в PR38; прежний CI FAIL сохраняется.

## Предыдущая выдача — M4.1-CONTRACT / C4 / HOLD

C4 вернул реализацию в PR38; source review C0 завершён, интеграция блокирована
browser CI. Следующая работа — только текущая C5 выдача выше. Исходный scope
ниже сохранён для проверки результата, не для параллельного продолжения C4.


**Результат и польза:** рабочий typed Gateway с проверкой входа/выхода, конечными
лимитами и детерминированным fake adapter. M4.2 подключит Polza через этот же
интерфейс; ошибки модели и неподдержанные возможности не попадут в дальнейшую
отправку как успешный результат. Сейчас нужен этот небольшой исполняемый контракт;
provider HTTP, агент и Telegram wiring идут в следующих последовательных задачах.

Принятая база: **1cb3b6e168276d77faa3f11f33f8ecd0408ce406** (actual main после PR #37).
Дерево: **25205a6644bff00f8afa110058ad1e569695791d**, совпадает с принятым planning head.
[Main CI 40725828529](https://github.com/Elefesys/ai-service-manager/actions/runs/40725828529),
push/main, attempt 1: **11/11 SUCCESS**. Проверены SHA и conclusions всех jobs;
прежние артефакты/M3/рынок заново не аудировались.

Repository: **Elefesys/ai-service-manager**. Ветка: **c4/m4-1-contract**, отдельный checkout.
C0 подготовил на этой ветке только текущую выдачу и переход статусов после PR #37,
одним commit поверх указанного actual main. Продолжать эту ветку, сохранив C0 docs;
точный стартовый head указан в передаче C0. Это docs seed, не новый runtime base.
C4 начинает реализацию этой единственной задачи; C1/C2/C3/C5/C6/C8 остаются HOLD.

**Зависимости и источники:** принятые M3 и IMPL-004; AGENTS.md, CURRENT реестра,
данный M4_HANDOFF. Для контракта — Spec §7.2/7.6/7.7/7.16/7.21,
ADR-023/024/026/180/259/260/261/267, Roadmap §8, Implementation Plan M4.1.
IMPL-004 явно сужает старую обязательность registry и второго рабочего adapter.
В актуальном pyproject уже есть Pydantic v2, pytest/asyncio, Ruff и mypy;
новые dependencies и изменения lockfiles для этого среза не ожидаются.

### Разрешённые файлы C4

Только реально нужные файлы из этого списка; не создавать пустые заготовки:
- backend/src/asm/ai/__init__.py
- backend/src/asm/ai/contracts.py
- backend/src/asm/ai/gateway.py
- backend/src/asm/ai/fake.py
- backend/src/asm/ai/prompts/conversation_v1.txt
- backend/src/asm/ai/schemas/conversation_result_v1.json
- tests/test_m4_gateway.py
- tests/test_m4_gateway_failures.py

C4 также может изменить **только строку M4.1-CONTRACT** в CURRENT
docs/TASK_REGISTER.md (IN_PROGRESS → REVIEW) и добавить короткий receipt под
этой выдачей в docs/tasks/M4_HANDOFF.md. Подробные результаты — в PR/artifacts.
Остальные строки, матрица A01–A08 и исторические записи сохраняются.

Migrations, conversations/messaging, backend entrypoint, shared config,
manifests/locks, workflows/scripts, UI и прочие paths вне write-set.
При конкретной необходимости расширения сообщить точный path, причину и
минимальную дельту C0; не добавлять будущие adapters/registries заранее.

### Что реализовать

1. Минимальные immutable/validated DTO: явно заданная route/model/config revision,
   prompt/schema revisions, messages, разрешённые read tool definitions,
   tool call/result correlation, deadline/input/output/token/call limits,
   result/refusal/error и usage/cost. RU_AGGREGATOR/DIRECT_PROVIDER различаются в
   конфигурационном контракте; fake обозначен как fake, рабочего direct adapter нет.
   Endpoint/model/upstream задаёт доверенная конфигурация. Нет модельного выбора
   маршрута, неявного fallback, ключа в DTO/repr/ошибках или угадывания upstream.
2. Один async adapter protocol и вызывающий его Gateway. Одна попытка на вызов,
   конечный deadline; никаких скрытых retry/repair или сетевых/DB side effects.
   До вызова проверяются лимиты и совместимость запрошенных tools/schema/limits;
   отсутствующая/неподтверждённая capability не считается поддержанной.
   Нельзя тихо выкинуть параметр. Кандидаты openai/gpt-6-luna и
   google/gemini-3.8-flash в synthetic fixtures остаются EVAL_ONLY:
   fake capability declaration не доказывает реальную совместимость.
3. Версионированный небольшой prompt и локальная строгая output schema:
   reply / handoff / no_reply с согласованным текстом/причиной.
   Gateway различает промежуточные read tool calls и финальный результат.
   Не принимает лишние поля, неверные типы/сочетания, неограниченные строки или
   произвольные tool names; tool arguments/results проверяются своим объявленным
   контрактом. JSON Schema и runtime DTO не должны расходиться.
   Provider structured output не отменяет local validation. Raw/invalid/truncated
   output не становится reply. Schema validity не выдаётся за истинность фактов.
4. Prompt сохраняет границу untrusted input / platform policy и правило уточнить
   неизвестные услуги/цену/длительность/запись. Handoff — предложение результата
   для будущего доверенного runtime, не mutation tool. Работающий ContextBuilder,
   авторизация чтения реальной БД, AIRun/agent loop и отправка здесь не реализуются.
5. Конечные лимиты явно заданы в config/request и проверяются на границах:
   нулевой/истёкший бюджет не вызывает adapter, oversized input/output отклоняется.
   Контракт передаёт остаток общего бюджета через tool round-trip, не сбрасывая его
   как новый run; ориентир IMPL-004 — максимум 3 model calls / 4 read executions.
   Это проверяемый контракт/учёт для fake, не durable spend enforcement.
   Валюта и известная стоимость отделены от estimate/UNKNOWN; отсутствие usage/cost
   и timeout не превращаются в нулевой расход или разрешение бесконечного повтора.
6. Детерминированный fake: обычный ответ, tools → synthetic result → ответ,
   refusal, invalid/truncated JSON, oversize, 429/5xx/timeout, неизвестная стоимость.
   Сценарии проверяют протокол и ограничения без настоящих секретов, HTTP и БД.
   Логи/ошибки не содержат содержимое переписки, ключи или chain-of-thought.

### Завершение и evidence

- Импортируемый работающий Gateway/DTO/schema/prompt/fake; endpoint/model меняются
  через config, business/M3 code не меняется. Не создавать fake «live success».
- Focused tests доказывают success и перечисленные отказы, schema drift, запрет
  неразрешённого tool/capability/fallback, отсутствие вызова при исчерпанных лимитах,
  budget continuity и tool call/result correlation. Потолок проверяется с обеих
  сторон, timeout — без долгих sleeps. Проверить assets в обычной wheel-сборке.
- Из существующей Python 3.13 locked environment, из корня repository:
  `pytest -q tests/test_m4_gateway.py tests/test_m4_gateway_failures.py`;
  `ruff check backend/src/asm/ai tests/test_m4_gateway.py tests/test_m4_gateway_failures.py`;
  `ruff format --check backend/src/asm/ai tests/test_m4_gateway.py tests/test_m4_gateway_failures.py`;
  `mypy backend/src`.
  Затем один полный штатный PR CI на согласованном конечном candidate.
  Не запускать полный цикл на промежуточных push ради проверки одного DTO;
  готовый candidate публикуется после targeted checks.
- Если CI упал, сгруппировать все известные причины, исправить и проверить
  затронутое поведение; неизменённый прогон ради PASS не повторять. Старые gates
  не ослаблять. Этот срез даёт contract/failure evidence для A01/A06, но не
  закрывает live A01, изоляцию A03, runtime A04/A05 либо весь M4.
- Возврат: PR + полный head/base SHA, точный diff/write-set, краткий public contract,
  команды и фактические результаты, ссылка run/attempt/head, ограничения.
  Авторский review не называется независимым C8. Статус до C0 — REVIEW; затем HOLD.

Платные API, Polza adapter, credentials/VM activation, SQL и текущие M3 guards
в эту выдачу не входят. Следующая зависимая задача — M4.2-PROBE после приёмки
M4.1; перед её платной частью нужны reproducible command, secret path инструкция
и отдельно подтверждённый владельцем бюджет.


### C4 receipt — M4.1-CONTRACT / 2026-10-29

**REVIEW**, затем C4 HOLD до решения C0. Реализованы `ModelGateway.call()`,
immutable DTO, versioned prompt/schema и явный EVAL_ONLY fake; continuation
сохраняет config/deadline и общий предел 3 calls / 4 reads. 89 focused tests,
Ruff check/format, mypy (68 source files) и обычная wheel-сборка с изолированным
импортом/вызовом Gateway PASS. Точные команды, head/base SHA, diff и штатный
PR CI run/attempt — в PR ветки `c4/m4-1-contract`. Это авторская проверка,
не независимый C8; A01/A06 только contract/failure evidence. HTTP/DB/Telegram,
Polza proof, durable spend enforcement и приёмка всего M4 не заявлены.

## Результат для пользователя

Тестовый клиент пишет в Telegram. Один AI-агент читает разрешённый актуальный
контекст, задаёт нужный вопрос или отвечает на основании известных фактов.
Неизвестная цена/длительность не выдумывается. При необходимости агент предлагает
передачу владельцу, которую выполняет доверенный runtime. Владелец видит диалог,
может перехватить его; устаревший AI-ответ не отправляется после принятого takeover.
Собранные факты можно проверить в структурированном результате run.

Это первый работающий текстовый AI-срез, а не законченный отраслевой пилот.
Услуги/правила/знания/Vision приходят в M5, формальная заявка/оценка — в M6.
M4 не должен строить эти домены или обещать реальные цены/запись без них.

## Проверенная исходная точка

| Что | Основание |
|---|---|
| Принятый runtime M3 | main d2f25673f6d2698d3c3dae2d7b2d709e134358f4 |
| Дерево | 141d0a6b2b2be0efe1fcb1c3f851796e9f4cb427 |
| Post-merge CI | [40681691046](https://github.com/Elefesys/ai-service-manager/actions/runs/40681691046), 11/11 SUCCESS |
| Поздняя координация C0 | 025688e94a9147891e83f69713e2476c3419ca3c: только TASK_REGISTER и M3_HANDOFF сверх main; итоговая приёмка перенесена в планирующую ветку |
| История M3 | [M3_HANDOFF, верхний финальный receipt](M3_HANDOFF.md); не исполнять архивные инструкции из середины |
| Текущая принятая база M4.1 | actual main 1cb3b6e168276d77faa3f11f33f8ecd0408ce406; PR #37 merged, main CI 40725828529 11/11 SUCCESS |

Перед стартом C0 проверяет актуальный main/open PRs: параллельные изменения нельзя
затереть. Если product source сдвинулся, адаптировать выдачу к нему; не переносить
механически старый SHA. Импортированные architecture/SOURCE_MANIFEST остаются
историей; IMPL-004 явно меняет текущий scope, а не их контрольные суммы.

M3 закрыт в LOCAL/TEST. Сохраняются PC/Happ/SSH как development route и no-refetch
для заменённого изображения. Состояние VM/ключей/TEST windows не выводится из
GitHub CI. Перед новым live шагом C6 проверяет только необходимые текущие условия;
не повторяет provisioning/native activation/renewal без обнаруженной причины.
Production, перенос облака и общая оптимизация CI сейчас не выдаются.

## Порядок небольших задач

Каждая строка — отдельная ограниченная выдача C0 и, как правило, небольшой PR.
При необходимости разделить runtime на DB и wiring можно только по реально
проверяемой границе, без параллельного изменения одной миграции. Зависимые задачи
начинаются после приёмки общего SHA. Контракт, тесты и короткий receipt входят в
свою задачу, а не составляют отдельный бесконечный этап документации.

| ID | Ведущий / помощь | Конкретный результат | Зависимость |
|---|---|---|---|
| M4.1-CONTRACT | C4; C0 review | Узкий typed Gateway, bounded config/request/result/errors, schema validation и рабочие fake fixtures. Изменение модели/endpoint не меняет business code | Принятие IMPL-004 |
| M4.2-PROBE | C4; C6 только secrets/network | Рабочий Polza adapter и короткая synthetic API-проверка: маршрут, JSON/tools, usage/цена/latency; выбран один runtime model | M4.1; ограниченный ключ/бюджет владельца |
| M4.3-CONTEXT | C4; C1/C3 review | ContextBuilder над M3 и один-два нужных read-only tools с серверной tenant/client authority; ограниченный агент на fixtures | M4.1, текущие M3 contracts; до live runtime — M4.2 |
| M4.3-RUNTIME | C4 + C2/C3; C1 wiring | Durable AIRun, bounded model/tool loop и настоящий AI→Outbox→Telegram путь; takeover/restart/UNKNOWN сохраняются | M4.2 + M4.3-CONTEXT |
| M4.3-QUALITY | C8 scoped review; авторы исправляют | Проверенные failure/concurrency границы и короткий предметный eval; при необходимости минимальная понятность статуса в существующей Console | Тесты пишутся в каждой задаче; итог на runtime candidate |
| M4-ACCEPTANCE | C0; C6/operator; C8 по дельте | Штатные CI, ограниченный живой synthetic диалог, main verification и короткая передача в M5 | Принятый кандидат, ключ/допустимый маршрут/действующая TEST среда |

Соответствие старому плану: CONTRACT = M4.1; PROBE = M4.2;
CONTEXT/RUNTIME/QUALITY = детализация M4.3. Новых продуктовых milestones нет.

### M4.1-CONTRACT — сначала минимальный интерфейс

Реализовать реально используемые DTO и вызов через adapter contract: messages,
явно разрешённые read tools/schema, модель/маршрут, deadline/token limits,
typed result/refusal/error/usage. Provider-specific поля локализованы в adapter.
Prompt и schema — versioned files, небольшой config — typed config, а не registry
с CRUD/UI/DB. Прописать совместимость полей для выбранных кандидатов: неподдерживаемые
tools/schema/limits дают понятный отказ, а не тихую потерю параметра.

Fake adapter нужен для обычного ответа, tool round-trip, invalid/truncated JSON,
refusal, 429/5xx/timeout и неизвестной стоимости. Это реализация контракта для CI,
не доказательство настоящего API и не фиктивный direct provider.

Предлагаемый первый write-set: новый backend/src/asm/ai/ с минимально нужными
файлами и относящиеся к ним tests/test_m4_*.py. C0 перечисляет точные файлы до выдачи.
Existing manifests/locks/config wiring — только если реально нужно и отдельно
включено в write-set. В этой задаче нет migrations, live activation, нового UI
или изменения M3 guards.

### M4.2-PROBE — проверить внешнюю зависимость рано

Polza — выбранный первый кандидат по desk research, ещё EVAL_ONLY.
Не создавать аккаунты всех агрегаторов. GPTunnel либо другая альтернатива
проверяется только при конкретном препятствии/непригодном результате Polza.

До платного вызова владелец предоставляет выделенный secret через штатный
локальный secret path и подтверждает сумму. Предлагаемый первоначальный предел
100–300 ₽; не пополнять/не тратить автоматически. В Git/CI ключ не попадает.

Одна воспроизводимая команда пробника:
- получает/фиксирует актуальные ID, official upstream, pricing/currency и capability
  metadata аккаунта; unofficial providers выключены, route закреплён;
- проверяет openai/gpt-6-luna и google/gemini-3.8-flash на одинаковых русских cases:
  краткий ответ/уточнение, неизвестная цена, owner facts, изменение контекста,
  недоверенные инструкции, handoff, JSON и реальный tools→result→ответ;
- проверяет несколько synthetic image inputs для ранней проверки M5 capability.
  Это не Vision runtime и не обработка реальных фото клиента;
- записывает request/call counts, correctness, observed latency и usage/списание
  без частного содержимого. Небольшая выборка 20–30 cases — ориентир, не SLA;
  критические/нестабильные случаи повторить, указать N для p50/p95;
- фиксирует выбранные route/model/prompt/schema revisions, ограничения, бюджет
  фактических вызовов, правила отключения и отсутствие неразрешённого fallback.

Сначала критерии пригодности, затем сравнение стоимости прошедших моделей.
Не объявлять качество доказанным по одиночному «привет». Provider capabilities
«unknown» не означают PASS; игнорирование max_tokens/strict schema недопустимо
маскировать «совместимостью OpenAI». При необходимости выберите другую модель
либо явный bounded local validation режим с соответствующим evidence.

Проверять доступность Polza с нужного backend environment, не только с ПК.
Работающий Telegram relay не означает разрешение отправлять через него AI traffic.
Менять egress/VM можно только отдельной малой выдачей при подтверждённом блокере.
До допуска реальной переписки использовать synthetic content.

### M4.3-CONTEXT — правильные факты до хорошей формулировки

Переиспользовать parse_snapshot/TurnSnapshotV2/V3 из conversations/turns.py,
parse_guarded_snapshot из guards.py, owner context из native_context.py,
material состояния и уже принятые observation/control tokens.
Строить bounded context с источниками/пределами; не добавлять raw Telegram fetch
или лог всего Workspace. Отсечение истории не должно незаметно удалять важные
owner facts или скрывать неполноту; при нехватке безопасного контекста — уточнение
или handoff, без обязательной дополнительной summary-модели.

Инструменты читают только уже реализованные данные этого разговора/бизнеса.
Один полезный current-context/history read tool достаточен; второй — лишь при
доказанной необходимости. Не придумывать ServiceCatalog/Quote repositories,
пустые будущие таблицы или универсальный SQL-инструмент ради tools demo.
Workspace/Client/conversation связывает сервер, каждое чтение авторизуется заново.
Не выдавать другим клиентам owner-only заметки, billing, секреты или служебные поля.

Schema результата минимальна: выбранное reply/handoff/no_reply, текст если нужен,
причина и небольшие extracted facts при необходимости. Schema валидность не
доказывает истинность ответа. Derived facts привязаны к источнику/текущему run;
не записываются как утверждённая цена, длительность или готовая ServiceRequest.
Владелец продолжает работать в существующем разговоре/Action Center.

### M4.3-RUNTIME — подключить действующий AI, сохранив M3

**Обязательный обнаруженный разрыв:** M3 consumer CONTROLLED_GUARDS_V1 и
consume_guarded тестовые; begin_guarded_send принимает только CONTROLLED provider.
0010/0013 закрепляют эту границу в SQL. Нельзя открыть Telegram снятием одного
if, подменой provider или использованием owner manual-send от имени AI.

C4/C2/C3 сначала согласуют короткую дельту: настоящий AI consumer/job, durable run
и result, авторитетная admission/generation проверка и создание ровно одного
канонического send intent. C2 назначает следующий свободный migration revision
по фактическому main; применённые 0001–0013 не правятся. Не фиксировать число
новых таблиц заранее: нужны только данные для реального recovery/trace.
Existing controlled tests остаются честно controlled и проверяются отдельно.

В runtime обязательны:
- lease/restart/replay на существующих durable Jobs; bounded loop, одна терминальная
  запись результата или понятный отказ. Persist before publishing send intent;
- проверка актуальной authority/context/native policy перед моделью/tools,
  сохранением результата и отправкой; takeover/new input/native event/Resume ABA
  не должны оживить старый run;
- свежие Telegram permission/delivery gates как у принятого живого пути,
  обязательные deadlines и отсутствие скрытого SDK send retry;
- короткие DB-транзакции; LLM HTTP снаружи. Ручные ответы/inbound не ждут окончания
  единственного занятого LLM worker;
- state-changing effects только у доверенного runtime. Handoff проходит существующий
  escalation command; read tools остаются read-only. Не строить новое уведомление;
- UNKNOWN после возможного send сохраняется после restart и не переотправляется.
  Повтор не создаёт второй Outbox intent/альтернативный уже принятый текст;
- finite tokens/time/call/spend limits, typed provider errors и trace без secrets,
  chain-of-thought и лишней копии переписки. Missing cost != 0;
- AI default disabled до отдельного TEST enable; при отключении остаются
  ручная переписка и текущий durable state. Rollback не удаляет receipts/migrations.

Начальный ориентир ограничений из IMPL-004 уточняется по пробе. Не нужен новый
Redis/broker, отдельный SaaS billing, custom provider-health framework или
автоматическое переключение на другой data route.

### M4.3-QUALITY — проверять поведение, не наращивать счётчик тестов

Автор проверяет свой срез сразу. C8 независимо смотрит конкретную изменённую
границу; review автора нельзя назвать независимым C8.
Использовать существующие PostgreSQL/worker/browser harnesses, маленький набор
JSON fixtures/eval script. Новая общая eval-платформа не требуется.

Обязательная матрица результата (одно место, здесь):

| ID | Что должно быть доказано | Нужное evidence |
|---|---|---|
| A01 | Выбранный реальный route умеет нужные tools/schema/limits; usage и цена понятны, неразрешённого fallback нет | Synthetic paid probe + adapter contract/failure tests; условия маршрута отдельно от технической пробы |
| A02 | AI использует текущие owner/canonical facts, явно учитывает недоступное/заменённое фото и неполноту; не выдумывает услуги/цену/запись | Context fixtures + реальные model cases |
| A03 | Tenant/client isolation, read permissions и revoked authority проверяются сервером; prompt injection не открывает чужие данные или mutation | Реальные PG/API negatives + agent/tool boundary tests |
| A04 | HUMAN/takeover, new input, edit/delete/native barrier и separate Resume не допускают stale send | PG/worker concurrency, границы actual AI consumer; существующие M3 guarantees сохранены |
| A05 | Duplicate jobs/restart после model result и неоднозначный Telegram send не дают второго intent/повторной отправки | Durable PG + controlled wire: возможный send → потеря ACK → restart → persistent wire count остаётся 1 |
| A06 | 429/5xx/timeout/refusal/invalid output/oversize/exhausted budget заканчиваются ограниченно; ручной путь не блокируется | Adapter/job failure tests + проверка параллельного manual/inbound пути |
| A07 | Реальный короткий русский сценарий проходит: уточнение → ответ из фактов или handoff, структурированный результат правдоподобен | Версионированный небольшой eval; модель/route/prompt/schema/N/cost/latency указаны |
| A08 | Оператор понимает enable/disable и ограничения; принятый код работает в LOCAL/TEST, actual main CI соответствует интеграции | Ограниченный synthetic live smoke + CI/операторский receipt, без production claims |

Производные новые race matrices вводить только для конкретного незакрытого риска.
CI без внешних платных API, deterministic fixtures не выдавать за real model proof.
Сначала targeted tests, затем штатный full candidate CI. Не менять критерии,
grants или общий timeout ради зелёного результата и не гонять неизменный CI лотереей.
При нескольких падениях перечислить все группы и исправлять первопричины.

### M4-ACCEPTANCE — закончить этап, не расширяя его

C0 принимает C8 findings по фактическому scope и один конечный candidate.
C6 готовит короткий preflight/deploy/disable для существующей TEST среды и ключа:
актуальный source/schema/environment/binding/сроки policy, только нужный route.
Старые VM команды не повторять без проверки; merge сам VM не обновляет.

Владелец подтверждает ограниченный сценарий: новое synthetic обращение →
AI уточняет/отвечает → HUMAN takeover → owner context → отдельный Resume →
ответ с актуальными фактами, без повтора старого. Не загружать реальные фото/данные
до разрешённого scope. C0 заранее выдаёт точные ожидаемые наблюдения, а не длинный
ручной чек-лист всех автоматических race tests.

Merge по действующей процедуре владельца, затем читать штатный CI actual main.
Не добавлять новый документационный коммит только для записи собственного SHA.
Короткий итог/ссылка на evidence в PR + единое обновление register/handoff достаточны.
M4 VERIFIED только после A01–A08 в заявленных границах; отсутствие полного data
допуска явно оставляет real-client rollout закрытым, но не подменяет synthetic TEST.
Передача M5: проверенная модель/route, ограничения image capability, текущий SHA,
контракт read tools и список действительно отложенных работ.

## Как C0 ведёт этап без повторения путаницы M1/M3

1. Первым сообщением — фактическая база, что уже принято и один ближайший результат.
   План/IMPL-004 приняты; текущая выдача M4.1-CONTRACT выше. Не открывать все чаты разом.
2. Перед каждой задачей показать понятную пользу для пилота, необходимость сейчас
   либо возможность отложить. Выдать ID/base SHA/точные paths/dependencies/criteria.
   C2 контролирует миграции; общие файлы не редактируются параллельно.
3. Сохранять один активный блок выдачи, короткий registry summary и ссылки на
   результаты. Завершённые verbose логи — в PR/artifacts, не новые сотни страниц
   инструкций с несколькими взаимоисключающими CURRENT.
4. Scope creep/тупик: назвать проблемный invariant, полученное evidence, ограниченное
   исправление и более простой вариант. Пересмотреть ошибочное решение через ADR,
   но не скрыто ослабить RLS, takeover, no-resend или утверждённый native context.
5. Продолжать уже разрешённые read-only/reversible работы самостоятельно.
   Пользователь нужен для credentials/budget, разрешённого live scope, фактического
   owner smoke и merge по текущей процедуре, не для пересылки технических догадок.

## Непосредственное следующее действие

C5 выполняет единственную C5-M4.1-CI-RECOVERY-R1 из текущей выдачи выше; C4 HOLD.
После исправления C0 принимает конечный M4.1 candidate и его полный CI;
затем M4.2-PROBE получает фактическую принятую общую базу.
Подготовка probe command/secret инструкции не разрешает платные вызовы или VM
активацию сама по себе; бюджет подтверждает владелец.
