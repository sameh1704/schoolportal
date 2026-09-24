from types import SimpleNamespace

from django.contrib.auth.backends import BaseBackend

from .ad_service import authenticate_ad_user, parse_username


class ADBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        cleaned_username = parse_username(username)
        try:
            ad_user = authenticate_ad_user(cleaned_username, password)
        except Exception:
            return None

        return SimpleNamespace(
            username=ad_user["username"],
            display_name=ad_user["display_name"],
            ad_groups=ad_user["groups"],
            ou=ad_user.get("ou", ""),
            is_active=True,
            is_authenticated=True,
        )

    def get_user(self, user_id):
        return None
