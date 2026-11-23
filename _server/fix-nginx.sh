#!/bin/bash
# Install the site's nginx config; restore the previous one if the check fails.
cp /etc/nginx/conf.d/mysite.conf /home/ec2-user/mysite.conf.before-fix
cp /opt/fvg-site/_server/nginx-site.conf /etc/nginx/conf.d/mysite.conf
if nginx -t 2>&1 | tail -1 | grep -q successful; then systemctl reload nginx; echo FIXED
else cp /home/ec2-user/mysite.conf.before-fix /etc/nginx/conf.d/mysite.conf; systemctl reload nginx; echo "RESTORED (old settings kept)"; fi
sleep 1
echo "== check"
echo "new home page: $(curl -sk --resolve summitbrilliance.com:443:127.0.0.1 https://summitbrilliance.com/zh/ | grep -c 'check.html')  (should be 1 or more)"
echo "contact page:  $(curl -sk --resolve summitbrilliance.com:443:127.0.0.1 https://summitbrilliance.com/zh/contact.html | grep -c 'data-booking')  (should be 1)"
echo "admin:        $(curl -sk -o /dev/null -w '%{http_code}' --resolve summitbrilliance.com:443:127.0.0.1 https://summitbrilliance.com/admin/)  (should be 302 or 200)"
echo DONE
