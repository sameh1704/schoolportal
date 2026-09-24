import socket
import ssl
import traceback

from django.core.management.base import BaseCommand
from ldap3 import Connection, Server, Tls

from school_portal.ad_config import get_ad_config


def classify_starttls_error(exc):
    message = f"{type(exc).__name__}: {exc}".lower()
    if any(term in message for term in ("certificate", "cert verify", "hostname", "unknown ca", "self signed")):
        return "Certificate / CA trust / hostname validation"
    if any(term in message for term in ("protocol version", "unsupported protocol", "wrong version", "tlsv", "handshake failure")):
        return "TLS version or TLS handshake"
    if any(term in message for term in ("timeout", "actively refused", "forcibly closed", "connection reset", "unreachable")):
        return "Network or Domain Controller TLS configuration"
    if any(term in message for term in ("ldapstarttlserror", "starttls", "extended operation")):
        return "LDAP StartTLS support / server configuration"
    if any(term in message for term in ("invalid server", "configuration", "attributeerror", "typeerror")):
        return "Configuration or LDAP library"
    return "Unclassified LDAP/TLS error; inspect the technical details"


class Command(BaseCommand):
    help = "Verify anonymous LDAP StartTLS and RootDSE over port 389 with certificate validation."

    def handle(self, *args, **options):
        cfg = get_ad_config()
        if not all((cfg.AD_SERVER, cfg.AD_HOSTNAME, cfg.AD_BASE_DN)):
            self.stderr.write(self.style.ERROR("Configuration: FAIL (AD_SERVER, AD_HOSTNAME, AD_BASE_DN required)"))
            raise SystemExit(1)
        if cfg.AD_PORT != 389:
            self.stderr.write(self.style.ERROR(f"Configuration: FAIL (Phase 2B requires AD_PORT=389; got {cfg.AD_PORT})"))
            raise SystemExit(1)

        try:
            with socket.create_connection((cfg.AD_SERVER, 389), timeout=8):
                self.stdout.write(self.style.SUCCESS(f"TCP {cfg.AD_SERVER}:389: PASS"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"TCP {cfg.AD_SERVER}:389: FAIL ({type(exc).__name__}: {exc})"))
            raise SystemExit(1)

        connection = None
        try:
            tls = Tls(
                validate=ssl.CERT_REQUIRED,
                valid_names=[cfg.AD_HOSTNAME],
                ca_certs_file=cfg.AD_LDAP_CA_CERTS_FILE or None,
                sni=cfg.AD_HOSTNAME,
            )
            server = Server(cfg.AD_SERVER, port=389, use_ssl=False, tls=tls, get_info=None, connect_timeout=8)
            connection = Connection(server, receive_timeout=8)
            connection.open()
            if connection.closed:
                raise ConnectionError(connection.last_error or "LDAP socket remained closed after open()")
            self.stdout.write(self.style.SUCCESS("LDAP connection on TCP 389: PASS"))

            if not connection.start_tls():
                raise ConnectionError(connection.last_error or "LDAP StartTLS operation returned false")
            if not connection.tls_started:
                raise ConnectionError("StartTLS returned success but ldap3 reports TLS is not established")
            self.stdout.write(self.style.SUCCESS("StartTLS negotiation: PASS"))
            self.stdout.write(self.style.SUCCESS("TLS certificate validation: PASS (CERT_REQUIRED; hostname checked)"))

            result = connection.search(
                search_base="",
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["defaultNamingContext", "rootDomainNamingContext", "supportedLDAPVersion"],
            )
            if not result or not connection.entries:
                raise ConnectionError(connection.last_error or "RootDSE read failed or returned no entries")
            self.stdout.write(self.style.SUCCESS("RootDSE read after StartTLS: PASS"))
            self.stdout.write(self.style.SUCCESS("Phase 2B StartTLS: PASS"))
        except Exception as exc:
            if connection is not None and connection.tls_started:
                self.stdout.write("StartTLS negotiation: PASS")
                self.stdout.write(self.style.ERROR("TLS/RootDSE phase: FAIL"))
            else:
                self.stdout.write(self.style.ERROR("StartTLS negotiation: FAIL"))
            self.stdout.write(self.style.ERROR(f"Failure category: {classify_starttls_error(exc)}"))
            self.stdout.write(self.style.ERROR(f"Technical error: {type(exc).__name__}: {exc}"))
            if connection is not None and connection.result:
                self.stdout.write(self.style.ERROR(f"LDAP response detail: {connection.result}"))
            if connection is not None and connection.last_error:
                self.stdout.write(self.style.ERROR(f"LDAP library detail: {connection.last_error}"))
            self.stdout.write("Traceback (credential-free connectivity check):")
            self.stdout.write(traceback.format_exc())
            raise SystemExit(1)
        finally:
            if connection is not None:
                try:
                    connection.unbind()
                except Exception:
                    pass

        self.stdout.write("No AD username or password was used.")
