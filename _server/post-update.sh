#!/bin/bash
# Runs on the EC2 server (as root) after each website update (called by /usr/local/bin/sync-site).
# 1. The daily news feed is no longer used by the new site: switch it off.
# 2. When the server programs in _server/ have changed (Django add-on or nginx settings), install them.
#    This happens once per change; install.sh backs up first and puts everything back if a step fails.
#    Log: /var/log/fvg-update.log
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SRV=/opt/fvg-site/_server
LOG=/var/log/fvg-update.log

rm -f /etc/cron.d/fvg-news /var/www/summit/news.json

exec 9>/run/fvg-update.lock
flock -n 9 || exit 0   # an install is still running from the previous sync

STAMP=/var/lib/fvg-server.sha
NEW=$(cd "$SRV" && find consultants nginx-site.conf fix-nginx.sh -type f -not -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)
[ "$NEW" = "$(cat $STAMP 2>/dev/null)" ] && exit 0

{
  echo "===== $(date '+%F %T') server programs changed - installing"
  if [ -d /home/ec2-user/mysite/consultants ]; then
    bash "$SRV/consultants/install.sh" && echo "RESULT: OK" || echo "RESULT: FAILED (restored to the previous version)"
  else
    bash "$SRV/fix-nginx.sh"
  fi
} >> "$LOG" 2>&1
mkdir -p /var/lib && echo "$NEW" > "$STAMP"   # recorded even after a failure, so a broken update is not retried every 5 minutes
exit 0
