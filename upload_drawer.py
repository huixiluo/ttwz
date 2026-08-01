# -*- coding: utf-8 -*-
"""完整上传：先封面(通过抽屉) → 标题 → 正文(含图片描述)"""
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
            # 图片 + 可能的描述
            img_html = f'<p><img src="{m.group(4)}" /></p>'
            if m.group(5):
                caption = re.sub(r'<[^>]+>', '', m.group(5))
                img_html += f'<p style="text-align:center;color:#999;font-size:12px;">{caption}</p>'
            parts.append(img_html)
    body_html = "\n".join(parts)

print(f"文章: {title}", flush=True)

# 启动浏览器 - 非headless
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
print("\n[1] 上传封面...", flush=True)
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

        # 点击 .article-cover-add 打开抽屉
        page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) { add.click(); }
""")
        time.sleep(2)

        # 等待抽屉出现
        drawer_found = False
        for _ in range(10):
            has_drawer = page.run_js("return document.querySelector('.byte-drawer-wrapper') !== null;")
            if has_drawer:
                drawer_found = True
                break
            time.sleep(0.5)

        if not drawer_found:
            print(f"    抽屉未出现", flush=True)
            continue

        print(f"    抽屉已打开", flush=True)

        # 在抽屉中查找file input
        file_input_info = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    if (inp.accept && inp.accept.indexOf('image') !== -1) {
        var rect = inp.getBoundingClientRect();
        return JSON.stringify({
            found: true,
            visible: rect.width > 0 && rect.height > 0,
            size: rect.width + 'x' + rect.height,
            parent: inp.parentElement ? inp.parentElement.className : 'none'
        });
    }
}
return JSON.stringify({found: false});
""")
        print(f"    file input: {file_input_info}", flush=True)

        # 使用DrissionPage找到file input并上传
        uploaded = False
        # 尝试在抽屉中找file input
        for _ in range(10):
            all_inputs = page.eles('tag:input@type=file')
            for inp in all_inputs:
                try:
                    accept = inp.attr('accept') or ''
                    if 'image' in accept:
                        inp.input(cf)
                        time.sleep(3)
                        uploaded = True
                        print(f"    已上传到file input", flush=True)
                        break
                except Exception as e:
                    pass
            if uploaded:
                break
            time.sleep(0.5)

        if not uploaded:
            # 兜底：用JS找到input然后通过DrissionPage操作
            print(f"    兜底方案...", flush=True)
            try:
                page.set.upload_files(cf)
                time.sleep(0.5)
                # 点击抽屉中的上传按钮
                page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
for (var i = 0; i < inputs.length; i++) {
    if (inputs[i].accept && inputs[i].accept.indexOf('image') !== -1) {
        inputs[i].click();
        return 'clicked';
    }
}
return 'not found';
""")
                time.sleep(3)
                print(f"    兜底方案已执行", flush=True)
            except Exception as e:
                print(f"    兜底方案失败: {e}", flush=True)

        # 关闭抽屉
        time.sleep(1)
        page.run_js("""
// 尝试点击关闭按钮
var closeBtns = document.querySelectorAll('.byte-drawer-wrapper button, .byte-drawer-wrapper .byte-icon-close, .byte-drawer-wrapper [class*="close"]');
for (var i = 0; i < closeBtns.length; i++) {
    try { closeBtns[i].click(); return; } catch(e) {}
}
// 尝试点击遮罩
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { try { mask.click(); } catch(e) {} }
""")
        time.sleep(2)

        # 检查封面区是否有图片
        cover_imgs = page.run_js("""
var imgs = document.querySelectorAll('.article-cover-images img');
return imgs.length;
""")
        print(f"  封面{ci+1}: 封面区当前{cover_imgs}张图", flush=True)

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

# ===== 步骤3: 填正文(paste，含图片描述) =====
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