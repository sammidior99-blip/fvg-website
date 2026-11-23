"""POST /api/booking - the booking form on the new (static) 聯絡與預約 page.
Saves it as a normal website enquiry (pages.Enquiry), so it shows in 諮詢查詢 as before; that in turn registers the
student in 客戶報備 (credited to the consultant whose link the visitor used) and sends the e-mail alerts."""
import re

from django.apps import apps
from django.core.cache import cache
from django.db import models
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

LIMIT, WINDOW = 5, 600  # at most 5 bookings per visitor IP per 10 minutes
LANGS = {"zh": "zh", "cn": "cn", "en": "en"}


def _ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))


def _clean(v, n):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (v or "").strip())[:n]


def _blank_for(f):
    """A harmless value for a required field the form does not fill."""
    if isinstance(f, models.BooleanField): return False
    if isinstance(f, (models.IntegerField, models.DecimalField, models.FloatField)): return 0
    return ""


@csrf_exempt  # a static page cannot carry Django's CSRF token; protected by honeypot, consent box and rate limit
@require_POST
def booking(request):
    p = request.POST
    if p.get("website"):  # honeypot filled in: a robot. Pretend all is well.
        return JsonResponse({"ok": True})
    name, contact = _clean(p.get("name"), 100), _clean(p.get("contact"), 120)
    role, concern, note = _clean(p.get("role"), 60), _clean(p.get("concern"), 120), _clean(p.get("note"), 2000)
    if not name or not contact or not p.get("consent"):
        return JsonResponse({"ok": False, "error": "missing"}, status=400)
    key = "fvg-booking-" + _ip(request)
    n = cache.get(key, 0)
    if n >= LIMIT:
        return JsonResponse({"ok": False, "error": "too_many"}, status=429)
    cache.set(key, n + 1, WINDOW)

    E = apps.get_model("pages", "Enquiry")
    names = {f.name: f for f in E._meta.concrete_fields}
    email = contact if "@" in contact else ""
    digits = re.sub(r"\D", "", contact)
    phone = contact if not email and len(digits) >= 7 and re.fullmatch(r"[\d\s+()\-]+", contact) else ""
    wechat = "" if (email or phone) else contact
    lines = [f"身份：{role}" if role else "", f"主要關切：{concern}" if concern else "",
             f"微信：{wechat}" if wechat else "", f"補充說明：{note}" if note else ""]
    data = {"parent_name": name, "email": email, "phone": phone or (contact if not email and not wechat else ""),
            "message": "\n".join(x for x in lines if x)}
    lang = LANGS.get(p.get("lang", ""), "")
    if "language" in names and lang:
        ch = [c[0] for c in (names["language"].choices or [])]
        if not ch or lang in ch: data["language"] = lang
    kw = {}
    for fname, f in names.items():
        if f.primary_key or getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False): continue
        if fname in data:
            v = data[fname]
            if getattr(f, "max_length", None): v = v[: f.max_length]
            kw[fname] = v
        elif not f.has_default() and not f.null and not f.blank and not isinstance(f, models.ForeignKey):
            kw[fname] = _blank_for(f)
    e = E.objects.create(**kw)  # triggers 客戶報備 registration + e-mail alerts (apps.py)

    from .models import Referral  # add what the enquiry model has no field for
    r = Referral.objects.filter(enquiry_ids__contains=f",{e.pk},").first()
    if r:
        changed = []
        if wechat and not r.wechat: r.wechat = wechat[:60]; changed.append("wechat")
        if concern and not r.interest: r.interest = concern[:200]; changed.append("interest")
        if changed: r.save(update_fields=changed + ["updated_at"])
    return JsonResponse({"ok": True})
