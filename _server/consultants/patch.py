"""Add the consultants app to the Django project by APPENDING a marked block to settings.py and urls.py.
Nothing existing is edited; running it twice changes nothing. `patch.py DIR --remove` takes the blocks out again.
Usage: patch.py /home/ec2-user/mysite [--remove]"""
import re, sys
D = sys.argv[1]
MARK_A, MARK_B = "# >>> fvg consultants (added by _server/consultants/install.sh)", "# <<< fvg consultants"
BLOCKS = {
    f"{D}/mysite/settings.py": (
        "INSTALLED_APPS = list(INSTALLED_APPS) + ['consultants']\n"
        "MIDDLEWARE = list(MIDDLEWARE) + ['consultants.middleware.ConsultantMiddleware']\n"
        "CONSULTANT_MEDIA_ROOT = '/var/www/consultant-media'\n"
        "DATA_UPLOAD_MAX_MEMORY_SIZE = max(globals().get('DATA_UPLOAD_MAX_MEMORY_SIZE') or 0, 5 * 1024 * 1024)\n"
        "try:  # SMTP + notification addresses from /etc/fvg-mail.env (setup-mail.sh)\n"
        "    from consultants.mailconf import load as _fvg_mail\n"
        "    globals().update(_fvg_mail())\n"
        "except Exception:\n"
        "    pass\n"),
    f"{D}/mysite/urls.py": (
        "from django.urls import include as _fvg_include, path as _fvg_path\n"
        "urlpatterns = [_fvg_path('', _fvg_include('consultants.urls'))] + list(urlpatterns)\n"),
}
for f, block in BLOCKS.items():
    s = open(f, encoding="utf-8").read()
    s = re.sub(rf"\n*{re.escape(MARK_A)}.*?{re.escape(MARK_B)}\n?", "\n", s, flags=re.S).rstrip("\n") + "\n"
    if "--remove" not in sys.argv:
        s += f"\n{MARK_A}\n{block}{MARK_B}\n"
    open(f, "w", encoding="utf-8").write(s)
    print(("removed from " if "--remove" in sys.argv else "patched ") + f)
