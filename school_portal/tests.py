from django.contrib.auth import get_user_model
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from school_portal.ad_config import ADConfig
from school_portal.ad_service import map_group_resources, normalize_group_name
from school_portal.file_access import build_file_open_plan, detect_display_os
from school_portal.models import OUShareMapping
from school_portal.views import (
    DEFAULT_VIEW_MODE,
    VALID_VIEW_MODES,
    build_material_entry,
    format_size,
    get_file_kind,
)
from school_portal.ou_access import (
    allowed_paths_for_ou,
    extract_user_ou,
    resolve_ou_request_path,
)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class SystemHealthTests(TestCase):
    def test_healthz_endpoint_is_available(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ad_configuration_is_not_assumed(self):
        self.assertEqual(normalize_group_name("EXAMPLE\\Science Teachers"), "science teachers")
        self.assertEqual(normalize_group_name("CN=English Dept,OU=School,DC=example,DC=org"), "english dept")

    def test_ad_config_reports_missing_fields(self):
        cfg = ADConfig({
            "AD_SERVER": "192.0.2.10",
            "AD_DOMAIN": "example.org",
            "AD_HOSTNAME": "dc.example.org",
        })
        self.assertIn("AD_BASE_DN", cfg.missing_fields)
        self.assertFalse(cfg.is_ready)

    @override_settings(
        AD_CONFIG_READY=False,
        AD_AUTH_READY=False,
        AD_CONFIG_ERRORS=["AD_BASE_DN"],
        AD_AUTH_CONFIG_ERRORS=["AD_AUTH_METHOD"],
    )
    def test_login_rejects_when_ad_not_configured(self):
        response = self.client.post("/", {"username": "teacher", "password": "secret"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active Directory configuration is incomplete")

    def test_local_django_user_still_authenticates(self):
        User = get_user_model()
        user = User.objects.create_user(username="localadmin", password="LocalPass123!")
        user.is_staff = True
        user.is_superuser = True
        user.save()

        self.assertTrue(self.client.login(username="localadmin", password="LocalPass123!"))


class ADResourceMappingTests(SimpleTestCase):
    def test_normalize_group_name_removes_domain_prefix_and_case(self):
        self.assertEqual(normalize_group_name("EXAMPLE\\Science Teachers"), "science teachers")
        self.assertEqual(normalize_group_name("CN=English Dept,OU=School,DC=example,DC=org"), "english dept")

    def test_map_group_resources_returns_only_authorized_shares(self):
        user_groups = ["EXAMPLE\\social-worker", "English Dept", "Other Group"]
        share_map = {
            "social-worker": r"\\fileserver.example.test\share-a",
            "English Dept": r"\\fileserver.example.test\share-b",
            "Math": r"\\fileserver.example.test\share-c",
        }

        result = map_group_resources(user_groups, share_map)

        self.assertEqual(result, [
            {"name": "social-worker", "path": r"\\fileserver.example.test\share-a"},
            {"name": "English Dept", "path": r"\\fileserver.example.test\share-b"},
        ])


class OUShareMappingValidationTests(TestCase):
    def test_share_name_with_spaces_is_valid(self):
        mapping = OUShareMapping(
            ou_name="COMPUTER LAB",
            share_slug="computer lab",
            share_path="/app/shares/computer lab",
        )

        mapping.full_clean()

    def test_share_name_cannot_escape_mount_root(self):
        mapping = OUShareMapping(
            ou_name="INVALID",
            share_slug="../outside",
            share_path="/app/shares/../outside",
        )

        with self.assertRaises(ValidationError):
            mapping.full_clean()


class OUShareMappingAdminSMBTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            password="AdminPass123!",
        )
        self.client.force_login(
            self.admin_user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        self.add_url = reverse("admin:school_portal_ousharemapping_add")
        self.mapping_data = {
            "ou_name": "SOCIAL",
            "share_slug": "social2",
            "share_path": "/app/shares/social2",
            "smb_username": "social-user",
            "smb_password": "social-password",
            "smb_domain": "ALMANARSCHOOL",
            "display_name": "مواد اجتماعية",
            "description": "",
            "is_active": "on",
        }

    @patch("school_portal.admin.test_share_access", return_value=(True, "ok"))
    def test_admin_saves_an_active_mapping_only_after_successful_smb_test(self, check_share):
        response = self.client.post(self.add_url, self.mapping_data)

        self.assertEqual(response.status_code, 302)
        mapping = OUShareMapping.objects.get(ou_name="SOCIAL")
        self.assertTrue(mapping.is_active)
        check_share.assert_called_once()

    @patch(
        "school_portal.admin.test_share_access",
        return_value=(False, "تعذر تسجيل الدخول إلى مشاركة SMB."),
    )
    def test_admin_rejects_an_active_mapping_when_smb_test_fails(self, check_share):
        response = self.client.post(self.add_url, self.mapping_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تعذر تسجيل الدخول إلى مشاركة SMB.")
        self.assertFalse(OUShareMapping.objects.filter(ou_name="SOCIAL").exists())
        check_share.assert_called_once()


class FileAccessPlatformTests(SimpleTestCase):
    def test_detect_display_os_uses_environment_override(self):
        self.assertEqual(detect_display_os("windows"), "windows")
        self.assertEqual(detect_display_os("ANDROID"), "android")
        self.assertEqual(detect_display_os("ubuntu"), "linux")

    def test_build_file_open_plan_uses_preview_for_browser_supported_formats(self):
        plan = build_file_open_plan(r"\\fileserver.example.test\share-a\Lesson.pdf", "windows")
        self.assertEqual(plan["action"], "preview")
        self.assertEqual(plan["mime"], "application/pdf")

        plan = build_file_open_plan(r"\\fileserver.example.test\share-a\Lesson.pptx", "windows")
        self.assertEqual(plan["action"], "native")


class DistinguishedNameOUParsingTests(SimpleTestCase):
    def test_extracts_first_ou_by_default(self):
        dn = "CN=teacher,OU=SUBJECT-A,OU=Stage 1,DC=example,DC=org"
        self.assertEqual(extract_user_ou(dn), "SUBJECT-A")

    def test_depth_is_configurable_for_nested_ous(self):
        dn = "CN=teacher,OU=SUBJECT-A,OU=Stage 1,DC=example,DC=org"
        self.assertEqual(extract_user_ou(dn, depth_index=1), "Stage 1")

    def test_missing_ou_or_distinguished_name_returns_empty_value(self):
        self.assertEqual(extract_user_ou("CN=teacher,CN=Users,DC=example,DC=org"), "")
        self.assertEqual(extract_user_ou(None), "")
        self.assertEqual(extract_user_ou(""), "")


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class OUMaterialPathTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mount_root = Path(self.temp_dir.name) / "shares"
        self.path_a = self.mount_root / "A"
        self.path_b = self.mount_root / "B"
        self.path_a.mkdir(parents=True)
        self.path_b.mkdir(parents=True)
        (self.path_a / "a.txt").write_text("A material", encoding="utf-8")
        (self.path_b / "secret.txt").write_text("B material", encoding="utf-8")
        self.ou_map = {"A": [str(self.path_a)], "B": [str(self.path_b)]}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ou_paths_are_limited_to_configured_mount_root(self):
        allowed = allowed_paths_for_ou("a", self.ou_map, str(self.mount_root))
        self.assertEqual(allowed, [os.path.realpath(self.path_a)])

    def test_resolver_rejects_parent_traversal_and_absolute_outside_path(self):
        allowed = allowed_paths_for_ou("A", self.ou_map, str(self.mount_root))
        with self.assertRaises(PermissionDenied):
            resolve_ou_request_path(allowed, "0", "../../etc/passwd")
        with self.assertRaises(PermissionDenied):
            resolve_ou_request_path(allowed, "0", str(self.path_b / "secret.txt"))

    def test_resolver_rejects_symlink_escape(self):
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.path_a / "escape.txt"
        link.write_text("link placeholder", encoding="utf-8")
        allowed = allowed_paths_for_ou("A", self.ou_map, str(self.mount_root))
        realpath = os.path.realpath

        def resolve_symlink(path):
            if os.fspath(path) == os.fspath(link):
                return os.fspath(outside)
            return realpath(path)

        with patch("school_portal.ou_access.os.path.realpath", side_effect=resolve_symlink):
            with self.assertRaises(PermissionDenied):
                resolve_ou_request_path(allowed, "0", "escape.txt")

    def test_user_from_ou_a_cannot_list_or_download_ou_b_paths(self):
        with override_settings(SHARE_MOUNT_ROOT=str(self.mount_root)), patch.object(
            OUShareMapping,
            "get_ou_subject_map",
            return_value=self.ou_map,
        ):
            session = self.client.session
            session["ad_user"] = {"username": "teacher-a", "display_name": "Teacher A", "ou": "A"}
            session.save()

            allowed_list = self.client.get(reverse("material_browser"), {"root": "0"})
            denied_list = self.client.get(reverse("material_browser"), {"root": "1"})
            allowed_download = self.client.get(
                reverse("material_download"),
                {"root": "0", "path": "a.txt"},
            )
            denied_download = self.client.get(
                reverse("material_download"),
                {"root": "1", "path": "secret.txt"},
            )
            write_attempt = self.client.post(reverse("material_browser"), {"root": "0"})
            traversal_response = self.client.get(
                reverse("material_download"),
                {"root": "0", "path": "../../B/secret.txt"},
            )
            downloaded_content = b"".join(allowed_download.streaming_content)
            allowed_download.close()

        self.assertEqual(allowed_list.status_code, 200)
        self.assertContains(allowed_list, "a.txt")
        self.assertNotContains(allowed_list, "secret.txt")
        self.assertEqual(denied_list.status_code, 403)
        self.assertEqual(write_attempt.status_code, 405)
        self.assertEqual(allowed_download.status_code, 200)
        self.assertEqual(downloaded_content, b"A material")
        self.assertEqual(denied_download.status_code, 403)
        self.assertEqual(traversal_response.status_code, 403)


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False)
class MaterialBrowserPresentationTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mount_root = Path(self.temp_dir.name) / "shares"
        self.root = self.mount_root / "materials-a"
        self.root.mkdir(parents=True)
        self.subfolder = self.root / "lesson folder"
        self.subfolder.mkdir()
        self.files = {
            "clip.mp4": b"video",
            "guide.pdf": b"pdf",
            "slides.pptx": b"slides",
            "notes.docx": b"document",
            "marks.xlsx": b"sheet",
            "cover.png": b"image",
            "readme": b"other",
        }
        for name, content in self.files.items():
            (self.root / name).write_bytes(content)
        (self.subfolder / "inside.pdf").write_bytes(b"inside")
        self.mapping = {"A": [str(self.root)]}
        self.mapping_patch = patch.object(OUShareMapping, "get_ou_subject_map", return_value=self.mapping)
        self.mapping_patch.start()
        self.settings_override = override_settings(SHARE_MOUNT_ROOT=str(self.mount_root))
        self.settings_override.enable()
        session = self.client.session
        session["ad_user"] = {"username": "teacher-a", "display_name": "Teacher A", "ou": "A"}
        session.save()

    def tearDown(self):
        self.settings_override.disable()
        self.mapping_patch.stop()
        self.temp_dir.cleanup()

    def test_listing_includes_safe_metadata_and_sorts_folders_first(self):
        response = self.client.get(reverse("material_browser"), {"root": "0"})

        self.assertEqual(response.status_code, 200)
        entries = response.context["entries"]
        self.assertTrue(entries[0]["is_directory"])
        self.assertEqual(entries[0]["name"], "lesson folder")
        by_name = {entry["name"]: entry for entry in entries}
        self.assertEqual(by_name["clip.mp4"]["kind"], "video")
        self.assertEqual(by_name["guide.pdf"]["kind"], "pdf")
        self.assertEqual(by_name["slides.pptx"]["kind"], "presentation")
        self.assertEqual(by_name["notes.docx"]["kind"], "document")
        self.assertEqual(by_name["marks.xlsx"]["kind"], "spreadsheet")
        self.assertEqual(by_name["cover.png"]["kind"], "image")
        self.assertEqual(by_name["readme"]["kind"], "other")
        self.assertEqual(by_name["clip.mp4"]["extension"], ".mp4")
        self.assertTrue(by_name["clip.mp4"]["size"])
        self.assertTrue(by_name["clip.mp4"]["modified"])
        self.assertNotContains(response, str(self.mount_root))

    def test_all_view_modes_render_the_expected_container_class(self):
        for view in VALID_VIEW_MODES:
            with self.subTest(view=view):
                response = self.client.get(reverse("material_browser"), {"root": "0", "view": view})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"materials-browser view-{view}")
                self.assertContains(response, "طرق عرض الملفات")

    def test_invalid_view_falls_back_to_documented_default(self):
        response = self.client.get(reverse("material_browser"), {"root": "0", "view": "<script>"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["view_mode"], DEFAULT_VIEW_MODE)
        self.assertContains(response, f"materials-browser view-{DEFAULT_VIEW_MODE}")
        self.assertNotContains(response, "&lt;script&gt;")

    def test_root_and_subfolder_keep_the_switcher_and_view_parameter(self):
        root_response = self.client.get(reverse("material_browser"), {"root": "0", "view": "content"})
        child_response = self.client.get(
            reverse("material_browser"),
            {"root": "0", "path": "lesson folder", "view": "content"},
        )

        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(child_response.status_code, 200)
        self.assertContains(root_response, 'data-view-mode="content"')
        self.assertContains(root_response, "view=content")
        self.assertContains(child_response, 'data-view-mode="content"')
        self.assertContains(child_response, "المجلد السابق")

    def test_user_outside_allowed_paths_still_gets_403(self):
        session = self.client.session
        session["ad_user"] = {"username": "teacher-other", "display_name": "Other", "ou": "OTHER"}
        session.save()

        response = self.client.get(reverse("material_browser"), {"root": "0"})

        self.assertEqual(response.status_code, 403)

    def test_stat_failure_keeps_the_entry_with_empty_size_and_date(self):
        class BrokenEntry:
            name = "broken.pdf"
            path = str(self.root / "broken.pdf")

            def is_dir(self, follow_symlinks=False):
                return False

            def stat(self, follow_symlinks=False):
                raise OSError("unavailable")

        entry = build_material_entry(BrokenEntry(), str(self.root))

        self.assertEqual(entry["kind"], "pdf")
        self.assertEqual(entry["size"], "")
        self.assertEqual(entry["modified"], "")


class MaterialMetadataHelperTests(SimpleTestCase):
    def test_size_formatter_uses_human_readable_units(self):
        self.assertEqual(format_size(None), "")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1024 * 1024), "1.0 MB")
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.0 GB")

    def test_extension_mapping_covers_requested_types(self):
        self.assertEqual(get_file_kind("folder", True), "folder")
        self.assertEqual(get_file_kind("clip.mp4", False), "video")
        self.assertEqual(get_file_kind("guide.pdf", False), "pdf")
        self.assertEqual(get_file_kind("slides.pptx", False), "presentation")
        self.assertEqual(get_file_kind("notes.docx", False), "document")
        self.assertEqual(get_file_kind("marks.xlsx", False), "spreadsheet")
        self.assertEqual(get_file_kind("cover.png", False), "image")
        self.assertEqual(get_file_kind("archive.zip", False), "archive")
        self.assertEqual(get_file_kind("readme", False), "other")
