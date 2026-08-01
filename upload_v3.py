# -*- coding: utf-8 -*-
"""最终策略：每步操作后通过修改标题(.input)触发保存"""
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
    if "profile" not in page.url.lower():
        page.quit()
        raise RuntimeError("Cookie登录失败")
    print("[OK] 登录成功")
    return page

def trigger_save_via_title(page):
    """通过修改标题来触发保存"""
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        return False
    
    # 点击标题区域
    title_el.click()
    time.sleep(0.3)
    # 在末尾加一个空格
    title_el.input(" ")
    time.sleep(0.3)
    # 删除空格
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
    return True

def wait_for_save(page, timeout=30):
    """等待保存完成"""
    for i in range(timeout // 2):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
return 'WAIT';
""")
        if status == 'SAVED':
            return True
    return False

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    art = articles[0]
    real_title = art.get("title", "")[:30]
    cover_files = art.get("cover_files", [])
    html_path = art.get("html_file", "")

    print(f"标题: {real_title}")

    # 读取HTML正文
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body_html = ""
    if body_match:
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

    for i in range(10):
        pm = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
        if pm > 0:
            break
        time.sleep(1)

    try:
        close_btn = page.ele("text:关闭", timeout=2)
        if close_btn:
            close_btn.click()
            time.sleep(1)
    except:
        pass

    # === 步骤1: 填标题 + 等待保存 ===
    print("\n[1] 填标题...")
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    title_el.click()
    time.sleep(0.3)
    title_el.input(real_title)
    time.sleep(1)
    # blur触发保存
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
    print(f"  标题: {real_title}")

    print("  等待保存...")
    if wait_for_save(page, 20):
        print("  [OK] 标题已保存")
    else:
        print("  [警告] 标题保存未确认，但继续...")

    # === 步骤2: 填正文(paste) + 触发保存 ===
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
    editor.dispatchEvent(new Event('change', {{bubbles: true}}));
}}
""")
    time.sleep(2)
    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  正文: {chars}字, {imgs}张图片")

    # 触发保存：通过修改标题
    print("  触发保存...")
    trigger_save_via_title(page)
    if wait_for_save(page, 20):
        print("  [OK] 正文已保存")
    else:
        print("  [警告] 正文保存未确认")

    # === 步骤3: 上传封面 + 触发保存 ===
    print("\n[3] 上传封面图...")
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
            file_input = None
            for _ in range(15):
                all_inputs = page.eles('tag:input@type=file')
                for fi in all_inputs:
                    try:
                        if 'image' in (fi.attr('accept') or ''):
                            if fi.rect.size[0] > 0:
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
                print(f"  封面{ci+1}: ✓")
            else:
                print(f"  封面{ci+1}: 未找到控件")

    # 触发保存
    print("  触发保存...")
    trigger_save_via_title(page)
    if wait_for_save(page, 30):
        print("  [OK] 封面已保存")
    else:
        print("  [警告] 封面保存未确认")

    # === 最终验证 ===
    print("\n[4] 最终验证...")
    trigger_save_via_title(page)
    if wait_for_save(page, 30):
        print("\n[SUCCESS] 草稿保存成功！")
    else:
        print("\n检查草稿箱...")
        page.get("https://mp.toutiao.com/profile_v4/manage/draft")
        time.sleep(5)
        draft_text = page.run_js("return document.body.innerText.substring(0, 800);")
        if real_title[:10] in draft_text:
            print("[SUCCESS] 文章已在草稿箱中！")
        else:
            print("[FAIL] 文章中未找到")

    page.quit()
    print("DONE")

if __name__ == "__main__":
    main()