# -*- coding: utf-8 -*-
"""极简测试：set.upload_files + 原生click"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
cover_files = art["cover_files"]
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
cf = valid[0]

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

page.get("https://mp.toutiao.com")
time.sleep(2)
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
page.get(PUBLISH_URL)
time.sleep(6)
for i in range(10):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        break
    time.sleep(1)
try:
    btn = page.ele("text:关闭", timeout=2)
    if btn:
        btn.click()
        time.sleep(1)
except:
    pass

# 选三图
page.run_js("window.scrollTo(0, 0);")
time.sleep(1)
page.run_js("""
var labels = document.querySelectorAll('label');
for (var i = 0; i < labels.length; i++) {
    if (labels[i].textContent.indexOf('三图') !== -1 && labels[i].textContent.indexOf('广告') === -1) {
        labels[i].click();
        return;
    }
}
""")
time.sleep(3)
print("已选三图", flush=True)

# 测试：set.upload_files + 原生click
print(f"\n测试文件: {os.path.basename(cf)}", flush=True)
page.set.upload_files(cf)
time.sleep(0.5)

# 原生click
add_btn = page.ele('.article-cover-add', timeout=5)
if add_btn:
    print("找到add按钮，点击...", flush=True)
    add_btn.click()
    time.sleep(5)
    print("已点击，等待5秒", flush=True)
else:
    print("add按钮未找到", flush=True)

# 检查封面区
cover_imgs = page.run_js("""
var imgs = document.querySelectorAll('.article-cover-images img');
var result = {count: imgs.length, srcs: []};
for (var i = 0; i < Math.min(imgs.length, 3); i++) {
    result.srcs.push((imgs[i].src || '').substring(0, 60));
}
return JSON.stringify(result);
""")
print(f"封面区: {cover_imgs}", flush=True)

# 检查所有file input
all_fi = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    result.push({
        accept: inputs[i].accept,
        visible: inputs[i].getBoundingClientRect().width > 0
    });
}
return JSON.stringify(result);
""")
print(f"file inputs: {all_fi}", flush=True)

page.quit()
print("DONE", flush=True)