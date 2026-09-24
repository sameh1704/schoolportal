from django.conf import settings
from django.core.management.base import BaseCommand

from school_portal.ad_config import get_ad_config


class Command(BaseCommand):
    help = "Validate Active Directory configuration without performing a live LDAP bind."

    def handle(self, *args, **options):
        cfg = get_ad_config()

        if cfg.is_ready:
            self.stdout.write(
                self.style.SUCCESS(
                    "Core Active Directory settings are present; no live LDAP bind was attempted."
                )
            )
            if cfg.AD_LDAP_ENCRYPTION not in {"starttls", "ldaps"} or cfg.AD_AUTH_METHOD not in {"NTLM", "SIMPLE"}:
                self.stdout.write(
                    self.style.WARNING(
                        "User authentication is not enabled. Explicitly configure AD_LDAP_ENCRYPTION and AD_AUTH_METHOD after verifying the secure LDAP option."
                    )
                )
            return

        self.stdout.write(
            self.style.WARNING(
                "Active Directory configuration is incomplete. Missing: " + ", ".join(cfg.missing_fields)
            )
        )
        raise SystemExit(1)
