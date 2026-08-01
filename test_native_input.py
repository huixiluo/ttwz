# -*- coding: utf-8 -*-
"""测试：只粘贴纯文本（不含base64图片），看保存是否成功"""
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
            parts.append('<p>[图片]</p>')
    body_html = "\n".join(parts)

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

# 等待标题保存
print("等待标题保存...")
for i in range(20):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'idle';
""")
    if s == 'SAVED':
        print(f"  标题已保存 ({i+1}s)")
        break
else:
    print("  标题保存未确认")

# 填正文 - 使用DrissionPage原生输入
print("\n填正文(DrissionPage原生输入)...")
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(1)
    # 逐段输入
    paragraphs = [p.strip() for p in re.findall(r'<p>(.*?)</p>', body_html, re.DOTALL)]
    for pi, para in enumerate(paragraphs):
        if para == '[图片]':
            print(f"  跳过图片占位")
            continue
        editor.input(para)
        time.sleep(0.3)
        editor.input("\n")
        time.sleep(0.3)
        if (pi + 1) % 3 == 0:
            print(f"  已输入 {pi+1}/{len(paragraphs)} 段")
    print(f"  正文输入完成: {len(paragraphs)} 段")

# 等待保存
print("\n等待保存...")
for i in range(30):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'idle';
""")
    if i % 5 == 0:
        print(f"  [{i}s] {s}")
    if s == 'SAVED':
        print(f"  [SUCCESS] {i+1}s")
        break
else:
    print("  [FAIL] 30秒未检测到保存")

# 上传封面
print("\n上传封面...")
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if valid:
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)
    page.run_js("""
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    if (radios[i].value === '3') {
        radios[i].click();
        radios[i].checked = true;
        radios[i].dispatchEvent(new Event('change', {bubbles: true}));
        return;
    }
}
""")
    time.sleep(3)

    for ci, cf in enumerate(valid):
        print(f"  封面{ci+1}: {os.path.basename(cf)}...")
        page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) {
    add.scrollIntoView({block: 'center'});
    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
        add.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    });
}
""")
        time.sleep(2)
        fi = None
        for _ in range(15):
            for inp in page.eles('tag:input@type=file'):
                try:
                    if 'image' in (inp.attr('accept') or '') and inp.rect.size[0] > 0:
                        fi = inp
                        break
                except:
                    pass
            if fi:
                break
            time.sleep(0.5)
        if fi:
            fi.input(cf)
            time.sleep(3)
            print(f"  封面{ci+1}: ✓")
        else:
            for inp in page.eles('tag:input@type=file'):
                try:
                    inp.input(cf)
                    time.sleep(3)
                    print(f"  封面{ci+1}: ✓ (兜底)")
                    break
                except:
                    continue
            else:
                print(f"  封面{ci+1}: 未找到")

# 触发保存
print("\n触发保存...")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.click()
    time.sleep(0.3)
    title_el.input(" ")
    time.sleep(0.3)
    page.actions.key_down('BACKSPACE').key_up('BACKSPACE').perform()
    time.sleep(0.5)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")

for i in range(30):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'idle';
""")
    if i % 5 == 0:
        print(f"  [{i}s] {s}")
    if s == 'SAVED':
        print(f"  [SUCCESS] {i+1}s")
        break
else:
    print("  [FAIL]")

# 验证
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