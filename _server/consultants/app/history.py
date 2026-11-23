"""Automatic change history (修改紀錄) for 客戶報備.
Every save or delete of a Referral, from any path (admin form, website booking form, company assignment actions,
release after the protection period, sync_leads), is compared with the values loaded from the database and written
to ReferralLog together with the logged-in user (from the current request) or 「系統」."""
from django.db.models.signals import post_delete, post_init, post_save

from .middleware import current_request
from .models import Referral, ReferralLog

SKIP = {"id", "created_at", "updated_at", "enquiry_ids", "last_activity"}


def tracked():
    return [f for f in Referral._meta.concrete_fields if f.name not in SKIP]


def snapshot(obj):
    return {f.attname: getattr(obj, f.attname, None) for f in tracked()}


def show(obj, f, v):
    """Human-readable value of field f for value v."""
    if v in (None, ""): return ""
    if f.is_relation:
        o = f.related_model._base_manager.filter(pk=v).first()
        return str(o) if o else f"#{v}"
    if f.choices: return str(dict(f.flatchoices).get(v, v))
    if hasattr(v, "isoformat"): return v.isoformat()
    return str(v)


def who():
    """(user, display name) of whoever is making the change."""
    req = current_request()
    u = getattr(req, "user", None) if req is not None else None
    if u is not None and u.is_authenticated:
        from .models import Consultant
        c = Consultant.objects.filter(user=u).first()
        name = f"{c.name_zh}（{c.code}）" if c else (u.get_full_name() or u.get_username())
        return u, name + ("" if c else "（公司）" if u.is_superuser else "")
    if req is not None and not req.path.startswith("/admin"): return None, "系統：官網表格"
    return None, "系統"


def diff(obj, before):
    out = []
    for f in tracked():
        old, new = before.get(f.attname), getattr(obj, f.attname, None)
        if old == new or (old in (None, "") and new in (None, "")): continue
        o, n = show(obj, f, old), show(obj, f, new)
        if o == n: continue
        if f.name == "notes" and o and n.startswith(o):  # notes are usually appended: keep only the new part
            o, n = "（之前內容不變）", "＋ " + n[len(o):].strip()
        out.append([str(f.verbose_name), o, n])
    return out


def remember(sender, instance, **kw):
    instance._fvg_before = snapshot(instance) if instance.pk else None


def saved(sender, instance, created, raw=False, **kw):
    if raw: return
    before = getattr(instance, "_fvg_before", None)
    user, actor = who()
    if created or before is None:
        ch = [[str(f.verbose_name), "", show(instance, f, getattr(instance, f.attname))] for f in tracked()
              if getattr(instance, f.attname) not in (None, "") and f.name != "currency"]
        action = "create"
    else:
        ch, action = diff(instance, before), "change"
        if not ch: return
    ReferralLog.objects.create(referral=instance, referral_pk=instance.pk, label=str(instance)[:250],
                               user=user, actor=actor, action=action, changes=ch)
    instance._fvg_before = snapshot(instance)


def deleted(sender, instance, **kw):
    user, actor = who()
    ch = [[str(f.verbose_name), show(instance, f, getattr(instance, f.attname)), ""] for f in tracked()
          if getattr(instance, f.attname) not in (None, "") and f.name != "currency"]
    ReferralLog.objects.create(referral=None, referral_pk=instance.pk, label=str(instance)[:250],
                               user=user, actor=actor, action="delete", changes=ch)


def connect():
    post_init.connect(remember, sender=Referral, dispatch_uid="fvg-referral-log-init")
    post_save.connect(saved, sender=Referral, dispatch_uid="fvg-referral-log-save")
    post_delete.connect(deleted, sender=Referral, dispatch_uid="fvg-referral-log-delete")
