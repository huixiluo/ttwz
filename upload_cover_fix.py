# -*- coding: utf-8 -*-
"""修复封面图上传：非headless模式 + DrissionPage原生点击"""
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
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            parts.append(f'<p>{re.sub(r"<[^>]+>", "", m.group(2))}</p>')
        elif m.group(4):
            parts.append(f'<p><img src="{m.group(4)}" /></p>')
    body_html = "\n".join(parts)

print(f"文章: {title}")

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
print("[OK] 登录")

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

# 填标题
print(f"\n标题: {title}")
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
time.sleep(3)

# 填正文
print("\n填正文...")
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
print(f"  正文: {chars}字, {imgs}张图片")

# 等待正文保存
for i in range(15):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 1;
return 0;
""")
    if s:
        print(f"  [OK] 正文已保存 ({i+1}s)")
        break
else:
    print("  [WARN] 正文保存未确认")

# === 上传封面 - 使用DrissionPage原生点击 ===
print("\n上传封面...")
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if valid:
    # 滚动到顶部
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(2)
    
    # 查找封面区域
    cover_info = page.run_js("""
var info = [];
var cover = document.querySelector('.article-cover');
if (cover) {
    info.push('article-cover found');
    cover.scrollIntoView({block: 'center'});
} else {
    info.push('article-cover NOT found');
}
// 列出所有radio button
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    var r = radios[i];
    var label = '';
    var parent = r.parentElement;
    if (parent) label = (parent.textContent || '').trim();
    info.push('radio[' + i + '] value=' + r.value + ' checked=' + r.checked + ' label=' + label.substring(0, 30));
}
return info.join('\\n');
""")
    print(f"  封面区域: {cover_info}")
    time.sleep(1)
    
    # 选择三图模式 - 使用DrissionPage原生点击
    try:
        three_img_radio = page.ele('tag:input@type=radio@value=3', timeout=3)
        if three_img_radio:
            three_img_radio.click()
            time.sleep(2)
            print("  已点击三图模式radio")
        else:
            # 尝试点击label
            labels = page.eles('tag:label')
            for label in labels:
                if '三图' in (label.text or ''):
                    label.click()
                    time.sleep(2)
                    print("  已点击三图模式label")
                    break
    except Exception as e:
        print(f"  点击三图模式失败: {e}")
    
    time.sleep(3)
    
    # 检查add按钮
    add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
    print(f"  add按钮数量: {add_count}")
    
    # 逐张上传封面
    for ci, cf in enumerate(valid):
        print(f"  封面{ci+1}: {os.path.basename(cf)}...")
        
        # 使用DrissionPage原生点击add按钮
        try:
            add_btn = page.ele('.article-cover-add', timeout=5)
            if add_btn:
                add_btn.click()
                time.sleep(2)
                print(f"    已点击add按钮")
            else:
                print(f"    add按钮未找到")
                # 尝试JS点击
                page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) {
    add.click();
    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
        add.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    });
}
""")
                time.sleep(2)
        except Exception as e:
            print(f"    点击add按钮失败: {e}")
        
        # 查找文件输入框
        fi = None
        for _ in range(20):
            all_inputs = page.eles('tag:input@type=file')
            for inp in all_inputs:
                try:
                    accept = inp.attr('accept') or ''
                    if 'image' in accept:
                        rect = inp.rect
                        if rect.size[0] > 0 and rect.size[1] > 0:
                            fi = inp
                            print(f"    找到文件输入框: {rect.size}")
                            break
                except:
                    pass
            if fi:
                break
            
            # 打印调试信息
            if _ == 0:
                total = len(all_inputs)
                print(f"    总file input: {total}")
                for idx, inp in enumerate(all_inputs[:5]):
                    try:
                        a = inp.attr('accept') or 'none'
                        r = inp.rect.size
                        print(f"      [{idx}] accept={a} size={r}")
                    except:
                        pass
            
            time.sleep(0.5)
        
        if fi:
            fi.input(cf)
            time.sleep(3)
            print(f"  封面{ci+1}: ✓")
        else:
            # 兜底：尝试所有file input
            print(f"    兜底尝试...")
            all_inputs = page.eles('tag:input@type=file')
            for inp in all_inputs:
                try:
                    inp.input(cf)
                    time.sleep(3)
                    print(f"  封面{ci+1}: ✓ (兜底)")
                    break
                except:
                    continue
            else:
                print(f"  封面{ci+1}: 失败")

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
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")

for i in range(20):
    time.sleep(1)
    s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 1;
return 0;
""")
    if s:
        print(f"  [OK] 保存成功 ({i+1}s)")
        break
else:
    print("  [WARN] 保存未确认")

# 验证
print("\n验证草稿箱...")
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;")
if title[:8] in draft_text:
    idx = draft_text.find(title[:8])
    print(f"[SUCCESS] 文章已在草稿箱中!")
    print(f"  {draft_text[idx:idx+120]}")
else:
    print("[FAIL] 未找到")
    print(f"  草稿箱: {draft_text[:500]}")

page.quit()
print("DONE")