from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count
from django.utils.html import format_html, format_html_join

from .models import Consultant, Referral

SITE = "https://summitbrilliance.com"
GROUP = "銷售顧問"
GROUP_PERMS = ["view_referral", "change_referral", "view_consultant", "change_consultant"]


def own(request):
    """The consultant record of the logged-in user (None for the company admins)."""
    if request.user.is_superuser: return None
    return Consultant.objects.filter(user=request.user).first()


def enquiry_model():
    try:
        return apps.get_model("pages", "Enquiry")
    except LookupError:
        return None


# ================================================================ consultants
class ConsultantForm(forms.ModelForm):
    """Company admins: everything except the code, which is given out automatically (fv01, fv02, ...)."""
    login = forms.CharField(label="後台登入名稱", required=False, max_length=150,
        help_text="填咗就會開一個後台帳號俾呢位顧問（例如 fv01 或者佢嘅英文名）。佢登入 /admin 只會見到自己嘅客戶同自己嘅資料。")
    password = forms.CharField(label="設定 / 重設密碼", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="新帳號必須填；之後留空 = 密碼不變。至少 8 個字元，唔好用太簡單嘅密碼。")

    class Meta:
        model = Consultant
        exclude = ("code", "user")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        if self.instance.pk and self.instance.user_id:
            self.fields["login"].initial = self.instance.user.get_username()

    def clean(self):
        d = super().clean()
        login, pw = (d.get("login") or "").strip(), d.get("password") or ""
        if login:
            U = get_user_model()
            if U.objects.filter(username=login).exclude(pk=self.instance.user_id or 0).exists():
                self.add_error("login", "呢個登入名稱已經有人用緊，請換一個。")
            if not self.instance.user_id and not pw:
                self.add_error("password", "新帳號要設定密碼。")
            if pw and len(pw) < 8:
                self.add_error("password", "密碼最少要 8 個字元。")
            elif pw:
                try:
                    validate_password(pw)
                except forms.ValidationError as e:
                    self.add_error("password", e)
        return d


class OwnConsultantForm(forms.ModelForm):
    """A consultant editing their own details."""
    class Meta:
        model = Consultant
        fields = ("name_zh", "name_en", "title_zh", "title_en", "photo", "phone", "whatsapp", "wechat_id", "wechat_qr", "email")


@admin.register(Consultant)
class ConsultantAdmin(admin.ModelAdmin):
    list_display = ("name_zh", "name_en", "code", "link", "qr_small", "has_login", "active", "leads")
    list_filter = ("active",)
    search_fields = ("name_zh", "name_en", "code", "phone", "email")

    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(n=Count("referrals")).select_related("user")
        return qs if request.user.is_superuser else qs.filter(user=request.user)

    def get_form(self, request, obj=None, **kw):
        kw["form"] = ConsultantForm if request.user.is_superuser else OwnConsultantForm
        return super().get_form(request, obj, **kw)

    def get_fieldsets(self, request, obj=None):
        info = ("顯示喺網站上嘅資料", {"fields": ("name_zh", "name_en", "title_zh", "title_en", "photo", "phone", "whatsapp", "wechat_id", "wechat_qr", "email")})
        if not request.user.is_superuser:
            return (("我的專屬連結及二維碼", {"fields": ("code_info", "link", "qr_big")}), info)
        return (("專屬連結及二維碼", {"fields": ("code_info", "link", "qr_big", "lang")}), info,
                ("後台帳號（顧問自己登入睇客戶進度）", {"fields": ("login", "password")}),
                ("狀態", {"fields": ("active", "forward_to", "created_at", "updated_at")}))

    def get_readonly_fields(self, request, obj=None):
        return ("code_info", "link", "qr_big", "created_at", "updated_at")

    def get_list_display(self, request):
        return self.list_display if request.user.is_superuser else ("name_zh", "code", "link", "qr_small")

    def has_add_permission(self, request): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not request.user.is_superuser: return
        login, pw = (form.cleaned_data.get("login") or "").strip(), form.cleaned_data.get("password") or ""
        if not login: return
        U = get_user_model()
        u = obj.user or U(username=login)
        u.username, u.is_staff, u.is_superuser = login, True, False
        u.is_active = obj.active
        u.first_name = obj.name_en or obj.name_zh
        u.email = obj.email or u.email
        if pw: u.set_password(pw)
        u.save()
        g, _ = Group.objects.get_or_create(name=GROUP)
        g.permissions.set(Permission.objects.filter(content_type__app_label="consultants", codename__in=GROUP_PERMS))
        u.groups.add(g)
        if obj.user_id != u.pk:
            obj.user = u
            obj.save(update_fields=["user"])

    @admin.display(description="連結代號")
    def code_info(self, obj):
        return obj.code if obj.pk else f"儲存後自動分配（下一個係 {Consultant.next_code()}）"

    @admin.display(description="客戶", ordering="n")
    def leads(self, obj):
        return getattr(obj, "n", 0)

    @admin.display(description="後台帳號", boolean=True)
    def has_login(self, obj):
        return bool(obj.user_id and obj.user.is_active)

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


