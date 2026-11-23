#!/bin/bash
# Install (or update) the sales-consultant add-on in the Django app on this server.
# Backs everything up first; if any step fails it puts the backup back and restarts, so the site stays as it was.
# Run:  sudo bash /opt/fvg-site/_server/consultants/install.sh
set -u
M=/home/ec2-user/mysite
SRC=/opt/fvg-site/_server/consultants
PY=$M/venv/bin/python
BK=/home/ec2-user/backup-consultants-$(date +%Y%m%d-%H%M%S)
OWNER=$(stat -c %U "$M/db.sqlite3")
SVC=$(systemctl show -p User --value gunicorn.service); SVC=${SVC:-root}
CHECK="curl -sk --resolve summitbrilliance.com:443:127.0.0.1"

restore() {
  echo "!! FAILED at: $1"
  echo "!! putting the backup back..."
  cp -a "$BK/settings.py" "$M/mysite/settings.py"; cp -a "$BK/urls.py" "$M/mysite/urls.py"; cp -a "$BK/db.sqlite3" "$M/db.sqlite3"
  rm -rf "$M/consultants"; [ -d "$BK/consultants" ] && cp -a "$BK/consultants" "$M/consultants"
  systemctl restart gunicorn
  echo "!! RESTORED - the website is as it was before. Send a screenshot of this screen to Claude."
  exit 1
}

echo "1/7 backup to $BK"
mkdir -p "$BK" && cp -a "$M/db.sqlite3" "$M/mysite/settings.py" "$M/mysite/urls.py" "$BK/" || { echo "backup failed - nothing was changed"; exit 1; }
[ -d "$M/consultants" ] && cp -a "$M/consultants" "$BK/"

echo "2/7 QR-code library"
"$M/venv/bin/pip" install -q --disable-pip-version-check segno || restore "pip install segno"

echo "3/7 add-on code"
rm -rf "$M/consultants" && cp -r "$SRC/app" "$M/consultants" && chown -R "$OWNER": "$M/consultants" || restore "copy code"

echo "4/7 settings + urls"
python3 "$SRC/patch.py" "$M" && chown "$OWNER": "$M/mysite/settings.py" "$M/mysite/urls.py" || restore "patch settings"

echo "5/7 photo folder /var/www/consultant-media"
mkdir -p /var/www/consultant-media/photos /var/www/consultant-media/wechat && chown -R "$SVC": /var/www/consultant-media && chmod -R a+rX /var/www/consultant-media || restore "media folder"

echo "6/7 database"
cd "$M" && sudo -u "$OWNER" "$PY" manage.py migrate consultants --noinput || restore "migrate"
sudo -u "$OWNER" "$PY" manage.py check 2>&1 | tail -1

echo "7/7 restart + nginx"
systemctl restart gunicorn || restore "restart gunicorn"
sleep 4
API=$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: summitbrilliance.com' http://127.0.0.1:8000/api/consultant.json)
[ "$API" = "200" ] || restore "app check ($API)"
bash /opt/fvg-site/_server/fix-nginx.sh > /tmp/fvg-nginx.log 2>&1; grep -E "FIXED|RESTORED" /tmp/fvg-nginx.log

echo "== check"
echo "consultant api: $($CHECK https://summitbrilliance.com/api/consultant.json)   (should be {})"
echo "test link:      $($CHECK -o /dev/null -w '%{http_code}' https://summitbrilliance.com/s/nobody)   (should be 302)"
echo "home page:      $($CHECK -o /dev/null -w '%{http_code}' https://summitbrilliance.com/zh/)   (should be 200)"
echo "contact form:   $($CHECK -o /dev/null -w '%{http_code}' https://summitbrilliance.com/zh/contact.html)   (should be 200)"
echo "admin:          $($CHECK -o /dev/null -w '%{http_code}' https://summitbrilliance.com/admin/)   (should be 302)"
echo "ALL DONE - backup kept in $BK"
