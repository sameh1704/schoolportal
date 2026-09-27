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

if [ -n "${SMB_HOST:-}" ] || [ -n "${SMB_MOUNTS:-}" ]; then
    case "$SHARE_MOUNT_ROOT" in
        /*) ;;
        *) fail "SHARE_MOUNT_ROOT must be an absolute path" ;;
    esac

    [ -n "${SMB_HOST:-}" ] || fail "SMB_HOST is required"
    # SMB_CREDENTIALS_FILE is optional now if per-share credentials are provided
    [ -n "${SMB_MOUNTS:-}" ] || fail "SMB_MOUNTS is required (comma-separated slug=share entries)"

    case "$SMB_HOST" in
        *[!A-Za-z0-9._:-]*) fail "SMB_HOST contains unsupported characters" ;;
    esac
    case "$APP_UID:$APP_GID" in
        *[!0-9:]*) fail "APP_UID and APP_GID must be numeric" ;;
    esac

    mkdir -p "$SHARE_MOUNT_ROOT"

    set -f
    mount_count=0
    for mount_spec in $(printf '%s' "$SMB_MOUNTS" | tr ',' ' '); do
        # Parse mount_spec: slug=share[:username:password:domain]
        case "$mount_spec" in
            *=*) slug=${mount_spec%%=*}; rest=${mount_spec#*=} ;;
            *) fail "Invalid SMB_MOUNTS entry '$mount_spec'; expected slug=share[:username:password:domain]" ;;
        esac
        [ -n "$slug" ] && [ -n "$rest" ] || fail "Invalid empty slug or share in SMB_MOUNTS"
        case "$slug" in
            *[!A-Za-z0-9._-]*|.|..) fail "Invalid mount slug '$slug'" ;;
        esac

        # Parse share and optional credentials from rest
        # rest format: share OR share:username:password:domain
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

        printf '%s' "$share" | grep -Eq '^[A-Za-z0-9._$-]+$' \
            || fail "Invalid SMB share name in mount entry '$slug'; use letters, digits, dot, underscore, dollar, or hyphen"
        mount_count=$((mount_count + 1))

        mount_path="$SHARE_MOUNT_ROOT/$slug"
        mkdir -p "$mount_path"
        if mountpoint -q "$mount_path"; then
            printf '[smb-mount] Already mounted: %s\n' "$mount_path"
            continue
        fi

        # Determine credentials file to use
        cred_file=""
        if [ -n "$mount_user" ] && [ -n "$mount_pass" ]; then
            # Create temporary credentials file for this share
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
            # Clean up temp cred file on failure
            if [ -n "$mount_user" ] && [ -f "$cred_file" ]; then
                rm -f "$cred_file"
            fi
            fail "Mount failed for configured share '$slug' (share=$share); Django will not start"
        fi

        # Clean up temp cred file after successful mount
        if [ -n "$mount_user" ] && [ -f "$cred_file" ]; then
            rm -f "$cred_file"
        fi
    done

    [ "$mount_count" -gt 0 ] || fail "SMB_MOUNTS contains no valid share entries"
else
    printf '[smb-mount] SMB is not configured; skipping mounts\n'
fi
printf '[static] Collecting static files\n'
if ! setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all --reuid "$APP_UID" --regid "$APP_GID" --init-groups python manage.py collectstatic --noinput; then
    fail "collectstatic failed; Django will not start"
fi
[ "$#" -gt 0 ] || fail "No application command was supplied"
printf '[smb-mount] All configured shares are mounted; dropping to app uid=%s gid=%s\n' "$APP_UID" "$APP_GID"
exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
    --reuid "$APP_UID" --regid "$APP_GID" --init-groups "$@"