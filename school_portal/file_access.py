import mimetypes
import ntpath
import os
import platform

from django.core.exceptions import ValidationError

from .security import ensure_within_share, get_authorized_share, validate_requested_share

BROWSER_PREVIEW_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".mp4",
    ".webm",
    ".ogg",
    ".mp3",
    ".wav",
    ".txt",
    ".html",
}

NATIVE_OPEN_EXTENSIONS = {
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".pdf",
}


def detect_display_os(value=None):
    raw = (value or os.getenv("DISPLAY_OS") or os.getenv("INTERACTIVE_DISPLAY_OS") or platform.system() or "unknown").strip()
    normalized = raw.lower()

    if "windows" in normalized or normalized in {"win32", "win64"}:
        return "windows"
    if "android" in normalized:
        return "android"
    if "linux" in normalized or normalized in {"ubuntu", "debian", "centos", "fedora"}:
        return "linux"
    if "darwin" in normalized or "mac" in normalized:
        return "mac"
    return "unknown"


def build_file_open_plan(file_path, display_os=None):
    path = str(file_path or "")
    extension = os.path.splitext(path)[1].lower()
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "application/octet-stream"

    target_os = detect_display_os(display_os)

    if extension in BROWSER_PREVIEW_EXTENSIONS:
        return {
            "action": "preview",
            "label": "Open in browser",
            "target": path,
            "mime": mime_type,
        }

    if extension in NATIVE_OPEN_EXTENSIONS and target_os == "windows":
        return {
            "action": "native",
            "label": "Open with installed app",
            "target": path,
            "mime": mime_type,
        }

    return {
        "action": "download",
        "label": "Download",
        "target": path,
        "mime": mime_type,
    }


def resolve_share_target(resource_name, subpath=""):
    share_root = validate_requested_share(resource_name)
    raw_path = str(subpath or "").strip()
    if raw_path.startswith("/") or raw_path.startswith("\\"):
        raw_path = raw_path.lstrip("/\\")
    if any(part in {"..", "."} for part in raw_path.replace("\\", "/").split("/")):
        raise ValidationError("Path traversal is not allowed.")
    if not raw_path:
        return {"share_root": share_root, "target_path": share_root}
    candidate = ntpath.join(share_root, raw_path)
    ensure_within_share(share_root, candidate)
    return {"share_root": share_root, "target_path": candidate}


def list_network_directory(directory_path):
    path = str(directory_path or "").strip()
    if not path:
        return []

    try:
        entries = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": entry.is_dir(),
                })
        entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        return entries
    except OSError:
        return []
