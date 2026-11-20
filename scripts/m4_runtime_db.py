"""C3-M4.3-RUNTIME-INTEGRATION-R11: separate owned PG18 application carrier."""

import asyncio
import contextlib
import functools
import hashlib
import inspect
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from uuid import UUID

# C0's exact M5.3A assignment; historical task routes remain unchanged.
M5_INTAKE_BASE = "220606193208a1ef082732e4dfcdf1f2ffbea857"
M5_INTAKE_TREE = "d15f9a75346ab881449010745cbe0216081b78cf"
M5_INTAKE_ASSIGNMENT = "c0b0800341ff6cf7b6d79a5012696f47ea717f64"
M5_INTAKE_ASSIGNMENT_TREE = "45c858d34d4098384b5f9e393af48e40e80b568e"
M5_INTAKE_SCOPE_AMENDMENT = "2c4baae377abd65bc3c807b265f123c23f3e818d"
M5_INTAKE_SCOPE_AMENDMENT_TREE = "196dc2c89f4ad8bdcb8b6bac44178a91b20412b3"
M5_INTAKE_SCOPE_AMENDMENT_PARENT = "5ccd2f84ab3eb036ac602240b3eda7924aa818a9"
M5_INTAKE_BRANCH = "c1/m5-3a-intake-duration-r1"
M5_INTAKE_C0_DOCS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M5_INTAKE_PATHS = {
    "tests/test_auth_contract.py",
    "AGENTS.md",
    "README.md",
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/context.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/fake.py",
    "backend/src/asm/ai/gateway.py",
    "backend/src/asm/ai/intake.py",
    "backend/src/asm/ai/knowledge.py",
    "backend/src/asm/ai/portfolio.py",
    "backend/src/asm/ai/portfolio_delivery.py",
    "backend/src/asm/ai/prompts/conversation_v7.txt",
    "backend/src/asm/ai/provider_runtime.py",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/ai/runtime_settings.py",
    "backend/src/asm/ai/schemas/conversation_result_v3.json",
    "backend/src/asm/ai/settings.py",
    "backend/src/asm/billing/models.py",
    "backend/src/asm/configuration/errors.py",
    "backend/src/asm/configuration/http.py",
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/permissions.py",
    "backend/src/asm/configuration/repository.py",
    "backend/src/asm/configuration/service.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/conversations/escalation_http.py",
    "backend/src/asm/conversations/escalation_http_models.py",
    "backend/src/asm/conversations/escalations.py",
    "backend/src/asm/conversations/guards.py",
    "backend/src/asm/conversations/http_models.py",
    "backend/src/asm/conversations/material.py",
    "backend/src/asm/conversations/turns.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/intake/__init__.py",
    "backend/src/asm/intake/duration_cases.py",
    "backend/src/asm/intake/errors.py",
    "backend/src/asm/intake/http.py",
    "backend/src/asm/intake/models.py",
    "backend/src/asm/intake/projection.py",
    "backend/src/asm/intake/repository.py",
    "backend/src/asm/intake/service.py",
    "backend/src/asm/intake/templates.py",
    "backend/src/asm/intake/validation.py",
    "backend/src/asm/messaging/database.py",
    "backend/src/asm/messaging/errors.py",
    "backend/src/asm/messaging/http.py",
    "backend/src/asm/messaging/http_models.py",
    "backend/src/asm/messaging/http_service.py",
    "backend/src/asm/messaging/models.py",
    "backend/src/asm/messaging/results.py",
    "backend/src/asm/messaging/worker.py",
    "backend/src/asm/portfolio/errors.py",
    "backend/src/asm/portfolio/http.py",
    "backend/src/asm/portfolio/models.py",
    "backend/src/asm/portfolio/repository.py",
    "backend/src/asm/portfolio/service.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
    "docs/tasks/M5_HANDOFF.md",
    "frontend/e2e/intake-duration.spec.ts",
    "frontend/e2e/messaging.spec.ts",
    "frontend/e2e/portfolio-delivery.spec.ts",
    "frontend/e2e/portfolio.spec.ts",
    "frontend/src/App.test.tsx",
    "frontend/src/App.tsx",
    "frontend/src/ConfigurationPanel.test.tsx",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/DurationCasesPanel.test.tsx",
    "frontend/src/DurationCasesPanel.tsx",
    "frontend/src/EscalationsPanel.test.tsx",
    "frontend/src/EscalationsPanel.tsx",
    "frontend/src/IntakePanel.test.tsx",
    "frontend/src/IntakePanel.tsx",
    "frontend/src/MessagingPanel.test.tsx",
    "frontend/src/MessagingPanel.tsx",
    "frontend/src/PortfolioPanel.test.tsx",
    "frontend/src/PortfolioPanel.tsx",
    "frontend/src/configuration-api.test.ts",
    "frontend/src/configuration-api.ts",
    "frontend/src/configuration-fixtures.test-helper.ts",
    "frontend/src/escalation-api.test.ts",
    "frontend/src/escalation-api.ts",
    "frontend/src/escalation-fixtures.test-helper.ts",
    "frontend/src/intake-api.test.ts",
    "frontend/src/intake-api.ts",
    "frontend/src/intake-fixtures.test-helper.ts",
    "frontend/src/messaging-api.test.ts",
    "frontend/src/messaging-api.ts",
    "frontend/src/messaging-fixtures.test-helper.ts",
    "frontend/src/portfolio-api.test.ts",
    "frontend/src/portfolio-api.ts",
    "frontend/src/portfolio-fixtures.test-helper.ts",
    "frontend/src/style.css",
    "migrations/versions/0023_intake_duration.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/m5_intake_fixture.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/fixtures/businesses.v1.json",
    "tests/generic_pg_schema.py",
    "tests/m5_configuration_fixtures.py",
    "tests/m5_intake_fixtures.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_delivery_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_foundation.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations.py",
    "tests/test_m3_2_escalations_api_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m3_2_escalations_postgres.py",
    "tests/test_m4_agent.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_gateway.py",
    "tests/test_m4_gateway_failures.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_database.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration.py",
    "tests/test_m5_configuration_api_postgres.py",
    "tests/test_m5_configuration_migrations.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_duration_cases.py",
    "tests/test_m5_duration_cases_postgres.py",
    "tests/test_m5_intake.py",
    "tests/test_m5_intake_api_postgres.py",
    "tests/test_m5_intake_migrations.py",
    "tests/test_m5_intake_postgres.py",
    "tests/test_m5_intake_runtime.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_auth_boundary.py",
    "tests/test_m5_portfolio_context.py",
    "tests/test_m5_portfolio_delivery.py",
    "tests/test_m5_portfolio_delivery_migrations.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_m5_portfolio_migrations.py",
    "tests/test_m5_portfolio_runtime.py",
    "tests/test_m5_portfolio_runtime_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_migration.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}

# C0's prepared M5.3B branch and the complete write set from its assignment.
M5_V7_FIX_BASE = "c0641147fb9bf703afb69ecd6a7ce6bb6e7c5cba"
M5_V7_FIX_TREE = "11c987fb12e4f88d27da3737911c468d520269b8"
M5_V7_FIX_ASSIGNMENT = "ba80e2500e56f45059c89eda0127362ffbfe1464"
M5_V7_FIX_ASSIGNMENT_TREE = "930c174f98015a1a706e033a8ea7b416b72acaf1"
M5_V7_FIX_BRANCH = "c1/m5-3b-v7-fixes-r1"
M5_V7_FIX_DOCS = M5_INTAKE_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}
M5_V7_FIX_PATHS = M5_V7_FIX_DOCS | {
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/context.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/intake.py",
    "backend/src/asm/ai/portfolio.py",
    "backend/src/asm/ai/portfolio_delivery.py",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/intake/models.py",
    "backend/src/asm/intake/projection.py",
    "backend/src/asm/intake/repository.py",
    "backend/src/asm/intake/service.py",
    "backend/src/asm/intake/templates.py",
    "backend/src/asm/intake/validation.py",
    "backend/src/asm/telegram/provisioning.py",
    "frontend/e2e/configuration.spec.ts",
    "frontend/e2e/intake-duration.spec.ts",
    "migrations/versions/0024_intake_v7_repair.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/m5_intake_fixture.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_intake_fixtures.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_delivery_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_foundation.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_intake.py",
    "tests/test_m5_intake_api_postgres.py",
    "tests/test_m5_intake_migrations.py",
    "tests/test_m5_intake_postgres.py",
    "tests/test_m5_intake_runtime.py",
    "tests/test_m5_intake_v7_integration_postgres.py",
    "tests/test_m5_intake_v7_repair_migrations.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_delivery.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}

BASE = "6851b8f1c12b50cf0051353f29a41cf89c94a280"
BASE_TREE = "ffed6f5c7560d080baa672d50850c56eba4060ba"
BRANCH = "c3/m4-precommit-rights-r1"
TARGETED_BRANCH = "c3/m4-3-runtime-targeted-run-r10"
# C0-approved planning PR45; no M5 application or migration changes are admitted.
M5_PLAN_BASE = "c9d42878ebfaf6def59d24cf7f95b1f74646eb83"
M5_PLAN_TREE = "19c7a2fe16ab40c88b71980b44d16e6582d2aa92"
M5_PLAN_BRANCH = "c0/m5-pilot-plan-20261112"
M5_PLAN_PATHS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/tasks/M4_HANDOFF.md",
    "docs/tasks/M5_HANDOFF.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
    "docs/runbooks/M4_RUNTIME_PILOT.md",
    "scripts/m4_runtime_db.py",
    "tests/test_m4_runtime_db_runner.py",
}
# PR55 carries the M5 closure and planning documents on the accepted 0024 tree.
M6_PLAN_BASE = "aee17b90ca2283688904da0d07992d9504f4dc33"
M6_PLAN_TREE = "cf2710c69fdd3823ed0a8b12b89d139b509ea13f"
M6_PLAN_INITIAL = "65471bc23ec4ceb69fa603237d0b2a4b51dc271c"
M6_PLAN_BRANCH = "c0/m6-pilot-plan-20261119"
M6_PLAN_REVIEW_PATHS = {
    "docs/TASK_REGISTER.md",
    "docs/tasks/M6_HANDOFF.md",
    "docs/decisions/IMPL-006-m6-pilot-agreement.md",
    "scripts/m4_runtime_db.py",
    "tests/test_m4_runtime_db_runner.py",
}
M6_PLAN_PATHS = M6_PLAN_REVIEW_PATHS | {
    "AGENTS.md",
    "README.md",
    "docs/tasks/M5_HANDOFF.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M6_REQUEST_BASE = "67129e43a5947f6eadea88b268b603fec5f22949"
M6_REQUEST_TREE = "2c235f6551524450a27bb7cd01959228ec06ac3c"
M6_REQUEST_ASSIGNMENT = "5c5c1b07ba34d37d8ef1486fbbba18efd93fad77"
M6_REQUEST_ASSIGNMENT_TREE = "097ae6fb66d4d95f5348cac280a68d5ab6fd97a9"
M6_REQUEST_BRANCH = "c1/m6-1a-request-draft"
M6_REQUEST_DOCS = {"docs/TASK_REGISTER.md", "docs/tasks/M6_HANDOFF.md"}
M6_REQUEST_MIGRATION = "migrations/versions/0025_service_requests.py"
M6_REQUEST_IMPLEMENTATION_PATHS = {
    "backend/src/asm/foundation.py",
    "backend/src/asm/service_requests/__init__.py",
    "backend/src/asm/service_requests/errors.py",
    "backend/src/asm/service_requests/http.py",
    "backend/src/asm/service_requests/models.py",
    "backend/src/asm/service_requests/repository.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "frontend/e2e/intake-duration.spec.ts",
    "frontend/e2e/service-requests.spec.ts",
    "frontend/src/IntakePanel.test.tsx",
    "frontend/src/IntakePanel.tsx",
    "frontend/src/intake-api.test.ts",
    "frontend/src/intake-api.ts",
    "frontend/src/intake-fixtures.test-helper.ts",
    M6_REQUEST_MIGRATION,
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/m5_intake_fixture.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/m6_service_requests_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_foundation.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_intake_migrations.py",
    "tests/test_m5_intake_v7_repair_migrations.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_m6_service_requests_api_postgres.py",
    "tests/test_m6_service_requests_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}
M6_PRICING_BASE = "82044525485266dfba645c0ed50b681373a8643f"
M6_PRICING_TREE = "c1f4f5f793eef2ba0a3b93b60735be38f3689412"
M6_PRICING_ASSIGNMENT = "04d9d9bfee1b59a05f7fd21ee5d25b79f9cbe79a"
M6_PRICING_ASSIGNMENT_TREE = "ab296c898e7f517b0bced825a181cdab2d8809e1"
M6_PRICING_BRANCH = "c1/m6-2-pricing"
M6_PRICING_DOCS = M6_REQUEST_DOCS
M6_PRICING_MIGRATION = "migrations/versions/0027_price_calculations.py"
M6_PRICING_IMPLEMENTATION_PATHS = {
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/service_requests/http.py",
    "backend/src/asm/service_requests/pricing.py",
    "backend/src/asm/service_requests/repository.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "frontend/e2e/intake-duration.spec.ts",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/IntakePanel.tsx",
    "frontend/src/configuration-api.ts",
    "frontend/src/intake-api.ts",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/m5_intake_fixture.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_foundation.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_intake_migrations.py",
    "tests/test_m5_intake_postgres.py",
    "tests/test_m5_intake_v7_repair_migrations.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_m6_pricing_postgres.py",
    "tests/test_m6_service_assessments_postgres.py",
    "tests/test_m6_service_requests_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
    M6_PRICING_MIGRATION,
}
M6_ASSESSMENT_BASE = "54350ddb3a8fc00076f7e065acb19c733e4f29a8"
M6_ASSESSMENT_TREE = "3b993281f8864022ddba461beb94285ee145dda1"
M6_ASSESSMENT_ASSIGNMENT = "add308854ddde3f5dd648dfd32216d4b7a0f9e8f"
M6_ASSESSMENT_ASSIGNMENT_TREE = "5c3cabc468129ac9549688390fc84e81eb39c457"
M6_ASSESSMENT_BRANCH = "c1/m6-1b-assessment-duration"
M6_ASSESSMENT_DOCS = M6_REQUEST_DOCS
M6_ASSESSMENT_MIGRATION = "migrations/versions/0026_service_assessments.py"
M6_ASSESSMENT_IMPLEMENTATION_PATHS = {
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/service_requests/assessment.py",
    "backend/src/asm/service_requests/http.py",
    "backend/src/asm/service_requests/models.py",
    "backend/src/asm/service_requests/repository.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "frontend/e2e/intake-duration.spec.ts",
    "frontend/src/ConfigurationPanel.test.tsx",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/IntakePanel.test.tsx",
    "frontend/src/IntakePanel.tsx",
    "frontend/src/configuration-api.test.ts",
    "frontend/src/configuration-api.ts",
    "frontend/src/intake-api.test.ts",
    "frontend/src/intake-api.ts",
    "frontend/src/intake-fixtures.test-helper.ts",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/m5_intake_fixture.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_foundation.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_intake_migrations.py",
    "tests/test_m5_intake_v7_repair_migrations.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_m6_service_assessment.py",
    "tests/test_m6_service_assessments_api_postgres.py",
    "tests/test_m6_service_assessments_postgres.py",
    "tests/test_m6_service_requests_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
    M6_ASSESSMENT_MIGRATION,
}

# C0's bounded M5.1A implementation assignment; not a general M5 allowance.
M5_CONFIGURATION_BASE = "49d3e25968507ac41037f369fce5bd7080475a8f"
M5_CONFIGURATION_TREE = "699bd90777771c5d22d37029336c3e0f8909fb5c"
M5_CONFIGURATION_BRANCH = "c1/m5-1a-configuration-r1"
M5_CONFIGURATION_PATHS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
    "docs/tasks/M5_HANDOFF.md",
    "backend/src/asm/configuration/__init__.py",
    "backend/src/asm/configuration/errors.py",
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/configuration/permissions.py",
    "backend/src/asm/configuration/repository.py",
    "backend/src/asm/configuration/service.py",
    "backend/src/asm/configuration/http.py",
    "migrations/versions/0018_business_configuration.py",
    "tests/test_m5_configuration.py",
    "tests/test_m5_configuration_migrations.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_configuration_api_postgres.py",
    "tests/m5_configuration_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_postgres.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "backend/src/asm/telegram/provisioning.py",
    "scripts/native_context_db_catalog.py",
    "scripts/m4_runtime_db.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/test_foundation.py",
    "tests/generic_pg_schema.py",
    "tests/test_tenancy_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_reply_rights_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
}
# C0's single bounded M5.1B task, preserving its immutable docs assignment.
M5_KNOWLEDGE_BASE = "6c27be8487f3f8792cf01ed2a0fcdde130ea7a52"
M5_KNOWLEDGE_TREE = "1aa2959f1ba28438304ef758947ba241f6d0b729"
M5_KNOWLEDGE_ASSIGNMENT = "3b2a28a192753103017dab5452288cde61226d95"
M5_KNOWLEDGE_ASSIGNMENT_TREE = "0d93ec5242def3e31b6a650b1c0b24d2766cf343"
M5_KNOWLEDGE_BRANCH = "c4/m5-1b-published-knowledge-r1"
M5_KNOWLEDGE_PATHS = {
    "AGENTS.md",
    "README.md",
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/context.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/fake.py",
    "backend/src/asm/ai/gateway.py",
    "backend/src/asm/ai/knowledge.py",
    "backend/src/asm/ai/prompts/conversation_v3.txt",
    "backend/src/asm/ai/provider_runtime.py",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/ai/runtime_settings.py",
    "backend/src/asm/ai/schemas/conversation_result_v2.json",
    "backend/src/asm/ai/settings.py",
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/repository.py",
    "backend/src/asm/configuration/service.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/messaging/database.py",
    "backend/src/asm/messaging/errors.py",
    "backend/src/asm/messaging/results.py",
    "backend/src/asm/messaging/worker.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
    "docs/tasks/M5_HANDOFF.md",
    "frontend/e2e/configuration.spec.ts",
    "frontend/e2e/messaging.spec.ts",
    "frontend/src/App.test.tsx",
    "frontend/src/App.tsx",
    "frontend/src/ConfigurationPanel.test.tsx",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/configuration-api.test.ts",
    "frontend/src/configuration-api.ts",
    "frontend/src/configuration-fixtures.test-helper.ts",
    "frontend/src/style.css",
    "migrations/versions/0019_published_knowledge.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m2_4_browser_worker.py",
    "scripts/m4_runtime_db.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_browser.sh",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_configuration_fixtures.py",
    "tests/m5_knowledge_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_browser_compose.py",
    "tests/test_foundation.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_agent.py",
    "tests/test_m4_context.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_gateway.py",
    "tests/test_m4_polza_runtime.py",
    "tests/test_m4_polza_runtime_migrations.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_reply_rights_postgres.py",
    "tests/test_m4_runtime_database.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_runtime_postgres.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration.py",
    "tests/test_m5_configuration_api_postgres.py",
    "tests/test_m5_configuration_migrations.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_knowledge.py",
    "tests/test_m5_knowledge_migrations.py",
    "tests/test_m5_knowledge_postgres.py",
    "tests/test_m5_knowledge_runtime.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}
# C0's M5.2A assignment is immutable; this admits only the standalone probe.
M5_CAPABILITY_BASE = "6942150e9a4ab96222f49702b2e9977178b04e74"
M5_CAPABILITY_TREE = "12e4481c8a54d219e5bae7acb94b5484cf0b166c"
M5_CAPABILITY_ASSIGNMENT = "64e80b214b3404728de73030acab4cd1fdc28a4e"
M5_CAPABILITY_ASSIGNMENT_TREE = "e1ab83979b090a1faa23ef4fd50d10be61a0e962"
# C0 separately approved this docs revision; the original assignment stays pinned.
M5_CAPABILITY_C0_DOCS_REVISION = "40641f310a42cc35b4ea01e0817ba6374fc92400"
M5_CAPABILITY_C0_DOCS_TREE = "e695db04d5dd17d3f262694d8eb997ee4ff0dbce"
M5_CAPABILITY_BRANCH = "c4/m5-2a-capability-probe-r1"
M5_CAPABILITY_C0_DOCS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M5_CAPABILITY_PATHS = M5_CAPABILITY_C0_DOCS | {
    "backend/src/asm/ai/capability_probe.py",
    "backend/src/asm/ai/polza.py",
    "tests/test_m5_capability_probe.py",
    "tests/fixtures/m5_capability_cases.json",
    "tests/test_m4_polza.py",
    "scripts/m4_runtime_db.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_telegram_egress_migration.py",
    "docs/tasks/M5_HANDOFF.md",
}
# C0's bounded M5.2B assignment; retain the older admission routes verbatim.
M5_SEARCH_BASE = "8eeeede1b4a05537b0afb8c29992e8b681eaeb65"
M5_SEARCH_TREE = "df31d522ff862a0af58f1876fd8f16ddcda7bdc1"
M5_SEARCH_ASSIGNMENT = "4ce066b171090a8f0716623cc2cd8a6a79fa6139"
M5_SEARCH_ASSIGNMENT_TREE = "b8bd004fece6faf3f758a932f8855fcc99e51e47"
M5_SEARCH_BRANCH = "c4/m5-2b-knowledge-search-r1"
M5_SEARCH_C0_DOCS = M5_CAPABILITY_C0_DOCS
M5_SEARCH_PATHS = M5_SEARCH_C0_DOCS | {
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/context.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/fake.py",
    "backend/src/asm/ai/gateway.py",
    "backend/src/asm/ai/knowledge.py",
    "backend/src/asm/ai/polza.py",
    "backend/src/asm/ai/prompts/conversation_v4.txt",
    "backend/src/asm/ai/provider_runtime.py",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/ai/runtime_settings.py",
    "backend/src/asm/ai/schemas/conversation_result_v2.json",
    "backend/src/asm/ai/settings.py",
    # C0 publication R2: closed linked-build refusal only.
    "backend/src/asm/configuration/errors.py",
    "backend/src/asm/configuration/http.py",
    "backend/src/asm/configuration/models.py",
    "backend/src/asm/configuration/repository.py",
    "backend/src/asm/configuration/service.py",
    "backend/src/asm/configuration/validation.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/knowledge/__init__.py",
    "backend/src/asm/knowledge/embeddings.py",
    "backend/src/asm/knowledge/errors.py",
    "backend/src/asm/knowledge/http.py",
    "backend/src/asm/knowledge/models.py",
    "backend/src/asm/knowledge/permissions.py",
    "backend/src/asm/knowledge/repository.py",
    "backend/src/asm/knowledge/service.py",
    "backend/src/asm/knowledge/validation.py",
    "backend/src/asm/messaging/database.py",
    "backend/src/asm/messaging/errors.py",
    "backend/src/asm/messaging/results.py",
    "backend/src/asm/messaging/worker.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "docs/tasks/M5_HANDOFF.md",
    "frontend/e2e/configuration.spec.ts",
    "frontend/src/App.test.tsx",
    "frontend/src/App.tsx",
    "frontend/src/ConfigurationPanel.test.tsx",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/configuration-api.test.ts",
    "frontend/src/configuration-api.ts",
    "frontend/src/configuration-fixtures.test-helper.ts",
    "frontend/src/style.css",
    "migrations/versions/0020_knowledge_search.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m2_4_browser_worker.py",
    "scripts/m4_runtime_db.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_configuration_fixtures.py",
    "tests/m5_knowledge_fixtures.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_foundation.py",
    # Owner-approved 2026-11-15: current-schema TRUNCATE compatibility only.
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_agent.py",
    "tests/test_m4_context.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_gateway.py",
    "tests/test_m4_polza_runtime.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_reply_rights_postgres.py",
    "tests/test_m4_runtime_database.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_runtime_postgres.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration.py",
    "tests/test_m5_configuration_api_postgres.py",
    "tests/test_m5_configuration_migrations.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_knowledge.py",
    "tests/test_m5_knowledge_migrations.py",
    "tests/test_m5_knowledge_postgres.py",
    "tests/test_m5_knowledge_runtime.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_knowledge_search.py",
    "tests/test_m5_knowledge_search_api_postgres.py",
    "tests/test_m5_knowledge_search_embeddings.py",
    "tests/test_m5_knowledge_search_migrations.py",
    "tests/test_m5_knowledge_search_postgres.py",
    "tests/test_m5_knowledge_search_runtime.py",
    "tests/test_m5_knowledge_search_runtime_postgres.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}

# C0's single M5.2C assignment and approved upload continuation. No later M5 scope.
M5_PORTFOLIO_BASE = "70804866f6838f77c12bd281febae47887559d75"
M5_PORTFOLIO_TREE = "a6ee68b5a6b0cd2091b4cecc89614bada4db2585"
M5_PORTFOLIO_ASSIGNMENT = "031af2b091d40800c103d182d135f0677e4fca53"
M5_PORTFOLIO_ASSIGNMENT_TREE = "e439d994f60c30e0fc1a56326a79eb26bb1eb0b6"
M5_PORTFOLIO_CONTRACT = "9bd32fbd2bb7bb27a0dca84334bd3e2d0039a567"
M5_PORTFOLIO_CONTRACT_TREE = "c9de945f45669183094ba48489c93ecfa837e3f4"
M5_PORTFOLIO_CONTINUATION = "a34834e004320de7257e7c9f98dcb4ac178b6c66"
M5_PORTFOLIO_CONTINUATION_TREE = "ec72c51acece599264e8a9048047e4d4f661eaa6"
M5_PORTFOLIO_CHECKPOINT = "93174249527c055f3a975ba097a8646b2d14f450"
M5_PORTFOLIO_CHECKPOINT_TREE = "bad38d145fcf368f5b98c9f609e872722d418258"
M5_PORTFOLIO_FINISH_ASSIGNMENT = "114a027be3417998360bb939690b55f5815bdaf1"
M5_PORTFOLIO_FINISH_ASSIGNMENT_TREE = "2107bd20f2929fd931befb9d38850a3d6a0dfbab"
M5_PORTFOLIO_REVIEW_BASE = "da3007ae464d505f2d7c98b57f0f88836709d87d"
M5_PORTFOLIO_REVIEW_BASE_TREE = "cc433bed24cab28e641ddb72c2f09431bcf32f26"
M5_PORTFOLIO_CI_FIX_ASSIGNMENT = "cecb92c5edd073f9b9d924c01d391d07f5373436"
M5_PORTFOLIO_CI_FIX_ASSIGNMENT_TREE = "8f4668dacb0e39e281f79341a9a52b1e197069ad"
M5_PORTFOLIO_UNIT_REVIEW_BASE = "4ddf6b0650480cf0ac935bb5b141ce5a399d5311"
M5_PORTFOLIO_UNIT_REVIEW_BASE_TREE = "b039985cf19f2ef8c5b49664febd648cdeba7dbf"
M5_PORTFOLIO_UNIT_FIX_ASSIGNMENT = "f7ef6215ef7121984aa7b8fc4293b7496b85ed3b"
M5_PORTFOLIO_UNIT_FIX_ASSIGNMENT_TREE = "8a4c9e885f4c70193c9269bbc2d8305bd594d2e8"
M5_PORTFOLIO_CORE_REVIEW_BASE = "30127f143349645fa1c75d00cf34a4bd3b5e6d03"
M5_PORTFOLIO_CORE_REVIEW_BASE_TREE = "edf04c471782439a78391ce2c7065b99b1dff470"
M5_PORTFOLIO_CORE_FIX_ASSIGNMENT = "5ac931f65264b8cc7b4a77c1fff034814891ee66"
M5_PORTFOLIO_CORE_FIX_ASSIGNMENT_TREE = "d4dab0dc4db1f5ac86a0253b3986b4c2391bf63d"
M5_PORTFOLIO_BRANCH = "c4/m5-2c-vision-portfolio-r1"
M5_PORTFOLIO_C0_DOCS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M5_PORTFOLIO_PATHS = M5_PORTFOLIO_C0_DOCS | {
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/gateway.py",
    "backend/src/asm/ai/portfolio.py",
    "backend/src/asm/ai/prompts/conversation_v5.txt",
    "backend/src/asm/ai/prompts/vision_v1.txt",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/ai/runtime_settings.py",
    "backend/src/asm/ai/schemas/vision_result_v1.json",
    "backend/src/asm/ai/vision.py",
    "backend/src/asm/ai/vision_contracts.py",
    "backend/src/asm/auth/http.py",
    "backend/src/asm/configuration/errors.py",
    "backend/src/asm/files/models.py",
    "backend/src/asm/files/storage.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/knowledge/errors.py",
    "backend/src/asm/messaging/database.py",
    "backend/src/asm/messaging/worker.py",
    "backend/src/asm/portfolio/__init__.py",
    "backend/src/asm/portfolio/errors.py",
    "backend/src/asm/portfolio/http.py",
    "backend/src/asm/portfolio/models.py",
    "backend/src/asm/portfolio/repository.py",
    "backend/src/asm/portfolio/service.py",
    "backend/src/asm/portfolio/storage.py",
    "backend/src/asm/portfolio/validation.py",
    "backend/src/asm/telegram/provisioning.py",
    "backend/src/asm/tenancy/database.py",
    "contracts/openapi.json",
    "docs/tasks/M5_HANDOFF.md",
    "frontend/e2e/portfolio.spec.ts",
    "frontend/src/ConfigurationPanel.test.tsx",
    "frontend/src/ConfigurationPanel.tsx",
    "frontend/src/PortfolioPanel.test.tsx",
    "frontend/src/PortfolioPanel.tsx",
    "frontend/src/configuration-api.test.ts",
    "frontend/src/configuration-api.ts",
    "frontend/src/portfolio-api.test.ts",
    "frontend/src/portfolio-api.ts",
    "frontend/src/portfolio-fixtures.test-helper.ts",
    "frontend/src/style.css",
    "migrations/versions/0021_vision_portfolio.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "scripts/test_browser.sh",
    "tests/generic_pg_schema.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_auth_contract.py",
    "tests/test_foundation.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_portfolio_api_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m1_3_http_contract.py",
    "tests/test_m4_probe.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_telegram_egress_migration.py",
    "tests/test_telegram_egress.py",
    "tests/test_m5_portfolio_auth_boundary.py",
    "tests/test_m5_portfolio_context.py",
    "tests/test_m5_portfolio_migrations.py",
    "tests/test_m5_portfolio_postgres.py",
    "tests/test_m5_portfolio_runtime.py",
    "tests/test_m5_portfolio_runtime_postgres.py",
    "tests/test_m5_portfolio_storage_postgres.py",
    "tests/test_m5_portfolio_unit.py",
    "tests/test_m5_vision_pixels.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_tenancy_postgres.py",
    "backend/src/asm/files/config.py",
    "compose.browser.yaml",
    "scripts/check_browser_compose.py",
    "tests/test_browser_compose.py",
    "tests/test_m2_2_media.py",
    "frontend/src/App.tsx",
    "frontend/src/App.test.tsx",
    "frontend/src/MessagingPanel.tsx",
    "frontend/src/MessagingPanel.test.tsx",
}

M5_DELIVERY_BASE = "8d98593bc739666176968c5d76b9c01a2a711686"
M5_DELIVERY_TREE = "a14ed9b69e3529ac060bc015b9a24dcea515ef9b"
M5_DELIVERY_ASSIGNMENT = "63bb7147ec899eda1a538388aff18a01fc054e57"
M5_DELIVERY_ASSIGNMENT_TREE = "9de6138d28298cb2ece968fee472e5bca78994d5"
M5_DELIVERY_SCOPE_AMENDMENT = "37a92eece23452ac8d8715efa078db34d9cc10ff"
M5_DELIVERY_SCOPE_AMENDMENT_TREE = "130f9466bea8e0e15feb537b5b1e6f817cc883ef"
M5_DELIVERY_SCOPE_AMENDMENT_02 = "55a6f09cacecc85490e79d096b48a433932fd746"
M5_DELIVERY_SCOPE_AMENDMENT_02_TREE = "c00bb1334704be2e88031f38d926b01ab720d153"
M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT = "b4871ef1ad5a46ae7244397727f30629957470bb"
M5_DELIVERY_BRANCH = "c3/m5-2d-portfolio-photo-r1"
M5_DELIVERY_C0_DOCS = {
    "docs/TASK_REGISTER.md",
    "README.md",
    "AGENTS.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M5_DELIVERY_PATHS = {
    "AGENTS.md",
    "README.md",
    "backend/src/asm/ai/agent.py",
    "backend/src/asm/ai/context.py",
    "backend/src/asm/ai/contracts.py",
    "backend/src/asm/ai/database.py",
    "backend/src/asm/ai/fake.py",
    "backend/src/asm/ai/gateway.py",
    "backend/src/asm/ai/portfolio.py",
    "backend/src/asm/ai/portfolio_delivery.py",
    "backend/src/asm/ai/prompts/conversation_v6.txt",
    "backend/src/asm/ai/provider_runtime.py",
    "backend/src/asm/ai/runtime.py",
    "backend/src/asm/ai/runtime_contracts.py",
    "backend/src/asm/ai/runtime_settings.py",
    "backend/src/asm/ai/schemas/conversation_result_v2.json",
    "backend/src/asm/ai/settings.py",
    "backend/src/asm/billing/models.py",
    "backend/src/asm/conversations/guards.py",
    "backend/src/asm/conversations/http_models.py",
    "backend/src/asm/conversations/material.py",
    "backend/src/asm/conversations/turns.py",
    "backend/src/asm/files/models.py",
    "backend/src/asm/files/storage.py",
    "backend/src/asm/foundation.py",
    "backend/src/asm/messaging/adapter.py",
    "backend/src/asm/messaging/database.py",
    "backend/src/asm/messaging/errors.py",
    "backend/src/asm/messaging/http.py",
    "backend/src/asm/messaging/http_models.py",
    "backend/src/asm/messaging/http_service.py",
    "backend/src/asm/messaging/models.py",
    "backend/src/asm/messaging/policy.py",
    "backend/src/asm/messaging/results.py",
    "backend/src/asm/messaging/worker.py",
    "backend/src/asm/portfolio/delivery.py",
    "backend/src/asm/portfolio/errors.py",
    "backend/src/asm/portfolio/http.py",
    "backend/src/asm/portfolio/models.py",
    "backend/src/asm/portfolio/repository.py",
    "backend/src/asm/portfolio/service.py",
    "backend/src/asm/portfolio/storage.py",
    "backend/src/asm/telegram/adapter.py",
    "backend/src/asm/telegram/client.py",
    "backend/src/asm/telegram/database.py",
    "backend/src/asm/telegram/normalization.py",
    "backend/src/asm/telegram/provisioning.py",
    "contracts/openapi.json",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
    "docs/tasks/M5_HANDOFF.md",
    "frontend/e2e/messaging.spec.ts",
    "frontend/e2e/portfolio-delivery.spec.ts",
    "frontend/e2e/portfolio.spec.ts",
    "frontend/src/MessagingPanel.test.tsx",
    "frontend/src/MessagingPanel.tsx",
    "frontend/src/messaging-api.test.ts",
    "frontend/src/messaging-api.ts",
    "frontend/src/messaging-fixtures.test-helper.ts",
    "frontend/src/portfolio-api.test.ts",
    "frontend/src/portfolio-api.ts",
    "frontend/src/portfolio-fixtures.test-helper.ts",
    "frontend/src/style.css",
    "migrations/versions/0022_portfolio_delivery.py",
    "scripts/m2_4_browser_fixture.py",
    "scripts/m4_runtime_db.py",
    "scripts/native_context_db_catalog.py",
    "scripts/prepare_telegram_egress.py",
    "scripts/test_telegram_egress.sh",
    "tests/fixtures/businesses.v1.json",
    "tests/generic_pg_schema.py",
    "tests/m5_knowledge_search_fixtures.py",
    "tests/m5_portfolio_delivery_fixtures.py",
    "tests/m5_portfolio_fixtures.py",
    "tests/test_foundation.py",
    "tests/test_m2_3_db_postgres.py",
    "tests/test_m2_3_schema_postgres.py",
    "tests/test_m2_3_setup.py",
    "tests/test_m2_4_browser_fixture.py",
    "tests/test_m3_1_guards_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
    "tests/test_m3_2_escalations_migrations.py",
    "tests/test_m4_agent.py",
    "tests/test_m4_delivery.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_gateway.py",
    "tests/test_m4_gateway_failures.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights.py",
    "tests/test_m4_runtime_database.py",
    "tests/test_m4_runtime_db_runner.py",
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m5_configuration_postgres.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
    "tests/test_m5_portfolio_auth_boundary.py",
    "tests/test_m5_portfolio_context.py",
    "tests/test_m5_portfolio_delivery.py",
    "tests/test_m5_portfolio_delivery_migrations.py",
    "tests/test_m5_portfolio_delivery_postgres.py",
    "tests/test_m5_portfolio_delivery_transport.py",
    "tests/test_m5_portfolio_migrations.py",
    "tests/test_m5_portfolio_runtime.py",
    "tests/test_native_context_db_runner.py",
    "tests/test_postgres.py",
    "tests/test_m1_3_c0_acceptance.py",
    "tests/test_telegram_egress.py",
    "tests/test_telegram_egress_migration.py",
    "tests/test_telegram_egress_postgres.py",
    "tests/test_tenancy_postgres.py",
}

M5_FOUNDATION_BASE = "84ad8e4c954005801f115aa8e6c0c6f7edef40db"
M5_FOUNDATION_TREE = "bf8992e20260e56f8d84884fc65fa3febcafc053"
M5_FOUNDATION_ASSIGNMENT = "eb64476e9c399eaefe8d6eaf3889098c04e949dd"
M5_FOUNDATION_ASSIGNMENT_TREE = "d2c67aa516bcbbd353ad2eea9d15b0f7eb83b4cf"
M5_FOUNDATION_BRANCH = "c4/m5-2c-foundation-budget-r1"
M5_FOUNDATION_C0_DOCS = {
    "AGENTS.md",
    "README.md",
    "docs/TASK_REGISTER.md",
    "docs/decisions/IMPL-005-m5-pilot-knowledge.md",
}
M5_FOUNDATION_PATHS = M5_FOUNDATION_C0_DOCS | {
    "docs/tasks/M5_HANDOFF.md",
    ".github/workflows/ci.yml",
    "scripts/native_context_db_catalog.py",
    "tests/test_native_context_db_runner.py",
    "scripts/m4_runtime_db.py",
    "tests/test_m4_runtime_db_runner.py",
}

DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
MODULES = [
    "tests/test_m4_runtime_postgres.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_schema_postgres.py",
    "tests/test_m4_polza_runtime_postgres.py",
    "tests/test_m4_reply_rights_postgres.py",
    "tests/test_m5_knowledge_postgres.py",
    "tests/test_m5_knowledge_runtime_postgres.py",
]
CURRENT_NATIVE_MODULE = "tests/test_m3_1_native_context_runtime_postgres.py"
# Exactly the six R1 cases blocked by the current0015 schema prerequisite.
# In full CI they remain in the complete native lane, outside the M4 partition.
CURRENT_NATIVE_NODES = [
    CURRENT_NATIVE_MODULE + "::test_native_host_" + name
    for name in (
        "policy_enable_noop_pause_old_replay_and_current",
        "policy_wrong_cas_and_key_conflict_roll_back[stale]",
        "policy_wrong_cas_and_key_conflict_roll_back[key]",
        "policy_catalog_drift_refuses_without_new_authority",
        "committed_receipt_survives_current_failure_then_read_only_retry",
        "unreadable_result_rolls_back_real_capability",
    )
]
COMMAND_REPORT = "runtime-command"
SUMMARY_REPORT = "runtime-summary.json"
COLLECTED = []
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
CASE = None
CASES = []
EVENT_LIMIT = 8192
PROBE_CONSTRAINTS = {
    "messaging_jobs_telegram_probe_check",
    "messaging_jobs_telegram_probe_generation_check",
    "messaging_jobs_telegram_probe_version_check",
}


class Refusal(RuntimeError):
    """A known carrier predicate, safe to preserve without exception values."""


def require(condition, code):
    if not condition:
        raise Refusal(code)


def failure_details(error):
    return {
        "error_type": type(error).__name__[:80],
        "code": str(error)
        if isinstance(error, Refusal) and re.fullmatch(r"[A-Z0-9_]{1,80}", str(error))
        else "OPERATION_FAILED",
        "frames": [
            {
                "file": Path(frame.filename).name[:120],
                "function": frame.name[:120],
                "line": frame.lineno,
            }
            for frame in traceback.extract_tb(error.__traceback__, limit=-8)
        ],
    }


def case_failure_details(excinfo):
    """Keep only bounded locations and known SQL diagnostics, never exception values."""
    from asm.messaging.errors import MessagingError
    from sqlalchemy.exc import DBAPIError

    data = {"exception_type": excinfo.typename[:80]}
    error = excinfo.value
    if isinstance(error, MessagingError):
        data["error_code"] = error.code.value
    if isinstance(error, DBAPIError):
        sqlstate = getattr(error.orig, "sqlstate", None)
        if type(sqlstate) is str and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
            data["sqlstate"] = sqlstate
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if type(constraint) is str and constraint in PROBE_CONSTRAINTS:
            data["constraint_name"] = constraint
    frames = traceback.extract_tb(error.__traceback__)
    data["frames"] = [
        {"file": Path(f.filename).name[:120], "function": f.name[:120], "line": f.lineno}
        for f in frames[-12:]
    ]
    application = []
    root = Path(__file__).resolve().parents[1]
    for frame in frames:
        try:
            path = Path(frame.filename).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if (
            (path.startswith("backend/src/asm/") or path.startswith("tests/"))
            and path.endswith(".py")
            and len(path) <= 180
            and re.fullmatch(r"[A-Za-z0-9_<>]{1,120}", frame.name)
        ):
            location = {"file": path, "function": frame.name, "line": frame.lineno}
            if location not in application:
                application.append(location)
    data["application_frames"] = application[-8:]
    return data


def evidence_path():
    return Path(os.environ.get("ASM_M4_EVIDENCE", "/evidence"))


def delivery_scope_amendment():
    return {
        "sha": M5_DELIVERY_SCOPE_AMENDMENT,
        "tree": M5_DELIVERY_SCOPE_AMENDMENT_TREE,
        "parent": M5_DELIVERY_ASSIGNMENT,
    }


def delivery_scope_amendment_02():
    return {
        "sha": M5_DELIVERY_SCOPE_AMENDMENT_02,
        "tree": M5_DELIVERY_SCOPE_AMENDMENT_02_TREE,
        "parent": M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT,
    }


def source_tree_from_evidence(path=None):
    """Bind the DB-only fixture to this executor's checked source, without Git in the image."""

    path = path or evidence_path() / "source.json"

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "SOURCE_IDENTITY_DUPLICATE_KEY")
            value[key] = item
        return value

    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        require(len(raw) <= 65536, "SOURCE_IDENTITY_TOO_LARGE")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except OSError:
        raise RuntimeError("SOURCE_IDENTITY_MISSING") from None
    except (UnicodeDecodeError, ValueError):
        raise RuntimeError("SOURCE_IDENTITY_MALFORMED") from None
    keys = {
        "base",
        "base_tree",
        "source",
        "tree",
        "paths",
        "run_id",
        "attempt",
        "event",
        "branch",
        "pins",
        "uv_lock_sha256",
    }
    require(type(value) is dict, "SOURCE_IDENTITY_SHAPE")
    m6_pricing = value.get("branch") == M6_PRICING_BRANCH
    m6_assessment = value.get("branch") == M6_ASSESSMENT_BRANCH
    m6_request = value.get("branch") == M6_REQUEST_BRANCH
    m6_plan = value.get("branch") == M6_PLAN_BRANCH
    v7_fix = value.get("branch") == M5_V7_FIX_BRANCH
    intake = value.get("branch") == M5_INTAKE_BRANCH
    delivery = value.get("branch") == M5_DELIVERY_BRANCH
    if v7_fix:
        keys.update({"v7_fix_assignment", "v7_fix_candidate"})
    if m6_plan:
        keys.add("m6_plan_candidate")
    if m6_pricing:
        keys.update({"m6_pricing_assignment", "m6_pricing_candidate"})
    if m6_assessment:
        keys.update({"m6_assessment_assignment", "m6_assessment_candidate"})
    if m6_request:
        keys.update({"m6_request_assignment", "m6_request_candidate"})
    if intake:
        keys.add("intake_assignment")
        keys.add("intake_scope_amendment")
    if delivery:
        keys.add("scope_amendment")
        keys.add("scope_amendment_02")
    require(set(value) == keys, "SOURCE_IDENTITY_SHAPE")
    if m6_pricing or m6_assessment or m6_request:
        if m6_pricing:
            prefix, assignment = "m6_pricing", m6_pricing_assignment_proof()
        elif m6_assessment:
            prefix, assignment = "m6_assessment", m6_assessment_assignment_proof()
        else:
            prefix, assignment = "m6_request", m6_request_assignment_proof()
        require(
            value[prefix + "_assignment"] == assignment,
            f"SOURCE_IDENTITY_{prefix.upper()}_ASSIGNMENT",
        )
        candidate = value[prefix + "_candidate"]
        require(
            type(candidate) is dict
            and set(candidate) == {"sha", "tree", "merge_parents"}
            and type(candidate["sha"]) is str
            and re.fullmatch(r"[0-9a-f]{40}", candidate["sha"])
            and candidate["sha"] not in (assignment["parent"], assignment["sha"], value["source"])
            and candidate["tree"] == value["tree"]
            and candidate["merge_parents"] == [assignment["parent"], candidate["sha"]],
            f"SOURCE_IDENTITY_{prefix.upper()}_CANDIDATE",
        )
    if v7_fix:
        require(
            value["v7_fix_assignment"] == v7_fix_assignment_proof(),
            "SOURCE_IDENTITY_V7_FIX_ASSIGNMENT",
        )
    if m6_plan or v7_fix:
        candidate = value["m6_plan_candidate" if m6_plan else "v7_fix_candidate"]
        candidate_base = M6_PLAN_BASE if m6_plan else M5_V7_FIX_BASE
        initial = M6_PLAN_INITIAL if m6_plan else M5_V7_FIX_ASSIGNMENT
        require(
            type(candidate) is dict
            and set(candidate) == {"sha", "tree", "merge_parents"}
            and type(candidate["sha"]) is str
            and re.fullmatch(r"[0-9a-f]{40}", candidate["sha"])
            and candidate["sha"] not in (candidate_base, initial, value["source"])
            and candidate["tree"] == value["tree"]
            and candidate["merge_parents"] == [candidate_base, candidate["sha"]],
            "SOURCE_IDENTITY_M6_PLAN_CANDIDATE" if m6_plan else "SOURCE_IDENTITY_V7_FIX_CANDIDATE",
        )
    if intake:
        require(
            value["intake_assignment"] == intake_assignment_proof(),
            "SOURCE_IDENTITY_INTAKE_ASSIGNMENT",
        )
        require(
            type(value["intake_scope_amendment"]) is dict
            and value["intake_scope_amendment"] == intake_scope_amendment_proof(),
            "SOURCE_IDENTITY_INTAKE_SCOPE_AMENDMENT",
        )
    if delivery:
        require(
            type(value["scope_amendment"]) is dict
            and value["scope_amendment"] == delivery_scope_amendment(),
            "SOURCE_IDENTITY_SCOPE_AMENDMENT",
        )
        require(
            type(value["scope_amendment_02"]) is dict
            and value["scope_amendment_02"] == delivery_scope_amendment_02(),
            "SOURCE_IDENTITY_SCOPE_AMENDMENT_02",
        )
    foundation_budget = value["branch"] == M5_FOUNDATION_BRANCH
    planning = value["branch"] == M5_PLAN_BRANCH
    configuration = value["branch"] == M5_CONFIGURATION_BRANCH
    knowledge = value["branch"] == M5_KNOWLEDGE_BRANCH
    portfolio = value["branch"] == M5_PORTFOLIO_BRANCH
    search = value["branch"] == M5_SEARCH_BRANCH
    capability = value["branch"] == M5_CAPABILITY_BRANCH
    base, base_tree = (
        (M6_PRICING_BASE, M6_PRICING_TREE)
        if m6_pricing
        else (M6_ASSESSMENT_BASE, M6_ASSESSMENT_TREE)
        if m6_assessment
        else (M6_REQUEST_BASE, M6_REQUEST_TREE)
        if m6_request
        else (M6_PLAN_BASE, M6_PLAN_TREE)
        if m6_plan
        else (M5_V7_FIX_BASE, M5_V7_FIX_TREE)
        if v7_fix
        else (M5_INTAKE_BASE, M5_INTAKE_TREE)
        if intake
        else (M5_DELIVERY_BASE, M5_DELIVERY_TREE)
        if delivery
        else (M5_FOUNDATION_BASE, M5_FOUNDATION_TREE)
        if foundation_budget
        else (M5_PORTFOLIO_BASE, M5_PORTFOLIO_TREE)
        if portfolio
        else (M5_SEARCH_BASE, M5_SEARCH_TREE)
        if search
        else (M5_CAPABILITY_BASE, M5_CAPABILITY_TREE)
        if capability
        else (M5_KNOWLEDGE_BASE, M5_KNOWLEDGE_TREE)
        if knowledge
        else (M5_CONFIGURATION_BASE, M5_CONFIGURATION_TREE)
        if configuration
        else (M5_PLAN_BASE, M5_PLAN_TREE)
        if planning
        else (BASE, BASE_TREE)
    )
    expected = {
        name: os.environ.get("ASM_M4_" + name)
        for name in ("SOURCE_SHA", "SOURCE_TREE", "RUN_ID", "RUN_ATTEMPT")
    }
    require(
        all(
            type(expected[k]) is str and re.fullmatch(r"[0-9a-f]{40}", expected[k])
            for k in ("SOURCE_SHA", "SOURCE_TREE")
        )
        and type(expected["RUN_ID"]) is str
        and re.fullmatch(r"[1-9][0-9]{0,19}", expected["RUN_ID"])
        and expected["RUN_ATTEMPT"] == "1",
        "SOURCE_IDENTITY_ENVIRONMENT",
    )
    require(
        all(
            type(value[k]) is str and re.fullmatch(r"[0-9a-f]{40}", value[k])
            for k in ("base", "base_tree", "source", "tree")
        )
        and value["base"] == base
        and value["base_tree"] == base_tree
        and value["source"] == expected["SOURCE_SHA"]
        and value["source"] != base
        and value["tree"] == expected["SOURCE_TREE"]
        and (
            value["branch"] == BRANCH
            and value["event"] in {"pull_request", "push"}
            or value["branch"] == TARGETED_BRANCH
            and value["event"] == "push"
            or planning
            and value["event"] == "pull_request"
            or configuration
            and value["event"] in {"pull_request", "push"}
            or knowledge
            and value["event"] in {"pull_request", "push"}
            or capability
            and value["event"] in {"pull_request", "push"}
            or search
            and value["event"] in {"pull_request", "push"}
            or (intake or v7_fix or m6_plan or m6_request or m6_assessment or m6_pricing)
            and value["event"] in {"pull_request", "push"}
            or delivery
            and value["event"] in {"pull_request", "push"}
            or foundation_budget
            and value["event"] in {"pull_request", "push"}
            or portfolio
            and value["event"] in {"pull_request", "push"}
        )
        and type(value["attempt"]) is int
        and value["attempt"] == 1
        and value["run_id"] == expected["RUN_ID"],
        "SOURCE_IDENTITY_MISMATCH",
    )
    paths = value["paths"]
    require(
        type(paths) is list
        and bool(paths)
        and all(type(p) is str for p in paths)
        and paths == sorted(set(paths))
        and type(value["pins"]) is dict
        and value["pins"].get("DB_IMAGE") == DB_IMAGE
        and all(type(k) is str and type(v) is str for k, v in value["pins"].items())
        and type(value["uv_lock_sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["uv_lock_sha256"]),
        "SOURCE_IDENTITY_SHAPE",
    )
    if m6_pricing:
        require(
            M6_PRICING_DOCS | {M6_PRICING_MIGRATION}
            <= set(paths)
            <= M6_PRICING_DOCS | M6_PRICING_IMPLEMENTATION_PATHS,
            "SOURCE_IDENTITY_WRITE_SET",
        )
    elif m6_assessment:
        require(
            M6_ASSESSMENT_DOCS | {M6_ASSESSMENT_MIGRATION}
            <= set(paths)
            <= M6_ASSESSMENT_DOCS | M6_ASSESSMENT_IMPLEMENTATION_PATHS,
            "SOURCE_IDENTITY_WRITE_SET",
        )
    elif m6_request:
        require(
            M6_REQUEST_DOCS | {M6_REQUEST_MIGRATION}
            <= set(paths)
            <= M6_REQUEST_DOCS | M6_REQUEST_IMPLEMENTATION_PATHS,
            "SOURCE_IDENTITY_WRITE_SET",
        )
    elif m6_plan:
        require(set(paths) <= M6_PLAN_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif v7_fix:
        require(M5_V7_FIX_DOCS <= set(paths) <= M5_V7_FIX_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif intake:
        require(set(paths) <= M5_INTAKE_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif delivery:
        require(set(paths) <= M5_DELIVERY_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif foundation_budget:
        require(set(paths) <= M5_FOUNDATION_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif portfolio:
        require(set(paths) <= M5_PORTFOLIO_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif search:
        require(set(paths) <= M5_SEARCH_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif capability:
        require(set(paths) <= M5_CAPABILITY_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif planning:
        require(set(paths) <= M5_PLAN_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif configuration:
        require(set(paths) <= M5_CONFIGURATION_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    elif knowledge:
        require(set(paths) <= M5_KNOWLEDGE_PATHS, "SOURCE_IDENTITY_WRITE_SET")
    return value["tree"]


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def preparation(stage, **facts):
    """Record only bounded synthetic preparation identities, never claims or snapshots."""
    if CASE is None:
        return
    if len(CASE["events"]) >= EVENT_LIMIT:
        CASE["overflow"] += 1
        return
    if stage not in {
        "INGRESS",
        "RECONCILE",
        "RESUME",
        "AI_INGRESS",
        "PRE_SEAL",
        "POST_SEAL",
        "SOURCE_CLAIM",
        "ENQUEUE",
        "AI_CLAIM",
        "PREPARE",
        "PREPARED",
        "STALE_REVISION_REJECTED",
        "DOWNGRADE_READY",
        "SELECTION",
        "MODEL_ENTER",
        "TIMEOUT",
        "REPLAY",
        "SEND",
        "STALE_OBSERVATION",
        "SEND_ATTEMPT",
        "SEND_REPLAY",
        "OLD_CHECK_REJECTION",
    }:
        CASE["invalid_fields"] += 1
        return
    event = {"stage": stage}
    for name, value in facts.items():
        if (
            name
            in {
                "workspace_id",
                "connection_id",
                "conversation_id",
                "turn_id",
                "source_job_id",
                "job_id",
                "run_id",
            }
            and type(value) is UUID
        ):
            event[name] = str(value)
        elif (
            name in {"before_revision", "turn_revision"}
            and type(value) is int
            and 0 < value <= 9223372036854775807
        ):
            event[name] = value
        elif (
            name == "state"
            and type(value) is str
            and value in {"COLLECTING", "WAITING_MEDIA", "READY", "FAILED"}
        ):
            event[name] = value
        elif name == "selected_kind" and (
            value is None or type(value) is str and value in {"reply", "handoff", "no_reply"}
        ):
            event[name] = value
        elif (
            name in {"call_count", "reservation_count", "observe_count", "send_count"}
            and type(value) is int
            and 0 <= value <= 2
        ):
            event[name] = value
        elif (
            name
            in {
                "adapter_entered",
                "adapter_cancelled",
                "has_result",
                "has_outbox",
                "reserve_held",
                "completion_unknown_metering",
                "send_completed",
            }
            and type(value) is bool
        ):
            event[name] = value
        elif (
            name == "job_state"
            and type(value) is str
            and value in {"READY", "RUNNING", "SUCCEEDED", "DEAD"}
        ):
            event[name] = value
        elif name == "error_code" and (
            value is None
            or type(value) is str
            and value
            in {
                "DEPENDENCY_UNAVAILABLE",
                "UNKNOWN_EXTERNAL_RESULT",
                "NOT_ALLOWED",
                "STALE_CLAIM",
                "AI_STALE",
                "AI_BUDGET",
                "AI_INCOMPLETE",
                "TIMEOUT",
                "CANCELLED",
            }
        ):
            event[name] = value
        elif name == "constraint_name" and type(value) is str and value in PROBE_CONSTRAINTS:
            event[name] = value
        elif name == "sqlstate" and type(value) is str and value == "23514":
            event[name] = value
        else:
            CASE["invalid_fields"] += 1
            return
    CASE["events"].append(event)
    flush_cases()


if os.environ.get("ASM_M4_PG_PLUGIN") == "1":
    import pytest

    def pytest_collection_modifyitems(session, config, items):
        global COLLECTED
        COLLECTED = [item.nodeid for item in items]
        write(evidence_path() / "collected.json", COLLECTED)
        validate_collection(COLLECTED)
        if os.environ.get("ASM_M4_CURRENT_NATIVE") == "1":
            guard_current_native(items)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(item):
        global CASE
        CASE = {
            "nodeid": item.nodeid,
            "events": [],
            "overflow": 0,
            "invalid_fields": 0,
            "phases": [],
        }
        CASES.append(CASE)
        active_case("setup")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_call(item):
        active_case("call")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_teardown(item):
        active_case("teardown")

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(item, call):
        result = yield
        report = result.get_result()
        data = {
            "phase": report.when,
            "outcome": report.outcome,
            "duration_seconds": report.duration,
            "xfail": hasattr(report, "wasxfail"),
        }
        if call.excinfo is not None:
            data.update(case_failure_details(call.excinfo))
            # Preserve failure and stack locations, never exception values,
            # cookies, query parameters, fixture reprs, captured logs or DSNs.
            report.longrepr = json.dumps(data, sort_keys=True)
        report.sections = []
        report.user_properties = []
        CASE["phases"].append(data)
        flush_cases()
        if report.when == "teardown":
            write(
                evidence_path() / "active-case.json", {"nodeid": item.nodeid, "phase": "completed"}
            )

    def pytest_collectreport(report):
        if report.failed:
            report.longrepr = "M4_OBSERVATION_COLLECTION_FAILED"
        report.sections = []

    def pytest_sessionfinish(session, exitstatus):
        flush_cases()
        summary = summarize(CASES, COLLECTED, int(exitstatus))
        write(evidence_path() / SUMMARY_REPORT, summary)
        if summary["result"] != "PASS" and session.exitstatus == 0:
            session.exitstatus = 1


def validate_collection(actual):
    expected = json.loads((evidence_path() / "inventory.json").read_text())["nodeids"]
    require(
        bool(actual) and actual == expected and len(set(actual)) == len(actual),
        "SOURCE_COLLECTION_MISMATCH",
    )


def native_identity():
    """The native reset runs only in the namespace of our fresh owned server."""
    import psycopg
    from sqlalchemy.engine import make_url

    admin = make_url(os.environ["ASM_NATIVE_TEST_ADMIN_URL"])
    require(
        os.environ.get("ASM_NATIVE_TEST_ALLOW_RESET") == "1"
        and admin.host == "127.0.0.1"
        and admin.port == 5432
        and admin.database == "postgres"
        and admin.username == "asm_admin",
        "CURRENT_NATIVE_ADMIN_TARGET",
    )
    for key, user in (
        ("ASM_DATABASE_URL", "asm_runtime"),
        ("ASM_MIGRATION_DATABASE_URL", "asm_migrator"),
    ):
        url = make_url(os.environ[key])
        require(
            (url.host, url.port, url.database, url.username)
            == (admin.host, admin.port, "asm_test", user),
            "CURRENT_NATIVE_TARGET",
        )
    with psycopg.connect(admin.render_as_string(hide_password=False), connect_timeout=5) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        row = c.execute(
            "SELECT system_identifier::text,pg_postmaster_start_time()::text,current_setting('server_version_num'),session_user,current_database() FROM pg_control_system()"
        ).fetchone()
    require(row[2:] == ("180006", "asm_admin", "postgres"), "CURRENT_NATIVE_SERVER")
    return {"system_identifier": row[0], "postmaster_start": row[1], "server_version_num": row[2]}


def guard_current_native(items):
    from scripts import native_context_db_catalog as catalog

    require([item.nodeid for item in items] == CURRENT_NATIVE_NODES, "CURRENT_NATIVE_SELECTION")
    module = sys.modules["test_m3_1_native_context_postgres"]
    native = inspect.unwrap(module.native)
    original = module.reset_disposable
    original_identity = module.source_tree_identity
    require(
        Path(original.__code__.co_filename).resolve() == catalog.ROOT / catalog.MODULES[1]
        and native.__globals__ is vars(module)
        and inspect.isfunction(original_identity)
        and original_identity.__name__ == "source_tree_identity"
        and Path(original_identity.__code__.co_filename).resolve()
        == catalog.ROOT / catalog.MODULES[1]
        and original_identity.__globals__ is vars(module)
        and native.__globals__["source_tree_identity"] is original_identity
        and all(
            inspect.unwrap(item._fixtureinfo.name2fixturedefs["native"][-1].func) is native
            for item in items
        ),
        "CURRENT_NATIVE_RESET_IMPLEMENTATION",
    )
    baseline = json.loads((evidence_path() / "native-owner.json").read_text())
    proofs = []
    identities = []

    def checked_source_tree():
        tree, _ = catalog.require_source(catalog.ROOT, os.environ["ASM_M4_SOURCE_SHA"])
        require(tree == source_tree_from_evidence(), "CURRENT_NATIVE_SOURCE")
        return tree

    @functools.wraps(original_identity)
    def checked_identity():
        # The historical fixture writes a temporary Git index. This carrier has
        # a read-only checkout; prove all actual bytes/modes again at point of use.
        tree = checked_source_tree()
        identities.append({"identity": len(identities) + 1, "source_tree": tree})
        write(evidence_path() / "native-identity-proofs.json", identities)
        return tree

    @functools.wraps(original)
    def checked_reset():
        tree = checked_source_tree()
        actual = native_identity()
        require(actual == baseline, "CURRENT_NATIVE_SERVER_CHANGED")
        proofs.append({"reset": len(proofs) + 1, "source_tree": tree, **actual})
        write(evidence_path() / "before-reset-proofs.json", proofs)
        return original()

    module.reset_disposable = checked_reset
    module.source_tree_identity = checked_identity
    write(
        evidence_path() / "fixture-guards.json",
        {
            "nodeids": CURRENT_NATIVE_NODES,
            "reset": catalog.MODULES[1] + "::reset_disposable",
            "source_and_server_before_each_reset": True,
            "identity": catalog.MODULES[1] + "::source_tree_identity",
            "full_source_check_at_identity_use": True,
        },
    )


def summarize(cases, expected, exitstatus):
    complete = (
        bool(expected)
        and [case["nodeid"] for case in cases] == expected
        and all(
            [p["phase"] for p in case["phases"]] == ["setup", "call", "teardown"]
            and all(p["outcome"] in {"passed", "failed"} and not p["xfail"] for p in case["phases"])
            and not case["overflow"]
            and not case["invalid_fields"]
            for case in cases
        )
    )
    passed = (
        complete
        and exitstatus == 0
        and all(p["outcome"] == "passed" for case in cases for p in case["phases"])
    )
    completed = [c["nodeid"] for c in cases if any(p["phase"] == "teardown" for p in c["phases"])]
    started = [c["nodeid"] for c in cases]
    called = [c["nodeid"] for c in cases if any(p["phase"] == "call" for p in c["phases"])]
    return {
        "completed": completed,
        "active": [n for n in started if n not in completed],
        "missing": [n for n in expected if n not in completed],
        "not_reached": [n for n in expected if n not in started],
        "call_reached": called,
        "missing_call_phases": [n for n in expected if n not in called],
        "pytest_exit": exitstatus,
        "cases": len(cases),
        "expected": len(expected),
        "complete": complete,
        "result": "PASS" if passed else "FAIL",
        "scope": "retained0014 and current0015 synthetic application; no live/paid transport",
        "paid_http": 0,
    }


def active_case(phase):
    write(
        evidence_path() / "active-case.json",
        {"nodeid": CASE["nodeid"], "phase": phase, "utc": time.time()},
    )
    flush_cases()


def flush_cases():
    write(
        evidence_path() / "cases.json",
        [{k: v for k, v in case.items() if k not in {"pending", "engine"}} for case in CASES],
    )


def versions():
    import psycopg
    import sqlalchemy
    from sqlalchemy.engine import make_url

    value = {
        "python": platform.python_version(),
        "psycopg": psycopg.__version__,
        "sqlalchemy": sqlalchemy.__version__,
        "libpq": psycopg.pq.version(),
    }
    for kind, env in (("migrator", "ASM_MIGRATION_DATABASE_URL"), ("runtime", "ASM_DATABASE_URL")):
        url = make_url(os.environ[env])
        require(url.database == "asm_test", "VERSION_PROBE_TARGET")
        with psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False)
        ) as c:
            identity = c.execute(
                "SELECT session_user,current_user,current_database(),current_setting('server_version'),current_setting('server_version_num')"
            ).fetchone()
            require(identity[:3] == ("asm_" + kind, "asm_" + kind, "asm_test"), "VERSION_IDENTITY")
            require(int(identity[4]) // 10000 == 18, "PG_MAJOR_MISMATCH")
            value[kind] = dict(
                zip(
                    (
                        "session_user",
                        "current_user",
                        "database",
                        "server_version",
                        "server_version_num",
                    ),
                    identity,
                    strict=True,
                )
            )
            if kind == "migrator":
                value["schema"] = c.execute(
                    "SELECT version_num FROM platform.alembic_version"
                ).fetchall()
                require(value["schema"] == [("0014",)], "SCHEMA_MISMATCH")
                value["roles"] = c.execute(
                    "SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolcanlogin FROM pg_roles WHERE rolname IN ('asm_runtime','asm_migrator') ORDER BY rolname"
                ).fetchall()
                require(
                    [row[0] for row in value["roles"]] == ["asm_migrator", "asm_runtime"]
                    and all(
                        row[1:5] == (False, False, False, False) and row[5]
                        for row in value["roles"]
                    ),
                    "ROLE_MISMATCH",
                )
                value["extensions"] = c.execute(
                    "SELECT extname,extversion FROM pg_extension WHERE extname IN ('vector','btree_gist') ORDER BY extname"
                ).fetchall()
                value["ai_tables"] = c.execute(
                    "SELECT relname,relowner::regrole::text,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',c.oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='platform' AND relname IN ('ai_runs','ai_provider_calls') ORDER BY relname"
                ).fetchall()
                require(
                    len(value["ai_tables"]) == 2
                    and all(
                        row[1:] == ("asm_migrator", True, True, False) for row in value["ai_tables"]
                    ),
                    "AI_DDL_SECURITY",
                )
    write(evidence_path() / "database-versions.json", value)


def root_path():
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(re.fullmatch(r"[1-9][0-9]{0,19}", run) and attempt == "1", "RUN_IDENTITY")
    return Path(os.environ["RUNNER_TEMP"]) / ("m4-runtime-" + run + "-" + attempt)


def v7_fix_assignment_proof():
    return {
        "sha": M5_V7_FIX_ASSIGNMENT,
        "tree": M5_V7_FIX_ASSIGNMENT_TREE,
        "parent": M5_V7_FIX_BASE,
        "paths": sorted(M5_V7_FIX_DOCS),
    }


def commit_parents(revision):
    headers = capture(["git", "cat-file", "commit", revision]).split("\n\n", 1)[0]
    return [
        line.removeprefix("parent ") for line in headers.splitlines() if line.startswith("parent ")
    ]


def v7_fix_event(event):
    if event.get("head_ref") == M5_V7_FIX_BRANCH:
        return True
    if event["ref"] != "refs/heads/main" or event["head"] == M5_V7_FIX_BASE:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_V7_FIX_BASE, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "V7_FIX_SOURCE_ANCESTRY")
    return result.returncode == 0


def merge_candidate(event, base, branch, initial, prefix):
    require(
        event["event"] == "pull_request"
        and event.get("head_ref") == branch
        and event.get("base_sha") == base
        or event["event"] == "push"
        and event["ref"] == "refs/heads/main",
        prefix + "_EVENT",
    )
    parents = commit_parents("HEAD")
    require(len(parents) == 2 and parents[0] == base, prefix + "_MERGE_PARENTS")
    candidate = parents[1]
    if event["event"] == "pull_request":
        require(candidate == event["head_sha"], prefix + "_MERGE_CANDIDATE")
    require(
        candidate != initial and capture(["git", "merge-base", initial, candidate]) == initial,
        prefix + "_ASSIGNMENT_ANCESTRY",
    )
    candidate_tree = capture(["git", "rev-parse", candidate + "^{tree}"])
    require(candidate_tree == event["tree"], prefix + "_MERGE_TREE")
    return {"sha": candidate, "tree": candidate_tree, "merge_parents": parents}


def v7_fix_candidate(event):
    return merge_candidate(event, M5_V7_FIX_BASE, M5_V7_FIX_BRANCH, M5_V7_FIX_ASSIGNMENT, "V7_FIX")


def m6_plan_event(event):
    return event.get("head_ref") == M6_PLAN_BRANCH or (
        event.get("event") == "push"
        and event["ref"] == "refs/heads/main"
        and commit_parents("HEAD")[:1] == [M6_PLAN_BASE]
    )


def m6_request_event(event):
    return event.get("head_ref") == M6_REQUEST_BRANCH or (
        event.get("event") == "push"
        and event["ref"] == "refs/heads/main"
        and commit_parents("HEAD")[:1] == [M6_REQUEST_BASE]
    )


def m6_request_assignment_proof():
    return {
        "sha": M6_REQUEST_ASSIGNMENT,
        "tree": M6_REQUEST_ASSIGNMENT_TREE,
        "parent": M6_REQUEST_BASE,
        "paths": sorted(M6_REQUEST_DOCS),
    }


def m6_request_candidate(event):
    return merge_candidate(
        event, M6_REQUEST_BASE, M6_REQUEST_BRANCH, M6_REQUEST_ASSIGNMENT, "M6_REQUEST"
    )


def m6_assessment_event(event):
    return event.get("head_ref") == M6_ASSESSMENT_BRANCH or (
        event.get("event") == "push"
        and event["ref"] == "refs/heads/main"
        and commit_parents("HEAD")[:1] == [M6_ASSESSMENT_BASE]
    )


def m6_assessment_assignment_proof():
    return {
        "sha": M6_ASSESSMENT_ASSIGNMENT,
        "tree": M6_ASSESSMENT_ASSIGNMENT_TREE,
        "parent": M6_ASSESSMENT_BASE,
        "paths": sorted(M6_ASSESSMENT_DOCS),
    }


def m6_assessment_candidate(event):
    return merge_candidate(
        event, M6_ASSESSMENT_BASE, M6_ASSESSMENT_BRANCH, M6_ASSESSMENT_ASSIGNMENT, "M6_ASSESSMENT"
    )


def admit_m6_slice_source(event, evidence, *, assessment=False, pricing=False):
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    if pricing:
        prefix, base_tree = "m6_pricing", M6_PRICING_TREE
        migration, allowed = M6_PRICING_MIGRATION, M6_PRICING_IMPLEMENTATION_PATHS
        assignment = m6_pricing_assignment_proof()
        candidate = m6_pricing_candidate(event)
    elif assessment:
        prefix, base_tree = "m6_assessment", M6_ASSESSMENT_TREE
        migration, allowed = M6_ASSESSMENT_MIGRATION, M6_ASSESSMENT_IMPLEMENTATION_PATHS
        assignment = m6_assessment_assignment_proof()
        candidate = m6_assessment_candidate(event)
    else:
        prefix, base_tree = "m6_request", M6_REQUEST_TREE
        migration, allowed = M6_REQUEST_MIGRATION, M6_REQUEST_IMPLEMENTATION_PATHS
        assignment = m6_request_assignment_proof()
        candidate = m6_request_candidate(event)
    base, assignment_sha, docs = assignment["parent"], assignment["sha"], set(assignment["paths"])
    require(capture(["git", "rev-parse", base + "^{tree}"]) == base_tree, "BASE_TREE")
    require(
        capture(["git", "rev-parse", assignment_sha + "^{tree}"]) == assignment["tree"]
        and commit_parents(assignment_sha) == [base],
        f"{prefix.upper()}_ASSIGNMENT_IDENTITY",
    )
    diff = ["git", "diff", "--no-renames", "--name-only"]
    require(
        set(capture([*diff, base, assignment_sha]).splitlines()) == docs,
        f"{prefix.upper()}_ASSIGNMENT_WRITE_SET",
    )
    implementation = set(capture([*diff, assignment_sha, candidate["sha"]]).splitlines())
    require(
        migration in implementation and implementation <= allowed, f"{prefix.upper()}_WRITE_SET"
    )
    paths = capture([*diff, base, "HEAD"]).splitlines()
    require(set(paths) == docs | implementation, f"{prefix.upper()}_MERGE_WRITE_SET")
    write(
        evidence / "source-admission.json",
        {
            "base": base,
            "base_tree": base_tree,
            "source": event["head"],
            "tree": event["tree"],
            "paths": paths,
            "result": "PASS",
            prefix + "_assignment": assignment,
            prefix + "_candidate": candidate,
        },
    )


def m6_pricing_event(event):
    return event.get("head_ref") == M6_PRICING_BRANCH or (
        event.get("event") == "push"
        and event["ref"] == "refs/heads/main"
        and commit_parents("HEAD")[:1] == [M6_PRICING_BASE]
    )


def m6_pricing_assignment_proof():
    return {
        "sha": M6_PRICING_ASSIGNMENT,
        "tree": M6_PRICING_ASSIGNMENT_TREE,
        "parent": M6_PRICING_BASE,
        "paths": sorted(M6_PRICING_DOCS),
    }


def m6_pricing_candidate(event):
    return merge_candidate(
        event, M6_PRICING_BASE, M6_PRICING_BRANCH, M6_PRICING_ASSIGNMENT, "M6_PRICING"
    )


def m6_plan_candidate(event):
    return merge_candidate(event, M6_PLAN_BASE, M6_PLAN_BRANCH, M6_PLAN_INITIAL, "M6_PLAN")


def admit_m6_plan_source(event, evidence):
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    require(event["event"] != "pull_request" or event["pr_number"] == 55, "M6_PLAN_PR_NUMBER")
    require(capture(["git", "rev-parse", M6_PLAN_BASE + "^{tree}"]) == M6_PLAN_TREE, "BASE_TREE")
    candidate = m6_plan_candidate(event)
    diff = ["git", "diff", "--no-renames", "--name-only"]
    review_paths = capture([*diff, M6_PLAN_INITIAL, candidate["sha"]]).splitlines()
    require(set(review_paths) <= M6_PLAN_REVIEW_PATHS, "M6_PLAN_REVIEW_WRITE_SET")
    paths = capture([*diff, M6_PLAN_BASE, "HEAD"]).splitlines()
    require(bool(paths) and set(paths) <= M6_PLAN_PATHS, "M6_PLAN_WRITE_SET")
    write(
        evidence / "source-admission.json",
        {
            "base": M6_PLAN_BASE,
            "base_tree": M6_PLAN_TREE,
            "source": event["head"],
            "tree": event["tree"],
            "paths": paths,
            "result": "PASS",
            "m6_plan_candidate": candidate,
        },
    )


def admit_v7_fix_source(event, manifest, evidence):
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    require(
        capture(["git", "rev-parse", M5_V7_FIX_BASE + "^{tree}"]) == M5_V7_FIX_TREE,
        "V7_FIX_BASE_TREE",
    )
    require(
        capture(["git", "rev-parse", M5_V7_FIX_ASSIGNMENT + "^{tree}"])
        == M5_V7_FIX_ASSIGNMENT_TREE,
        "V7_FIX_ASSIGNMENT_TREE",
    )
    require(commit_parents(M5_V7_FIX_ASSIGNMENT) == [M5_V7_FIX_BASE], "V7_FIX_ASSIGNMENT_PARENT")
    assignment = v7_fix_assignment_proof()
    require(
        capture(["git", "diff", "--name-only", M5_V7_FIX_BASE, M5_V7_FIX_ASSIGNMENT]).splitlines()
        == assignment["paths"],
        "V7_FIX_ASSIGNMENT_PATHS",
    )
    candidate = v7_fix_candidate(event)
    require(
        not capture(
            [
                "git",
                "diff",
                "--name-only",
                M5_V7_FIX_ASSIGNMENT,
                candidate["sha"],
                "--",
                *sorted(M5_INTAKE_C0_DOCS),
            ]
        ),
        "V7_FIX_C0_DOCS_IMMUTABLE",
    )
    paths = capture(["git", "diff", "--name-only", M5_V7_FIX_BASE, "HEAD"]).splitlines()
    require(M5_V7_FIX_DOCS <= set(paths) <= M5_V7_FIX_PATHS, "V7_FIX_WRITE_SET")
    require(
        not capture(["git", "status", "--porcelain", "--untracked-files=all"]),
        "V7_FIX_CLEAN_SOURCE",
    )
    write(
        evidence / "source-admission.json",
        {
            "base": M5_V7_FIX_BASE,
            "base_tree": M5_V7_FIX_TREE,
            "source": event["head"],
            "tree": event["tree"],
            "paths": paths,
            "result": "PASS",
            "v7_fix_assignment": assignment,
            "v7_fix_candidate": candidate,
        },
    )
    return event, manifest


def intake_assignment_proof():
    return {
        "sha": M5_INTAKE_ASSIGNMENT,
        "tree": M5_INTAKE_ASSIGNMENT_TREE,
        "parent": M5_INTAKE_BASE,
        "paths": sorted(M5_INTAKE_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}),
    }


def intake_scope_amendment_proof():
    return {
        "sha": M5_INTAKE_SCOPE_AMENDMENT,
        "tree": M5_INTAKE_SCOPE_AMENDMENT_TREE,
        "parent": M5_INTAKE_SCOPE_AMENDMENT_PARENT,
        "paths": ["docs/tasks/M5_HANDOFF.md"],
    }


def intake_event(event):
    if event.get("head_ref") == M5_INTAKE_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    # A damaged assignment cannot silently fall back through an older main route.
    for revision in (M5_INTAKE_BASE, M5_INTAKE_ASSIGNMENT):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        require(result.returncode in (0, 1, 128), "INTAKE_SOURCE_ANCESTRY")
        if result.returncode == 0:
            return True
    return False


def admit_intake_source(event, manifest, evidence):
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    require(event["event"] in {"pull_request", "push"}, "INTAKE_EVENT")
    if event["event"] == "pull_request":
        require(event["base_sha"] == M5_INTAKE_BASE, "INTAKE_EVENT_BASE")
    else:
        require(event["ref"] == "refs/heads/main", "INTAKE_MAIN_ONLY")
    require(
        capture(["git", "rev-parse", M5_INTAKE_BASE + "^{tree}"]) == M5_INTAKE_TREE,
        "INTAKE_BASE_TREE",
    )
    require(
        capture(["git", "rev-parse", M5_INTAKE_ASSIGNMENT + "^{tree}"])
        == M5_INTAKE_ASSIGNMENT_TREE,
        "INTAKE_ASSIGNMENT_TREE",
    )
    require(
        capture(["git", "rev-list", "--parents", "-n", "1", M5_INTAKE_ASSIGNMENT]).split()
        == [M5_INTAKE_ASSIGNMENT, M5_INTAKE_BASE],
        "INTAKE_ASSIGNMENT_PARENT",
    )
    require(
        capture(["git", "merge-base", M5_INTAKE_ASSIGNMENT, "HEAD"]) == M5_INTAKE_ASSIGNMENT,
        "INTAKE_ASSIGNMENT_ANCESTRY",
    )
    require(
        capture(["git", "diff", "--name-only", M5_INTAKE_BASE, M5_INTAKE_ASSIGNMENT]).splitlines()
        == intake_assignment_proof()["paths"],
        "INTAKE_ASSIGNMENT_PATHS",
    )
    require(
        capture(["git", "rev-parse", M5_INTAKE_SCOPE_AMENDMENT + "^{tree}"])
        == M5_INTAKE_SCOPE_AMENDMENT_TREE,
        "INTAKE_SCOPE_AMENDMENT_TREE",
    )
    require(
        capture(["git", "rev-list", "--parents", "-n", "1", M5_INTAKE_SCOPE_AMENDMENT]).split()
        == [M5_INTAKE_SCOPE_AMENDMENT, M5_INTAKE_SCOPE_AMENDMENT_PARENT],
        "INTAKE_SCOPE_AMENDMENT_PARENT",
    )
    require(
        capture(["git", "merge-base", M5_INTAKE_SCOPE_AMENDMENT, "HEAD"])
        == M5_INTAKE_SCOPE_AMENDMENT,
        "INTAKE_SCOPE_AMENDMENT_ANCESTRY",
    )
    require(
        capture(
            [
                "git",
                "diff",
                "--name-only",
                M5_INTAKE_SCOPE_AMENDMENT_PARENT,
                M5_INTAKE_SCOPE_AMENDMENT,
            ]
        ).splitlines()
        == intake_scope_amendment_proof()["paths"],
        "INTAKE_SCOPE_AMENDMENT_PATHS",
    )
    require(
        not capture(
            [
                "git",
                "diff",
                "--name-only",
                M5_INTAKE_ASSIGNMENT,
                "HEAD",
                "--",
                *sorted(M5_INTAKE_C0_DOCS),
            ]
        ),
        "INTAKE_C0_DOCS_IMMUTABLE",
    )
    paths = capture(["git", "diff", "--name-only", M5_INTAKE_BASE, "HEAD"]).splitlines()
    require(bool(paths) and set(paths) <= M5_INTAKE_PATHS, "INTAKE_WRITE_SET")
    require(
        not capture(["git", "status", "--porcelain", "--untracked-files=all"]),
        "INTAKE_CLEAN_SOURCE",
    )
    write(
        evidence / "source-admission.json",
        {
            "base": M5_INTAKE_BASE,
            "base_tree": M5_INTAKE_TREE,
            "source": event["head"],
            "tree": event["tree"],
            "paths": paths,
            "result": "PASS",
            "intake_assignment": intake_assignment_proof(),
            "intake_scope_amendment": intake_scope_amendment_proof(),
        },
    )
    return event, manifest


def delivery_event(event):
    if event.get("head_ref") == M5_DELIVERY_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    # Either known anchor selects this route; a damaged other anchor must not
    # fall back to historical main admission before its exact checks.
    for revision in (M5_DELIVERY_BASE, M5_DELIVERY_ASSIGNMENT):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        require(result.returncode in (0, 1, 128), "DELIVERY_SOURCE_ANCESTRY")
        if result.returncode == 0:
            return True
    return False


def foundation_budget_event(event):
    if event.get("head_ref") == M5_FOUNDATION_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    # Either known anchor selects this route; a damaged other anchor must not
    # fall back to historical main admission before its exact checks.
    for revision in (M5_FOUNDATION_BASE, M5_FOUNDATION_ASSIGNMENT):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        require(result.returncode in (0, 1, 128), "FOUNDATION_BUDGET_SOURCE_ANCESTRY")
        if result.returncode == 0:
            return True
    return False


def portfolio_event(event):
    if event.get("head_ref") == M5_PORTFOLIO_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_PORTFOLIO_ASSIGNMENT, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "PORTFOLIO_ASSIGNMENT_ANCESTRY")
    return result.returncode == 0


def search_event(event):
    if event.get("head_ref") == M5_SEARCH_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_SEARCH_ASSIGNMENT, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "SEARCH_ASSIGNMENT_ANCESTRY")
    return result.returncode == 0


def capability_event(event):
    if event.get("head_ref") == M5_CAPABILITY_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_CAPABILITY_ASSIGNMENT, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "CAPABILITY_ASSIGNMENT_ANCESTRY")
    return result.returncode == 0


def knowledge_event(event):
    if event.get("head_ref") == M5_KNOWLEDGE_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_KNOWLEDGE_ASSIGNMENT, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "KNOWLEDGE_ASSIGNMENT_ANCESTRY")
    return result.returncode == 0


def configuration_event(event):
    if event.get("head_ref") == M5_CONFIGURATION_BRANCH:
        return True
    if event["ref"] != "refs/heads/main":
        return False
    # The ordinary main route follows the same accepted implementation base.
    # Older source fixtures retain their historical route and closed write-set.
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", M5_CONFIGURATION_BASE, "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(result.returncode in (0, 1, 128), "CONFIGURATION_BASE_ANCESTRY")
    return result.returncode == 0


def admit_source(evidence):
    from scripts import native_context_db_catalog as catalog

    event, manifest = catalog.admit_event(evidence, entrypoint="run")
    pricing = m6_pricing_event(event)
    assessment = m6_assessment_event(event)
    if pricing or assessment or m6_request_event(event):
        admit_m6_slice_source(event, evidence, assessment=assessment, pricing=pricing)
        return event, manifest
    if m6_plan_event(event):
        admit_m6_plan_source(event, evidence)
        return event, manifest
    if v7_fix_event(event):
        return admit_v7_fix_source(event, manifest, evidence)
    if intake_event(event):
        return admit_intake_source(event, manifest, evidence)
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    planning = event.get("head_ref") == M5_PLAN_BRANCH
    intake = intake_event(event)
    delivery = not intake and delivery_event(event)
    foundation_budget = not (intake or delivery) and foundation_budget_event(event)
    portfolio = not (intake or delivery or foundation_budget) and portfolio_event(event)
    search = not (intake or delivery or foundation_budget or portfolio) and search_event(event)
    capability = not (
        intake or delivery or foundation_budget or portfolio or search
    ) and capability_event(event)
    knowledge = not (
        intake or delivery or foundation_budget or portfolio or search or capability
    ) and knowledge_event(event)
    configuration = not (
        intake or delivery or foundation_budget or portfolio or search or capability or knowledge
    ) and configuration_event(event)
    require(
        event["ref"] in {"refs/heads/" + TARGETED_BRANCH, "refs/heads/main"}
        or event.get("head_ref") == BRANCH
        or planning
        or delivery
        or foundation_budget
        or configuration
        or knowledge
        or capability
        or search
        or portfolio,
        "POLZA_RUNTIME_EVENT_BRANCH",
    )
    base, base_tree = (
        (M5_INTAKE_BASE, M5_INTAKE_TREE)
        if intake
        else (M5_DELIVERY_BASE, M5_DELIVERY_TREE)
        if delivery
        else (M5_FOUNDATION_BASE, M5_FOUNDATION_TREE)
        if foundation_budget
        else (M5_PORTFOLIO_BASE, M5_PORTFOLIO_TREE)
        if portfolio
        else (M5_SEARCH_BASE, M5_SEARCH_TREE)
        if search
        else (M5_CAPABILITY_BASE, M5_CAPABILITY_TREE)
        if capability
        else (M5_KNOWLEDGE_BASE, M5_KNOWLEDGE_TREE)
        if knowledge
        else (M5_CONFIGURATION_BASE, M5_CONFIGURATION_TREE)
        if configuration
        else (M5_PLAN_BASE, M5_PLAN_TREE)
        if planning
        else (BASE, BASE_TREE)
    )
    if delivery:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "DELIVERY_EVENT_BASE")
        require(
            capture(["git", "rev-parse", M5_DELIVERY_ASSIGNMENT + "^{tree}"])
            == M5_DELIVERY_ASSIGNMENT_TREE,
            "DELIVERY_ASSIGNMENT_TREE",
        )
        require(
            capture(["git", "merge-base", M5_DELIVERY_ASSIGNMENT, "HEAD"])
            == M5_DELIVERY_ASSIGNMENT,
            "DELIVERY_ASSIGNMENT_ANCESTRY",
        )
        require(
            capture(["git", "rev-parse", M5_DELIVERY_ASSIGNMENT + "^"]) == M5_DELIVERY_BASE,
            "DELIVERY_ASSIGNMENT_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_DELIVERY_SCOPE_AMENDMENT + "^{tree}"])
            == M5_DELIVERY_SCOPE_AMENDMENT_TREE,
            "DELIVERY_SCOPE_AMENDMENT_TREE",
        )
        require(
            capture(
                ["git", "rev-list", "--parents", "-n", "1", M5_DELIVERY_SCOPE_AMENDMENT]
            ).split()
            == [M5_DELIVERY_SCOPE_AMENDMENT, M5_DELIVERY_ASSIGNMENT],
            "DELIVERY_SCOPE_AMENDMENT_PARENT",
        )
        require(
            capture(["git", "merge-base", M5_DELIVERY_SCOPE_AMENDMENT, "HEAD"])
            == M5_DELIVERY_SCOPE_AMENDMENT,
            "DELIVERY_SCOPE_AMENDMENT_ANCESTRY",
        )
        require(
            capture(
                ["git", "diff", "--name-only", M5_DELIVERY_ASSIGNMENT, M5_DELIVERY_SCOPE_AMENDMENT]
            ).splitlines()
            == ["docs/tasks/M5_HANDOFF.md"],
            "DELIVERY_SCOPE_AMENDMENT_PATHS",
        )
        require(
            capture(["git", "rev-parse", M5_DELIVERY_SCOPE_AMENDMENT_02 + "^{tree}"])
            == M5_DELIVERY_SCOPE_AMENDMENT_02_TREE,
            "DELIVERY_SCOPE_AMENDMENT_02_TREE",
        )
        require(
            capture(
                ["git", "rev-list", "--parents", "-n", "1", M5_DELIVERY_SCOPE_AMENDMENT_02]
            ).split()
            == [M5_DELIVERY_SCOPE_AMENDMENT_02, M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT],
            "DELIVERY_SCOPE_AMENDMENT_02_PARENT",
        )
        require(
            capture(["git", "merge-base", M5_DELIVERY_SCOPE_AMENDMENT_02, "HEAD"])
            == M5_DELIVERY_SCOPE_AMENDMENT_02,
            "DELIVERY_SCOPE_AMENDMENT_02_ANCESTRY",
        )
        require(
            capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT,
                    M5_DELIVERY_SCOPE_AMENDMENT_02,
                ]
            ).splitlines()
            == ["docs/tasks/M5_HANDOFF.md"],
            "DELIVERY_SCOPE_AMENDMENT_02_PATHS",
        )
        require(
            not capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_DELIVERY_ASSIGNMENT,
                    "HEAD",
                    "--",
                    *sorted(M5_DELIVERY_C0_DOCS),
                ]
            ),
            "DELIVERY_C0_DOCS_IMMUTABLE",
        )
    if foundation_budget:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "FOUNDATION_BUDGET_EVENT_BASE")
        require(
            capture(["git", "rev-parse", M5_FOUNDATION_ASSIGNMENT + "^{tree}"])
            == M5_FOUNDATION_ASSIGNMENT_TREE,
            "FOUNDATION_BUDGET_ASSIGNMENT_TREE",
        )
        require(
            capture(["git", "merge-base", M5_FOUNDATION_ASSIGNMENT, "HEAD"])
            == M5_FOUNDATION_ASSIGNMENT,
            "FOUNDATION_BUDGET_ASSIGNMENT_ANCESTRY",
        )
        require(
            capture(["git", "rev-parse", M5_FOUNDATION_ASSIGNMENT + "^"]) == M5_FOUNDATION_BASE,
            "FOUNDATION_BUDGET_ASSIGNMENT_PARENT",
        )
        require(
            not capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_FOUNDATION_ASSIGNMENT,
                    "HEAD",
                    "--",
                    *sorted(M5_FOUNDATION_C0_DOCS),
                ]
            ),
            "FOUNDATION_BUDGET_C0_DOCS_IMMUTABLE",
        )
    if configuration and event["event"] == "pull_request":
        require(event["base_sha"] == base, "CONFIGURATION_EVENT_BASE")
    if portfolio:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "PORTFOLIO_EVENT_BASE")
        for name, revision, tree in (
            ("ASSIGNMENT", M5_PORTFOLIO_ASSIGNMENT, M5_PORTFOLIO_ASSIGNMENT_TREE),
            ("CONTRACT", M5_PORTFOLIO_CONTRACT, M5_PORTFOLIO_CONTRACT_TREE),
            ("CONTINUATION", M5_PORTFOLIO_CONTINUATION, M5_PORTFOLIO_CONTINUATION_TREE),
            ("CHECKPOINT", M5_PORTFOLIO_CHECKPOINT, M5_PORTFOLIO_CHECKPOINT_TREE),
            (
                "FINISH_ASSIGNMENT",
                M5_PORTFOLIO_FINISH_ASSIGNMENT,
                M5_PORTFOLIO_FINISH_ASSIGNMENT_TREE,
            ),
            ("REVIEW_BASE", M5_PORTFOLIO_REVIEW_BASE, M5_PORTFOLIO_REVIEW_BASE_TREE),
            (
                "CI_FIX_ASSIGNMENT",
                M5_PORTFOLIO_CI_FIX_ASSIGNMENT,
                M5_PORTFOLIO_CI_FIX_ASSIGNMENT_TREE,
            ),
            ("UNIT_REVIEW_BASE", M5_PORTFOLIO_UNIT_REVIEW_BASE, M5_PORTFOLIO_UNIT_REVIEW_BASE_TREE),
            (
                "UNIT_FIX_ASSIGNMENT",
                M5_PORTFOLIO_UNIT_FIX_ASSIGNMENT,
                M5_PORTFOLIO_UNIT_FIX_ASSIGNMENT_TREE,
            ),
            ("CORE_REVIEW_BASE", M5_PORTFOLIO_CORE_REVIEW_BASE, M5_PORTFOLIO_CORE_REVIEW_BASE_TREE),
            (
                "CORE_FIX_ASSIGNMENT",
                M5_PORTFOLIO_CORE_FIX_ASSIGNMENT,
                M5_PORTFOLIO_CORE_FIX_ASSIGNMENT_TREE,
            ),
        ):
            require(
                capture(["git", "rev-parse", revision + "^{tree}"]) == tree,
                "PORTFOLIO_" + name + "_TREE",
            )
            require(
                capture(["git", "merge-base", revision, "HEAD"]) == revision,
                "PORTFOLIO_" + name + "_ANCESTRY",
            )
        require(
            capture(["git", "merge-base", M5_PORTFOLIO_ASSIGNMENT, M5_PORTFOLIO_CONTRACT])
            == M5_PORTFOLIO_ASSIGNMENT,
            "PORTFOLIO_CONTRACT_ASSIGNMENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_CONTINUATION + "^"]) == M5_PORTFOLIO_CONTRACT,
            "PORTFOLIO_CONTINUATION_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_CHECKPOINT + "^"])
            == M5_PORTFOLIO_CONTINUATION,
            "PORTFOLIO_CHECKPOINT_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_FINISH_ASSIGNMENT + "^"])
            == M5_PORTFOLIO_CHECKPOINT,
            "PORTFOLIO_FINISH_ASSIGNMENT_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_CI_FIX_ASSIGNMENT + "^"])
            == M5_PORTFOLIO_REVIEW_BASE,
            "PORTFOLIO_CI_FIX_ASSIGNMENT_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_UNIT_FIX_ASSIGNMENT + "^"])
            == M5_PORTFOLIO_UNIT_REVIEW_BASE,
            "PORTFOLIO_UNIT_FIX_ASSIGNMENT_PARENT",
        )
        require(
            capture(["git", "rev-parse", M5_PORTFOLIO_CORE_FIX_ASSIGNMENT + "^"])
            == M5_PORTFOLIO_CORE_REVIEW_BASE,
            "PORTFOLIO_CORE_FIX_ASSIGNMENT_PARENT",
        )
        require(
            not capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_PORTFOLIO_ASSIGNMENT,
                    "HEAD",
                    "--",
                    *sorted(M5_PORTFOLIO_C0_DOCS),
                ]
            ),
            "PORTFOLIO_C0_DOCS_IMMUTABLE",
        )
    if search:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "SEARCH_EVENT_BASE")
        require(
            capture(["git", "rev-parse", M5_SEARCH_ASSIGNMENT + "^{tree}"])
            == M5_SEARCH_ASSIGNMENT_TREE,
            "SEARCH_ASSIGNMENT_TREE",
        )
        require(
            capture(["git", "merge-base", M5_SEARCH_ASSIGNMENT, "HEAD"]) == M5_SEARCH_ASSIGNMENT,
            "SEARCH_ASSIGNMENT_ANCESTRY",
        )
        require(
            not capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_SEARCH_ASSIGNMENT,
                    "HEAD",
                    "--",
                    *sorted(M5_SEARCH_C0_DOCS),
                ]
            ),
            "SEARCH_C0_DOCS_IMMUTABLE",
        )
    if capability:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "CAPABILITY_EVENT_BASE")
        require(
            capture(["git", "rev-parse", M5_CAPABILITY_ASSIGNMENT + "^{tree}"])
            == M5_CAPABILITY_ASSIGNMENT_TREE,
            "CAPABILITY_ASSIGNMENT_TREE",
        )
        require(
            capture(["git", "merge-base", M5_CAPABILITY_ASSIGNMENT, "HEAD"])
            == M5_CAPABILITY_ASSIGNMENT,
            "CAPABILITY_ASSIGNMENT_ANCESTRY",
        )
        require(
            capture(["git", "rev-parse", M5_CAPABILITY_C0_DOCS_REVISION + "^{tree}"])
            == M5_CAPABILITY_C0_DOCS_TREE,
            "CAPABILITY_C0_DOCS_TREE",
        )
        require(
            capture(["git", "merge-base", M5_CAPABILITY_C0_DOCS_REVISION, "HEAD"])
            == M5_CAPABILITY_C0_DOCS_REVISION,
            "CAPABILITY_C0_DOCS_ANCESTRY",
        )
        require(
            not capture(
                [
                    "git",
                    "diff",
                    "--name-only",
                    M5_CAPABILITY_C0_DOCS_REVISION,
                    "HEAD",
                    "--",
                    *sorted(M5_CAPABILITY_C0_DOCS),
                ]
            ),
            "CAPABILITY_C0_DOCS_IMMUTABLE",
        )
    if knowledge:
        if event["event"] == "pull_request":
            require(event["base_sha"] == base, "KNOWLEDGE_EVENT_BASE")
        require(
            capture(["git", "rev-parse", M5_KNOWLEDGE_ASSIGNMENT + "^{tree}"])
            == M5_KNOWLEDGE_ASSIGNMENT_TREE,
            "KNOWLEDGE_ASSIGNMENT_TREE",
        )
        require(
            capture(["git", "merge-base", M5_KNOWLEDGE_ASSIGNMENT, "HEAD"])
            == M5_KNOWLEDGE_ASSIGNMENT,
            "KNOWLEDGE_ASSIGNMENT_ANCESTRY",
        )
    require(capture(["git", "rev-parse", base + "^{tree}"]) == base_tree, "BASE_TREE")
    require(capture(["git", "merge-base", base, "HEAD"]) == base, "BASE_ANCESTRY")
    allowed = {
        "AGENTS.md",
        "tests/test_m2_4_browser_fixture.py",
        "tests/generic_pg_schema.py",
        "backend/src/asm/ai/runtime.py",
        "tests/test_m4_delivery.py",
        "backend/src/asm/telegram/client.py",
        "scripts/m4_runtime_pilot.py",
        "docs/runbooks/M4_RUNTIME_PILOT.md",
        "tests/test_m4_schema_postgres.py",
        "backend/src/asm/messaging/worker.py",
        "tests/test_m2_3_db_postgres.py",
        "backend/src/asm/ai/database.py",
        "backend/src/asm/ai/runtime_settings.py",
        "docs/runbooks/M4_POLZA_PROBE.md",
        "tests/test_m4_polza_runtime_postgres.py",
        "scripts/m4_runtime_db.py",
        "backend/src/asm/ai/provider_runtime.py",
        "backend/src/asm/ai/polza.py",
        "tests/test_foundation.py",
        "tests/test_postgres.py",
        "tests/test_m1_3_c0_acceptance.py",
        "tests/test_m1_3_api_postgres.py",
        "tests/test_auth_postgres.py",
        "scripts/native_context_db_catalog.py",
        "docs/TASK_REGISTER.md",
        "tests/test_m3_2_escalations_migrations.py",
        "tests/test_tenancy_postgres.py",
        "backend/src/asm/messaging/results.py",
        "tests/test_telegram_egress_postgres.py",
        "tests/test_m4_runtime_db_runner.py",
        "tests/test_m4_runtime_migrations.py",
        "backend/src/asm/telegram/provisioning.py",
        "tests/test_m4_polza_runtime.py",
        "backend/src/asm/foundation.py",
        "tests/test_m4_delivery_postgres.py",
        "docs/decisions/IMPL-004-m4-pilot-ai.md",
        "scripts/m2_4_browser_fixture.py",
        "tests/test_m3_1_native_context_postgres.py",
        "tests/test_m3_1_native_context_runtime_postgres.py",
        "backend/src/asm/messaging/database.py",
        "scripts/prepare_telegram_egress.py",
        "scripts/test_telegram_egress.sh",
        "tests/test_m3_1_guards_migrations.py",
        "tests/test_telegram_egress.py",
        "migrations/versions/0016_polza_runtime.py",
        "migrations/versions/0017_ai_reply_rights.py",
        "tests/test_m4_reply_rights_postgres.py",
        "tests/test_m4_reply_rights.py",
        "tests/polling/test_receiver.py",
        "tests/test_m4_polza_runtime_migrations.py",
        "tests/test_m2_3_setup.py",
        "docs/tasks/M4_HANDOFF.md",
        "tests/test_native_context_db_runner.py",
        "tests/test_m2_3_schema_postgres.py",
    }
    if delivery:
        allowed = M5_DELIVERY_PATHS
    elif foundation_budget:
        allowed = M5_FOUNDATION_PATHS
    elif portfolio:
        allowed = M5_PORTFOLIO_PATHS
    elif search:
        allowed = M5_SEARCH_PATHS
    elif capability:
        allowed = M5_CAPABILITY_PATHS
    elif knowledge:
        allowed = M5_KNOWLEDGE_PATHS
    elif configuration:
        allowed = M5_CONFIGURATION_PATHS
    elif planning:
        allowed = M5_PLAN_PATHS
    elif event["ref"] == "refs/heads/main":
        # The ordinary post-merge lane retains its original ancestry and checks.
        allowed = allowed | M5_PLAN_PATHS
    paths = capture(["git", "diff", "--name-only", base, "HEAD"]).splitlines()
    require(bool(paths) and set(paths) <= allowed, "POLZA_RUNTIME_WRITE_SET")
    admission = {
        "base": base,
        "base_tree": base_tree,
        "source": event["head"],
        "tree": event["tree"],
        "paths": paths,
        "result": "PASS",
    }
    if delivery:
        admission["scope_amendment"] = delivery_scope_amendment()
        admission["scope_amendment_02"] = delivery_scope_amendment_02()
    write(evidence / "source-admission.json", admission)
    return event, manifest


