# -*- coding: utf-8 -*-
"""删除旧草稿，释放草稿箱空间"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

# 要保留的9篇文章标题关键词
KEEP_TITLES = [
    "网红揭恶毒闺蜜",
    "神仙姐姐下沉市场",
    "复旦王水牛走红",
    "进球悼念故友",
    "孙颖莎登青年榜",
    "C罗表情包回应婚礼",
    "上海迎台风天",
    "拜登癌症扩散",
    "杭州地铁引热议",
]

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

print("[1] 启动浏览器...")
co = ChromiumOptions()
co.set_browser_path(CHROME_PATH)
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--window-size=1920,1080")
co.set_argument("--disable-background-timer-throttling")
co.set_argument("--disable-backgrounding-occluded-windows")
co.set_argument("--disable-renderer-backgrounding")
co.set_address("127.0.0.1:9227")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_delete"))

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass

page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(8)
print(f"URL: {page.url}")

# 滚动加载
for i in range(3):
    page.run_js("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

# 获取草稿列表 - 每个草稿项的结构
drafts_info = page.run_js("""
var results = [];
// 查找所有包含"编辑删除"的草稿项
var allElements = document.querySelectorAll('*');
var draftItems = [];

// 通过查找"编辑删除"按钮来定位草稿项
var editDeleteBtns = [];
for (var el of allElements) {
    if (el.children.length === 0 && el.textContent.trim() === '编辑删除') {
        editDeleteBtns.push(el);
    }
}

results.push('找到编辑删除按钮数: ' + editDeleteBtns.length);

// 获取每个草稿的标题
for (var i = 0; i < editDeleteBtns.length; i++) {
    var btn = editDeleteBtns[i];
    // 向上找到草稿容器
    var container = btn.parentElement;
    while (container && container.children.length < 2) {
        container = container.parentElement;
    }
    if (container) {
        var titleEl = container.querySelector('a, span, div');
        var title = '';
        // 尝试获取标题文本
        var text = container.innerText || '';
        var lines = text.split('\\n').filter(l => l.trim());
        if (lines.length > 0) {
            title = lines[0].trim();
        }
        results.push({index: i, title: title, hasDelete: true});
    }
}

return JSON.stringify(results);
""")

print(f"\n草稿信息: {drafts_info[:2000]}")

# 尝试通过点击删除按钮来删除旧草稿
# 策略：删除最后5条旧草稿（保留最新的）
print("\n[2] 尝试删除旧草稿...")

deleted_count = 0
# 从最后一条开始删除（最旧的）
for attempt in range(5):
    print(f"\n  删除第 {attempt+1} 条旧草稿...")
    
    # 找到"编辑删除"按钮并点击
    clicked = page.run_js("""
// 找到所有"删除"文本的元素
var allElements = document.querySelectorAll('*');
var deleteBtns = [];
for (var el of allElements) {
    if (el.children.length === 0 && el.textContent.trim() === '删除') {
        deleteBtns.push(el);
    }
}

if (deleteBtns.length === 0) return 'no_delete_btn';

// 点击最后一个删除按钮（最旧的草稿）
var lastBtn = deleteBtns[deleteBtns.length - 1];
lastBtn.click();
return 'clicked';
""")
    
    if clicked != 'clicked':
        print(f"  未找到删除按钮: {clicked}")
        break
    
    time.sleep(2)
    
    # 查找确认删除按钮
    confirmed = page.run_js("""
// 查找确认按钮（通常是"确定"或"确认删除"）
var allElements = document.querySelectorAll('button, a, span, div');
for (var el of allElements) {
    var text = el.textContent.trim();
    if ((text === '确定' || text === '确认删除' || text === '确认') && el.offsetParent !== null) {
        el.click();
        return 'confirmed: ' + text;
    }
}
return 'no_confirm';
""")
    
    print(f"  确认: {confirmed}")
    
    if 'confirmed' in str(confirmed):
        deleted_count += 1
        time.sleep(3)
        # 刷新页面
        page.run_js("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
    else:
        # 尝试其他方式确认
        print("  尝试查找弹窗确认按钮...")
        time.sleep(1)
        confirmed2 = page.run_js("""
// 查找弹窗中的确认按钮
var dialogs = document.querySelectorAll('.byte-modal, .modal, [role="dialog"], .ant-modal');
for (var d of dialogs) {
    var btns = d.querySelectorAll('button');
    for (var b of btns) {
        var text = b.textContent.trim();
        if (text === '确定' || text === '确认' || text === '确认删除') {
            b.click();
            return 'confirmed2: ' + text;
        }
    }
}
// 尝试查找所有可见的确定按钮
var allBtns = document.querySelectorAll('button');
for (var b of allBtns) {
    var text = b.textContent.trim();
    if ((text === '确定' || text === '确认') && b.offsetParent !== null) {
        b.click();
        return 'confirmed3: ' + text;
    }
}
return 'still_no_confirm';
""")
        print(f"  二次确认: {confirmed2}")
        if 'confirmed' in str(confirmed2):
            deleted_count += 1
            time.sleep(3)
        else:
            print("  无法确认删除，停止")
            break

print(f"\n[3] 共删除 {deleted_count} 条旧草稿")

# 刷新并检查草稿数
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(5)
draft_text = page.run_js("return document.body.innerText;") or ""
import re
count_match = re.search(r'共\s*(\d+)\s*条内容', draft_text)
if count_match:
    print(f"  当前草稿数: {count_match.group(1)}")

page.quit()
print("\nDONE")
