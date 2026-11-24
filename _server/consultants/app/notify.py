"""E-mail alerts (新预约 / 新报备 / 分派) and the daily follow-up digest.
Sending never blocks or breaks the website: instant alerts go out in a background thread after the
database has saved, and any failure is only written to the log."""
import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

log = logging.getLogger(__name__)
OPEN = ("signed", "closed", "released")  # statuses that need no more follow-up
WARN_DAYS = (14, 7, 3, 1, 0)  # remind on these days before the protection period ends


def site(): return getattr(settings, "LEAD_SITE_URL", "https://summitbrilliance.com")
def company(): return list(getattr(settings, "LEAD_NOTIFY_EMAILS", []))
def lead_url(r): return f"{site()}/admin/consultants/referral/{r.pk}/change/"


def consultant_email(c):
    if not c or not c.active: return ""
    return c.email or (c.user.email if c.user_id and c.user and c.user.email else "")


def send(to, subject, rows, intro="", sync=False, raise_errors=False):
    """rows: list of (label, value) or a ready HTML string. sync=False: send in the background after commit."""
    to = sorted({t for t in to if t})
    if not to: return 0
    if isinstance(rows, str):
        body_html, body_txt = rows, ""
    else:
        body_html = "".join(f'<tr><td style="padding:4px 12px 4px 0;color:#667;white-space:nowrap;vertical-align:top">{escape(k)}</td>'
                            f'<td style="padding:4px 0">{v if getattr(v, "__html__", None) else escape(v)}</td></tr>'
                            for k, v in rows if v not in (None, ""))
        body_html = f"<table>{body_html}</table>"
        body_txt = "\n".join(f"{k}：{v}" for k, v in rows if v not in (None, ""))
    html = (f'<div style="font-family:system-ui,-apple-system,sans-serif;color:#0F2340;font-size:14px;line-height:1.6">'
            f'{f"<p>{escape(intro)}</p>" if intro else ""}{body_html}'
            f'<p style="color:#99a;font-size:12px;margin-top:24px">中昊寰宇 summitbrilliance.com 后台自动通知</p></div>')
    import re
    text = (intro + "\n\n" if intro else "") + (body_txt or re.sub(r"<[^>]+>", " ", body_html))

    def go():
        try:
            m = EmailMultiAlternatives(subject, text, None, to)
            m.attach_alternative(html, "text/html")
            return m.send()
        except Exception:
            if raise_errors: raise
            log.exception("mail failed: %s -> %s", subject, to)
            return 0
    if sync: return go()
    transaction.on_commit(lambda: threading.Thread(target=go, daemon=True).start())
    return len(to)


def _lead_rows(r):
    from django.utils.safestring import mark_safe
    return [("服务对象", f"{r.student_name}{'（' + r.get_gender_display() + '）' if r.gender else ''}"),
            ("年级 / 学校", " · ".join(x for x in (r.grade, r.school) if x)),
            ("家长", r.parent_name), ("电话", r.phone), ("微信", r.wechat), ("邮箱", r.email),
            ("感兴趣的服务", r.interest),
            ("合作方式", r.get_coop_type_display() + (f"：{r.coop_name}" if r.coop_name else "")),
            ("报备顾问", f"{r.consultant.name_zh}（{r.consultant.code}）" if r.consultant else "未分派"),
            ("进度", r.get_status_display()),
            ("备注", r.notes[-600:]),
            ("后台", mark_safe(f'<a href="{escape(lead_url(r))}">打开这个报备</a>'))]


def new_enquiry(e, r, consultant=None):
    """A website booking form was submitted (r = the 客户报备 it was registered under)."""
    try:
        who = r.student_name or r.parent_name or "客户"
        rows = [("查询编号", f"#{e.pk}"), ("客户留言", getattr(e, "message", "") or "")] + _lead_rows(r)
        if r.consultant and r.consultant != consultant:  # an existing, protected registration of another consultant
            intro = "这位服务对象已有报备，查询已并入原有记录。"
        elif consultant:
            intro = f"客户经 {consultant.name_zh} 的专属链接提交了预约。"
        else:
            intro = "客户没有经顾问链接提交，请到后台分派给顾问。"
        send(company(), f"【新预约】{who} · {r.consultant.name_zh if r.consultant else '未分派'}", rows, intro)
        if r.consultant:
            send([consultant_email(r.consultant)], f"【新预约】{who}", rows,
                 f"{r.consultant.name_zh} 你好，你的客户经官网提交了预约，请尽快联系。")
    except Exception:
        log.exception("new_enquiry alert failed")


def new_referral(r, by_company=False):
    """A consultant (or the company) entered a 客户报备 by hand."""
    try:
        who = r.student_name or r.parent_name or "客户"
        if not by_company:
            send(company(), f"【新报备】{who} · {r.consultant.name_zh if r.consultant else '—'}", _lead_rows(r))
        elif r.consultant:
            assigned(r)
    except Exception:
        log.exception("new_referral alert failed")


