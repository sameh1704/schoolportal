import os
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from .ad_service import authenticate_ad_user, parse_username
from .file_access import detect_display_os
from .forms import ADLoginForm
from .models import AuditLoginAttempt, Favorite, FileAccessLog, OUShareMapping, UserPreference
from .ou_access import allowed_paths_for_ou, ou_resources, resolve_ou_request_path
from .thumbnails import get_thumbnail


# ============================================================================
# File kind mapping & helpers (NEW)
# ============================================================================

FILE_KIND_MAP = {
    # Video
    ".mp4": "video", ".webm": "video", ".mkv": "video", ".avi": "video",
    ".mov": "video", ".flv": "video", ".wmv": "video", ".m4v": "video",
    ".ts": "video", ".3gp": "video", ".ogv": "video",
    # PDF
    ".pdf": "pdf",
    # Presentations
    ".pptx": "presentation", ".ppt": "presentation", ".odp": "presentation",
    ".key": "presentation",
    # Documents
    ".docx": "document", ".doc": "document", ".odt": "document",
    ".rtf": "document", ".txt": "document", ".md": "document",
    # Spreadsheets
    ".xlsx": "spreadsheet", ".xls": "spreadsheet", ".ods": "spreadsheet",
    ".csv": "spreadsheet",
    # Images
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".webp": "image", ".bmp": "image", ".svg": "image", ".ico": "image",
    ".tiff": "image", ".tif": "image", ".heic": "image",
    # Archives
    ".zip": "archive", ".rar": "archive", ".7z": "archive",
    ".tar": "archive", ".gz": "archive", ".bz2": "archive",
    ".xz": "archive", ".iso": "archive",
}

KIND_LABELS = {
    "folder": "مجلد",
    "video": "فيديو",
    "pdf": "ملف PDF",
    "presentation": "عرض تقديمي",
    "document": "مستند",
    "spreadsheet": "جدول بيانات",
    "image": "صورة",
    "archive": "أرشيف",
    "other": "ملف",
}

# Default view mode (validated against allowlist on server)
VALID_VIEW_MODES = {
    "extra-large", "large", "medium", "small",
    "list", "details", "tiles", "content"
}
DEFAULT_VIEW_MODE = "tiles"


def get_file_kind(name: str, is_directory: bool) -> str:
    """Return a semantic kind key for a file or folder name."""
    if is_directory:
        return "folder"
    ext = Path(name).suffix.lower()
    return FILE_KIND_MAP.get(ext, "other")


def format_size(size_bytes: int | None) -> str:
    """Format file size in human-readable form (KB/MB/GB)."""
    if size_bytes is None or size_bytes < 0:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size_bytes /= 1024
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
    return f"{size_bytes:.1f} PB"


def format_modified_time(timestamp: float | None) -> str:
    """Format a file modification timestamp for the browser listing."""
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.get_current_timezone(),
    ).strftime("%Y-%m-%d %H:%M")


def sort_entries(entries: list[dict]) -> list[dict]:
    """Sort entries: folders first, then name (case-insensitive, natural-ish)."""
    def sort_key(item):
        name = item["name"]
        return (not item["is_directory"], name.casefold())
    return sorted(entries, key=sort_key)


def build_material_entry(entry: os.DirEntry, root: str) -> dict:
    """Build display metadata without exposing an absolute mounted path."""
    try:
        is_directory = entry.is_dir(follow_symlinks=False)
    except OSError:
        is_directory = False

    name = entry.name
    extension = Path(name).suffix.lower()
    kind = get_file_kind(name, is_directory)
    size_bytes = None
    modified_timestamp = None
    try:
        stat = entry.stat(follow_symlinks=False)
        if not is_directory:
            size_bytes = stat.st_size
        modified_timestamp = stat.st_mtime
    except OSError:
        pass

    return {
        "name": name,
        "is_directory": is_directory,
        "extension": extension,
        "kind": kind,
        "icon_kind": kind if kind in {"folder", "video", "pdf", "presentation", "document", "spreadsheet", "image"} else "generic",
        "kind_label": KIND_LABELS.get(kind, KIND_LABELS["other"]),
        "size": format_size(size_bytes) if size_bytes is not None else "",
        "size_bytes": size_bytes,
        "modified": format_modified_time(modified_timestamp),
        "modified_timestamp": int(modified_timestamp) if modified_timestamp is not None else "",
        "relative_path": os.path.relpath(os.path.realpath(entry.path), root).replace(os.sep, "/"),
        "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
    }


