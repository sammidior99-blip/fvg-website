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
                n = notify.send([test], "【測試】summitbrilliance 通知設定成功",
                                [("結果", "郵件設定正常，之後新預約、新報備和每日跟進提醒都會寄出。"),
                                 ("公司收件人", ", ".join(notify.company()) or "（未設定 NOTIFY_EMAILS）")], sync=True, raise_errors=True)
            except Exception as e:
                raise CommandError(f"寄不出測試信：{e!r}\n請檢查 SMTP 主機、連接埠、帳號和密碼。")
            if not n: raise CommandError("寄不出測試信（伺服器沒有接受）。")
            self.stdout.write(f"OK test mail sent to {test}"); return
        n = notify.send_digest(dry_run=dry_run, stdout=self.stdout)
        self.stdout.write(f"reminders sent: {n}" + (" (dry run)" if dry_run else ""))
