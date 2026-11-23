"""業績總覽 as an Excel file: sheet 總覽 (the same figures as the page) and sheet 客戶明細 (one row per lead).
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

    # ---- 總覽
    ws = wb.active
    ws.title = "總覽"
    who = f"{consultant.name_zh}（{consultant.code}）" if consultant else "全公司"
    ws.append(["業績總覽"]); ws["A1"].font = Font(bold=True, size=14)
    ws.append(["範圍", who])
    ws.append(["期間", f"{period_label}（按報備時間）"])
    ws.append(["匯出時間", timezone.localtime().strftime("%Y-%m-%d %H:%M")])
    ws.append(["匯出帳號", request.user.get_username()])
    ws.append([])
    statuses = ctx["statuses"]
    cols = ["", "報備"] + [v for _, v in statuses] + ["成交率"] + [f"成交金額 {c}" for c in CURRENCIES] + ["保護中", "待跟進"]

    def block(title, groups):
        ws.append([title]); ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        header(ws, cols)
        for name, s in groups:
            put(ws, [name, s["total"]] + [s["by"].get(k, 0) for k, _ in statuses] + [s["rate"]]
                + [float(s["amounts"][c]) if c in s["amounts"] else 0 for c in CURRENCIES] + [s["protected"], s["due"]])
        if not groups: ws.append(["暫時未有資料"])
        ws.append([])

    block("合計", [("全部", ctx["total"])])
    if ctx["is_boss"]: block("按顧問", ctx["by_consultant"])
    block("按合作方式", ctx["by_coop"])
    if ctx["by_partner"]: block("按合作方名稱", ctx["by_partner"])
    ws.append(["成交金額只計「已簽約」嘅客戶。保護期：最後跟進後 %s 日；已簽約永久保護。" % ctx["protect_days"]])
    widths(ws)
    ws.column_dimensions["A"].width = 28

    # ---- 客戶明細
    ws2 = wb.create_sheet("客戶明細")
    today = timezone.localdate()
    cols2 = (["報備時間"] + (["報備顧問", "顧問代號"] if ctx["is_boss"] else [])
             + ["服務對象", "性別", "年級", "就讀學校", "客戶／家長", "電話", "微信號", "電郵", "感興趣的服務",
                "合作方式", "合作方名稱", "錄入方式", "進度", "下次跟進日期", "最後跟進", "保護狀態",
                "簽約日期", "簽約產品", "合約金額", "貨幣", "跟進備註"])
    header(ws2, cols2)
    for r in sorted(rows, key=lambda r: r.created_at):
        u = r.protected_until()
        prot = ("未分派" if not r.consultant_id else "永久（已簽約）" if u == "permanent"
                else f"保護至 {u:%Y-%m-%d}" if u and u >= today else "已過期")
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
    name = f"業績總覽-{consultant.code + '-' if consultant else ''}{period_label}-{timezone.localdate():%Y%m%d}.xlsx"
    from urllib.parse import quote
    resp["Content-Disposition"] = f"attachment; filename=\"report-{timezone.localdate():%Y%m%d}.xlsx\"; filename*=UTF-8''{quote(name)}"
    wb.save(resp)
    return resp
