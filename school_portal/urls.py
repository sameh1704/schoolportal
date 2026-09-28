from django.urls import path

from .views import (
    dashboard_view,
    favorite_toggle_view,
    health_check_view,
    keep_alive_view,
    login_view,
    logout_view,
    material_browser_view,
    material_download_view,
    thumbnail_view,
)

urlpatterns = [
    path("", login_view, name="login"),
    path("healthz/", health_check_view, name="healthz"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("materials/", material_browser_view, name="material_browser"),
    path("materials/download/", material_download_view, name="material_download"),
    path("materials/favorite/", favorite_toggle_view, name="material_favorite"),
    path("materials/keep-alive/", keep_alive_view, name="materials_keep_alive"),
    path("materials/thumb/", thumbnail_view, name="material_thumbnail"),
    path("logout/", logout_view, name="logout"),
]