def catalog_comparison(expected, digest, nonfunction, declared):
    from asm.foundation import NATIVE_CONTEXT_PROFILE_SHA256, NATIVE_PROFILE_BODY_SHA256

    revision = expected["revision"]
    profile = (
        "platform.price_schema_profile()"
        if revision == "0027"
        else "platform.service_assessment_schema_profile()"
        if revision == "0026"
        else "platform.service_request_schema_profile()"
        if revision == "0025"
        else "platform.intake_v7_schema_profile()"
        if revision == "0024"
        else "platform.intake_schema_profile()"
        if revision == "0023"
        else "platform.portfolio_delivery_schema_profile()"
        if revision == "0022"
        else "platform.portfolio_schema_profile()"
        if revision == "0021"
        else "platform.knowledge_search_schema_profile()"
        if revision == "0020"
        else "platform.published_knowledge_schema_profile()"
        if revision == "0019"
        else "platform.business_configuration_schema_profile()"
        if revision == "0018"
        else "platform.ai_reply_rights_schema_profile()"
        if revision == "0017"
        else "platform.human_context_schema_profile()"
    )
    body_hash = expected["functions"][profile]["body_sha256"]
    declared_matches = (
        declared == {"schema_revision": revision, "valid": True, "profile_sha256": digest}
        and type(declared.get("valid")) is bool
    )
    profile_pin, body_pin = NATIVE_CONTEXT_PROFILE_SHA256, NATIVE_PROFILE_BODY_SHA256
    if revision == "0026":
        profile_pin = "4c51a6773a39f4596dbf6da3dcc36e4ff0dfa0e0ed8eadaa399734aff2ed9910"
        body_pin = "c7c9624fcc55e4ff00a3b4abf7ec8e907f099898ec41a21fc3fbfef5d68493f8"
    if revision == "0025":
        profile_pin = "98be26f6a296c95d4e9a489d0a63db6f1c0e8b36df391c6cb7ab6b32058c6bde"
        body_pin = "b6fb012dec5fcc2e74b1ed83ff11a3c2d02ac82cdb819a7062a6d70abdbd95a0"
    if revision == "0024":
        profile_pin = "33fbfcc9e3c09021ea7bc38de857706a8f23270d7c1dcd79d55ed20f3a5b63c0"
        body_pin = "ab79bb829f4c2262557732cd4bfff38145231038c5504d0edfca58845a98ceac"
    if revision == "0023":
        profile_pin = "4732ea9f9b0039b8616daf081f78e0ce4731a63884605eb88fe22bfb5851179d"
        body_pin = "87197672ba2e5476ec2657e5c1d96c49ef78eff6892c26258f0fb3eb8c07e899"
    if revision == "0022":
        profile_pin = "5e4191f74a2eba509085072acc5d4fc62366207d4b434a33a770d504273a2bc7"
        body_pin = "499d3b25887b3dd50f0a2f8f7e7b324d8cca226a270a3dd99e5506e376733bf0"
    if revision == "0019":
        profile_pin = "e2bfd685188e1b67430de02c03eb3cef3af8f13de74e13d641032085b3b23c36"
        body_pin = "93c1c8615c17619929194606686ebd21b7f99afa7698cfd425bb6b65035137f5"
    if revision == "0018":
        profile_pin = "01bb105b2012725a3905cf5fcf9826f9f58afd21897caf237645dbd7a88c0999"
        body_pin = "0f9dcf5d0a11c56e4d78f76626c70ea7f705962aa6bbd71a1cde183f5c530498"
    if revision == "0017":
        # Accepted0017 pins stay closed for its historical checker. They are
        # never substituted for the successor application's readiness gate.
        profile_pin = "b01e35c20cf91788c863ddebd78de8c1c54ac19896f6f16388e2295eba5c3538"
        body_pin = "6b635b12b8d2e7f0f69500792d7ec3b1c71cd0f85c51e810e3332b910b6189c0"
    pin_matches = revision == "0013" or digest == profile_pin
    body_matches = revision == "0013" or body_hash == body_pin
    return {
        "revision": revision,
        "independent_profile_sha256": digest,
        "nonfunction_sha256": hashlib.sha256(nonfunction.encode()).hexdigest(),
        "functions_checked": len(expected["functions"]),
        "tables_checked": len(expected["columns"]),
        "verifier_body_sha256": body_hash,
        "application_body_pin_matches": body_matches,
        "application_profile_pin": profile_pin,
        "application_body_pin": body_pin,
        "all_source_bodies_security_roles_nonfunction": "PASS",
        "declared_equals_independent": declared_matches,
        "application_pin_matches": pin_matches,
        "failed_predicate": "CATALOG_DECLARED_PROFILE"
        if not declared_matches
        else "APPLICATION_VERIFIER_BODY_PIN"
        if not body_matches
        else "APPLICATION_FULL_CATALOG_PIN"
        if not pin_matches
        else None,
    }


