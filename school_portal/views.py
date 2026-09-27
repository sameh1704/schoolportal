import os
import mimetypes
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_safe

from .ad_service import authenticate_ad_user, parse_username
from .file_access import detect_display_os
from .forms import ADLoginForm
from .models import AuditLoginAttempt, OUShareMapping
from .ou_access import allowed_paths_for_ou, ou_resources, resolve_ou_request_path


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
                relative_path = os.path.relpath(resolved_entry, root).replace(os.sep, "/")
                entries.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(follow_symlinks=False),
                    "relative_path": relative_path,
                    "mime": mimetypes.guess_type(entry.name)[0] or "application/octet-stream",
                })
    except PermissionError:
        raise PermissionDenied from None
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].casefold()))

    current_relative_path = os.path.relpath(current_path, root)
    if current_relative_path == ".":
        current_relative_path = ""
    parent_path = os.path.dirname(current_relative_path).replace(os.sep, "/")
    is_root = not current_relative_path

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
        },
    )


@portal_login_required
@require_safe
def material_download_view(request):
    _, _, file_path = _requested_material_path(request)
    if not os.path.isfile(file_path):
        raise Http404("File not found")
    try:
        file_handle = open(file_path, "rb")
    except PermissionError:
        raise PermissionDenied from None
    except OSError:
        raise Http404("File not found") from None
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=os.path.basename(file_path),
        content_type=mimetypes.guess_type(file_path)[0] or "application/octet-stream",
    )


@portal_login_required
def logout_view(request):
    request.session.flush()
    return redirect("login")
