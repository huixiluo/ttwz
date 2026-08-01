# -*- coding: utf-8 -*-
"""测试头条号编辑器图片上传流程"""
import os, json, time, sys, base64, re
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

log("测试图片上传流程...")

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

# 打开发布页
page.get(PUBLISH_URL)
time.sleep(5)

# 关闭弹窗
try:
    close_btn = page.ele('text:关闭', timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# 先填标题和正文（让编辑器激活）
log("填入测试内容...")
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if title_el:
    title_el.input("测试图片上传")
    log("标题已填")

# 点击正文区域激活编辑器
editor = page.ele('.ProseMirror', timeout=5)
if editor:
    editor.click()
    time.sleep(1)

# 尝试方法1: 点击工具栏中的图片按钮
log("\n方法1: 点击图片按钮...")
img_btn = page.ele('.syl-toolbar-tool.image', timeout=5)
if img_btn:
    log(f"找到图片按钮: class={img_btn.attr('class')}")
    img_btn.click()
    time.sleep(2)
    
    # 检查是否有file input出现
    file_inputs = page.run_js("""
    const inputs = document.querySelectorAll('input[type="file"]');
    return inputs.length;
    """)
    log(f"点击后file inputs数量: {file_inputs}")
    
    if file_inputs and int(file_inputs) > 0:
        # 找到file input并上传
        log("找到file input，尝试上传...")
        test_img = os.path.join(BASE_DIR, "output", "covers", "娱乐_1_20260729_021713_cover_1.jpg")
        if os.path.exists(test_img):
            # 尝试通过JS找到file input
            file_input = page.ele('tag:input@type=file', timeout=5)
            if file_input:
                file_input.input(test_img)
                time.sleep(3)
                log("图片上传完成")
            else:
                log("找不到file input元素")
        else:
            log(f"测试图片不存在: {test_img}")
    else:
        log("点击后没有file input出现")
else:
    log("找不到图片按钮")

# 方法2: 尝试通过拖拽区域上传
log("\n方法2: 查找拖拽上传区域...")
drop_zones = page.run_js("""
const zones = document.querySelectorAll('[class*="drop"], [class*="drag"], [class*="upload-area"]');
let result = [];
zones.forEach(z => result.push({tag: z.tagName, class: z.className}));
return JSON.stringify(result);
""")
log(f"拖拽区域: {drop_zones}")

# 方法3: 尝试模拟粘贴图片
log("\n方法3: 尝试粘贴图片...")
test_img = os.path.join(BASE_DIR, "output", "covers", "娱乐_1_20260729_021713_cover_1.jpg")
if os.path.exists(test_img):
    with open(test_img, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    # 尝试通过fetch + blob方式插入图片
    paste_js = f"""
    (async function() {{
        const editor = document.querySelector('.ProseMirror');
        if (!editor) return 'no editor';
        
        // 从base64创建blob
        const byteChars = atob('{img_b64[:500]}');
        return 'tried, img too large for inline test';
    }})()
    """
    result = page.run_js(paste_js)
    log(f"方法3结果: {result}")

# 方法4: 查找所有按钮并列出详细信息
log("\n方法4: 工具栏按钮详情...")
all_btns = page.run_js("""
const btns = document.querySelectorAll('.syl-toolbar-button');
let result = [];
btns.forEach((b, i) => {
    const svg = b.querySelector('svg');
    const icon = b.querySelector('[class*="icon"]');
    result.push({
        index: i,
        title: b.title || b.getAttribute('aria-label') || '',
        hasSvg: !!svg,
        className: b.className,
        innerHTML: b.innerHTML.substring(0, 100)
    });
});
return JSON.stringify(result);
""")
log(f"按钮详情: {all_btns}")

# 方法5: 尝试点击图片按钮并监听DOM变化
log("\n方法5: 监听文件选择...")
# 设置文件选择监听
page.run_js("""
window.__fileInputDetected = false;
const observer = new MutationObserver((mutations) => {
    mutations.forEach(m => {
        m.addedNodes.forEach(node => {
            if (node.tagName === 'INPUT' && node.type === 'file') {
                window.__fileInputDetected = true;
                window.__lastFileInput = node;
            }
        });
    });
});
observer.observe(document.body, {childList: true, subtree: true});
""")

# 再次点击图片按钮
img_btn = page.ele('.syl-toolbar-tool.image', timeout=5)
if img_btn:
    img_btn.click()
    time.sleep(2)
    detected = page.run_js("return window.__fileInputDetected")
    log(f"检测到file input: {detected}")
    if detected:
        file_input_info = page.run_js("""
        if (window.__lastFileInput) {
            return {
                accept: window.__lastFileInput.accept,
                multiple: window.__lastFileInput.multiple,
                className: window.__lastFileInput.className,
                parent: window.__lastFileInput.parentElement ? window.__lastFileInput.parentElement.className : ''
            };
        }
        return 'no input';
        """)
        log(f"File input详情: {file_input_info}")

page.quit()
log("完成")