def stock_catalog():
    """Independent stock facts before consulting the installed verifier/pin."""
    import psycopg
    from psycopg.rows import dict_row
    from sqlalchemy.engine import make_url

    from scripts import native_context_db_catalog as catalog

    url = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"])
    require(url.database == "asm_test" and url.username == "asm_migrator", "CATALOG_TARGET")
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    ) as c:
        c.execute("SET TRANSACTION READ ONLY")
        for sql in (
            "SET LOCAL search_path=pg_catalog,pg_temp",
            "SET LOCAL timezone='UTC'",
            "SET LOCAL extra_float_digits=3",
            "SET LOCAL statement_timeout='10s'",
        ):
            c.execute(sql)
        revision = c.execute("SELECT version_num FROM platform.alembic_version").fetchone()[0]
        require(
            revision
            in {
                "0013",
                "0017",
                "0018",
                "0019",
                "0020",
                "0021",
                "0022",
                "0023",
                "0024",
                "0025",
                "0026",
                "0027",
            },
            "CATALOG_REVISION",
        )
        destination = evidence_path() / ("catalog-" + revision)
        destination.mkdir(mode=0o700)
        expected = catalog.source_catalog(catalog.ROOT, revision)
        write(destination / "expected-source-catalog.json", expected)
        if revision in {
            "0017",
            "0018",
            "0019",
            "0020",
            "0021",
            "0022",
            "0023",
            "0024",
            "0025",
            "0026",
            "0027",
        }:
            write(
                destination / "embedded-invariant.json", catalog.compare_embedded_profile(expected)
            )
        (destination / "independent-catalog.sql").write_text(
            catalog.CATALOG_SQL + ";\n" + catalog.FUNCTION_SQL + ";\n" + catalog.ROLE_SQL
        )
        full, nonfunction = c.execute(catalog.CATALOG_SQL).fetchone()
        (destination / "installed-catalog.pg-json.txt").write_text(full)
        (destination / "installed-nonfunction.pg-json.txt").write_text(nonfunction)
        locale = c.execute(
            "SELECT jsonb_build_object('server_version',current_setting('server_version'),'server_version_num',current_setting('server_version_num'),'lc_collate',datcollate,'lc_ctype',datctype,'provider',datlocprovider,'locale',to_jsonb(d)->'datlocale','collation_version',datcollversion,'encoding',pg_encoding_to_char(encoding)) FROM pg_database d WHERE datname=current_database()"
        ).fetchone()[0]
        locale["function_order"] = [row[0] for row in json.loads(full)["functions"]]
        locale["function_order_C"] = c.execute(
            "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f' ORDER BY p.oid::regprocedure::text COLLATE \"C\""
        ).fetchall()
        write(destination / "locale-and-order.json", locale)
        require(locale["server_version_num"] == "180006", "CATALOG_SERVER_VERSION")
        c.row_factory = dict_row
        functions = c.execute(catalog.FUNCTION_SQL).fetchall()
        resolved = {
            r["signature"]: r["oid"]
            for r in c.execute(
                "SELECT signature,to_regprocedure(signature)::oid::bigint AS oid FROM unnest(%s::text[]) AS source(signature) ORDER BY signature",
                (sorted(expected["functions"]),),
            ).fetchall()
        }
        write(
            destination / "installed-function-oids.json",
            {"functions": functions, "resolved": resolved},
        )
        roles = c.execute(catalog.ROLE_SQL).fetchall()
        memberships = c.execute(
            "SELECT roleid,member FROM pg_auth_members WHERE roleid IN ('asm_runtime'::regrole,'asm_migrator'::regrole) OR member IN ('asm_runtime'::regrole,'asm_migrator'::regrole)"
        ).fetchall()
        owned = c.execute(
            "SELECT (SELECT count(*) FROM pg_database WHERE datdba='asm_runtime'::regrole) + (SELECT count(*) FROM pg_namespace WHERE nspowner='asm_runtime'::regrole) + (SELECT count(*) FROM pg_class WHERE relowner='asm_runtime'::regrole) + (SELECT count(*) FROM pg_proc WHERE proowner='asm_runtime'::regrole) AS count"
        ).fetchone()["count"]
        write(
            destination / "roles.json",
            {"roles": roles, "memberships": memberships, "owned_by_runtime": owned},
        )
        catalog.compare_roles(roles, memberships, owned)
        catalog.compare_functions(expected["functions"], functions, resolved)
        digest = catalog.compare_snapshot(expected["columns"], full, nonfunction, revision=revision)
        profile = (
            "platform.price_schema_profile()"
            if revision == "0027"
            else "platform.service_assessment_schema_profile()"
            if revision == "0026"
            else "platform.service_request_schema_profile()"
            if revision == "0025"
            else "platform.intake_v7_schema_profile()"
            if revision == "0024"
            else "platform.intake_schema_profile()"
            if revision == "0023"
            else "platform.portfolio_delivery_schema_profile()"
            if revision == "0022"
            else "platform.portfolio_schema_profile()"
            if revision == "0021"
            else "platform.knowledge_search_schema_profile()"
            if revision == "0020"
            else "platform.published_knowledge_schema_profile()"
            if revision == "0019"
            else "platform.business_configuration_schema_profile()"
            if revision == "0018"
            else "platform.ai_reply_rights_schema_profile()"
            if revision == "0017"
            else catalog.PROFILE
        )
        declared = c.execute("SELECT " + profile + " AS profile").fetchone()["profile"]
        write(destination / "declared-profile.json", declared)
        comparison = catalog_comparison(expected, digest, nonfunction, declared)
        write(destination / "comparison.json", comparison)
        require(comparison["failed_predicate"] is None, comparison["failed_predicate"])


