#!/bin/sh
set -eu

SHARE_MOUNT_ROOT=${SHARE_MOUNT_ROOT:-/app/shares}
APP_UID=${APP_UID:-10001}
APP_GID=${APP_GID:-10001}
DJANGO_ENV_FILE=${DJANGO_ENV_FILE:-/run/secrets/django_env}

fail() {
    printf '[smb-mount] ERROR: %s\n' "$*" >&2
    exit 1
}

if [ -r "$DJANGO_ENV_FILE" ]; then
    cp "$DJANGO_ENV_FILE" /app/.env
    chown "$APP_UID:$APP_GID" /app/.env
    chmod 0400 /app/.env
fi

# Wait for database to be ready
if [ -n "${POSTGRES_HOST:-}" ]; then
    printf '[smb-mount] Waiting for database at %s:%s...\n' "${POSTGRES_HOST}" "${POSTGRES_PORT:-5432}"
    for i in $(seq 1 30); do
        if pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-portal}" -d "${POSTGRES_DB:-portal}" >/dev/null 2>&1; then
            printf '[smb-mount] Database is ready\n'
            break
        fi
        sleep 1
    done
fi

# Load SMB mounts from database if possible, otherwise fall back to .env
load_smb_mounts_from_db() {
    python3 -c "
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'portal.settings')
sys.path.insert(0, '/app')

try:
    django.setup()
    from school_portal.models import OUShareMapping
    
    mappings = OUShareMapping.objects.filter(is_active=True)
    mounts = []
    for m in mappings:
        creds = m.get_smb_credentials()
        if creds:
            mounts.append(f'{m.share_slug}={m.share_slug}:{creds[\"username\"]}:{creds[\"password\"]}:{creds[\"domain\"]}')
        else:
            mounts.append(f'{m.share_slug}={m.share_slug}')
    
    if mounts:
        print('\n'.join(mounts))
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    print(f'DB load failed: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
}

# Determine SMB_MOUNTS: try database first, then .env
MOUNTS_TO_PROCESS=""
if [ -n "${SMB_HOST:-}" ]; then
    if DB_MOUNTS=$(load_smb_mounts_from_db) && [ -n "$DB_MOUNTS" ]; then
        printf '[smb-mount] Loaded SMB mounts from database\n'
        MOUNTS_TO_PROCESS="$DB_MOUNTS"
    elif [ -n "${SMB_MOUNTS:-}" ]; then
        printf '[smb-mount] Using SMB_MOUNTS from .env\n'
        MOUNTS_TO_PROCESS=$(printf '%s' "$SMB_MOUNTS" | tr ',' '\n')
    else
        printf '[smb-mount] No SMB mounts configured (neither in DB nor .env); skipping mounts\n'
    fi
fi

