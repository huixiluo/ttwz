# -*- coding: utf-8 -*-
"""探索头条号编辑器，找到图片上传按钮"""
import os, json, time, sys
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

log("探索头条号编辑器工具栏...")

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

# 登录
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
page.get("https://mp.toutiao.com")
time.sleep(2)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)

log(f"登录后URL: {page.url}")
if "profile" not in page.url.lower():
    log("登录失败")
    page.quit()
    sys.exit(1)

# 打开发布页
page.get(PUBLISH_URL)
time.sleep(5)
log(f"发布页URL: {page.url}")

# 关闭弹窗
try:
    close_btn = page.ele('text:关闭', timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 探索工具栏
log("\n--- 工具栏元素 ---")
# 查找所有按钮
try:
    buttons = page.run_js("""
    const toolbar = document.querySelector('.editor-toolbar') || document.querySelector('.toolbar') || document.querySelector('[class*="toolbar"]');
    if (toolbar) {
        const btns = toolbar.querySelectorAll('button, [role="button"], span, div[class*="icon"]');
        let result = [];
        btns.forEach((b, i) => {
            result.push({
                index: i,
                tag: b.tagName,
                class: b.className,
                title: b.title || b.getAttribute('aria-label') || '',
                text: b.innerText ? b.innerText.substring(0, 20) : ''
            });
        });
        return JSON.stringify(result);
    }
    return 'no toolbar';
    """)
    log(f"工具栏: {buttons[:500]}")

    # 查找所有file input
    file_inputs = page.run_js("""
    const inputs = document.querySelectorAll('input[type="file"]');
    let result = [];
    inputs.forEach((inp, i) => {
        result.push({
            index: i,
            accept: inp.accept,
            class: inp.className,
            parent_class: inp.parentElement ? inp.parentElement.className : ''
        });
    });
    return JSON.stringify(result);
    """)
    log(f"File inputs: {file_inputs}")

    # 查找所有带upload相关class的元素
    upload_els = page.run_js("""
    const els = document.querySelectorAll('[class*="upload"], [class*="image"], [class*="img"], [class*="picture"]');
    let result = [];
    els.forEach(el => {
        result.push({tag: el.tagName, class: el.className, text: el.innerText ? el.innerText.substring(0, 30) : ''});
    });
    return JSON.stringify(result.slice(0, 20));
    """)
    log(f"Upload相关元素: {upload_els}")

    # 检查ProseMirror的可用操作
    editor_info = page.run_js("""
    const editor = document.querySelector('.ProseMirror');
    if (editor) {
        return {
            hasEditor: true,
            childCount: editor.childElementCount,
            firstChild: editor.firstElementChild ? editor.firstElementChild.tagName : 'none'
        };
    }
    return {hasEditor: false};
    """)
    log(f"编辑器信息: {editor_info}")

except Exception as e:
    log(f"探索出错: {e}")

page.quit()
log("完成")