#!/bin/sh
set -eu
# ADMIN-ONLY, idempotent preflight for databases already upgraded to 0003.
# The URL must identify a database administrator; no production credential contract
# is introduced by this LOCAL/TEST helper.
: "${ASM_ADMIN_DATABASE_URL:?set ASM_ADMIN_DATABASE_URL to an admin PostgreSQL URL}"
psql "$ASM_ADMIN_DATABASE_URL" --single-transaction --set=ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions VERSION '1.8';
DO $verify$
DECLARE ok boolean;
BEGIN
  SELECT e.extversion = '1.8' AND n.nspname = 'extensions'
    AND EXISTS (
      SELECT 1 FROM pg_catalog.pg_opclass oc
      JOIN pg_catalog.pg_namespace onsp ON onsp.oid=oc.opcnamespace
      JOIN pg_catalog.pg_am am ON am.oid=oc.opcmethod
      JOIN pg_catalog.pg_opfamily ofam ON ofam.oid=oc.opcfamily
      JOIN pg_catalog.pg_amop ao ON ao.amopfamily=ofam.oid
      JOIN pg_catalog.pg_operator opr ON opr.oid=ao.amopopr
      WHERE onsp.nspname='extensions' AND oc.opcname='gist_uuid_ops'
        AND am.amname='gist' AND ao.amopstrategy=3
        AND opr.oprname='=' AND opr.oprleft='uuid'::pg_catalog.regtype
        AND opr.oprright='uuid'::pg_catalog.regtype)
  INTO ok
  FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
  WHERE e.extname='btree_gist';
  IF ok IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'M1.3 btree_gist prerequisite is incompatible';
  END IF;
END $verify$;
SQL
