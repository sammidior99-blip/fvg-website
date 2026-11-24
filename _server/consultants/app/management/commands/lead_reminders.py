"""Daily follow-up e-mails (run by cron every morning, see install.sh).
  manage.py lead_reminders             send today's reminders
  manage.py lead_reminders --dry-run   only show who would get what
  manage.py lead_reminders --test you@example.com   send one test e-mail to check the mail settings"""
from django.core.management.base import BaseCommand, CommandError

from consultants import notify


class Command(BaseCommand):
    help = "E-mail consultants their overdue / due-today follow-ups and protection periods ending soon; e-mail the company a summary."

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--test", metavar="EMAIL")

    def handle(self, *a, dry_run=False, test=None, **k):
        if test:
            try:
                n = notify.send([test], "【测试】summitbrilliance 通知设置成功",
                                [("结果", "邮件设置正常，之后新预约、新报备和每日跟进提醒都会发送。"),
                                 ("公司收件人", ", ".join(notify.company()) or "（未设置 NOTIFY_EMAILS）")], sync=True, raise_errors=True)
            except Exception as e:
                raise CommandError(f"测试邮件发送失败：{e!r}\n请检查 SMTP 主机、端口、账号和密码。")
            if not n: raise CommandError("测试邮件发送失败（服务器未接受）。")
            self.stdout.write(f"OK test mail sent to {test}"); return
        n = notify.send_digest(dry_run=dry_run, stdout=self.stdout)
        self.stdout.write(f"reminders sent: {n}" + (" (dry run)" if dry_run else ""))
