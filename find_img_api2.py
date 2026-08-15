# -*- coding: utf-8 -*-
"""fetch hook捕获图片上传端点"""
import os, json, time, base64, io
from PIL import Image
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
""")

# fetch hook
page.run_js("""
window._uploads = [];
var origFetch = window.fetch;
window.fetch = function(url, opts) {
    var u = typeof url === 'string' ? url : (url && url.url) || '';
    var method = (opts && opts.method) || 'GET';
    var isPost = method.toUpperCase() === 'POST';
    var looksUpload = u.indexOf('image') >= 0 || u.indexOf('upload') >= 0 || u.indexOf('photo') >= 0 || u.indexOf('material') >= 0 || (isPost && opts && opts.body instanceof FormData);
    if (looksUpload) {
        var entry = {url: String(u).substring(0, 250), method: method};
        window._uploads.push(entry);
        return origFetch.apply(this, arguments).then(function(resp) {
            return resp.clone().text().then(function(t) {
                entry.status = resp.status;
                entry.resp = t.substring(0, 500);
                return resp;
            });
        });
    }
    return origFetch.apply(this, arguments);
};
return 'hooked';
""")

img = Image.new("RGB", (400, 240), (60, 180, 90))
buf = io.BytesIO()
img.save(buf, format="JPEG")
raw_b64 = base64.b64encode(buf.getvalue()).decode('ascii')

page.run_js("""
    var editor = document.querySelector('.ProseMirror');
    if (editor) { editor.innerHTML = '<p></p>'; }
""")
time.sleep(0.3)
page.run_js("var e=document.querySelector('.ProseMirror'); if(e) e.focus();")
time.sleep(0.3)

paste_js = """
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'no_editor';
editor.focus();
var byteString = atob(B64PLACEHOLDER);
var ab = new ArrayBuffer(byteString.length);
var ia = new Uint8Array(ab);
for (var i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
var blob = new Blob([ab], {type: 'image/jpeg'});
var file = new File([blob], 'testimg2.jpg', {type: 'image/jpeg'});
var pasteEvent = new ClipboardEvent('paste', {bubbles: true, cancelable: true});
var fakeData = {
    files: [file], items: [], types: ['Files'],
    getData: function() { return ''; },
    setData: function() {}, clearData: function() {}
};
Object.defineProperty(pasteEvent, 'clipboardData', {value: fakeData, writable: false, configurable: true});
editor.dispatchEvent(pasteEvent);
return 'pasted';
""".replace("B64PLACEHOLDER", json.dumps(raw_b64))
print("粘贴:", page.run_js(paste_js))

for _ in range(30):
    time.sleep(1)
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
    if imgs > 0:
        break
time.sleep(6)

print("\n=== 捕获的上传请求(fetch) ===")
uploads = page.run_js("return JSON.stringify(window._uploads, null, 1);")
print(uploads[:4000] if uploads else "无")

page.quit()
