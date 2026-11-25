from django.apps import AppConfig


class ConsultantsConfig(AppConfig):
    name = "consultants"
    verbose_name = "销售顾问"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from django.apps import apps
        from django.db.models.signals import post_save
        from .middleware import current_request
        from .views import COOKIE, find
        from .history import connect as connect_history
        connect_history()  # 修改记录 for every change of a 客户报备
        from .zhs import convert_app
        convert_app("pages")  # 咨询查询 etc. of the original website app: Simplified Chinese labels in the 后台

        def remember(sender, instance, created, **kw):
            """A new website booking form: register the student automatically (and credit the consultant whose link was used)."""
            if not created: return
            req = current_request()
            code = req.COOKIES.get(COOKIE, "") if req is not None else ""
            from .leads import from_enquiry
            from .notify import new_enquiry
            try:
                c = find(code) if code else None
                new_enquiry(instance, from_enquiry(instance, c, code), c)
            except Exception:  # never let this break the customer's form
                import logging
                logging.getLogger(__name__).exception("lead registration failed for enquiry %s", instance.pk)

        try:
            post_save.connect(remember, sender=apps.get_model("pages", "Enquiry"), weak=False, dispatch_uid="consultant-referral")
        except LookupError:
            pass

        # login security: wrong-password limits + 登录记录 (see security.py)
        from django.contrib import admin
        from django.contrib.auth.signals import user_logged_in, user_login_failed
        from .security import LockoutLoginForm, on_logged_in, on_login_failed
        admin.site.login_form = LockoutLoginForm
        user_login_failed.connect(on_login_failed, weak=False, dispatch_uid="fvg-login-failed")
        user_logged_in.connect(on_logged_in, weak=False, dispatch_uid="fvg-logged-in")

        from django.db.models.signals import post_migrate
        post_migrate.connect(sync_group_permissions, sender=self, weak=False, dispatch_uid="fvg-group-perms")

        try:
            self._extend_enquiry_admin(apps.get_model("pages", "Enquiry"))
        except Exception:
            pass

    @staticmethod
    def _extend_enquiry_admin(Enquiry):
        """In the company's existing enquiry list: a 报备顾问 / 进度 column, and actions to assign the ticked
        enquiries (e.g. from visitors who came without a consultant's link) to a consultant."""
        from django.contrib import admin, messages
        from django.utils import timezone
        from .models import Consultant, Referral
        ma = admin.site._registry.get(Enquiry)
        if not ma or getattr(ma, "_consultants_extended", False): return
        ma._consultants_extended = True

        def lead_of(e):
            return Referral.objects.filter(enquiry_ids__contains=f",{e.pk},").select_related("consultant").first()

        def consultant_col(obj):
            r = lead_of(obj)
            if not r or not r.consultant: return "—（未分派）"
            return f"{r.consultant.name_zh} · {r.get_status_display()}"
        consultant_col.short_description = "报备顾问 / 进度"
        ma.list_display = tuple(ma.list_display) + (consultant_col,)

        original = ma.get_actions

        def get_actions(request):
            actions = original(request)
            if not request.user.is_superuser: return actions
            from .leads import from_enquiry, note
            from .notify import assigned
            for c in Consultant.objects.filter(active=True).order_by("code"):
                def assign(modeladmin, req, queryset, c=c):
                    for e in queryset:
                        r = lead_of(e) or from_enquiry(e)
                        if r.consultant_id != c.pk:
                            note(r, f"公司分派给 {c.name_zh}（{c.code}）。")
                            r.consultant, r.code, r.source, r.last_activity = c, c.code, "assigned", timezone.now()
                            r.save()
                            assigned(r)
                    modeladmin.message_user(req, f"已将 {queryset.count()} 个查询分派给 {c.name_zh}（{c.code}）。", messages.SUCCESS)
                name = f"assign_consultant_{c.pk}"
                actions[name] = (assign, name, f"分派给顾问：{c.name_zh}（{c.code}）".replace("%", "%%"))

            def unassign(modeladmin, req, queryset):
                n = 0
                for e in queryset:
                    r = lead_of(e)
                    if r and r.consultant_id:
                        note(r, "公司取消分派。")
                        r.consultant, r.source = None, "website"
                        r.save(); n += 1
                modeladmin.message_user(req, f"已取消 {n} 个查询的顾问分派。", messages.SUCCESS)
            actions["unassign_consultant"] = (unassign, "unassign_consultant", "取消顾问分派")
            return actions

        ma.get_actions = get_actions


def sync_group_permissions(**kw):
    """After migrate: the 销售顾问 group gets the permissions of new features too (e.g. 请示与反馈)."""
    try:
        from django.contrib.auth.models import Group, Permission
        from .admin import GROUP, GROUP_PERMS
        g = Group.objects.filter(name=GROUP).first()
        if g: g.permissions.set(Permission.objects.filter(content_type__app_label="consultants", codename__in=GROUP_PERMS))
    except Exception:
        import logging
        logging.getLogger(__name__).exception("could not update the consultant group's permissions")
