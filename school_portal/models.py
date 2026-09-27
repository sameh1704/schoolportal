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
        return f"{self.ou_name}  ({"نشط" if self.is_active else "غير نشط"})"

    def get_absolute_path(self):
        return self.share_path

    @classmethod
    def get_ou_subject_map(cls):
        """Return OU -> share_path mapping from active database records."""
        mappings = cls.objects.filter(is_active=True)
        return {m.ou_name: [m.share_path] for m in mappings}

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.share_path and not self.share_path.startswith('/app/shares/'):
            raise ValidationError({
                'share_path': 'يجب أن يبدأ المسار بـ /app/shares/'
            })