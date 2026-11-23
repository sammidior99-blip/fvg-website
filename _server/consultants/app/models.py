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


STATUS = [("new", "新查詢"), ("contacted", "已聯絡"), ("meeting", "已安排會談"), ("proposal", "已提交方案"),
          ("signed", "已簽約"), ("closed", "暫不跟進")]


class Referral(models.Model):
    """A booking-form enquiry handled by a consultant (came through their link, or assigned by the company),
    with the consultant's follow-up progress. pages.Enquiry itself is left untouched."""
    enquiry_id = models.IntegerField("查詢編號", unique=True)
    consultant = models.ForeignKey(Consultant, verbose_name="負責顧問", null=True, on_delete=models.SET_NULL, related_name="referrals")
    code = models.CharField("連結代號", max_length=40, blank=True)
    source = models.CharField("來源", max_length=10, choices=[("link", "顧問連結"), ("assigned", "公司分派")], default="link")
    status = models.CharField("進度", max_length=10, choices=STATUS, default="new")
    next_date = models.DateField("下次跟進日期", null=True, blank=True)
    notes = models.TextField("跟進備註", blank=True, help_text="例如：已 WhatsApp 聯絡，家長想了解英國本科，約咗下星期三見面。")
    created_at = models.DateTimeField("時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "客戶跟進"
        ordering = ["-created_at"]

    def __str__(self):
        from django.apps import apps
        try:
            e = apps.get_model("pages", "Enquiry")._base_manager.filter(pk=self.enquiry_id).first()
        except LookupError:
            e = None
        name = (getattr(e, "parent_name", "") or getattr(e, "student_name", "")) if e else ""
        return f"{name or '客戶'}（查詢 #{self.enquiry_id}）"
