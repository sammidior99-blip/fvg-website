"""Mail settings for the notifications, read from /etc/fvg-mail.env on the server (written by setup-mail.sh).
The password lives only in that file (readable by root and the website program), never in GitHub.
settings.py does:  globals().update(consultants.mailconf.load())"""
PATH = "/etc/fvg-mail.env"


def read(path=PATH):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    out[k.strip()] = v
    except OSError:
        pass
    return out


def load(path=PATH):
    c = read(path)
    s = {"LEAD_NOTIFY_EMAILS": [x.strip() for x in c.get("NOTIFY_EMAILS", "").replace(";", ",").split(",") if x.strip()],
         "LEAD_SITE_URL": c.get("SITE_URL", "https://summitbrilliance.com").rstrip("/")}
    if c.get("EMAIL_HOST"):
        port = int(c.get("EMAIL_PORT") or 587)
        s.update(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                 EMAIL_HOST=c["EMAIL_HOST"].strip(), EMAIL_PORT=port,
                 EMAIL_HOST_USER=c.get("EMAIL_HOST_USER", "").strip(), EMAIL_HOST_PASSWORD=c.get("EMAIL_HOST_PASSWORD", ""),
                 EMAIL_USE_SSL=port == 465, EMAIL_USE_TLS=port != 465, EMAIL_TIMEOUT=20,
                 DEFAULT_FROM_EMAIL=(c.get("FROM_EMAIL") or c.get("EMAIL_HOST_USER", "")).strip(),
                 SERVER_EMAIL=(c.get("FROM_EMAIL") or c.get("EMAIL_HOST_USER", "")).strip())
    return s
