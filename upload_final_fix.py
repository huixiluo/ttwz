# -*- coding: utf-8 -*-
"""封面图上传：点击add → JS找file input → set.upload_files → JS点击input"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
title = art["title"][:30]
cover_files = art["cover_files"]
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
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*(<p[^>]*>.*?</p>)?\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            parts.append(f'<p>{re.sub(r"<[^>]+>", "", m.group(2))}</p>')
        elif m.group(4):
            img_html = f'<p><img src="{m.group(4)}" /></p>'
            if m.group(5):
                caption = re.sub(r'<[^>]+>', '', m.group(5))
                img_html += f'<p style="text-align:center;color:#999;font-size:12px;">{caption}</p>'
            parts.append(img_html)
    body_html = "\n".join(parts)

print(f"文章: {title}", flush=True)

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
print("[OK] 登录", flush=True)

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

# ===== 步骤1: 先上传封面 =====
print("\n[1] 上传封面(先上传再填内容)...", flush=True)
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if valid:
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(2)

    # 选择三图模式
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
    print("  已选三图模式", flush=True)

    for ci, cf in enumerate(valid):
        print(f"  封面{ci+1}: {os.path.basename(cf)}...", flush=True)

        # 预设文件
        page.set.upload_files(cf)
        time.sleep(0.3)

        # 点击add按钮
        page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) { add.click(); }
""")
        time.sleep(1.5)

        # JS查找file input并点击
        result = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
for (var i = 0; i < inputs.length; i++) {
    if (inputs[i].accept && inputs[i].accept.indexOf('image') !== -1) {
        inputs[i].click();
        return JSON.stringify({found: true, index: i, accept: inputs[i].accept});
    }
}
return JSON.stringify({found: false, total: inputs.length});
""")
        print(f"    点击结果: {result}", flush=True)
        time.sleep(3)

        # 检查封面区
        cover_imgs = page.run_js("""
var imgs = document.querySelectorAll('.article-cover-images img');
return imgs.length;
""")
        print(f"    封面区图片: {cover_imgs}", flush=True)

        # 如果仍然为0，尝试用DrissionPage的eles
        if cover_imgs == 0:
            print(f"    尝试DrissionPage方式...", flush=True)
            for _ in range(10):
                all_inputs = page.eles('tag:input@type=file')
                for inp in all_inputs:
                    try:
                        accept = inp.attr('accept') or ''
                        if 'image' in accept:
                            inp.input(cf)
                            time.sleep(3)
                            print(f"    DrissionPage上传完成", flush=True)
                            break
                    except:
                        pass
                time.sleep(0.5)

        # 关闭可能弹出的抽屉
        page.run_js("""
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { try { mask.click(); } catch(e) {} }
var closeBtns = document.querySelectorAll('.byte-drawer-wrapper [class*="close"], .byte-drawer-wrapper button');
for (var i = 0; i < closeBtns.length; i++) {
    try { closeBtns[i].click(); return; } catch(e) {}
}
""")
        time.sleep(1)

    print(f"  封面图上传完成", flush=True)
else:
    print("  没有有效的封面文件", flush=True)

# ===== 步骤2: 填标题 =====
print("\n[2] 填标题...", flush=True)
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
title_el.click()
time.sleep(0.5)
title_el.input(title)
time.sleep(1)
page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
print(f"  标题: {title}", flush=True)

for i in range(15):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 1;
return 0;
""")
    if s:
        print(f"  [OK] 标题已保存 ({i+1}s)", flush=True)
        break
else:
    print("  [WARN] 标题保存未确认", flush=True)

# ===== 步骤3: 填正文 =====
print("\n[3] 填正文...", flush=True)
page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (editor) {{
    editor.focus();
    editor.innerHTML = '';
    var dt = new DataTransfer();
    dt.setData('text/html', {json.dumps(body_html)});
    editor.dispatchEvent(new ClipboardEvent('paste', {{
        bubbles: true, cancelable: true, clipboardData: dt
    }}));
    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
    editor.dispatchEvent(new Event('change', {{bubbles: true}}));
}}
""")
time.sleep(2)
chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
print(f"  正文: {chars}字, {imgs}张图片", flush=True)

for i in range(15):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 1;
return 0;
""")
    if s:
        print(f"  [OK] 正文已保存 ({i+1}s)", flush=True)
        break
else:
    print("  [WARN] 正文保存未确认", flush=True)

# ===== 步骤4: 触发保存 =====
print("\n[4] 触发最终保存...", flush=True)
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
if not title_el:
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
if title_el:
    title_el.click()
    time.sleep(0.3)
    title_el.input(" ")
    time.sleep(0.3)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
    time.sleep(0.5)

for i in range(20):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 1;
return 0;
""")
    if s:
        print(f"  [OK] 保存成功 ({i+1}s)", flush=True)
        break
else:
    print("  [WARN] 保存未确认", flush=True)

# ===== 验证 =====
print("\n[5] 验证草稿箱...", flush=True)
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;")
if title[:8] in draft_text:
    idx = draft_text.find(title[:8])
    print(f"[SUCCESS] 文章已在草稿箱中!", flush=True)
    print(f"  {draft_text[idx:idx+150]}", flush=True)
else:
    print("[FAIL] 未找到", flush=True)
    print(f"  草稿箱: {draft_text[:500]}", flush=True)

page.quit()
print("\nDONE", flush=True)