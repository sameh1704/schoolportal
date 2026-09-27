from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import AuditLoginAttempt, OUShareMapping


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


@admin.register(OUShareMapping)
class OUShareMappingAdmin(admin.ModelAdmin):
    list_display = ('ou_name', 'share_slug', 'display_name', 'share_path', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('ou_name', 'share_slug', 'display_name', 'description')
    ordering = ('ou_name',)
    list_per_page = 25
    date_hierarchy = 'created_at'
    list_editable = ('is_active',)
    fieldsets = (
        ('\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0627\u0644\u062a\u0639\u0631\u0641', {
            'fields': ('ou_name', 'share_slug', 'is_active'),
            'description': '\u0647\u0630\u0647 \u0627\u0644\u062d\u0642\u0648\u0644 \u0645\u0637\u0644\u0648\u0628\u0629 \u0648\u062a\u062d\u062f\u062f \u0631\u0628\u0637 OU \u0628\u0627\u0644\u0645\u0634\u0627\u0631\u0643\u0629.'
        }),
        ('\u0645\u0633\u0627\u0631 \u0627\u0644\u0645\u0634\u0627\u0631\u0643\u0629', {
            'fields': ('share_path',),
            'description': '\u0627\u0644\u0645\u0633\u0627\u0631 \u062f\u0627\u062e\u0644 \u0627\u0644\u062d\u0627\u0648\u064a\u0629 \u062d\u064a\u062b \u064a\u062a\u0645 mount \u0645\u0634\u0627\u0631\u0631\u0643\u0629 SMB.'
        }),
        ('\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0627\u0644\u0639\u0631\u0636', {
            'fields': ('display_name', 'description'),
            'description': '\u0645\u0639\u0644\u0648\u0645\u0627\u062a \u062a\u0638\u0647\u0631 \u0644\u0644\u0645\u0639\u0644\u0645 \u0641\u064a \u0644\u0648\u062d\u0629 \u0627\u062a\u062d\u0643\u0645 (\u0627\u062e\u062a\u064a\u0627\u0631\u064a\u0629).'
        }),
    )
    readonly_fields = ('created_at', 'updated_at')
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['ou_name'].help_text = '\u0645\u062b\u0627\u0644: MATH-PRIM (\u0627\u0633\u0645 OU \u0643\u0645\u0627 \u064a\u0638\u0647\u0631 \u0641\u064a Active Directory)'
        form.base_fields['share_slug'].help_text = '\u0645\u062b\u0627\u0644: math-prim (\u064a\u062c\u0628 \u0623\u0646 \u064a\u062a\u0637\u0627\u0628\u0642 \u0645\u0639 slug \u0641\u064a SMB_MOUNTS \u0628\u0627\u0644\u062c .env)'
        form.base_fields['share_path'].help_text = '\u0645\u062b\u0627\u0644: /app/shares/math-prim (\u0645\u0633\u0627\u0631 mount \u062f\u0627\u062e\u0644 \u0627\u0644\u062d\u0627\u0648\u064a\u0629)'
        form.base_fields['display_name'].help_text = '\u0645\u062b\u0627\u0644: \u0645\u0648\u0627\u062f \u0627\u0644\u0631\u064a\u0627\u0636\u064a\u0627\u062a \u0627\u0627\u0628\u062a\u062f\u0627\u0626\u064a\u0629 (\u0633\u064a\u0638\u0647\u0631 \u0641\u064a \u0648\u0627\u062c\u0647\u0629 \u0627\u0644\u0645\u0639\u0644\u0645)'
        form.base_fields['description'].help_text = '\u0645\u062b\u0627\u0644: \u064a\u062d\u062a\u0648\u064a \u0639\u0644\u0649 \u0643\u062a\u0628 \u0627\u0644\u0637\u0627\u0644\u0628\u060c \u062f\u0644\u064a\u0644 \u0627\u0644\u0645\u0639\u0644\u0645\u060c \u0641\u064a\u062f\u064a\u0648\u0647\u0627\u062a \u062a\u0639\u0644\u0645\u064a\u0649\u0629\u060c \u0648\u0623\u0648\u0631\u0627\u0642 \u0639\u0645\u0644'
        return form
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self.update_env_mappings()
    def update_env_mappings(self):
        mappings = OUShareMapping.objects.filter(is_active=True)
        ou_map = {m.ou_name: [m.share_path] for m in mappings}
        mounts = {m.share_slug: m.share_slug for m in mappings}
        pass
