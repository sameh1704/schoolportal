import re
import ssl
from typing import Any, Iterable, Mapping

from django.conf import settings
from ldap3 import Connection, Server, Tls
from ldap3.utils.conv import escape_filter_chars

from .ou_access import extract_user_ou


def parse_username(username: str) -> str:
    if not username:
        return ""

    cleaned = username.strip()
    if "\\" in cleaned:
        return cleaned.rsplit("\\", 1)[-1]
    if "@" in cleaned:
        return cleaned.split("@", 1)[0]
    return cleaned


def normalize_group_name(group_name: str) -> str:
    if group_name is None:
        return ""

    name = str(group_name).strip()
    if not name:
        return ""

    match = re.search(r"CN=([^,]+)", name, flags=re.IGNORECASE)
    if match:
        name = match.group(1)

    if "\\" in name:
        name = name.split("\\")[-1]

    name = name.replace(";", " ")
    name = name.replace(",", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name.lower()


def map_group_resources(user_groups: Iterable[str], share_map: Mapping[str, Any] | None = None):
    resolved_map = share_map or getattr(settings, "AD_SHARE_GROUPS", {})
    normalized_user_groups = {normalize_group_name(group) for group in user_groups}

    results = []
    for group_name, path in resolved_map.items():
        if normalize_group_name(group_name) in normalized_user_groups:
            results.append({"name": str(group_name), "path": str(path)})
    return results


def authenticate_ad_user(username: str, password: str, domain: str | None = None, ldap_server: str | None = None, search_base: str | None = None):
    if not username or not password:
        raise ValueError("Username and password are required.")

    clean_username = parse_username(username)
    domain_name = (domain or getattr(settings, "AD_DOMAIN", "") or "").strip()
    ldap_host = (ldap_server or getattr(settings, "AD_LDAP_SERVER", "") or "").strip()
    encryption = getattr(settings, "AD_LDAP_ENCRYPTION", "")
    auth_method = getattr(settings, "AD_AUTH_METHOD", "")
    port = getattr(settings, "AD_LDAPS_PORT", 636) if encryption == "ldaps" else getattr(settings, "AD_PORT", 389)
    target_base = (search_base or getattr(settings, "AD_USER_SEARCH_BASE", "") or getattr(settings, "AD_BASE_DN", "")).strip()

    if not domain_name or not ldap_host or not target_base:
        raise RuntimeError("LDAP/AD configuration is incomplete.")
    if encryption not in {"starttls", "ldaps"}:
        raise RuntimeError("AD_LDAP_ENCRYPTION must explicitly be starttls or ldaps before password authentication.")
    if auth_method not in {"NTLM", "SIMPLE"}:
        raise RuntimeError("AD_AUTH_METHOD must explicitly be NTLM or SIMPLE before password authentication.")

    tls = Tls(
        validate=ssl.CERT_REQUIRED,
        valid_names=[getattr(settings, "AD_HOSTNAME", ldap_host)],
        ca_certs_file=getattr(settings, "AD_LDAP_CA_CERTS_FILE", "") or None,
        sni=getattr(settings, "AD_HOSTNAME", ldap_host),
    )
    server = Server(ldap_host, port=port, use_ssl=(encryption == "ldaps"), tls=tls, get_info=None)
    ntlm_domain = getattr(settings, "AD_NETBIOS_DOMAIN", "").strip()
    if auth_method == "NTLM" and not ntlm_domain:
        raise RuntimeError("AD_NETBIOS_DOMAIN is required for NTLM authentication.")
    bind_user = f"{ntlm_domain}\\{clean_username}" if auth_method == "NTLM" else f"{clean_username}@{domain_name}"
    connection = Connection(server, user=bind_user, password=password, authentication=auth_method)
    try:
        if encryption == "starttls":
            connection.open()
            if not connection.start_tls():
                raise ConnectionError("Could not establish verified LDAP StartTLS.")
        if not connection.bind():
            raise PermissionError("Invalid username or password.")

        display_name = clean_username
        groups = []
        distinguished_name = ""
        user_ou = ""
        search_filter_template = getattr(settings, "AD_USER_SEARCH_FILTER", "")
        if search_filter_template:
            safe_username = escape_filter_chars(clean_username)
            search_filter = search_filter_template.format(username=safe_username)
            connection.search(
                target_base,
                search_filter,
                attributes=["displayName", "sAMAccountName", "memberOf", "distinguishedName"],
            )
            if connection.entries:
                entry = connection.entries[0]
                display_name = entry["displayName"].value if "displayName" in entry and entry["displayName"].value else clean_username
                raw_groups = entry["memberOf"].value if "memberOf" in entry else []
                groups = [str(group) for group in ([raw_groups] if isinstance(raw_groups, str) else (raw_groups or []))]
                distinguished_name = (
                    entry["distinguishedName"].value
                    if "distinguishedName" in entry and entry["distinguishedName"].value
                    else entry.entry_dn
                )
                user_ou = extract_user_ou(
                    distinguished_name,
                    getattr(settings, "LDAP_OU_DEPTH_INDEX", 0),
                )
        return {
            "username": clean_username,
            "display_name": display_name,
            "groups": groups,
            "distinguished_name": distinguished_name,
            "ou": user_ou,
        }
    finally:
        if connection.bound or connection.closed is False:
            connection.unbind()