async def readiness():
    from asm.foundation import RuntimeDatabase, Settings

    runtime = RuntimeDatabase(Settings())
    try:
        await runtime.check()
        from asm.foundation import DATABASE_SCHEMA_REVISION

        write(
            evidence_path() / "readiness.json",
            {"revision": DATABASE_SCHEMA_REVISION, "runtime_check": "PASS"},
        )
    finally:
        await runtime.close()


def compose(root):
    return DOCKER + [
        "compose",
        "--project-name",
        "asm-" + root.name,
        "--env-file",
        str(root / "private/test.env"),
        "--env-file",
        "infra/images.lock.env",
        "-f",
        "compose.yaml",
        "--profile",
        "test",
    ]


def capture(args):
    result = subprocess.run(args, capture_output=True, timeout=30)
    require(result.returncode == 0 and len(result.stdout) < 1048576, "INSPECTION_FAILED")
    return result.stdout.decode().strip()


def sanitize(raw, root):
    value = raw.decode(errors="replace")
    env = root / "private/test.env"
    if env.exists():
        for line in env.read_text().splitlines():
            secret = line.partition("=")[2]
            if secret:
                value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"postgres(?:ql)?(?:\+[a-z]+)?://[^\s\"']+", "[REDACTED_DSN]", value)
    return value


