# -*- coding: utf-8 -*-
"""直接检查封面图区域的DOM结构"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

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

# 深入检查封面区域
cover_html = page.run_js("""
var result = [];
var cover = document.querySelector('.article-cover');
if (!cover) { return 'article-cover not found'; }

// 整个封面区域的HTML
result.push('=== article-cover HTML ===');
result.push(cover.innerHTML.substring(0, 5000));

// article-cover-add 的HTML
var adds = document.querySelectorAll('.article-cover-add');
result.push('\\n=== article-cover-add count: ' + adds.length + ' ===');
for (var i = 0; i < adds.length; i++) {
    var add = adds[i];
    result.push('add[' + i + ']: tag=' + add.tagName + ' class=' + add.className);
    result.push('  innerHTML=' + add.innerHTML.substring(0, 500));
    result.push('  outerHTML=' + add.outerHTML.substring(0, 500));
    // 检查父元素
    var parent = add.parentElement;
    if (parent) {
        result.push('  parent: tag=' + parent.tagName + ' class=' + parent.className);
        result.push('  parent.innerHTML=' + parent.innerHTML.substring(0, 1000));
    }
    // 检查兄弟元素
    var siblings = add.parentElement ? add.parentElement.children : [];
    result.push('  siblings count: ' + siblings.length);
    for (var j = 0; j < siblings.length; j++) {
        var s = siblings[j];
        result.push('  sibling[' + j + ']: tag=' + s.tagName + ' class=' + s.className + ' text=' + (s.textContent || '').trim().substring(0, 30));
    }
}

// 查找所有input[type=file]并检查它们的位置
result.push('\\n=== All file inputs ===');
var allInputs = document.querySelectorAll('input[type="file"]');
for (var i = 0; i < allInputs.length; i++) {
    var inp = allInputs[i];
    var rect = inp.getBoundingClientRect();
    // 找到祖先链
    var ancestors = [];
    var el = inp.parentElement;
    for (var d = 0; d < 10 && el; d++) {
        ancestors.push(el.tagName + '.' + (el.className || ''));
        el = el.parentElement;
    }
    result.push('input[' + i + ']: accept=' + (inp.accept || 'none') + 
                ' visible=' + (rect.width > 0 && rect.height > 0) +
                ' size=' + rect.width + 'x' + rect.height +
                '\\n  ancestors: ' + ancestors.join(' > '));
}

// 检查article-cover-add是否包含或关联file input
result.push('\\n=== article-cover-images 结构 ===');
var images = document.querySelector('.article-cover-images');
if (images) {
    result.push('innerHTML=' + images.innerHTML.substring(0, 3000));
    // 所有子元素
    for (var i = 0; i < images.children.length; i++) {
        var child = images.children[i];
        result.push('child[' + i + ']: tag=' + child.tagName + ' class=' + child.className);
    }
}

return result.join('\\n');
""")
print(cover_html, flush=True)

# 尝试直接在article-cover-add区域找file input
print("\n\n=== 尝试点击add后立即查找file input ===", flush=True)
# 先记录当前所有file input
before = page.run_js("return document.querySelectorAll('input[type=\"file\"]').length;")
print(f"点击前file input数量: {before}", flush=True)

# 点击add
page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) { add.click(); }
""")
time.sleep(0.5)

# 立即检查
after = page.run_js("return document.querySelectorAll('input[type=\"file\"]').length;")
print(f"点击后0.5s file input数量: {after}", flush=True)

time.sleep(1)
after2 = page.run_js("return document.querySelectorAll('input[type=\"file\"]').length;")
print(f"点击后1.5s file input数量: {after2}", flush=True)

# 关闭可能弹出的任何东西
page.run_js("""
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { try { mask.click(); } catch(e) {} }
""")

page.quit()
print("\nDONE", flush=True)