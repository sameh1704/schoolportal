import os

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import AuditLoginAttempt, Favorite, FileAccessLog, OUShareMapping, UserPreference
from .smb import test_share_access


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


class OUShareMappingAdminForm(forms.ModelForm):
    class Meta:
        model = OUShareMapping
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_active"):
            return cleaned_data

        host = os.getenv("SMB_HOST", "").strip()
        ok, message = test_share_access(
            host=host,
            share_name=cleaned_data.get("share_slug", ""),
            username=cleaned_data.get("smb_username", ""),
            password=cleaned_data.get("smb_password", ""),
            domain=cleaned_data.get("smb_domain", ""),
            credentials_file=os.getenv("SMB_CREDENTIALS_FILE", "/run/secrets/smb_credentials"),
        )
        if not ok:
            raise forms.ValidationError(message)
        return cleaned_data


@admin.register(OUShareMapping)
class OUShareMappingAdmin(admin.ModelAdmin):
    form = OUShareMappingAdminForm
    list_display = ('ou_name', 'share_slug', 'display_name', 'share_path', 'has_custom_credentials', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('ou_name', 'share_slug', 'display_name', 'description')
    ordering = ('ou_name',)
    list_per_page = 25
    date_hierarchy = 'created_at'
    list_editable = ('is_active',)
    fieldsets = (
        ('معلومات التعريف', {
            'fields': ('ou_name', 'share_slug', 'is_active'),
            'description': 'هذه الحقول مطلبية وتربط OU بالمشاركة.'
        }),
        ('مسار المشاركة', {
            'fields': ('share_path',),
            'description': 'المسار داخل الحاوية حيث يتم mount مشاركة SMB.'
        }),
        ('بيانات اعتماد SMB (اختياري)', {
            'fields': ('smb_username', 'smb_password', 'smb_domain'),
            'description': 'إذا تركت هذه الحقول فارغة، ستستخدم بيانات الاعتماد الافتراضية من ملف secrets. املأها فقط إذا كانت المشاركة تتطلب مستخدم/كلمة مرور مختلفة.',
            'classes': ('collapse',),
        }),
        ('معلومات العرض', {
            'fields': ('display_name', 'description'),
            'description': 'معلومات تظهر للمعلم في لوحة التحكم (اختياري).'
        }),
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['ou_name'].help_text = 'مثال: MATH-PRIM (اسم OU كما يظهر في Active Directory)'
        form.base_fields['share_slug'].help_text = 'مثال: math-prim (يجب أن يتطابق مع slug في SMB_MOUNTS في .env)'
        form.base_fields['share_path'].help_text = 'مثال: /app/shares/math-prim (مسار mount داخل الحاوية)'
        form.base_fields['smb_username'].help_text = 'مثال: hazem (اتركه فارغاً للافتراضي)'
        form.base_fields['smb_password'].help_text = 'مثال: 12345 (اتركه فارغاً للافتراضي)'
        form.base_fields['smb_domain'].help_text = 'مثال: ALMANARSCHOOL (اتركه فارغاً للافتراضي)'
        form.base_fields['display_name'].help_text = 'مثال: مواد الرياضيات الابتدائية (يظهر في واجهة المعلم)'
        form.base_fields['description'].help_text = 'مثال: يحتوي على كتب، فيديوهات، أوراق عمل'
        return form
    
    @admin.display(boolean=True, description='بيانات اعتماد مخصصة')
    def has_custom_credentials(self, obj):
        return bool(obj.smb_username and obj.smb_password)
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self.update_env_mappings()
    
    def update_env_mappings(self):
        """This method can be called to sync .env with database records."""
        mappings = OUShareMapping.objects.filter(is_active=True)
        ou_map = {m.ou_name: [m.share_path] for m in mappings}
        mounts = {m.share_slug: m.share_slug for m in mappings}
        # The entrypoint.sh will read from database directly
        pass


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "root_index", "relative_path", "is_directory", "created_at")
    list_filter = ("is_directory", "created_at")
    search_fields = ("user__username", "relative_path")
    readonly_fields = ("created_at",)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "materials_view", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("updated_at",)


@admin.register(FileAccessLog)
class FileAccessLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "extension", "relative_path", "client_ip")
    list_filter = ("action", "extension", "timestamp")
    search_fields = ("user__username", "relative_path")
    date_hierarchy = "timestamp"
    readonly_fields = ("user", "root_index", "relative_path", "extension", "action", "timestamp", "client_ip", "user_agent")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
