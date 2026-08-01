# -*- coding: utf-8 -*-
"""测试：纯文本（不含图片）能否保存成功"""
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

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
body_html = ""
if body_match:
    body = body_match.group(1)
    parts = []
    for m in re.finditer(
        r'(<p>(.*?)</p>)|'
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            parts.append('<p>' + re.sub(r'<[^>]+>', '', m.group(2)) + '</p>')
        elif m.group(4):
            # 跳过图片
            pass
    body_html = "\n".join(parts)

print(f"正文段落数: {len(parts)}")

co = ChromiumOptions()
co.headless(True)
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
print("[OK] 登录")

page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
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

# 填标题
print(f"\n标题: {title}")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
title_el.click()
time.sleep(0.3)
title_el.input(title)
time.sleep(0.5)
page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")

# 填正文 - 纯文本 paste
print("\n填正文(纯文本)...")
result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'editor_not_found';
editor.focus();
editor.innerHTML = '';
var dt = new DataTransfer();
dt.setData('text/html', {json.dumps(body_html)});
editor.dispatchEvent(new ClipboardEvent('paste', {{
    bubbles: true, cancelable: true, clipboardData: dt
}}));
editor.dispatchEvent(new Event('input', {{bubbles: true}}));
editor.dispatchEvent(new Event('change', {{bubbles: true}}));
return 'ok';
""")
time.sleep(2)
chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
print(f"  正文: {chars}字")

# 等待保存 - 监控状态
print("\n等待保存...")
for i in range(40):
    time.sleep(1)
    status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
if (body.indexOf('保存失败') !== -1) return 'FAILED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'idle';
""")
    if i % 5 == 0:
        print(f"  [{i}s] {status}")
    if status in ('SAVED', 'FAILED'):
        print(f"  [{i}s] 最终状态: {status}")
        break
else:
    print("  超时")

# 验证草稿箱
print("\n验证草稿箱...")
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;")
if title[:8] in draft_text:
    idx = draft_text.find(title[:8])
    print(f"[SUCCESS] 文章在草稿箱中!")
    print(f"  {draft_text[idx:idx+120]}")
else:
    print("[FAIL] 未找到")
    print(f"  草稿箱: {draft_text[:500]}")

page.quit()
print("DONE")