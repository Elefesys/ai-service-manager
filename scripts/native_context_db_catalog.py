"""Bounded, disposable stock DB lane; no application readiness attestation.

The source manifest is expanded from every migration, independently of the
installed profile capability. Installed catalog SQL below is maintained here,
not obtained from that capability. No DB driver is imported for unit checks or
ownership-only cleanup. Private credentials and raw logs never enter evidence/.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
NONFUNCTION_SHA256 = "57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370"
EXECUTION_REF = "refs/heads/c0/m3-1-native-context-db-stock-r1"
REPOSITORY = "Elefesys/ai-service-manager"
REPOSITORY_ID = 1369650588
MODULES = (
    "tests/test_m3_1_native_context_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_api_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
)
# Only these complete destructive modules leave generic PG execution. Keep this
# independent of MODULES so dropping a carrier module cannot shrink the gate.
PG_MODULES = (
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_api_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
)
# Bind the actual inputs, including ten ordinary jobs (the two serial foundation
# boundaries plus the unchanged eight) and the unconditional native job: eleven.
# Preserve default merge/main checkout, unconditional same-commit reusable call, pinned
# owned lane and exact generic command. No fallback/embedded workflow is used.
CI_INPUT_SHA256 = {
    ".github/workflows/ci.yml": "3fa9fb80384d80cafeac55da9b5309feebca29c7999341eeed3ab1a964d56cbf",
    ".github/workflows/native-context-db.yml": "ff43d2470b56d26cf9c616cad5bc570e31634a19d97bdec4f28e73a205e049fd",
    "scripts/check_backend.sh": "1473e64b8ed0819b046b764f281072583271acd5f7b0929b3f8aa959c5d69330",
}
SECRET_ENV = (
    "ASM_NATIVE_TEST_ALLOW_RESET",
    "ASM_NATIVE_TEST_ADMIN_URL",
    "ASM_DATABASE_URL",
    "ASM_MIGRATION_DATABASE_URL",
)
PROFILE = "platform.human_context_schema_profile()"
ROOT = Path(__file__).resolve().parents[1]


class Refusal(RuntimeError):
    """Fail closed, including on source/ownership/catalog ambiguity."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


def redact(value, passwords=()):
    for password in passwords:
        value = value.replace(password, "[REDACTED]")
    # Also covers unexpected connection strings in SQLAlchemy/JUnit tracebacks.
    value = re.sub(r"(?:postgres(?:ql)?(?:\+\w+)?://)[^\s<>\"']+", "[DB_URL]", value)
    return re.sub(r"(?i)(password\s*[=:]\s*)[^\s,;\"']+", r"\1[REDACTED]", value)


def split_sql(value, separator=";"):
    """Strict lexical split outside comments, quotes, dollar bodies and parens."""
    i = start = depth = 0
    while i < len(value):
        if value.startswith("--", i):
            end = value.find("\n", i)
            i = len(value) if end < 0 else end + 1
            continue
        if value.startswith("/*", i):
            level = 1
            i += 2
            while level:
                require(i < len(value), "Unclosed SQL comment")
                if value.startswith("/*", i):
                    level += 1
                    i += 2
                elif value.startswith("*/", i):
                    level -= 1
                    i += 2
                else:
                    i += 1
            continue
        if value[i] in "'\"":
            quote = value[i]
            i += 1
            while True:
                require(i < len(value), "Unclosed SQL quote")
                char = value[i]
                i += 1
                if char == quote:
                    if i < len(value) and value[i] == quote:
                        i += 1
                    else:
                        break
            continue
        tag = re.match(r"\$(?:[a-zA-Z_][a-zA-Z_0-9]*)?\$", value[i:])
        if tag:
            end = value.find(tag[0], i + len(tag[0]))
            require(end >= 0, "Unclosed SQL dollar body")
            i = end + len(tag[0])
            continue
        if value[i] == "(":
            depth += 1
        elif value[i] == ")":
            depth -= 1
            require(depth >= 0, "Unexpected SQL closing parenthesis")
        if value[i] == separator and depth == 0:
            if value[start:i].strip():
                yield value[start:i].strip()
            start = i + 1
        i += 1
    require(depth == 0, "Unclosed SQL parenthesis")
    if value[start:].strip():
        yield value[start:].strip()


def leading_comments(value):
    # Never strip/normalize comments or whitespace inside executable bodies.
    return re.sub(r"\A(?:\s*--[^\n]*(?:\n|$))+", "", value).strip()


def canonical(value):
    value = value.replace("timestamp with time zone", "timestamptz")
    return re.sub(r"\s*([(),])\s*", r"\1", value.strip())


TYPE = r"(?:[a-z_][a-z_0-9]*\.)?[a-z_][a-z_0-9]*(?:\[\])?"
NAME = r"(?:app|platform)\.[a-z_][a-z_0-9]*"


def parse_function(sql):
    match = re.fullmatch(
        rf"CREATE (?:OR REPLACE )?FUNCTION ({NAME})\((.*?)\)\s+RETURNS (.*?)\s+"
        r"LANGUAGE (sql|plpgsql)\s+(.*?)\bSET search_path\s*=\s*pg_catalog,\s*pg_temp\s+"
        r"AS (\$(?:[a-zA-Z_][a-zA-Z_0-9]*)?\$)(.*?)\6",
        sql,
        re.S,
    )
    require(match is not None, "Unsupported function declaration: " + sql[:120])
    name, arguments, returns, language, options, _, body = match.groups()
    option_tokens = options.replace("SECURITY DEFINER", "DEFINER").split()
    require(
        set(option_tokens) <= {"DEFINER", "STABLE", "VOLATILE", "IMMUTABLE", "STRICT"}
        and len(option_tokens) == len(set(option_tokens))
        and len(set(option_tokens) & {"STABLE", "VOLATILE", "IMMUTABLE"}) <= 1,
        "Unknown/duplicate function options",
    )
    names, types, defaults = [], [], []
    for argument in split_sql(arguments, ","):
        arg = re.fullmatch(rf"([a-z_][a-z_0-9]*)\s+({TYPE})(?:\s+DEFAULT (false))?", argument)
        require(arg is not None, "Unsupported typed argument: " + argument)
        names.append(arg[1])
        types.append(arg[2])
        if arg[3]:
            defaults.append(arg[3])
        else:
            require(not defaults, "Non-trailing argument default")
    output_names, output_types = [], []
    table = re.fullmatch(r"TABLE\((.*)\)", returns, re.S)
    if table:
        for column in split_sql(table[1], ","):
            arg = re.fullmatch(rf"([a-z_][a-z_0-9]*)\s+({TYPE})", column)
            require(arg is not None, "Unsupported table return column")
            output_names.append(arg[1])
            output_types.append(arg[2])
        require(len(output_names) > 1, "Unreviewed single-column TABLE result")
    else:
        require(re.fullmatch(TYPE, returns) is not None, "Unsupported function result")
    return {
        "signature": name + "(" + ",".join(types) + ")",
        "input_types": types,
        "argnames": names + output_names,
        "all_types": types + output_types if table else None,
        "argmodes": ["i"] * len(types) + ["t"] * len(output_types) if table else None,
        "defaults": ", ".join(defaults) or None,
        "return_type": "record" if table else returns,
        "returns_set": bool(table),
        "language": language,
        "security_definer": "DEFINER" in option_tokens,
        "strict": "STRICT" in option_tokens,
        "volatility": "s"
        if "STABLE" in option_tokens
        else "i"
        if "IMMUTABLE" in option_tokens
        else "v",
        "proconfig": ["search_path=pg_catalog, pg_temp"],
        "owner": "asm_migrator",
        "body": body,
        "body_sha256": sha256(body.encode()),
        "definition": sql,
    }


