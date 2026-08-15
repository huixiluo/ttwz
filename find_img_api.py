# -*- coding: utf-8 -*-
"""粘贴图片到编辑器，捕获图片上传API端点"""
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

# XHR hook 捕获所有POST（找上传端点）
page.run_js("""
window._uploads = [];
var OrigXHR = window.XMLHttpRequest;
function HookedXHR() {
    var xhr = new OrigXHR();
    var origOpen = xhr.open, origSend = xhr.send, _url = '', _method = '';
    xhr.open = function(m, u) { _url = u; _method = m; return origOpen.apply(xhr, arguments); };
    xhr.send = function(body) {
        var u = String(_url);
        var isUpload = (body instanceof FormData) && _method.toUpperCase() === 'POST';
        var isImgApi = u.indexOf('image') >= 0 || u.indexOf('upload') >= 0 || u.indexOf('material') >= 0 || u.indexOf('photo') >= 0 || u.indexOf('media') >= 0;
        if (isUpload || isImgApi) {
            var fdInfo = '';
            try {
                if (body instanceof FormData) {
                    for (var pair of body.entries()) {
                        fdInfo += pair[0] + (typeof pair[1] === 'string' ? '=' + pair[1].substring(0, 50) : '(file)') + ' & ';
                    }
                }
            } catch(e) {}
            var entry = {url: u.substring(0, 200), method: _method, form: fdInfo.substring(0, 300)};
            window._uploads.push(entry);
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

# 生成测试图片并粘贴（复用batch流程的粘贴方法）
img = Image.new("RGB", (400, 240), (60, 120, 200))
buf = io.BytesIO()
img.save(buf, format="JPEG")
raw_b64 = base64.b64encode(buf.getvalue()).decode('ascii')

page.run_js("""
    var editor = document.querySelector('.ProseMirror');
    if (editor) { editor.innerHTML = '<p></p>'; editor.dispatchEvent(new Event('input', {bubbles: true})); }
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
var file = new File([blob], 'testimg.jpg', {type: 'image/jpeg'});
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
r = page.run_js(paste_js)
print("粘贴:", r)

# 等待上传完成
for _ in range(30):
    time.sleep(1)
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
    if imgs > 0:
        print("编辑器已出现图片")
        break

time.sleep(5)

print("\n=== 捕获的上传请求 ===")
uploads = page.run_js("return JSON.stringify(window._uploads, null, 1);")
print(uploads[:3000] if uploads else "无")

img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';")
print("\n编辑器图片src:", img_url)

page.quit()
