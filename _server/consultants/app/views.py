import html
import io
import json

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import Consultant

COOKIE = "fvg_consultant"
DAYS = 30
HOME = {"en": "/", "zh": "/zh/", "cn": "/cn/"}
BRAND = {"en": "Firmament Voyage Global", "zh": "中昊寰宇", "cn": "中昊寰宇"}
INVITE = {"en": "{n} invites you to {b}", "zh": "{n} 為您推薦 · {b}", "cn": "{n} 为您推荐 · {b}"}
DESC = {"en": "A global path for families who aim higher — growth planning, overseas admissions, identity and global mobility.",
        "zh": "托舉精英家庭的國際化之路：國際化成長規劃、海外升學、身份與全球流動性。",
        "cn": "托举精英家庭的国际化之路：国际化成长规划、海外升学、身份与全球流动性。"}


def find(code):
    c = Consultant.objects.filter(code=(code or "").strip().lower()).first()
    return c.current() if c else None


@require_GET
@never_cache
def go(request, code):
    """Personal link /s/<code>: remember the consultant for 30 days, then open the site.
    Link-preview robots (WhatsApp, Facebook...) read the title and picture on this short page."""
    c = find(code)
    lang = request.GET.get("lang") if request.GET.get("lang") in HOME else (c.lang if c else "zh")
    dest = HOME[lang]
    if not c:
        r = HttpResponseRedirect(dest); r.delete_cookie(COOKIE); return r
    name = (c.name_en if lang == "en" and c.name_en else c.name_zh) or c.name_en
    title = INVITE[lang].format(n=name, b=BRAND[lang])
    img = request.build_absolute_uri(c.photo.url if c.photo else "/images/logo-fvg.png")
    e = lambda s: html.escape(s, quote=True)
    page = (f'<!doctype html><html lang="{ {"en": "en", "zh": "zh-HK", "cn": "zh-CN"}[lang] }"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(title)}</title>'
            f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(DESC[lang])}">'
            f'<meta property="og:image" content="{e(img)}"><meta property="og:type" content="website">'
            f'<meta property="og:url" content="{e(request.build_absolute_uri())}"><meta name="robots" content="noindex">'
            f'<meta http-equiv="refresh" content="0; url={e(dest)}"></head>'
            f'<body style="font-family:system-ui,sans-serif;padding:40px;color:#0F2340">'
            f'<p><a href="{e(dest)}">{e(BRAND[lang])} →</a></p><script>location.replace({json.dumps(dest)})</script></body></html>')
    r = HttpResponse(page)
    r.set_cookie(COOKIE, c.code, max_age=DAYS * 86400, samesite="Lax", httponly=True, secure=request.is_secure())
    return r


@require_GET
@never_cache
def api(request):
    """The consultant this visitor came through, for the website's contact areas ({} = show company contact)."""
    c = find(request.COOKIES.get(COOKIE))
    if not c: return JsonResponse({})
    wa = c.wa_number()
    return JsonResponse({
        "code": c.code, "name_zh": c.name_zh, "name_en": c.name_en, "title_zh": c.title_zh, "title_en": c.title_en,
        "photo": c.photo.url if c.photo else "", "phone": c.phone, "email": c.email, "wechat_id": c.wechat_id,
        "wechat_qr": c.wechat_qr.url if c.wechat_qr else "",
        "whatsapp": f"https://wa.me/{wa}" if wa else "", "whatsapp_qr": f"/s/{c.code}/whatsapp-qr.png" if wa else "",
    }, json_dumps_params={"ensure_ascii": False})


@require_GET
def qr(request, code, kind):
    """QR codes: link-qr.png = the consultant's personal link; whatsapp-qr.png = chat with them on WhatsApp."""
    import segno
    c = Consultant.objects.filter(code=code.lower()).first()
    if not c: return HttpResponse(status=404)
    if kind == "whatsapp":
        if not c.wa_number(): return HttpResponse(status=404)
        data = f"https://wa.me/{c.wa_number()}"
    else:
        data = request.build_absolute_uri(f"/s/{c.code}")
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=12, border=2, dark="#0F2340")
    r = HttpResponse(buf.getvalue(), content_type="image/png")
    r["Cache-Control"] = "public, max-age=3600"
    if request.GET.get("download"):
        r["Content-Disposition"] = f'attachment; filename="{c.code}-{kind}-qr.png"'
    return r
