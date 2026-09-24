from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import AuditLoginAttempt


admin.site.site_header = "إدارة بوابة المدرسة"
admin.site.site_title = "إدارة البوابة"
admin.site.index_title = "مركز الإدارة والمصادقة"

User = get_user_model()


class PortalUserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "display_name",
        "email",
        "active_status",
        "staff_status",
        "last_login",
    )
    list_display_links = ("username", "display_name")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    list_per_page = 25
    date_hierarchy = "date_joined"
    change_list_template = "admin/auth/user/change_list.html"

    @admin.display(description="الاسم", ordering="first_name")
    def display_name(self, obj):
        return obj.get_full_name() or "—"

    @admin.display(description="الحساب", boolean=True, ordering="is_active")
    def active_status(self, obj):
        return obj.is_active

    @admin.display(description="موظف إداري", boolean=True, ordering="is_staff")
    def staff_status(self, obj):
        return obj.is_staff

    def changelist_view(self, request, extra_context=None):
        summary = User.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
            staff=Count("pk", filter=Q(is_staff=True)),
        )
        context = {**(extra_context or {}), "user_summary": summary}
        return super().changelist_view(request, extra_context=context)


if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, PortalUserAdmin)


@admin.register(AuditLoginAttempt)
class AuditLoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "result_badge", "ip_address", "reason")
    list_filter = ("success", "created_at")
    search_fields = ("username", "ip_address", "reason")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    fields = ("created_at", "username", "success", "reason", "ip_address", "user_agent")
    readonly_fields = fields

    @admin.display(description="النتيجة", ordering="success")
    def result_badge(self, obj):
        if obj.success:
            return format_html('<span class="portal-status portal-status--ok">نجاح</span>')
        return format_html('<span class="portal-status portal-status--bad">فشل</span>')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
