#!/bin/bash
# Take the sales-consultant add-on out again (keeps all enquiries; the consultant tables stay unused in the database).
# Run:  sudo bash /opt/fvg-site/_server/consultants/uninstall.sh
M=/home/ec2-user/mysite
python3 /opt/fvg-site/_server/consultants/patch.py "$M" --remove
rm -rf "$M/consultants"
systemctl restart gunicorn && sleep 3
echo "admin: $(curl -sk -o /dev/null -w '%{http_code}' --resolve summitbrilliance.com:443:127.0.0.1 https://summitbrilliance.com/admin/)  (should be 302)"
echo "REMOVED"
