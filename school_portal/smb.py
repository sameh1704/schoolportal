"""Safe SMB connectivity checks used when administrators change share mappings."""

import os
import subprocess
import tempfile
from pathlib import Path


SMB_TEST_TIMEOUT_SECONDS = 15


def test_share_access(host, share_name, username="", password="", domain="", credentials_file=""):
    """Return ``(ok, message)`` without exposing credentials in logs or forms."""
    if not host or not share_name:
        return False, "يلزم تحديد خادم SMB واسم المشاركة."

    credential_path = credentials_file
    temporary_credentials = None
    try:
        if username or password:
            if not username or not password:
                return False, "أدخل اسم مستخدم SMB وكلمة المرور معاً، أو اتركهما فارغين لاستخدام الحساب الافتراضي."
            temporary_credentials = tempfile.NamedTemporaryFile(mode="w", prefix="smb-check-", delete=False)
            temporary_credentials.write(f"username={username}\npassword={password}\n")
            if domain:
                temporary_credentials.write(f"domain={domain}\n")
            temporary_credentials.close()
            os.chmod(temporary_credentials.name, 0o600)
            credential_path = temporary_credentials.name

        if not credential_path or not Path(credential_path).is_file():
            return False, "ملف بيانات اعتماد SMB الافتراضي غير متاح."

        result = subprocess.run(
            ["smbclient", f"//{host}/{share_name}", "-A", credential_path, "-c", "quit"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=SMB_TEST_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return False, "أداة اختبار SMB غير متاحة على الخادم."
    except subprocess.TimeoutExpired:
        return False, "انتهت مهلة اختبار اتصال SMB. تحقق من الخادم والشبكة."
    finally:
        if temporary_credentials:
            Path(temporary_credentials.name).unlink(missing_ok=True)

    if result.returncode == 0:
        return True, "تم التحقق من الوصول إلى مشاركة SMB بنجاح."
    return False, "تعذر تسجيل الدخول إلى مشاركة SMB. تحقق من اسم المشاركة وبيانات الاعتماد والصلاحيات."