def phase(root, label, args, budget, *, separate_stdout=False):
    reports = root / "evidence/phases"
    reports.mkdir(exist_ok=True, mode=0o700)
    start = time.monotonic()
    entry = {"phase": label, "command": args, "budget_seconds": budget, "started_utc": time.time()}
    write(reports / "active.json", entry)
    private = root / ("private/" + label + ".log")
    with (
        private.open("wb") as output,
        (
            (root / ("private/" + label + ".stdout")).open("wb")
            if separate_stdout
            else contextlib.nullcontext(output)
        ) as stdout,
    ):
        process = subprocess.Popen(args, stdout=stdout, stderr=output, start_new_session=True)
        try:
            code = process.wait(timeout=budget)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            code = 124
    entry.update(exit_code=code, seconds=time.monotonic() - start)
    write(reports / (label + ".json"), entry)
    with private.open("rb") as stream:
        raw = stream.read(8388609)
    if len(raw) > 8388608:
        raw = raw[:8388608]
        entry["log_incomplete"] = True
        write(reports / (label + ".json"), entry)
    (reports / (label + ".log")).write_text(sanitize(raw, root))
    print("M4_PG_PHASE=" + label + " EXIT=" + str(code), flush=True)
    require(code == 0, label.upper().replace("-", "_") + "_FAILED")


