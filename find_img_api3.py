# -*- coding: utf-8 -*-
"""CDP网络监听捕获图片上传端点"""
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

img = Image.new("RGB", (400, 240), (180, 120, 60))
buf = io.BytesIO()
img.save(buf, format="JPEG")
raw_b64 = base64.b64encode(buf.getvalue()).decode('ascii')

# CDP监听（监听所有mp.toutiao.com的POST）
page.listen.start("mp.toutiao.com", method="POST")

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
var file = new File([blob], 'testimg3.jpg', {type: 'image/jpeg'});
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

img_url = ""
for _ in range(40):
    time.sleep(1)
    img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
    if img_url and not img_url.startswith('blob:'):
        print("图片已上传:", img_url[:100])
        break

time.sleep(3)

print("\n=== 捕获的POST请求 ===")
try:
    for packet in page.listen.steps(timeout=3):
        try:
            u = packet.url or ""
            if 'word_check' in u or 'spell_check' in u or 'title_check' in u or 'punctuation' in u:
                continue
            print(f"URL: {u[:200]}")
            try:
                print(f"  body: {str(packet.postData)[:300]}")
            except Exception:
                pass
            try:
                print(f"  resp: {str(packet.response.body)[:250]}")
            except Exception:
                pass
            print()
        except Exception as e:
            print("ERR", e)
except Exception as e:
    print("监听异常:", e)

page.quit()
