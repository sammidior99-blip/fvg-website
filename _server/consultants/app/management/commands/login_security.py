"""Emergency help for admin logins, run on the server:
  cd /home/ec2-user/mysite && sudo -u ec2-user venv/bin/python manage.py login_security status
  ... login_security unlock [LOGIN_NAME]     forget wrong passwords (all, or for one login name)
  ... login_security reset-2fa LOGIN_NAME    turn off authenticator codes for that login (e.g. lost phone)"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...models import LoginAttempt, TwoFactor
from ...security import clear


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["status", "unlock", "reset-2fa"])
        parser.add_argument("username", nargs="?")

    def handle(self, action, username=None, **kw):
        if action == "unlock":
            n = clear(username=username) if username else clear()
            if username:  # also free the IPs that user was typing from
                for ip in set(LoginAttempt.objects.filter(username=username.lower()).values_list("ip", flat=True)):
                    n += clear(ip=ip)
            self.stdout.write(f"unlocked: {n} wrong tries forgotten")
        elif action == "reset-2fa":
            if not username: raise CommandError("give the login name, e.g. login_security reset-2fa boss")
            u = get_user_model().objects.filter(username=username).first()
            if not u: raise CommandError(f"no login named {username}")
            n = TwoFactor.objects.filter(user=u).update(enabled=False, secret="", backup_codes="", enabled_at=None, required=False)
            self.stdout.write(f"two-factor turned off for {username}" if n else f"{username} had no two-factor")
        else:
            for tf in TwoFactor.objects.select_related("user").order_by("user__username"):
                self.stdout.write(f"{tf.user.username:20} 2fa={'on' if tf.enabled else 'off'}{' (required)' if tf.required else ''}")
            for a in LoginAttempt.objects.all()[:15]:
                self.stdout.write(f"{a.at:%Y-%m-%d %H:%M} {a.username:20} {a.kind:9} {a.ip}{' (cleared)' if a.cleared else ''}")