def stack_diagnostics(root, prefix):
    """Bounded startup evidence: states and known schema-refusal fields only."""
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True, mode=0o700)
    result = {"services": [], "schema_refusals": [], "probe_errors": []}
    for kind, tail in (
        ("states", ["ps", "--all", "--format", "json"]),
        ("logs", ["logs", "--no-color", "--tail", "80", "api", "worker", "migrate"]),
    ):
        try:
            proc = subprocess.run([*prefix, *tail], capture_output=True, timeout=10)
            if proc.returncode or len(proc.stdout) > 262144:
                result["probe_errors"].append(
                    {"probe": kind, "exit": proc.returncode, "bounded": len(proc.stdout) <= 262144}
                )
                continue
            raw = proc.stdout.decode(errors="replace")
            if kind == "states":
                rows = (
                    json.loads(raw)
                    if raw.lstrip().startswith("[")
                    else [json.loads(line) for line in raw.splitlines() if line.strip()]
                )
                for row in rows[:32]:
                    service = row.get("Service", "")
                    if re.fullmatch(r"[a-z][a-z0-9-]{0,48}", service):
                        result["services"].append(
                            {
                                "service": service,
                                "state": row.get("State")
                                if row.get("State")
                                in {
                                    "running",
                                    "exited",
                                    "created",
                                    "restarting",
                                    "dead",
                                    "removing",
                                    "paused",
                                }
                                else "UNKNOWN",
                                "health": row.get("Health")
                                if row.get("Health") in {"", "healthy", "unhealthy", "starting"}
                                else "UNKNOWN",
                                "exit_code": row.get("ExitCode")
                                if type(row.get("ExitCode")) is int
                                else None,
                            }
                        )
            else:
                for line in raw.splitlines():
                    if "{" not in line:
                        continue
                    try:
                        row = json.loads(line[line.index("{") :])
                    except ValueError:
                        continue
                    if (
                        type(row) is dict
                        and row.get("component") == "schema-admission"
                        and row.get("event") == "refused"
                        and row.get("stage")
                        in {"VERIFIER_BODY_OR_SECURITY", "DECLARED_PROFILE_OR_FULL_PIN"}
                    ):
                        error = row.get("error_type", "")
                        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,60}", error):
                            result["schema_refusals"].append(
                                {"stage": row["stage"], "error_type": error}
                            )
        except Exception as error:
            result["probe_errors"].append({"probe": kind, "error_type": type(error).__name__})
    write(evidence / "stack-diagnostics.json", result)


