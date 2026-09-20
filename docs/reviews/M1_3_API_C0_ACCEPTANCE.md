# C0 — M1.3 backend/API slice acceptance

Дата: 2026-09-20. Приёмка после интеграции только backend/API PR #14.
Единственный реестр — [TASK_REGISTER](../TASK_REGISTER.md); активные инструкции —
верхний [M1_HANDOFF](../tasks/M1_HANDOFF.md). Это evidence, не второй task register.

## Текущий post-merge verdict

**M1.3 BACKEND/API SLICE — INTEGRATED / VERIFIED.** C0 подтвердил фактическую
интеграцию и отдельное исполнение main. DB сохраняет VERIFIED. Это evidence
API-приёмки; текущий статус UI/M1.3 находится в едином реестре, UI review — в
[отдельном UI receipt](M1_3_UI_C0_ACCEPTANCE.md). Все pre-merge указания ниже —
история, не текущий незакрытый gate.

- PR #14 MERGED пользователем 2026-09-20T11:34:47Z.
- Actual merge / accepted C5 implementation base:
  `43f22b5e28a93e269eccc25bf73653e47fd01426`.
- Parents: `2bd339ee9bb4638588e5f07b63723caaf717c619` и
  `817e9b472dab896d4afeca5eaf2d4f5313b9a686` — обычный merge commit.
