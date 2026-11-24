import threading

_local = threading.local()
SCRIPT = b'<script src="/consultant.js" defer></script>'


def current_request():
    return getattr(_local, "request", None)


class ConsultantMiddleware:
    """Remembers the request (so a new enquiry can be linked to the consultant cookie) and adds the
    consultant script to Django-rendered pages such as the contact page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        admin_page = request.path.startswith("/admin")
        if admin_page:  # 后台 always in Simplified Chinese (zhs.py)
            from django.utils import translation
            from .zhs import ADMIN_LANGUAGE
            before = translation.get_language()
            translation.activate(ADMIN_LANGUAGE)
            request.LANGUAGE_CODE = ADMIN_LANGUAGE
        try:
            response = self.get_response(request)
        finally:
            _local.request = None
            if admin_page:
                if before: translation.activate(before)
                else: translation.deactivate()
        if (not request.path.startswith("/admin") and response.status_code == 200 and not response.streaming
                and response.get("Content-Type", "").startswith("text/html")
                and b"</body>" in response.content and SCRIPT not in response.content):
            response.content = response.content.replace(b"</body>", SCRIPT + b"</body>", 1)
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response


class TwoFactorMiddleware:
    """For admin users who turned on (or must turn on) authenticator codes: after the password, ask for the code
    before any other /admin page opens."""
    OPEN = ("/admin/2fa/", "/admin/login/", "/admin/logout/", "/admin/jsi18n/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (request.path.startswith("/admin/") and not request.path.startswith(self.OPEN)
                and user is not None and user.is_authenticated and user.is_staff):
            from urllib.parse import quote
            from django.http import HttpResponseRedirect
            from .security import SESSION_KEY, two_factor_of
            tf = two_factor_of(user)
            if tf and tf.enabled and request.session.get(SESSION_KEY) != user.pk:
                return HttpResponseRedirect("/admin/2fa/verify/?next=" + quote(request.get_full_path()))
            if tf and tf.required and not tf.enabled:
                return HttpResponseRedirect("/admin/2fa/")
        return self.get_response(request)