# ================================================================ customer follow-up
ENQ_FIELDS = [("created_at", "提交時間"), ("language", "語言"), ("parent_name", "家長／監護人"), ("student_name", "學生"),
              ("phone", "電話"), ("email", "電郵"), ("school", "就讀學校"), ("grade", "年級"), ("service", "感興趣的服務"),
              ("channel", "偏好聯絡方式"), ("message", "留言")]


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("when", "who", "student", "contact", "service", "consultant", "status", "next_date", "source")
    list_display_links = ("when", "who")
    list_filter = ("status", "consultant", "source")
    date_hierarchy = "created_at"
    search_fields = ("notes",)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("consultant")
        if request.user.is_superuser: return qs
        c = own(request)
        return qs.filter(consultant=c) if c else qs.none()

    def get_list_display(self, request):
        if request.user.is_superuser: return self.list_display
        return ("when", "who", "student", "contact", "service", "status", "next_date")

    def get_list_filter(self, request):
        return self.list_filter if request.user.is_superuser else ("status",)

    def get_fields(self, request, obj=None):
        f = ["details", "status", "next_date", "notes"]
        return (["consultant"] + f + ["source", "created_at", "updated_at"]) if request.user.is_superuser else f + ["updated_at"]

    def get_readonly_fields(self, request, obj=None):
        return ("details", "source", "created_at", "updated_at")

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        E = enquiry_model()
        if E and hasattr(E, "followed_up"):  # keep the company's enquiry list in step
            E._base_manager.filter(pk=obj.enquiry_id).update(followed_up=obj.status != "new")

    # ---- details of the enquiry itself (read from pages.Enquiry)
    def _enq(self, obj):
        E = enquiry_model()
        if not E: return None
        if getattr(self, "_cache", (None,))[0] is not obj:
            self._cache = (obj, E._base_manager.filter(pk=obj.enquiry_id).first())
        return self._cache[1]

    def _get(self, obj, f):
        e = self._enq(obj)
        if e is None: return ""
        disp = getattr(e, f"get_{f}_display", None)
        return disp() if disp else (getattr(e, f, "") or "")

    @admin.display(description="提交時間", ordering="created_at")
    def when(self, obj):
        v = self._get(obj, "created_at") or obj.created_at
        return v.strftime("%Y-%m-%d %H:%M")

    @admin.display(description="家長／稱呼")
    def who(self, obj):
        return self._get(obj, "parent_name") or ("（查詢已刪除）" if self._enq(obj) is None else "—")

    @admin.display(description="學生")
    def student(self, obj): return self._get(obj, "student_name")

    @admin.display(description="聯絡方式")
    def contact(self, obj):
        return " / ".join(x for x in (self._get(obj, "phone"), self._get(obj, "email")) if x)

    @admin.display(description="感興趣的服務")
    def service(self, obj): return self._get(obj, "service")

    @admin.display(description="客戶查詢內容")
    def details(self, obj):
        e = self._enq(obj)
        if e is None: return "呢個查詢已被刪除。"
        rows = [(label, self._get(obj, f)) for f, label in ENQ_FIELDS if hasattr(e, f)]
        rows = [(k, v.strftime("%Y-%m-%d %H:%M") if hasattr(v, "strftime") else v) for k, v in rows]
        return format_html('<table style="border-collapse:collapse">{}</table>', format_html_join("",
            '<tr><th style="text-align:left;padding:4px 16px 4px 0;white-space:nowrap;vertical-align:top">{}</th>'
            '<td style="padding:4px 0;white-space:pre-wrap">{}</td></tr>', rows))