- Tree: `a6051034784d30e1ecb4af4c28caf4a596dafdab`, равен final reviewed PR tree.
- [Отдельный main CI 35508232378](https://github.com/Elefesys/ai-service-manager/actions/runs/35508232378),
  event push / branch main / attempt1: SUCCESS. Head и tested-commit равны actual
  merge выше, это не PR virtual merge. Foundation job `106071528594`, browser
  `106071528724`; оба clean-source gates PASS.
- 153 non-integration + 189 real PostgreSQL + 30 frontend + 6 прежних M1.2 browser
  = 378 cases. Canonical/lint/format/types, generated contracts, migration cycles,
  reproducibility и smoke PASS. Новых локальных PostgreSQL/browser прогонов C0 нет.
- Artifact `10603753909`, ZIP SHA-256
  `427b7d7c5b177459dfc936e97dc35d57c3333e575e653810f9a1199e3c61977e`.
  C0 скачал архив и подтвердил digest, exact tested SHA, пустой worktree,
  reconstructed Git tree и byte equality 11/11 предоставленных originals.

API-01/02 CLOSED, прежние C0 и targeted C8 verdict/evidence сохраняются.
После review implementation bytes не менялись, повторное broad review не нужно.
На момент API-приёмки следующим действием была выдача ограниченного C5 UI/browser
slice от accepted base. Это выполненная историческая выдача; текущие действия
задаются только верхним M1_HANDOFF. Первый coordination commit сохранил accepted
implementation base без отдельного docs merge перед C5.

## История pre-merge решения и границы

**C0 full-PR review PASS; targeted C8 PASS для API-01/02. Backend/API готов к
обычному merge commit при SUCCESS итогового опубликованного head.** Состояние API
до фактического merge и отдельного main CI — REVIEW, не INTEGRATED/VERIFIED.
DB остаётся INTEGRATED / VERIFIED. M1.3 IN_PROGRESS; UI C5 ещё не выдан, M2 не выдан.

Основание: принятые R4, C0/C2 disposition и конечное поручение C1. R4 SHA-256
`0d33a26aa13fb3eda34b0a5c07a4a11dc263b1ee37ce9e3fda126f53e0c0282a` сохранён;
исторические PROPOSED/PENDING в snapshot не переоткрывают принятые D-01…D-13.
Spec/ADR-002/005/006/064/099…109/126/182 и Implementation Plan прочитаны применительно
к этому срезу; 11 canonical originals побайтно совпадают с предоставленными файлами.

## Проверенные snapshots и исполнение

- Accepted base / actual merge PR #13: `2bd339ee9bb4638588e5f07b63723caaf717c619`,
  tree `5bf0a4fc429cc11b1b1b2da03147fad6ab088ad8`; отдельный main CI 35503584157 SUCCESS.
- Сохранён первый C0 coordination commit `4c167e2ea1e2cb3e9721a7cefe5da72372eca0ad`.
- C1 head `26ca3db6f5dd6c6e784583e02d3026edfa321954`, tree
  `0b1a5f9e7365fdfa510de60677f3d736fd460ac6`.
  [CI 35506227688](https://github.com/Elefesys/ai-service-manager/actions/runs/35506227688)
  attempt 1 SUCCESS: 152 non-integration + 189 PostgreSQL + 30 frontend + 6 прежних
  browser = 377 cases. Foundation job 106066399290, browser 106066399214, clean-source PASS.
  Tested virtual merge `48d774c57358cb7c6e057fca704b22cc68b07109` имеет parents accepted
  base + C1 head и тот же tree. Artifact 10604405358, ZIP SHA-256
  `3aeca1c713d8f2f44800adc482ed16ea94f95945d9dad0be145ee3bb28153d19`;
  C0 скачал и сверил digest/tested SHA/пустой worktree/reconstructed tree/originals.
- C0 bounded fix head `a6d44560f035a4a288ab62abbac1ad2bde3651ad`, parent C1 head,
  tree `2a587356a9591c6a997ab245a2c0c9403930222b`.
  [CI 35507439390](https://github.com/Elefesys/ai-service-manager/actions/runs/35507439390)
  SUCCESS: 153 non-integration + 189 real PostgreSQL + 30 frontend + 6 прежних browser = 378 cases; оба clean-source gates PASS.
  Foundation job `106069530080`, browser `106069530154`. Tested virtual merge
  `c391eafdc1fc2d7e14bde03648d39321a7e1b217` имеет parents accepted base + fix head
  и тот же tree. Artifact `10604027359`, ZIP SHA-256
  `a51631b9ec40a7b7246584e9fd7d69c0d8d63f5fe560add3f1682ff67065e915`; C0 проверил
  download digest, tested SHA, clean-source и reconstructed tree. Все обычные
  lint/type/contract/canonical/migration/reproducibility/smoke gates прошли.
- C0 локально: Python 3.13.15, frozen/offline dependencies, Ruff/format/strict mypy,
  153 non-integration tests и generated OpenAPI check PASS. Новый schema regression
  сначала RED на исходном C1, затем PASS на исправлении. Docker локально отсутствует;
  новые локальные PostgreSQL/Playwright результаты не заявляются.
- Targeted C8 проверил именно пять файлов delta `26ca3db6… → a6d44560…`: source,
  47 focused unit/schema/service cases и 14 Node Unicode pattern vectors PASS.
  PostgreSQL execution evidence — штатный GitHub runner, не отдельный локальный C8 run.

После этого receipt отдельный согласованный docs update не меняет implementation.
Его финальные published head/tested SHA/tree/CI C0 проверяет и публикует в PR/ответе.
Следующего коммита только ради записи SHA этого документа не требуется.

## Полный C0 review и ограниченное исправление

Проверен весь diff PR относительно принятого DB base, включая сохранённую
coordination дельту. C1 добавил необходимые billing modules, узкие guarded UOW
adapters, wiring, три routes, additive CORS, generated contracts и tests.
Прежние семь OpenAPI paths и прежние component schemas семантически равны base.
Auth service/store/guards, общий tenancy SQLSTATE mapping, migrations 0001…0004,
grants, frozen auth/tenancy snapshots, frontend, dependencies/locks и CI неизменны.

Только эти два конкретных P2 потребовали targeted C8; повторного полного DB/auth
review не назначалось:

| Finding | Причина и исправление | Проверка / disposition |
|---|---|---|
| C8-M1.3-API-01 | Raw padded 200-scalar contact разрешён runtime после U+0020 trim, но OpenAPI raw maxLength=200 отвергал его. Input-only json_schema_input_type описывает ту же нормализацию/границы, output/runtime constraints сохранены. | Локальный RED→PASS regression, Unicode/emoji/control boundaries, Node Unicode vectors, generated contract check; CLOSED. |
| C8-M1.3-API-02 | Sequential observer 2+2s конкурировал с DB lock2s и outer auth4s; revocation failure мог оставить task вне cleanup. Один observer deadline2s; только test-local command lock3s/statement3.5s; auth4s/idle10s/defaults неизменны; ранний HTTP результат виден, finally release/cancel/bounded gather. | Реальные same-key/conflict/different-key API+PostgreSQL assertions и revocation ordering сохранены; targeted source review и CI; CLOSED. |

Нормализация, fingerprint bytes, permissions, CAS, receipt/Audit и DB lock order
не изменялись. Проверки не удалены и не ослаблены ради CI. Общее подозрение о
`$`/финальном LF не стало finding: Python re и ECMA имеют разные semantics;
универсальное нарушение опубликованного contract не было подтверждено.

## Проверяемая матрица API

Это новая матрица по принятому R4/выданному C1 scope, не исторический документ
1–48 и не новые требования. Происхождение отсутствующей старой матрицы и отдельная
DB-A01…32 остаются в [DB receipt](M1_3_DB_C0_ACCEPTANCE.md).

Сокращения: `API` = `tests/test_m1_3_api_postgres.py`,
`SERVICE` = `tests/test_m1_3_service.py`, `WIRE` = `tests/test_m1_3_http_contract.py`.
API rows исполняются через HTTP adapter и настоящий asm_runtime PostgreSQL.

| ID / R4 | Критерий | Конкретное evidence / существенное assertion |
|---|---|---|
| API-A01 / §6 | Один согласованный snapshot с DB time | `queries.SNAPSHOT` source: один fixed SQL/CURRENT_TIMESTAMP, RLS workspace predicates и pinned revision. API `test_get_real_coherent_snapshot_modes_and_administration_without_billing_gate`: один statement, один CURRENT_TIMESTAMP, evaluated_at между двумя DB timestamps. |
| API-A02 / §6 | Настоящий EntitlementService, modes и typed decisions | Тот же API test: все четыре mode, BOOLEAN false, INTEGER positive/zero string; SERVICE `test_service_modes_typed_values_and_all_precedence_layers`: exact five sorted keys, precedence missing→mode restriction→typed value, archived pinned plan не отменён. |
| API-A03 / §6 | Независимые half-open intervals | API `test_independent_inactive_intervals_in_real_get`: future/expired subscription и mode отдельно; SERVICE `test_half_open_endpoints_and_independent_mode_activity`: включён start, исключён end. |
| API-A04 / §6 | Structural precedence, без pretend empty success | API `test_missing_state_is_structural_503_and_missing_account_patch_is_404`; SERVICE precedence и `test_impossible_snapshots_fail_closed_without_reinterpreting_ddl`: duplicate/wrong scope/overlap/revision/value failures. Невозможные при нормальном DDL состояния — unit evidence. |
| API-A05 / §3–4,7 | Live OWNER permissions отдельно от tenancy:write | API `test_all_routes_repeat_live_authority_before_fingerprint_or_receipt`: ADMIN/PROVIDER/revoked/disabled/expired/foreign/anonymous, точные 401/403 на всех трёх routes, spy fingerprint не вызван, SQL data/command не вызваны, state unchanged. Отдельная typed policy source. |
| API-A06 / §4 | Auth admission + distinct tenant connection + guards | Неизменные AuthService.workspace/AuthStore/TenantDatabase; новые narrow adapters на том же UOW. API mode test: context reset и обе pools checkedout=0; `test_poisoned_uow_cannot_continue_after_billing_command_error`: poisoned operation/release rejected. Прежние auth/tenancy guard cases в полном CI. |
| API-A07 / §4 | Revocation не обгоняет admitted command | API `test_revocation_cannot_overtake_admitted_http_command_then_blocks_replay`: 55P03 при revoke за shared admission, затем один success, после committed revoke replay401 без второй записи; bounded cleanup в исправлении. |
| API-A08 / §4 | Единственный write path, stale-before-no-op, immutable replay | Source: только `platform.update_billing_contact(bigint,text,text)`. API `test_http_command_cas_noop_stale_conflict_replay_and_safe_audit`: NOOP сохраняет name/version/updated_at, stale409/zero claim, key conflict409, UPDATE+1/Audit+1, прежняя metadata после later change, current state отдельным GET. |
| API-A09 / §4 | Same/different key concurrent winner | API `test_real_concurrent_http_claims_and_cas_have_one_changing_winner`: два разных runtime PID реально ждут Lock/blocker, same intent identical200 metadata; same-key different body409; different-key stale409; ровно version2/receipt1/Audit2 including provision. Observer/SQL/auth deadline hierarchy исправлена. |
| API-A10 / §4 | Atomic rollback account/receipt/Audit | API `test_api_command_failure_rolls_back_account_receipt_and_audit`: реальные Audit/finalize constraint faults и outer fault до commit →503, весь state unchanged; subsequent successful same intention. |
| API-A11 / §4,7 | Ambiguous result recovery | API `test_ambiguous_result_after_commit_recovers_same_intent_then_get`: injected response-path failure после настоящего commit, подтверждён state, auth/session+CSRF recovery, same key/body replay без дубля, GET current contact. Это не физический network/browser fault. |
| API-A12 / §5 | Exact normalization/fingerprint и bigint | SERVICE `test_fingerprint_entire_canonical_bytes_and_digest_match_r4` проверяет literal full bytes/hash восьми vectors; API `test_eight_fingerprint_vectors_through_http_match_receipts` сверяет API hash с реальным stored receipt; `test_name_and_bigint_boundaries_reach_real_command_without_precision_loss`: padded200emoji/128key/max version NOOP и overflow rollback503. |
| API-A13 / §5,7 | Strict raw input до hash/claim | API `test_strict_raw_inputs_do_not_hash_claim_or_mutate`: malformed UTF-8/BOM/duplicates/extra fields/wrong scalar types/controls/surrogate/decimal bounds/key cardinality/If-Match/query/Origin/CSRF/content type; fingerprint spy unreachable/state unchanged. Новый C0 schema test закрывает raw-vs-normalized input mismatch. |
| API-A14 / §7.3 | Tenant-scoped exact Audit pagination | API `test_audit_keyset_tie_break_end_empty_and_strict_tenant_anchor`: equal timestamps, UUID tie-break, tuple pages, last-row anchor, null end, foreign/nonexistent/invalid/duplicate cursor/query422; собственный existing anchor допустим. Command/Audit test подтверждает exact payload и отсутствие contact/key/fingerprint. |
| API-A15 / §7.4 | Exact errors, оба 503; общий mapper сохранён | API `test_both_503_variants_with_actual_postgres_read_failure`: настоящий failing SQL billing→required DATABASE_UNAVAILABLE, auth boundary→code-only UNAVAILABLE, no diagnostics и следующий healthy GET. Command tests: 404/409/422; scoped `contact_error` проверяет code/message/function context, global `_SQL_ERRORS` byte unchanged. SERVICE/WIRE exact disjoint error schema tests. |
| API-A16 / §7 | Ровно три новых routes, strict DTO/generated contract | `tests/test_auth_contract.py::test_auth_machine_contract_and_generated_c5_api_have_no_drift`: exact old7 + new3 inventory. WIRE `test_generated_billing_schemas_are_strict_disjoint_complete_and_keep_auth_error`: required/additionalProperties, union, decimal strings, six-digit timestamps; export check и semantic comparison всех old paths/components с base. |
| API-A17 / §7 | Только additive CORS | WIRE `test_additive_cors_preserves_configured_origin_credentials_and_old_headers`: configured-Origin PATCH/content-type,x-csrf-token,idempotency-key200, old POST/GET retained, hostile origin/method/header denied, credentials/no wildcard. Реальный M1.3 browser proof остаётся C5. |
| API-A18 / scope | Сохранность принятого и честная граница готовности | Full diff/file comparison: DB/auth/tenancy frozen mechanisms, R4, 11 originals, frontend/dependencies/CI сохранены; все старые tests в том же run. Docs говорят только о backend/API review, без готовности UI/M1.3/production. |

## Что остаётся

Обязательных implementation blockers этого backend/API-среза после двух исправлений
не выявлено. Final-head CI перед merge и отдельный actual main CI после merge
остаются gates, не повторным проектированием. До них не ставить API VERIFIED.

Затем отдельное C5 поручение: минимальный owner screen, subscription/entitlements,
contact edit/recovery, Audit, component tests и реальные M1.3 browser journeys.
Шесть прежних browser journeys подтверждают только M1.2 regression. После C5 review,
integration и общего main CI C0 принимает всю M1.3. Provider billing/client payments,
catalog/subscription/mode editors, Jobs, production и M2 за границей этого среза.
