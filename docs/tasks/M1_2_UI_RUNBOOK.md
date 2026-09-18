# M1.2 Business Console — LOCAL/TEST runbook

Этот runbook запускает только принятый LOCAL/TEST slice. Production credentials, реальные данные и Platform Ops privileges не используются.

## LOCAL через nginx (`127.0.0.1:8080`)

1. Создать локальные случайные DB credentials: `python3 scripts/init_local.py` (существующий `.env` не заменяется).
2. Загрузить pinned images: `set -a; . ./.env; . ./infra/images.lock.env; set +a`.
3. Запустить стек: `docker compose --env-file .env up -d --build postgres migrate api frontend`.
4. Создать synthetic owner через migration identity. Пароль нельзя передавать аргументом: `docker compose --env-file .env run --rm -it -e ASM_ENVIRONMENT=LOCAL -e ASM_MIGRATION_DATABASE_URL="postgresql+psycopg://asm_migrator:${PG_MIGRATION_PASSWORD}@postgres:5432/asm_local" checks python scripts/provision_local_auth.py --login local.owner`.
5. Открыть `http://127.0.0.1:8080/`. `/ops/` показывает только readiness. Остановить: `docker compose --env-file .env down`.

Для разработки Vite используется строго `127.0.0.1:8080`: сначала отдельно поднять API на `127.0.0.1:8000`, затем `cd frontend && npm run dev`. Порт 5173 не входит в accepted allowlist.

## Проверки

Frontend: `cd frontend && npm ci --ignore-scripts --no-audit --no-fund && npm run typecheck && npm test && npm run build`.

Полный disposable browser gate: сначала `cd frontend && npx playwright install --with-deps chromium`, затем из корня `sh scripts/test_browser.sh`. Скрипт создаёт отдельный `asm_test` на tmpfs, случайный password в private temporary file, запускает собранный nginx + настоящий API/PostgreSQL, выполняет Playwright workers=1 и всегда удаляет volume/temporary directory. Password не печатается. Trace, video, HAR, storageState и автоматические auth screenshots выключены.

Ручные screenshots можно делать только после logout или на пустой anonymous форме; не включать введённый login/password, идентификаторы, cookies или browser storage. Воспроизводимые обзорные изображения anonymous desktop/narrow сохраняются как `frontend/e2e/screenshots/login-desktop.png` и `login-narrow.png`; эти два generated PNG игнорируются Git и передаются C0 отдельно от source commit.

## Диагностика без ослабления защиты

`401 SESSION_REQUIRED` после reload означает обычную anonymous/session-expired ветку. При network uncertainty нажать «Проверить снова»: mutations автоматически не повторяются. `403` не исправляется сменой client-side UUID — сервер проверяет membership. Не добавлять wildcard Origin/Host, не читать cookie из JavaScript и не переносить CSRF в storage. Docker-less окружение может выполнить frontend checks, но не является evidence browser/API/PostgreSQL PASS.
