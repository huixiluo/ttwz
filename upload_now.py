# -*- coding: utf-8 -*-
"""上传脚本：标题DrissionPage输入 + 正文paste + 编辑器输入触发保存 + 封面上传"""
import os, re, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"


def wait_for_save(page, timeout=30):
    """等待保存完成，通过body.innerText和按钮文本双重检测"""
    for i in range(timeout):
        time.sleep(1)
        s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
// 也检查按钮文本
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
}
return 'idle';
""")
        if s and 'SAVED' in str(s):
            print(f"  [OK] 保存成功 ({i+1}s)")
            return True
    return False


def trigger_save_via_title(page):
    """通过修改标题来触发保存"""
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        return False
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
    return True


def trigger_save_via_editor(page):
    """通过在编辑器里输入空格再删除来触发React保存"""
    editor = page.ele('.ProseMirror', timeout=5)
    if not editor:
        return False
    editor.click()
    time.sleep(0.5)
    editor.input(" ")
    time.sleep(0.3)
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    editor.dispatchEvent(new Event('input', {bubbles: true}));
    editor.blur();
    editor.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
    time.sleep(0.5)
    return True


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
    print(f"  URL: {page.url}")
    if "profile" not in page.url.lower():
        print("  [错误] Cookie登录失败")
        page.quit()
        raise RuntimeError("Cookie登录失败")
    print("  [OK] 登录成功")
    return page


def upload_cover(page, cover_paths):
    """上传封面图（三图模式）"""
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("  [封面] 无有效封面图文件")
        return

    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)

    # 选择三图模式
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
        print(f"    封面{ci+1}: {os.path.basename(cf)}...")
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
            print(f"    封面{ci+1}: ✓")
        else:
            # 兜底: 尝试所有file input
            for inp in page.eles('tag:input@type=file'):
                try:
                    inp.input(cf)
                    time.sleep(3)
                    print(f"    封面{ci+1}: ✓ (兜底)")
                    break
                except:
                    continue
            else:
                print(f"    封面{ci+1}: 未找到上传控件")


def main():
    # 加载清单
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        art = json.load(f)[0]
    title = art["title"][:30]
    cover_files = art["cover_files"]
    html_path = art["html_file"]
    print(f"文章: {title}")

    # 读取HTML，提取正文
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

    # 启动浏览器
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

    # === 第1步：填标题（DrissionPage原生输入） ===
    print("\n[2] 填标题...")
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

    # 等待标题自动保存
    if not wait_for_save(page, timeout=20):
        print("  [WARN] 标题保存未确认，触发保存...")
        trigger_save_via_title(page)
        wait_for_save(page, timeout=15)

    # === 第2步：填正文（JS paste + 编辑器输入触发） ===
    print("\n[3] 填正文...")
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

    # 关键：在编辑器里输入一个空格再删除，触发React onChange
    print("  触发编辑器输入事件...")
    trigger_save_via_editor(page)
    time.sleep(1)

    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    print(f"  正文: {chars}字, {imgs}张图片")

    # 等待正文保存
    if not wait_for_save(page, timeout=20):
        print("  [WARN] 正文保存未确认，触发保存...")
        trigger_save_via_title(page)
        wait_for_save(page, timeout=15)

    # === 第3步：上传封面 ===
    print("\n[4] 上传封面...")
    upload_cover(page, cover_files)

    # 触发保存
    trigger_save_via_title(page)
    wait_for_save(page, timeout=20)

    # === 验证 ===
    print("\n[5] 验证草稿箱...")
    page.get("https://mp.toutiao.com/profile_v4/manage/draft")
    time.sleep(5)
    text = page.run_js("return document.body.innerText;")
    if title[:8] in text:
        idx = text.find(title[:8])
        print(f"[SUCCESS] 文章已在草稿箱中！")
        print(f"  {text[idx:idx+120]}")
    else:
        print("[CHECK] 未在草稿箱中找到文章")
        print(f"  草稿箱内容: {text[:500]}")
    
    page.quit()
    print("\nDONE")


if __name__ == "__main__":
    main()