# -*- coding: utf-8 -*-
"""混合策略上传：标题真实输入 + 正文paste后触发输入 + 封面上传"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def init_browser():
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.headless(True)
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
    if "profile" not in page.url.lower():
        page.quit()
        raise RuntimeError("Cookie登录失败")
    print("  [OK] 登录成功")
    return page

def wait_for_save(page, timeout=60):
    """等待保存完成"""
    for i in range(timeout // 2):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED';
    if (t.indexOf('草稿保存中') !== -1) return 'SAVING';
}
return 'IDLE';
""")
        if status == 'SAVED':
            return True
        if i % 5 == 0:
            print(f"    保存状态({i*2}s): {status}")
    return False

def upload_cover_images(page, cover_paths):
    """上传封面图"""
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        return False

    print(f"  [封面] 上传{len(valid)}张...")

    # 滚动到顶部
    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)

    # 选三图
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

    add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
    print(f"    add按钮: {add_count}")

    success = 0
    for ci, cf in enumerate(valid):
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

        file_input = None
        for _ in range(15):
            all_inputs = page.eles('tag:input@type=file')
            for fi in all_inputs:
                try:
                    accept = fi.attr('accept') or ''
                    if 'image' in accept:
                        rect = fi.rect
                        if rect.size[0] > 0 and rect.size[1] > 0:
                            file_input = fi
                            break
                except:
                    pass
            if file_input:
                break
            time.sleep(0.5)

        if file_input:
            file_input.input(cf)
            time.sleep(3)
            success += 1
            print(f"    封面{ci+1}: ✓")
        else:
            print(f"    封面{ci+1}: 找不到控件")

    print(f"  [封面] 成功 {success}/{len(valid)}")
    return success > 0

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    title = art.get("title", "")
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"文章: {title}")

    # 读取HTML构建正文
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_match:
        print("未找到正文")
        return
    body = body_match.group(1)
    result_parts = []
    for m in re.finditer(
        r'(<p>(.*?)</p>)|'
        r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*</div>)',
        body, re.DOTALL
    ):
        if m.group(1):
            para_text = re.sub(r'<[^>]+>', '', m.group(2))
            result_parts.append(f'<p>{para_text}</p>')
        elif m.group(4):
            result_parts.append(f'<p><img src="{m.group(4)}" /></p>')
    body_html = "\n".join(result_parts)

    page = init_browser()
    page.get(PUBLISH_URL)
    time.sleep(6)

    # 等待ProseMirror
    for i in range(10):
        pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
        if pm > 0:
            break
        time.sleep(1)
    print(f"ProseMirror: {pm}")

    # 关闭弹窗
    try:
        close_btn = page.ele("text:关闭", timeout=2)
        if close_btn:
            close_btn.click()
            time.sleep(1)
    except:
        pass

    # === 第1步：填标题（真实输入，触发保存） ===
    print("\n=== 第1步：填标题 ===")
    title_text = title[:30]
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.click()
        time.sleep(0.3)
        title_el.clear()
        time.sleep(0.2)
        title_el.input(title_text)
        time.sleep(0.5)
        # 触发blur确保保存
        page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
        print(f"  标题: {title_text}")

    # 等待标题保存
    print("  等待标题保存...")
    if wait_for_save(page, 30):
        print("  [OK] 标题已保存")
    else:
        print("  [警告] 标题保存未确认")

    # === 第2步：上传封面（在页面顶部） ===
    print("\n=== 第2步：上传封面 ===")
    if cover_files:
        upload_cover_images(page, cover_files)

    # 等待封面保存
    print("  等待封面保存...")
    wait_for_save(page, 30)

    # === 第3步：填正文（paste + 触发输入事件） ===
    print("\n=== 第3步：填正文 ===")
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

    # 关键：在编辑器里输入一个空格再删除，触发React的onChange
    print("  触发编辑器输入事件...")
    editor = page.ele('.ProseMirror', timeout=5)
    if editor:
        editor.click()
        time.sleep(0.5)
        # 输入一个空格
        editor.input(" ")
        time.sleep(0.2)
        # 删除空格（触发backspace）
        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    editor.dispatchEvent(new KeyboardEvent('keyup', {key: 'Backspace', bubbles: true}));
    editor.dispatchEvent(new Event('input', {bubbles: true}));
    editor.dispatchEvent(new Event('change', {bubbles: true}));
    editor.blur();
}
""")
        time.sleep(1)

    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  正文: {chars}字, {imgs}张图片")

    # === 第4步：触发标题修改（确保保存） ===
    print("\n=== 第4步：触发保存 ===")
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.click()
        time.sleep(0.3)
        # 在标题末尾加空格再删除
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
        print("  已触发标题修改")

    # 等待最终保存
    print("  等待最终保存...")
    if wait_for_save(page, 60):
        print("\n[SUCCESS] 草稿保存成功！")
    else:
        print("\n[警告] 保存未确认，检查草稿箱...")

    page.quit()
    print("DONE")

if __name__ == "__main__":
    main()