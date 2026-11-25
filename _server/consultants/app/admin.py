from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count
from django.utils.html import format_html, format_html_join

from .models import PROTECT_DAYS, Application, Consultant, TeamTree, LeadReport, LoginAttempt, Message, Referral, ReferralLog, TwoFactor

SITE = "https://summitbrilliance.com"
GROUP = "销售顾问"
ACCOUNT_TITLE = "顾问账户设置"  # what a consultant (not the boss) sees for their own 销售顾问 record
GROUP_PERMS = ["view_referral", "change_referral", "add_referral", "view_consultant", "change_consultant", "view_leadreport",
               "view_message", "add_message", "change_message", "view_application", "add_application", "change_application"]


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
    login = forms.CharField(label="后台登录名称", required=False, max_length=150,
        help_text="填写后会为该顾问开通后台账号（例如 fv01 或其英文名）。其登录 /admin 后只能看到自己的客户和资料。")
    password = forms.CharField(label="设置 / 重设密码", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="新账号必须填；之后留空 = 密码不变。至少 8 个字符，请勿使用过于简单的密码。")
    require_2fa = forms.BooleanField(label="必须开启双重验证", required=False,
        help_text="勾选后，顾问下次登录须先用微信小程序“腾讯身份验证器”（或其他验证 App）完成设置，才可以继续使用后台。")
    is_admin = forms.BooleanField(label="总权限账号（老板／管理员）", required=False,
        help_text="勾选后，这个账号与老板一样：可查看所有顾问的客户和业绩、可以分派查询、开顾问账号。其本人的专属链接和客户仍归在其名下。")
    reset_2fa = forms.BooleanField(label="重设双重验证", required=False,
        help_text="顾问换了手机且备用码已用完时使用：清除其验证设置，下次登录时重新扫描 QR 码。")

    class Meta:
        model = Consultant
        exclude = ("code", "user")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        if self.instance.pk and self.instance.user_id:
            self.fields["login"].initial = self.instance.user.get_username()
            tf = TwoFactor.objects.filter(user_id=self.instance.user_id).first()
            self.fields["require_2fa"].initial = bool(tf and tf.required)
            self.fields["is_admin"].initial = self.instance.user.is_superuser
            self.fields["reset_2fa"].help_text += "（当前：" + ("已开启" if tf and tf.enabled else "未开启") + "）"

    def clean(self):
        d = super().clean()
        par = d.get("parent")
        if par and self.instance.pk and (par.pk == self.instance.pk or par.pk in self.instance.downline_ids()):
            self.add_error("parent", "推荐人不能是此人自己，或此人介绍进来的人。")
        login, pw = (d.get("login") or "").strip(), d.get("password") or ""
        if login:
            U = get_user_model()
            if U.objects.filter(username=login).exclude(pk=self.instance.user_id or 0).exists():
                self.add_error("login", "该登录名称已被使用，请更换。")
            if not self.instance.user_id and not pw:
                self.add_error("password", "新账号要设置密码。")
            if pw and len(pw) < 8:
                self.add_error("password", "密码最少要 8 个字符。")
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
    list_display = ("name_zh", "name_en", "code", "kind", "parent", "link", "qr_small", "has_login", "active", "leads")
    list_filter = ("active", "kind", ("parent", admin.RelatedOnlyFieldListFilter))
    search_fields = ("name_zh", "name_en", "code", "phone", "email")

    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(n=Count("referrals")).select_related("user", "parent")
        return qs if request.user.is_superuser else qs.filter(user=request.user)

    def get_form(self, request, obj=None, **kw):
        kw["form"] = ConsultantForm if request.user.is_superuser else OwnConsultantForm
        return super().get_form(request, obj, **kw)

    def get_fieldsets(self, request, obj=None):
        info = ("在网站上显示的资料", {"fields": ("name_zh", "name_en", "title_zh", "title_en", "photo", "phone", "whatsapp", "wechat_id", "wechat_qr", "email")})
        if not request.user.is_superuser:
            return (("我的专属链接及二维码", {"fields": ("code_info", "link", "qr_big")}), info,
                    ("我介绍的人", {"fields": ("team",), "description": "这些人报备的客户，你可以在“客户报备”中查看（只读）。"}))
        return (("专属链接及二维码", {"fields": ("code_info", "link", "qr_big", "lang")}), info,
                ("推荐关系", {"fields": ("kind", "parent", "team")}),
                ("后台账号（顾问自行登录查看客户进度）", {"fields": ("login", "password", "is_admin", "require_2fa", "reset_2fa")}),
                ("状态", {"fields": ("active", "forward_to", "created_at", "updated_at")}))

    def get_readonly_fields(self, request, obj=None):
        return ("code_info", "link", "qr_big", "team", "created_at", "updated_at")

    def get_list_display(self, request):
        return self.list_display if request.user.is_superuser else ("name_zh", "code", "link", "qr_small")

    def formfield_for_foreignkey(self, db_field, request, **kw):
        if db_field.name == "parent": kw["queryset"] = Consultant.objects.filter(active=True)
        return super().formfield_for_foreignkey(db_field, request, **kw)

    def has_add_permission(self, request): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    # A consultant only has their own record: the menu item opens it directly as 顾问账户设置 (the boss keeps 销售顾问).
    def changelist_view(self, request, extra_context=None):
        if not request.user.is_superuser:
            me = Consultant.objects.filter(user=request.user).first()
            if me:
                from django.shortcuts import redirect
                return redirect("admin:consultants_consultant_change", me.pk)
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if not request.user.is_superuser:
            extra_context = {**(extra_context or {}), "title": ACCOUNT_TITLE, "subtitle": None}
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        if not request.user.is_superuser and "_continue" not in request.POST:
            from django.shortcuts import redirect
            messages.success(request, "已保存。")
            return redirect("admin:consultants_consultant_change", obj.pk)
        return super().response_change(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not request.user.is_superuser: return
        login, pw = (form.cleaned_data.get("login") or "").strip(), form.cleaned_data.get("password") or ""
        if not login: return
        U = get_user_model()
        u = obj.user or U(username=login)
        admin_wanted = bool(form.cleaned_data.get("is_admin"))
        if not admin_wanted and u.pk and u.pk == request.user.pk:  # never lock yourself out of 总权限
            admin_wanted = True
            messages.warning(request, "你不能取消自己的总权限，请用另一个总权限账号操作。")
        u.username, u.is_staff, u.is_superuser = login, True, admin_wanted
        u.is_active = obj.active
        u.first_name = obj.name_en or obj.name_zh
        u.email = obj.email or u.email
        if pw: u.set_password(pw)
        u.save()
        tf, _ = TwoFactor.objects.get_or_create(user=u)
        if form.cleaned_data.get("reset_2fa"):
            tf.enabled, tf.secret, tf.backup_codes, tf.enabled_at = False, "", "", None
        tf.required = bool(form.cleaned_data.get("require_2fa"))
        tf.save()
        g, _ = Group.objects.get_or_create(name=GROUP)
        g.permissions.set(Permission.objects.filter(content_type__app_label="consultants", codename__in=GROUP_PERMS))
        u.groups.add(g)
        if obj.user_id != u.pk:
            obj.user = u
            obj.save(update_fields=["user"])

    @admin.display(description="介绍的人（下线）")
    def team(self, obj):
        if not obj.pk: return "—"
        ids = obj.downline_ids()
        if not ids: return "暂无"
        people = {c.pk: c for c in Consultant.objects.filter(pk__in=ids).annotate(n=Count("referrals"))}
        def line(c, depth):
            via = "" if c.parent_id == obj.pk else f"（经 {people[c.parent_id].name_zh} 介绍）" if c.parent_id in people else ""
            return (c.name_zh, c.code, via, c.n, "" if c.active else "（已停用）")
        rows = [line(people[i], 0) for i in ids if i in people]
        return format_html_join("", "<div>{}（{}）{}：客户 {} 位{}</div>", rows)

    @admin.display(description="链接代号")
    def code_info(self, obj):
        return obj.code if obj.pk else f"保存后自动分配（下一个是 {Consultant.next_code()}）"

    @admin.display(description="客户", ordering="n")
    def leads(self, obj):
        return getattr(obj, "n", 0)

    @admin.display(description="后台账号", boolean=True)
    def has_login(self, obj):
        return bool(obj.user_id and obj.user.is_active)

    @admin.display(description="专属链接")
    def link(self, obj):
        if not obj.pk: return "保存后显示"
        u = f"{SITE}/s/{obj.code}"
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', u, u)

    @admin.display(description="二维码")
    def qr_small(self, obj):
        return format_html('<img src="/s/{}/link-qr.png" width="56" height="56" alt="">', obj.code) if obj.pk else ""

    @admin.display(description="二维码（扫描即打开专属链接）")
    def qr_big(self, obj):
        if not obj.pk: return "保存后自动生成"
        return format_html('<img src="/s/{0}/link-qr.png" width="200" height="200" alt="" style="border:1px solid #ddd"><br>'
                           '<a href="/s/{0}/link-qr.png?download=1">下载二维码 PNG</a>', obj.code)


# ================================================================ lead registration (客户报备)
from django.contrib import messages  # noqa: E402
from django.template.response import TemplateResponse  # noqa: E402
from django.utils import timezone  # noqa: E402

from . import leads as L  # noqa: E402
from . import notify as N  # noqa: E402
from datetime import timedelta  # noqa: E402

ENQ_FIELDS = [("created_at", "提交时间"), ("language", "语言"), ("parent_name", "家长／监护人"), ("student_name", "学生"),
              ("phone", "电话"), ("email", "邮箱"), ("school", "就读学校"), ("grade", "年级"), ("service", "感兴趣的服务"),
              ("channel", "偏好联系方式"), ("message", "留言")]
FOLLOW_FIELDS = {"status", "next_date", "notes", "signed_date", "product", "amount"}


class LeadForm(forms.ModelForm):
    id_last4 = forms.CharField(label="身份证最后四位", max_length=30, required=False,
                               help_text="填写最后 4 位即可（也可贴上完整号码，系统只保留最后 4 位）；用于区分同名同姓，可留空")

    class Meta:
        model = Referral
        fields = "__all__"

    def __init__(self, *a, request=None, **k):
        super().__init__(*a, **k)
        self.request = request
        if "status" in self.fields:  # 已释放 is set by the system only
            self.fields["status"].choices = [c for c in self.fields["status"].choices if c[0] != "released"]
        if "consultant" in self.fields:
            self.fields["consultant"].queryset = Consultant.objects.filter(active=True)
            self.fields["consultant"].help_text = "留空 = 未分派"
        for f in ("student_name", "phone"):
            if f in self.fields: self.fields[f].required = True

    def clean_id_last4(self):
        v = L.norm_id(self.cleaned_data.get("id_last4"))
        if v and len(v) != 4: raise forms.ValidationError("请填身份证号码最后 4 个字（数字或字母）。")
        return v

    def clean(self):
        d = super().clean()
        if d.get("status") == "signed" and not d.get("signed_date"):
            d["signed_date"] = timezone.localdate(); self.cleaned_data["signed_date"] = d["signed_date"]
        mine = Consultant.objects.filter(user=self.request.user).first() if not self.request.user.is_superuser else d.get("consultant")
        self.claims, self.releases = [], []
        for m in L.matches(d.get("student_name"), d.get("gender"), d.get("phone"), d.get("id_last4"), exclude_pk=self.instance.pk):
            if m.is_protected():
                if mine and m.consultant_id == mine.pk:
                    raise forms.ValidationError(f"你已于 {timezone.localtime(m.created_at):%Y-%m-%d} 报备过该服务对象，请在“客户报备”列表中更新其进度。")
                u = m.protected_until()
                until = "（已签约，永久保护）" if u == "permanent" else f"，保护期至 {u:%Y-%m-%d}"
                team = Consultant.objects.get(pk=mine.pk).downline_ids() if mine and not self.request.user.is_superuser else []
                who = f"{m.consultant.name_zh}（{m.consultant.code}）" if self.request.user.is_superuser or m.consultant_id in team else "其他顾问"
                raise forms.ValidationError(f"报备不成功：该服务对象已由{who}于 {timezone.localtime(m.created_at):%Y-%m-%d} 报备{until}。以第一个报备为准。")
            (self.claims if not m.consultant_id else self.releases).append(m)
        return d


class ProtectionFilter(admin.SimpleListFilter):
    title, parameter_name = "保护状态", "prot"

    def lookups(self, request, model_admin): return (("on", "保护中"), ("off", "已过期／未分派"))

    def queryset(self, request, qs):
        if self.value() not in ("on", "off"): return qs
        ids = [r.pk for r in qs if r.is_protected() == (self.value() == "on")]
        return qs.filter(pk__in=ids)


class DueFilter(admin.SimpleListFilter):
    title, parameter_name = "跟进提醒", "due"

    def lookups(self, request, model_admin):
        return (("overdue", "已逾期"), ("today", "今天要跟进"), ("due", "今天或之前（逾期 + 今天）"), ("week", "未来 7 天"), ("none", "未定跟进日期"))

    def queryset(self, request, qs):
        v, t = self.value(), timezone.localdate()
        if not v: return qs
        qs = qs.exclude(status__in=["signed", "closed", "released"])
        if v == "overdue": return qs.filter(next_date__lt=t)
        if v == "today": return qs.filter(next_date=t)
        if v == "due": return qs.filter(next_date__lte=t)
        if v == "week": return qs.filter(next_date__gt=t, next_date__lte=t + timedelta(days=7))
        if v == "none": return qs.filter(next_date__isnull=True)
        return qs


class TeamFilter(admin.SimpleListFilter):
    """For a consultant who introduced others: their own clients / clients of the people they introduced."""
    title, parameter_name = "归属", "team"

    def lookups(self, request, model_admin):
        c = own(request)
        out = [("mine", "我的客户"), ("down", "我介绍的人的客户")]
        if c: out += [(str(p.pk), f"{p.name_zh}（{p.code}）") for p in Consultant.objects.filter(pk__in=c.downline_ids())]
        return out

    def queryset(self, request, qs):
        c, v = own(request), self.value()
        if not c or not v: return qs
        if v == "mine": return qs.filter(consultant=c)
        if v == "down": return qs.exclude(consultant=c)
        return qs.filter(consultant_id=v) if v.isdigit() and int(v) in c.downline_ids() else qs


@admin.register(Referral)
class LeadAdmin(admin.ModelAdmin):
    form = LeadForm
    list_display = ("reg_date", "student_name", "gender", "phone", "coop", "consultant", "status", "next_col", "protection")
    list_display_links = ("reg_date", "student_name")
    list_filter = ("status", DueFilter, "coop_type", "consultant", ProtectionFilter, "source")
    search_fields = ("student_name", "parent_name", "phone", "wechat", "email", "coop_name", "notes")
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, **kw):
        Form = super().get_form(request, obj, **kw)

        class F(Form):
            def __init__(s, *a, **k): super().__init__(*a, request=request, **k)
        return F

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("consultant")
        if request.user.is_superuser: return qs
        c = own(request)
        return qs.filter(consultant_id__in=c.team_ids()).exclude(status="released") if c else qs.none()

    def get_list_display(self, request):
        if request.user.is_superuser: return self.list_display
        c = own(request)
        if c and c.downline_ids(): return self.list_display  # 报备顾问 column shows whose client it is
        return tuple(x for x in self.list_display if x != "consultant")

    def get_list_filter(self, request):
        if request.user.is_superuser: return self.list_filter
        c = own(request)
        return ((TeamFilter,) if c and c.downline_ids() else ()) + ("status", DueFilter, "coop_type", ProtectionFilter)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            c = own(request)
            if not c or obj.consultant_id != c.pk: return False  # clients of people they introduced: view only
        return super().has_change_permission(request, obj)

    def get_fieldsets(self, request, obj=None):
        fs = [("服务对象（学生）", {"fields": ("student_name", "gender", "id_last4", "grade", "school")}),
              ("客户（家长）", {"fields": ("parent_name", "phone", "wechat", "email", "interest")}),
              ("来源", {"fields": ("coop_type", "coop_name")}),
              ("跟进", {"fields": ("status", "next_date", "notes")}),
              ("成交", {"fields": ("signed_date", "product", "amount", "currency")})]
        if obj and obj.enquiry_ids.strip(","): fs.insert(0, ("官网查询内容", {"fields": ("details",)}))
        info = ["protection", "created_at", "last_activity"] + (["source", "code"] if request.user.is_superuser else [])
        if request.user.is_superuser: fs.insert(0, ("报备顾问", {"fields": ("consultant",)}))
        if obj: fs.append(("报备资料", {"fields": info}))
        if obj: fs.append(("修改记录", {"fields": ("history",), "description": "系统自动记录，任何人都无法修改。"}))
        return fs

    def get_readonly_fields(self, request, obj=None):
        return ("details", "protection", "created_at", "last_activity", "source", "code", "history")

    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    def get_changeform_initial_data(self, request):
        d = super().get_changeform_initial_data(request)
        if request.user.is_superuser and "consultant" not in d:
            c = Consultant.objects.filter(user=request.user, active=True).first()
            if c: d["consultant"] = c.pk
        return d

    def save_model(self, request, obj, form, change):
        if not change:
            if not request.user.is_superuser: obj.consultant = own(request)
            obj.source = "manual"
        reassigned = request.user.is_superuser and "consultant" in form.changed_data and obj.consultant_id
        if not change or FOLLOW_FIELDS & set(form.changed_data) or "consultant" in form.changed_data:
            obj.last_activity = timezone.now()
        for m in getattr(form, "claims", []):  # an unassigned website enquiry of the same student: merge it in
            for pk in m.enquiry_list(): obj.add_enquiry(pk)
            if m.notes and m.notes not in obj.notes: obj.notes = (obj.notes + "\n" + m.notes).strip()
        super().save_model(request, obj, form, change)
        for m in getattr(form, "claims", []): m.delete()
        by = obj.consultant.name_zh if obj.consultant else "公司"
        for m in getattr(form, "releases", []): L.release(m, by)
        if not change: N.new_referral(obj, by_company=request.user.is_superuser and not (obj.consultant and obj.consultant.user_id == request.user.pk))
        elif reassigned: N.assigned(obj)
        sib = L.siblings(obj.phone, obj.student_name, exclude_pk=obj.pk)
        if sib and not change:
            messages.info(request, "提示：同一电话已报备了其他服务对象（例如兄弟姊妹）：" + "、".join(s.student_name or "—" for s in sib[:5]))
        E = enquiry_model()
        if E and hasattr(E, "followed_up") and obj.enquiry_list():
            E._base_manager.filter(pk__in=obj.enquiry_list()).update(followed_up=obj.status not in ("new",))

    @admin.display(description="下次跟进日期", ordering="next_date")
    def next_col(self, obj):
        if not obj.next_date: return "—"
        late = (timezone.localdate() - obj.next_date).days
        if obj.status in ("signed", "closed", "released") or late < 0: return f"{obj.next_date:%Y-%m-%d}"
        if late == 0: return format_html('<b style="color:#b26a00">{}（今天）</b>', f"{obj.next_date:%Y-%m-%d}")
        return format_html('<b style="color:#c62828">{}（逾期 {} 天）</b>', f"{obj.next_date:%Y-%m-%d}", late)

    @admin.display(description="报备时间", ordering="created_at")
    def reg_date(self, obj): return timezone.localtime(obj.created_at).strftime("%Y-%m-%d")

    @admin.display(description="合作方式", ordering="coop_type")
    def coop(self, obj):
        return obj.get_coop_type_display() + (f"：{obj.coop_name}" if obj.coop_name else "")

    @admin.display(description="保护状态")
    def protection(self, obj):
        if not obj.pk: return "保存后开始计算"
        if not obj.consultant_id: return "未分派"
        u = obj.protected_until()
        if u == "permanent": return "永久（已签约）"
        if u and u >= timezone.localdate(): return f"保护至 {u:%Y-%m-%d}"
        return "已过期"

    @admin.display(description="修改记录")
    def history(self, obj):
        logs = list(obj.logs.all()) if obj.pk else []
        return render_logs(logs) if logs else "—"

    @admin.display(description="官网查询内容")
    def details(self, obj):
        E = enquiry_model()
        if not E or not obj.enquiry_list(): return "—"
        parts = []
        for e in E._base_manager.filter(pk__in=obj.enquiry_list()).order_by("pk"):
            rows = []
            for f, label in ENQ_FIELDS:
                if not hasattr(e, f): continue
                v = getattr(e, f"get_{f}_display")() if hasattr(e, f"get_{f}_display") else (getattr(e, f) or "")
                rows.append((label, timezone.localtime(v).strftime("%Y-%m-%d %H:%M") if hasattr(v, "astimezone") else v))
            parts.append(format_html('<p style="margin:8px 0 4px;font-weight:700">查询 #{}</p><table style="border-collapse:collapse">{}</table>', e.pk,
                format_html_join("", '<tr><th style="text-align:left;padding:3px 16px 3px 0;white-space:nowrap;vertical-align:top">{}</th>'
                                     '<td style="padding:3px 0;white-space:pre-wrap">{}</td></tr>', rows)))
        return format_html_join("", "{}", ((p,) for p in parts)) if parts else "—"


