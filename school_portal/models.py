import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditLoginAttempt(models.Model):
    username = models.CharField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Login attempt"
        verbose_name_plural = "Login attempts"

    def __str__(self):
        return f"{self.username} - {'success' if self.success else 'failed'}"


class OUShareMapping(models.Model):
    """
    يربط كل OU في Active Directory بمجلد مشاركة SMB محدد.
    عند تسجيل دخول مستخدم، يتم تحديد OU الخاص به وعرض المجلدات المرتبطة به.
    """
    ou_name = models.CharField(max_length=255, unique=True, verbose_name='اسم OU', help_text='مثال: MATH-PRIM أو SCIENCE-SEC أو ADMIN')
    share_slug = models.CharField(max_length=100, verbose_name='معرف المشاركة (Slug)', help_text='مثال: math-prim أو science-sec — يجب أن يتطابق مع SMB_MOUNTS في .env')
    share_path = models.CharField(max_length=500, verbose_name='مسار المشاركة داخل الحاوية', help_text='مثال: /app/shares/math-prim — المسار حيث يتم mount المجلد داخل الحاوية')
    
    # SMB Credentials (اختياري - إذا لم يتم تحديدها، تستخدم بيانات الاعتماد الافتراضية)
    smb_username = models.CharField(max_length=100, blank=True, verbose_name='اسم مستخدم SMB', help_text='مثال: hazem — اتركه فارغاً لاستخدام بيانات الاعتماد الافتراضية')
    smb_password = models.CharField(max_length=255, blank=True, verbose_name='كلمة مرور SMB', help_text='مثال: 12345 — اتركها فارغة لاستخدام بيانات الاعتماد الافتراضية')
    smb_domain = models.CharField(max_length=100, blank=True, verbose_name='دومين SMB', help_text='مثال: ALMANARSCHOOL — اتركه فارغاً لاستخدام الدومين الافتراضي')
    
    display_name = models.CharField(max_length=255, blank=True, verbose_name='اسم العرض', help_text='مثال: مواد الرياضيات الابتدائية — سيظهر للمعلم في لوحة التحكم')
    description = models.TextField(blank=True, verbose_name='وصف', help_text='مثال: مجلد مواد الرياضيات للمرحلة الابتدائية - يحتوي على كتب، فيديوهات، وأوراق عمل')
    is_active = models.BooleanField(default=True, verbose_name='نشط', help_text='إذا كان غير نشط، لن يظهر للمدرسين المنتمين لهذا OU')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')

    class Meta:
        ordering = ['ou_name']
        verbose_name = 'ربط OU بالمشاركة'
        verbose_name_plural = 'روابط OU بالمشاركات'
        indexes = [
            models.Index(fields=['ou_name']),
            models.Index(fields=['share_slug']),
        ]

    def __str__(self):
        return f"{self.ou_name}  ({'نشط' if self.is_active else 'غير نشط'})"

    def get_absolute_path(self):
        return self.share_path

    def get_smb_credentials(self):
        """Return SMB credentials for this share, or None to use defaults."""
        if self.smb_username and self.smb_password:
            return {
                'username': self.smb_username,
                'password': self.smb_password,
                'domain': self.smb_domain or 'ALMANARSCHOOL',
            }
        return None

    @classmethod
    def get_ou_subject_map(cls):
        """Return OU -> share_path mapping from active database records."""
        mappings = cls.objects.filter(is_active=True)
        return {m.ou_name: [m.share_path] for m in mappings}

    @classmethod
    def get_smb_mounts(cls):
        """Return SMB_MOUNTS string from active database records."""
        mappings = cls.objects.filter(is_active=True)
        mounts = []
        for m in mappings:
            creds = m.get_smb_credentials()
            if creds:
                mounts.append(f"{m.share_slug}={m.share_slug}:{creds['username']}:{creds['password']}:{creds['domain']}")
            else:
                mounts.append(f"{m.share_slug}={m.share_slug}")
        return ','.join(mounts)

    def clean(self):
        errors = {}
        if not re.fullmatch(r"[A-Za-z0-9 ._$-]+", self.share_slug or "") or self.share_slug in {".", ".."}:
            errors["share_slug"] = "اسم المشاركة يحتوي على رموز غير مسموح بها."

        expected_path = f"/app/shares/{self.share_slug}"
        if self.share_path != expected_path:
            errors["share_path"] = f"يجب أن يطابق المسار اسم المشاركة: {expected_path}"

        if errors:
            raise ValidationError(errors)


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    materials_view = models.CharField(max_length=20, default="tiles")
    updated_at = models.DateTimeField(auto_now=True)


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="material_favorites")
    root_index = models.PositiveIntegerField()
    relative_path = models.CharField(max_length=1000)
    is_directory = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "root_index", "relative_path"], name="unique_user_material_favorite"),
        ]
        ordering = ["-is_directory", "relative_path"]


class FileAccessLog(models.Model):
    ACTION_OPEN = "open"
    ACTION_DENIED = "denied"
    ACTION_CHOICES = [(ACTION_OPEN, "Open"), (ACTION_DENIED, "Denied")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    root_index = models.PositiveIntegerField(null=True, blank=True)
    relative_path = models.CharField(max_length=1000)
    extension = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=["timestamp"]), models.Index(fields=["action", "timestamp"])]
        ordering = ["-timestamp"]
