from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Prune the oldest generated thumbnails over THUMBNAIL_CACHE_MAX_BYTES."

    def handle(self, *args, **options):
        cache_root = Path(settings.THUMBNAIL_CACHE_ROOT)
        files = [path for path in cache_root.glob("*.jpg") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in files)
        removed = 0
        for path in files:
            if total <= settings.THUMBNAIL_CACHE_MAX_BYTES:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
            removed += 1
        self.stdout.write(f"Removed {removed} thumbnail(s); cache uses {total} bytes.")
