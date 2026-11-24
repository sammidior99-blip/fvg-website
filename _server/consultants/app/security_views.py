"""Pages for two-factor codes: /admin/2fa/ (turn on / off, backup codes) and /admin/2fa/verify/ (after the password)."""
from django.contrib import messages
from django.contrib.admin import site
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from . import security as sec
from .models import TwoFactor

PENDING = "fvg_2fa_pending"  # secret shown as a QR code, not saved until the first code is typed correctly


def _next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or "/admin/"
    return nxt if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()) else "/admin/"


def _page(request, title, **ctx):
    return render(request, "admin/consultants/two_factor.html",
                  {**site.each_context(request), "title": title, "next": _next(request), **ctx})


def _qr_svg(uri):
    import segno
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#111")


@never_cache
@staff_member_required
def verify(request):
    """Second step of the login: the 6-digit code from the phone (or a backup code)."""
    tf = sec.two_factor_of(request.user)
    if not tf or not tf.enabled or request.session.get(sec.SESSION_KEY) == request.user.pk:
        return HttpResponseRedirect(_next(request))
    error = ""
    if request.method == "POST":
        if sec.verify(tf, request.POST.get("code", "")):
            sec.record(request, request.user.get_username(), "2fa_ok")
            sec.clear(username=request.user.get_username(), ip=sec.client_ip(request), kinds=("2fa_fail",))
            request.session[sec.SESSION_KEY] = request.user.pk
            request.session.pop("fvg_2fa_fails", None)
            left = sec.backup_codes_left(tf)
            if left <= 3:
                messages.warning(request, f"备用码只剩 {left} 个，请到“双重验证”重新产生。")
            return HttpResponseRedirect(_next(request))
        sec.record(request, request.user.get_username(), "2fa_fail")
        fails = request.session.get("fvg_2fa_fails", 0) + 1
        request.session["fvg_2fa_fails"] = fails
        if fails >= sec.CODE_FAIL_LIMIT:
            logout(request)
            messages.error(request, "验证码错误次数太多，已登出。")
            return HttpResponseRedirect("/admin/login/")
        error = f"验证码不正确，请再试（还剩 {sec.CODE_FAIL_LIMIT - fails} 次机会）。"
    return _page(request, "输入验证码", mode="verify", error=error)


@never_cache
@staff_member_required
def setup(request):
    """Every admin user's own page: turn codes on (scan the QR code), new backup codes, or turn off."""
    tf, _ = TwoFactor.objects.get_or_create(user=request.user)
    username = request.user.get_username()
    error = ""
    if not tf.enabled:
        secret = request.session.get(PENDING) or sec.new_secret()
        request.session[PENDING] = secret
        if request.method == "POST":
            step = sec.check_code(secret, request.POST.get("code", ""))
            if step is None:
                error = "验证码不正确。请确认手机时间准确，然后输入 App 当前显示的 6 位数字。"
            else:
                tf.secret, tf.last_step, tf.enabled, tf.enabled_at = secret, step, True, timezone.now()
                codes = sec.new_backup_codes(tf)
                tf.save()
                request.session.pop(PENDING, None)
                request.session[sec.SESSION_KEY] = request.user.pk
                return _page(request, "双重验证已开启", mode="codes", codes=codes, just_enabled=True)
        return _page(request, "开启双重验证", mode="setup", secret=secret, qr=_qr_svg(sec.otpauth_uri(secret, username)),
                     required=tf.required, error=error)

    if request.method == "POST":
        action = request.POST.get("action")
        if not sec.verify(tf, request.POST.get("code", "")):
            error = "验证码不正确，未作修改。"
        elif action == "backup":
            codes = sec.new_backup_codes(tf)
            tf.save(update_fields=["backup_codes"])
            return _page(request, "新备用码", mode="codes", codes=codes)
        elif action == "disable" and not tf.required:
            tf.enabled, tf.secret, tf.backup_codes, tf.enabled_at = False, "", "", None
            tf.save()
            request.session.pop(sec.SESSION_KEY, None)
            messages.success(request, "已停用双重验证。")
            return HttpResponseRedirect("/admin/2fa/")
    return _page(request, "双重验证", mode="status", tf=tf, left=sec.backup_codes_left(tf), error=error)