if [ -n "$MOUNTS_TO_PROCESS" ]; then
    case "$SHARE_MOUNT_ROOT" in
        /*) ;;
        *) fail "SHARE_MOUNT_ROOT must be an absolute path" ;;
    esac

    [ -n "${SMB_HOST:-}" ] || fail "SMB_HOST is required"

    case "$SMB_HOST" in
        *[!A-Za-z0-9._:-]*) fail "SMB_HOST contains unsupported characters" ;;
    esac
    case "$APP_UID:$APP_GID" in
        *[!0-9:]*) fail "APP_UID and APP_GID must be numeric" ;;
    esac

    mkdir -p "$SHARE_MOUNT_ROOT"

    set -f
    mount_count=0
    while IFS= read -r mount_spec || [ -n "$mount_spec" ]; do
        case "$mount_spec" in
            *=*) slug=${mount_spec%%=*}; rest=${mount_spec#*=} ;;
            *) fail "Invalid SMB_MOUNTS entry '$mount_spec'; expected slug=share[:username:password:domain]" ;;
        esac
        [ -n "$slug" ] && [ -n "$rest" ] || fail "Invalid empty slug or share in SMB_MOUNTS"
        case "$slug" in
            ''|.|..|*/*|*\\*|*:*|*,*) fail "Invalid mount slug '$slug'" ;;
        esac

        if printf '%s' "$rest" | grep -q ':'; then
            share=$(printf '%s' "$rest" | cut -d: -f1)
            mount_user=$(printf '%s' "$rest" | cut -d: -f2)
            mount_pass=$(printf '%s' "$rest" | cut -d: -f3)
            mount_domain=$(printf '%s' "$rest" | cut -d: -f4)
        else
            share=$rest
            mount_user=""
            mount_pass=""
            mount_domain=""
        fi

        printf '%s' "$share" | grep -Eq '^[A-Za-z0-9 ._$-]+$' \
            || fail "Invalid SMB share name in mount entry '$slug'; use letters, digits, spaces, dot, underscore, dollar, or hyphen"
        mount_count=$((mount_count + 1))

        mount_path="$SHARE_MOUNT_ROOT/$slug"
        mkdir -p "$mount_path"
        if mountpoint -q "$mount_path"; then
            printf '[smb-mount] Already mounted: %s\n' "$mount_path"
            continue
        fi

        cred_file=""
        if [ -n "$mount_user" ] && [ -n "$mount_pass" ]; then
            cred_file="/tmp/smb_cred_${slug}"
            printf 'username=%s\npassword=%s\n' "$mount_user" "$mount_pass" > "$cred_file"
            if [ -n "$mount_domain" ]; then
                printf 'domain=%s\n' "$mount_domain" >> "$cred_file"
            fi
            chmod 600 "$cred_file"
            printf '[smb-mount] Using per-share credentials for %s\n' "$slug"
        elif [ -n "${SMB_CREDENTIALS_FILE:-}" ] && [ -r "$SMB_CREDENTIALS_FILE" ]; then
            cred_file="$SMB_CREDENTIALS_FILE"
            printf '[smb-mount] Using default credentials for %s\n' "$slug"
        else
            fail "No credentials available for share '$slug' (slug=$slug, share=$share)"
        fi

        printf '[smb-mount] Mounting //%s/%s at %s (read-only)\n' "$SMB_HOST" "$share" "$mount_path"
        if ! mount -t cifs "//$SMB_HOST/$share" "$mount_path" \
            -o "credentials=$cred_file,vers=3.0,ro,sec=ntlmssp,uid=$APP_UID,gid=$APP_GID,nosuid,nodev"; then
            if [ -n "$mount_user" ] && [ -f "$cred_file" ]; then
                rm -f "$cred_file"
            fi
            printf '[smb-mount] WARNING: Mount failed for configured share %s; continuing without it\n' "$slug" >&2
            continue
        fi

        if [ -n "$mount_user" ] && [ -f "$cred_file" ]; then
            rm -f "$cred_file"
        fi
    done <<EOF
$MOUNTS_TO_PROCESS
EOF

    [ "$mount_count" -gt 0 ] || fail "SMB_MOUNTS contains no valid share entries"
else
    printf '[smb-mount] SMB is not configured; skipping mounts\n'
fi

printf '[django] Applying database migrations\n'
if ! setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all --reuid "$APP_UID" --regid "$APP_GID" --init-groups python manage.py migrate --noinput; then
    fail "database migrations failed; Django will not start"
fi

printf '[static] Collecting static files\n'
if ! setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all --reuid "$APP_UID" --regid "$APP_GID" --init-groups python manage.py collectstatic --noinput; then
    fail "collectstatic failed; Django will not start"
fi
[ "$#" -gt 0 ] || fail "No application command was supplied"
printf '[smb-mount] All configured shares are mounted; dropping to app uid=%s gid=%s\n' "$APP_UID" "$APP_GID"
exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
    --reuid "$APP_UID" --regid "$APP_GID" --init-groups "$@"
