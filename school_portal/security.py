import ntpath
from pathlib import PureWindowsPath

from django.conf import settings
from django.core.exceptions import ValidationError


def normalize_share_name(value):
    return (value or "").strip().lower().replace("\\", "/")


def get_authorized_share(resource_name):
    normalized_name = normalize_share_name(resource_name)
    for key, path in getattr(settings, "AD_SHARE_GROUPS", {}).items():
        if normalize_share_name(key) == normalized_name:
            return path
    return None


def validate_requested_share(resource_name):
    if not resource_name or any(part in {"..", "."} for part in str(resource_name).replace("\\", "/").split("/")):
        raise ValidationError("Invalid share name.")
    if get_authorized_share(resource_name) is None:
        raise ValidationError("Requested share is not authorized.")
    return get_authorized_share(resource_name)


def ensure_within_share(share_root, requested_path):
    share_normalized = ntpath.normpath(share_root).lower().rstrip("\\/")
    requested_normalized = ntpath.normpath(requested_path).lower().rstrip("\\/")

    if any(part == ".." for part in requested_normalized.replace("\\", "/").split("/")):
        raise ValidationError("Path traversal is not allowed.")

    if requested_normalized == share_normalized:
        return True
    if requested_normalized.startswith(share_normalized + "\\") or requested_normalized.startswith(share_normalized + "/"):
        return True
    raise ValidationError("Requested path is outside the authorized share.")


def resolve_share_target(resource_name, subpath=""):
    share_root = validate_requested_share(resource_name)
    raw_path = str(subpath or "").strip()
    if not raw_path:
        return {"share_root": share_root, "target_path": share_root}

    if raw_path.startswith("/") or raw_path.startswith("\\"):
        raw_path = raw_path.lstrip("/\\")

    if any(part in {"..", "."} for part in raw_path.replace("\\", "/").split("/")):
        raise ValidationError("Path traversal is not allowed.")

    candidate = ntpath.join(share_root, raw_path)
    ensure_within_share(share_root, candidate)
    return {"share_root": share_root, "target_path": candidate}
