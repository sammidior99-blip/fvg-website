"""推荐新顾问: approve / reject an application. Approving creates the 推荐渠道 consultant + their login."""
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils import timezone

from .models import Consultant

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: easy to type from a message


def temp_password():
    return "Fv" + "".join(secrets.choice(ALPHABET) for _ in range(8))


def approve(app, by):
    """Returns the new consultant, or None when the application was already handled."""
    from .admin import GROUP, GROUP_PERMS
    from . import notify as N
    if app.status != "pending": return None
    with transaction.atomic():
        parent = app.applicant if app.applicant and app.applicant.active else None
        c = Consultant.objects.create(name_zh=app.name_zh, phone=app.phone, wechat_id=app.wechat_id, email=app.email,
                                      kind="channel", parent=parent, lang=parent.lang if parent else "cn")
        U = get_user_model()
        login = c.code
        while U.objects.filter(username=login).exists():
            login = f"{c.code}-{secrets.randbelow(900) + 100}"
        pw = temp_password()
        u = U.objects.create_user(username=login, password=pw, email=app.email or "")
        u.is_staff, u.first_name = True, app.name_zh
        u.save()
        g, _ = Group.objects.get_or_create(name=GROUP)
        g.permissions.set(Permission.objects.filter(content_type__app_label="consultants", codename__in=GROUP_PERMS))
        u.groups.add(g)
        c.user = u
        c.save(update_fields=["user"])
        app.status, app.consultant, app.temp_password, app.must_change = "approved", c, pw, True
        app.decided_by, app.decided_at = by, timezone.now()
        app.save()
    N.application_decided(app)
    return c


def reject(app, by, reason=""):
    from . import notify as N
    if app.status != "pending": return False
    app.status, app.reject_reason, app.decided_by, app.decided_at = "rejected", reason or app.reject_reason, by, timezone.now()
    app.save()
    N.application_decided(app)
    return True


def password_changed(user):
    """The new consultant set their own password: forget the initial one."""
    from .models import Application
    Application.objects.filter(consultant__user=user, must_change=True).update(must_change=False, temp_password="")


def must_change(user):
    from .models import Application
    return Application.objects.filter(consultant__user=user, must_change=True).exists()
