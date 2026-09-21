# M2.2 — private images в LOCAL/TEST

Этот runbook описывает реализацию Draft PR #19. Статус и очередность работ —
только в [TASK_REGISTER](../TASK_REGISTER.md) и активном
[M2_HANDOFF](../tasks/M2_HANDOFF.md); технический контракт —
[M2_CONTRACT §9](../tasks/M2_CONTRACT.md#9-m22-private-images--принято-c0c2c3-2026-09-21).
Это controlled provider и внутренний owner service, без Telegram, HTTP file route,
Console UI, owner uploads или production deployment.

## Версии и конфигурация

| Компонент | Зафиксированная версия |
|---|---|
| Миграция | `0006_private_images.py`, revision `0006`, predecessor `0005`; 0001–0005 неизменны |
| S3 SDK | `boto3==1.43.98`; dev typing `boto3-stubs[s3]==1.43.98` |
| Decoder | `pillow==12.3.0` |
| S3 server | MinIO `RELEASE.2025-09-07T16-13-09Z`, официальный `quay.io/minio/minio`; digest в `infra/images.lock.env` |
| Bootstrap CLI | MinIO mc `RELEASE.2025-02-15T10-36-16Z`, официальный `quay.io/minio/mc`; digest в том же lock |

`uv.lock` добавляет только эти зависимости и необходимые transitive/typing packages;
прежние external package blocks, hashes и пять прежних image pins сохранены. `pin_images.sh`
сохраняет имеющиеся pins и добавляет отсутствующие; обычный checkout использует lock.

`python3 scripts/init_local.py` создаёт отсутствующие LOCAL secrets в игнорируемом
`.env` с mode 0600. Повторный запуск не заменяет прежние значения или содержимое.
Не включать `.env`, credentials, подписанные URL или вывод раскрытого Compose config
в source, build context, logs и reports. Bootstrap выводит только bounded PASS/FAILED.

| Переменная | Назначение |
|---|---|
| `STORAGE_ROOT_USER`, `STORAGE_ROOT_PASSWORD` | Только server/bootstrap; API/worker/checks их не получают |
| `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` | Отдельный runtime user для private bucket |
| `ASM_STORAGE_ENVIRONMENT` | `LOCAL` или `TEST`; worker требует совпадения с DB environment |
| `ASM_STORAGE_ENDPOINT` | Operator-owned origin; `http://storage:9000` или `http://storage-test:9000` внутри Compose |
| `ASM_STORAGE_BUCKET` | `asm-private-local` / `asm-private-test` |
| `ASM_STORAGE_REGION` | `us-east-1` по умолчанию, подпись SigV4 |

LOCAL object data находятся в `storage-data`, TEST — в disposable tmpfs отдельного
`storage-test`. S3 и admin console не публикуют host ports; HTTP допустим здесь
только внутри изолированной LOCAL/TEST сети. Runtime policy даёт Get/Put/Delete
лишь `bucket/workspaces/*` и ListBucket лишь своего bucket (для точного HEAD 404
при отсутствии key); создание/администрирование bucket и доступ к другому bucket
запрещены. Anonymous GET/LIST/PUT запрещены. После нового init existing LOCAL bucket
остаётся private; root credentials никогда не становятся runtime credentials.

## Запуск и проверка

Нужны Docker/Compose и зависимости штатного browser script. Из корня checkout:

```sh
python3 scripts/init_local.py
docker compose --env-file infra/images.lock.env --env-file .env up -d --wait api worker scheduler frontend
```

Compose выполняет PostgreSQL bootstrap/migration и private bucket bootstrap до
worker/scheduler. API readiness проверяет DB; outage S3 не превращает auth/DB health
в storage health. CONTROLLED provider хранит только зарегистрированные synthetic
bytes в процессе; пустой provider при обычном запуске не скачивает произвольные URL.
В integration tests provider получает bytes через `ControlledImageProvider.register`
для точной пары canonical bot identity / opaque image reference.

Полная штатная проверка (только disposable TEST database/storage):

```sh
sh scripts/ci.sh
test -z "$(git status --porcelain --untracked-files=all)"
sh scripts/test_browser.sh
test -z "$(git status --porcelain --untracked-files=all)"
```

CI запускает эти scripts на обычном GitHub Linux runner. Первый script проверяет
real PostgreSQL/S3, unit/static checks, migration cycles, contracts, wheel/frontend
reproducibility и HTTP/worker/scheduler smoke. Второй сохраняет прежние M1 browser
journeys. Это не browser E2E изображений: новый публичный API/UI не входит в M2.2.
Foundation archive содержит tested commit, source archive, worktree status и logs;
точные final head/tree/tested SHA/run/artifact фиксируются в PR receipt после CI.

## Работа и recovery

1. DB capability в одной транзакции создаёт inbound Message, PENDING FileObject и
   FETCH_IMAGE Job. UNIQUE/composite FK и locks защищают concurrent dedupe.
   Миграция делает такой же backfill прежних image Messages без внешнего I/O.
2. Короткий worker unit восстанавливает source по Job → FileObject → Message →
   Connection. Caller Workspace/ref/key/URL не заменяют эту связь.
3. Provider stream ограничен фактическими 10 MiB. Decoder проверяет JPEG/PNG/static
   WebP, один frame, максимум 20 млн pixels и 8192 на сторону, container integrity
   и полное decode. Сохраняется оригинал с actual MIME, size, SHA-256 и dimensions.
4. До PUT фиксируется immutable intent и отдельный key
   `workspaces/<workspace>/files/<file>/attempts/<intent>`. После подтверждённого PUT
   одна fenced transaction делает intent WINNER, file READY и Job SUCCEEDED.
   Повтор finalize после потерянного ACK читает тот же canonical winner.
5. Ошибка/cancellation/expiry оставляет durable intent. Retry получает другой key;
   старый PUT не перезаписывает новый winner. Потеря prepare ACK не разрешает PUT.
   Invalid/missing input terminal; остальные retry ограничены пятью claims/15 min.
6. Scheduler получает до двух due cleanup intents за sweep (SQL capability допускает
   до 100), выполняет DELETE вне transaction и guarded finish. Lease 30 s; error
   backoff ограничен 1 h. Даже успешный DELETE сохраняет ABANDONED tombstone и
   повторяет check через 1 h, убирая поздний PUT. WINNER не eligible для cleanup.

FETCH общий budget 20 s при lease 30 s. S3 connect/read — 2/5 s, один SDK attempt,
await budget 8 s и максимум два реально выполняемых synchronous I/O. Cancellation
не освобождает slot, пока sync operation не завершилась. Decoder имеет один slot,
удерживаемый до действительного окончания decode. Provider/S3 I/O не держит DB
connection/transaction. SEND deadline остаётся 10 s; UNKNOWN/no-resend не изменены.

`read_image` принимает authenticated actor и точные Workspace/Conversation/Message/
FileObject IDs, допускает только live OWNER и READY. Signing локальный, без metadata
или credential discovery. Возвращается URL на 60 s и точный `expires_at`, безопасное
UUID filename, validated MIME, `private, no-store`. После revoke новые URL запрещены;
уже выданная bearer URL может работать до expiry. Отдельный raw storage key/provider
URL service не выдаёт. Disconnect connection не закрывает OWNER доступ к истории.

## Диагностика

| Наблюдение | Проверка и допустимое действие |
|---|---|
| Image FileObject FAILED | Bounded `error_code` и Job state через доверенный diagnostic/migrator context; malformed/missing input не исправляется resend Message |
| PENDING при S3 outage | Вернуть доступность LOCAL/TEST сервиса; scheduler reclaim/retry обработает durable intent, не устанавливать READY вручную |
| `STORAGE_BOOTSTRAP_FAILED` | Проверить доступность pinned image/server и согласованность уже существующего `.env`, не печатая credentials; bootstrap можно повторить |
| ABANDONED key появился после DELETE | Это ожидаемый поздний PUT; tombstone сохраняется, следующий bounded sweep снова удалит key |
| Cleanup service outage/потерянный ACK | Состояние остаётся durable, lease reclaim и retry; не удалять tombstone и не выполнять массовый DELETE prefix |
| Signed URL 403 | Проверить TTL, exact URL и текущую S3 конфигурацию; получить новую через owner service после live authorization, не увеличивать TTL |
| DB revision mismatch | Выполнить штатный upgrade head; не менять применённые 0001–0005 |

Downgrade 0006→0005 предусмотрен только в согласованном disposable TEST cycle:
удаляет file metadata/FETCH jobs, сохраняет Message IDs/content/fingerprints и
прежние billing/receipts/UNKNOWN. Внешний S3 I/O в migration запрещён; downgrade
не является production rollback/garbage collection. Re-upgrade снова планирует
image fetch. Не применять этот цикл к постоянному LOCAL storage с ценными данными.

При потере DB вместе с tombstones объектная очистка не гарантируется этим срезом.
Cleanup eventual при доступных DB/S3; tombstones не compaction/retention система.
Внешнее облако, HTTPS ingress, Telegram, multi-node S3 durability, backup/restore
private objects и production эксплуатация требуют отдельной проверки.
