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
        try:
            response = self.get_response(request)
        finally:
            _local.request = None
        if (not request.path.startswith("/admin") and response.status_code == 200 and not response.streaming
                and response.get("Content-Type", "").startswith("text/html")
                and b"</body>" in response.content and SCRIPT not in response.content):
            response.content = response.content.replace(b"</body>", SCRIPT + b"</body>", 1)
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response
