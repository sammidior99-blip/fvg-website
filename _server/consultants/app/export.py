"""业绩总览 as an Excel file: sheet 总览 (the same figures as the page) and sheet 客户明细 (one row per lead).
Uses exactly the leads the page shows, so a consultant only ever exports their own customers."""
from django.http import HttpResponse
from django.utils import timezone

FILL = "0F2340"
CURRENCIES = ["HKD", "CNY", "USD"]


def report_xlsx(request, ctx, rows, period_label, consultant):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=FILL)
    wb = Workbook()

    def header(ws, values):
        ws.append(values)
        for cell in ws[ws.max_row]:
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(vertical="center")

    def put(ws, values):
        ws.append(values)
        for cell in ws[ws.max_row]:  # text typed by website visitors (e.g. "=...") must stay text, never a formula
            if cell.data_type == "f": cell.data_type = "s"

    def widths(ws, minimum=8, maximum=40):
        for i, col in enumerate(ws.columns, 1):
            w = max((sum(2 if ord(ch) > 255 else 1 for ch in str(c.value)) for c in col if c.value is not None), default=minimum)
            ws.column_dimensions[get_column_letter(i)].width = max(minimum, min(maximum, w + 2))

    # ---- 总览
    ws = wb.active
    ws.title = "总览"
    who = f"{consultant.name_zh}（{consultant.code}）" if consultant else "全公司"
    ws.append(["业绩总览"]); ws["A1"].font = Font(bold=True, size=14)
    ws.append(["范围", who])
    ws.append(["期间", f"{period_label}（按报备时间）"])
    ws.append(["导出时间", timezone.localtime().strftime("%Y-%m-%d %H:%M")])
    ws.append(["导出账号", request.user.get_username()])
    ws.append([])
    statuses = ctx["statuses"]
    cols = ["", "报备"] + [v for _, v in statuses] + ["成交率"] + [f"成交金额 {c}" for c in CURRENCIES] + ["保护中", "待跟进"]

    def block(title, groups):
        ws.append([title]); ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        header(ws, cols)
        for name, s in groups:
            put(ws, [name, s["total"]] + [s["by"].get(k, 0) for k, _ in statuses] + [s["rate"]]
                + [float(s["amounts"][c]) if c in s["amounts"] else 0 for c in CURRENCIES] + [s["protected"], s["due"]])
        if not groups: ws.append(["暂无资料"])
        ws.append([])

    block("合计", [("全部", ctx["total"])])
    if ctx["is_boss"]: block("按顾问", ctx["by_consultant"])
    block("按合作方式", ctx["by_coop"])
    if ctx["by_partner"]: block("按合作方名称", ctx["by_partner"])
    ws.append(["成交金额只计“已签约”的客户。保护期：最后跟进后 %s 日；已签约永久保护。" % ctx["protect_days"]])
    widths(ws)
    ws.column_dimensions["A"].width = 28

    # ---- 客户明细
    ws2 = wb.create_sheet("客户明细")
    today = timezone.localdate()
    cols2 = (["报备时间"] + (["报备顾问", "顾问代号"] if ctx["is_boss"] else [])
             + ["服务对象", "性别", "年级", "就读学校", "客户／家长", "电话", "微信号", "邮箱", "感兴趣的服务",
                "合作方式", "合作方名称", "录入方式", "进度", "下次跟进日期", "最后跟进", "保护状态",
                "签约日期", "签约产品", "合约金额", "货币", "跟进备注"])
    header(ws2, cols2)
    for r in sorted(rows, key=lambda r: r.created_at):
        u = r.protected_until()
        prot = ("未分派" if not r.consultant_id else "永久（已签约）" if u == "permanent"
                else f"保护至 {u:%Y-%m-%d}" if u and u >= today else "已过期")
        loc = lambda d: timezone.localtime(d).replace(tzinfo=None) if d else None
        put(ws2, [loc(r.created_at)]
            + ([r.consultant.name_zh if r.consultant else "未分派", r.consultant.code if r.consultant else ""] if ctx["is_boss"] else [])
            + [r.student_name, r.get_gender_display() if r.gender else "", r.grade, r.school, r.parent_name, r.phone, r.wechat, r.email,
               r.interest, r.get_coop_type_display(), r.coop_name, r.get_source_display(), r.get_status_display(), r.next_date,
               loc(r.last_activity), prot, r.signed_date, r.get_product_display() if r.product else "",
               float(r.amount) if r.amount is not None else None, r.currency if r.amount is not None else "", r.notes])
    for row in ws2.iter_rows(min_row=2):
        for cell in row:
            if hasattr(cell.value, "hour"): cell.number_format = "yyyy-mm-dd hh:mm"
            elif hasattr(cell.value, "isoformat"): cell.number_format = "yyyy-mm-dd"
            elif isinstance(cell.value, float): cell.number_format = "#,##0.00"
    widths(ws2)
    ws2.freeze_panes = "B2"
    ws2.auto_filter.ref = ws2.dimensions

    resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    name = f"业绩总览-{consultant.code + '-' if consultant else ''}{period_label}-{timezone.localdate():%Y%m%d}.xlsx"
    from urllib.parse import quote
    resp["Content-Disposition"] = f"attachment; filename=\"report-{timezone.localdate():%Y%m%d}.xlsx\"; filename*=UTF-8''{quote(name)}"
    wb.save(resp)
    return resp
