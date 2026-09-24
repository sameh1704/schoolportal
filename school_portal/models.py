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