# ================================================================ change history (修改记录)
CELL = "padding:4px 12px 4px 0;vertical-align:top;border-bottom:1px solid var(--hairline-color,#eee)"


def render_changes(changes):
    return format_html_join("", '<div><b>{}</b>：{} → {}</div>',
                            ((f, o or "（空白）", n or "（空白）") for f, o, n in (changes or []))) or "—"


def render_logs(logs):
    rows = format_html_join("", '<tr><td style="' + CELL + ';white-space:nowrap">{}</td><td style="' + CELL + ';white-space:nowrap">{}</td>'
                                '<td style="' + CELL + ';white-space:nowrap">{}</td><td style="' + CELL + ';white-space:pre-wrap">{}</td></tr>',
                            ((timezone.localtime(x.at).strftime("%Y-%m-%d %H:%M"), x.actor or "—", x.get_action_display(), render_changes(x.changes))
                             for x in logs))
    return format_html('<table style="border-collapse:collapse;width:100%"><thead><tr><th style="text-align:left">时间</th><th style="text-align:left">操作者</th>'
                       '<th style="text-align:left">动作</th><th style="text-align:left">改动</th></tr></thead><tbody>{}</tbody></table>', rows)


@admin.register(ReferralLog)
class ReferralLogAdmin(admin.ModelAdmin):
    """Company admins only: every change of every 客户报备, including deleted ones. Read-only for everybody."""
    list_display = ("when", "label", "actor", "action", "summary", "open_referral")
    list_filter = ("action", "actor")
    search_fields = ("label", "actor", "referral_pk")
    date_hierarchy = "at"
    fields = ("when", "label", "referral_pk", "open_referral", "actor", "user", "action", "detail")
    readonly_fields = fields

    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description="时间", ordering="at")
    def when(self, obj): return timezone.localtime(obj.at).strftime("%Y-%m-%d %H:%M:%S")

    @admin.display(description="改动")
    def summary(self, obj):
        ch = obj.changes or []
        t = "、".join(c[0] for c in ch[:4]) + ("…" if len(ch) > 4 else "")
        return t or "—"

    @admin.display(description="改动内容")
    def detail(self, obj): return render_changes(obj.changes)

    @admin.display(description="客户报备")
    def open_referral(self, obj):
        if not obj.referral_id: return "（已删除）" if obj.referral_pk else "—"
        from django.urls import reverse
        return format_html('<a href="{}">打开</a>', reverse("admin:consultants_referral_change", args=[obj.referral_id]))