def capture_source(root):
    """Expand the actual chain without importing/mutating the real Alembic module."""
    paths = sorted((root / "migrations/versions").glob("*.py"))
    require(
        [p.name[:4] for p in paths] == [f"{n:04d}" for n in range(1, 14)],
        "Unexpected migration chain",
    )
    commands, modules = [], {}
    for number, path in enumerate(paths, 1):
        operations = []
        tree = ast.parse(path.read_text())
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                require(
                    node.module == "alembic"
                    and len(node.names) == 1
                    and node.names[0].name == "op"
                    and node.names[0].asname is None,
                    "Unsupported migration import",
                )
                continue
            if isinstance(node, ast.Import):
                require(
                    all(n.name in {"hashlib", "re"} and n.asname is None for n in node.names),
                    "Unsupported migration import",
                )
            elif isinstance(node, ast.For):
                require(
                    ast.dump(node)
                    == ast.dump(
                        ast.parse(
                            "for _table, _columns in COLUMN_DELTA.items():\n    NATIVE_COLUMNS[_table] = NATIVE_COLUMNS.get(_table, ()) + _columns"
                        ).body[0]
                    ),
                    "Unsupported source inventory loop",
                )
            elif isinstance(node, ast.Assert):
                require(
                    ast.dump(node)
                    == ast.dump(ast.parse("assert len(NATIVE_COLUMNS) == 45").body[0]),
                    "Unsupported source assertion",
                )
            else:
                require(
                    isinstance(node, (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.Expr)),
                    "Unsupported migration AST",
                )
                if isinstance(node, ast.Expr):
                    require(
                        isinstance(node.value, ast.Constant) and isinstance(node.value.value, str),
                        "Unsupported top-level expression",
                    )
            nodes.append(node)
        namespace = {"op": SimpleNamespace(execute=operations.append)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        revision = f"{number:04d}"
        require(
            namespace["revision"] == revision
            and namespace["down_revision"] == (f"{number - 1:04d}" if number > 1 else None),
            "Migration predecessor mismatch",
        )
        namespace["upgrade"]()
        modules[revision] = namespace
        for index, sql in enumerate(operations):
            require(isinstance(sql, str), "Only expanded SQL strings are supported")
            commands.append({"revision": revision, "index": index, "sql": sql})
    return modules, commands


def source_catalog(root):
    modules, commands = capture_source(root)
    functions, baseline, runtime = {}, {}, set()
    # Alembic's locked version-table implementation, not a business table.
    columns = {"platform.alembic_version": ["version_num"]}
    ddl = []
    default_public = True
    public = {}
    for command in commands:
        revision = command["revision"]
        for value in split_sql(command["sql"]):
            sql = leading_comments(value)
            if sql.startswith(("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")):
                row = parse_function(sql)
                signature = row["signature"]
                functions[signature] = row
                public.setdefault(signature, default_public)
                continue
            ddl.append({**command, "sql": sql})
            if m := re.fullmatch(rf"CREATE TABLE ({NAME})\s*\((.*)\)", sql, re.S):
                require(m[1] not in columns, "Duplicate source table")
                cols = []
                for part in split_sql(m[2], ","):
                    part = leading_comments(part)
                    if part.startswith(
                        ("PRIMARY ", "UNIQUE", "FOREIGN ", "CONSTRAINT ", "CHECK", "EXCLUDE ")
                    ):
                        continue
                    col = re.fullmatch(r"([a-z_][a-z_0-9]*)\s+(.+)", part, re.S)
                    require(
                        col is not None and col[1] not in cols,
                        "Unsupported/duplicate source column",
                    )
                    cols.append(col[1])
                columns[m[1]] = cols
            elif m := re.fullmatch(rf"ALTER TABLE ({NAME})\s+(.*)", sql, re.S):
                require(m[1] in columns, "ALTER of unknown source table")
                for operation in split_sql(m[2], ","):
                    if col := re.fullmatch(
                        r"ADD COLUMN ([a-z_][a-z_0-9]*)\s+(.+)", operation, re.S
                    ):
                        require(col[1] not in columns[m[1]], "Duplicate added column")
                        columns[m[1]].append(col[1])
                    else:
                        require(
                            re.fullmatch(
                                r"(?:ADD CONSTRAINT \w+\s+.+|DROP CONSTRAINT \w+|ENABLE ROW LEVEL SECURITY|FORCE ROW LEVEL SECURITY|OWNER TO asm_migrator)",
                                operation,
                                re.S,
                            ),
                            "Unsupported ALTER TABLE operation",
                        )
            elif m := re.fullmatch(
                r"(GRANT|REVOKE) (EXECUTE|ALL(?: PRIVILEGES)?) ON FUNCTION (.*?) (?:TO|FROM) (.*)",
                sql,
                re.S,
            ):
                roles = m[4].replace(" ", "").split(",")
                require(set(roles) <= {"PUBLIC", "asm_runtime"}, "Unreviewed function grantee")
                for target in split_sql(m[3], ","):
                    sig = canonical(target)
                    require(sig in functions, "Grant/revoke on unknown function")
                    if "asm_runtime" in roles:
                        runtime.add(sig) if m[1] == "GRANT" else runtime.discard(sig)
                    if "PUBLIC" in roles:
                        public[sig] = m[1] == "GRANT"
            elif m := re.fullmatch(r"DROP FUNCTION (.*)", sql, re.S):
                for target in split_sql(m[1], ","):
                    sig = canonical(target)
                    require(sig in functions, "Drop of unknown function")
                    del functions[sig]
                    public.pop(sig)
                    runtime.discard(sig)
            elif (
                sql
                == "ALTER DEFAULT PRIVILEGES FOR ROLE asm_migrator IN SCHEMA app, platform REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
            ):
                default_public = False
            elif re.fullmatch(rf"ALTER FUNCTION ({NAME}\(.*\)) OWNER TO asm_migrator", sql, re.S):
                sig = canonical(
                    sql.removeprefix("ALTER FUNCTION ").removesuffix(" OWNER TO asm_migrator")
                )
                require(sig in functions, "Owner change on unknown function")
            else:
                # These bounded non-function forms are fingerprinted in full by
                # the independently queried, C0-frozen non-function catalog hash.
                patterns = (
                    rf"CREATE (?:UNIQUE )?INDEX \w+ ON {NAME}\s*.+",
                    rf"CREATE (?:CONSTRAINT )?TRIGGER \w+ (?:BEFORE|AFTER) .+ ON {NAME} .+",
                    rf"DROP TRIGGER \w+ ON {NAME}",
                    rf"CREATE POLICY \w+ ON {NAME} .+",
                    rf"CREATE SEQUENCE {NAME} AS bigint MINVALUE 1 NO CYCLE CACHE 1",
                    rf"LOCK TABLE (?:{NAME})(?:,\s*{NAME})* IN (?:ACCESS EXCLUSIVE|SHARE ROW EXCLUSIVE) MODE",
                    r"(?:GRANT|REVOKE) (?:USAGE|SELECT|INSERT|UPDATE|DELETE|ALL|,|\s)+ ON (?:SCHEMA |SEQUENCE )?[a-z_.,\s]+ (?:TO|FROM) (?:asm_runtime|PUBLIC)(?:,\s*(?:asm_runtime|PUBLIC))*",
                    r"DO (\$(?:check)?\$).+\1",
                    r"SELECT platform\.files_plan\(.+FROM app\.messages m WHERE m\.direction='INBOUND' AND m\.content_type='IMAGE_REFERENCE'",
                )
                require(
                    any(re.fullmatch(p, " ".join(sql.split()), re.S) for p in patterns),
                    "Unsupported source SQL: " + sql[:140],
                )
        if revision == "0012":
            baseline = dict(functions)
    additions = set(functions) - set(baseline)
    replacements = {s for s in baseline if functions[s]["body"] != baseline[s]["body"]}
    require(
        len(baseline) == 132
        and len(functions) == 167
        and len(additions) == 35
        and len(replacements) == 18,
        "Unexpected effective source inventory",
    )
    require(not any(public.values()), "Source leaves PUBLIC EXECUTE")
    require(
        columns == {t: list(c) for t, c in modules["0013"]["NATIVE_COLUMNS"].items()}
        and len(columns) == 45,
        "Independent source column replay differs",
    )
    for sig, row in functions.items():
        row["runtime_execute"] = sig in runtime
        # PG18 acldefault stores no owner grant-option bits; ownership supplies
        # those rights implicitly (postgres REL_18_STABLE, acl.c/acldefault).
        row["acl"] = [["asm_migrator", "asm_migrator", "EXECUTE", False]]
        if sig in runtime:
            row["acl"].append(["asm_migrator", "asm_runtime", "EXECUTE", False])
    return {
        "functions": functions,
        "columns": columns,
        "commands": commands,
        "nonfunction_ddl": ddl,
        "additions": sorted(additions),
        "replacements": sorted(replacements),
        "serialization": "Exact expanded source bodies (UTF-8); no body normalization. Installed PG jsonb::text is hashed separately.",
    }


# The query is deliberately independent of platform.human_context_schema_profile.
# Return *server serialized text*, not a Python reserialization of JSONB. OIDs
# are in a separate manifest so they never perturb the portable profile hash.
CATALOG_SQL = """
WITH rels AS MATERIALIZED (
 SELECT c.oid,n.nspname||'.'||c.relname AS name,c.relowner,c.relrowsecurity,c.relforcerowsecurity,c.relacl
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname IN ('app','platform') AND c.relkind='r'
), funcs AS MATERIALIZED (
 SELECT p.*,n.nspname,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 JOIN pg_language l ON l.oid=p.prolang
 WHERE n.nspname IN ('app','platform') AND p.prokind='f'
), inventory AS (
 SELECT jsonb_build_object(
 'functions',(SELECT jsonb_agg(jsonb_build_array(oid::regprocedure::text,pg_get_functiondef(oid),proacl::text,proowner::regrole::text) ORDER BY oid::regprocedure::text) FROM funcs),
 'columns',(SELECT jsonb_agg(jsonb_build_array(r.name,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)) ORDER BY r.name,a.attnum)
   FROM rels r JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON (d.adrelid,d.adnum)=(a.attrelid,a.attnum)),
 'constraints',(SELECT jsonb_agg(jsonb_build_array(r.name,k.conname,pg_get_constraintdef(k.oid),k.convalidated) ORDER BY r.name,k.conname) FROM rels r JOIN pg_constraint k ON k.conrelid=r.oid),
 'indices',(SELECT jsonb_agg(jsonb_build_array(schemaname,tablename,indexname,indexdef) ORDER BY schemaname,tablename,indexname) FROM pg_indexes WHERE schemaname IN ('app','platform')),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY schemaname,tablename,policyname) FROM pg_policies p WHERE schemaname IN ('app','platform')),
 'triggers',(SELECT jsonb_agg(jsonb_build_array(r.name,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled) ORDER BY r.name,t.tgname) FROM rels r JOIN pg_trigger t ON t.tgrelid=r.oid AND NOT t.tgisinternal),
 'relations',(SELECT jsonb_agg(jsonb_build_array(name,relowner::regrole::text,relrowsecurity,relforcerowsecurity,relacl::text) ORDER BY name) FROM rels),
 'sequences',(SELECT jsonb_agg(jsonb_build_array(n.nspname,c.relname,c.relowner::regrole::text,c.relacl::text,s.seqtypid::regtype::text,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle) ORDER BY n.nspname,c.relname)
   FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform')),
 'schemas',(SELECT jsonb_agg(jsonb_build_array(nspname,nspowner::regrole::text,nspacl::text) ORDER BY nspname) FROM pg_namespace WHERE nspname IN ('app','platform')),
 'extensions',(SELECT jsonb_agg(jsonb_build_array(e.extname,e.extversion,n.nspname) ORDER BY e.extname) FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname IN ('vector','btree_gist'))
 ) AS value
)
SELECT value::text,(value-'functions')::text FROM inventory
"""

FUNCTION_SQL = """
SELECT p.oid::bigint AS oid,p.oid::regprocedure::text AS signature,
 p.prosrc AS body,l.lanname AS language,p.prosecdef AS security_definer,
 p.provolatile::text AS volatility,p.proisstrict AS strict,
 p.proowner::regrole::text AS owner,p.proconfig,
 ARRAY(SELECT format_type(t,NULL) FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY a(t,k) ORDER BY k) AS input_types,
 p.proargnames AS argnames,
 CASE WHEN p.proallargtypes IS NULL THEN NULL ELSE
 ARRAY(SELECT format_type(t,NULL) FROM unnest(p.proallargtypes) WITH ORDINALITY a(t,k) ORDER BY k) END AS all_types,
 p.proargmodes::text[] AS argmodes,pg_get_expr(p.proargdefaults,0) AS defaults,
 format_type(p.prorettype,NULL) AS return_type,p.proretset AS returns_set,
 p.prokind::text AS kind,p.proleakproof AS leakproof,p.proparallel::text AS parallel,
 has_function_privilege('asm_runtime',p.oid,'EXECUTE') AS runtime_execute,
 (SELECT jsonb_agg(jsonb_build_array(a.grantor::regrole::text,
   CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE a.grantee::regrole::text END,
   a.privilege_type,a.is_grantable) ORDER BY a.grantee::regrole::text,a.privilege_type,a.grantor::regrole::text)
  FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a) AS acl
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
JOIN pg_language l ON l.oid=p.prolang
WHERE n.nspname IN ('app','platform')
ORDER BY p.oid::regprocedure::text
"""

ROLE_SQL = """
SELECT rolname AS name,rolcanlogin AS login,rolsuper AS superuser,rolbypassrls AS bypassrls,
 rolinherit AS inherit,rolcreaterole AS createrole,rolcreatedb AS createdb,rolreplication AS replication
FROM pg_roles WHERE rolname IN ('asm_runtime','asm_migrator') ORDER BY rolname
"""


def compare_roles(rows, memberships, owned_by_runtime):
    require(
        {r["name"] for r in rows} == {"asm_runtime", "asm_migrator"} and len(rows) == 2,
        "Missing/extra login roles",
    )
    for row in rows:
        require(
            row["login"] is True
            and not any(
                row[k] for k in ("superuser", "bypassrls", "createrole", "createdb", "replication")
            ),
            "Unsafe login role attributes",
        )
        require(
            row["inherit"] is (row["name"] == "asm_migrator"),
            "Unexpected runtime/migrator inheritance attributes",
        )
    require(not memberships, "Unexpected runtime/migrator role membership")
    require(not owned_by_runtime, "Runtime owns database/schema/relation/function")


def compare_functions(expected, rows, resolved):
    actual = {}
    for row in rows:
        signature = canonical(row["signature"])
        require(signature not in actual, "Duplicate installed signature")
        actual[signature] = row
    require(
        set(actual) == set(expected),
        "Missing/extra installed function: " + str(sorted(set(actual) ^ set(expected))),
    )
    oids = [r["oid"] for r in rows]
    require(
        len(set(oids)) == len(expected) and all(isinstance(oid, int) and oid > 0 for oid in oids),
        "Duplicate/unresolved installed OID",
    )
    require(set(resolved) == set(expected), "Incomplete signature resolution")
    for signature, source in expected.items():
        row = actual[signature]
        require(resolved[signature] == row["oid"], "Typed signature/OID mismatch: " + signature)
        require(row["body"] == source["body"], "Source body mismatch: " + signature)
        for key in ("input_types", "return_type", "all_types"):
            actual_value, expected_value = row[key], source[key]
            if isinstance(actual_value, list):
                actual_value = [canonical(x) for x in actual_value]
            elif actual_value is not None:
                actual_value = canonical(actual_value)
            require(actual_value == expected_value, "Function " + key + " drift: " + signature)
        for key in (
            "argnames",
            "argmodes",
            "defaults",
            "returns_set",
            "language",
            "security_definer",
            "strict",
            "volatility",
            "owner",
            "proconfig",
            "runtime_execute",
        ):
            # PostgreSQL stores NULL rather than [] for zero named arguments.
            value = row[key] or [] if key == "argnames" else row[key]
            require(value == source[key], "Function " + key + " drift: " + signature)
        require(sorted(row["acl"]) == sorted(source["acl"]), "Function ACL drift: " + signature)
        require(
            row["kind"] == "f" and row["leakproof"] is False and row["parallel"] == "u",
            "Unexpected function flags",
        )


def compare_snapshot(expected_columns, full_text, nonfunction_text):
    full, nonfunction = json.loads(full_text), json.loads(nonfunction_text)
    require(
        nonfunction == {k: v for k, v in full.items() if k != "functions"},
        "Incoherent catalog serialization",
    )
    actual_columns = {}
    for table, column, *_ in full["columns"]:
        actual_columns.setdefault(table, []).append(column)
    require(actual_columns == expected_columns, "Missing/extra/reordered table columns")
    require(
        sha256(nonfunction_text.encode("utf-8")) == NONFUNCTION_SHA256,
        "Non-function catalog drift (types/defaults/constraints/indices/RLS/ACL/policies/triggers/sequences/extensions)",
    )
    return sha256(b"asm:m3:native_schema:v1\n" + full_text.encode("utf-8"))


def compare_catalog(expected, rows, resolved, full_text, nonfunction_text, read_profile):
    compare_functions(expected["functions"], rows, resolved)
    full_hash = compare_snapshot(expected["columns"], full_text, nonfunction_text)
    declared = read_profile()
    require(
        declared == {"schema_revision": "0013", "valid": True, "profile_sha256": full_hash},
        "Declared profile differs from independent catalog",
    )
    return full_hash, declared


def exception_sqlstates(error):
    states, seen, pending = set(), set(), [error]
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        state = getattr(value, "sqlstate", None)
        if isinstance(state, str) and re.fullmatch(r"[0-9A-Z]{5}", state):
            states.add(state)
        pending.extend(getattr(value, key, None) for key in ("orig", "__cause__", "__context__"))
        pending.extend(getattr(value, "exceptions", ()))
    return sorted(states)


class Commands:
    def __init__(self, private, evidence, deadline, passwords=(), prefix="payload"):
        self.private, self.evidence = private, evidence
        self.deadline, self.passwords = deadline, passwords
        self.prefix = prefix
        self.number = 0

    def run(self, argv, *, env=None, check=True, limit=None, quiet=False):
        remaining = self.deadline - time.time()
        require(remaining > 0, "Whole-job payload budget exhausted")
        timeout = min(remaining, limit) if limit else remaining
        self.number += 1
        started = time.monotonic()
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate(timeout=3)
            if not quiet:
                (self.evidence / f"{self.prefix}-command-{self.number:03d}.log").write_text(
                    redact(output.decode(errors="replace"), self.passwords)
                )
            raise
        if not quiet:
            safe = redact(output.decode(errors="replace"), self.passwords)
            (self.evidence / f"{self.prefix}-command-{self.number:03d}.log").write_text(
                json.dumps(
                    {
                        "argv": argv,
                        "exit": process.returncode,
                        "seconds": time.monotonic() - started,
                    }
                )
                + "\n"
                + safe
            )
        require(
            not check or process.returncode == 0,
            f"Command {self.number} failed (exit {process.returncode}); see sanitized evidence",
        )
        return process.returncode, output

    def docker_json(self, *argv):
        # Full inspect, especially Config.Env, remains memory-only.
        _, raw = self.run(["docker", *argv], quiet=True, limit=10)
        result = json.loads(raw)
        require(isinstance(result, list) and len(result) == 1, "Ambiguous Docker identity")
        return result[0]


def git_bytes(root, *argv):
    return subprocess.check_output(["git", *argv], cwd=root, timeout=10, stderr=subprocess.PIPE)


def require_ci_inputs():
    for path, expected in CI_INPUT_SHA256.items():
        require(sha256((ROOT / path).read_bytes()) == expected, "CI gate input drift: " + path)


def event_operands(env, payload=None, *, head=None, tree=None, parents=None):
    """Bounded source operands only; malformed values, URLs and event text stay private."""
    sha_pattern = r"[0-9a-f]{40}"
    number_pattern = r"[1-9][0-9]{0,19}"
    branch_pattern = r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}"

    def safe(value, pattern):
        return value if isinstance(value, str) and re.fullmatch(pattern, value) else "INVALID"

    def number(value):
        return (
            value if type(value) is int and re.fullmatch(number_pattern, str(value)) else "INVALID"
        )

    def object_value(value):
        return value if isinstance(value, dict) else {}

    payload = object_value(payload)
    pr = object_value(payload.get("pull_request"))
    base, branch = object_value(pr.get("base")), object_value(pr.get("head"))
    repository = object_value(payload.get("repository"))
    base_repository = object_value(base.get("repo"))
    head_repository = object_value(branch.get("repo"))
    advisory = pr.get("merge_commit_sha")
    advisory_state = (
        "missing" if "merge_commit_sha" not in pr else "null" if advisory is None else "sha"
    )
    if advisory is not None and safe(advisory, sha_pattern) == "INVALID":
        advisory_state = "invalid"
    elif advisory is not None and safe(head, sha_pattern) != "INVALID":
        advisory_state = "current" if advisory == head else "stale"
    return {
        "actions": env.get("GITHUB_ACTIONS") == "true",
        "repository_matches": env.get("GITHUB_REPOSITORY") == REPOSITORY,
        "repository_id": safe(env.get("GITHUB_REPOSITORY_ID"), number_pattern),
        "payload_repository_matches": repository.get("full_name") == REPOSITORY,
        "payload_repository_id": number(repository.get("id")),
        "payload_repository_fork": repository.get("fork")
        if type(repository.get("fork")) is bool
        else "INVALID",
        "base_repository_matches": base_repository.get("full_name") == REPOSITORY,
        "base_repository_id": number(base_repository.get("id")),
        "base_repository_fork": base_repository.get("fork")
        if type(base_repository.get("fork")) is bool
        else "INVALID",
        "head_repository_matches": head_repository.get("full_name") == REPOSITORY,
        "head_repository_id": number(head_repository.get("id")),
        "head_repository_fork": head_repository.get("fork")
        if type(head_repository.get("fork")) is bool
        else "INVALID",
        "event": safe(
            env.get("GITHUB_EVENT_NAME"),
            r"push|pull_request|workflow_call|workflow_dispatch|pull_request_target|merge_group|schedule",
        ),
        "ref": safe(
            env.get("GITHUB_REF"),
            r"refs/(?:heads/" + branch_pattern + r"|pull/" + number_pattern + r"/(?:merge|head))",
        ),
        "run_id": safe(env.get("GITHUB_RUN_ID"), number_pattern),
        "attempt": safe(env.get("GITHUB_RUN_ATTEMPT"), number_pattern),
        "push_ref": safe(payload.get("ref"), r"refs/heads/" + branch_pattern),
        "push_after": safe(payload.get("after"), sha_pattern),
        "push_head_sha": safe(object_value(payload.get("head_commit")).get("id"), sha_pattern),
        "push_deleted": payload.get("deleted")
        if type(payload.get("deleted")) is bool
        else "INVALID",
        "push_base_ref_state": "null" if payload.get("base_ref") is None else "present",
        "event_sha": safe(env.get("GITHUB_SHA"), sha_pattern),
        "actual_head": safe(head, sha_pattern),
        "actual_tree": safe(tree, sha_pattern),
        "parent_count": len(parents) if isinstance(parents, list) else None,
        "actual_parents": [safe(p, sha_pattern) for p in parents[:3]]
        if isinstance(parents, list)
        else [],
        "parents_truncated": isinstance(parents, list) and len(parents) > 3,
        "pr_number": number(payload.get("number")),
        "pr_object_number": number(pr.get("number")),
        "pr_state": safe(pr.get("state"), r"open|closed"),
        "pr_merged": pr.get("merged") if type(pr.get("merged")) is bool else "INVALID",
        "action": safe(payload.get("action"), r"opened|reopened|synchronize|closed|edited"),
        "event_base_ref": safe(base.get("ref"), branch_pattern),
        "env_base_ref": safe(env.get("GITHUB_BASE_REF"), branch_pattern),
        "event_head_ref": safe(branch.get("ref"), branch_pattern),
        "env_head_ref": safe(env.get("GITHUB_HEAD_REF"), branch_pattern),
        "event_base_sha": safe(base.get("sha"), sha_pattern),
        "event_head_sha": safe(branch.get("sha"), sha_pattern),
        "advisory_merge_commit_sha_state": advisory_state,
        "advisory_merge_commit_sha": safe(advisory, sha_pattern) if advisory is not None else None,
    }


