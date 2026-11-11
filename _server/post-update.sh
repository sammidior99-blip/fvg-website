#!/bin/bash
# Runs on the EC2 server (as root) after each website update.
# Sets up the daily insights feed: fetch every 6 hours, keep the latest copy in /opt/fvg-news.
install -d /opt/fvg-news
cat > /etc/cron.d/fvg-news <<'CRON'
15 */6 * * * root /usr/bin/python3 /opt/fvg-site/_server/news.py /opt/fvg-news/news.json >> /var/log/fvg-news.log 2>&1; cp -f /opt/fvg-news/news.json /var/www/summit/news.json 2>/dev/null; mkdir -p /var/www/summit/news-img; cp -rf /opt/fvg-news/img/. /var/www/summit/news-img/ 2>/dev/null; chmod -R a+rX /var/www/summit/news-img
CRON
chmod 644 /etc/cron.d/fvg-news
if [ ! -f /opt/fvg-news/news.json ]; then
  /usr/bin/python3 /opt/fvg-site/_server/news.py /opt/fvg-news/news.json >> /var/log/fvg-news.log 2>&1
fi
[ -f /opt/fvg-news/news.json ] && cp -f /opt/fvg-news/news.json /var/www/summit/news.json && chmod 644 /var/www/summit/news.json
mkdir -p /var/www/summit/news-img && cp -rf /opt/fvg-news/img/. /var/www/summit/news-img/ 2>/dev/null; chmod -R a+rX /var/www/summit/news-img
exit 0
