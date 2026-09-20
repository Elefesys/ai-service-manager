# C0 — M1.3 DB slice acceptance

Дата: 2026-09-20. Это receipt DB-среза PR #13, не приёмка всей M1.3.
Единственный реестр — [TASK_REGISTER](../TASK_REGISTER.md); единственный активный
handoff — верхний блок [M1_HANDOFF](../tasks/M1_HANDOFF.md).

## Текущий post-merge verdict — 2026-09-20

**M1.3 DB SLICE — INTEGRATED / VERIFIED.** Это приёмка только DB. Milestone
M1.3 остаётся IN_PROGRESS; backend/API и UI ещё не приняты. Исторические
pre-merge условия ниже выполнены и сохранены как evidence, не как текущий блокер.

PR #13 фактически MERGED пользователем 2026-09-20T09:54:20Z обычным merge commit:

- Actual main / accepted C1 base: `2bd339ee9bb4638588e5f07b63723caaf717c619`.
- Parents: `552e74c7b542b81ee523d1eccfa0fffe7de06a5b` и `0df55aa577b49b6bc863c2f8b76d1851eea01457`.
- Tree: `5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8`, совпадает с final reviewed PR tree.
- Отдельный [main CI 35503584157](https://github.com/Elefesys/ai-service-manager/actions/runs/35503584157): event `push`, branch `main`, head/tested-commit равен actual merge. Это отдельный run после слияния, не PR virtual merge.
- `foundation` job `106059511797`, `browser` job `106059511924`: SUCCESS, оба clean-source gates PASS.
- 106 non-integration + 146 real PostgreSQL + 30 frontend + 6 прежних M1.2 Playwright = 288 cases. Canonical import, migration lifecycle/readiness, contracts/types/lint, Docker/proxy smoke и wheel/assets reproducibility прошли.
- Artifact `10603615904`, ZIP SHA-256 `d7262e5802a1271907f4c215ed40258dcbe7217118d76fabf04615fd8f36b834`. C0 скачал archive, проверил digest, actual tested SHA, пустой worktree, reconstructed Git tree и byte equality 11/11 canonical originals.

Новых code delta после C0/C8 acceptance нет. Прежние границы новой DB-A01…32
матрицы и targeted C8 сохраняются; отдельный повторный review не нужен.

C0 выдаёт следующий ограниченный backend/API scope C1 в единственном активном
M1_HANDOFF от подтверждённого base выше. Первый docs commit task branch
`c1/m1-3-billing-api` синхронизирует только реестр/handoff/этот receipt; code base
сохраняется. C1 API acceptance и отдельная интеграция предшествуют C5 owner UI.
После C5/integration C0 решает статус всей M1.3; до этого не выдавать M2.

## История pre-merge решения и границы

**C0 DB REVIEW — PASS; TARGETED C8 — PASS.** Оставшихся implementation blockers
DB-среза не выявлено. Implementation PostgreSQL CI прошёл. Для разрешения
пользователю обычного merge commit обязателен SUCCESS обоих jobs именно итогового
документационного head; C0 фиксирует его точный SHA/run в PR без нового docs commit. Actual merge и
отдельный push/main CI ещё не выполнены; DB остаётся REVIEW до интеграции.
Backend/API/UI M1.3 не приняты; M1.3 — IN_PROGRESS; M2 не выдан.

Нормативное основание: принятый R4 `docs/tasks/M1_3_CONTRACT.md`, D-01…D-13,
применимые Spec/ADR и разрешённый C0/C2 DB scope. SHA-256 R4:
`0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a`;
Git blob `d1e80cb9242a4c0a88e2762bb17d46fa4d9f3320`.
Исторические PROPOSED/PENDING внутри сохранённого R4 не отменяют последующей
приёмки PR #9 и prerequisite PASS. Сам контракт не переписан.

## Проверенные snapshots и execution evidence

| Назначение | Head / tested snapshot | Результат |
|---|---|---|
| Base main PR #13 | `552e74c7b542b81ee523d1eccfa0fffe7de06a5b`; tree `aa2291439857af7c4e10a06baad81be58eada781` | Проверен текущий base |
| Исходный implementation | `fa83d6122bf03ccd8f91a28cb8712eb7f9703616`; tree `e09daa0577a24fbaf4f9870da648596ccd9b7d76` | [CI 35496392135](https://github.com/Elefesys/ai-service-manager/actions/runs/35496392135) SUCCESS; targeted C8-M1.3-DB-01 PASS, только observer/timing fix |
| Новые regressions без исправления | `46311fad4f5ea8959a117c52b5441ab79f4565a3` | [CI 35502294158](https://github.com/Elefesys/ai-service-manager/actions/runs/35502294158): 9 ожидаемых DB failures, 137 DB passed; прежние 134 DB cases сохранились |
| Исправленный implementation | `cc172d12e3d48f47d294d862a0c73b6ea126320d`; tree `f32ec3b726d5c008476530625b56ce32c31fe1e3` | [CI 35502644158](https://github.com/Elefesys/ai-service-manager/actions/runs/35502644158) SUCCESS; 106 non-integration + 146 PostgreSQL + 30 frontend + 6 browser = 288 cases |
| Фактически протестированный PR merge исправления | `06644d970a9dbf9ebad423179d4b41cf42586dad`; то же tree `f32ec3b726d5c008476530625b56ce32c31fe1e3` | Artifact `10603230182`; C0 проверил ZIP SHA-256, tested-commit, пустой worktree и reconstructed Git tree |

Artifact исправления SHA-256:
`2cce46f9639462a320371060c434ecd330b5c730f2a6315495366607a87bf1f3`.
Jobs `foundation` / `browser` и оба clean-source gates SUCCESS. Выполнены обычные
`sh scripts/ci.sh` и `sh scripts/test_browser.sh`: pinned PostgreSQL Docker image,
реальные `asm_migrator`/`asm_runtime`, migration cycles, lint/format/mypy, generated
contract drift checks, frontend type/build/tests, wheel/assets reproducibility,
HTTP/proxy smoke и Playwright. Повторные frontend runs не суммируются.
Это GitHub Linux/amd64 execution, не неподтверждённый локальный Docker запуск.

Финальная синхронизация разрешает поверх reviewed implementation ровно три paths:
`docs/TASK_REGISTER.md`, `docs/tasks/M1_HANDOFF.md`, этот receipt. C0 проверяет
final head, неизменность всех implementation blobs и полный CI этого head;
точные final SHA/run фиксируются в PR acceptance comment и сообщении пользователю.
Receipt намеренно не требует нового commit ради SHA собственного docs commit.
Изменение кода/base сверх указанного требует отдельной оценки дельты C0.

## C0 review всего PR и ограниченные исправления

Полный diff main → PR проверен, включая bootstrap/preflight, миграцию 0004,
функции, grants/RLS, readiness, тестовые inventories и реальные результаты.
0001/0002/0003, tenant/auth implementation и frozen tenancy contract, существующие
семь auth routes/DTO, frontend, generated contracts, locks/image pins и обычный CI
не изменены. Readiness требует 0004 отдельно от frozen tenancy contract 0003.
Admin URL добавлен только disposable PostgreSQL test runner; приложение не получает
admin identity. btree_gist устанавливает admin/bootstrap; migrator не получает
SUPERUSER/BYPASSRLS/DB CREATE/расширенные monitoring privileges.

| Finding | Воспроизведение и причина | Исправление / граница |
|---|---|---|
| C8-M1.3-DB-01 | В run 35494457084 migrator не видел runtime activity fields; короткий lock timeout мог завершить фоновую команду раньше observer | Ранее принятый same-role observer, actual blocker/state/Lock checks, observer 5s < lock 15s < statement 20s, early-task failure propagation и cleanup сохранены; прежний C8 PASS не распространялся на весь PR |
| C0-M1.3-DB-02 | Fresh connection без `asm.actor_kind`: NULL в `<>` не входит в IF; ожидание 42501 падало | `IS DISTINCT FROM 'user_account'`; deny до claim, state неизменен |
| C0-M1.3-DB-03 | CHECK пропускал SUCCEEDED с NULL outcome; ожидание 23514 падало | Exact R4 `result_outcome IS NOT NULL`; остальные receipt rules сохранены |
| C0-M1.3-DB-04 | CONFLICT после catalog writes оставлял catalog; NULL code/revision принимались; повреждённый provisioning Audit давал NOOP | NULL-safe bounded input checks, rollback subtransaction для четырёх bounded conflict reasons, проверка Audit object/version; ошибки Audit/SQL не проглатываются |
| C0-M1.3-DB-05 | Два разных keys держат account KEY SHARE от receipt FK; оба повышали lock до FOR UPDATE, фактически получали 40P01 | Account `FOR NO KEY UPDATE`: non-key contact/version update сериализуется совместимо с FK locks; winner UPDATED, loser 40001; order receipt → account и CAS сохранены |

Изменение account lock mode не меняет обязательный R4 lock order и не ослабляет
CAS: account keys не изменяются. Initializer по-прежнему начинает с exact catalog
advisory lock, затем revision parent → Workspace → account/subscription/mode/Audit.
Это исправления существующих обязательств R4, не новый scope или architecture ADR.
Код дельты C0 ограничен 0004 и одним файлом PostgreSQL regressions; старые тесты
не удалены, skip/xfail не добавлены, assertions не ослаблены.

Targeted C8 на новые C0-M1.3-DB-02…05: **PASS** для exact delta
`fa83d6122bf03ccd8f91a28cb8712eb7f9703616` →
`cc172d12e3d48f47d294d862a0c73b6ea126320d`. Новых Blocker/High/Medium/Low findings
нет. C8 independently сверил source/artifact, Ruff/format и 106 non-integration;
второй local PostgreSQL instance не запускался. Полная C0
оценка DB-среза и ограниченный C8 verdict различаются; повторный полный review
старых принятых частей не назначался.

## Происхождение новой матрицы

**Исторический оригинал критериев 1–48 не найден в доступных источниках.** Проверены
переданный continuation/audit, 11 canonical originals и текущие repo docs,
доступные прежние материалы/контекст, PR #13 commits/patch/comments, связанные
PR #9/#11/#12 acceptance records и история handoff. В docstrings тестов остались
частичные ссылки `Criteria 8–11`, `15–30`, `31–45`, `46–48`; это не исходная
матрица, и они не позволяют достоверно восстановить все формулировки/номера.

Ниже **новая C0 traceability matrix от принятого R4**, с собственными ID DB-A01…32.
Она не выдаётся за найденный оригинал и не добавляет требования. `PG` означает
PASS в исправленном implementation run 35502644158; `S` — C0 source/diff review,
не отдельный выполненный тест. Final-head CI повторно проверяет тот же код.

Для точных pytest node IDs: `P::name` = `tests/test_m1_3_postgres.py::name`,
`C::name` = `tests/test_m1_3_c0_acceptance.py::name`,
`M::name` = `tests/test_m1_3_migrations.py::name`.

| ID / источник | Конкретный test / source | Assertions и фактический результат |
|---|---|---|
| DB-A01 / §1–2, C0 reservation | P::test_m1_3_inventory_extension_rls_and_privileges; 0004 revision metadata | Ровно восемь M1.3 таблиц, 0004 → 0003, без изменения старых revisions; PG + S |
| DB-A02 / §2 | P::test_exact_physical_schema_constraints_keys_and_grants | Все column order/type/nullability/defaults равны матрице; entity uuidv7, внешние FK без default; PG |
| DB-A03 / §2 | тот же P test | Named PK/UNIQUE/FK exact columns/targets, RESTRICT/NO ACTION, not deferrable; PG |
| DB-A04 / §2 | тот же P test + 0004 DDL against R4 | Наличие/type CHECK проверяется автоматически; полные CHECK expressions сверены C0 вручную, существенные negatives ниже; PG + S, не заявлено автоматическое сравнение всех выражений |
| DB-A05 / §2.5 | P::test_initializer_manifest_overlap_adjacency_and_replay; P::test_exact_physical_schema_constraints_keys_and_grants | Exact immediate GiST exclusion `[)`; overlap same Workspace rejected, adjacency accepted; PG |
| DB-A06 / §2.5–2.7 | P::test_finite_intervals_and_tenant_safe_composite_fk_negatives | Два infinity cases отвергнуты (23514); Audit object из другого Workspace отвергнут (23503). Actor FK проверен introspection DB-A03; discriminator/payload — DB-A28; PG |
| DB-A07 / §3 | P::test_m1_3_inventory_extension_rls_and_privileges; P::test_exact_physical_schema_constraints_keys_and_grants | ENABLE+FORCE RLS всех пяти tenant tables; runtime SELECT семи, none receipts, нет INSERT/UPDATE/DELETE; PG |
| DB-A08 / §3 | tests/test_tenancy_postgres.py::test_runtime_roles_policies_functions_and_platform_surface; _rls_and_grants source | Exact function/profile surface, PUBLIC revoked, runtime execute только typed contact command из новых functions, qualified references/search_path; PG + S |
| DB-A09 / §3 | P::test_m1_3_runtime_cross_workspace_and_xid_fail_closed | A и B видят только свои rows четырёх readable tenant tables; missing/malformed/stale-XID context даёт zero rows и command 42501; PG |
| DB-A10 / §3–4 | C::test_missing_actor_kind_is_denied_before_receipt_claim | На физически свежем connection missing GUC равен NULL; command 42501, account/receipts/Audit неизменны; PG; red→green |
| DB-A11 / §2.2–2.3, §8 | P::test_sealed_manifest_immutability_and_draft_subscription_rejection | Exact пять capabilities/typed values/criticality и SHA-256 manifest; sealed mutations rejected, DRAFT subscription FK rejected; PG |
| DB-A12 / §2.2–2.3, §4 | P::test_entitlement_insert_and_seal_serialize_on_catalog_and_parent_locks | Реальные separate-connection writers блокируются на catalog/parent locks; после seal поздняя вставка rejected; PG. Supported initializer seal также сверён S; raw privileged bypass не обещается |
| DB-A13 / §8 | P::test_initializer_manifest_overlap_adjacency_and_replay | INITIALIZED → NOOP и INITIALIZED другого Workspace, один catalog и пять entitlements; PG. Отсутствие writes на NOOP, стабильность полей и один provision event проверены initializer source; S |
| DB-A14 / §4, §8 | P::test_initializer_conflicts_and_concurrent_serialization; initializer source | Две fresh Workspaces дают INITIALIZED; same Workspace INITIALIZED/NOOP; глобальный lock до catalog lookup. PG проверяет concurrency с уже существующим catalog; S проверяет общий create/resolve lock path, не заявлен отдельный first-catalog race run |
| DB-A15 / §8 | P::test_initializer_conflicts_and_concurrent_serialization; C::test_initializer_detects_provisioning_audit_drift | Partial/input/drift дают bounded conflict без repair; повреждённый provision object_version не принимается за NOOP; PG, Audit red→green |
| DB-A16 / §8 | C::test_initializer_conflict_has_no_catalog_or_workspace_side_effects[missing_workspace,partial,input,null_code,null_revision] | Изолированный пустой catalog; пять conflicts оставляют counts всех восьми tables без изменений; NULL catalog inputs не INITIALIZED; PG, red→green |
| DB-A17 / §3–4 | P::test_billing_contact_authorization_cas_replay_audit_and_fingerprint | Outsider denied 42501; trusted OWNER success. Source явно scoped по workspace для всех receipt/account/Audit references; PG + S |
| DB-A18 / §4 | тот же P test | Version CAS до normalized no-op: stale 40001 без новых receipt/Audit; update +1 и UPDATED; PG |
| DB-A19 / §4 | тот же P test + no-op branch source | Normalized same-name NOOP, version тот же, SUCCEEDED receipt, нет нового contact Audit; отсутствие account UPDATE/timestamp mutation сверено S; PG + S |
| DB-A20 / §4 | тот же P test; C::test_replay_after_later_change_rechecks_live_authorization | Exact metadata replay; после более позднего изменения прежний response сохранён и current account не откатывается; PG |
| DB-A21 / §4 | C::test_replay_after_later_change_rechecks_live_authorization | После revoke и старый, и новый key получают 42501; состояние включая updated_at не меняется; PG |
| DB-A22 / §4 | P::test_concurrent_new_idempotency_key_serializes_before_account_lock[False,True] | Same key waits на actual blocker под asm_runtime observer; затем replay либо 23505, одна mutation; preserved timing/early-task guard; PG |
| DB-A23 / §4 | C::test_different_keys_share_fk_locks_and_have_one_cas_winner | Barrier после immediate receipt FK checks; оба держат KEY SHARE; ровно UPDATED v2 и 40001, один receipt, два Audit включая provision; PG, 40P01 red→green |
| DB-A24 / §2.8 | C::test_succeeded_receipt_rejects_null_outcome; command finalize source | SUCCEEDED/NULL outcome rejected 23514; supported command не коммитит IN_PROGRESS; PG + S, red→green |
| DB-A25 / §4 | P::test_billing_contact_authorization_cas_replay_audit_and_fingerprint; C::test_command_failure_rolls_back_receipt_account_and_audit[audit,finalize] | Outer rollback и реальные failures на Audit/finalize не оставляют claim/account/Audit изменений; PG |
| DB-A26 / §5 | P::test_exact_published_fingerprint_vectors_in_postgres (8); actual command loop в test_billing_contact_authorization_cas_replay_audit_and_fingerprint | Все восемь exact published digests проверены и reference SQL, и stored fingerprint настоящей команды, включая Cyrillic/escaping/emoji/U+2028/U+2029/NFC distinction; PG |
| DB-A27 / §2.4, §5 | P::test_billing_contact_authorization_cas_replay_audit_and_fingerprint | Invalid name/control/length, nonpositive version и invalid/long key → 22023; payload/receipt не содержат contact value; PG |
| DB-A28 / §2.7 | тот же P test; P::test_finite_intervals_and_tenant_safe_composite_fk_negatives; Audit DDL | Exact payload changed_fields, composite object/actor FKs, discriminator allowlist/4096-byte bound; PG + S |
| DB-A29 / §6, DB часть | P::test_coherent_entitlement_snapshot_and_service_mode_filtering (4 modes) | One-statement SQL snapshot; criticality sets NORMAL/GRACE/LIMITED/SUSPENDED и independent inactive/future intervals; PG. Это feasibility данных, не реализация EntitlementService/API |
| DB-A30 / §8 prerequisite | M::test_prerequisite_damage_fails_before_domain_ddl (4 damages) | Missing/wrong namespace/wrong version/wrong UUID opclass: upgrade fails и ни одной domain table; PG |
| DB-A31 / §8 lifecycle | M::test_existing_0003_admin_prerequisite_repeat_downgrade_and_reupgrade; tests/test_tenancy_migrations.py::test_fresh_m0_idempotent_downgrade_reupgrade_and_readiness | Existing 0003 + repeated admin preflight, 0004→0003→0004, extension retained; fresh/M0/repeat cycles и readiness exact head; PG |
| DB-A32 / preservation / scope | Полный CI + main→PR source diff; tests/test_foundation.py::test_runtime_database_head_is_independent_from_frozen_tenancy_contract | Прежние tenant/auth/PostgreSQL механизмы и M1.2 browser сохранены; canonical imports 11/11; нет API/CORS/UI M1.3 implementation claims; PG + S |

## Существенные ограничения доказательства

Матрица сочетает catalog introspection, реальные positive/negative/concurrency
executions и source review; она не объявляет каждое предложение контракта отдельно
исполненным тестом. Исходные 134 PostgreSQL cases плюс 12 C0 regressions дают 146;
никаких отдельного production certification, privileged SQL compromise protection
или выполнения на ПК пользователя не заявлено.

C0 принимает DB-A14 с явно указанным составным доказательством: общий
advisory-first путь create/resolve проверен source review, фактическая блокировка
и два concurrent Workspace writers проверены PG, fresh-catalog rollback — новыми
PG regressions. Отдельный first-catalog race не выдаётся за выполненный тест;
конкретного незакрытого дефекта этой ветки не установлено, поэтому дополнительная
итерация review/новый scope не назначаются.

В DB-срезе нет billing repository/EntitlementService, HTTP routes, permission
mapping в API, DTO/error union/cursor, additive CORS, generated M1.3 consumers,
owner UI и M1.3 browser journeys. Их accepted specification уже есть в R4, но
реализацию и end-to-end доказательства должен дать следующий C1/C5 scope.
Принятая M1.2 admission/revocation семантика сохранена; прямые SQL tests не выдают
её за уже выполненную интеграцию будущего billing HTTP handler.

## История pre-merge последовательности действий (DB шаг выполнен)

1. После targeted C8 и SUCCESS final head C0 даёт пользователю READY TO MERGE
   только PR #13 DB. Пользователь выполняет обычный **Create a merge commit**
   (при необходимости Ready for review), возвращает PR URL или merge SHA.
2. C0 проверяет actual merge/parents/tree и отдельный push/main SUCCESS; только
   после этого фиксирует DB INTEGRATED / VERIFIED и готовит одно готовое поручение
   C1 с подтверждённым base и всем обязательным scope из активного handoff.
3. После приёмки и интеграции C1 C0 выдаёт C5 один минимальный owner screen,
   recovery/Audit/component/browser scope. До принятого API C5 не запускать.
4. После C1+C5 и общей интеграционной приёмки C0 решает статус M1.3. До этого
   milestone не завершён, M2/production не выданы.

Обоснованное упрощение — продолжать существующие auth/UOW и один owner screen,
переиспользовать принятую SQL command без второго write path. Не нужны новый
billing framework, расширение API, дополнительные экраны, runtime catalog editor
или отдельная архитектурная итерация. R4 checks, atomicity, security, recovery и
обязательные реальные тесты при этом сохраняются.
