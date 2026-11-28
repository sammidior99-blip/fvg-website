"""关系图 (company only), drawn as a mind map: the company in the middle-left, every consultant branching out
to their clients, and from a client who became a 推荐渠道, that person's own clients and recruits, and so on.
Click a name to open the client / consultant."""
from collections import defaultdict

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join, mark_safe

from .models import Application, Consultant, Referral

ST_COLOR = {"new": "#1565c0", "contacted": "#00838f", "meeting": "#6a1b9a", "proposal": "#b26a00", "signed": "#2e7d32", "closed": "#757575"}


def build():
    today = timezone.localdate()
    people = {c.pk: c for c in Consultant.objects.all().order_by("code")}
    kids = defaultdict(list)            # consultant pk -> consultants they introduced
    for c in people.values():
        if c.parent_id in people and c.parent_id != c.pk: kids[c.parent_id].append(c)
    leads = defaultdict(list)           # consultant pk (or None) -> their clients
    for r in Referral.objects.exclude(status="released").order_by("-created_at"):
        leads[r.consultant_id].append(r)
    from_client = {}                    # referral pk -> the consultant this client became (推荐新顾问 with 从我的客户中选择)
    became = {}                         # consultant pk -> the client record they came from
    for a in Application.objects.filter(status="approved", referral__isnull=False, consultant__isnull=False):
        from_client[a.referral_id] = people.get(a.consultant_id)
        became[a.consultant_id] = a.referral_id

    def team_size(c, seen):
        n, s = len(leads[c.pk]), sum(1 for r in leads[c.pk] if r.status == "signed")
        for k in kids[c.pk]:
            if k.pk in seen: continue
            seen.add(k.pk); a, b = team_size(k, seen); n += a; s += b
        return n, s

    def lead_li(r, seen):
        late = (today - r.next_date).days if r.next_date and r.status not in ("signed", "closed") else None
        deal = format_html('<div class="fvt-x">成交 {}</div>', f"{r.currency} {r.amount:,.0f}") if r.status == "signed" and r.amount else ""
        meta = " · ".join(x for x in (f"家长 {r.parent_name}" if r.parent_name and r.student_name else "", r.phone or "") if x)
        nxt = "" if late is None else format_html('<div class="fvt-x" style="color:{}">下次跟进 {}{}</div>',
            "#c62828" if late > 0 else "#b26a00" if late == 0 else "inherit", f"{r.next_date:%m-%d}", f"（逾期 {late} 天）" if late > 0 else "（今天）" if late == 0 else "")
        node = format_html('<div class="fvt-n fvt-lead" style="--c:{}"><div class="fvt-t"><a href="{}">{}</a>'
                           '<span class="fvt-st">{}</span></div>{}{}{}</div>',
                           ST_COLOR.get(r.status, "#757575"), reverse("admin:consultants_referral_change", args=[r.pk]),
                           r.student_name or r.parent_name or "客户", r.get_status_display(),
                           format_html('<div class="fvt-m">{}</div>', meta) if meta else "", nxt, deal)
        sub = from_client.get(r.pk)
        if sub and sub.pk not in seen:   # this client became a 推荐渠道: their own team branches out from them
            seen.add(sub.pk)
            return format_html('<li class="fvt-r">{}<ul>{}</ul></li>', node, person_li(sub, seen, via_client=True))
        return format_html('<li class="fvt-r">{}</li>', node)

    def person_li(c, seen, via_client=False):
        n, s = team_size(c, set([c.pk]))
        own = len(leads[c.pk])
        down = [k for k in kids[c.pk] if k.pk not in seen and not (became.get(k.pk) and any(r.pk == became[k.pk] for r in leads[c.pk]))]
        for k in down: seen.add(k.pk)
        children = [lead_li(r, seen) for r in leads[c.pk]] + [person_li(k, seen) for k in down]
        tag = format_html('<span class="fvt-tag fvt-{}">{}</span>', c.kind, c.get_kind_display())
        off = mark_safe(' <span class="fvt-off">已停用</span>') if not c.active else ""
        orig = ""
        if became.get(c.pk) and not via_client:
            orig = format_html('<div class="fvt-m">原为客户 <a href="{}">查看</a></div>', reverse("admin:consultants_referral_change", args=[became[c.pk]]))
        stats = f"客户 {own}" + (f" · 含下线共 {n} · 已签约 {s}" if n != own else f" · 已签约 {s}")
        head = format_html('<div class="fvt-n fvt-person fvt-k-{}"><div class="fvt-t">{}<a href="{}"><b>{}</b></a> <code>{}</code>{}</div>'
                           '<div class="fvt-m">{}</div>{}</div>',
                           c.kind, tag, reverse("admin:consultants_consultant_change", args=[c.pk]), c.name_zh, c.code, off, stats, orig)
        body = format_html("<ul>{}</ul>", format_html_join("", "{}", ((x,) for x in children))) if children \
            else mark_safe('<ul><li class="fvt-empty"><div class="fvt-n">暂无客户</div></li></ul>')
        return format_html('<li class="fvt-p">{}{}</li>', head, body)

    seen = set()
    roots = [c for c in people.values() if c.parent_id not in people or c.parent_id == c.pk]
    for c in roots: seen.add(c.pk)
    items = [person_li(c, seen) for c in roots]
    left = [c for c in people.values() if c.pk not in seen]   # safety net (e.g. a loop): never hide anyone
    for c in left: seen.add(c.pk)
    items += [person_li(c, seen) for c in left]
    if leads[None]:
        items.append(format_html('<li class="fvt-p"><div class="fvt-n fvt-person fvt-k-none"><div class="fvt-t"><span class="fvt-tag fvt-none">未分派</span>'
                                 '<b>公司未分派的客户</b></div><div class="fvt-m">客户 {}</div></div><ul>{}</ul></li>',
                                 len(leads[None]), format_html_join("", "{}", ((lead_li(r, seen),) for r in leads[None]))))
    totals = {"people": len(people), "channel": sum(1 for c in people.values() if c.kind == "channel"),
              "leads": sum(len(v) for v in leads.values()), "signed": sum(1 for v in leads.values() for r in v if r.status == "signed")}
    return format_html_join("", "{}", ((x,) for x in items)), totals
