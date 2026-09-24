#!/bin/sh
set -eu

SHARE_MOUNT_ROOT=${SHARE_MOUNT_ROOT:-/app/shares}
APP_UID=${APP_UID:-10001}
APP_GID=${APP_GID:-10001}

fail() {
    printf '[smb-mount] ERROR: %s\n' "$*" >&2
    exit 1
}

case "$SHARE_MOUNT_ROOT" in
    /*) ;;
    *) fail "SHARE_MOUNT_ROOT must be an absolute path" ;;
esac

[ -n "${SMB_HOST:-}" ] || fail "SMB_HOST is required"
[ -n "${SMB_CREDENTIALS_FILE:-}" ] || fail "SMB_CREDENTIALS_FILE is required"
[ -r "$SMB_CREDENTIALS_FILE" ] || fail "SMB credentials file is missing or unreadable: $SMB_CREDENTIALS_FILE"
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
    case "$mount_spec" in
        *=*) slug=${mount_spec%%=*}; share=${mount_spec#*=} ;;
        *) fail "Invalid SMB_MOUNTS entry '$mount_spec'; expected slug=share" ;;
    esac
    [ -n "$slug" ] && [ -n "$share" ] || fail "Invalid empty slug or share in SMB_MOUNTS"
    case "$slug" in
        *[!A-Za-z0-9._-]*|.|..) fail "Invalid mount slug '$slug'" ;;
    esac
    printf '%s' "$share" | grep -Eq '^[A-Za-z0-9._$-]+$' \
        || fail "Invalid SMB share name in mount entry '$slug'; use letters, digits, dot, underscore, dollar, or hyphen"
    mount_count=$((mount_count + 1))

    mount_path="$SHARE_MOUNT_ROOT/$slug"
    mkdir -p "$mount_path"
    if mountpoint -q "$mount_path"; then
        printf '[smb-mount] Already mounted: %s\n' "$mount_path"
        continue
    fi

    printf '[smb-mount] Mounting //%s/%s at %s (read-only)\n' "$SMB_HOST" "$share" "$mount_path"
    if ! mount -t cifs "//$SMB_HOST/$share" "$mount_path" \
        -o "credentials=$SMB_CREDENTIALS_FILE,vers=3.0,ro,sec=ntlmssp,uid=$APP_UID,gid=$APP_GID,nosuid,nodev"; then
        fail "Mount failed for configured share '$slug'; Django will not start"
    fi
done

[ "$mount_count" -gt 0 ] || fail "SMB_MOUNTS contains no valid share entries"
[ "$#" -gt 0 ] || fail "No application command was supplied"
printf '[smb-mount] All configured shares are mounted; dropping to app uid=%s gid=%s\n' "$APP_UID" "$APP_GID"
exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
    --reuid "$APP_UID" --regid "$APP_GID" --init-groups "$@"