# ================================================================ results summary (业绩总览)
PERIODS = [("month", "本月"), ("quarter", "今季"), ("year", "今年"), ("all", "全部")]


def period_start(p):
    t = timezone.localdate()
    if p == "month": return t.replace(day=1)
    if p == "quarter": return t.replace(month=(t.month - 1) // 3 * 3 + 1, day=1)
    if p == "year": return t.replace(month=1, day=1)
    return None


def summarise(rows):
    """Counts per status, deals and amounts for a list of leads."""
    today = timezone.localdate()
    s = {"total": len(rows), "by": {k: 0 for k, _ in Referral._meta.get_field("status").choices}, "protected": 0, "due": 0, "amounts": {}}
    for r in rows:
        s["by"][r.status] = s["by"].get(r.status, 0) + 1
        if r.is_protected(today): s["protected"] += 1
        if r.next_date and r.next_date <= today and r.status not in ("signed", "closed", "released"): s["due"] += 1
        if r.status == "signed" and r.amount: s["amounts"][r.currency] = s["amounts"].get(r.currency, 0) + r.amount
    active = s["total"] - s["by"].get("released", 0)
    s["signed"] = s["by"].get("signed", 0)
    s["rate"] = f"{s['signed'] * 100 / active:.0f}%" if active else "—"
    s["amount_text"] = "、".join(f"{c} {v:,.0f}" for c, v in sorted(s["amounts"].items())) or "—"
    return s


@admin.register(LeadReport)
class LeadReportAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def changelist_view(self, request, extra_context=None):
        p = request.GET.get("p") if request.GET.get("p") in dict(PERIODS) else "year"
        qs = Referral.objects.select_related("consultant")
        start = period_start(p)
        if start: qs = qs.filter(created_at__date__gte=start)
        c = own(request)
        if not request.user.is_superuser: qs = qs.filter(consultant_id__in=c.team_ids()) if c else qs.none()
        rows = list(qs)
        statuses = [(k, v) for k, v in Referral._meta.get_field("status").choices if k != "released"]

        def group(key, label):
            g = {}
            for r in rows: g.setdefault(key(r), []).append(r)
            return sorted(((label(k), summarise(v)) for k, v in g.items()), key=lambda x: -x[1]["total"])
        coop_label = dict(Referral._meta.get_field("coop_type").choices)
        ctx = {**self.admin_site.each_context(request), "title": "业绩总览", "opts": self.model._meta,
               "periods": PERIODS, "p": p, "statuses": statuses, "total": summarise(rows),
               "by_consultant": group(lambda r: r.consultant, lambda k: f"{k.name_zh}（{k.code}）" if k else "未分派"),
               "by_coop": group(lambda r: r.coop_type, lambda k: coop_label.get(k, k)),
               "by_partner": [x for x in group(lambda r: (r.coop_type, r.coop_name.strip()), lambda k: f"{coop_label.get(k[0], k[0])}：{k[1]}") if not x[0].endswith("：")][:30],
               "is_boss": request.user.is_superuser or bool(c and c.downline_ids()), "protect_days": PROTECT_DAYS}
        if request.GET.get("export") == "xlsx":
            from .export import report_xlsx
            return report_xlsx(request, ctx, rows, dict(PERIODS)[p], c)
        return TemplateResponse(request, "admin/consultants/report.html", ctx)


# ================================================================ 请示与反馈 (consultant -> 推荐人 / company)
def me_of(request):
    """The consultant record of the logged-in user, also for an admin who is a consultant."""
    return Consultant.objects.filter(user=request.user).first() if request.user.is_authenticated else None


class MessageForm(forms.ModelForm):
    send_to = forms.ChoiceField(label="发给", choices=[("company", "公司")])

    class Meta:
        model = Message
        fields = ("kind", "referral", "subject", "content")

    def __init__(self, *a, request=None, **k):
        super().__init__(*a, **k)
        me = me_of(request) if request else None
        if self.instance.pk: self.fields.pop("send_to", None)  # already sent: the addressee does not change
        if "send_to" in self.fields:
            ch = [("company", "公司")]
            if me and me.parent_id and me.parent.active: ch.insert(0, (str(me.parent_id), f"我的推荐人：{me.parent.name_zh}（{me.parent.code}）"))
            self.fields["send_to"].choices = ch
        if "referral" in self.fields:
            self.fields["referral"].queryset = (Referral.objects.filter(consultant=me).exclude(status="released") if me and not request.user.is_superuser
                                                else Referral.objects.all())


class InboxFilter(admin.SimpleListFilter):
    title, parameter_name = "范围", "box"

    def lookups(self, request, model_admin): return (("in", "发给我的"), ("out", "我提交的"))

    def queryset(self, request, qs):
        me = me_of(request)
        if self.value() == "in": return qs.filter(to_consultant=me) if me else qs.filter(to_consultant__isnull=True)
        if self.value() == "out": return qs.filter(sender=me) if me else qs.none()
        return qs


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("when", "sender", "to_col", "kind", "subject", "status_col", "replied_at")
    list_display_links = ("when", "subject")
    list_filter = (InboxFilter, "status", "kind")
    search_fields = ("subject", "content", "reply", "sender__name_zh")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("sender", "to_consultant", "referral")
        if request.user.is_superuser: return qs
        me = me_of(request)
        from django.db.models import Q
        return qs.filter(Q(sender=me) | Q(to_consultant=me)) if me else qs.none()

    def has_add_permission(self, request): return bool(me_of(request)) and super().has_add_permission(request)
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser:
            me = me_of(request)
            if not me: return False
            if obj.to_consultant_id == me.pk: return super().has_change_permission(request, obj)  # the 推荐人 replies
            if obj.sender_id == me.pk and obj.status == "open" and not obj.reply: return super().has_change_permission(request, obj)  # still editable
            return False
        return super().has_change_permission(request, obj)

    def _role(self, request, obj):
        """'new', 'sender' (may still edit), 'answer' (推荐人 or company replies) or 'view'."""
        if obj is None: return "new"
        me = me_of(request)
        if request.user.is_superuser or (me and obj.to_consultant_id == me.pk): return "answer"
        if me and obj.sender_id == me.pk and obj.status == "open" and not obj.reply: return "sender"
        return "view"

    def get_form(self, request, obj=None, **kw):
        role = self._role(request, obj)
        if role in ("new", "sender"):
            kw["form"] = MessageForm
            if role == "sender": kw["fields"] = ("kind", "referral", "subject", "content")
        else:
            kw["form"] = forms.ModelForm
            kw["fields"] = ("status", "reply") if role == "answer" else ()
        Form = super().get_form(request, obj, **kw)
        if role not in ("new", "sender"): return Form

        class F(Form):
            def __init__(s, *a, **k): super().__init__(*a, request=request, **k)
        return F

    def get_fieldsets(self, request, obj=None):
        role = self._role(request, obj)
        if role == "new":
            return ((None, {"fields": ("send_to", "kind", "referral", "subject", "content"),
                            "description": "遇到问题、需要支持或要向上级汇报，都可以在这里提交。对方回复后会通知你。"}),)
        ask = ("kind", "referral", "subject", "content") if role == "sender" else ("kind", "lead_col", "subject", "content_col")
        return (("请示内容", {"fields": ("sender", "to_col", "when") + ask}),
                ("回复", {"fields": ("status", "reply", "replied_by", "replied_at") if role == "answer" else ("status_col", "reply_col", "replied_by", "replied_at")}))

    def get_readonly_fields(self, request, obj=None):
        if obj is None: return ()
        base = ("sender", "to_col", "when", "replied_by", "replied_at", "lead_col", "content_col", "status_col", "reply_col")
        return base + (() if self._role(request, obj) == "sender" else ("kind", "subject"))

    def save_model(self, request, obj, form, change):
        if not change:
            me = me_of(request)
            obj.sender = me
            st = form.cleaned_data.get("send_to")
            obj.to_consultant = Consultant.objects.filter(pk=st).first() if st and st.isdigit() and me and str(me.parent_id) == st else None
        replied = change and "reply" in form.changed_data and obj.reply.strip()
        if replied:
            me = me_of(request)
            obj.replied_by = me.name_zh if me else (request.user.get_full_name() or request.user.get_username() or "公司")
            obj.replied_at = timezone.now()
            if obj.status == "open": obj.status = "done"
        super().save_model(request, obj, form, change)
        if not change: N.new_message(obj)
        elif replied: N.message_replied(obj)

    @admin.display(description="提交时间", ordering="created_at")
    def when(self, obj): return timezone.localtime(obj.created_at).strftime("%Y-%m-%d %H:%M") if obj.pk else "—"

    @admin.display(description="发给")
    def to_col(self, obj): return obj.to_label()

    @admin.display(description="处理状态", ordering="status")
    def status_col(self, obj):
        color = {"open": "#c62828", "doing": "#b26a00", "done": "#2e7d32"}.get(obj.status, "inherit")
        return format_html('<b style="color:{}">{}</b>', color, obj.get_status_display())

    @admin.display(description="相关客户")
    def lead_col(self, obj): return obj.referral.student_name if obj.referral else "—"

    @admin.display(description="内容")
    def content_col(self, obj): return format_html('<div style="white-space:pre-wrap">{}</div>', obj.content)

    @admin.display(description="回复")
    def reply_col(self, obj): return format_html('<div style="white-space:pre-wrap">{}</div>', obj.reply) if obj.reply else "（尚未回复）"


# ================================================================ 推荐新顾问 (a consultant proposes; the company approves)
class ApplicationForm(forms.ModelForm):
    decision = forms.ChoiceField(label="审批", required=False, choices=[("", "暂不处理"), ("approve", "批准并开通账号"), ("reject", "拒绝")],
                                 help_text="批准：系统自动开通“推荐渠道”顾问账号，推荐人 = 申请人，并把登录资料通知申请人。")

    class Meta:
        model = Application
        fields = ("referral", "name_zh", "phone", "wechat_id", "email", "note", "reject_reason")

    def __init__(self, *a, request=None, **k):
        super().__init__(*a, **k)
        for f in ("name_zh", "phone"):
            if f in self.fields: self.fields[f].required = False  # may come from the chosen client
        if "referral" in self.fields:
            me = me_of(request) if request else None
            qs = Referral.objects.exclude(status="released")
            self.fields["referral"].queryset = qs if request and request.user.is_superuser else qs.filter(consultant=me) if me else qs.none()
            self.fields["referral"].label_from_instance = lambda r: (f"{r.parent_name or r.student_name}"
                + (f"（学生：{r.student_name}）" if r.parent_name and r.student_name else "") + (f" · {r.phone}" if r.phone else ""))

    def clean(self):
        d = super().clean()
        r = d.get("referral")
        if r:  # fill what was left blank from the chosen client (the parent is the one who becomes a 推荐渠道)
            for f, v in (("name_zh", r.parent_name or r.student_name), ("phone", r.phone), ("wechat_id", r.wechat), ("email", r.email)):
                if not d.get(f) and v: d[f] = self.cleaned_data[f] = v
        for f, label in (("name_zh", "姓名"), ("phone", "电话")):
            if not d.get(f): self.add_error(f, f"请填写{label}，或在上面选择一位客户。")
        if d.get("decision") == "approve":
            ph = "".join(ch for ch in (d.get("phone") or "") if ch.isdigit())[-8:]
            if ph:
                for c in Consultant.objects.exclude(phone=""):
                    if "".join(ch for ch in c.phone if ch.isdigit())[-8:] == ph:
                        raise forms.ValidationError(f"电话与现有顾问 {c.name_zh}（{c.code}）相同，请确认是否重复申请。")
        return d


class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("when", "applicant", "name_zh", "phone", "wechat_id", "status_col", "new_col")
    list_display_links = ("when", "name_zh")
    list_filter = ("status",)
    search_fields = ("name_zh", "phone", "wechat_id", "applicant__name_zh")
    actions = ["approve_selected", "reject_selected"]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("applicant", "consultant", "consultant__user")
        if request.user.is_superuser: return qs
        me = me_of(request)
        return qs.filter(applicant=me) if me else qs.none()

    def get_actions(self, request):
        return super().get_actions(request) if request.user.is_superuser else {}

    def has_add_permission(self, request): return bool(me_of(request)) and super().has_add_permission(request)
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.status != "pending": return False  # handled: read-only for everybody
        return super().has_change_permission(request, obj)

    def get_form(self, request, obj=None, **kw):
        kw["form"] = ApplicationForm
        if not request.user.is_superuser: kw["fields"] = ("referral", "name_zh", "phone", "wechat_id", "email", "note")
        Form = super().get_form(request, obj, **kw)

        class F(Form):
            def __init__(s, *a, **k): super().__init__(*a, request=request, **k)
        return F

    def get_fieldsets(self, request, obj=None):
        who = ("推荐的人", {"fields": ("referral", "name_zh", "phone", "wechat_id", "email", "note"),
                           "description": "批准后，此人会成为你名下的“推荐渠道”顾问：你可以查看其客户（只读）。" if not request.user.is_superuser else ""})
        if obj is None: return (who,)
        info = ("申请资料", {"fields": ("applicant", "when", "status_col")})
        if obj.status == "pending":
            return (info, who) + ((("审批", {"fields": ("decision", "reject_reason")}),) if request.user.is_superuser else ())
        res = ("审批结果", {"fields": ("decided_by", "decided_at", "account") if obj.status == "approved" else ("decided_by", "decided_at", "reject_reason")})
        return (info, who, res)

    def get_readonly_fields(self, request, obj=None):
        return ("applicant", "when", "status_col", "decided_by", "decided_at", "account") + (("reject_reason",) if obj and obj.status != "pending" else ())

    def save_model(self, request, obj, form, change):
        from . import applications as AP
        if not change: obj.applicant = me_of(request)
        super().save_model(request, obj, form, change)
        if not change: N.new_application(obj)
        d = form.cleaned_data.get("decision") if request.user.is_superuser else ""
        by = (me_of(request).name_zh if me_of(request) else "") or request.user.get_full_name() or request.user.get_username()
        if d == "approve":
            c = AP.approve(obj, by)
            if c: messages.success(request, f"已批准：{c.name_zh}（{c.code}），登录名称 {c.user.get_username()}，初始密码 {obj.temp_password}。登录资料已通知申请人。")
        elif d == "reject":
            AP.reject(obj, by, obj.reject_reason)
            messages.info(request, "已拒绝，并已通知申请人。")

    @admin.action(description="批准所选申请（开通账号）")
    def approve_selected(self, request, queryset):
        from . import applications as AP
        by = request.user.get_full_name() or request.user.get_username()
        done = [c for a in queryset if (c := AP.approve(a, by))]
        self.message_user(request, f"已批准 {len(done)} 个申请：" + "、".join(f"{c.name_zh}（{c.code}）" for c in done) if done else "所选申请都已处理过。")

    @admin.action(description="拒绝所选申请")
    def reject_selected(self, request, queryset):
        from . import applications as AP
        by = request.user.get_full_name() or request.user.get_username()
        n = sum(1 for a in queryset if AP.reject(a, by))
        self.message_user(request, f"已拒绝 {n} 个申请，并已通知申请人。")

    @admin.display(description="申请时间", ordering="created_at")
    def when(self, obj): return timezone.localtime(obj.created_at).strftime("%Y-%m-%d %H:%M") if obj.pk else "—"

    @admin.display(description="审批状态", ordering="status")
    def status_col(self, obj):
        color = {"pending": "#b26a00", "approved": "#2e7d32", "rejected": "#c62828"}.get(obj.status, "inherit")
        return format_html('<b style="color:{}">{}</b>', color, obj.get_status_display())

    @admin.display(description="开通的顾问")
    def new_col(self, obj): return f"{obj.consultant.name_zh}（{obj.consultant.code}）" if obj.consultant else "—"

    @admin.display(description="账号资料（请私下转交新顾问）")
    def account(self, obj):
        c = obj.consultant
        if not c: return "—"
        pw = obj.temp_password or "（新顾问已自行修改密码）"
        return format_html("<div>顾问：{}（{}）</div><div>后台网址：{}/admin/</div><div>登录名称：<b>{}</b></div><div>初始密码：<b>{}</b></div>"
                           "<div>专属链接：{}/s/{}</div><div style='color:#667'>首次登录后系统会要求修改密码。</div>",
                           c.name_zh, c.code, SITE, c.user.get_username() if c.user_id else "—", pw, SITE, c.code)


admin.site.register(Application, ApplicationAdmin)


# ================================================================ 关系图 (company only)
@admin.register(TeamTree)
class TeamTreeAdmin(admin.ModelAdmin):
    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def changelist_view(self, request, extra_context=None):
        from django.core.exceptions import PermissionDenied
        if not request.user.is_superuser: raise PermissionDenied
        from .tree import build
        tree, totals = build()
        ctx = {**self.admin_site.each_context(request), "title": "关系图", "opts": self.model._meta, "tree": tree, "totals": totals}
        return TemplateResponse(request, "admin/consultants/tree.html", ctx)


# ================================================================ login security
@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Company only: every admin login try, and 解锁 for a consultant who typed the wrong password too often."""
    list_display = ("at", "username", "kind", "ip", "agent")
    list_filter = ("kind", "at")
    search_fields = ("username", "ip")
    date_hierarchy = "at"
    actions = ["unlock"]

    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def get_actions(self, request):
        return super().get_actions(request) if request.user.is_superuser else {}

    @admin.action(description="解锁所选记录的登录名称和 IP（可立即重试）")
    def unlock(self, request, queryset):
        from .security import clear, record
        n = 0
        for username, ip in set(queryset.values_list("username", "ip")):
            n += clear(username=username) + clear(ip=ip)
            record(request, username, "unlock")
        self.message_user(request, f"已解锁（已清除 {n} 个错误记录）。")


@admin.register(TwoFactor)
class TwoFactorAdmin(admin.ModelAdmin):
    """A menu entry for every admin user: opens their own two-factor page."""
    def has_module_permission(self, request): return request.user.is_active and request.user.is_staff
    def has_view_permission(self, request, obj=None): return request.user.is_active and request.user.is_staff
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def changelist_view(self, request, extra_context=None):
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect("/admin/2fa/")


# ================================================================ menu: 顾问账户设置 for consultants
_site_get_app_list = admin.site.get_app_list


def _get_app_list(request, app_label=None):
    app_list = _site_get_app_list(request, app_label)
    if request.user.is_authenticated and not request.user.is_superuser:
        me = Consultant.objects.filter(user=request.user).first()
        for app in app_list:
            for m in app.get("models", []):
                if app.get("app_label") == "consultants" and m.get("object_name") == "Consultant":
                    m["name"] = ACCOUNT_TITLE
                    if me:
                        from django.urls import reverse
                        m["admin_url"] = reverse("admin:consultants_consultant_change", args=[me.pk])
    return app_list


admin.site.get_app_list = _get_app_list
