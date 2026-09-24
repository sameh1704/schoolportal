import socket
import ssl

from django.core.management.base import BaseCommand
from ldap3 import ALL, Connection, Server, Tls

from school_portal.ad_config import get_ad_config


class Command(BaseCommand):
    help = "Check DNS, TCP, LDAP 389, and certificate-validated LDAPS 636 without credentials."

    def handle(self, *args, **options):
        cfg = get_ad_config()
        if not cfg.AD_HOSTNAME or not cfg.AD_SERVER:
            self.stderr.write(self.style.ERROR("AD_HOSTNAME and AD_SERVER are required."))
            raise SystemExit(1)

        failures = 0
        try:
            addresses = sorted({item[4][0] for item in socket.getaddrinfo(cfg.AD_HOSTNAME, None)})
            self.stdout.write(self.style.SUCCESS(f"DNS {cfg.AD_HOSTNAME}: PASS ({', '.join(addresses)})"))
        except OSError as exc:
            addresses = []
            failures += 1
            self.stdout.write(self.style.ERROR(f"DNS {cfg.AD_HOSTNAME}: FAIL ({exc})"))

        for port in (cfg.AD_PORT, cfg.AD_LDAPS_PORT):
            try:
                with socket.create_connection((cfg.AD_SERVER, port), timeout=5):
                    self.stdout.write(self.style.SUCCESS(f"TCP {cfg.AD_SERVER}:{port}: PASS"))
            except OSError as exc:
                failures += 1
                self.stdout.write(self.style.ERROR(f"TCP {cfg.AD_SERVER}:{port}: FAIL ({exc})"))

        try:
            # Use the confirmed IP so protocol probing remains possible even if DNS is unavailable.
            server = Server(cfg.AD_SERVER, port=cfg.AD_PORT, get_info=ALL, connect_timeout=5)
            connection = Connection(server, receive_timeout=5, auto_bind=True)
            try:
                rootdse_ok = connection.search(
                    search_base="",
                    search_filter="(objectClass=*)",
                    search_scope="BASE",
                    attributes=["defaultNamingContext", "rootDomainNamingContext", "supportedLDAPVersion"],
                )
                if not rootdse_ok or not connection.entries:
                    raise OSError("LDAP connected, but anonymous RootDSE read was denied or returned no data")
                self.stdout.write(self.style.SUCCESS("LDAP anonymous RootDSE on 389: PASS"))
            finally:
                connection.unbind()
        except Exception as exc:
            failures += 1
            self.stdout.write(self.style.ERROR(f"LDAP on {cfg.AD_PORT}: FAIL ({type(exc).__name__}: {exc})"))

        try:
            tls = Tls(
                validate=ssl.CERT_REQUIRED,
                valid_names=[cfg.AD_HOSTNAME],
                ca_certs_file=cfg.AD_LDAP_CA_CERTS_FILE or None,
                sni=cfg.AD_HOSTNAME,
            )
            server = Server(
                cfg.AD_SERVER,
                port=cfg.AD_LDAPS_PORT,
                use_ssl=True,
                tls=tls,
                get_info=ALL,
                connect_timeout=5,
            )
            connection = Connection(server, receive_timeout=5, auto_bind=True)
            try:
                rootdse_ok = connection.search(
                    search_base="",
                    search_filter="(objectClass=*)",
                    search_scope="BASE",
                    attributes=["defaultNamingContext", "rootDomainNamingContext", "supportedLDAPVersion"],
                )
                if not rootdse_ok or not connection.entries:
                    raise OSError("LDAPS connected, but anonymous RootDSE read was denied or returned no data")
                self.stdout.write(self.style.SUCCESS("LDAPS certificate validation + RootDSE on 636: PASS"))
            finally:
                connection.unbind()
        except Exception as exc:
            failures += 1
            self.stdout.write(self.style.ERROR(f"LDAPS certificate validation on {cfg.AD_LDAPS_PORT}: FAIL ({type(exc).__name__}: {exc})"))

        self.stdout.write("No credentials were used by this command.")
        if failures:
            raise SystemExit(1)
