"""后台简体化: the Django admin is shown in Simplified Chinese.
- /admin pages use Django's zh-hans translation (see middleware.py).
- Labels of the original website app (pages: 咨询查询 etc.), written in Traditional Chinese, are converted when Django starts.
Needs the opencc-python-reimplemented package (installed by install.sh); without it the labels simply stay as they are."""
import logging

ADMIN_LANGUAGE = "zh-hans"
FIX = [("帐号", "账号"), ("登入", "登录"), ("电邮", "邮箱"), ("联络", "联系"), ("连结", "链接"), ("设定", "设置"), ("储存", "保存"),
       ("讯息", "消息"), ("纪录", "记录"), ("上载", "上传"), ("资讯", "信息"), ("汇出", "导出"), ("预设", "默认"), ("「", "“"), ("」", "”")]
log = logging.getLogger(__name__)


def _converter():
    try:
        from opencc import OpenCC
    except ImportError:
        return None
    for cfg in ("hk2s", "hk2s.json", "t2s", "t2s.json"):
        try:
            cc = OpenCC(cfg)
            cc.convert("測試")
            return cc
        except Exception:
            continue
    return None


def make():
    cc = _converter()
    if cc is None:
        return None

    def s(v):
        if v is None: return v
        t = str(v)
        if not any("㐀" <= ch <= "鿿" for ch in t): return v
        t = cc.convert(t)
        for a, b in FIX: t = t.replace(a, b)
        return t
    return s


def _choices(ch, s):
    out = []
    for k, v in ch:
        out.append((k, _choices(v, s)) if isinstance(v, (list, tuple)) else (k, s(v)))
    return out


def convert_app(label):
    """Convert one app's labels (app name, model names, field names/help texts/choices, its admin columns/sections/actions)."""
    try:
        s = make()
        if s is None:
            log.warning("opencc not installed: %s labels stay in Traditional Chinese", label)
            return
        from django.apps import apps
        from django.contrib import admin
        cfg = apps.get_app_config(label)
        cfg.verbose_name = s(cfg.verbose_name)
        for m in cfg.get_models():
            o = m._meta
            o.verbose_name, o.verbose_name_plural = s(o.verbose_name), s(o.verbose_name_plural)
            for f in o.get_fields():
                if hasattr(f, "verbose_name") and f.verbose_name: f.verbose_name = s(f.verbose_name)
                if getattr(f, "help_text", None): f.help_text = s(f.help_text)
                if getattr(f, "choices", None): f.choices = _choices(f.choices, s)
            ma = admin.site._registry.get(m)
            if ma is None: continue
            for name in ("fieldsets", "add_fieldsets"):
                fs = getattr(ma, name, None)
                if isinstance(fs, (list, tuple)):
                    setattr(ma, name, [(s(t), opts) for t, opts in fs])
            for attr in dir(type(ma)):
                fn = getattr(type(ma), attr, None)
                if callable(fn) and getattr(fn, "short_description", None):
                    try: fn.short_description = s(fn.short_description)
                    except AttributeError: pass
            for a in (getattr(ma, "actions", None) or []):
                fn = getattr(ma, a, None) if isinstance(a, str) else a
                fn = getattr(fn, "__func__", fn)
                if fn is not None and getattr(fn, "short_description", None):
                    try: fn.short_description = s(fn.short_description)
                    except AttributeError: pass
    except Exception:
        log.exception("could not convert %s labels to Simplified Chinese", label)
