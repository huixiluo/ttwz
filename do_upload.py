# -*- coding: utf-8 -*-
"""简化策略：串行操作，每步等待保存确认"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def init_browser():
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
    print("[OK] 登录")
    return page

def wait_save(page, timeout=20):
    for i in range(timeout):
        time.sleep(1)
        s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return null;
""")
        if s:
            return True
    return False

def trigger_save(page):
    """通过修改标题触发保存"""
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if title_el:
        title_el.click()
        time.sleep(0.2)
        title_el.input(" ")
        time.sleep(0.2)
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

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    title = art.get("title", "")[:30]
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"标题: {title}")

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

    page = init_browser()
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

    # === 步骤1: 填标题，等待保存 ===
    print("\n[1] 填标题...")
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
    print(f"  标题: {title}")

    if wait_save(page, 15):
        print("  [OK] 标题已保存")
    else:
        print("  [WARN] 标题保存未确认")

    # === 步骤2: 填正文(paste)，触发保存 ===
    print("\n[2] 填正文...")
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
}}
""")
    time.sleep(2)
    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    print(f"  正文: {chars}字")

    trigger_save(page)
    if wait_save(page, 20):
        print("  [OK] 正文已保存")
    else:
        print("  [WARN] 正文保存未确认")

    # === 步骤3: 上传封面，触发保存 ===
    print("\n[3] 上传封面...")
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
                print(f"  封面{ci+1}: 未找到")

    trigger_save(page)
    if wait_save(page, 20):
        print("  [OK] 封面已保存")
    else:
        print("  [WARN] 封面保存未确认")

    # === 最终验证 ===
    print("\n[4] 最终验证...")
    trigger_save(page)
    if wait_save(page, 30):
        print("\n[SUCCESS] 草稿已保存！")
    else:
        page.get("https://mp.toutiao.com/profile_v4/manage/draft")
        time.sleep(5)
        text = page.run_js("return document.body.innerText;")
        if title[:8] in text:
            print("[SUCCESS] 文章在草稿箱中!")
        else:
            print("[CHECK] 草稿箱:")
            print(text[:500])

    page.quit()
    print("DONE")

if __name__ == "__main__":
    main()