from django.urls import path, re_path

from . import security_views, views

urlpatterns = [
    re_path(r"^s/(?P<code>[A-Za-z0-9-]+)/?$", views.go, name="consultant-go"),
    re_path(r"^s/(?P<code>[A-Za-z0-9-]+)/(?P<kind>link|whatsapp)-qr\.png$", views.qr, name="consultant-qr"),
    path("admin/2fa/", security_views.setup, name="two-factor-setup"),
    path("admin/2fa/verify/", security_views.verify, name="two-factor-verify"),
    path("api/consultant.json", views.api, name="consultant-api"),
]
