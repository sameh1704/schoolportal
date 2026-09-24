from django.urls import path

from .views import dashboard_view, health_check_view, login_view, logout_view, material_browser_view, material_download_view

urlpatterns = [
    path("", login_view, name="login"),
    path("healthz/", health_check_view, name="healthz"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("materials/", material_browser_view, name="material_browser"),
    path("materials/download/", material_download_view, name="material_download"),
    path("logout/", logout_view, name="logout"),
]
