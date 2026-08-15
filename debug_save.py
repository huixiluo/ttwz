# -*- coding: utf-8 -*-
"""调试保存：fetch hook捕获autosave请求及响应"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
chrome_path = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
if os.path.exists(chrome_path):
    co.set_browser_path(chrome_path)
co.auto_port()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.headless()
page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass
page.get(PUBLISH_URL)
time.sleep(8)

# 处理弹窗
for text in ["不恢复", "关闭"]:
    try:
        btn = page.ele(f"text:{text}", timeout=2)
        if btn:
            btn.click(); time.sleep(1)
    except Exception:
        pass
page.run_js("""
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { mask.click(); mask.remove(); }
var drawer = document.querySelector('.ai-assistant-drawer');
if (drawer) drawer.remove();
""")

# fetch + XHR 双hook
page.run_js("""
window._apiResults = [];
var origFetch = window.fetch;
window.fetch = function(url, opts) {
    var u = typeof url === 'string' ? url : (url && url.url) || '';
    if (u.indexOf('/mp/') >= 0 || u.indexOf('save') >= 0 || u.indexOf('publish') >= 0 || u.indexOf('draft') >= 0) {
        var entry = {url: u.substring(0, 150), method: (opts && opts.method) || 'GET', body: ((opts && opts.body) || '').substring(0, 400)};
        window._apiResults.push(entry);
        return origFetch.apply(this, arguments).then(function(resp) {
            return resp.clone().text().then(function(t) {
                entry.status = resp.status;
                entry.resp = t.substring(0, 400);
                return resp;
            });
        });
    }
    return origFetch.apply(this, arguments);
};
var OrigXHR = window.XMLHttpRequest;
function HookedXHR() {
    var xhr = new OrigXHR();
    var origOpen = xhr.open;
    var origSend = xhr.send;
    var _url = '';
    xhr.open = function(m, u) {
        _url = u;
        return origOpen.apply(xhr, arguments);
    };
    xhr.send = function(body) {
        if (_url.indexOf('/mp/') >= 0 || _url.indexOf('save') >= 0 || _url.indexOf('publish') >= 0) {
            var entry = {url: String(_url).substring(0, 150), method: 'XHR', body: String(body || '').substring(0, 400)};
            window._apiResults.push(entry);
            xhr.addEventListener('load', function() {
                entry.status = xhr.status;
                entry.resp = String(xhr.responseText || '').substring(0, 400);
            });
        }
        return origSend.apply(xhr, arguments);
    };
    return xhr;
}
window.XMLHttpRequest = HookedXHR;
return 'hooked';
""")

# 设置标题（native setter + input事件）
title_json = json.dumps("测试保存流程-可删除")
page.run_js(f"""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (!el) return 'no_el';
el.focus();
var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
nativeSetter.call(el, {title_json});
el.dispatchEvent(new Event('input', {{bubbles: true}}));
el.dispatchEvent(new Event('change', {{bubbles: true}}));
el.blur();
return 'ok';
""")
print("标题已设置，等待25秒观察autosave...")
time.sleep(25)

print("\n=== 捕获的API请求 ===")
api_results = page.run_js("return JSON.stringify(window._apiResults, null, 1);")
print(api_results[:4000] if api_results else "无请求")

# 页面上有无"保存"提示
ui_text = page.run_js("""
var t = document.body.innerText;
var m = t.match(/.{0,30}(保存|草稿).{0,30}/g);
return m ? m.slice(0, 10).join('\\n') : '无保存相关文本';
""")
print("\n=== UI保存提示 ===")
print(ui_text)

page.quit()
