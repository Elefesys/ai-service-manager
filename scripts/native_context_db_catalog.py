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
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
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
MODULES = (
    "tests/test_m3_1_native_context_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
)
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
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_REPOSITORY",
        "GITHUB_REF",
        "GITHUB_EVENT_NAME",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(
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
        "Full two-module collection is required",
    )
    require(not deselected, "Deselected tests are forbidden")
    require(
        not any(r["outcome"] == "skipped" or r["xfail"] for r in reports),
        "Skip/xfail cannot produce PASS",
    )
    if exit_code == 0:
        passed = {r["nodeid"] for r in reports if r["when"] == "call" and r["outcome"] == "passed"}
        require(
            passed == set(nodes) and not any(r["outcome"] == "failed" for r in reports),
            "Incomplete test execution cannot produce PASS",
        )


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
    lease = load_lease(private)
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
    try:
        require(
            os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == EXECUTION_REF
            and os.environ.get("GITHUB_REPOSITORY") == "Elefesys/ai-service-manager",
            "Only the dedicated C0 push event is authorized",
        )
        require(sys.version_info[:2] == (3, 13), "Python 3.13 required; no patched runtime")
        source_sha = os.environ["GITHUB_SHA"]
        tree, manifest = require_source(ROOT, source_sha)
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
                "head": source_sha,
                "tree": tree,
                "event": "push",
                "ref": EXECUTION_REF,
                "run_id": os.environ["GITHUB_RUN_ID"],
                "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
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
        _, docker_version = commands.run(
            ["docker", "version", "--format", "{{json .Server.Version}}"]
        )
        write_json(
            evidence / "versions.json",
            {
                "python": sys.version,
                "uv": uv_version.decode().strip(),
                "git": git_version.decode().strip(),
                "docker_server": json.loads(docker_version),
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
        require_source(ROOT, source_sha)
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
    except Exception:
        passwords = ()
        if (private / "state.json").exists():
            passwords = tuple(load_lease(private)["passwords"].values())
        (evidence / "runner-error.log").write_text(redact(traceback.format_exc(), passwords))
    finally:
        try:
            collect_owned_logs(private, evidence)
        except Exception:
            receipt.update(result="FAIL", owned_log_capture="REFUSED_OR_FAILED")
            result = 1
            (evidence / "owned-log-error.log").write_text(
                redact(traceback.format_exc(), commands.passwords)
            )
        try:
            cleanup(private, evidence)
            final_tree, _ = require_source(ROOT, os.environ.get("GITHUB_SHA", ""))
            receipt.update(
                clean_tracked_and_untracked_after=True, final_tree=final_tree, owned_cleanup="PASS"
            )
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "carrier", "catalog", "cleanup"))
    args = parser.parse_args()
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
        cleanup(private, evidence)
        return 0
    try:
        return child(args.mode, private, evidence)
    except Exception:
        passwords = tuple(load_lease(private)["passwords"].values())
        (evidence / (args.mode + "-error.log")).write_text(
            redact(traceback.format_exc(), passwords)
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