def event_identity(env, payload, head, tree, parents, *, diagnostic=None):
    """Test-source admission only; never deployment approval or process drain."""

    def check(condition, reason):
        if diagnostic is not None:
            diagnostic["predicate"] = reason
        require(condition, reason)

    check(isinstance(payload, dict), "EVENT_PAYLOAD_OBJECT")
    check(env.get("GITHUB_ACTIONS") == "true", "EVENT_ACTIONS_CONTEXT")
    check(env.get("GITHUB_REPOSITORY") == REPOSITORY, "EVENT_ENV_REPOSITORY")
    check(env.get("GITHUB_REPOSITORY_ID") == str(REPOSITORY_ID), "EVENT_ENV_REPOSITORY_ID")

    def repository(value, scope):
        check(isinstance(value, dict), scope + "_OBJECT")
        check(value.get("full_name") == REPOSITORY, scope + "_NAME")
        check(type(value.get("id")) is int and value["id"] == REPOSITORY_ID, scope + "_ID")
        check(value.get("fork") is False, scope + "_FORK")

    def commit(value, reason):
        check(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
            reason,
        )
        return value

    repository(payload.get("repository"), "EVENT_REPOSITORY")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(key)
        check(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value), "EVENT_" + key)
    commit(env.get("GITHUB_SHA"), "EVENT_SHA_FORMAT")
    commit(head, "EVENT_HEAD_FORMAT")
    check(env["GITHUB_SHA"] == head, "EVENT_SHA_HEAD_MISMATCH")
    commit(tree, "EVENT_TREE_FORMAT")
    identity = {
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "event": env.get("GITHUB_EVENT_NAME"),
        "ref": env.get("GITHUB_REF"),
        "run_id": env["GITHUB_RUN_ID"],
        "attempt": env["GITHUB_RUN_ATTEMPT"],
        "head": head,
        "tree": tree,
        "event_identity_is_c0_approval": False,
    }
    if identity["event"] == "push":
        check(identity["ref"] in (EXECUTION_REF, "refs/heads/main"), "EVENT_PUSH_ENV_REF")
        check(payload.get("ref") == identity["ref"], "EVENT_PUSH_PAYLOAD_REF")
        check(payload.get("deleted") is False, "EVENT_PUSH_DELETED")
        check(payload.get("base_ref") is None, "EVENT_PUSH_BASE_REF")
        check(not env.get("GITHUB_BASE_REF"), "EVENT_PUSH_ENV_BASE_REF")
        check(not env.get("GITHUB_HEAD_REF"), "EVENT_PUSH_ENV_HEAD_REF")
        check(commit(payload.get("after"), "EVENT_PUSH_AFTER_FORMAT") == head, "EVENT_PUSH_AFTER")
        check(isinstance(payload.get("head_commit"), dict), "EVENT_PUSH_HEAD_OBJECT")
        check(
            commit(payload["head_commit"].get("id"), "EVENT_PUSH_HEAD_FORMAT") == head,
            "EVENT_PUSH_HEAD",
        )
        identity["route"] = "stock-push" if identity["ref"] == EXECUTION_REF else "main-push"
    elif identity["event"] == "pull_request":
        pr = payload.get("pull_request")
        check(isinstance(pr, dict), "EVENT_PR_OBJECT")
        check(payload.get("action") in ("opened", "reopened", "synchronize"), "EVENT_PR_ACTION")
        check(type(payload.get("number")) is int and payload["number"] > 0, "EVENT_PR_NUMBER")
        check(
            type(pr.get("number")) is int and pr["number"] == payload["number"],
            "EVENT_PR_OBJECT_NUMBER",
        )
        check(pr.get("state") == "open", "EVENT_PR_STATE")
        check(pr.get("merged") is False, "EVENT_PR_MERGED")
        base, branch = pr.get("base"), pr.get("head")
        check(isinstance(base, dict), "EVENT_PR_BASE_OBJECT")
        check(isinstance(branch, dict), "EVENT_PR_HEAD_OBJECT")
        repository(base.get("repo"), "EVENT_PR_BASE_REPOSITORY")
        repository(branch.get("repo"), "EVENT_PR_HEAD_REPOSITORY")
        check(base.get("ref") == "main", "EVENT_PR_BASE_REF")
        check(env.get("GITHUB_BASE_REF") == base["ref"], "EVENT_PR_ENV_BASE_REF")
        check(
            isinstance(branch.get("ref"), str)
            and branch["ref"]
            and branch["ref"] == env.get("GITHUB_HEAD_REF"),
            "EVENT_PR_HEAD_REF",
        )
        check(identity["ref"] == f"refs/pull/{payload['number']}/merge", "EVENT_PR_MERGE_REF")
        base_sha = commit(base.get("sha"), "EVENT_PR_BASE_SHA_FORMAT")
        head_sha = commit(branch.get("sha"), "EVENT_PR_HEAD_SHA_FORMAT")
        check(
            isinstance(parents, list)
            and all(isinstance(p, str) and re.fullmatch(r"[0-9a-f]{40}", p) for p in parents),
            "EVENT_PR_PARENTS_FORMAT",
        )
        check(len(parents) == 2, "EVENT_PR_PARENT_COUNT")
        check(parents[0] == base_sha, "EVENT_PR_BASE_PARENT")
        check(parents[1] == head_sha, "EVENT_PR_HEAD_PARENT")
        check(head not in (base_sha, head_sha), "EVENT_PR_MERGE_DISTINCT")
        advisory = pr.get("merge_commit_sha")
        check(
            advisory is None
            or isinstance(advisory, str)
            and re.fullmatch(r"[0-9a-f]{40}", advisory),
            "EVENT_PR_ADVISORY_FORMAT",
        )
        # GITHUB_SHA/HEAD/raw ordered parents prove the actual merge. GitHub's
        # optional test-merge snapshot is computed asynchronously; retain it as
        # advisory metadata, never as the tested source or a substitute for it.
        advisory_state = (
            "missing"
            if "merge_commit_sha" not in pr
            else "null"
            if advisory is None
            else "current"
            if advisory == head
            else "stale"
        )
        identity.update(
            route="same-repository-pr-merge",
            pr_number=payload["number"],
            action=payload["action"],
            base_ref=base["ref"],
            head_ref=branch["ref"],
            base_sha=base_sha,
            head_sha=head_sha,
            merge_parents=parents,
            advisory_merge_commit_sha=advisory,
            advisory_merge_commit_sha_state=advisory_state,
        )
    else:
        check(False, "EVENT_UNSUPPORTED")
    return identity


def publish_event_diagnostic(evidence, diagnostic, refusal=None):
    if evidence is None:
        return
    try:
        write_json(
            Path(evidence) / ("event-admission-" + diagnostic["entrypoint"] + ".json"), diagnostic
        )
    except Exception:
        if refusal is not None:
            refusal.add_note("EVENT_DIAGNOSTIC_WRITE_FAILED")
            return
        error = Refusal("EVENT_DIAGNOSTIC_WRITE_FAILED")
        error.admission_diagnostic = {
            **diagnostic,
            "result": "REFUSED",
            "failure_reason": "EVENT_DIAGNOSTIC_WRITE_FAILED",
        }
        raise error from None


def admit_event(evidence=None, *, entrypoint="admission"):
    require(entrypoint in {"admission", "run", "cleanup", "carrier", "catalog"}, "EVENT_ENTRYPOINT")
    diagnostic = {
        "version": 1,
        "entrypoint": entrypoint,
        "result": "REFUSED",
        "predicate": "EVENT_PAYLOAD_READ",
        "failure_reason": None,
        "operands": event_operands(os.environ),
        "event_payload_sha256": None,
    }

    def unique_object(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            diagnostic["predicate"] = "EVENT_PAYLOAD_DUPLICATE_KEYS"
            raise Refusal("EVENT_PAYLOAD_DUPLICATE_KEYS")
        return value

    def invalid_constant(value):
        raise ValueError("Non-JSON constant")

    try:
        raw = Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()
        diagnostic["event_payload_sha256"] = sha256(raw)
        diagnostic["predicate"] = "EVENT_PAYLOAD_JSON"
        payload = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        diagnostic["operands"] = event_operands(os.environ, payload)
        diagnostic["predicate"] = "EVENT_CI_INPUTS"
        require_ci_inputs()
        diagnostic["predicate"] = "EVENT_HEAD_READ"
        head = git_bytes(ROOT, "rev-parse", "HEAD").decode().strip()
        diagnostic["operands"] = event_operands(os.environ, payload, head=head)
        diagnostic["predicate"] = "EVENT_COMMIT_HEADERS"
        # Raw headers retain both parents even at fetch-depth1, unlike rev-list.
        headers = (
            git_bytes(ROOT, "cat-file", "-p", "HEAD").decode().split("\n\n", 1)[0].splitlines()
        )
        trees = [row[5:] for row in headers if row.startswith("tree ")]
        parents = [row[7:] for row in headers if row.startswith("parent ")]
        diagnostic["operands"] = event_operands(
            os.environ,
            payload,
            head=head,
            tree=trees[0] if len(trees) == 1 else None,
            parents=parents,
        )
        for value, reason in (
            (os.environ.get("GITHUB_SHA"), "EVENT_SHA_FORMAT"),
            (head, "EVENT_HEAD_FORMAT"),
        ):
            diagnostic["predicate"] = reason
            require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), reason)
        diagnostic["predicate"] = "EVENT_SHA_HEAD_MISMATCH"
        require(head == os.environ["GITHUB_SHA"], "EVENT_SHA_HEAD_MISMATCH")
        diagnostic["predicate"] = "EVENT_SOURCE_VERIFY"
        tree, manifest = require_source(ROOT, os.environ.get("GITHUB_SHA", ""))
        diagnostic["predicate"] = "EVENT_HEAD_TREE"
        require(trees == [tree], "EVENT_HEAD_TREE")
        identity = event_identity(os.environ, payload, head, tree, parents, diagnostic=diagnostic)
        identity["event_payload_sha256"] = diagnostic["event_payload_sha256"]
    except Exception as error:
        diagnostic["failure_reason"] = diagnostic["predicate"]
        refusal = error if isinstance(error, Refusal) else Refusal(diagnostic["failure_reason"])
        refusal.admission_diagnostic = diagnostic
        publish_event_diagnostic(evidence, diagnostic, refusal)
        raise refusal from None
    diagnostic.update(result="PASS", predicate="EVENT_ADMITTED")
    publish_event_diagnostic(evidence, diagnostic)
    return identity, manifest


def require_source(root, expected_sha):
    require(
        re.fullmatch(r"[0-9a-f]{40}", expected_sha) is not None, "Invalid event source identity"
    )
    actual = git_bytes(root, "rev-parse", "HEAD").decode().strip()
    require(actual == expected_sha, "HEAD differs from event SHA; destructive operations refused")
    require(
        not git_bytes(root, "status", "--porcelain", "--untracked-files=all"),
        "Tracked/untracked source is dirty; destructive operations refused",
    )
    tree = git_bytes(root, "rev-parse", "HEAD^{tree}").decode().strip()
    manifest = []
    for entry in git_bytes(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t")
        mode, kind, blob = meta.decode().split()
        path = root / name.decode()
        require(
            kind == "blob"
            and mode in {"100644", "100755"}
            and path.is_file()
            and not path.is_symlink(),
            "Unsupported source entry",
        )
        raw = path.read_bytes()
        actual_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(
            actual_blob == blob and bool(path.stat().st_mode & 0o111) == (mode == "100755"),
            "Tracked source bytes/mode differ: " + name.decode(),
        )
        manifest.append(
            {
                "path": name.decode(),
                "mode": mode,
                "blob": blob,
                "sha256": sha256(raw),
                "bytes": len(raw),
            }
        )
    return tree, manifest


def external_directory(path, root=ROOT):
    path = Path(path).resolve()
    require(
        not path.is_relative_to(root.resolve()) and path != root.resolve().parent,
        "Artifacts/cache/private state must be outside checkout",
    )
    return path


def validate_volume(lease, volume):
    require(volume.get("Name") == lease["volume"], "Foreign volume name")
    require(volume.get("Labels") == lease["labels"], "Foreign volume labels")
    require(
        volume.get("Driver") == "local"
        and volume.get("Scope") == "local"
        and not volume.get("Options"),
        "Foreign/remote volume driver or mount options",
    )
    require(
        volume.get("Mountpoint") == lease["volume_mountpoint"]
        and volume.get("CreatedAt") == lease["volume_created"],
        "Foreign volume mountpoint/creation identity",
    )


def validate_container(lease, container, *, live=True):
    require(
        container.get("Id") == lease["container_id"]
        and re.fullmatch(r"[0-9a-f]{64}", container.get("Id", "")),
        "Foreign container ID",
    )
    require(
        container.get("Image") == lease["image_id"] and container["Config"]["Image"] == DB_IMAGE,
        "Foreign container image/digest",
    )
    require(
        container["Config"].get("Labels") == lease.get("container_labels", lease["labels"]),
        "Foreign container labels",
    )
    host = container["HostConfig"]
    require(
        not host.get("Privileged")
        and host.get("NetworkMode") == "bridge"
        and host["RestartPolicy"]["Name"] == "no",
        "Unexpected container privileges/network/restart policy",
    )
    bindings = host.get("PortBindings")
    require(
        set(bindings or {}) == {"5432/tcp"} and len(bindings["5432/tcp"]) == 1,
        "Unexpected published ports",
    )
    binding = bindings["5432/tcp"][0]
    require(
        binding["HostIp"] == "127.0.0.1"
        and binding["HostPort"] in ("", str(lease.get("port", ""))),
        "Foreign bind host/port",
    )
    mounts = container.get("Mounts", [])
    require(len(mounts) == 2, "Unexpected mount count")
    destinations = {m["Destination"]: m for m in mounts}
    require(
        set(destinations)
        == {"/var/lib/postgresql", "/docker-entrypoint-initdb.d/010-bootstrap.sh"},
        "Foreign mount destination",
    )
    data = destinations["/var/lib/postgresql"]
    require(
        data["Type"] == "volume"
        and data.get("Name") == lease["volume"]
        and data["Source"] == lease["volume_mountpoint"]
        and data["RW"] is True,
        "Foreign data volume/mount",
    )
    boot = destinations["/docker-entrypoint-initdb.d/010-bootstrap.sh"]
    require(
        boot["Type"] == "bind" and boot["Source"] == lease["bootstrap"] and boot["RW"] is False,
        "Foreign bootstrap mount",
    )
    require(container.get("RestartCount") == 0, "Container restarted unexpectedly")
    state = container["State"]
    if lease.get("started_at"):
        require(state["StartedAt"] == lease["started_at"], "Foreign process start identity")
    if live:
        require(
            lease.get("pid", 0) > 0 and state["Running"] is True and state["Pid"] == lease["pid"],
            "Foreign/stopped process PID",
        )
    elif state["Running"]:
        require(
            not lease.get("pid") or state["Pid"] == lease["pid"], "Foreign running PID at cleanup"
        )
    ports = container["NetworkSettings"].get("Ports") or {}
    if live or lease.get("port") and ports.get("5432/tcp"):
        require(
            ports == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(lease["port"])}]},
            "Foreign server host/port mapping",
        )
    elif ports:
        require(
            set(ports) == {"5432/tcp"}
            and (
                ports["5432/tcp"] is None
                or len(ports["5432/tcp"]) == 1
                and ports["5432/tcp"][0]["HostIp"] == "127.0.0.1"
            ),
            "Foreign port at cleanup",
        )


