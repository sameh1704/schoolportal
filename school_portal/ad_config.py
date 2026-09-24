import os
from dataclasses import dataclass, field


REQUIRED_AD_FIELDS = ["AD_SERVER", "AD_HOSTNAME", "AD_DOMAIN", "AD_BASE_DN"]


def _read_value(env: dict, key: str, default: str = "") -> str:
    value = env.get(key, default)
    return "" if value is None else str(value).strip()


@dataclass
class ADConfig:
    env: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.env:
            self.env = dict(os.environ)
        for name in (
            "AD_SERVER", "AD_HOSTNAME", "AD_DOMAIN", "AD_NETBIOS_DOMAIN", "AD_BASE_DN",
            "AD_USER_SEARCH_BASE", "AD_GROUP_SEARCH_BASE", "AD_BIND_USERNAME",
            "AD_BIND_PASSWORD", "AD_TEST_USERNAME", "AD_LDAP_CA_CERTS_FILE",
        ):
            setattr(self, name, _read_value(self.env, name))
        self.AD_PORT = int(_read_value(self.env, "AD_PORT", "389") or "389")
        self.AD_LDAPS_PORT = int(_read_value(self.env, "AD_LDAPS_PORT", "636") or "636")
        self.AD_LDAP_ENCRYPTION = _read_value(self.env, "AD_LDAP_ENCRYPTION").lower()
        self.AD_AUTH_METHOD = _read_value(self.env, "AD_AUTH_METHOD").upper()
        self.AD_USE_SSL = self.AD_LDAP_ENCRYPTION == "ldaps"
        self.AD_USE_STARTTLS = self.AD_LDAP_ENCRYPTION == "starttls"
        self.missing_fields = [name for name in REQUIRED_AD_FIELDS if not getattr(self, name)]
        self.is_ready = not self.missing_fields

    @property
    def status_message(self) -> str:
        if self.is_ready:
            return "Active Directory connection settings are present; this does not verify LDAP connectivity."
        return "Active Directory configuration is incomplete. Missing: " + ", ".join(self.missing_fields)


def get_ad_config(env: dict | None = None) -> ADConfig:
    return ADConfig(env if env is not None else dict(os.environ))
