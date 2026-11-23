"""Admin login security: limits on wrong passwords, and optional authenticator-app codes (two-factor).

Limits (change in settings.py if needed):
  LOGIN_FAIL_LIMIT      = 5    wrong passwords for one login name from one IP ...
  LOGIN_IP_FAIL_LIMIT   = 20   ... or for any login names from one IP ...
  LOGIN_LOCK_MINUTES    = 15   ... within this many minutes = that IP is refused for this long.
Locks count per login name + IP, so somebody guessing the boss's password elsewhere cannot lock the boss out.
Emergency (on the server): manage.py login_security --help
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.utils import timezone

from .models import LoginAttempt, TwoFactor

FAIL_LIMIT = getattr(settings, "LOGIN_FAIL_LIMIT", 5)
IP_FAIL_LIMIT = getattr(settings, "LOGIN_IP_FAIL_LIMIT", 20)
LOCK_MINUTES = getattr(settings, "LOGIN_LOCK_MINUTES", 15)
CODE_FAIL_LIMIT = 5  # wrong authenticator codes in one login before being logged out
ISSUER = "Summit Brilliance"
SESSION_KEY = "fvg_2fa_user"  # set to the user's id once their code was checked in this login


# ---------------------------------------------------------------- who is asking
def client_ip(request):
    """The visitor's IP. Behind nginx every request comes from 127.0.0.1; nginx ADDS the real address as the
    last X-Forwarded-For entry (anything before it was sent by the visitor and can be made up)."""
    if request is None: return "?"
    ip = request.META.get("REMOTE_ADDR", "") or "?"
    if ip in ("127.0.0.1", "::1"):
        fwd = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if fwd: ip = fwd[-1]
    return ip[:45]


def record(request, username, kind):
    return LoginAttempt.objects.create(username=(username or "")[:150].strip().lower(), ip=client_ip(request), kind=kind,
                                       agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:200])


# ---------------------------------------------------------------- wrong-password limits
def _recent_fails(**filters):
    since = timezone.now() - timedelta(minutes=LOCK_MINUTES)
    # wrong authenticator codes count too: someone who has the password still cannot keep guessing codes
    return LoginAttempt.objects.filter(kind__in=("fail", "2fa_fail"), cleared=False, at__gte=since, **filters).count()


def is_locked(request, username):
    ip = client_ip(request)
    return (_recent_fails(ip=ip, username=(username or "").strip().lower()) >= FAIL_LIMIT
            or _recent_fails(ip=ip) >= IP_FAIL_LIMIT)


def clear(username=None, ip=None, kinds=("fail", "2fa_fail")):
    """Forget the wrong tries so far (after a good login, or when the company unlocks)."""
    qs = LoginAttempt.objects.filter(kind__in=kinds, cleared=False)
    if username is not None: qs = qs.filter(username=username.strip().lower())
    if ip is not None: qs = qs.filter(ip=ip)
    return qs.update(cleared=True)


class LockoutLoginForm(AdminAuthenticationForm):
    """The /admin login form, refusing to even check the password while the name/IP is locked."""
    error_messages = {**AdminAuthenticationForm.error_messages,
                      "locked": f"嘗試次數太多，請 {LOCK_MINUTES} 分鐘後再試。如需即時解鎖請聯絡公司管理員。"}

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and is_locked(self.request, username):
            record(self.request, username, "locked")
            raise forms.ValidationError(self.error_messages["locked"], code="locked")
        return super().clean()


def on_login_failed(sender, credentials, request=None, **kw):
    if request is not None and request.path.startswith("/admin"):
        record(request, credentials.get("username", ""), "fail")


def on_logged_in(sender, request, user, **kw):
    if request is None: return
    record(request, user.get_username(), "ok")
    # only wrong passwords: wrong authenticator codes are forgotten after a correct code (security_views.verify),
    # so knowing the password does not give fresh code guesses with every new login
    clear(username=user.get_username(), ip=client_ip(request), kinds=("fail",))
    LoginAttempt.objects.filter(at__lt=timezone.now() - timedelta(days=365)).delete()  # keep one year of 登入紀錄


# ---------------------------------------------------------------- authenticator codes (RFC 6238)
def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def _code_at(secret, step):
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    o = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[o:o + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def check_code(secret, code, last_step=0, now=None):
    """The 30-second step the code belongs to (one step either side allowed for phone clock drift), or None.
    A step at or before last_step is refused, so each code works only once."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6 or not secret: return None
    step = int((now or time.time()) // 30)
    for s in (step - 1, step, step + 1):
        if s > last_step and hmac.compare_digest(_code_at(secret, s), code):
            return s
    return None


def otpauth_uri(secret, username):
    from urllib.parse import quote
    return f"otpauth://totp/{quote(ISSUER)}:{quote(username)}?secret={secret}&issuer={quote(ISSUER)}&digits=6&period=30"


def _hash_backup(code):
    return hashlib.sha256((settings.SECRET_KEY + ":" + code).encode()).hexdigest()


def new_backup_codes(tf, n=10):
    """Ten one-time codes for when the phone is lost. Only their hashes are stored; the codes are shown once."""
    codes = ["-".join(secrets.token_hex(2) for _ in range(2)) for _ in range(n)]  # e.g. 3f9a-07c2
    tf.backup_codes = "\n".join(_hash_backup(c) for c in codes)
    return codes


def use_backup_code(tf, code):
    code = code.strip().lower().replace(" ", "")
    if len(code) == 8 and "-" not in code: code = code[:4] + "-" + code[4:]
    hashes = [h for h in tf.backup_codes.split("\n") if h]
    h = _hash_backup(code)
    if h not in hashes: return False
    hashes.remove(h)
    tf.backup_codes = "\n".join(hashes)
    tf.save(update_fields=["backup_codes"])
    return True


def backup_codes_left(tf):
    return len([h for h in tf.backup_codes.split("\n") if h])


def verify(tf, code):
    """Authenticator code or backup code. Saves the accepted step so the same code cannot be replayed."""
    step = check_code(tf.secret, code, tf.last_step)
    if step is not None:
        tf.last_step = step
        tf.save(update_fields=["last_step"])
        return True
    return use_backup_code(tf, code)


def two_factor_of(user):
    try:
        return user.two_factor
    except TwoFactor.DoesNotExist:
        return None
