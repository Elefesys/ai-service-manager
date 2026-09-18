# M1.2 — контракт Business Console UI

Дата: 2026-09-18. Владелец реализации: C5. Принятый API snapshot: `aa7e792555c19d798eafa0cae17d29b73ca12376`. Это consumer contract, а не новый реестр, endpoint или доменное решение.

## Границы и состояния

Business Console имеет взаимоисключающие состояния: `checking` (первичный `GET /auth/session`, защищённые данные скрыты), `anonymous`, `authenticating`, `authenticated`, `recovering` и `uncertain`. Серверный `401 SESSION_REQUIRED`, а не часы браузера, определяет отсутствие/истечение/revocation сессии. `uncertain` всегда скрывает identity и Business и предлагает один явный повтор проверки. Нет signup/reset/MFA, CRUD, тарифов и будущей CRM.

В authenticated-состоянии показываются только проверенные поля ответа: `user_account_id`, `expires_at`, memberships (`workspace_id`, `role`, `permissions`) и Business (`workspace_id`, `id`, `name`, `status`, `version`, `created_at`). Названия Workspace не синтезируются. Нет memberships, пустой список Business, `403`, `404`, `429` и недоступность — разные состояния. `/ops/` остаётся независимой технической shell с настоящим `/health/ready`, без tenant-данных и операторских действий.

## DTO и transport

Минимальный typed client проверяет на consumer boundary exact JSON shapes из `contracts/openapi.json`: bootstrap содержит только `csrf_token` и `expires_at`, тогда как session/login/rotate дополнительно требуют `user_account_id` и `memberships`; UUIDv4 и UUIDv7 принимаются без изменения значения. Неизвестный/невалидный payload считается unavailable, а не доверенным состоянием. Все URL относительные `/api/v1/...`, каждый запрос использует `credentials: 'include'` и `cache: 'no-store'`. Cookie остаётся HttpOnly. Password, cookie, bearer и CSRF не пишутся в URL, DOM-диагностику, логи или Web Storage. CSRF хранится только в памяти текущей страницы и целиком заменяется успешным session/login/rotate ответом.

Протокол: `POST /auth/bootstrap` с `{}` и `X-CSRF-Bootstrap: 1`; затем один `POST /auth/login` с `{login,password}` и текущим `X-CSRF-Token`; `GET /auth/session`; `POST /auth/rotate`/`POST /auth/logout` с `{}` и текущим CSRF. Login — 3–72 символа на форме; password не trim/normalize и очищается после завершения попытки. Submit блокируется in-flight.

Выбранный явный trigger rotation — кнопка «Обновить защиту сессии». Таймеров и sliding expiry нет; успешная rotation обязана сохранить `expires_at`. Focus/visibility выполняет не чаще одного current-session запроса за событие и не запускает polling.

## Владение запросами и recovery

Каждая auth-смена увеличивает generation и отменяет предыдущие `AbortController`. Business-запрос принадлежит generation + principal + workspace; смена любого владельца немедленно очищает данные, отменяет запрос, а поздний ответ игнорируется. StrictMode bootstrap защищён cleanup/abort; mutation запускается только обработчиком и не повторяется автоматически. Более старый ответ не заменяет новый CSRF.

`401 SESSION_REQUIRED` очищает identity/Business/CSRF и возвращает anonymous flow. `401 INVALID_CREDENTIALS` — общая безопасная ошибка входа. `403 CSRF_REJECTED` запускает только current-session/bootstrap resync, но не повторяет mutation. `403 ACCESS_DENIED` и `404 NOT_FOUND` очищают прежний Business context. `429 RATE_LIMITED` отображает `Retry-After` и не ставит retry timer. 5xx/timeout/network после read означает unavailable.

Network error после login/rotate/logout — неоднозначный результат: mutation не replay. UI скрывает защищённые данные и один раз вызывает current-session. Valid session становится единственной фактической identity/CSRF; `401` подтверждает отсутствие session и ведёт к bootstrap/входу. Если recovery offline, состояние `uncertain` не заявляет успех и ждёт явного «Проверить снова».

Logout intent сохраняется в памяти до доказанного результата. После неоднозначного logout current-session `401` подтверждает signed-out (без заявления о конкретной revocation-транзакции). Если current-session valid, UI ровно один раз завершает logout с полученным актуальным CSRF; следующая неоднозначность снова требует явной проверки. Старый `401` от потенциально устаревшего token не считается успехом. BroadcastChannel не используется: возврат вкладки перепроверяет сервер.

## Запуск и проверки

Vite dev слушает только `127.0.0.1:8080` с `strictPort`; предпочтительный полный путь — собранный frontend/nginx на `http://127.0.0.1:8080`. Synthetic credentials создаются существующим provisioning flow только в LOCAL/TEST; frontend их не содержит.

Vitest/RTL проверяет state machine, DTO validation, ошибки, double submit, generation/abort и ambiguity recovery с test doubles. Playwright (workers=1, trace/video/HAR/storageState выключены) проверяет небольшой набор journey A–F через собранный nginx, настоящий API и disposable PostgreSQL TEST. Browser password передаётся приватным временным файлом/переменной процесса, не печатается; screenshots не содержат credentials/token. Vitest и Playwright discovery разделены. До фактического `scripts/test_browser.sh` PASS E2E считается только подготовленным.
