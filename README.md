# School File Portal

> Important: deployment-specific LDAP, AD, OU, and file-share values belong in local environment configuration, not source control.

This project is a portal for teachers who sign in on classroom devices using their Active Directory credentials. Once authenticated, the portal shows material paths authorized for the user's configured AD OU.

## Active Directory configuration

The project does not hard-code AD settings. The following values are supported via environment variables in `.env` or Docker secrets:

```env
AD_SERVER=<directory-server-address>
AD_HOSTNAME=<directory-server-hostname>
AD_DOMAIN=<directory-domain>
AD_PORT=389
AD_USE_SSL=False
AD_USE_STARTTLS=False
AD_LDAP_SERVER=
AD_BASE_DN=<base-distinguished-name>
AD_USER_SEARCH_BASE=
AD_GROUP_SEARCH_BASE=
AD_BIND_USERNAME=
AD_BIND_PASSWORD=
AD_TEST_USERNAME=
```

Replace placeholder values locally. Do not commit hostnames, domain names, Base DNs, credentials, share names, or OU names.

## Safe startup validation

The project checks the AD configuration at startup and in a dedicated management command. It does not attempt a live LDAP bind unless the developer has provided the actual required values.

To validate the current configuration without touching AD:

```bash
python manage.py check_ad_config
```

If settings are incomplete, the command prints the missing fields and exits with a non-zero status. No password or secret is printed to logs.

## Required behavior before live login

Before live AD testing is approved:

- no real LDAP bind is attempted
- no password is stored in the repository
- no secret is printed in logs
- the UI rejects login with a clear message when AD settings are incomplete
- the developer must provide the real values in `.env` or a Docker secret

## Security and safety rules

- no password in Git or source code
- no default AD bind account in project files
- no anonymous LDAP assumptions
- no claim of a successful AD connection unless a real bind test is executed with valid environment values
- no production share is exposed until the container mount and OU path map are configured

## Core concept

This solution does not replace the existing school infrastructure. It works with the current design:

- Active Directory authenticates users and supplies each user's distinguished name
- Django extracts the configured OU and applies `OU_SUBJECT_MAP` to decide which read-only roots the user can browse
- A dedicated SMB account mounts shares read-only inside the web container
- The portal lists and downloads files server-side for browser clients, including Android

## Requirements

- Python 3.12+
- Django 6.x
- ldap3
- Python dotenv

## Local setup

1. Create a virtual environment.
2. Install dependencies:
   python -m pip install Django ldap3 python-dotenv
3. Copy `.env.example` to `.env` and update the values for your domain and shares.
4. Run database migrations:
   python manage.py migrate
5. Start the app:
   python manage.py runserver 0.0.0.0:8000

## Active Directory flow

The portal checks the teacher username and password against AD. After a successful bind, it reads the user's distinguished name and maps the configured OU to allowed paths in `OU_SUBJECT_MAP`.

The content is read from the container-mounted share tree. The portal does not copy files into Django or PostgreSQL.

## Read-only material browsing with OU authorization

The portal authenticates the submitted user against AD over the configured encrypted LDAP connection. After a successful bind it reads `distinguishedName`, extracts the configured OU level, and stores only the username, display name, and OU in the Django session. It never stores the AD password.

At startup, the web container mounts the required SMB share or shares under `SHARE_MOUNT_ROOT` with a dedicated, read-only AD service account. The container process then drops to the unprivileged `app` user before Django starts. The web service receives `SYS_ADMIN` for mounting; it is not run in privileged mode. `/dev/fuse` is not used because CIFS is mounted by the Linux kernel.

`OU_SUBJECT_MAP` is the application authorization map: JSON object keys are OU names and values are lists of absolute paths below `SHARE_MOUNT_ROOT`. An empty map denies access to all material paths. Use environment configuration for deployment-specific OU names and paths; do not put real school values in source control.

Example map shape (placeholders only):

```json
{"<OU_NAME>":["/app/shares/<subject-directory>"]}
```

The browser listing and download endpoints resolve every requested path, enforce containment inside the current user's configured OU roots, and reject traversal and symlink escapes. The mounted tree and Django endpoints are read-only.

### Container-side SMB mounts

The `portal-web` image installs `cifs-utils` and `smbclient`. Set `SMB_HOST` to a DNS name or IP address, and set `SMB_MOUNTS` to a comma-separated list of `mount-slug=share-name` entries. Each share is mounted read-only at `/app/shares/<mount-slug>`. Keep `OU_SUBJECT_MAP` paths aligned with these mount paths.

Create the credentials file locally at the path in `SMB_CREDENTIALS_SOURCE` (example: `./secrets/smb_credentials`), outside source control. It should contain `username=`, `password=`, and, if needed, `domain=` lines for a dedicated read-only service account. Copy `secrets.example` to the ignored `secrets/smb_credentials` path and replace the placeholders. Do not put secrets in `.env`, the image, or Git. Compose mounts this file as `/run/secrets/smb_credentials`.

Example environment shape (placeholders only):

```env
SMB_HOST=<smb-server-dns-name-or-ip>
SMB_MOUNTS=<mount-slug>=<share-name>,<another-slug>=<another-share>
SMB_CREDENTIALS_SOURCE=./secrets/smb_credentials
SHARE_MOUNT_ROOT=/app/shares
```

If the DNS name cannot be resolved from Docker, temporarily use the server IP in the same `SMB_HOST` variable. A DNS name is preferred long-term. The Linux kernel used by Docker Engine (the Docker Desktop VM in development, or the Ubuntu host in production) must provide CIFS filesystem support and permit outbound SMB traffic; installing `cifs-utils` in the image provides the mount helper, not the kernel driver. Docker Desktop behavior depends on its VM kernel and security configuration, so verify it there rather than assuming Windows host mounts or domain membership are involved.

The Compose web service adds only `SYS_ADMIN` for the mount operation. It does not use `privileged: true`, `/dev/fuse`, or `apparmor:unconfined` by default. If the host's AppArmor policy blocks mounting, inspect the host audit logs and use a scoped policy; do not disable AppArmor globally. Revisit the mount capability and confinement for production hardening.

Verify SMB connectivity and the credentials file before relying on the startup mounts:

```sh
sh scripts/check_smb.sh
```

The check runs `smbclient -L` inside a one-off web container and reads credentials from the mounted secret file. The normal web container exits with an error if any configured mount fails; Django starts only after all listed shares mount successfully.
### OU selection

`LDAP_OU_DEPTH_INDEX` selects which OU from the leaf-first distinguished name is used; the default `0` means the first OU immediately above the user object. Adjust it only after confirming real user DNs and which OU represents the subject or department.

Because a shared service account can read files for multiple OUs, `OU_SUBJECT_MAP` and the Django path checks are security-sensitive authorization controls. Restrict who can change deployment environment values and portal code. SMB access from the container is not the individual teacher's NTFS token; the application must enforce the OU map on every listing and download request.
