from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from school_portal.models import FileAccessLog


class Command(BaseCommand):
    help = "Purge file access logs older than FILE_ACCESS_LOG_RETENTION_DAYS."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.FILE_ACCESS_LOG_RETENTION_DAYS)
        deleted, _ = FileAccessLog.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(f"Removed {deleted} old file access log row(s).")
