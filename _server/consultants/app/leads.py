"""Lead registration rules (獲客報備).
The same 服務對象 (student) = same name AND (same phone OR same last 4 ID digits), unless both genders are filled in and differ.
A parent with two children = two students. The first registration wins while it is protected:
protection lasts LEAD_PROTECT_DAYS (default 90) after the last follow-up; signed students stay protected."""
import re

from django.utils import timezone

from .models import Referral


def norm_name(s): return re.sub(r"\s+", "", s or "").lower()


def norm_phone(s):
    d = re.sub(r"\D", "", s or "")
    return d[-8:] if len(d) >= 8 else d  # last 8 digits: same number with or without +852 / +86


def norm_id(s): return re.sub(r"[^0-9A-Za-z]", "", s or "").upper()[-4:]


def matches(name, gender="", phone="", id4="", exclude_pk=None):
    """Existing (not released) records of the same student."""
    n, p, i = norm_name(name), norm_phone(phone), norm_id(id4)
    if not n or not (p or i): return []
    out = []
    for r in Referral.objects.exclude(pk=exclude_pk).exclude(status="released").select_related("consultant"):
        if norm_name(r.student_name) != n: continue
        if gender and r.gender and gender != r.gender: continue
        if (p and norm_phone(r.phone) == p) or (i and norm_id(r.id_last4) == i):
            out.append(r)
    return out


def siblings(phone, name, exclude_pk=None):
    """Other students registered with the same phone (e.g. a brother or sister) - for information only."""
    p, n = norm_phone(phone), norm_name(name)
    if not p: return []
    return [r for r in Referral.objects.exclude(pk=exclude_pk).exclude(status="released")
            if norm_phone(r.phone) == p and norm_name(r.student_name) != n]


def note(obj, text):
    stamp = timezone.localtime().strftime("%Y-%m-%d")
    obj.notes = (obj.notes.rstrip() + "\n" if obj.notes.strip() else "") + f"[{stamp}] {text}"


def release(old, by):
    """An expired record that someone else has now registered."""
    old.status = "released"
    note(old, f"保護期已過，由 {by} 重新報備。")
    old.save(update_fields=["status", "notes", "updated_at"])


def from_enquiry(e, consultant=None, code=""):
    """A website booking form was submitted: register (or attach to) the student it is about."""
    f = lambda k: (getattr(e, k, "") or "")
    disp = lambda k: (getattr(e, f"get_{k}_display")() if hasattr(e, f"get_{k}_display") else f(k))
    existing = Referral.objects.filter(enquiry_ids__contains=f",{e.pk},").first()
    if existing: return existing
    found = matches(f("student_name"), "", f("phone"))
    prot = [m for m in found if m.is_protected()]
    if prot:  # first registration wins
        m = prot[0]
        m.add_enquiry(e.pk)
        note(m, f"客戶再次經官網提交查詢（#{e.pk}{'，經 ' + code + ' 連結' if code else ''}）。")
        m.save()
        return m
    open_ = [m for m in found if not m.consultant_id]
    if open_:  # not yet assigned: attach, and give it to the consultant whose link was used
        m = open_[0]
        m.add_enquiry(e.pk)
        if consultant:
            m.consultant, m.code, m.source, m.last_activity = consultant, code, "link", timezone.now()
        m.save()
        return m
    if found and not consultant:  # expired registration, no new consultant: keep the history together
        m = found[0]
        m.add_enquiry(e.pk)
        note(m, f"客戶再次經官網提交查詢（#{e.pk}），保護期已過，可由公司重新分派。")
        m.save()
        return m
    r = Referral(consultant=consultant, code=code, source="link" if consultant else "website",
                 student_name=f("student_name"), parent_name=f("parent_name"), phone=f("phone"), email=f("email"),
                 school=f("school"), grade=str(disp("grade"))[:50], interest=str(disp("service"))[:200],
                 last_activity=timezone.now() if consultant else None)
    r.add_enquiry(e.pk)
    if f("message"): r.notes = f"客戶留言：{f('message')}"
    r.save()
    for m in found:  # older, expired registrations of the same student
        release(m, consultant.name_zh if consultant else "官網新查詢")
    return r
