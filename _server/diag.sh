#!/bin/bash
# Quick health check of the website server. Run:  sudo bash /opt/fvg-site/_server/diag.sh
# Add --fix to also restart nginx and the Django app (gunicorn).
[ "$1" = "--fix" ] && { echo "== restarting nginx + gunicorn"; systemctl restart gunicorn; systemctl restart nginx; sleep 2; }
r() { curl -sk -o /dev/null -m 10 -w '%{http_code}' --resolve summitbrilliance.com:443:127.0.0.1 "https://summitbrilliance.com$1"; }
echo "== $(date '+%F %T')  up: $(uptime -p)"
echo "disk: $(df -h / | awk 'NR==2{print $4" free ("$5" used)"}')   memory: $(free -m | awk '/Mem/{print $7" MB free of "$2}')"
echo "nginx:    $(systemctl is-active nginx)    gunicorn: $(systemctl is-active gunicorn)"
echo "ports:    $(ss -ltn | awk 'NR>1{print $4}' | grep -oE ':(80|443|8000)$' | sort -u | tr '\n' ' ')"
echo "nginx -t: $(nginx -t 2>&1 | tail -1)"
echo "home $(r /zh/)   admin $(r /admin/login/)   api $(r /api/consultant.json)   (want 200 200 200)"
echo "certificate ends: $(echo | openssl s_client -connect 127.0.0.1:443 -servername summitbrilliance.com 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
echo "== last update log"; tail -n 25 /var/log/fvg-update.log 2>/dev/null
echo "== nginx errors"; tail -n 8 /var/log/nginx/error.log 2>/dev/null
echo "== gunicorn"; journalctl -u gunicorn -n 8 --no-pager 2>/dev/null | cut -c1-200
