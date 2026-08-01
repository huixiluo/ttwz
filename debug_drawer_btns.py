# -*- coding: utf-8 -*-
"""调试抽屉内的按钮：上传文件后需要点击确认按钮"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
cover_files = art["cover_files"]
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if not valid:
    print("No valid cover files!")
    exit(1)

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

# 选三图模式
page.run_js("window.scrollTo(0, 0);")
time.sleep(1)
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
print("已选三图模式", flush=True)

# 打开抽屉
page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) { add.click(); }
""")
time.sleep(3)
print("抽屉已打开", flush=True)

# 探索抽屉内的所有按钮和可点击元素
drawer_info = page.run_js("""
var result = [];
var drawer = document.querySelector('.byte-drawer-wrapper');
if (!drawer) { return 'drawer not found'; }

// 所有按钮
result.push('=== 按钮 ===');
var buttons = drawer.querySelectorAll('button');
for (var i = 0; i < buttons.length; i++) {
    var b = buttons[i];
    result.push('button[' + i + ']: text="' + (b.textContent || '').trim() + '" class="' + b.className + '"');
}

// 所有span
result.push('\\n=== SPAN ===');
var spans = drawer.querySelectorAll('span');
for (var i = 0; i < spans.length; i++) {
    var s = spans[i];
    var text = (s.textContent || '').trim();
    if (text) {
        result.push('span[' + i + ']: text="' + text.substring(0, 30) + '" class="' + s.className + '"');
    }
}

// 所有有click事件的元素
result.push('\\n=== 可点击元素 ===');
var all = drawer.querySelectorAll('*');
for (var i = 0; i < all.length; i++) {
    var el = all[i];
    var text = (el.textContent || '').trim();
    if (text && (el.onclick || el.getAttribute('role') === 'button' || el.tagName === 'BUTTON' || el.tagName === 'A')) {
        result.push('tag=' + el.tagName + ' text="' + text.substring(0, 30) + '" class="' + (el.className || '') + '"');
    }
}

// 所有class包含btn或button的元素
result.push('\\n=== btn/button class ===');
var btnEls = drawer.querySelectorAll('[class*="btn"], [class*="button"]');
for (var i = 0; i < btnEls.length; i++) {
    var el = btnEls[i];
    var text = (el.textContent || '').trim();
    result.push('tag=' + el.tagName + ' text="' + text.substring(0, 30) + '" class="' + (el.className || '') + '"');
}

// 抽屉底部区域
result.push('\\n=== 抽屉footer ===');
var footer = drawer.querySelector('.byte-drawer-footer, [class*="footer"]');
if (footer) {
    result.push('footer found, html=' + footer.innerHTML.substring(0, 500));
} else {
    // 找最后一个子元素
    var children = drawer.children;
    if (children.length > 0) {
        var last = children[children.length - 1];
        result.push('last child: tag=' + last.tagName + ' class=' + last.className + ' html=' + last.innerHTML.substring(0, 500));
    }
}

return result.join('\\n');
""")
print(drawer_info, flush=True)

# 上传文件并查找确认按钮
print("\n上传文件后查找确认按钮...", flush=True)
# 上传文件
all_inputs = page.eles('tag:input@type=file')
for inp in all_inputs:
    try:
        accept = inp.attr('accept') or ''
        if 'image' in accept:
            inp.input(valid[0])
            time.sleep(3)
            print("  文件已上传", flush=True)
            break
    except:
        pass

time.sleep(2)

# 再次检查抽屉内的按钮
drawer_info2 = page.run_js("""
var result = [];
var drawer = document.querySelector('.byte-drawer-wrapper');
if (!drawer) { return 'drawer not found'; }

// 所有按钮
result.push('=== 上传后按钮 ===');
var buttons = drawer.querySelectorAll('button');
for (var i = 0; i < buttons.length; i++) {
    var b = buttons[i];
    var disabled = b.disabled ? ' [DISABLED]' : ' [ENABLED]';
    result.push('button[' + i + ']: text="' + (b.textContent || '').trim() + '" class="' + b.className + '"' + disabled);
}

// 所有span
result.push('\\n=== 上传后SPAN ===');
var spans = drawer.querySelectorAll('span');
for (var i = 0; i < spans.length; i++) {
    var s = spans[i];
    var text = (s.textContent || '').trim();
    if (text) {
        result.push('span[' + i + ']: text="' + text.substring(0, 30) + '" class="' + s.className + '"');
    }
}

// 所有class包含btn或button的元素
result.push('\\n=== 上传后btn/button class ===');
var btnEls = drawer.querySelectorAll('[class*="btn"], [class*="button"]');
for (var i = 0; i < btnEls.length; i++) {
    var el = btnEls[i];
    var text = (el.textContent || '').trim();
    var disabled = el.disabled ? ' [DISABLED]' : ' [ENABLED]';
    result.push('tag=' + el.tagName + ' text="' + text.substring(0, 30) + '" class="' + (el.className || '') + '"' + disabled);
}

return result.join('\\n');
""")
print(drawer_info2, flush=True)

page.quit()
print("\nDONE", flush=True)