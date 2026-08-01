# -*- coding: utf-8 -*-
"""通过剪贴板粘贴方式插入图片到头条号编辑器"""
import os, json, time, sys, base64, subprocess, tempfile
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

def paste_image_to_editor(page, img_path):
    """通过JS模拟剪贴板粘贴图片到编辑器"""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # 使用fetch将图片作为blob粘贴到编辑器
    # 这需要将图片数据通过JS的Clipboard API写入
    paste_js = f"""
    (async function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';

        try {{
            // 将base64转为blob
            const byteString = atob('{img_b64}');
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) {{
                ia[i] = byteString.charCodeAt(i);
            }}
            const blob = new Blob([ab], {{type: 'image/jpeg'}});
            const file = new File([blob], 'image.jpg', {{type: 'image/jpeg'}});

            // 创建DataTransfer并添加文件
            const dt = new DataTransfer();
            dt.items.add(file);

            // 创建paste事件
            const pasteEvent = new ClipboardEvent('paste', {{
                bubbles: true,
                cancelable: true,
                clipboardData: dt
            }});

            // 确保编辑器有焦点
            editor.focus();

            // 分发paste事件
            editor.dispatchEvent(pasteEvent);

            return 'paste dispatched';
        }} catch(e) {{
            return 'error: ' + e.message;
        }}
    }})()
    """
    result = page.run_js(paste_js)
    time.sleep(2)
    return result

def insert_image_as_img_tag(page, img_path):
    """直接在编辑器中插入img标签（使用base64）"""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    js = f"""
    (function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';

        // 创建图片元素
        const img = document.createElement('img');
        img.src = 'data:image/jpeg;base64,{img_b64[:200]}...';
        img.style.maxWidth = '100%';
        img.style.display = 'block';
        img.style.margin = '16px auto';

        // 在光标位置插入
        const sel = window.getSelection();
        if (sel.rangeCount > 0) {{
            const range = sel.getRangeAt(0);
            range.insertNode(img);
            // 在图片后添加一个空行
            const br = document.createElement('br');
            img.parentNode.insertBefore(br, img.nextSibling);
            editor.dispatchEvent(new Event('input', {{bubbles: true}}));
            return 'inserted';
        }}
        return 'no selection';
    }})()
    """
    result = page.run_js(js)
    time.sleep(1)
    return result

log("=" * 50)
log("上传文章（使用剪贴板粘贴图片）")
log("=" * 50)

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    articles = json.load(f)

# 启动浏览器
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

if "profile" not in page.url.lower():
    log("登录失败")
    page.quit()
    sys.exit(1)

log("登录成功")

# 先测试图片插入
log("\n[测试] 先测试单篇文章的图片插入...")
page.get(PUBLISH_URL)
time.sleep(4)

# 关闭弹窗
try:
    close_btn = page.ele('text:关闭', timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 填标题
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
title_el.input("测试图片插入")
time.sleep(1)

# 点击编辑器
editor = page.ele('.ProseMirror', timeout=5)
editor.click()
time.sleep(1)

# 先写一段文字
page.run_js("""
const editor = document.querySelector('.ProseMirror');
editor.innerHTML = '<p>这是测试段落1</p><p>这是测试段落2</p>';
editor.dispatchEvent(new Event('input', {bubbles: true}));
""")
time.sleep(1)

# 测试图片插入
test_img = os.path.join(BASE_DIR, "output", "covers", "娱乐_1_20260729_021713_cover_1.jpg")
if os.path.exists(test_img):
    log(f"测试图片: {test_img}")

    # 方法1: 模拟paste事件
    log("方法1: 模拟paste事件...")
    result = paste_image_to_editor(page, test_img)
    log(f"  结果: {result}")

    # 检查是否有图片
    has_img = page.run_js("return document.querySelector('.ProseMirror img') !== null;")
    log(f"  编辑器中有图片: {has_img}")

    if has_img:
        img_count = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
        log(f"  图片数量: {img_count}")
        img_src = page.run_js("const img = document.querySelector('.ProseMirror img'); return img ? img.src.substring(0, 100) : 'none';")
        log(f"  图片src: {img_src}")

    # 如果paste不工作，尝试直接插入
    if not has_img:
        log("方法2: 直接插入img标签...")
        result2 = insert_image_as_img_tag(page, test_img)
        log(f"  结果: {result2}")
        has_img = page.run_js("return document.querySelector('.ProseMirror img') !== null;")
        log(f"  编辑器中有图片: {has_img}")

    # 检查编辑器内容
    editor_html = page.run_js("return document.querySelector('.ProseMirror').innerHTML.substring(0, 500);")
    log(f"  编辑器HTML片段: {editor_html}")

# 等待保存
time.sleep(5)
save_tip = page.ele('text:已保存', timeout=3) or page.ele('text:保存成功', timeout=3)
log(f"保存状态: {'已保存' if save_tip else '未检测到保存提示'}")

log("\n测试完成。请在头条号草稿箱检查'测试图片插入'这篇文章是否有图片。")
page.quit()