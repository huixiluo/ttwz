# -*- coding: utf-8 -*-
"""最简方案：标题.input() + 正文innerHTML + .input()触发React"""
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

# 提取纯文本正文（不含图片）
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
plain_text = ""
if body_match:
    body = body_match.group(1)
    # Remove all HTML tags and image placeholders
    plain_text = re.sub(r'<div\s+class="img-wrap">.*?</div>', '', body, flags=re.DOTALL)
    plain_text = re.sub(r'<[^>]+>', '', plain_text)
    plain_text = re.sub(r'\n+', '\n', plain_text).strip()

print(f"纯文本长度: {len(plain_text)} 字")

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

# 填正文 - 使用DrissionPage .input()逐段输入
print("\n填正文(.input逐段)...")
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(1)
    
    paragraphs = [p.strip() for p in plain_text.split('\n') if p.strip()]
    print(f"  共{len(paragraphs)}段")
    
    for pi, para in enumerate(paragraphs):
        # 每段用.input()输入
        editor.input(para)
        time.sleep(0.2)
        # 段落间回车
        if pi < len(paragraphs) - 1:
            editor.input("\n")
            time.sleep(0.1)
        if (pi + 1) % 3 == 0:
            print(f"  已输入 {pi+1}/{len(paragraphs)} 段")
    
    print(f"  正文输入完成")

chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
print(f"  正文: {chars}字")

# 等待保存
print("\n等待保存...")
for i in range(30):
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
        print(f"  最终: {status}")
        break
else:
    print("  超时")

# 如果保存失败，尝试通过修改标题触发
if status != 'SAVED':
    print("\n通过修改标题触发保存...")
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
if (body.indexOf('保存失败') !== -1) return 'FAILED';
return 'idle';
""")
        if i % 5 == 0:
            print(f"  [{i}s] {s}")
        if s in ('SAVED', 'FAILED'):
            print(f"  最终: {s}")
            break

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
        print(f"  封面{ci+1}: ...")
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
if (body.indexOf('保存失败') !== -1) return 'FAILED';
return 'idle';
""")
    if i % 5 == 0:
        print(f"  [{i}s] {s}")
    if s in ('SAVED', 'FAILED'):
        print(f"  最终: {s}")
        break

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