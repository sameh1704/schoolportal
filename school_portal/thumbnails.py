import hashlib
import os
import subprocess
import threading
from pathlib import Path

from django.conf import settings


_generation_slots = threading.BoundedSemaphore(2)


def thumbnail_path(root, relative_path, source):
    stat = source.stat()
    key = hashlib.sha256(f"{root}\0{relative_path}\0{stat.st_mtime_ns}\0{stat.st_size}".encode()).hexdigest()
    return Path(settings.THUMBNAIL_CACHE_ROOT) / f"{key}.jpg"


def get_thumbnail(root, relative_path, source):
    extension = source.suffix.lower()
    if extension not in {".pdf", ".mp4"}:
        return None
    try:
        target = thumbnail_path(root, relative_path, source)
    except OSError:
        return None
    if target.is_file():
        return target
    if not _generation_slots.acquire(blocking=False):
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp.jpg")
        if extension == ".pdf":
            command = [
                "pdftoppm", "-jpeg", "-f", "1", "-singlefile", "-scale-to-x", "320",
                "-scale-to-y", "-1", os.fspath(source), os.fspath(temporary.with_suffix("")),
            ]
        else:
            command = [
                "ffmpeg", "-y", "-ss", "1", "-i", os.fspath(source), "-frames:v", "1",
                "-vf", "scale=320:-2", os.fspath(temporary),
            ]
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
        if temporary.is_file() and temporary.stat().st_size > 0:
            temporary.replace(target)
            return target
        temporary.unlink(missing_ok=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        _generation_slots.release()
    return None
