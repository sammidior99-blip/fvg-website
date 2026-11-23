/* Shows the visitor's own sales consultant (set by their personal link /s/<code>) instead of the company contact.
   Works with the contact float (.sb-chat-panel) and with any element marked data-consultant-*:
   data-consultant-show / -hide, -name, -title, -photo (img), -phone, -email, -whatsapp (a), -wechat-qr (img), -wechat-id */
(function () {
  if (window.__fvgConsultant) return; window.__fvgConsultant = 1;
  var lang = (document.documentElement.lang || '').toLowerCase();
  var k = /^zh-(cn|hans|sg)/.test(lang) ? 'cn' : (/^zh/.test(lang) ? 'zh' : 'en');
  var T = {
    zh: { head: '您的專屬顧問', sub: '掃描二維碼，或按下方按鈕，直接聯絡您的顧問。', wa: '開啟 WhatsApp', call: '電話', mail: '電郵', wid: '微信號', fab: '聯絡顧問', chatH: '透過 WhatsApp 或微信聯絡 {n}' },
    cn: { head: '您的专属顾问', sub: '扫描二维码，或点击下方按钮，直接联系您的顾问。', wa: '打开 WhatsApp', call: '电话', mail: '邮箱', wid: '微信号', fab: '联系顾问', chatH: '通过 WhatsApp 或微信联系 {n}' },
    en: { head: 'Your consultant', sub: 'Scan a QR code or tap below to reach your consultant directly.', wa: 'Open WhatsApp', call: 'Phone', mail: 'Email', wid: 'WeChat ID', fab: 'Contact', chatH: 'Chat with {n} on WhatsApp or WeChat' }
  }[k];
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function safeUrl(u) { return /^(https:\/\/|\/(?!\/))/.test(u || '') ? u : ''; }
  function hide(e) { if (e) e.style.display = 'none'; }

  function apply(c) {
    var name = k === 'en' ? (c.name_en || c.name_zh) : (c.name_zh || c.name_en);
    var title = k === 'en' ? (c.title_en || c.title_zh) : (c.title_zh || c.title_en);
    var tel = (c.phone || '').replace(/[^\d+]/g, '');
    function card() { return cardFor(c, name, title); }

    // 1) generic slots (new site design)
    document.querySelectorAll('[data-consultant-hide]').forEach(hide);
    document.querySelectorAll('[data-consultant-show]').forEach(function (e) { e.hidden = false; e.style.removeProperty('display'); });
    function each(sel, fn, has) { document.querySelectorAll(sel).forEach(function (e) { if (has) fn(e); else hide(e); }); }
    each('[data-consultant-name]', function (e) { e.textContent = name; }, name);
    each('[data-consultant-title]', function (e) { e.textContent = title; }, title);
    each('[data-consultant-photo]', function (e) { e.src = safeUrl(c.photo); e.alt = name; }, safeUrl(c.photo));
    each('[data-consultant-wechat-qr]', function (e) { e.src = safeUrl(c.wechat_qr); }, safeUrl(c.wechat_qr));
    each('[data-consultant-wechat-id]', function (e) { e.textContent = c.wechat_id; }, c.wechat_id);
    each('[data-consultant-phone]', function (e) { e.textContent = c.phone; if (e.tagName === 'A') e.href = 'tel:' + tel; }, tel);
    each('[data-consultant-email]', function (e) { e.textContent = c.email; if (e.tagName === 'A') e.href = 'mailto:' + c.email; }, c.email);
    each('[data-consultant-whatsapp]', function (e) { e.href = safeUrl(c.whatsapp); }, safeUrl(c.whatsapp));

    // 2) every company QR code, WhatsApp button and contact value on the page -> the consultant's
    document.querySelectorAll('img').forEach(function (q) {
      var s = (q.getAttribute('src') || '') + ' ' + (q.alt || ''), wa = /qr-whatsapp|whatsapp/i.test(s), wc = /qr-wechat|微信|wechat/i.test(s);
      if (!wa && !wc) return;
      var src = safeUrl(wa ? c.whatsapp_qr : c.wechat_qr);
      if (src) q.src = src; else hide(q.parentNode);
    });
    document.querySelectorAll('a[href*="wa.me"]').forEach(function (a) {
      if (safeUrl(c.whatsapp)) { a.href = c.whatsapp; a.textContent = T.wa; } else hide(a);
    });
    document.querySelectorAll('aside p, aside dd, aside span').forEach(function (v) {
      var label = v.previousElementSibling ? v.previousElementSibling.textContent : '';
      if (/電郵|电邮|邮箱|e-?mail/i.test(label) && c.email) v.textContent = c.email;
      if (/電話|电话|phone/i.test(label) && c.phone) v.textContent = c.phone;
    });
    var chat = document.getElementById('chat');
    if (chat) {
      var hh = chat.querySelector('h2'), eye = hh && hh.previousElementSibling;
      if (eye) eye.textContent = T.head;
      if (hh) { hh.textContent = T.chatH.replace('{n}', name); hh.parentNode.insertBefore(card(), hh.nextSibling); }
    }

    // 3) the contact float
    var p = document.querySelector('.sb-chat-panel');
    if (!p) { style(); return; }
    var ps = p.querySelectorAll('p');
    if (ps[0]) ps[0].textContent = T.head;
    if (ps[1]) ps[1].textContent = T.sub;
    var head = p.firstElementChild; head.parentNode.insertBefore(card(), head.nextSibling);
    var btn = p.querySelector('a[href*="wa.me"]');
    var list = el('dl', 'fvc-list');
    function row(label, text, href) { if (!text) return; list.appendChild(el('dt', '', label)); var d = el('dd'); var a = href ? el('a', '', text) : el('span', '', text); if (href) a.href = href; d.appendChild(a); list.appendChild(d); }
    row(T.call, c.phone, tel ? 'tel:' + tel : ''); row(T.wid, c.wechat_id); row(T.mail, c.email, c.email ? 'mailto:' + c.email : '');
    if (list.children.length) (btn || p.lastElementChild).insertAdjacentElement('afterend', list);
    var fab = document.querySelector('.sb-chat-fab span'); if (fab) fab.textContent = T.fab;
    style();
  }

  function cardFor(c, name, title) {
    var cd = el('div', 'fvc-card');
    if (safeUrl(c.photo)) { var im = el('img'); im.src = safeUrl(c.photo); im.alt = ''; im.width = 56; im.height = 56; cd.appendChild(im); }
    var who = el('div'); who.appendChild(el('b', '', name)); if (title) who.appendChild(el('span', '', title)); cd.appendChild(who);
    return cd;
  }

  function style() {
    if (document.getElementById('fvc-style')) return;
    var st = el('style'); st.id = 'fvc-style';
    st.textContent = '.fvc-card{display:flex;align-items:center;gap:12px;margin-top:16px;padding:12px;border:1px solid #E1E6EE;border-radius:14px;background:#F6F8FB}' +
      '.fvc-card img{width:56px;height:56px;border-radius:50%;object-fit:cover;flex:none}.fvc-card b{display:block;font-size:17px;color:#0F2340}' +
      '.fvc-card span{display:block;margin-top:2px;font-size:13px;color:#4A5A72}' +
      '.fvc-list{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:14px 0 0;font-size:14px}.fvc-list dt{color:#5B6B82}.fvc-list dd{margin:0;font-weight:600;color:#0F2340;word-break:break-all}' +
      '.fvc-list a{color:#0F2340}';
    document.head.appendChild(st);
  }

  fetch('/api/consultant.json', { credentials: 'same-origin', cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (c) { if (c && c.code) apply(c); })
    .catch(function () {});
})();