def assigned(r):
    """The company gave a lead to a consultant."""
    try:
        if not r.consultant: return
        send([consultant_email(r.consultant)], f"【公司分派】{r.student_name or r.parent_name or '客户'}", _lead_rows(r),
             f"{r.consultant.name_zh} 你好，公司把以下客户分派给你，请尽快联系。")
    except Exception:
        log.exception("assigned alert failed")


# ------------------------------------------------------------------ daily digest

def digest_data(today=None):
    """Per consultant: overdue / due today / protection ending soon, plus unassigned website leads for the company."""
    from .models import Referral
    today = today or timezone.localdate()
    out = {}
    unassigned = []
    for r in Referral.objects.exclude(status__in=OPEN).select_related("consultant", "consultant__user"):
        if not r.consultant_id:
            if timezone.localdate(r.created_at) <= today - timedelta(days=1): unassigned.append(r)
            continue
        d = out.setdefault(r.consultant, {"overdue": [], "today": [], "expiring": []})
        if r.next_date and r.next_date < today: d["overdue"].append(r)
        elif r.next_date == today: d["today"].append(r)
        u = r.protected_until()
        if u not in (None, "permanent") and (u - today).days in WARN_DAYS: d["expiring"].append(r)
    return {c: d for c, d in out.items() if any(d.values())}, unassigned


def _table(rs, today, extra):
    from django.utils.html import format_html
    head = "".join(f'<th style="text-align:left;padding:4px 10px;border-bottom:1px solid #dde">{h}</th>'
                   for h in ("服务对象", "家长 / 电话", "进度", extra))
    body = ""
    for r in rs:
        if extra == "保护期至":
            u = r.protected_until(); x = f"{u:%Y-%m-%d}（尚余 {(u - today).days} 天）"
        elif extra == "报备时间":
            x = f"{timezone.localtime(r.created_at):%Y-%m-%d}"
        else:
            x = f"{r.next_date:%Y-%m-%d}" + (f"（逾期 {(today - r.next_date).days} 天）" if r.next_date < today else "")
        body += format_html('<tr><td style="padding:4px 10px"><a href="{}">{}</a></td><td style="padding:4px 10px">{}</td>'
                            '<td style="padding:4px 10px">{}</td><td style="padding:4px 10px">{}</td></tr>',
                            lead_url(r), r.student_name or "—", " ".join(x for x in (r.parent_name, r.phone) if x) or "—",
                            r.get_status_display(), x)
    return f'<table style="border-collapse:collapse;margin-bottom:18px"><tr>{head}</tr>{body}</table>'


def _sections(d, today, with_consultant=False):
    html = ""
    for key, title, extra in (("overdue", "已逾期", "下次跟进日期"), ("today", "今天要跟进", "下次跟进日期"),
                              ("expiring", "保护期快到（到期后其他顾问可重新报备；更新跟进可延长保护）", "保护期至")):
        if d.get(key):
            html += f'<h3 style="font-size:15px;margin:16px 0 6px">{title}（{len(d[key])}）</h3>' + _table(d[key], today, extra)
    return html


def send_digest(today=None, dry_run=False, stdout=None):
    today = today or timezone.localdate()
    per, unassigned = digest_data(today)
    sent = 0
    say = (lambda s: stdout.write(s)) if stdout else (lambda s: None)
    for c, d in per.items():
        to = consultant_email(c)
        n = sum(len(v) for v in d.values())
        subj = f"【跟进提醒 {today:%m-%d}】逾期 {len(d['overdue'])} · 今天 {len(d['today'])} · 保护期快到 {len(d['expiring'])}"
        say(f"{c.code} {c.name_zh} <{to or '没有邮箱'}>: {n} items")
        if to and not dry_run:
            sent += send([to], subj, _sections(d, today), f"{c.name_zh} 你好，以下是今天需要处理的客户。", sync=True)
    # company summary
    html = ""
    for c, d in per.items():
        if d["overdue"] or d["expiring"]:
            html += f'<h2 style="font-size:16px;margin:22px 0 4px">{escape(c.name_zh)}（{escape(c.code)}）</h2>' + \
                    _sections({"overdue": d["overdue"], "expiring": d["expiring"]}, today)
    if unassigned:
        html += f'<h2 style="font-size:16px;margin:22px 0 4px">未分派的官网预约（{len(unassigned)}）</h2>' + _table(unassigned, today, "报备时间")
    total_over = sum(len(d["overdue"]) for d in per.values())
    say(f"company <{', '.join(company()) or '未设置 NOTIFY_EMAILS'}>: overdue {total_over}, unassigned {len(unassigned)}")
    if html and company() and not dry_run:
        sent += send(company(), f"【每日跟进总表 {today:%m-%d}】逾期 {total_over} · 未分派 {len(unassigned)}", html, sync=True)
    return sent
