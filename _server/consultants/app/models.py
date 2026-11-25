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
LANGS = [("en", "English"), ("zh", "繁体中文"), ("cn", "简体中文")]
KINDS = [("staff", "公司顾问"), ("channel", "推荐渠道")]


class Consultant(models.Model):
    code = models.CharField("链接代号", max_length=40, unique=True,
        validators=[RegexValidator(r"^[a-z0-9][a-z0-9-]*$", "只可用英文小写、数字和 -，例如 amy 或 amy-chan")],
        help_text="专属链接将为 summitbrilliance.com/s/<代号>，例如 amy。发出二维码之后请勿再修改。")
    name_zh = models.CharField("中文姓名", max_length=60)
    name_en = models.CharField("英文姓名", max_length=60, blank=True)
    title_zh = models.CharField("中文职称", max_length=60, blank=True, help_text="例如：升学规划顾问")
    title_en = models.CharField("英文职称", max_length=60, blank=True, help_text="例如：Education Consultant")
    photo = models.FileField("照片", storage=media_storage, upload_to="photos/", blank=True, validators=IMAGE,
        help_text="正方形照片效果最好（jpg / png / webp，2MB 以内）")
    phone = models.CharField("电话", max_length=40, blank=True, help_text="连国家码，例如 +852 9123 4567")
    whatsapp = models.CharField("WhatsApp 号码", max_length=40, blank=True,
        help_text="连国家码，例如 85291234567。留空则使用上面的电话。")
    wechat_id = models.CharField("微信号", max_length=60, blank=True)
    wechat_qr = models.FileField("微信二维码", storage=media_storage, upload_to="wechat/", blank=True, validators=IMAGE,
        help_text="在微信“我 › 个人资料 › 我的二维码”截图上传")
    email = models.EmailField("邮箱", blank=True)
    lang = models.CharField("链接打开的语言", max_length=2, choices=LANGS, default="zh")
    active = models.BooleanField("启用", default=True, help_text="顾问离职时取消勾选。其链接将改为显示下方“转交给”的顾问，或公司联系方式。")
    forward_to = models.ForeignKey("self", verbose_name="停用后转交给", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", limit_choices_to={"active": True})
    kind = models.CharField("类型", max_length=10, choices=KINDS, default="staff",
        help_text="推荐渠道 = 原本是客户、现在介绍朋友来的人（客户转介绍）。权限与公司顾问一样，只看到自己的客户。")
    parent = models.ForeignKey("self", verbose_name="推荐人（上级）", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recruits",
        help_text="由谁介绍加入。推荐人可以查看此人及其再介绍的人所报备的客户（只读，不能修改）；其他顾问看不到。")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="后台登录账号", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="consultant")
    created_at = models.DateTimeField("建立时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后修改", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "销售顾问"
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
        """The consultant who should be shown for this link (follows 停用后转交给)."""
        if self.active: return self
        if self.forward_to_id and depth < 5: return self.forward_to.current(depth + 1)
        return None

    def downline_ids(self, max_depth=10):
        """Everyone this person brought in, and everyone they brought in, and so on (not including this person)."""
        found, level = [], [self.pk]
        for _ in range(max_depth):
            level = [pk for pk in Consultant.objects.filter(parent_id__in=level).values_list("pk", flat=True) if pk not in found and pk != self.pk]
            if not level: break
            found += level
        return found

    def team_ids(self):
        """This person plus their whole downline: whose 客户报备 they may see."""
        return [self.pk] + self.downline_ids()

    def wa_number(self):
        return "".join(ch for ch in (self.whatsapp or self.phone) if ch.isdigit())


STATUS = [("new", "新报备"), ("contacted", "已联系"), ("meeting", "已安排会谈"), ("proposal", "已提交方案"),
          ("signed", "已签约"), ("closed", "暂不跟进"), ("released", "已释放（由他人重新报备）")]
COOP = [("direct", "官网／直接客户"), ("channel", "渠道合作"), ("push", "客户推进"), ("referral", "客户推荐"), ("branch", "分公司")]
SOURCE = [("website", "官网表格"), ("manual", "顾问录入"), ("link", "顾问链接"), ("assigned", "公司分派")]
GENDER = [("M", "男"), ("F", "女")]
PRODUCTS = [("ug", "本科升学全案"), ("pg", "研究生升学全案"), ("hs", "海外高中入学全案"), ("dual", "国内美高升学全案"),
            ("camp", "名校研学营"), ("research", "世界名校教授科研项目"), ("online", "线上美国高中"),
            ("growth", "国际化成长规划"), ("identity", "身份与全球流动性"), ("other", "其他")]
CURRENCY = [("HKD", "港币 HKD"), ("CNY", "人民币 CNY"), ("USD", "美元 USD")]
PROTECT_DAYS = getattr(settings, "LEAD_PROTECT_DAYS", 90)


class Referral(models.Model):
    """One registered 服务对象 (the student being served) and the consultant who registered it first.
    Entered automatically from the website booking form, or by a consultant. A parent can have several children:
    each child is its own record. pages.Enquiry itself is left untouched."""
    consultant = models.ForeignKey(Consultant, verbose_name="报备顾问", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals")
    # the student being served
    student_name = models.CharField("服务对象姓名", max_length=100, default="", blank=True)
    gender = models.CharField("性别", max_length=1, choices=GENDER, blank=True)
    id_last4 = models.CharField("身份证最后四位", max_length=4, blank=True, help_text="用于区分同名同姓；可留空")
    grade = models.CharField("年级", max_length=50, blank=True)
    school = models.CharField("就读学校", max_length=150, blank=True)
    # the client (usually a parent)
    parent_name = models.CharField("客户／家长姓名", max_length=100, blank=True)
    phone = models.CharField("电话", max_length=40, blank=True, help_text="连国家码，例如 +852 9123 4567")
    wechat = models.CharField("微信号", max_length=60, blank=True)
    email = models.EmailField("邮箱", blank=True)
    interest = models.CharField("感兴趣的服务", max_length=200, blank=True)
    # where the client came from
    coop_type = models.CharField("合作方式", max_length=10, choices=COOP, default="direct")
    coop_name = models.CharField("合作方名称", max_length=150, blank=True, help_text="例如渠道公司名称、分公司名称、推荐人姓名")
    source = models.CharField("录入方式", max_length=10, choices=SOURCE, default="website")
    code = models.CharField("链接代号", max_length=40, blank=True)
    enquiry_ids = models.CharField("官网查询编号", max_length=200, blank=True, help_text="内部使用")
    # follow-up
    status = models.CharField("进度", max_length=10, choices=STATUS, default="new")
    next_date = models.DateField("下次跟进日期", null=True, blank=True)
    notes = models.TextField("跟进备注", blank=True, help_text="例如：已 WhatsApp 联系，家长想了解英国本科，约了下周三见面。")
    last_activity = models.DateTimeField("最后跟进", null=True, blank=True)
    # deal
    signed_date = models.DateField("签约日期", null=True, blank=True)
    product = models.CharField("签约产品", max_length=10, choices=PRODUCTS, blank=True)
    amount = models.DecimalField("合约金额", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("货币", max_length=3, choices=CURRENCY, default="HKD")
    created_at = models.DateTimeField("报备时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后更新", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "客户报备"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student_name or self.parent_name or '客户'}（{self.parent_name or self.phone or '—'}）"

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
        verbose_name = verbose_name_plural = "业绩总览"


class ReferralLog(models.Model):
    """Change history of a 客户报备, written automatically on every save/delete (see history.py).
    Nobody can edit or delete it in the admin, so it can settle disputes about who registered whom and when."""
    ACTIONS = [("baseline", "起始状态"), ("create", "新增"), ("change", "修改"), ("delete", "删除")]
    referral = models.ForeignKey(Referral, verbose_name="客户报备", null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    referral_pk = models.IntegerField("报备编号", null=True, blank=True, db_index=True)
    label = models.CharField("服务对象", max_length=250, blank=True)
    at = models.DateTimeField("时间", auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="账号", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.CharField("操作者", max_length=150, blank=True)
    action = models.CharField("动作", max_length=10, choices=ACTIONS)
    changes = models.JSONField("改动", default=list, blank=True)  # [[field label, old, new], ...]

    class Meta:
        verbose_name = verbose_name_plural = "修改记录"
        ordering = ["-at", "-pk"]

    def __str__(self):
        return f"{self.label} · {self.get_action_display()}"


# ================================================================ login security
class LoginAttempt(models.Model):
    """One row per admin login try (and per two-factor code try): used to slow down password guessing,
    and kept as a 登录记录 the company can look through."""
    KINDS = [("ok", "登录成功"), ("fail", "密码错误"), ("locked", "已锁定，拒绝登录"),
             ("2fa_ok", "验证码正确"), ("2fa_fail", "验证码错误"), ("unlock", "公司解锁")]
    at = models.DateTimeField("时间", auto_now_add=True, db_index=True)
    username = models.CharField("登录名称", max_length=150, db_index=True)
    ip = models.CharField("IP", max_length=45, db_index=True)
    kind = models.CharField("结果", max_length=10, choices=KINDS)
    cleared = models.BooleanField("已解除", default=False, help_text="成功登录或公司解锁之后，之前的错误不再计数。")
    agent = models.CharField("浏览器", max_length=200, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "登录记录"
        ordering = ["-at"]

    def __str__(self):
        return f"{self.username} {self.get_kind_display()} {self.at:%Y-%m-%d %H:%M}"


class TwoFactor(models.Model):
    """Authenticator-app codes (Google / Microsoft Authenticator) for one admin login."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="后台账号", on_delete=models.CASCADE,
                                related_name="two_factor")
    secret = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField("已开启", default=False)
    required = models.BooleanField("必须开启", default=False)
    backup_codes = models.TextField(blank=True)  # salted hashes, one per line; a used code is removed
    last_step = models.BigIntegerField(default=0)  # the last 30-second step accepted, so a code works only once
    enabled_at = models.DateTimeField("开启时间", null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "双重验证"

    def __str__(self):
        return f"{self.user} ({'已开启' if self.enabled else '未开启'})"


MSG_KINDS = [("problem", "遇到问题"), ("support", "需要支持"), ("report", "工作汇报"), ("other", "其他")]
MSG_STATUS = [("open", "待处理"), ("doing", "处理中"), ("done", "已完成")]


class Message(models.Model):
    """请示与反馈: a consultant raises a problem or a request with their 推荐人（上级） or with the company, and gets a reply.
    (Not to be confused with 客户报备, which registers clients.)"""
    sender = models.ForeignKey(Consultant, verbose_name="提交人", null=True, on_delete=models.SET_NULL, related_name="sent_messages")
    to_consultant = models.ForeignKey(Consultant, verbose_name="发给", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="inbox", help_text="空白 = 公司")
    kind = models.CharField("类别", max_length=10, choices=MSG_KINDS, default="problem")
    referral = models.ForeignKey("Referral", verbose_name="相关客户", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                 help_text="可选：与哪位客户有关")
    subject = models.CharField("主题", max_length=120)
    content = models.TextField("内容")
    status = models.CharField("处理状态", max_length=10, choices=MSG_STATUS, default="open")
    reply = models.TextField("回复", blank=True)
    replied_by = models.CharField("回复人", max_length=80, blank=True)
    replied_at = models.DateTimeField("回复时间", null=True, blank=True)
    created_at = models.DateTimeField("提交时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后更新", auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "请示与反馈"
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject

    def to_label(self):
        return f"{self.to_consultant.name_zh}（推荐人）" if self.to_consultant_id else "公司"


APP_STATUS = [("pending", "待审批"), ("approved", "已批准"), ("rejected", "已拒绝")]


class Application(models.Model):
    """推荐新顾问: a consultant asks for one of their clients (or a friend) to become a 推荐渠道 under them.
    The company approves with one click: the account is created with 推荐人 = the applicant."""
    applicant = models.ForeignKey(Consultant, verbose_name="推荐人（申请人）", null=True, on_delete=models.SET_NULL, related_name="applications")
    referral = models.ForeignKey("Referral", verbose_name="从我的客户中选择", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                 help_text="可选：选择后，下面的姓名、电话、微信号、邮箱留空即可，系统会自动带入该客户（家长）的资料。")
    name_zh = models.CharField("姓名", max_length=60)
    phone = models.CharField("电话", max_length=40, help_text="连国家码，例如 +86 138 0000 0000")
    wechat_id = models.CharField("微信号", max_length=60, blank=True)
    email = models.EmailField("邮箱", blank=True, help_text="可选：新顾问收取客户通知用")
    note = models.TextField("推荐说明", blank=True, help_text="例如：原本是我的客户，愿意介绍朋友")
    status = models.CharField("审批状态", max_length=10, choices=APP_STATUS, default="pending")
    reject_reason = models.CharField("拒绝原因", max_length=200, blank=True)
    consultant = models.ForeignKey(Consultant, verbose_name="开通的顾问", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    temp_password = models.CharField("初始密码", max_length=40, blank=True)
    must_change = models.BooleanField("首次登录须修改密码", default=False)
    decided_by = models.CharField("审批人", max_length=80, blank=True)
    decided_at = models.DateTimeField("审批时间", null=True, blank=True)
    created_at = models.DateTimeField("申请时间", auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "推荐新顾问"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name_zh}（{self.get_status_display()}）"


class TeamTree(Consultant):
    """关系图: the company's tree of consultants → clients → people they introduced → their clients."""
    class Meta:
        proxy = True
        verbose_name = verbose_name_plural = "关系图"