def checks(root, *args, plugin=False):
    command = compose(root) + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        str(root / "evidence") + ":/evidence",
    ]
    if plugin:
        command += ["-e", "ASM_M4_PG_PLUGIN=1"]
        expected = {
            "SOURCE_SHA": os.environ["GITHUB_SHA"],
            "SOURCE_TREE": capture(["git", "rev-parse", "HEAD^{tree}"]),
            "RUN_ID": os.environ["GITHUB_RUN_ID"],
            "RUN_ATTEMPT": os.environ["GITHUB_RUN_ATTEMPT"],
        }
        for name, value in expected.items():
            command += ["-e", "ASM_M4_" + name + "=" + value]
    return command + ["checks", *args]


def inventory(root):
    project = "asm-" + root.name
    return {
        "containers": capture(
            DOCKER + ["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]
        ).split(),
        "networks": capture(
            DOCKER + ["network", "ls", "-q", "--filter", "name=^" + project + "_default$"]
        ).split(),
        "volumes": capture(DOCKER + ["volume", "ls", "-q", "--filter", "name=" + project]).split(),
    }


def current_native_checks(root, label, *args):
    """Use the built locked image, actual read-only Git checkout and owned DB namespace."""
    values = dict(
        line.split("=", 1) for line in (root / "private/test.env").read_text().splitlines()
    )
    env = {
        "ASM_ENVIRONMENT": "TEST",
        "ASM_NATIVE_TEST_ALLOW_RESET": "1",
        "ASM_M4_CURRENT_NATIVE": "1",
        "ASM_M4_PG_PLUGIN": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ASM_M4_SOURCE_SHA": os.environ["GITHUB_SHA"],
        "ASM_M4_SOURCE_TREE": capture(["git", "rev-parse", "HEAD^{tree}"]),
        "ASM_M4_RUN_ID": os.environ["GITHUB_RUN_ID"],
        "ASM_M4_RUN_ATTEMPT": "1",
    }
    for name, user, key, database, driver in (
        (
            "ASM_DATABASE_URL",
            "asm_runtime",
            "PG_RUNTIME_PASSWORD",
            "asm_test",
            "postgresql+psycopg",
        ),
        (
            "ASM_MIGRATION_DATABASE_URL",
            "asm_migrator",
            "PG_MIGRATION_PASSWORD",
            "asm_test",
            "postgresql+psycopg",
        ),
        ("ASM_NATIVE_TEST_ADMIN_URL", "asm_admin", "PG_ADMIN_PASSWORD", "postgres", "postgresql"),
    ):
        env[name] = f"{driver}://{user}:{values[key]}@127.0.0.1:5432/{database}"
    env_path = root / "private/native.env"
    env_path.write_text("".join(k + "=" + v + "\n" for k, v in env.items()))
    identity = capture(compose(root) + ["ps", "-q", "postgres-test"])
    image = capture(
        DOCKER + ["image", "inspect", "--format", "{{.Id}}", "asm-" + root.name + "-checks"]
    )
    return DOCKER + [
        "run",
        "--rm",
        "--cidfile",
        str(root / ("private/" + label + ".cid")),
        "--label",
        "com.docker.compose.project=asm-" + root.name,
        "--label",
        "asm.m4.run=" + os.environ["GITHUB_RUN_ID"],
        "--label",
        "asm.m4.attempt=1",
        "--network",
        "container:" + identity,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env-file",
        str(env_path),
        "--volume",
        str(Path.cwd()) + ":/app:ro",
        "--volume",
        str(root / "evidence") + ":/evidence",
        image,
        *args,
    ]


def collect_current_native():
    import pytest

    require(not os.environ.get("PYTEST_ADDOPTS"), "CURRENT_NATIVE_EXTERNAL_SELECTION")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    data = {"nodeids": [], "deselected": []}

    class Inventory:
        def pytest_collection_finish(self, session):
            data["nodeids"] = [item.nodeid for item in session.items]
            require(data["nodeids"] == CURRENT_NATIVE_NODES, "CURRENT_NATIVE_SELECTION")
            require(
                all(
                    not item.get_closest_marker(m)
                    for item in session.items
                    for m in ("skip", "skipif", "xfail")
                ),
                "CURRENT_NATIVE_SKIP",
            )

        def pytest_deselected(self, items):
            data["deselected"].extend(item.nodeid for item in items)

        def pytest_runtest_setup(self, item):
            raise RuntimeError("INVENTORY_MUST_NOT_EXECUTE")

    code = 1
    try:
        code = int(
            pytest.main(
                [
                    *CURRENT_NATIVE_NODES,
                    "--collect-only",
                    "-q",
                    "-p",
                    "pytest_asyncio.plugin",
                    "-p",
                    "no:cacheprovider",
                ],
                plugins=[Inventory()],
            )
        )
    finally:
        write(evidence_path() / "current-native-inventory.json", {**data, "collection_exit": code})
    require(code == 0 and not data["deselected"], "CURRENT_NATIVE_COLLECTION")


def cleanup(root):
    evidence = root / "evidence"
    if not (root / "owned.json").exists():
        if evidence.exists():
            write(evidence / "cleanup.json", {"outcome": "NOT_OWNED_NOT_TOUCHED"})
        return
    attempts = []
    if (evidence / "cleanup.json").exists():
        old = json.loads((evidence / "cleanup.json").read_text())
        attempts = old.get("attempts", [])
        if old.get("outcome") == "PASS":
            require(not any(inventory(root).values()), "RESOURCES_REAPPEARED")
            return
    owner = json.loads((root / "owned.json").read_text())
    require(
        owner
        == {"project": "asm-" + root.name, "run_id": os.environ["GITHUB_RUN_ID"], "attempt": 1},
        "CLEANUP_OWNERSHIP",
    )
    try:
        # A cancelled docker-run client need not have stopped its container.
        # Its cidfile and exact run/project labels bind this cleanup authority.
        for cidfile in sorted((root / "private").glob("*.cid")):
            cid = cidfile.read_text().strip()
            require(re.fullmatch(r"[0-9a-f]{64}", cid), "NATIVE_CLEANUP_ID")
            if capture(DOCKER + ["ps", "-aq", "--filter", "id=" + cid]):
                labels = json.loads(
                    capture(DOCKER + ["inspect", "--format", "{{json .Config.Labels}}", cid])
                )
                require(
                    all(
                        labels.get(k) == v
                        for k, v in {
                            "com.docker.compose.project": "asm-" + root.name,
                            "asm.m4.run": os.environ["GITHUB_RUN_ID"],
                            "asm.m4.attempt": "1",
                        }.items()
                    ),
                    "NATIVE_CLEANUP_OWNERSHIP",
                )
                phase(root, "native-cleanup-" + cidfile.stem, DOCKER + ["rm", "-f", cid], 30)
        phase(
            root,
            "cleanup-command-" + str(len(attempts) + 1),
            compose(root)
            + ["down", "--volumes", "--remove-orphans", "--rmi", "local", "--timeout", "10"],
            60,
        )
        remaining = inventory(root)
        require(not any(remaining.values()), "CLEANUP_INCOMPLETE")
        attempts.append({"outcome": "PASS", "remaining": remaining})
        write(evidence / "cleanup.json", {"outcome": "PASS", "attempts": attempts})
        shutil.rmtree(root / "private")
    except Exception as error:
        attempts.append({"outcome": "FAIL", **failure_details(error)})
        write(evidence / "cleanup.json", {"outcome": "FAIL", "attempts": attempts})
        raise


def run(root):
    # Each complete module owns a fresh cluster. In particular, used 0014/0015
    # downgrade guards are observed before destruction, never bypassed by row reset.
    require(not root.exists(), "RUN_ALREADY_STARTED")
    (root / "evidence").mkdir(parents=True, mode=0o700)
    (root / "private").mkdir(mode=0o700)
    event, manifest = admit_source(root / "evidence")
    mode = "targeted" if event["ref"] == "refs/heads/" + TARGETED_BRANCH else "runtime"
    write(root / "evidence/mode.json", {"mode": mode})
    # This finite extension is selected only after exact source admission. No
    # environment/CLI override, and the historical/targeted routes remain 600s.
    sql_test_budget_seconds = (
        900
        if mode == "runtime"
        and (
            m6_pricing_event(event)
            or m6_assessment_event(event)
            or m6_request_event(event)
            or m6_plan_event(event)
            or v7_fix_event(event)
            or intake_event(event)
            or delivery_event(event)
            or foundation_budget_event(event)
            or portfolio_event(event)
            or search_event(event)
            or capability_event(event)
            or knowledge_event(event)
        )
        else 600
    )
    run_admitted(root, event, manifest, mode, sql_test_budget_seconds=sql_test_budget_seconds)


def run_admitted(root, event, manifest, mode, *, sql_test_budget_seconds=600):
    # No resource access or credentials before the complete source admission.
    require(mode in {"targeted", "runtime"}, "R5_MODE")
    modules = ["preflight", *MODULES]
    planned = dict(zip(MODULES[:3], (35, 22, 9), strict=True)) | {m: 0 for m in MODULES[3:]}
    native_nodes = CURRENT_NATIVE_NODES if mode == "targeted" else []
    if mode == "targeted":
        modules.append(CURRENT_NATIVE_MODULE)
        planned[CURRENT_NATIVE_MODULE] = len(native_nodes)
    pins = dict(
        line.split("=", 1) for line in Path("infra/images.lock.env").read_text().splitlines()
    )
    require(pins["DB_IMAGE"] == DB_IMAGE, "DB_IMAGE_PIN")
    planning = event.get("head_ref") == M5_PLAN_BRANCH
    m6_pricing = m6_pricing_event(event)
    m6_assessment = not m6_pricing and m6_assessment_event(event)
    m6_request = not (m6_pricing or m6_assessment) and m6_request_event(event)
    m6_slice = m6_pricing or m6_assessment or m6_request
    m6_plan = not m6_slice and m6_plan_event(event)
    v7_fix = not (m6_slice or m6_plan) and v7_fix_event(event)
    intake = not (m6_slice or m6_plan or v7_fix) and intake_event(event)
    intake_carrier = intake or v7_fix or m6_plan or m6_slice
    delivery = not intake_carrier and delivery_event(event)
    foundation_budget = not (intake_carrier or delivery) and foundation_budget_event(event)
    portfolio = not (intake_carrier or delivery or foundation_budget) and portfolio_event(event)
    search = not (intake_carrier or delivery or foundation_budget or portfolio) and search_event(
        event
    )
    capability = not (
        intake_carrier or delivery or foundation_budget or portfolio or search
    ) and capability_event(event)
    knowledge = not (
        intake_carrier or delivery or foundation_budget or portfolio or search or capability
    ) and knowledge_event(event)
    configuration = not (
        intake_carrier
        or delivery
        or foundation_budget
        or portfolio
        or search
        or capability
        or knowledge
    ) and configuration_event(event)
    require(
        sql_test_budget_seconds == 600
        or sql_test_budget_seconds == 900
        and mode == "runtime"
        and (
            intake_carrier
            or delivery
            or foundation_budget
            or portfolio
            or search
            or knowledge
            or capability
        ),
        "SQL_TEST_BUDGET_ADMISSION",
    )
    base, base_tree = (
        (M6_PRICING_BASE, M6_PRICING_TREE)
        if m6_pricing
        else (M6_ASSESSMENT_BASE, M6_ASSESSMENT_TREE)
        if m6_assessment
        else (M6_REQUEST_BASE, M6_REQUEST_TREE)
        if m6_request
        else (M6_PLAN_BASE, M6_PLAN_TREE)
        if m6_plan
        else (M5_V7_FIX_BASE, M5_V7_FIX_TREE)
        if v7_fix
        else (M5_INTAKE_BASE, M5_INTAKE_TREE)
        if intake
        else (M5_DELIVERY_BASE, M5_DELIVERY_TREE)
        if delivery
        else (M5_FOUNDATION_BASE, M5_FOUNDATION_TREE)
        if foundation_budget
        else (M5_PORTFOLIO_BASE, M5_PORTFOLIO_TREE)
        if portfolio
        else (M5_SEARCH_BASE, M5_SEARCH_TREE)
        if search
        else (M5_CAPABILITY_BASE, M5_CAPABILITY_TREE)
        if capability
        else (M5_KNOWLEDGE_BASE, M5_KNOWLEDGE_TREE)
        if knowledge
        else (M5_CONFIGURATION_BASE, M5_CONFIGURATION_TREE)
        if configuration
        else (M5_PLAN_BASE, M5_PLAN_TREE)
        if planning
        else (BASE, BASE_TREE)
    )
    require(capture(["git", "rev-parse", base + "^{tree}"]) == base_tree, "BASE_TREE")
    require(not Path(".env").exists(), "UNEXPECTED_ENV_FILE")
    source = {
        "base": base,
        "base_tree": base_tree,
        "source": os.environ["GITHUB_SHA"],
        "tree": capture(["git", "rev-parse", "HEAD^{tree}"]),
        "paths": capture(["git", "diff", "--name-only", base, "HEAD"]).splitlines(),
        "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": 1,
        "event": os.environ["GITHUB_EVENT_NAME"],
        "branch": event.get("head_ref")
        or (
            event["ref"][11:]
            if event["ref"] != "refs/heads/main"
            else M6_PRICING_BRANCH
            if m6_pricing
            else M6_ASSESSMENT_BRANCH
            if m6_assessment
            else M6_REQUEST_BRANCH
            if m6_request
            else M6_PLAN_BRANCH
            if m6_plan
            else M5_V7_FIX_BRANCH
            if v7_fix
            else M5_INTAKE_BRANCH
            if intake
            else M5_DELIVERY_BRANCH
            if delivery
            else M5_FOUNDATION_BRANCH
            if foundation_budget
            else M5_PORTFOLIO_BRANCH
            if portfolio
            else M5_SEARCH_BRANCH
            if search
            else M5_CAPABILITY_BRANCH
            if capability
            else M5_KNOWLEDGE_BRANCH
            if knowledge
            else M5_CONFIGURATION_BRANCH
            if configuration
            else BRANCH
        ),
        "pins": pins,
        "uv_lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
    }
    if m6_pricing:
        source["m6_pricing_assignment"] = m6_pricing_assignment_proof()
        source["m6_pricing_candidate"] = m6_pricing_candidate(event)
    if m6_assessment:
        source["m6_assessment_assignment"] = m6_assessment_assignment_proof()
        source["m6_assessment_candidate"] = m6_assessment_candidate(event)
    if m6_request:
        source["m6_request_assignment"] = m6_request_assignment_proof()
        source["m6_request_candidate"] = m6_request_candidate(event)
    if m6_plan:
        source["m6_plan_candidate"] = m6_plan_candidate(event)
    if v7_fix:
        source["v7_fix_assignment"] = v7_fix_assignment_proof()
        source["v7_fix_candidate"] = v7_fix_candidate(event)
    if intake:
        source["intake_assignment"] = intake_assignment_proof()
        source["intake_scope_amendment"] = intake_scope_amendment_proof()
    if delivery:
        source["scope_amendment"] = delivery_scope_amendment()
        source["scope_amendment_02"] = delivery_scope_amendment_02()
    write(root / "evidence/source.json", source)
    write(root / "evidence/event.json", event)
    write(root / "evidence/source-manifest.json", manifest)
    subprocess.run(
        ["git", "archive", "--format=tar.gz", "-o", str(root / "evidence/source.tar.gz"), "HEAD"],
        check=True,
    )
    outcomes, all_nodes, collected_nodes = [], list(native_nodes), []
    test_seconds = sql_test_seconds = 0.0

    def inventory_record():
        return {
            "mode": mode,
            "planned_cases_by_module": planned,
            "expected_cases": sum(planned.values()),
            "nodeids": all_nodes,
            "inventory_complete": len(all_nodes) == sum(planned.values()),
            "unknown_inventory_cases": sum(planned.values()) - len(all_nodes),
            "collected_nodeids": collected_nodes,
            "collected_cases": len(collected_nodes),
            "collection_complete": len(collected_nodes) == sum(planned.values()),
        }

    write(root / "evidence/inventory.json", inventory_record())

    def sql_phase(group, name, command, cap):
        nonlocal sql_test_seconds, test_seconds
        require(sql_test_seconds < sql_test_budget_seconds, "TOTAL_SQL_TEST_BUDGET_EXHAUSTED")
        start = time.monotonic()
        try:
            phase(group, name, command, min(cap, sql_test_budget_seconds - sql_test_seconds))
        finally:
            elapsed = time.monotonic() - start
            sql_test_seconds += elapsed
            if name == COMMAND_REPORT:
                test_seconds += elapsed
        require(sql_test_seconds <= sql_test_budget_seconds, "TOTAL_SQL_TEST_BUDGET_EXHAUSTED")

    for index, module in enumerate(modules):
        group = root / (root.name + "-group-" + str(index))
        (group / "evidence").mkdir(parents=True, mode=0o700)
        (group / "private").mkdir(mode=0o700)
        write(group / "evidence/source.json", source)
        nodes = (
            [] if module == "preflight" else [n for n in all_nodes if n.startswith(module + "::")]
        )
        write(group / "evidence/inventory.json", {"nodeids": nodes})
        result = {"module": module, "outcome": "NOT_REACHED"}
        try:
            require(not any(inventory(group).values()), "RESOURCE_NAME_CONFLICT")
            credentials = {
                name: secrets.token_hex(24)
                for name in (
                    "PG_ADMIN_PASSWORD",
                    "PG_MIGRATION_PASSWORD",
                    "PG_RUNTIME_PASSWORD",
                    "STORAGE_ROOT_USER",
                    "STORAGE_ROOT_PASSWORD",
                    "STORAGE_ACCESS_KEY",
                    "STORAGE_SECRET_KEY",
                )
            }
            (group / "private/test.env").write_text(
                "".join(k + "=" + v + "\n" for k, v in credentials.items())
            )
            write(
                group / "owned.json",
                {
                    "project": "asm-" + group.name,
                    "run_id": os.environ["GITHUB_RUN_ID"],
                    "attempt": 1,
                },
            )
            phase(group, "build", compose(group) + ["build", "checks"], 420)
            if module == "preflight":
                phase(
                    group,
                    "inventory",
                    checks(
                        group,
                        "python",
                        "scripts/native_context_db_catalog.py",
                        "collect-m4",
                        "--inventory",
                        "/evidence/all-m4.json",
                    ),
                    90,
                )
                expected = json.loads((group / "evidence/all-m4.json").read_text())
                require(
                    expected["collection_exit"] == 0 and not expected["deselected"],
                    "INVENTORY_FAILED",
                )
                m4_nodes = expected["nodeids"]
                require(
                    {n.split("::", 1)[0] for n in m4_nodes} == set(MODULES), "INVENTORY_MODULES"
                )
                require(
                    all(
                        sum(n.startswith(m + "::") for n in m4_nodes) == planned[m]
                        for m in MODULES[:3]
                    ),
                    "RETAINED_CASES_LOST",
                )
                for carrier_module in MODULES[3:]:
                    planned[carrier_module] = sum(
                        n.startswith(carrier_module + "::") for n in m4_nodes
                    )
                    require(planned[carrier_module] > 0, "PROVIDER_CASES_EMPTY")
                planned_nodes = [*m4_nodes, *native_nodes]
                require(len(planned_nodes) == len(set(planned_nodes)), "INVENTORY_DUPLICATE")
                all_nodes = planned_nodes
                collected_nodes = list(m4_nodes)
                write(root / "evidence/inventory.json", inventory_record())
                if mode == "targeted":
                    phase(
                        group,
                        "current-native-inventory",
                        checks(
                            group, "python", "scripts/m4_runtime_db.py", "collect-current-native"
                        ),
                        60,
                    )
                    native = json.loads(
                        (group / "evidence/current-native-inventory.json").read_text()
                    )
                    require(
                        native["collection_exit"] == 0
                        and not native["deselected"]
                        and native["nodeids"] == CURRENT_NATIVE_NODES,
                        "CURRENT_NATIVE_SELECTION",
                    )
                    collected_nodes.extend(native["nodeids"])
                write(root / "evidence/inventory.json", inventory_record())
            phase(
                group,
                "database-start",
                compose(group) + ["up", "-d", "--wait", "--wait-timeout", "80", "postgres-test"],
                120,
            )
            identity = capture(compose(group) + ["ps", "-q", "postgres-test"])
            status = capture(DOCKER + ["exec", identity, "cat", "/proc/1/status"])
            uid = int(
                next(line.split()[1] for line in status.splitlines() if line.startswith("Uid:"))
            )
            image_id = capture(DOCKER + ["inspect", "--format", "{{.Image}}", identity])
            require(
                uid != 0
                and image_id
                == capture(DOCKER + ["image", "inspect", "--format", "{{.Id}}", DB_IMAGE]),
                "SERVER_IDENTITY",
            )
            write(
                group / "evidence/server-process.json",
                {"uid": uid, "image_id": image_id, "pin": DB_IMAGE, "container_id": identity},
            )
            if module == "preflight":
                current_revision = (
                    "0027"
                    if m6_pricing
                    else "0026"
                    if m6_assessment
                    else "0025"
                    if m6_request
                    else "0024"
                    if m6_plan or v7_fix
                    else "0023"
                    if intake
                    else "0022"
                    if delivery
                    else "0021"
                )
                sql_phase(
                    group,
                    "schema-" + current_revision,
                    checks(group, "alembic", "upgrade", current_revision),
                    120,
                )
                sql_phase(
                    group,
                    "catalog-" + current_revision,
                    checks(group, "python", "scripts/m4_runtime_db.py", "catalog-snapshot"),
                    60,
                )
                sql_phase(
                    group,
                    "readiness",
                    checks(group, "python", "scripts/m4_runtime_db.py", "readiness"),
                    30,
                )
            else:
                require(bool(nodes), "EMPTY_MODULE_INVENTORY")
                if module == CURRENT_NATIVE_MODULE:
                    sql_phase(
                        group,
                        "native-owner",
                        current_native_checks(
                            group,
                            "native-owner",
                            "python",
                            "scripts/m4_runtime_db.py",
                            "native-owner",
                        ),
                        30,
                    )
                else:
                    sql_phase(group, "schema", checks(group, "alembic", "upgrade", "0014"), 120)
                    sql_phase(
                        group,
                        "versions",
                        checks(group, "python", "scripts/m4_runtime_db.py", "versions"),
                        30,
                    )
                arguments = [
                    "pytest",
                    "-p",
                    "scripts.m4_runtime_db",
                    "-q",
                    "--tb=short",
                    "--show-capture=no",
                    "-p",
                    "no:cacheprovider",
                    "--junitxml=/evidence/junit.xml",
                ]
                command = (
                    current_native_checks(group, "native-tests", *arguments, *nodes)
                    if module == CURRENT_NATIVE_MODULE
                    else checks(group, *arguments, module, plugin=True)
                )
                sql_phase(group, COMMAND_REPORT, command, 600)
                summary = json.loads((group / "evidence" / SUMMARY_REPORT).read_text())
                require(
                    summary["result"] == "PASS" and summary["complete"],
                    "RUNTIME_EVIDENCE_INCOMPLETE",
                )
                if module == CURRENT_NATIVE_MODULE:
                    proofs = json.loads((group / "evidence/before-reset-proofs.json").read_text())
                    require(
                        len(proofs) == len(CURRENT_NATIVE_NODES),
                        "CURRENT_NATIVE_RESET_COMPLETENESS",
                    )
                    identities = json.loads(
                        (group / "evidence/native-identity-proofs.json").read_text()
                    )
                    require(
                        len(identities) == len(CURRENT_NATIVE_NODES),
                        "CURRENT_NATIVE_IDENTITY_COMPLETENESS",
                    )
            result["outcome"] = "PASS"
        except Exception as error:
            result.update(outcome="FAIL", **failure_details(error))
            active_phase = group / "evidence/phases/active.json"
            if active_phase.exists():
                result["last_phase"] = json.loads(active_phase.read_text())["phase"]
        finally:
            if module != "preflight":
                cases_path = group / "evidence/cases.json"
                summary_path = group / "evidence" / SUMMARY_REPORT
                if not summary_path.exists():
                    cases = json.loads(cases_path.read_text()) if cases_path.exists() else []
                    write(summary_path, summarize(cases, nodes, None))
                result["tests"] = json.loads(summary_path.read_text())
            write(group / "evidence/primary.json", result)
            try:
                cleanup(group)
            except Exception as error:
                result.update(outcome="FAIL", cleanup=failure_details(error))
            outcomes.append(result)
            completed = {n for v in outcomes for n in v.get("tests", {}).get("completed", [])}
            started = {
                n
                for v in outcomes
                for n in v.get("tests", {}).get("completed", [])
                + v.get("tests", {}).get("active", [])
            }
            called = {n for v in outcomes for n in v.get("tests", {}).get("call_reached", [])}
            write(root / "evidence/inventory.json", inventory_record())
            write(
                root / "evidence/summary.json",
                {
                    "groups": outcomes,
                    "test_seconds": test_seconds,
                    "sql_test_seconds": sql_test_seconds,
                    "sql_test_budget_seconds": sql_test_budget_seconds,
                    "groups_visited": len(outcomes),
                    "groups_expected": modules,
                    "not_reached_modules": modules[len(outcomes) :],
                    "planned_cases_by_module": planned,
                    "expected_cases": sum(planned.values()),
                    "inventory_complete": len(all_nodes) == sum(planned.values()),
                    "unknown_inventory_cases": sum(planned.values()) - len(all_nodes),
                    "collected_cases": len(collected_nodes),
                    "collection_complete": len(collected_nodes) == sum(planned.values()),
                    "missing_count": sum(planned.values()) - len(completed),
                    "not_reached_count": sum(planned.values()) - len(started),
                    "missing_call_phase_count": sum(planned.values()) - len(called),
                    "missing_call_phases": [n for n in all_nodes if n not in called],
                    "missing": [n for n in all_nodes if n not in completed],
                    "not_reached": [n for n in all_nodes if n not in started],
                    "complete": len(outcomes) == len(modules)
                    and all(
                        v.get("tests", {}).get(
                            "complete", v["module"] == "preflight" and v["outcome"] == "PASS"
                        )
                        for v in outcomes
                    ),
                    "result": "PASS"
                    if len(outcomes) == len(modules)
                    and all(v["outcome"] == "PASS" for v in outcomes)
                    and sql_test_seconds <= sql_test_budget_seconds
                    else "FAIL",
                },
            )
            shutil.copytree(group / "evidence", root / "evidence" / group.name, dirs_exist_ok=True)
        # A failed prerequisite cannot authorize destructive runtime fixtures.
        # Other test modules still report their independent outcomes within budget.
        if (
            module == "preflight"
            and result["outcome"] != "PASS"
            or sql_test_seconds >= sql_test_budget_seconds
        ):
            break
    clean = not capture(["git", "status", "--porcelain", "--untracked-files=all"])
    write(root / "evidence/source-preservation.json", {"clean": clean})
    require(clean, "SOURCE_CHANGED")
    require(
        len(outcomes) == len(modules)
        and all(v["outcome"] == "PASS" for v in outcomes)
        and sql_test_seconds <= sql_test_budget_seconds,
        "PRIMARY_FAILED",
    )


def main():
    os.umask(0o077)
    if sys.argv[1:] == ["collect-current-native"]:
        collect_current_native()
        return
    if sys.argv[1:] == ["native-owner"]:
        write(evidence_path() / "native-owner.json", native_identity())
        return
    if sys.argv[1:] == ["readiness"]:
        asyncio.run(readiness())
        return
    if sys.argv[1:] == ["catalog-snapshot"]:
        stock_catalog()
        return
    if sys.argv[1:] == ["versions"]:
        versions()
        return
    require(sys.argv[1:] in (["run"], ["cleanup"]), "USAGE")
    root = root_path()
    if sys.argv[1] == "run":
        run(root)
    else:
        try:
            for group in sorted(root.glob("*-group-*")):
                cleanup(group)
                shutil.copytree(
                    group / "evidence", root / "evidence" / group.name, dirs_exist_ok=True
                )
        finally:
            if (root / "evidence").exists():
                files = {
                    str(p.relative_to(root / "evidence")): {
                        "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in (root / "evidence").rglob("*")
                    if p.is_file() and p.name != "manifest.json"
                }
                write(root / "evidence/manifest.json", files)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        main()
    except Exception as error:
        code = str(error)
        print(
            "M4_PG_STOP="
            + (code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else type(error).__name__)
        )
        raise SystemExit(1) from None
