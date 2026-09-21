#!/bin/sh
# LOCAL/TEST only. All mc output is suppressed: aliases can contain credentials.
set -eu
exec 3>&1
exec >/dev/null 2>&1
trap 'echo STORAGE_BOOTSTRAP_FAILED >&3' EXIT
export MC_CONFIG_DIR=/tmp/mc
export MC_HOST_admin="http://${STORAGE_ROOT_USER}:${STORAGE_ROOT_PASSWORD}@${STORAGE_HOST}:9000"
mc ready admin
mc mb --ignore-existing "admin/$STORAGE_BUCKET"
mc anonymous set none "admin/$STORAGE_BUCKET"
# HEAD must distinguish an absent key (404) from denied access (403).
# Listing authority is restricted to this private bucket, never anonymous.
cat > /tmp/runtime-policy.json <<POLICY
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":["arn:aws:s3:::$STORAGE_BUCKET"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":["arn:aws:s3:::$STORAGE_BUCKET/workspaces/*"]}]}
POLICY
mc admin user add admin "$STORAGE_ACCESS_KEY" "$STORAGE_SECRET_KEY"
mc admin policy create admin asm-private /tmp/runtime-policy.json
mc admin policy attach admin asm-private --user "$STORAGE_ACCESS_KEY"
rm -f /tmp/runtime-policy.json
trap - EXIT
echo STORAGE_PRIVATE_BOOTSTRAP_PASS >&3