def cleanup_owned(lease, inspect_container, inspect_volume, remove_container, remove_volume):
    """Validate *all* extant identities before the first removal; no name search."""
    container = inspect_container(lease["container_id"]) if lease.get("container_id") else None
    volume = inspect_volume(lease["volume"]) if lease.get("volume") else None
    if container is not None:
        require(volume is not None, "Owned container lost its recorded volume")
        validate_container(lease, container, live=False)
    if volume is not None:
        validate_volume(lease, volume)
    if container is not None:
        remove_container(lease["container_id"])
    if volume is not None:
        # Revalidate after container removal, including labels and mountpoint.
        validate_volume(lease, inspect_volume(lease["volume"]))
        remove_volume(lease["volume"])


def guarded_reset(source_guard, owner_guard, reset):
    source_guard()
    owner_guard()
    return reset()


def urls(lease):
    base = f"@127.0.0.1:{lease['port']}/"
    return {
        "ASM_NATIVE_TEST_ALLOW_RESET": "1",
        "ASM_NATIVE_TEST_ADMIN_URL": "postgresql+psycopg://asm_admin:"
        + lease["passwords"]["admin"]
        + base
        + "postgres",
        "ASM_DATABASE_URL": "postgresql+psycopg://asm_runtime:"
        + lease["passwords"]["runtime"]
        + base
        + "asm_test",
        "ASM_MIGRATION_DATABASE_URL": "postgresql+psycopg://asm_migrator:"
        + lease["passwords"]["migrator"]
        + base
        + "asm_test",
    }


def require_child_urls(lease):
    require(
        all(os.environ.get(key) == value for key, value in urls(lease).items()),
        "Child reset opt-in/URLs differ from owned lease",
    )


def db_connect(lease, role="admin", database="postgres"):
    import psycopg

    return psycopg.connect(
        host="127.0.0.1",
        port=lease["port"],
        user="asm_" + role,
        password=lease["passwords"][role],
        dbname=database,
        connect_timeout=5,
        options="-c statement_timeout=5000 -c lock_timeout=2000",
    )


def compare_server_identity(lease, identity, direct_id, *, initial=False):
    require(
        identity[:4] == ["postgres", "asm_admin", "asm_admin", 5432]
        and identity[4].startswith("18"),
        "Foreign DB/server login/version",
    )
    require(re.fullmatch(r"\d+", identity[5]) is not None, "Missing cluster identity")
    if not initial:
        require(
            identity == lease["server_identity"],
            "Foreign PostgreSQL system_identifier/postmaster identity",
        )
    require(direct_id == identity[5], "Network server differs from owned container cluster")


def verify_server(lease, commands, *, initial=False):
    from psycopg.rows import dict_row

    container = commands.docker_json("container", "inspect", lease["container_id"])
    volume = commands.docker_json("volume", "inspect", lease["volume"])
    validate_volume(lease, volume)
    validate_container(lease, container)
    with db_connect(lease) as connection:
        identity = list(
            connection.execute(
                "SELECT current_database(),session_user,current_user,inet_server_port(),current_setting('server_version_num'),system_identifier::text,pg_postmaster_start_time()::text FROM pg_control_system()"
            ).fetchone()
        )
        _, direct = commands.run(
            [
                "docker",
                "exec",
                lease["container_id"],
                "psql",
                "-X",
                "-U",
                "asm_admin",
                "-d",
                "postgres",
                "-Atqc",
                "SELECT system_identifier::text FROM pg_control_system()",
            ],
            quiet=True,
            limit=10,
        )
        compare_server_identity(lease, identity, direct.decode().strip(), initial=initial)
        connection.row_factory = dict_row
        roles = connection.execute(ROLE_SQL).fetchall()
        memberships = connection.execute(
            "SELECT roleid::regrole::text AS role,member::regrole::text AS member,admin_option,inherit_option,set_option FROM pg_auth_members WHERE member IN ('asm_runtime'::regrole,'asm_migrator'::regrole)"
        ).fetchall()
    with db_connect(lease, database="asm_test") as connection:
        owned = connection.execute(
            "SELECT (SELECT count(*) FROM pg_database WHERE datdba='asm_runtime'::regrole)+(SELECT count(*) FROM pg_namespace WHERE nspowner='asm_runtime'::regrole)+(SELECT count(*) FROM pg_class WHERE relowner='asm_runtime'::regrole)+(SELECT count(*) FROM pg_proc WHERE proowner='asm_runtime'::regrole)"
        ).fetchone()[0]
        compare_roles(roles, memberships, owned)
        extensions = connection.execute(
            "SELECT e.extname,e.extversion,n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname IN ('vector','btree_gist') ORDER BY e.extname"
        ).fetchall()
        require(
            extensions == [("btree_gist", "1.8", "extensions"), ("vector", "0.8.6", "extensions")],
            "Stock extension version/schema mismatch",
        )
        encoding = connection.execute("SHOW server_encoding").fetchone()[0]
        require(encoding == "UTF8", "Catalog serialization requires UTF8")
    logins = []
    for role in ("runtime", "migrator"):
        with db_connect(lease, role, "asm_test") as connection:
            row = connection.execute(
                "SELECT session_user,current_user,current_database(),current_setting('server_version_num')"
            ).fetchone()
            require(
                row[:3] == ("asm_" + role, "asm_" + role, "asm_test") and row[3].startswith("18"),
                "Dedicated LOGIN proof failed",
            )
            logins.append(list(row))
    return {
        "server_identity": identity,
        "roles": roles,
        "memberships": memberships,
        "owned_by_runtime": owned,
        "actual_logins": logins,
        "extensions": extensions,
        "server_encoding": encoding,
    }


def private_json(path, value):
    require(not path.is_symlink(), "Symlinked private state")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        json.dump(value, file)
    require(stat.S_IMODE(path.stat().st_mode) == 0o600, "Private state mode is not 0600")


def load_lease(private):
    path = private / "state.json"
    require(
        path.is_file() and not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600,
        "Missing/insecure private state",
    )
    lease = json.loads(path.read_text())
    require(
        re.fullmatch(r"asm-native-[0-9a-f]{32}", lease["name"]) is not None,
        "Invalid owned resource name",
    )
    require(
        lease["bootstrap"] == str(ROOT / "infra/postgres/bootstrap.sh"),
        "Foreign source mount in lease",
    )
    return lease


def require_event_lease(private, identity):
    if not (private / "state.json").exists():
        return
    lease = load_lease(private)
    require(
        lease["source_sha"] == identity["head"]
        and lease["tree"] == identity["tree"]
        and lease["labels"]["asm.c6.source"] == identity["head"]
        and lease["labels"]["asm.c6.tree"] == identity["tree"]
        and lease["labels"]["asm.c6.run"] == identity["run_id"] + ":" + identity["attempt"],
        "Lease differs from admitted source/tree/run/attempt",
    )


def inspect_if_present(commands, kind, identity):
    code, raw = commands.run(
        ["docker", kind, "inspect", identity], quiet=True, check=False, limit=10
    )
    if code:
        text = raw.decode(errors="replace")
        require(
            re.search(r"No such (?:object|container|volume):", text) is not None,
            "Docker inspection failed; cleanup refused",
        )
        return None
    rows = json.loads(raw)
    require(len(rows) == 1, "Ambiguous cleanup inspection")
    return rows[0]


def cleanup(private, evidence):
    if not (private / "state.json").exists():
        # Also run on preparation failure; never invent a resource/name to remove.
        require_source(ROOT, os.environ.get("GITHUB_SHA", ""))
        return
    lease = load_lease(private)
    require_source(ROOT, lease["source_sha"])
    commands = Commands(
        private,
        evidence,
        time.time() + 75,
        tuple(lease["passwords"].values()),
        "cleanup-" + secrets.token_hex(3),
    )
    cleanup_owned(
        lease,
        lambda identity: inspect_if_present(commands, "container", identity),
        lambda identity: inspect_if_present(commands, "volume", identity),
        lambda identity: commands.run(["docker", "container", "rm", "--force", identity], limit=20),
        lambda identity: commands.run(["docker", "volume", "rm", identity], limit=15),
    )
    write_json(
        evidence / "cleanup.json",
        {
            "result": "PASS",
            "container_id": lease.get("container_id"),
            "volume": lease.get("volume"),
            "scope": "Only revalidated owned identities; no global cleanup",
        },
    )
    for name in ("state.json", "bootstrap.env"):
        (private / name).unlink(missing_ok=True)


def collect_owned_logs(private, evidence):
    if not (private / "state.json").exists():
        return
    lease = load_lease(private)
    if not lease.get("container_id"):
        return
    require_source(ROOT, lease["source_sha"])
    commands = Commands(
        private, evidence, time.time() + 20, tuple(lease["passwords"].values()), "db-final-log"
    )
    validate_volume(lease, commands.docker_json("volume", "inspect", lease["volume"]))
    validate_container(
        lease, commands.docker_json("container", "inspect", lease["container_id"]), live=False
    )
    commands.run(["docker", "logs", lease["container_id"]], check=False, limit=8)


