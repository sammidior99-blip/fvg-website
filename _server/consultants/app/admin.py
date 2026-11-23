from django import forms
from django.apps import apps
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import Consultant, Referral

SITE = "https://summitbrilliance.com"


class ConsultantForm(forms.ModelForm):
    class Meta:
        model = Consultant
        exclude = ("code",)  # the code is given out automatically (fv01, fv02, ...) and never edited


@admin.register(Consultant)
class ConsultantAdmin(admin.ModelAdmin):
    form = ConsultantForm
    list_display = ("name_zh", "name_en", "code", "link", "qr_small", "active", "leads")
    list_filter = ("active",)
    search_fields = ("name_zh", "name_en", "code", "phone", "email")
    readonly_fields = ("code_info", "link", "qr_big", "created_at", "updated_at")
    fieldsets = (
        ("專屬連結及二維碼", {"fields": ("code_info", "link", "qr_big", "lang")}),
        ("顯示喺網站上嘅資料", {"fields": ("name_zh", "name_en", "title_zh", "title_en", "photo", "phone", "whatsapp", "wechat_id", "wechat_qr", "email")}),
        ("狀態", {"fields": ("active", "forward_to", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n=Count("referrals"))

    @admin.display(description="連結代號")
    def code_info(self, obj):
        return obj.code if obj.pk else f"儲存後自動分配（下一個係 {Consultant.next_code()}）"

    @admin.display(description="帶來查詢", ordering="n")
    def leads(self, obj):
        return getattr(obj, "n", 0)

    @admin.display(description="專屬連結")
    def link(self, obj):
        if not obj.pk: return "儲存後顯示"
        u = f"{SITE}/s/{obj.code}"
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', u, u)

    @admin.display(description="二維碼")
    def qr_small(self, obj):
        return format_html('<img src="/s/{}/link-qr.png" width="56" height="56" alt="">', obj.code) if obj.pk else ""

    @admin.display(description="二維碼（掃描即打開專屬連結）")
    def qr_big(self, obj):
        if not obj.pk: return "儲存後自動生成"
        return format_html('<img src="/s/{0}/link-qr.png" width="200" height="200" alt="" style="border:1px solid #ddd"><br>'
                           '<a href="/s/{0}/link-qr.png?download=1">下載二維碼 PNG</a>', obj.code)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("created_at", "consultant", "code", "who", "contact", "enquiry_link")
    list_filter = ("consultant",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

    def _enq(self, obj):
        try:
            return apps.get_model("pages", "Enquiry").objects.filter(pk=obj.enquiry_id).first()
        except LookupError:
            return None

    @admin.display(description="稱呼")
    def who(self, obj):
        e = self._enq(obj)
        return (getattr(e, "parent_name", "") or getattr(e, "student_name", "")) if e else "（已刪除）"

    @admin.display(description="聯絡方式")
    def contact(self, obj):
        e = self._enq(obj)
        return " / ".join(x for x in (getattr(e, "phone", ""), getattr(e, "email", "")) if x) if e else ""

    @admin.display(description="查詢")
    def enquiry_link(self, obj):
        return format_html('<a href="/admin/pages/enquiry/{}/change/">查看 #{}</a>', obj.enquiry_id, obj.enquiry_id)
