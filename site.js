/* New site behaviour: 規劃初判 (planning check) and the booking form on 聯絡與預約. */
(function () {
  var lang = (document.documentElement.lang || '').toLowerCase();
  var k = /^zh-(cn|hans|sg)/.test(lang) ? 'cn' : (/^zh/.test(lang) ? 'zh' : 'en');

  // ---- 規劃初判: three choices -> suggested planning focus (rules from the client's brief)
  document.querySelectorAll('[data-check]').forEach(function (box) {
    var cfg; try { cfg = JSON.parse(box.getAttribute('data-check')); } catch (e) { return; }
    var form = box.querySelector('form'), title = box.querySelector('[data-r-title]'), text = box.querySelector('[data-r-text]'),
        chips = box.querySelector('[data-r-chips]'), link = box.querySelector('.fv-check-result a');
    var base = link ? link.getAttribute('href') : '';
    function show() {
      var v = {}; ['grade', 'dest', 'base'].forEach(function (n) { v[n] = form.elements[n].value; });
      chips.textContent = '';
      if (!v.grade || !v.dest || !v.base) {
        title.textContent = cfg.empty[0]; text.textContent = cfg.empty[1];
        if (link) link.setAttribute('href', base);
        return;
      }
      var t = cfg.title.replace('{grade}', cfg.labels.grade[v.grade]).replace('{dest}', cfg.labels.dest[v.dest]);
      var p = cfg.dest[v.dest] + ' ' + cfg.base[v.base] + ' ' + cfg.tail;
      title.textContent = t; text.textContent = p;
      (cfg.focus[v.grade] || []).forEach(function (f) { var li = document.createElement('li'); li.textContent = f; chips.appendChild(li); });
      if (link) link.setAttribute('href', base + (base.indexOf('?') < 0 ? '?' : '&') + 'check=' +
        encodeURIComponent(t + '｜' + cfg.labels.base[v.base] + '｜' + (cfg.focus[v.grade] || []).join('、')));
    }
    form.addEventListener('submit', function (ev) { ev.preventDefault(); show(); });
    form.addEventListener('change', function () { if (title.textContent !== cfg.empty[0]) show(); });
  });

  // ---- booking form on 聯絡與預約
  document.querySelectorAll('form[data-booking]').forEach(function (form) {
    var note = form.elements.note, pre = new URLSearchParams(location.search).get('check');
    if (pre && note && !note.value) note.value = ({ zh: '規劃初判結果：', cn: '规划初判结果：', en: 'Planning check result: ' })[k] + pre;
    var ok = form.querySelector('[data-booking-ok]'), err = form.querySelector('[data-booking-err]'), btn = form.querySelector('button[type=submit]');
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (!form.reportValidity()) return;
      err.hidden = true; btn.disabled = true;
      var data = new FormData(form); data.append('lang', k);
      fetch('/api/booking', { method: 'POST', body: data, credentials: 'same-origin' })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || !j.ok) throw j; }); })
        .then(function () {
          [].forEach.call(form.querySelectorAll('.fv-field, .fv-two, .fv-check-line, button[type=submit], .fv-small'), function (el) { el.hidden = true; el.style.display = 'none'; });
          ok.hidden = false; ok.scrollIntoView({ behavior: 'smooth', block: 'center' });
        })
        .catch(function () { err.hidden = false; btn.disabled = false; });
    });
  });
})();