def create_database(private, evidence, commands, source_sha, tree):
    require(
        not any(key in os.environ for key in SECRET_ENV),
        "Reset opt-in/DB URLs must not be supplied to the parent runner",
    )
    require(
        not any(
            os.environ.get(key) for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY")
        ),
        "Remote/overridden Docker context refused",
    )
    _, context = commands.run(
        ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
        quiet=True,
        limit=10,
    )
    require(
        json.loads(context) in {"unix:///var/run/docker.sock", "unix:///run/docker.sock"},
        "Stock local Docker socket required",
    )
    pin_lines = (ROOT / "infra/images.lock.env").read_text().splitlines()
    require(pin_lines.count("DB_IMAGE=" + DB_IMAGE) == 1, "Committed DB digest differs")
    require_source(ROOT, source_sha)
    commands.run(["docker", "pull", DB_IMAGE])
    image = commands.docker_json("image", "inspect", DB_IMAGE)
    require(
        DB_IMAGE in image["RepoDigests"]
        and image["Os"] == "linux"
        and image["Architecture"] == "amd64",
        "Stock digest/platform mismatch",
    )
    nonce = secrets.token_hex(16)
    name = "asm-native-" + nonce
    labels = {
        "asm.c6.task": "m3-1-native-context-db-stock-runner-r1",
        "asm.c6.nonce": nonce,
        "asm.c6.source": source_sha,
        "asm.c6.tree": tree,
        "asm.c6.run": os.environ["GITHUB_RUN_ID"] + ":" + os.environ["GITHUB_RUN_ATTEMPT"],
    }
    lease = {
        "name": name,
        "source_sha": source_sha,
        "tree": tree,
        "labels": labels,
        "container_labels": {**(image.get("Config", {}).get("Labels") or {}), **labels},
        "image_id": image["Id"],
        "bootstrap": str(ROOT / "infra/postgres/bootstrap.sh"),
        "passwords": {role: secrets.token_hex(32) for role in ("admin", "runtime", "migrator")},
        "deadline": commands.deadline,
    }
    commands.passwords = tuple(lease["passwords"].values())
    private_json(private / "state.json", lease)
    label_args = [part for key, value in labels.items() for part in ("--label", key + "=" + value)]
    _, result = commands.run(["docker", "volume", "create", *label_args, name + "-data"])
    volume_name = result.decode().strip()
    require(volume_name == name + "-data", "Unexpected new volume identity")
    volume = commands.docker_json("volume", "inspect", volume_name)
    lease.update(
        volume=volume_name,
        volume_mountpoint=volume["Mountpoint"],
        volume_created=volume["CreatedAt"],
    )
    private_json(private / "state.json", lease)
    validate_volume(lease, volume)
    env = {
        "POSTGRES_USER": "asm_admin",
        "POSTGRES_DB": "asm_test",
        "POSTGRES_PASSWORD": lease["passwords"]["admin"],
        "ASM_RUNTIME_PASSWORD": lease["passwords"]["runtime"],
        "ASM_MIGRATION_PASSWORD": lease["passwords"]["migrator"],
    }
    with os.fdopen(
        os.open(private / "bootstrap.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as file:
        file.write("".join(key + "=" + value + "\n" for key, value in env.items()))
    _, result = commands.run(
        [
            "docker",
            "create",
            "--name",
            name,
            "--pull=never",
            "--restart=no",
            "--network=bridge",
            *label_args,
            "--env-file",
            str(private / "bootstrap.env"),
            "--mount",
            "type=volume,source=" + volume_name + ",destination=/var/lib/postgresql",
            "--mount",
            "type=bind,source="
            + lease["bootstrap"]
            + ",destination=/docker-entrypoint-initdb.d/010-bootstrap.sh,readonly",
            "--publish",
            "127.0.0.1::5432",
            DB_IMAGE,
        ]
    )
    lease["container_id"] = result.decode().strip()
    require(re.fullmatch(r"[0-9a-f]{64}", lease["container_id"]), "Invalid new container ID")
    private_json(private / "state.json", lease)
    validate_container(
        lease, commands.docker_json("container", "inspect", lease["container_id"]), live=False
    )
    require_source(ROOT, source_sha)
    commands.run(["docker", "start", lease["container_id"]])
    container = commands.docker_json("container", "inspect", lease["container_id"])
    ports = container["NetworkSettings"]["Ports"]
    require(
        set(ports) == {"5432/tcp"}
        and len(ports["5432/tcp"]) == 1
        and ports["5432/tcp"][0]["HostIp"] == "127.0.0.1",
        "Not a single loopback-only ephemeral PG port",
    )
    port = ports["5432/tcp"][0]["HostPort"]
    require(port.isdecimal() and 1024 < int(port) < 65536, "Invalid ephemeral PG host port")
    lease.update(
        port=int(port), pid=container["State"]["Pid"], started_at=container["State"]["StartedAt"]
    )
    private_json(private / "state.json", lease)
    validate_container(lease, container)
    import psycopg

    waiting_until = min(commands.deadline, time.time() + 90)
    while True:
        try:
            with db_connect(lease) as connection:
                ready = connection.execute(
                    "SELECT to_regrole('asm_runtime') IS NOT NULL AND to_regrole('asm_migrator') IS NOT NULL"
                ).fetchone()[0]
            require(ready, "Bootstrap role creation incomplete")
            break
        except (psycopg.OperationalError, Refusal):
            require(time.time() < waiting_until, "Stock bootstrap readiness timeout")
            time.sleep(0.5)
    proof = verify_server(lease, commands, initial=True)
    lease["server_identity"] = proof["server_identity"]
    private_json(private / "state.json", lease)
    write_json(
        evidence / "ownership-and-login.json",
        {
            **proof,
            "container_id": lease["container_id"],
            "container_pid": lease["pid"],
            "started_at": lease["started_at"],
            "image_ref": DB_IMAGE,
            "image_id": lease["image_id"],
            "repo_digests": image["RepoDigests"],
            "labels": labels,
            "volume": volume_name,
            "volume_mountpoint": volume["Mountpoint"],
            "bootstrap_sha256": sha256(Path(lease["bootstrap"]).read_bytes()),
            "bind_host": "127.0.0.1",
            "host_port": lease["port"],
        },
    )
    return lease


def child_environment(private):
    # Explicit environment, no inherited credentials, reset opt-in, pytest
    # selection flags, Git index override, provider tokens or application config.
    keep = (
        "PATH",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "GITHUB_SHA",
        "GITHUB_ACTIONS",
        "GITHUB_EVENT_PATH",
        "GITHUB_REPOSITORY_ID",
        "GITHUB_BASE_REF",
        "GITHUB_HEAD_REF",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_REPOSITORY",
        "GITHUB_REF",
        "GITHUB_EVENT_NAME",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(
        ASM_ENVIRONMENT="TEST",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONPATH=os.pathsep.join(str(ROOT / path) for path in ("backend/src", "tests", ".")),
        TMPDIR=str(private / "tmp"),
        XDG_CACHE_HOME=str(private / "cache"),
        NATIVE_ROOT=str(private.parent),
    )
    return env


def sanitize_file(private, evidence, name, passwords):
    path = private / name
    if path.exists():
        (evidence / name).write_text(redact(path.read_text(errors="replace"), passwords))


def require_unit_junit(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    require(
        cases
        and all(
            not any(case.find(tag) is not None for tag in ("skipped", "failure", "error"))
            for case in cases
        ),
        "Runner unit checks incomplete/skipped/failed",
    )


def validate_collection(nodes, deselected, reports, exit_code):
    require(nodes and len(set(nodes)) == len(nodes), "No tests/duplicate test node IDs")
    require(
        {n.split("::", 1)[0] for n in nodes} == set(MODULES),
        "Full four-module collection is required",
    )
    require(not deselected, "Deselected tests are forbidden")
    required_phases = {(node, phase) for node in nodes for phase in ("setup", "call", "teardown")}
    reported_phases = [(row["nodeid"], row["when"]) for row in reports]
    require(
        len(reported_phases) == len(set(reported_phases))
        and set(reported_phases) <= required_phases
        and all(row["outcome"] in ("passed", "failed", "skipped") for row in reports),
        "Duplicate/foreign/unknown test phase reports are forbidden",
    )
    require(
        not any(r["outcome"] == "skipped" or r["xfail"] for r in reports),
        "Skip/xfail cannot produce PASS",
    )
    if exit_code == 0:
        require(
            set(reported_phases) == required_phases
            and all(row["outcome"] == "passed" for row in reports),
            "Incomplete test execution cannot produce PASS",
        )


def require_native_fixture_guards(items, test_module, reset):
    native = inspect.unwrap(test_module.native)
    require(
        getattr(native, "__globals__", None) is vars(test_module)
        and Path(native.__code__.co_filename).resolve() == ROOT / MODULES[1]
        and native.__globals__.get("reset_disposable") is reset,
        "Native fixture must resolve the guarded disposable reset",
    )
    consumers = {}
    for path in MODULES[1:]:
        module = sys.modules.get(Path(path).stem)
        require(
            module is not None
            and Path(module.__file__).resolve() == ROOT / path
            and getattr(module, "native", None) is test_module.native,
            "PG module must import the same native fixture: " + path,
        )
        selected = [item for item in items if item.nodeid.split("::", 1)[0] == path]
        require(selected, "Missing guarded PG module: " + path)
        for item in selected:
            definitions = item._fixtureinfo.name2fixturedefs.get("native", ())
            require(
                item.module is module
                and definitions
                and inspect.unwrap(definitions[-1].func) is native,
                "PG node must resolve the shared guarded native fixture: " + item.nodeid,
            )
        consumers[path] = [item.nodeid for item in selected]
    return {
        "reset_entry_point": MODULES[1] + "::reset_disposable",
        "native_fixture": MODULES[1] + "::native",
        "per_module": consumers,
    }


def integration_arguments():
    return ["-v", "--durations=20", "-m", "integration", *("--ignore=" + p for p in PG_MODULES)]


def collect_partition(mode, destination):
    """Fresh-process collection only; the hook refuses any fixture execution."""
    import pytest

    require(not os.environ.get("PYTEST_ADDOPTS"), "External pytest selection is forbidden")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    inventory = {
        "nodeids": [],
        "integration_nodeids": [],
        "native_fixture_nodes": [],
        "deselected": [],
    }

    class Inventory:
        def pytest_collection_finish(self, session):
            for item in session.items:
                inventory["nodeids"].append(item.nodeid)
                if item.get_closest_marker("integration"):
                    inventory["integration_nodeids"].append(item.nodeid)
                require(
                    not any(item.get_closest_marker(m) for m in ("skip", "skipif", "xfail")),
                    "Skipped/xfail partition member: " + item.nodeid,
                )
                definitions = item._fixtureinfo.name2fixturedefs.get("native", ())
                if definitions:
                    function = inspect.unwrap(definitions[-1].func)
                    if Path(function.__code__.co_filename).resolve() == ROOT / MODULES[1]:
                        inventory["native_fixture_nodes"].append(item.nodeid)
            if mode == "collect-native":
                module = sys.modules["test_m3_1_native_context_postgres"]
                inventory["fixture_guards"] = require_native_fixture_guards(
                    session.items, module, module.reset_disposable
                )

        def pytest_deselected(self, items):
            inventory["deselected"].extend(item.nodeid for item in items)

        def pytest_runtest_setup(self, item):
            raise Refusal("Partition inventory must never execute fixtures")

    selection = (
        list(MODULES)
        if mode == "collect-native"
        else integration_arguments()
        if mode == "collect-generic-pg"
        else ["-m", "integration"]
    )
    code = 1
    try:
        code = int(
            pytest.main(
                [
                    *selection,
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
        return code
    finally:
        write_json(destination, {**inventory, "collection_exit": code})


def validate_partition(all_pg, native, generic):
    require(tuple(MODULES[1:]) == PG_MODULES, "Native carrier lost a complete PG module")
    for inventory in (all_pg, native, generic):
        nodes = inventory["nodeids"]
        require(
            inventory["collection_exit"] == 0 and nodes and len(nodes) == len(set(nodes)),
            "Failed/empty/duplicate partition collection",
        )
    a, n, g = (set(i["nodeids"]) for i in (all_pg, native, generic))
    pg = set(native["integration_nodeids"])
    source = n - pg
    require(
        not native["deselected"]
        and {node.split("::", 1)[0] for node in n} == set(MODULES)
        and {node.split("::", 1)[0] for node in pg} == set(PG_MODULES)
        and {node.split("::", 1)[0] for node in source} == {MODULES[0]},
        "Incomplete native inventory or unexpected integration markers",
    )
    require(
        a == set(all_pg["integration_nodeids"])
        and g == set(generic["integration_nodeids"])
        and pg == {node for node in a if node.split("::", 1)[0] in PG_MODULES}
        and pg == set(native["native_fixture_nodes"]) == set(all_pg["native_fixture_nodes"])
        and not generic["native_fixture_nodes"]
        and not (pg & g)
        and a == pg | g
        and generic["nodeids"] == [node for node in all_pg["nodeids"] if node not in pg]
        and set(all_pg["deselected"]) == set(generic["deselected"])
        and source <= set(all_pg["deselected"]),
        "Lost/foreign PG cases or native fixture escaped the exact three-module partition",
    )
    return {
        "result": "PASS",
        "all_pg": len(a),
        "generic_pg": len(g),
        "native_pg": len(pg),
        "native_source": len(source),
        "native_total": len(n),
        "excluded_modules": PG_MODULES,
        "disjoint_pg_sets_and_complete_union": True,
        "fixed_total_required": False,
        "inventory_sha256": {
            key: sha256(json.dumps(value, sort_keys=True).encode())
            for key, value in (("all", all_pg), ("native", native), ("generic", generic))
        },
    }


def prove_partition(private, evidence, commands, env):
    require_ci_inputs()
    inventories = []
    for name in ("all-pg", "native", "generic-pg"):
        path = private / ("partition-" + name + ".json")
        code, _ = commands.run(
            [
                sys.executable,
                "scripts/native_context_db_catalog.py",
                "collect-" + name,
                "--inventory",
                str(path),
            ],
            env=env,
            check=False,
        )
        if path.exists():
            value = json.loads(path.read_text())
            write_json(evidence / path.name, value)
        require(code == 0 and path.is_file(), "Partition collection failed: " + name)
        inventories.append(value)
    proof = validate_partition(*inventories)
    write_json(evidence / "integration-partition.json", proof)
    return proof, inventories[2]["nodeids"]


FOUNDATION_HOST = ("init", "config", "build")
FOUNDATION_CORE = (
    "checks",
    "storage-version",
    "storage-admin-version",
    "services",
    "http",
    "images",
)
FOUNDATION_BACKEND = (
    "ruff",
    "format",
    "mypy",
    "unit",
    "upgrade",
    "repeat-upgrade",
    "generic",
    "downgrade",
    "reupgrade",
    "contracts",
    "wheel-one",
    "wheel-two",
    "wheel-compare",
    "wheel-hash",
)
FOUNDATION_FILES = (
    "binding.json",
    "host.jsonl",
    "backend.jsonl",
    "cases.jsonl",
    "failures.jsonl",
    "issues.jsonl",
    "partition-all-pg.json",
    "partition-native.json",
    "partition-generic-pg.json",
    "integration-partition.json",
    "generic-result.json",
    "execution.json",
)
FOUNDATION_COPY = (
    "backend/",
    "migrations/",
    "tests/",
    "scripts/",
    "contracts/",
    "pyproject.toml",
    "uv.lock",
    "alembic.ini",
    "infra/postgres/ensure_m1_3_prerequisites.sh",
    ".github/workflows/ci.yml",
    ".github/workflows/native-context-db.yml",
)
FOUNDATION_LIMIT = 16 * 1024 * 1024
FOUNDATION_LIFECYCLES = (
    "fresh",
    "recovery",
    "recover-stopped",
    "recover-missing",
    "legacy-disable",
    "legacy-stop",
)


def foundation_stat(info, uid, *, directory=False):
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == uid
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "Foundation evidence type/owner/mode/link mismatch",
    )
    return [info.st_dev, info.st_ino]


def foundation_prepare(route):
    """No resources: admit clean source, then exclusively create host-owned evidence."""
    require(route in {"all", "normal-durable", "foundation-core"}, "Foundation route")
    require(not os.environ.get("ASM_FOUNDATION_EVIDENCE"), "Foundation evidence cannot be adopted")
    require_ci_inputs()
    head = git_bytes(ROOT, "rev-parse", "HEAD").decode().strip()
    tree, manifest = require_source(ROOT, head)
    headers = git_bytes(ROOT, "cat-file", "commit", head).decode().split("\n\n", 1)[0].splitlines()
    parents = [line[7:] for line in headers if line.startswith("parent ")]
    identity = {"head": head, "tree": tree, "parents": parents, "event_payload_sha256": None}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        require(os.environ.get("GITHUB_SHA") == head, "Foundation event/HEAD mismatch")
        job = os.environ.get("GITHUB_JOB", "")
        workflow = os.environ.get("GITHUB_WORKFLOW_REF", "")
        if route != "all":
            require(
                job == ("foundation-durable" if route == "normal-durable" else "foundation"),
                "Foundation job/route mismatch",
            )
            require(
                workflow.startswith(REPOSITORY + "/.github/workflows/ci.yml@"),
                "Foundation workflow",
            )
            admitted, _ = admit_event()
            identity.update(admitted)
        else:
            # The existing full caller has its own workflow_dispatch/push policy.
            # Do not broaden native/event_identity to admit storage packaging.
            require(
                job == "verify"
                and workflow.startswith(REPOSITORY + "/.github/workflows/storage-images.yml@")
                and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                and os.environ.get("GITHUB_REPOSITORY_ID") == str(REPOSITORY_ID)
                and (os.environ.get("GITHUB_EVENT_NAME"), os.environ.get("GITHUB_REF"))
                in {
                    ("workflow_dispatch", "refs/heads/main"),
                    ("push", "refs/heads/c6/m2-live-smoke"),
                },
                "Foundation full storage caller",
            )
            identity["event_payload_sha256"] = sha256(
                Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()
            )
        run, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
        require(
            all(re.fullmatch(r"[1-9][0-9]{0,19}", x) for x in (run, attempt)),
            "Foundation run identity",
        )
    else:
        job, run, attempt = "local", str(os.getpid()), "1"
    uid = os.getuid()
    reports = ROOT / "reports"
    require(not reports.is_symlink(), "Symlinked reports")
    reports.mkdir(exist_ok=True)
    require(
        reports.stat().st_uid == uid
        and stat.S_ISDIR(reports.stat().st_mode)
        and not reports.stat().st_mode & 0o022,
        "Unsafe reports parent",
    )
    if route != "foundation-core":
        require(
            not any(
                (reports / name).exists() or (reports / name).is_symlink()
                for name in ("telegram-egress.json", "candidate-egress-source.json")
            ),
            "Foundation cannot adopt previous durable reports",
        )
    parent = reports / ("foundation-" + job)
    require(not parent.is_symlink(), "Symlinked foundation parent")
    parent.mkdir(mode=0o700, exist_ok=True)
    foundation_stat(parent.stat(), uid, directory=True)
    path = parent / (run + "-" + attempt + "-" + head + "-" + secrets.token_hex(8))
    require(path.absolute() == path.resolve(), "Foundation path escape")
    path.mkdir(mode=0o700)
    files = {}
    for name in FOUNDATION_FILES:
        fd = os.open(path / name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            files[name] = foundation_stat(os.fstat(fd), uid)
        finally:
            os.close(fd)
    binding = {
        "version": 1,
        "uid": uid,
        "directory": foundation_stat(path.stat(), uid, directory=True),
        "files": files,
        "route": route,
        "run": run,
        "attempt": attempt,
        "job": job,
        "identity": identity,
        "source_manifest": manifest,
        "origin_ns": time.monotonic_ns(),
        "ci_inputs": CI_INPUT_SHA256,
        "source_identity_is_runtime_approval": False,
        "project": "asm-foundation-" + route + "-" + path.name.rsplit("-", 1)[1]
        if route != "all"
        else os.environ.get("COMPOSE_PROJECT_NAME", ROOT.name),
    }
    raw = (json.dumps(binding, sort_keys=True, ensure_ascii=True) + "\n").encode()
    fd = os.open(path / "binding.json", os.O_WRONLY | os.O_NOFOLLOW)
    try:
        require(os.write(fd, raw) == len(raw), "Partial foundation binding")
        os.fsync(fd)
    finally:
        os.close(fd)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        values = {
            "ASM_FOUNDATION_EVIDENCE": str(path),
            "ASM_FOUNDATION_OWNER_UID": str(uid),
            "ASM_FOUNDATION_BINDING_SHA256": sha256(raw),
        }
        require(
            all("\n" not in x and "\r" not in x for x in values.values()), "Invalid foundation path"
        )
        with open(os.environ["GITHUB_ENV"], "a") as output:
            output.write("".join(k + "=" + v + "\n" for k, v in values.items()))
    return path


class FoundationEvidence:
    """Fixed precreated files; inode/host-UID pins also apply inside the narrow bind."""

    def __init__(self):
        path = Path(os.environ["ASM_FOUNDATION_EVIDENCE"])
        require(path.is_absolute() and path == path.resolve(), "Foundation evidence path/symlink")
        require(
            path == Path("/asm-evidence") or path.is_relative_to(ROOT / "reports"),
            "Foundation evidence outside reports/bind",
        )
        uid = os.environ["ASM_FOUNDATION_OWNER_UID"]
        require(re.fullmatch(r"0|[1-9][0-9]{0,9}", uid), "Foundation UID")
        self.uid, self.path = int(uid), path
        directory = foundation_stat(path.lstat(), self.uid, directory=True)
        self.binding = None
        raw = self.read("binding.json", limit=2 * 1024 * 1024)
        require(
            sha256(raw) == os.environ["ASM_FOUNDATION_BINDING_SHA256"], "Foundation binding digest"
        )
        value = json.loads(raw)
        require(
            type(value["version"]) is int
            and value["version"] == 1
            and type(value["uid"]) is int
            and value["uid"] == self.uid
            and value["directory"] == directory
            and set(value["files"]) == set(FOUNDATION_FILES)
            and value["route"] in {"all", "normal-durable", "foundation-core"}
            and type(value["origin_ns"]) is int
            and 0 < value["origin_ns"] <= time.monotonic_ns()
            and value["ci_inputs"] == CI_INPUT_SHA256,
            "Foundation binding identity",
        )
        self.binding = value
        require(
            type(value["source_manifest"]) is list
            and value["source_manifest"]
            and len({entry["path"] for entry in value["source_manifest"]})
            == len(value["source_manifest"])
            and all(
                type(entry["path"]) is str
                and not Path(entry["path"]).is_absolute()
                and ".." not in Path(entry["path"]).parts
                and entry["path"] == Path(entry["path"]).as_posix()
                and entry["mode"] in {"100644", "100755"}
                and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                for entry in value["source_manifest"]
            )
            and set(CI_INPUT_SHA256) <= {entry["path"] for entry in value["source_manifest"]},
            "Foundation source manifest",
        )
        for name in FOUNDATION_FILES:
            fd = self.open(name)
            os.close(fd)
        require_ci_inputs()
        for entry in value["source_manifest"]:
            name = entry["path"]
            if any(name.startswith(p) if p.endswith("/") else name == p for p in FOUNDATION_COPY):
                source = ROOT / name
                require(
                    source.is_file()
                    and not source.is_symlink()
                    and sha256(source.read_bytes()) == entry["sha256"]
                    and bool(source.stat().st_mode & 0o111) == (entry["mode"] == "100755"),
                    "Foundation copied source differs",
                )

    def open(self, name):
        require(name in FOUNDATION_FILES, "Unknown foundation file")
        require(self.path == self.path.resolve(), "Foundation directory replaced")
        directory = foundation_stat(self.path.lstat(), self.uid, directory=True)
        require(
            self.binding is None or directory == self.binding["directory"],
            "Foundation directory inode",
        )
        directory_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(
                foundation_stat(os.fstat(directory_fd), self.uid, directory=True) == directory,
                "Foundation directory race",
            )
            fd = os.open(
                name, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
        finally:
            os.close(directory_fd)
        try:
            identity = foundation_stat(os.fstat(fd), self.uid)
            require(
                self.binding is None or identity == self.binding["files"][name],
                "Foundation file inode",
            )
        except Exception:
            os.close(fd)
            raise
        return fd

    def read(self, name, *, limit=FOUNDATION_LIMIT):
        fd = self.open(name)
        try:
            size = os.fstat(fd).st_size
            require(size <= limit, "Foundation file limit")
            raw = os.pread(fd, size + 1, 0)
            require(len(raw) == size, "Foundation read changed")
            return raw
        finally:
            os.close(fd)

    def publish(self, name, value):
        raw = (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode()
        require(len(raw) <= FOUNDATION_LIMIT, "Foundation JSON limit")
        fd = self.open(name)
        try:
            require(os.fstat(fd).st_size == 0, "Foundation JSON cannot be replaced/adopted")
            require(os.write(fd, raw) == len(raw), "Partial foundation JSON")
            os.fsync(fd)
        finally:
            os.close(fd)

    def append(self, name, row):
        fd = self.open(name)
        try:
            size = os.fstat(fd).st_size
            previous = os.pread(fd, min(size, 4096), max(0, size - 4096))
            require(not size or previous.endswith(b"\n"), "Torn foundation journal")
            sequence = json.loads(previous.splitlines()[-1])["sequence"] + 1 if size else 1
            elapsed = (time.monotonic_ns() - self.binding["origin_ns"]) / 1e9
            require(math.isfinite(elapsed) and elapsed >= 0, "Foundation elapsed")
            raw = (
                json.dumps(
                    {**row, "version": 1, "sequence": sequence, "elapsed": elapsed},
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            require(
                len(raw) <= 4096 and size + len(raw) <= FOUNDATION_LIMIT, "Foundation journal limit"
            )
            require(os.write(fd, raw) == len(raw), "Partial foundation journal")
            os.fsync(fd)
        finally:
            os.close(fd)

    def issue(self):
        # Closed signal only; even a sink exception may contain credentials/argv.
        print("FOUNDATION_EVIDENCE_WRITE_FAILED", flush=True)
        try:
            self.append("issues.jsonl", {"issue": "EVIDENCE_WRITE_FAILED"})
        except Exception:
            pass  # Missing/invalid records independently fail the completeness gate.


def foundation_store():
    return FoundationEvidence()


FOUNDATION_CLEANUP = (
    "docker",
    "compose",
    "--env-file",
    "infra/images.lock.env",
    "--env-file",
    ".env",
    "--profile",
    "test",
    "down",
    "--remove-orphans",
)


def foundation_ownership():
    """Called before resources; the shell retains this admission in readonly memory."""
    store = foundation_store()  # All original source/file/UID/inode checks still apply.
    require(
        store.uid == os.getuid() and store.path.is_relative_to(ROOT / "reports"),
        "Foundation host ownership",
    )
    project = os.environ.get("COMPOSE_PROJECT_NAME")
    require(
        store.binding["route"] == "all" or project == store.binding["project"],
        "Foundation owned project",
    )
    # Preserve the full caller's original Compose resolution when unset, rather
    # than guessing a project from a checkout/directory name. No credentials.
    return {
        "version": 1,
        "uid": store.uid,
        "path": str(store.path),
        "cwd": str(ROOT),
        "project": project,
        "binding": {k: store.binding[k] for k in ("directory", "files", "origin_ns")},
    }


def foundation_owned_cleanup():
    """Only the parent's inherited FD4 carries authority; current files cannot grant it.

    The descriptor is supplied from readonly shell memory after full admission,
    not opened from an evidence path. This snapshot permits the fixed owned down
    command and best-effort writes to individually pinned original sinks only.
    """
    with os.fdopen(os.dup(4), "rb") as source:
        raw = source.read(4097)
    require(len(raw) <= 4096, "Foundation ownership limit")
    value = json.loads(raw)
    require(
        set(value) == {"version", "uid", "path", "cwd", "project", "binding"}
        and type(value["version"]) is int
        and value["version"] == 1
        and type(value["uid"]) is int
        and value["uid"] == os.getuid()
        and value["cwd"] == str(ROOT) == str(Path.cwd())
        and type(value["path"]) is str
        and Path(value["path"]).is_absolute()
        and ".." not in Path(value["path"]).parts
        and Path(value["path"]).is_relative_to(ROOT / "reports")
        and (value["project"] is None or type(value["project"]) is str),
        "Foundation inherited ownership",
    )
    binding = value["binding"]
    require(
        set(binding) == {"directory", "files", "origin_ns"}
        and set(binding["files"]) == set(FOUNDATION_FILES)
        and all(
            type(pair) is list and len(pair) == 2 and all(type(n) is int and n >= 0 for n in pair)
            for pair in (binding["directory"], *binding["files"].values())
        )
        and type(binding["origin_ns"]) is int
        and 0 < binding["origin_ns"] <= time.monotonic_ns(),
        "Foundation inherited inode pins",
    )
    store = object.__new__(FoundationEvidence)
    store.uid, store.path, store.binding = value["uid"], Path(value["path"]), binding
    env = os.environ.copy()
    if value["project"] is None:
        env.pop("COMPOSE_PROJECT_NAME", None)
    else:
        env["COMPOSE_PROJECT_NAME"] = value["project"]
    failed = False
    try:
        current = foundation_store()
        require(
            current.uid == store.uid
            and current.path == store.path
            and all(current.binding[k] == v for k, v in binding.items()),
            "Foundation ownership changed",
        )
    except Exception:
        failed = True
        store.issue()
    # Never reopen/recreate a missing sink to recover authority. Each reporting
    # write still checks its own original directory/file inode, mode and UID.
    return store, failed, env


def foundation_step(stream, phase, argv, *, owned_cleanup=False):
    require(stream in {"host", "backend"}, "Foundation phase stream")
    allowed = (
        (*FOUNDATION_HOST, "normal-durable", *FOUNDATION_CORE, "cleanup")
        if stream == "host"
        else FOUNDATION_BACKEND
    )
    require(phase in allowed and argv, "Foundation phase/command")
    if owned_cleanup:
        require(
            stream == "host" and phase == "cleanup" and tuple(argv) == FOUNDATION_CLEANUP,
            "Foundation owned cleanup command",
        )
        store, recording_failed, env = foundation_owned_cleanup()
    else:
        store, recording_failed, env = foundation_store(), False, None
    try:
        store.append(stream + ".jsonl", {"phase": phase, "edge": "start"})
    except Exception:
        recording_failed = True
        store.issue()
    child, interrupted = None, None

    def forward(signum, frame):
        nonlocal interrupted
        interrupted = signum
        if child is not None:
            try:
                # The unchanged durable shell embeds Python. SIGINT enters its
                # existing finally/owned90s cleanup; retain the original incoming
                # cancellation status below, never grant extra job time.
                delivered = (
                    signal.SIGINT
                    if phase == "normal-durable" and signum == signal.SIGTERM
                    else signum
                )
                os.killpg(child.pid, delivered)
            except ProcessLookupError:
                pass

    handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    for s in handlers:
        signal.signal(s, forward)
    try:
        try:
            child = subprocess.Popen(
                argv, start_new_session=True, **({"env": env} if owned_cleanup else {})
            )
        except OSError:
            code = 127
        else:
            if interrupted is not None:
                forward(interrupted, None)
            try:
                code = child.wait(timeout=90 if phase == "cleanup" else None)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                code = 124
            code = 128 - code if code < 0 else code
        child_code = code
        if interrupted is not None:
            code = 128 + interrupted
    finally:
        for s, previous in handlers.items():
            signal.signal(s, previous)
    try:
        store.append(
            stream + ".jsonl",
            {
                "phase": phase,
                "edge": "end",
                "status": code,
                "process_exit": child_code,
                "signal": interrupted,
            },
        )
    except Exception:
        recording_failed = True
        store.issue()
    # This is an evidence gate after the process, not a replacement for its exit.
    # A failed primary/signal always wins, including when every sink is broken.
    # The owned cleanup status is the actual command's status. Reporting errors
    # remain separate in issues/phase records and the finish/completeness gate.
    return code if code or owned_cleanup else int(recording_failed)


def foundation_locations(manifest):
    """Source-relative frame ranges; never traceback formatting/source statements."""
    result = {}
    for entry in manifest:
        relative = entry["path"]
        if not relative.endswith(".py") or relative.split("/", 1)[0] not in {
            "backend",
            "tests",
            "scripts",
            "migrations",
        }:
            continue
        path = ROOT / relative
        source = path.read_text()
        require(
            not path.is_symlink() and sha256(source.encode()) == entry["sha256"],
            "Foundation frame source drift",
        )
        tree = ast.parse(source)
        result[relative] = [("<module>", 1, max(1, len(source.splitlines())))]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[relative].append((node.name, node.lineno, node.end_lineno))
    return result


def foundation_failure(error, locations, catalog):
    classes = {
        "AssertionError",
        "ValueError",
        "TypeError",
        "KeyError",
        "RuntimeError",
        "Refusal",
        "MessagingError",
        "DBAPIError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DatabaseError",
        "InternalError",
        "InterfaceError",
        "TimeoutError",
        "CancelledError",
        "DeadlockDetected",
        "LockNotAvailable",
        "ForeignKeyViolation",
        "CheckViolation",
        "NotNullViolation",
        "UniqueViolation",
        "SerializationFailure",
        "InFailedSqlTransaction",
    }
    tables = {t.split(".", 1)[1] for t in catalog["columns"]}
    functions = {signature.split("(", 1)[0] for signature in catalog["functions"]}
    ddl = catalog["nonfunction_ddl"]
    require(
        type(ddl) is list
        and ddl
        and all(
            type(row) is dict
            and set(row) == {"index", "revision", "sql"}
            and type(row["index"]) is int
            and row["index"] >= 0
            and type(row["revision"]) is str
            and re.fullmatch(r"[0-9]{4}", row["revision"])
            and type(row["sql"]) is str
            and row["sql"].strip()
            for row in ddl
        ),
        "Foundation source DDL records",
    )
    constraints = set(
        re.findall(
            r"\bCONSTRAINT\s+([a-z_][a-z_0-9]{0,62})\b", "\n".join(row["sql"] for row in ddl)
        )
    )
    labels = {
        c: c.__name__
        for c in (
            AssertionError,
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
            TimeoutError,
            Refusal,
        )
    }
    for name in (
        "sqlalchemy.exc",
        "psycopg",
        "psycopg.errors",
        "asyncio.exceptions",
        "asm.messaging.errors",
    ):
        module = sys.modules.get(name)
        if module is not None:
            labels.update(
                {
                    value: key
                    for key, value in vars(module).items()
                    if key in classes and isinstance(value, type)
                }
            )
    psycopg = sys.modules.get("psycopg")
    diagnostic = (
        vars(sys.modules["psycopg.errors"]).get("Diagnostic")
        if "psycopg.errors" in sys.modules
        else None
    )
    pg_error = vars(psycopg).get("Error") if psycopg is not None else None

    def field(value, name):
        try:
            raw = inspect.getattr_static(value, name, None)
            if (
                name in {"__traceback__", "__cause__", "__context__"}
                and raw is BaseException.__dict__[name]
            ):
                return raw.__get__(value, type(value))
            if isinstance(raw, property):
                # Only exact pinned psycopg properties may be evaluated. Foreign
                # descriptors, including properties raising BaseException, are inert.
                if (
                    diagnostic is not None
                    and type(value) is diagnostic
                    and raw is inspect.getattr_static(diagnostic, name, None)
                ):
                    return raw.__get__(value, diagnostic)
                if (
                    pg_error is not None
                    and type(value) in labels
                    and isinstance(value, pg_error)
                    and raw is inspect.getattr_static(pg_error, name, None)
                ):
                    return raw.__get__(value, type(value))
                return None
            return raw
        except Exception:
            return None

    def known(value, choices):
        return value if type(value) is str and value in choices else "UNKNOWN"

    chain, seen, pending = [], set(), [("primary", error)]
    python_budget = 8
    while pending and len(chain) < 4:
        via, fault = pending.pop(0)
        if not isinstance(fault, BaseException) or id(fault) in seen:
            continue
        seen.add(id(fault))
        diag = field(fault, "diag")
        state = field(fault, "sqlstate")
        if type(state) is not str or not re.fullmatch(r"[0-9A-Z]{5}", state):
            state = "UNKNOWN"
        python_frames, frames = [], []
        trace = field(fault, "__traceback__")
        scanned = 0
        while trace is not None and scanned < 128 and python_budget:
            scanned += 1
            code = trace.tb_frame.f_code
            name = code.co_filename
            if len(name) <= 1024:
                try:
                    path = Path(name).resolve()
                except (OSError, ValueError):
                    path = ROOT.parent
                relative = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else None
                if relative in locations and any(
                    function == code.co_name and start <= trace.tb_lineno <= end
                    for function, start, end in locations[relative]
                ):
                    python_frames.append(
                        {"path": relative, "function": code.co_name, "line": trace.tb_lineno}
                    )
                    python_budget -= 1
                    if not python_budget:
                        break
            trace = trace.tb_next
        context = field(diag, "context")
        if type(context) is str and len(context) <= 16384:
            for match in re.finditer(
                r"^PL/pgSQL function ((?:platform\.|app\.)?[a-z_][a-z_0-9]{0,62})\([a-z0-9_.,\[\] ]{0,240}\) line ([1-9][0-9]{0,5}) at [^\n]*$",
                context,
                re.MULTILINE,
            ):
                function, line = match.groups()
                function = function if "." in function else "platform." + function
                if function in functions:
                    frames.append({"function": function, "line": int(line)})
                    if len(frames) == 3:
                        break
        chain.append(
            {
                "via": via,
                "exception": labels.get(type(fault), "UNKNOWN"),
                "sqlstate": state,
                "schema": known(field(diag, "schema_name"), {"app", "platform"}),
                "table": known(field(diag, "table_name"), tables),
                "constraint": known(field(diag, "constraint_name"), constraints),
                "python_frames": python_frames,
                "plpgsql_frames": frames,
                "frames_limited": trace is not None,
                "context_limited": type(context) is str and len(context) > 16384,
            }
        )
        for attr in ("orig", "__cause__", "__context__"):
            linked = field(fault, attr)
            if isinstance(linked, BaseException) and id(linked) not in seen:
                pending.append((attr, linked))
    value = {
        "chain": chain,
        "chain_limited": any(id(f) not in seen for _, f in pending),
        "detail_limited": False,
    }
    # Reserve room for the journal's fixed case/sequence/time envelope.
    while len(json.dumps(value, ensure_ascii=True).encode()) > 3400:
        value["detail_limited"] = True
        for node in reversed(chain):
            if node["python_frames"]:
                node["python_frames"].pop()
                node["frames_limited"] = True
                break
            if node["plpgsql_frames"]:
                node["plpgsql_frames"].pop()
                node["context_limited"] = True
                break
        else:
            chain.pop()
            value["chain_limited"] = True
    return value


class GenericJournal:
    def __init__(self, store, expected):
        self.store, self.expected = store, expected
        self.index = {node: i for i, node in enumerate(expected)}
        self.started, self.phases, self.completed = [], {}, {}
        self.failed = False
        self.locations, self.catalog = (
            foundation_locations(store.binding["source_manifest"]),
            source_catalog(ROOT),
        )

    def persist_partition(self, work):
        for name in (
            "partition-all-pg.json",
            "partition-native.json",
            "partition-generic-pg.json",
            "integration-partition.json",
        ):
            self.store.publish(name, json.loads((work / name).read_text()))

    def record(self, name, row):
        try:
            self.store.append(name, row)
        except Exception:
            self.failed = True
            self.store.issue()

    def key(self, node):
        return {"index": self.index[node], "nodeid_sha256": sha256(node.encode())}

    def start(self, node):
        try:
            require(
                node in self.index and self.index[node] == len(self.started), "Generic start order"
            )
            self.started.append(node)
            self.phases[node] = {}
            self.record("cases.jsonl", {"event": "start", **self.key(node)})
        except Exception:
            self.failed = True
            self.store.issue()

    def report(self, node, report, error):
        try:
            require(
                node in self.phases and report.when in {"setup", "call", "teardown"},
                "Generic report identity",
            )
            phases = self.phases[node]
            require(
                report.when not in phases and report.outcome in {"passed", "failed", "skipped"},
                "Generic phase duplicate/outcome",
            )
            duration = report.duration
            require(
                type(duration) in {int, float} and math.isfinite(duration) and duration >= 0,
                "Generic duration",
            )
            phases[report.when] = {
                "outcome": report.outcome,
                "xfail": bool(getattr(report, "wasxfail", False)),
            }
            self.record(
                "cases.jsonl",
                {
                    "event": "phase",
                    **self.key(node),
                    "phase": report.when,
                    "outcome": report.outcome,
                    "duration": duration,
                    "xfail": phases[report.when]["xfail"],
                },
            )
            if report.outcome == "failed":
                self.record(
                    "failures.jsonl",
                    {
                        **self.key(node),
                        "phase": report.when,
                        "failure": foundation_failure(error, self.locations, self.catalog),
                    },
                )
            if report.when == "teardown":
                setup = phases.get("setup", {})
                complete = bool(setup) and (setup["outcome"] != "passed" or "call" in phases)
                outcome = "INCOMPLETE"
                if complete:
                    outcome = (
                        "FAILED"
                        if any(p["outcome"] == "failed" for p in phases.values())
                        else "PASSED"
                        if all(p["outcome"] == "passed" and not p["xfail"] for p in phases.values())
                        else "SKIPPED"
                    )
                self.completed[node] = outcome
                self.record(
                    "cases.jsonl", {"event": "case-end", **self.key(node), "outcome": outcome}
                )
        except Exception:
            self.failed = True
            self.store.issue()

    def finish(self, code):
        complete = (
            self.started == self.expected
            and set(self.completed) == set(self.expected)
            and not any(x in {"INCOMPLETE", "SKIPPED"} for x in self.completed.values())
        )
        try:
            self.store.publish(
                "generic-result.json",
                {
                    "pytest_exit": code,
                    "complete": complete,
                    "evidence_failed": self.failed,
                    "expected": len(self.expected),
                    "completed": len(self.completed),
                },
            )
        except Exception:
            self.failed = True
            self.store.issue()


def foundation_check(store):
    require(not store.read("issues.jsonl"), "Foundation evidence sink failed")

    def rows(name):
        raw = store.read(name)
        require(raw.endswith(b"\n"), "Missing/torn foundation journal")
        values = [json.loads(line) for line in raw.splitlines()]
        require(
            all(len(line) + 1 <= 4096 for line in raw.splitlines()), "Oversized foundation record"
        )
        require(
            all(type(r["sequence"]) is int for r in values)
            and [r["sequence"] for r in values] == list(range(1, len(values) + 1)),
            "Foundation journal sequence",
        )
        require(
            all(
                r["version"] == 1
                and type(r["elapsed"]) in {float, int}
                and math.isfinite(r["elapsed"])
                and r["elapsed"] >= 0
                for r in values
            ),
            "Foundation journal clock",
        )
        require(
            [r["elapsed"] for r in values] == sorted(r["elapsed"] for r in values),
            "Foundation clock regressed",
        )
        return values

    route = store.binding["route"]
    host = (
        *FOUNDATION_HOST,
        *(("normal-durable",) if route != "foundation-core" else ()),
        *(FOUNDATION_CORE if route != "normal-durable" else ()),
        "cleanup",
    )
    expected = [
        {"phase": p, "edge": edge, **({"status": 0} if edge == "end" else {})}
        for p in host
        for edge in ("start", "end")
    ]
    require(
        [{k: r[k] for k in ("phase", "edge", "status") if k in r} for r in rows("host.jsonl")]
        == expected,
        "Foundation host incomplete/failed",
    )
    execution = json.loads(store.read("execution.json"))
    require(
        execution == {"primary_exit": 0, "cleanup_exit": 0}, "Foundation execution/cleanup failed"
    )
    if route != "foundation-core":
        durable = {}
        for name in ("telegram-egress.json", "candidate-egress-source.json"):
            fd = os.open(ROOT / "reports" / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                foundation_stat(os.fstat(fd), store.uid)
                size = os.fstat(fd).st_size
                require(size <= FOUNDATION_LIMIT, "Foundation durable report size")
                durable[name] = json.loads(os.pread(fd, size + 1, 0))
            finally:
                os.close(fd)
        report, source = durable["telegram-egress.json"], durable["candidate-egress-source.json"]
        require(
            report["source_sha"] == source["source_sha"] == store.binding["identity"]["head"]
            and source["parents"] == store.binding["identity"]["parents"]
            and source["expected_revision"] == "0013"
            and set(source["images"]) == {"api", "worker", "scheduler", "fixture"}
            and list(report["lifecycles"]) == list(FOUNDATION_LIFECYCLES)
            and all(
                row["source_sha"] == source["source_sha"] for row in report["lifecycles"].values()
            )
            and report["assertions"]
            and all(row["result"] == "PASS" for row in report["assertions"]),
            "Foundation current durable evidence incomplete/different source",
        )
    if route == "normal-durable":
        return
    expected = [
        {"phase": p, "edge": edge, **({"status": 0} if edge == "end" else {})}
        for p in FOUNDATION_BACKEND
        for edge in ("start", "end")
    ]
    require(
        [{k: r[k] for k in ("phase", "edge", "status") if k in r} for r in rows("backend.jsonl")]
        == expected,
        "Foundation backend incomplete/failed",
    )
    inventories = [
        json.loads(store.read("partition-" + name + ".json"))
        for name in ("all-pg", "native", "generic-pg")
    ]
    proof = validate_partition(*inventories)
    require(
        json.loads(json.dumps(proof)) == json.loads(store.read("integration-partition.json")),
        "Foundation partition differs",
    )
    nodes = inventories[2]["nodeids"]
    cases = rows("cases.jsonl")
    starts = [r for r in cases if r["event"] == "start"]
    ends = [r for r in cases if r["event"] == "case-end"]
    require(
        [r["index"] for r in starts] == list(range(len(nodes))) == [r["index"] for r in ends],
        "Generic cases incomplete/order",
    )
    require(
        [(r["event"], r["index"], r.get("phase")) for r in cases]
        == [
            (event, i, phase)
            for i in range(len(nodes))
            for event, phase in (
                ("start", None),
                ("phase", "setup"),
                ("phase", "call"),
                ("phase", "teardown"),
                ("case-end", None),
            )
        ],
        "Generic journal event order",
    )
    require(
        all(r["nodeid_sha256"] == sha256(nodes[r["index"]].encode()) for r in cases),
        "Generic journal case identity",
    )
    require(all(r["outcome"] == "PASSED" for r in ends), "Generic case failed/incomplete")
    phases = [r for r in cases if r["event"] == "phase"]
    require(
        [(r["index"], r["phase"]) for r in phases]
        == [(i, p) for i in range(len(nodes)) for p in ("setup", "call", "teardown")],
        "Generic actual phases incomplete/order",
    )
    require(
        all(
            r["outcome"] == "passed"
            and r["xfail"] is False
            and type(r["duration"]) in {float, int}
            and math.isfinite(r["duration"])
            and r["duration"] >= 0
            for r in phases
        ),
        "Generic actual phase failed",
    )
    require(not store.read("failures.jsonl"), "Generic failure records")
    result = json.loads(store.read("generic-result.json"))
    require(
        result
        == {
            "pytest_exit": 0,
            "complete": True,
            "evidence_failed": False,
            "expected": len(nodes),
            "completed": len(nodes),
        },
        "Generic completion failed",
    )


def foundation_cli(argv):
    parser = argparse.ArgumentParser(description="Fixed foundation source/evidence plumbing")
    parser.add_argument(
        "mode",
        choices=(
            "foundation-prepare",
            "foundation-ownership",
            "foundation-step",
            "foundation-finish",
            "foundation-check",
        ),
    )
    parser.add_argument("values", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.mode == "foundation-prepare":
        require(len(args.values) == 1, "Foundation prepare arguments")
        print(foundation_prepare(args.values[0]))
        return 0
    if args.mode == "foundation-step":
        owned = args.values[2:3] == ["--owned-cleanup-fd=4"]
        if owned:
            del args.values[2]
        require(len(args.values) >= 4 and args.values[2] == "--", "Foundation step arguments")
        return foundation_step(args.values[0], args.values[1], args.values[3:], owned_cleanup=owned)
    if args.mode == "foundation-ownership":
        require(not args.values, "Foundation ownership arguments")
        raw = json.dumps(foundation_ownership(), ensure_ascii=True, sort_keys=True)
        require(len(raw.encode()) + 1 <= 4096, "Foundation ownership limit")
        print(raw)
        return 0
    owned = args.mode == "foundation-finish" and args.values[-1:] == ["--owned-cleanup-fd=4"]
    if owned:
        args.values.pop()
        store, reporting_failed, _ = foundation_owned_cleanup()
    else:
        store, reporting_failed = foundation_store(), False
    if args.mode == "foundation-finish":
        require(
            len(args.values) == 2
            and all(re.fullmatch(r"[0-9]{1,3}", x) and int(x) <= 255 for x in args.values),
            "Foundation finish status",
        )
        try:
            store.publish(
                "execution.json",
                {
                    "primary_exit": int(args.values[0]),
                    "cleanup_exit": int(args.values[1]),
                    **({"evidence_failed": True} if reporting_failed else {}),
                },
            )
        except Exception:
            store.issue()
            return 1
        return int(reporting_failed)
    else:
        require(not args.values, "Foundation check arguments")
        foundation_check(store)
        print("FOUNDATION_COMPLETE_EVIDENCE_PASS")
    return 0


def generic_integration():
    import pytest

    require(
        not any(key in os.environ for key in SECRET_ENV[:2]),
        "Generic checks must never receive native reset/admin credentials",
    )
    require(not os.environ.get("PYTEST_ADDOPTS"), "External pytest selection is forbidden")
    store = foundation_store()  # Refuse a missing/foreign sink before collection or fixtures.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    with tempfile.TemporaryDirectory(prefix="asm-integration-partition-") as directory:
        work = external_directory(directory)
        try:
            proof, expected = prove_partition(
                work, work, Commands(work, work, time.time() + 180), dict(os.environ)
            )
        except Exception:
            # The foundation job already publishes stdout/stderr in ci.log.
            # Keep collection diagnostics there before the temporary files go.
            for path in sorted(work.iterdir()):
                if path.suffix in (".json", ".log"):
                    print(path.name + "\n" + redact(path.read_text(errors="replace")), flush=True)
            raise
        print(json.dumps(proof, sort_keys=True), flush=True)
        journal = GenericJournal(store, expected)
        journal.persist_partition(work)

        class ExactGeneric:
            def pytest_collection_finish(self, session):
                require(
                    [item.nodeid for item in session.items] == expected,
                    "Actual generic PG execution differs from the proven partition",
                )

            def pytest_runtest_logstart(self, nodeid, location):
                journal.start(nodeid)

            @pytest.hookimpl(hookwrapper=True)
            def pytest_runtest_makereport(self, item, call):
                outcome = yield
                report = outcome.get_result()
                journal.report(item.nodeid, report, call.excinfo.value if call.excinfo else None)

        # Retain the original pytest verbosity/durations/marker and exit code.
        code = int(
            pytest.main(
                [*integration_arguments(), "-p", "pytest_asyncio.plugin"], plugins=[ExactGeneric()]
            )
        )
        journal.finish(code)
        if code == 0:
            require(
                not journal.failed, "Generic evidence completeness failed after pytest exit zero"
            )
        return code


def carrier(private, evidence, lease, commands):
    import functools

    import pytest

    nodes, deselected, reports, reset_proofs = [], [], [], []
    original_reset = None
    test_module = None

    class Audit:
        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_finish(self, session):
            nonlocal original_reset, test_module
            nodes.extend(item.nodeid for item in session.items)
            require(
                nodes and {n.split("::", 1)[0] for n in nodes} == set(MODULES),
                "Incomplete carrier collection",
            )
            test_module = sys.modules["test_m3_1_native_context_postgres"]
            original_reset = test_module.reset_disposable
            require(
                Path(original_reset.__code__.co_filename).resolve() == ROOT / MODULES[1],
                "Unexpected disposable-reset implementation",
            )

            @functools.wraps(original_reset)
            def checked_reset():
                def owner_guard():
                    require_child_urls(lease)
                    proof = verify_server(lease, commands)
                    reset_proofs.append({"reset": len(reset_proofs) + 1, **proof})
                    write_json(evidence / "before-reset-proofs.json", reset_proofs)

                return guarded_reset(
                    lambda: require_source(ROOT, lease["source_sha"]), owner_guard, original_reset
                )

            # A guard around the unchanged destructive fixture entry point. It
            # adds refusal checks; assertions, SQL, cases and markers are intact.
            test_module.reset_disposable = checked_reset
            write_json(
                evidence / "fixture-guards.json",
                require_native_fixture_guards(session.items, test_module, checked_reset),
            )

        @pytest.hookimpl(tryfirst=True)
        def pytest_runtest_setup(self, item):
            require_source(ROOT, lease["source_sha"])

        def pytest_deselected(self, items):
            deselected.extend(item.nodeid for item in items)

        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(self, item, call):
            outcome = yield
            report = outcome.get_result()
            report.native_sqlstates = exception_sqlstates(
                call.excinfo.value if call.excinfo else None
            )

        def pytest_runtest_logreport(self, report):
            row = {
                "nodeid": report.nodeid,
                "when": report.when,
                "outcome": report.outcome,
                "seconds": report.duration,
                "xfail": hasattr(report, "wasxfail"),
                "sqlstates": getattr(report, "native_sqlstates", []),
            }
            if report.failed:
                row["trace"] = redact(str(report.longrepr), commands.passwords)
            reports.append(row)

    started = time.monotonic()
    exit_code = 1
    try:
        exit_code = int(
            pytest.main(
                [
                    *MODULES,
                    "-vv",
                    "-rA",
                    "--durations=0",
                    "--tb=long",
                    "-p",
                    "pytest_asyncio.plugin",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp=" + str(private / "carrier-tmp"),
                    "--junitxml=" + str(private / "carrier.xml"),
                ],
                plugins=[Audit()],
            )
        )
        validate_collection(nodes, deselected, reports, exit_code)
        return exit_code
    finally:
        if original_reset is not None:
            test_module.reset_disposable = original_reset
        write_json(
            evidence / "collection.json",
            {
                "modules": MODULES,
                "per_module": {
                    path: [node for node in nodes if node.split("::", 1)[0] == path]
                    for path in MODULES
                },
                "nodeids": nodes,
                "deselected": deselected,
                "count": len(nodes),
                "sha256": sha256("\n".join(nodes).encode()),
                "fixed_total_required": False,
            },
        )
        write_json(
            evidence / "test-results.json",
            {
                "pytest_exit": exit_code,
                "seconds": time.monotonic() - started,
                "reports": reports,
                "reset_count": len(reset_proofs),
            },
        )
        sanitize_file(private, evidence, "carrier.xml", commands.passwords)


def independent_catalog(private, evidence, lease, commands):
    from psycopg.rows import dict_row
    from test_m3_1_native_context_postgres import reset_disposable

    # All test data stays until the next guarded whole-DB reset. Fresh catalog
    # preparation follows the full carrier and cannot make a used downgrade pass.
    guarded_reset(
        lambda: require_source(ROOT, lease["source_sha"]),
        lambda: (require_child_urls(lease), verify_server(lease, commands)),
        reset_disposable,
    )
    commands.run([sys.executable, "-m", "alembic", "upgrade", "0013"], limit=30)
    proof = verify_server(lease, commands)
    expected = source_catalog(ROOT)
    write_json(evidence / "expected-source-catalog.json", expected)
    (evidence / "independent-catalog.sql").write_text(
        "SET TRANSACTION READ ONLY;\nSET LOCAL search_path=pg_catalog,pg_temp;\n"
        + CATALOG_SQL
        + ";\n"
        + FUNCTION_SQL
        + ";\n"
        + ROLE_SQL
        + ";\n"
    )
    with db_connect(lease, "migrator", "asm_test") as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog,pg_temp")
        connection.execute("SET LOCAL timezone='UTC'")
        connection.execute("SET LOCAL extra_float_digits=3")
        require(
            connection.execute("SELECT version_num FROM platform.alembic_version").fetchall()
            == [("0013",)],
            "Fresh checkpoint is not 0013",
        )
        extra_relations = connection.execute(
            "SELECT n.nspname,c.relname,c.relkind,c.relpersistence FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') AND (c.relkind NOT IN ('r','i','S') OR c.relpersistence<>'p') ORDER BY 1,2"
        ).fetchall()
        require(not extra_relations, "Extra/temporary/non-table relation in owned checkpoint")
        full_text, nonfunction_text = connection.execute(CATALOG_SQL).fetchone()
        connection.row_factory = dict_row
        functions = connection.execute(FUNCTION_SQL).fetchall()
        # Resolve full typed signatures independently, then compare unique OIDs.
        signatures = sorted(expected["functions"])
        resolved_rows = connection.execute(
            "SELECT signature,to_regprocedure(signature)::oid::bigint AS oid FROM unnest(%s::text[]) AS source(signature) ORDER BY signature",
            (signatures,),
        ).fetchall()
        resolved = {r["signature"]: r["oid"] for r in resolved_rows}
        (evidence / "installed-catalog.pg-json.txt").write_text(full_text, encoding="utf-8")
        (evidence / "installed-nonfunction.pg-json.txt").write_text(
            nonfunction_text, encoding="utf-8"
        )
        write_json(
            evidence / "installed-function-oids.json",
            {"functions": functions, "resolved": resolved},
        )
        compare_roles(proof["roles"], proof["memberships"], proof["owned_by_runtime"])

        # Only after checking every body, including the verifier's own exact
        # source body, may its self-report be compared with the independent hash.
        def read_profile():
            declared = connection.execute(
                "SELECT platform.human_context_schema_profile() AS profile"
            ).fetchone()["profile"]
            write_json(evidence / "declared-profile.json", declared)
            return declared

        full_hash, declared = compare_catalog(
            expected, functions, resolved, full_text, nonfunction_text, read_profile
        )
        write_json(
            evidence / "profile-comparison.json",
            {
                "schema_revision": "0013",
                "function_count": len(functions),
                "table_count": len(expected["columns"]),
                "nonfunction_sha256": sha256(nonfunction_text.encode()),
                "independent_profile_sha256": full_hash,
                "declared_profile": declared,
                "all_source_bodies_checked_before_profile_call": True,
                "own_profile_body_sha256": expected["functions"][PROFILE]["body_sha256"],
            },
        )
    return 0


def child(mode, private, evidence):
    require(sys.version_info[:2] == (3, 13), "Stock lane requires Python 3.13")
    require(
        not any(key in os.environ for key in SECRET_ENV),
        "Child reset credentials must originate in its private lease",
    )
    identity, _ = admit_event(evidence, entrypoint=mode)
    require_event_lease(private, identity)
    lease = load_lease(private)
    require(lease["source_sha"] == identity["head"], "Lease differs from admitted event source")
    require_source(ROOT, lease["source_sha"])
    commands = Commands(
        private, evidence, lease["deadline"], tuple(lease["passwords"].values()), mode
    )
    verify_server(lease, commands)
    os.environ.update(urls(lease))
    try:
        return (
            carrier(private, evidence, lease, commands)
            if mode == "carrier"
            else independent_catalog(private, evidence, lease, commands)
        )
    finally:
        for key in SECRET_ENV:
            os.environ.pop(key, None)


def run_lane(private, evidence):
    started = int((private.parent / "job-start").read_text().strip())
    require(0 <= time.time() - started < 1080, "Invalid/exhausted whole-job budget")
    # Reserve two minutes for owned cleanup, evidence and upload inside 20m.
    commands = Commands(private, evidence, started + 1080)
    receipt = {
        "event_identity_is_c0_approval": False,
        "stock_db": "NOT_RUN",
        "carrier_exit": None,
        "catalog_exit": None,
        "result": "FAIL",
    }
    result = 1
    admitted = False
    try:
        identity, manifest = admit_event(evidence, entrypoint="run")
        require(not (private / "state.json").exists(), "Run must start without retained resources")
        admitted = True
        receipt.update(admission="PASS", source_identity=identity)
        require(sys.version_info[:2] == (3, 13), "Python 3.13 required; no patched runtime")
        source_sha, tree = identity["head"], identity["tree"]
        require(
            external_directory(os.environ["UV_PROJECT_ENVIRONMENT"]) == Path(sys.prefix).resolve(),
            "Frozen external project venv required",
        )
        for key in ("UV_CACHE_DIR", "RUFF_CACHE_DIR"):
            external_directory(os.environ[key])
        write_json(evidence / "source-manifest.json", manifest)
        source_archive = git_bytes(ROOT, "archive", "--format=tar", "HEAD")
        (evidence / "source.tar").write_bytes(source_archive)
        write_json(
            evidence / "source-identity.json",
            {
                **identity,
                "run_url": "https://github.com/Elefesys/ai-service-manager/actions/runs/"
                + os.environ["GITHUB_RUN_ID"],
                "source_archive_sha256": sha256(source_archive),
                "manifest_sha256": sha256((evidence / "source-manifest.json").read_bytes()),
                "python": sys.version,
                "uv_lock_sha256": sha256((ROOT / "uv.lock").read_bytes()),
                "clean_tracked_and_untracked_before": True,
                "event_identity_is_c0_approval": False,
            },
        )
        _, uv_version = commands.run(["uv", "--version"])
        require(
            re.fullmatch(r"uv 0\.10\.0(?: \([^\n]+\))?", uv_version.decode().strip()),
            "Locked uv version required",
        )
        _, git_version = commands.run(["git", "--version"])
        write_json(
            evidence / "versions.json",
            {
                "python": sys.version,
                "uv": uv_version.decode().strip(),
                "git": git_version.decode().strip(),
                "distributions": sorted(
                    (distribution.metadata["Name"], distribution.version)
                    for distribution in importlib.metadata.distributions()
                ),
            },
        )
        expected = source_catalog(ROOT)
        write_json(evidence / "expected-source-catalog.json", expected)
        unit_env = child_environment(private)
        commands.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "scripts/native_context_db_catalog.py",
                "tests/test_native_context_db_runner.py",
            ]
        )
        commands.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                "--diff",
                "scripts/native_context_db_catalog.py",
                "tests/test_native_context_db_runner.py",
            ]
        )
        unit_code, _ = commands.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_native_context_db_runner.py",
                "-vv",
                "-rA",
                "-p",
                "no:cacheprovider",
                "-p",
                "pytest_asyncio.plugin",
                "-o",
                "addopts=",
                "--basetemp=" + str(private / "unit-tmp"),
                "--junitxml=" + str(private / "runner-unit.xml"),
            ],
            env=unit_env,
            check=False,
        )
        sanitize_file(private, evidence, "runner-unit.xml", ())
        require(unit_code == 0, "Runner negative unit checks failed")
        require_unit_junit(private / "runner-unit.xml")
        prove_partition(private, evidence, commands, unit_env)
        require_source(ROOT, source_sha)
        _, docker_version = commands.run(
            ["docker", "version", "--format", "{{json .Server.Version}}"]
        )
        versions = json.loads((evidence / "versions.json").read_text())
        write_json(
            evidence / "versions.json", {**versions, "docker_server": json.loads(docker_version)}
        )
        create_database(private, evidence, commands, source_sha, tree)
        receipt["stock_db"] = "CREATED_AND_OWNERSHIP_VERIFIED"
        for mode in ("carrier", "catalog"):
            code, _ = commands.run(
                [sys.executable, "scripts/native_context_db_catalog.py", mode],
                env=child_environment(private),
                check=False,
            )
            receipt[mode + "_exit"] = code
        require(
            receipt["carrier_exit"] == 0 and receipt["catalog_exit"] == 0,
            "Focused carrier/catalog failed; original exit codes preserved",
        )
        require_source(ROOT, source_sha)
        receipt["result"] = "PASS"
        result = 0
    except Exception as error:
        if hasattr(error, "admission_diagnostic"):
            receipt["admission_diagnostic"] = error.admission_diagnostic
        passwords = ()
        if admitted and (private / "state.json").exists():
            passwords = tuple(load_lease(private)["passwords"].values())
        (evidence / "runner-error.log").write_text(redact(traceback.format_exc(), passwords))
    finally:
        try:
            if admitted:
                require_event_lease(private, identity)
                collect_owned_logs(private, evidence)
        except Exception:
            receipt.update(result="FAIL", owned_log_capture="REFUSED_OR_FAILED")
            result = 1
            (evidence / "owned-log-error.log").write_text(
                redact(traceback.format_exc(), commands.passwords)
            )
        try:
            if admitted:
                require_event_lease(private, identity)
                cleanup(private, evidence)
                final_tree, _ = require_source(ROOT, os.environ.get("GITHUB_SHA", ""))
                receipt.update(
                    clean_tracked_and_untracked_after=True,
                    final_tree=final_tree,
                    owned_cleanup="PASS",
                )
            else:
                receipt.update(admission="REFUSED", owned_cleanup="NOT_ATTEMPTED_EVENT_REFUSED")
        except Exception:
            receipt.update(result="FAIL", owned_cleanup="REFUSED_OR_FAILED")
            result = 1
            (evidence / "cleanup-error.log").write_text(
                redact(traceback.format_exc(), commands.passwords)
            )
        receipt["process_exit"] = result
        receipt["elapsed_since_job_start_seconds"] = time.time() - started
        write_json(evidence / "receipt.json", receipt)
    return result


def main():
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1].startswith("foundation-"):
        try:
            return foundation_cli(sys.argv[1:])
        except Exception:
            print("FOUNDATION_EVIDENCE_REFUSED", file=sys.stderr, flush=True)
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "run",
            "carrier",
            "catalog",
            "cleanup",
            "generic-integration",
            "collect-all-pg",
            "collect-native",
            "collect-generic-pg",
        ),
    )
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if args.mode.startswith("collect-"):
        require(args.inventory is not None, "Collection output path required")
        return collect_partition(args.mode, external_directory(args.inventory))
    require(args.inventory is None, "Inventory output is collection-only")
    if args.mode == "generic-integration":
        return generic_integration()
    work = external_directory(os.environ["NATIVE_ROOT"])
    private, evidence = work / "private", work / "evidence"
    require(
        not private.is_symlink() and not evidence.is_symlink(),
        "Symlinked external state/evidence directory",
    )
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    (private / "tmp").mkdir(mode=0o700, exist_ok=True)
    require(stat.S_IMODE(private.stat().st_mode) == 0o700, "Private directory must be 0700")

    def interrupted(signum, frame):
        raise Refusal("Runner interrupted by signal " + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.mode == "run":
        return run_lane(private, evidence)
    if args.mode == "cleanup":
        identity, _ = admit_event(evidence, entrypoint="cleanup")
        require_event_lease(private, identity)
        cleanup(private, evidence)
        return 0
    try:
        return child(args.mode, private, evidence)
    except Exception as error:
        if hasattr(error, "admission_diagnostic"):
            # Refusal has no resource authority, including retained private state.
            raise
        passwords = tuple(load_lease(private)["passwords"].values())
        (evidence / (args.mode + "-error.log")).write_text(
            redact(traceback.format_exc(), passwords)
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
