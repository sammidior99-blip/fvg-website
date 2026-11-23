from django.apps import AppConfig


class ConsultantsConfig(AppConfig):
    name = "consultants"
    verbose_name = "銷售顧問"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from django.db.models.signals import post_save
        from .middleware import current_request
        from .views import COOKIE, find

        def remember(sender, instance, created, **kw):
            """A new booking-form enquiry: note which consultant's link the visitor came through."""
            req = current_request()
            if not created or req is None: return
            code = req.COOKIES.get(COOKIE)
            c = find(code) if code else None
            if code:
                from .models import Referral
                Referral.objects.get_or_create(enquiry_id=instance.pk, defaults={"consultant": c, "code": code})

        try:
            from django.apps import apps
            post_save.connect(remember, sender=apps.get_model("pages", "Enquiry"), weak=False, dispatch_uid="consultant-referral")
        except LookupError:
            pass

        # Show the consultant as a column in the existing enquiry list in /admin
        try:
            from django.contrib import admin
            from django.apps import apps
            Enquiry = apps.get_model("pages", "Enquiry")
            ma = admin.site._registry.get(Enquiry)
            if ma and "consultant_col" not in [getattr(x, "__name__", x) for x in ma.list_display]:
                from .models import Referral

                def consultant_col(obj):
                    r = Referral.objects.filter(enquiry_id=obj.pk).select_related("consultant").first()
                    return (r.consultant.name_zh if r and r.consultant else (r.code if r else "—"))
                consultant_col.short_description = "推薦顧問"
                ma.list_display = tuple(ma.list_display) + (consultant_col,)
        except Exception:
            pass
