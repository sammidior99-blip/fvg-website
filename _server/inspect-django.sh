#!/bin/bash
# Read-only look at the Django app, so the sales-consultant feature can be added to it.
# Prints structure only: no SECRET_KEY, passwords or database contents.
D=/home/ec2-user/mysite
echo "== files =="
cd "$D" 2>/dev/null || { echo "NO $D"; exit 1; }
find . -maxdepth 3 \( -name venv -o -name .venv -o -name env -o -name __pycache__ -o -name static -o -name staticfiles -o -name media -o -name .git -o -name node_modules -o -name migrations \) -prune -o \( -name "*.py" -o -name "*.sqlite3" -o -type d \) -print | sort | tr '\n' ' '; echo
echo "== gunicorn =="
systemctl list-units --type=service --no-legend 2>/dev/null | grep -iE "gunicorn|django|mysite" | awk '{print $1}' | tr '\n' ' '; echo
PY=$(ps -eo args | grep -m1 "[g]unicorn" | awk '{print $1}' | sed 's/gunicorn$/python/'); [ -x "$PY" ] || PY=$(ls -d $D/*/bin/python 2>/dev/null | head -1); [ -x "$PY" ] || PY=python3
echo "python: $PY | gunicorn: $(ps -eo args | grep -m1 '[g]unicorn' | cut -c1-150)"
echo "== django =="
sudo -u ec2-user "$PY" manage.py shell -c '
import django
from django.conf import settings as s
from django.apps import apps
print("django", django.get_version(), "| settings", s.SETTINGS_MODULE, "| urls", s.ROOT_URLCONF)
print("apps", [a for a in s.INSTALLED_APPS if not a.startswith("django.")])
print("db", s.DATABASES["default"]["ENGINE"].split(".")[-1], "| media", s.MEDIA_URL, s.MEDIA_ROOT, "| static", s.STATIC_URL, s.STATIC_ROOT)
print("email", getattr(s, "EMAIL_BACKEND", "-").split(".")[-1], "| host set:", bool(getattr(s, "EMAIL_HOST", "")) and s.EMAIL_HOST != "localhost", "| user set:", bool(getattr(s, "EMAIL_HOST_USER", "")))
for m in apps.get_models():
    if m._meta.app_label not in ("admin", "auth", "contenttypes", "sessions"):
        print("model", m._meta.label, [f.name for f in m._meta.fields])
from django.urls import get_resolver
print("urls", [str(p.pattern) for p in get_resolver().url_patterns])
' 2>&1 | tail -n 25
echo "== views using forms =="
grep -rlE "def .*contact|class .*Contact" --include=*.py . 2>/dev/null | grep -v -e venv -e migrations | head
echo "== DONE =="
