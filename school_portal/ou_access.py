import ntpath
import os
from pathlib import Path

from django.core.exceptions import PermissionDenied
from ldap3.core.exceptions import LDAPInvalidDnError
from ldap3.utils.dn import parse_dn


def extract_user_ou(distinguished_name, depth_index=0):
    """Return the OU at depth_index from a leaf-first LDAP distinguished name."""
    if not distinguished_name or depth_index < 0:
        return ""

    try:
        parsed_dn = parse_dn(str(distinguished_name))
    except (LDAPInvalidDnError, TypeError, ValueError):
        return ""

    ous = [value for attribute, value, _ in parsed_dn if attribute.casefold() == "ou"]
    return ous[depth_index] if depth_index < len(ous) else ""


def _is_within(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except (OSError, ValueError):
        return False


def allowed_paths_for_ou(ou_name, ou_subject_map, mount_root):
    """Resolve configured paths for an OU, failing closed outside the mount."""
    if not ou_name:
        return []

    configured_paths = next(
        (paths for name, paths in (ou_subject_map or {}).items() if str(name).casefold() == ou_name.casefold()),
        [],
    )
    if not isinstance(configured_paths, (list, tuple)):
        return []

    real_mount_root = os.path.realpath(os.fspath(mount_root))
    allowed_paths = []
    for configured_path in configured_paths:
        path = os.fspath(configured_path)
        if not os.path.isabs(path):
            continue
        real_path = os.path.realpath(path)
        if _is_within(real_path, real_mount_root) and real_path != real_mount_root:
            allowed_paths.append(real_path)
    return allowed_paths


def resolve_ou_request_path(allowed_roots, root_index, relative_path=""):
    """Resolve a relative request path and reject traversal or symlink escapes."""
    if not allowed_roots:
        raise PermissionDenied

    try:
        index = int(root_index)
    except (TypeError, ValueError):
        raise PermissionDenied from None
    if index < 0 or index >= len(allowed_roots):
        raise PermissionDenied

    requested = str(relative_path or "")
    normalized = requested.replace("\\", "/")
    if "\x00" in normalized or os.path.isabs(normalized) or ntpath.isabs(requested):
        raise PermissionDenied
    if any(part == ".." for part in normalized.split("/")):
        raise PermissionDenied

    root = os.path.realpath(allowed_roots[index])
    candidate = os.path.realpath(os.path.join(root, normalized))
    if not _is_within(candidate, root):
        raise PermissionDenied
    return index, root, candidate


def ou_resources(ou_name, ou_subject_map, mount_root):
    resources = []
    for index, path in enumerate(allowed_paths_for_ou(ou_name, ou_subject_map, mount_root)):
        resources.append({"name": Path(path).name or "المواد", "root_index": index})
    return resources
