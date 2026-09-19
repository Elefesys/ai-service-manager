# C0 — M1.3 R3: решение по targeted C2 re-review R2

Дата: 2026-09-19. Это решение C0 о следующей редакции, не принятый DDL contract и не новый LOCKED ADR.

## Snapshot и evidence

C2 проверил published head `cded2b2417df2d7a98e83c0b41acbe0c0c7c34b3`, tree `07057b6f37da8d44603f18b0ef4d4327176ba97f`. Исходный task base `28c289ce6f77e33676cfa416585cc0e20c0be4e3` сохраняется. Текущий принятый main `049b212f135f09c025d2f81badc810fa7c2c9d13` — отдельный maintenance merge PR #10. Локальная недоступность этого object у C2 не опровергает ранее проверенный C0 main CI; ancestry main→R2 не утверждается.

Исходный C2 отчёт предоставлен пользователем; SHA-256 UTF-8 файла: `8d03f5cbd5225232843e220e0b5e55193b3848f9563abe9e0166b06188bd45b8`. Собственное execution evidence C2 ограничено чтением, Git/hash проверками и manifest digest, без PostgreSQL/browser. C0 дополнительно сверил отчёт с R2, D-01…D-13, архитектурой, принятым auth/UOW и актуальными refs. Новый runtime test result отсутствует.

## Disposition

CHANGES_REQUESTED сохраняется. OPEN: C0-M1.3-R2-01 P2; C2-M1.3-R2-02/03/04/08 P1; C2-M1.3-R2-05/06/07/09 P2. Девять замечаний относятся к контракту до реализации. Ни одно не закрывается автоматически после правки C1.

## Направления R3

1. Вернуть GET /api/v1/workspaces/{workspace_id}/billing; PATCH /api/v1/workspaces/{workspace_id}/billing-account; GET /api/v1/workspaces/{workspace_id}/audit-events.
2. Live authorization до любого receipt observation/claim. Внешняя auth admission и tenant UOW — две connections; receipt/account/Audit — одна tenant transaction.
3. Exact column/constraint/index/grant matrix для существующих восьми таблиц. Полные двухсторонние receipt-state и Audit discriminator CHECK, без SQL NULL loopholes. Новые детали C1 — предложения R3 для review, не уже принятые решения.
4. Каждый Workspace-owned lookup/write definer-команды явно scoped по единожды проверенному trusted workspace; никаких unscoped lookup по id/key. FORCE RLS сохраняется; SECURITY DEFINER сам по себе не отключает FORCE RLS. Учитывать эффективную роль и migrator policy, не полагаться только на runtime policy.
5. Fingerprint v1 сохраняет SHA-256 canonical JSON из четырёх D-04 полей. R3 уточняет raw UTF-8, exact escaping, отсутствие BOM/newline и strict scalar validation; одинаковые bytes обязательны для будущих DB/application реализаций. C0 предоставляет synthetic vectors; не вводится новая dependency или fingerprint argument функции.
6. Provisioning Audit payload — ровно {}; contact payload — ровно {"changed_fields":["contact_display_name"]}. Пары event/actor/object задаются CHECK; raw name, fingerprint, key и секреты в Audit не попадают.
7. Полные DTO/error shapes всех трёх routes, decimal-string bigint и единый UTC timestamp format. Существующий M1.2 envelope {"error":{"code":"..."}} и его endpoints не изменять.
8. LOCAL/TEST initializer адресуется Workspace и явными catalog revision/interval inputs. Fresh создаёт complete state атомарно; complete matching repeat — no-op без нового Audit/UUID/версии; partial/mismatch — conflict без overwrite/repair. После поздних contact/mode/subscription изменений повтор не откатывает состояние. Это initializer contract, не обещание replay старого contact response.
9. Pinned LOCAL/TEST image extension/version/namespace/opclass и admin preflight остаются локальными prerequisites до отдельной implementation-выдачи; неизвестные значения не выдумывать. Будущий production SKU/retention/prices/privacy остаются отдельными OPEN и не блокируют саму локальную contract correction.

Решения D-01…D-13 не отменены. Полный fingerprint/provisioning/DTO алгоритм фиксирует R3 с явным mapping девяти findings и повторным C0/C2 review. Без нового inventory/roles, Jobs/Outbox/provider/paid billing и без изменения принятых исходников.

## Разрешение и ограничения

C1 разрешены только `docs/TASK_REGISTER.md` (точный C0 transfer), этот receipt (точный C0 текст), `docs/tasks/M1_3_CONTRACT.md` (R3 proposal). Предыдущий `docs/reviews/M1_3_C0_C2_DISPOSITION.md` сохраняется побайтово как история D-01…D-13. PR #9 остаётся OPEN/DRAFT/NOT MERGED. C1 не изменяет main, не копирует keyboard patch в контрактную ветку и не назначает successor 0003. M1.3 остаётся IN_PROGRESS.