def get_validated_view_mode(value) -> str:
    """Get view mode from ?view= query param, validate against allowlist."""
    view = str(value or "").strip().lower()
    if view in VALID_VIEW_MODES:
        return view
    return DEFAULT_VIEW_MODE


def portal_user(request):
    """Return the server-side user record for the authenticated AD session."""
    username = str(request.session.get("ad_user", {}).get("username", "")).strip()
    if not username:
        raise PermissionDenied
    user, _ = get_user_model().objects.get_or_create(username=username)
    return user


def safe_log_path(value):
    value = str(value or "").replace("\\", "/")
    if value.startswith("/") or ".." in value.split("/"):
        return ""
    return value[:1000]


def log_file_access(request, action, root_index=None, relative_path="", user=None):
    try:
        FileAccessLog.objects.create(
            user=user,
            root_index=root_index,
            relative_path=safe_log_path(relative_path),
            extension=Path(safe_log_path(relative_path)).suffix.lower()[:20],
            action=action,
            client_ip=get_client_ip(request) or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
    except Exception:
        pass


# ============================================================================
# Existing views (unchanged authorization/path logic)
# ============================================================================

def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def audit_login(username, success, request, reason=""):
    AuditLoginAttempt.objects.create(
        username=username or "unknown",
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        success=success,
        reason=reason,
    )


def rate_limited_for_login(username, request):
    window_minutes = getattr(settings, "LOGIN_RATE_WINDOW_MINUTES", 15)
    limit = getattr(settings, "LOGIN_RATE_LIMIT", 5)
    threshold = timezone.now() - timedelta(minutes=window_minutes)
    recent_failures = AuditLoginAttempt.objects.filter(
        username=username,
        success=False,
        created_at__gte=threshold,
    ).count()
    return recent_failures >= limit


def portal_login_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.session.get("ad_user"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapped


def health_check_view(request):
    return JsonResponse({"status": "ok", "service": "portal"})


def login_view(request):
    if request.session.get("ad_user"):
        return redirect("dashboard")

    form = ADLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not getattr(settings, "AD_AUTH_READY", False):
            missing_items = getattr(settings, "AD_CONFIG_ERRORS", []) + getattr(settings, "AD_AUTH_CONFIG_ERRORS", [])
            missing = ", ".join(missing_items or ["AD authentication configuration"])
            audit_login(parse_username(form.cleaned_data["username"]), False, request, reason="ad_config_missing")
            form.add_error(None, f"Active Directory configuration is incomplete for authentication. Missing: {missing}. No user credentials were sent.")
            return render(request, "school_portal/login.html", {"form": form})

        username = parse_username(form.cleaned_data["username"])
        password = form.cleaned_data["password"]

        if rate_limited_for_login(username, request):
            audit_login(username, False, request, reason="rate_limited")
            form.add_error(None, "Too many failed login attempts. Please try again later.")
            return render(request, "school_portal/login.html", {"form": form})

        try:
            ad_user = authenticate_ad_user(username, password)
        except Exception:
            audit_login(username, False, request, reason="invalid_credentials")
            form.add_error(None, "Invalid username or password.")
        else:
            audit_login(username, True, request, reason="success")
            request.session["ad_user"] = {
                "username": ad_user["username"],
                "display_name": ad_user["display_name"],
                "ou": ad_user.get("ou", ""),
            }
            request.session["display_os"] = detect_display_os(os.getenv("DISPLAY_OS") or os.getenv("INTERACTIVE_DISPLAY_OS") or getattr(settings, "DISPLAY_OS", "windows"))
            request.session.set_expiry(getattr(settings, "SESSION_COOKIE_AGE", 900))
            return redirect("dashboard")

    return render(request, "school_portal/login.html", {"form": form})


@portal_login_required
def dashboard_view(request):
    ad_user = request.session.get("ad_user", {})
    resources = ou_resources(
        ad_user.get("ou", ""),
        OUShareMapping.get_ou_subject_map(),
        settings.SHARE_MOUNT_ROOT,
    )
    display_os = detect_display_os(request.session.get("display_os") or os.getenv("DISPLAY_OS") or os.getenv("INTERACTIVE_DISPLAY_OS") or getattr(settings, "DISPLAY_OS", "windows"))

    return render(
        request,
        "school_portal/dashboard.html",
        {
            "display_name": ad_user.get("display_name") or ad_user.get("username") or "Teacher",
            "username": ad_user.get("username") or "teacher",
            "resources": resources,
            "share_mapping_configured": bool(OUShareMapping.get_ou_subject_map()),
            "display_os": display_os,
        },
    )


def _requested_material_path(request):
    ad_user = request.session.get("ad_user", {})
    allowed_roots = allowed_paths_for_ou(
        ad_user.get("ou", ""),
        OUShareMapping.get_ou_subject_map(),
        settings.SHARE_MOUNT_ROOT,
    )
    return resolve_ou_request_path(
        allowed_roots,
        request.GET.get("root", "0"),
        request.GET.get("path", ""),
    )


@portal_login_required
@never_cache
@require_safe
def material_browser_view(request):
    root_index, root, current_path = _requested_material_path(request)
    if not os.path.isdir(current_path):
        raise Http404("Directory not found")

    entries = []
    try:
        with os.scandir(current_path) as iterator:
            for entry in iterator:
                if entry.is_symlink():
                    continue
                resolved_entry = os.path.realpath(entry.path)
                try:
                    if os.path.commonpath((resolved_entry, root)) != root:
                        continue
                except ValueError:
                    continue
                entries.append(build_material_entry(entry, root))
    except PermissionError:
        raise PermissionDenied from None

    entries = sort_entries(entries)

    current_relative_path = os.path.relpath(current_path, root)
    if current_relative_path == ".":
        current_relative_path = ""
    parent_path = os.path.dirname(current_relative_path).replace(os.sep, "/")
    is_root = not current_relative_path
    breadcrumbs = []
    parts = [part for part in current_relative_path.split("/") if part]
    for index, part in enumerate(parts):
        breadcrumbs.append({"name": part, "path": "/".join(parts[: index + 1])})

    user = portal_user(request)
    preference, _ = UserPreference.objects.get_or_create(user=user)
    requested_view = request.GET.get("view")
    if requested_view is not None:
        view_mode = get_validated_view_mode(requested_view)
        if view_mode != preference.materials_view:
            preference.materials_view = view_mode
            preference.save(update_fields=["materials_view", "updated_at"])
    else:
        view_mode = get_validated_view_mode(preference.materials_view)

    favorites = []
    for favorite in Favorite.objects.filter(user=user):
        try:
            _, favorite_root, favorite_path = _requested_material_path_for(favorite.root_index, favorite.relative_path, request)
        except (PermissionDenied, Http404):
            continue
        if not os.path.exists(favorite_path):
            continue
        favorites.append({
            "name": os.path.basename(favorite_path) or os.path.basename(favorite_root),
            "root_index": favorite.root_index,
            "relative_path": favorite.relative_path,
            "is_directory": favorite.is_directory,
        })
    favorite_keys = {(favorite.root_index, favorite.relative_path) for favorite in Favorite.objects.filter(user=user)}
    for entry in entries:
        entry["is_favorite"] = (root_index, entry["relative_path"]) in favorite_keys

    return render(
        request,
        "school_portal/material_browser.html",
        {
            "resource_name": os.path.basename(root.rstrip(os.sep)) or "المواد",
            "entries": entries,
            "root_index": root_index,
            "current_path": current_relative_path,
            "parent_path": parent_path,
            "is_root": is_root,
            "breadcrumbs": breadcrumbs,
            "view_mode": view_mode,
            "valid_view_modes": sorted(VALID_VIEW_MODES),
            "favorites": sorted(favorites, key=lambda item: (not item["is_directory"], item["name"].casefold())),
            "idle_seconds": settings.SESSION_COOKIE_AGE,
        },
    )


def _requested_material_path_for(root_index, relative_path, request):
    ad_user = request.session.get("ad_user", {})
    allowed_roots = allowed_paths_for_ou(
        ad_user.get("ou", ""),
        OUShareMapping.get_ou_subject_map(),
        settings.SHARE_MOUNT_ROOT,
    )
    return resolve_ou_request_path(allowed_roots, root_index, relative_path)


@portal_login_required
@require_POST
def favorite_toggle_view(request):
    root_index = request.POST.get("root", "")
    relative_path = request.POST.get("path", "")
    try:
        root_index, _, target_path = _requested_material_path_for(root_index, relative_path, request)
    except PermissionDenied:
        return JsonResponse({"detail": "غير مسموح"}, status=403)
    if not os.path.exists(target_path):
        raise Http404("File not found")
    user = portal_user(request)
    relative_path = os.path.relpath(target_path, _requested_material_path_for(root_index, "", request)[1]).replace(os.sep, "/")
    favorite, created = Favorite.objects.get_or_create(
        user=user,
        root_index=root_index,
        relative_path=relative_path,
        defaults={"is_directory": os.path.isdir(target_path)},
    )
    if created and Favorite.objects.filter(user=user).count() > 100:
        favorite.delete()
        return JsonResponse({"detail": "الحد الأقصى للمفضلة هو 100 عنصر."}, status=400)
    if not created:
        favorite.delete()
    return JsonResponse({"favorite": created})


@portal_login_required
@require_POST
def keep_alive_view(request):
    request.session.modified = True
    return JsonResponse({"idle_seconds": settings.SESSION_COOKIE_AGE})


@portal_login_required
@require_safe
def thumbnail_view(request):
    try:
        root_index, root, source = _requested_material_path(request)
    except PermissionDenied:
        return HttpResponse(status=403)
    if not os.path.isfile(source):
        return HttpResponse(status=404)
    relative_path = os.path.relpath(source, root).replace(os.sep, "/")
    thumbnail = get_thumbnail(root, relative_path, Path(source))
    if not thumbnail:
        return HttpResponse(status=204)
    response = FileResponse(thumbnail.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=300"
    return response


@portal_login_required
@require_safe
def material_download_view(request):
    try:
        root_index, root, file_path = _requested_material_path(request)
    except PermissionDenied:
        log_file_access(request, FileAccessLog.ACTION_DENIED, relative_path=request.GET.get("path", ""))
        raise
    if not os.path.isfile(file_path):
        raise Http404("File not found")
    try:
        file_handle = open(file_path, "rb")
    except PermissionError:
        raise PermissionDenied from None
    except OSError:
        raise Http404("File not found") from None
    user = portal_user(request)
    relative_path = os.path.relpath(file_path, root).replace(os.sep, "/")
    range_header = request.META.get("HTTP_RANGE", "")
    if not range_header or range_header.startswith("bytes=0-"):
        log_file_access(request, FileAccessLog.ACTION_OPEN, root_index, relative_path, user)
    extension = Path(file_path).suffix.lower()
    return FileResponse(
        file_handle,
        as_attachment=extension not in {".mp4", ".webm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"},
        filename=os.path.basename(file_path),
        content_type=mimetypes.guess_type(file_path)[0] or "application/octet-stream",
    )


@portal_login_required
@require_POST
def logout_view(request):
    request.session.flush()
    return redirect("login")
