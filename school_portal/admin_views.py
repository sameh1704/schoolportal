from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse

from .ad_service import authenticate_ad_user, parse_username
from .forms import ADAuthenticationTestForm
from .models import AuditLoginAttempt
from .views import audit_login, rate_limited_for_login


def admin_authentication_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    initial = {"username": getattr(settings, "AD_TEST_USERNAME", "")}
    form = ADAuthenticationTestForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        username = parse_username(form.cleaned_data["username"])
        password = form.cleaned_data["password"]

        if not settings.AD_AUTH_READY:
            missing = settings.AD_CONFIG_ERRORS + settings.AD_AUTH_CONFIG_ERRORS
            messages.error(request, "إعدادات مصادقة AD غير مكتملة: " + ", ".join(missing))
        elif rate_limited_for_login(username, request):
            audit_login(username, False, request, reason="rate_limited")
            messages.error(request, "محاولات كثيرة. انتظر قليلًا ثم حاول مرة أخرى.")
        else:
            try:
                ad_user = authenticate_ad_user(username, password)
            except Exception:
                audit_login(username, False, request, reason="invalid_credentials")
                messages.error(request, "تعذرت مصادقة الحساب. تحقق من البيانات وحالة اتصال AD.")
            else:
                audit_login(username, True, request, reason="admin_auth_test")
                messages.success(request, f"تمت مصادقة الحساب بنجاح: {ad_user['display_name']}")
                form = ADAuthenticationTestForm(initial={"username": username})

    encryption = settings.AD_LDAP_ENCRYPTION.upper() if settings.AD_LDAP_ENCRYPTION else "غير مضبوط"
    port = settings.AD_LDAPS_PORT if settings.AD_LDAP_ENCRYPTION == "ldaps" else settings.AD_PORT
    status = {
        "ready": settings.AD_AUTH_READY,
        "server": settings.AD_LDAP_SERVER or settings.AD_HOSTNAME,
        "domain": settings.AD_DOMAIN,
        "base_dn": settings.AD_USER_SEARCH_BASE or settings.AD_BASE_DN,
        "transport": encryption,
        "port": port,
        "auth_method": settings.AD_AUTH_METHOD or "غير مضبوط",
        "certificate_validation": "مفعّل" if settings.AD_LDAP_ENCRYPTION in {"ldaps", "starttls"} else "غير مفعّل",
    }
    context = {
        **admin.site.each_context(request),
        "title": "مصادقة Active Directory",
        "status": status,
        "form": form,
        "recent_attempts": AuditLoginAttempt.objects.order_by("-created_at")[:8],
        "users_url": reverse("admin:auth_user_changelist"),
        "attempts_url": reverse("admin:school_portal_auditloginattempt_changelist"),
    }
    return render(request, "admin/authentication.html", context)
