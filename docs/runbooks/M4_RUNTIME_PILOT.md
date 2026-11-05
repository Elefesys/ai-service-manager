# M4 Polza runtime: plan / enable / disable

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
