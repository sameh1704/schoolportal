#!/bin/sh
set -eu

exec docker compose run --rm --no-deps \
    --entrypoint /bin/sh portal-web -c \
    'exec smbclient -L "//$SMB_HOST" -A "$SMB_CREDENTIALS_FILE"'
