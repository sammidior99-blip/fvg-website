#!/bin/bash
# Turn on the e-mail alerts: asks for the company mailbox's SMTP details, saves them in /etc/fvg-mail.env
# (only root and the website program can read it - the password never goes to GitHub), restarts the site
# and sends a test e-mail.
# Run:  sudo bash /opt/fvg-site/_server/consultants/setup-mail.sh
# Typical SMTP settings:  Google Workspace  smtp.gmail.com 587     Microsoft 365  smtp.office365.com 587
#                         Zoho Mail          smtp.zoho.com 587       Tencent Exmail smtp.exmail.qq.com 465
# The password is usually an "app password" made in the mailbox's security settings, not the normal login password.
set -u
M=/home/ec2-user/mysite
F=/etc/fvg-mail.env
OWNER=$(stat -c %U "$M/db.sqlite3")
SVC=$(systemctl show -p User --value gunicorn.service); SVC=${SVC:-root}

perms() {
  [ -f "$F" ] || return 0
  chown root:"$(id -gn "$OWNER")" "$F" && chmod 640 "$F"
  if [ "$SVC" != root ] && ! id -nG "$SVC" | tr ' ' '\n' | grep -qx "$(id -gn "$OWNER")"; then
    setfacl -m "u:$SVC:r" "$F" 2>/dev/null || chmod 644 "$F"
  fi
}
[ "${1:-}" = "--permissions-only" ] && { perms; exit 0; }
[ "$(id -u)" = 0 ] || { echo "Please run with sudo"; exit 1; }

old() { [ -f "$F" ] && grep -m1 "^$1=" "$F" | cut -d= -f2- ; }
ask() { local d; d=$(old "$1"); read -r -p "$2${d:+ [$d]}: " v; echo "${v:-$d}"; }

echo "== summitbrilliance e-mail alerts =="
HOST=$(ask EMAIL_HOST "SMTP server (e.g. smtp.gmail.com)")
PORT=$(ask EMAIL_PORT "Port (587 or 465)"); PORT=${PORT:-587}
USER_=$(ask EMAIL_HOST_USER "Mailbox login (e.g. notice@summitbrilliance.com)")
read -r -s -p "Password / app password$( [ -n "$(old EMAIL_HOST_PASSWORD)" ] && echo ' [Enter = keep the saved one]'): " PW; echo
[ -z "$PW" ] && PW=$(old EMAIL_HOST_PASSWORD)
FROM=$(ask FROM_EMAIL "Sender shown on the e-mails, e.g. 中昊寰宇 <notice@summitbrilliance.com>"); FROM=${FROM:-$USER_}
TO=$(ask NOTIFY_EMAILS "Company addresses that get every alert (comma separated)")
[ -n "$HOST" ] && [ -n "$USER_" ] && [ -n "$PW" ] && [ -n "$TO" ] || { echo "Missing details - nothing saved."; exit 1; }

umask 077
{
  echo "# summitbrilliance e-mail alerts - written by setup-mail.sh on $(date '+%Y-%m-%d %H:%M'). Do not commit."
  printf 'EMAIL_HOST=%s\nEMAIL_PORT=%s\nEMAIL_HOST_USER=%s\nEMAIL_HOST_PASSWORD=%s\nFROM_EMAIL=%s\nNOTIFY_EMAILS=%s\n' \
    "$HOST" "$PORT" "$USER_" "$PW" "$FROM" "$TO"
} > "$F.new" && mv "$F.new" "$F"
perms
echo "saved $F"

systemctl restart gunicorn
FIRST=${TO%%,*}
echo "sending a test e-mail to $FIRST ..."
cd "$M" && sudo -u "$OWNER" "$M/venv/bin/python" manage.py lead_reminders --test "$FIRST" \
  && echo "DONE - check the inbox of $FIRST (and the spam folder). Alerts are now on." \
  || echo "!! The test e-mail failed - run this script again and check the server, port, login and password."
