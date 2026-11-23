from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator, FileExtensionValidator
from django.db import models

# Photos and WeChat QR codes live outside the code folder and are served by nginx at /consultant-media/
media = FileSystemStorage(location=getattr(settings, "CONSULTANT_MEDIA_ROOT", "/var/www/consultant-media"),
                          base_url="/consultant-media/")


def media_storage():
    # a callable, so the folder comes from settings and is not written into the migrations
    return media
IMAGE = [FileExtensionValidator(["jpg", "jpeg", "png", "webp"])]
LANGS = [("en", "English"), ("zh", "繁體中文"), ("cn", "简体中文")]


class Consultant(models.Model):
    code = models.CharField("連結代號", max_length=40, unique=True,
        validators=[RegexValidator(r"^[a-z0-9][a-z0-9-]*$", "只可用英文小寫、數字同 -，例如 amy 或 amy-chan")],
        help_text="專屬連結會係 summitbrilliance.com/s/<代號>，例如 amy。發出二維碼之後唔好再改。")
    name_zh = models.CharField("中文姓名", max_length=60)
    name_en = models.CharField("英文姓名", max_length=60, blank=True)
    title_zh = models.CharField("中文職稱", max_length=60, blank=True, help_text="例如：升學規劃顧問")
    title_en = models.CharField("英文職稱", max_length=60, blank=True, help_text="例如：Education Consultant")
    photo = models.FileField("相片", storage=media_storage, upload_to="photos/", blank=True, validators=IMAGE,
        help_text="正方形相片效果最好（jpg / png / webp，2MB 以內）")
    phone = models.CharField("電話", max_length=40, blank=True, help_text="連國家碼，例如 +852 9123 4567")
    whatsapp = models.CharField("WhatsApp 號碼", max_length=40, blank=True,
        help_text="連國家碼，例如 85291234567。留空就用上面嘅電話。")
    wechat_id = models.CharField("微信號", max_length=60, blank=True)
    wechat_qr = models.FileField("微信二維碼", storage=media_storage, upload_to="wechat/", blank=True, validators=IMAGE,
        help_text="喺微信「我 › 個人資料 › 我的二維碼」截圖上載")
    email = models.EmailField("電郵", blank=True)
    lang = models.CharField("連結打開嘅語言", max_length=2, choices=LANGS, default="zh")
    active = models.BooleanField("啟用", default=True, help_text="顧問離職就取消剔選。佢嘅連結會改為顯示下面「轉交給」嘅顧問，或者公司聯絡方式。")
    forward_to = models.ForeignKey("self", verbose_name="停用後轉交給", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", limit_choices_to={"active": True})
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="後台登入帳號", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="consultant")
    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後修改", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "銷售顧問"
        ordering = ["name_en", "name_zh"]

    def __str__(self):
        return f"{self.name_zh}{' / ' + self.name_en if self.name_en else ''} ({self.code})"

    def save(self, *a, **k):
        self.code = (self.code or "").strip().lower() or self.next_code()
        super().save(*a, **k)

    @staticmethod
    def next_code():
        """fv01, fv02, ...: one more than the highest number ever given out (numbers of departed consultants are never reused)."""
        nums = [int(c[2:]) for c in Consultant.objects.values_list("code", flat=True) if c[:2] == "fv" and c[2:].isdigit()]
        return f"fv{(max(nums) + 1) if nums else 1:02d}"

    def current(self, depth=0):
        """The consultant who should be shown for this link (follows 停用後轉交給)."""
        if self.active: return self
        if self.forward_to_id and depth < 5: return self.forward_to.current(depth + 1)
        return None

    def wa_number(self):
        return "".join(ch for ch in (self.whatsapp or self.phone) if ch.isdigit())


STATUS = [("new", "新報備"), ("contacted", "已聯絡"), ("meeting", "已安排會談"), ("proposal", "已提交方案"),
          ("signed", "已簽約"), ("closed", "暫不跟進"), ("released", "已釋放（由他人重新報備）")]
COOP = [("direct", "官網／直接客戶"), ("channel", "渠道合作"), ("push", "客戶推進"), ("referral", "客戶推薦"), ("branch", "分公司")]
SOURCE = [("website", "官網表格"), ("manual", "顧問錄入"), ("link", "顧問連結"), ("assigned", "公司分派")]
GENDER = [("M", "男"), ("F", "女")]
PRODUCTS = [("ug", "本科升學全案"), ("pg", "研究生升學全案"), ("hs", "海外高中入學全案"), ("dual", "國內美高升學全案"),
            ("camp", "名校研學營"), ("research", "世界名校教授科研項目"), ("online", "線上美國高中"),
            ("growth", "國際化成長規劃"), ("identity", "身份與全球流動性"), ("other", "其他")]
CURRENCY = [("HKD", "港元 HKD"), ("CNY", "人民幣 CNY"), ("USD", "美元 USD")]
PROTECT_DAYS = getattr(settings, "LEAD_PROTECT_DAYS", 90)


