# -*- coding: utf-8 -*-
"""使用test_simple_save.py的方式，但用真实标题+短内容测试"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
title = art["title"][:30]
html_path = art["html_file"]
cover_files = art["cover_files"]

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
plain_text = ""
if body_match:
    body = body_match.group(1)
    plain_text = re.sub(r'<div\s+class="img-wrap">.*?</div>', '', body, flags=re.DOTALL)
    plain_text = re.sub(r'<[^>]+>', '', plain_text)
    plain_text = re.sub(r'\n+', '\n', plain_text).strip()

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
print(f"Login: {page.url}")

page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(6)
for i in range(10):
    pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
    if pm > 0:
        break
    time.sleep(1)
print(f"ProseMirror: {pm}")
try:
    close_btn = page.ele("text:关闭", timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 测试1: 填标题
print("\n=== 测试1: 填标题 ===")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if title_el:
    title_el.click()
    time.sleep(0.5)
    title_el.input(title)
    time.sleep(1)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
    print(f"标题已填写: {title}")
    time.sleep(3)

status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'IDLE';
""")
print(f"填标题后状态: {status}")

# 测试2: 填正文（只填第一段）
print("\n=== 测试2: 填正文(第一段) ===")
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(1)
    first_para = plain_text.split('\n')[0][:100]  # 只取第一段的前100字
    editor.input(first_para)
    time.sleep(2)
    print(f"正文已输入: {first_para[:50]}...")
else:
    print("找不到编辑器")

for i in range(20):
    time.sleep(2)
    status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
    if (t.indexOf('草稿保存中') !== -1) return 'SAVING';
}
return 'IDLE';
""")
    print(f"  [{i*2}s] {status}")
    if 'SAVED' in status:
        print("\n[SUCCESS] 可以保存!")
        break
    if status == 'IDLE' and i > 3:
        page.run_js("""
var btns = document.querySelectorAll('button, span');
for (var i = 0; i < btns.length; i++) {
    var t = (btns[i].textContent || '').trim();
    if (t === '保存' || t.indexOf('保存草稿') !== -1) {
        btns[i].click();
        break;
    }
}
""")

# 验证草稿箱
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;")
if title[:8] in draft_text:
    print(f"[SUCCESS] 文章在草稿箱中!")
else:
    print("[FAIL] 未找到")
    print(f"  草稿箱: {draft_text[:500]}")

page.quit()
print("DONE")