class Referral(models.Model):
    """One registered 服務對象 (the student being served) and the consultant who registered it first.
    Entered automatically from the website booking form, or by a consultant. A parent can have several children:
    each child is its own record. pages.Enquiry itself is left untouched."""
    consultant = models.ForeignKey(Consultant, verbose_name="報備顧問", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals")
    # the student being served
    student_name = models.CharField("服務對象姓名", max_length=100, default="", blank=True)
    gender = models.CharField("性別", max_length=1, choices=GENDER, blank=True)
    id_last4 = models.CharField("身份證最後四位", max_length=4, blank=True, help_text="用嚟分辨同名同姓；可留空")
    grade = models.CharField("年級", max_length=50, blank=True)
    school = models.CharField("就讀學校", max_length=150, blank=True)
    # the client (usually a parent)
    parent_name = models.CharField("客戶／家長姓名", max_length=100, blank=True)
    phone = models.CharField("電話", max_length=40, blank=True, help_text="連國家碼，例如 +852 9123 4567")
    wechat = models.CharField("微信號", max_length=60, blank=True)
    email = models.EmailField("電郵", blank=True)
    interest = models.CharField("感興趣的服務", max_length=200, blank=True)
    # where the client came from
    coop_type = models.CharField("合作方式", max_length=10, choices=COOP, default="direct")
    coop_name = models.CharField("合作方名稱", max_length=150, blank=True, help_text="例如渠道公司名稱、分公司名稱、推薦人姓名")
    source = models.CharField("錄入方式", max_length=10, choices=SOURCE, default="website")
    code = models.CharField("連結代號", max_length=40, blank=True)
    enquiry_ids = models.CharField("官網查詢編號", max_length=200, blank=True, help_text="內部使用")
    # follow-up
    status = models.CharField("進度", max_length=10, choices=STATUS, default="new")
    next_date = models.DateField("下次跟進日期", null=True, blank=True)
    notes = models.TextField("跟進備註", blank=True, help_text="例如：已 WhatsApp 聯絡，家長想了解英國本科，約咗下星期三見面。")
    last_activity = models.DateTimeField("最後跟進", null=True, blank=True)
    # deal
    signed_date = models.DateField("簽約日期", null=True, blank=True)
    product = models.CharField("簽約產品", max_length=10, choices=PRODUCTS, blank=True)
    amount = models.DecimalField("合約金額", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("貨幣", max_length=3, choices=CURRENCY, default="HKD")
    created_at = models.DateTimeField("報備時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "客戶報備"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student_name or self.parent_name or '客戶'}（{self.parent_name or self.phone or '—'}）"

    def enquiry_list(self):
        return [int(x) for x in self.enquiry_ids.strip(",").split(",") if x.isdigit()]

    def add_enquiry(self, pk):
        if pk not in self.enquiry_list():
            self.enquiry_ids = "," + ",".join(str(x) for x in self.enquiry_list() + [pk]) + ","

    def protected_until(self):
        """Date until which nobody else can register this student; None = not protected."""
        from datetime import timedelta
        if not self.consultant_id or self.status in ("closed", "released"): return None
        if self.status == "signed": return "permanent"
        start = self.last_activity or self.created_at
        return (start + timedelta(days=PROTECT_DAYS)).date() if start else None

    def is_protected(self, today=None):
        from django.utils import timezone
        u = self.protected_until()
        return u == "permanent" or (u is not None and u >= (today or timezone.localdate()))


class LeadReport(Referral):
    class Meta:
        proxy = True
        verbose_name = verbose_name_plural = "業績總覽"


# ================================================================ login security
class LoginAttempt(models.Model):
    """One row per admin login try (and per two-factor code try): used to slow down password guessing,
    and kept as a 登入紀錄 the company can look through."""
    KINDS = [("ok", "登入成功"), ("fail", "密碼錯誤"), ("locked", "已鎖定，拒絕登入"),
             ("2fa_ok", "驗證碼正確"), ("2fa_fail", "驗證碼錯誤"), ("unlock", "公司解鎖")]
    at = models.DateTimeField("時間", auto_now_add=True, db_index=True)
    username = models.CharField("登入名稱", max_length=150, db_index=True)
    ip = models.CharField("IP", max_length=45, db_index=True)
    kind = models.CharField("結果", max_length=10, choices=KINDS)
    cleared = models.BooleanField("已解除", default=False, help_text="成功登入或公司解鎖之後，之前嘅錯誤唔再計數。")
    agent = models.CharField("瀏覽器", max_length=200, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "登入紀錄"
        ordering = ["-at"]

    def __str__(self):
        return f"{self.username} {self.get_kind_display()} {self.at:%Y-%m-%d %H:%M}"


class TwoFactor(models.Model):
    """Authenticator-app codes (Google / Microsoft Authenticator) for one admin login."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="後台帳號", on_delete=models.CASCADE,
                                related_name="two_factor")
    secret = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField("已開啟", default=False)
    required = models.BooleanField("必須開啟", default=False)
    backup_codes = models.TextField(blank=True)  # salted hashes, one per line; a used code is removed
    last_step = models.BigIntegerField(default=0)  # the last 30-second step accepted, so a code works only once
    enabled_at = models.DateTimeField("開啟時間", null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "雙重驗證"

    def __str__(self):
        return f"{self.user} ({'已開啟' if self.enabled else '未開啟'})"
