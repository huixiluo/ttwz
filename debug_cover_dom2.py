# -*- coding: utf-8 -*-
"""调试封面图区域的DOM结构 - 更深入探索"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

TTWZ_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(TTWZ_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

print("[1] 启动浏览器...")
co = ChromiumOptions()
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass

page.get(PUBLISH_URL)
time.sleep(5)

# 先选择三图模式
result = page.run_js(
    "var labels = document.querySelectorAll('label');\n"
    "for (var i = 0; i < labels.length; i++) {\n"
    "  if (labels[i].textContent.indexOf('三图') !== -1) {\n"
    "    labels[i].click();\n"
    "    return 'clicked';\n"
    "  }\n"
    "}\n"
    "return 'not_found';"
)
print(f"选择三图模式: {result}")
time.sleep(3)

# 深入探查封面区域
result = page.run_js("""
var results = [];

// 1. 查找 .article-cover-images-wrap 下的所有子元素
var wrap = document.querySelector('.article-cover-images-wrap');
if (wrap) {
    results.push('=== .article-cover-images-wrap 子元素 ===');
    results.push('children count: ' + wrap.children.length);
    for (var i = 0; i < wrap.children.length; i++) {
        var child = wrap.children[i];
        results.push('child[' + i + ']: tag=' + child.tagName + ' class=' + child.className + 
                     ' innerHTML_len=' + child.innerHTML.length);
    }
    results.push('\\n=== wrap innerHTML (前3000字符) ===');
    results.push(wrap.innerHTML.substring(0, 3000));
} else {
    results.push('.article-cover-images-wrap 未找到!');
}

// 2. 查找 .article-cover-images 下的元素
var images = document.querySelector('.article-cover-images');
if (images) {
    results.push('\\n=== .article-cover-images 子元素 ===');
    results.push('children count: ' + images.children.length);
    for (var i = 0; i < images.children.length; i++) {
        var child = images.children[i];
        var rect = child.getBoundingClientRect();
        results.push('child[' + i + ']: tag=' + child.tagName + ' class=' + child.className + 
                     ' w=' + rect.width + ' h=' + rect.height);
    }
}

// 3. 查找所有 .article-cover-add
var adds = document.querySelectorAll('.article-cover-add');
results.push('\\n=== .article-cover-add ===');
results.push('querySelectorAll count: ' + adds.length);
for (var i = 0; i < adds.length; i++) {
    var rect = adds[i].getBoundingClientRect();
    var parent = adds[i].parentElement;
    results.push('add[' + i + ']: tag=' + adds[i].tagName + 
                 ' w=' + rect.width + ' h=' + rect.height +
                 ' parent.class=' + (parent ? parent.className : 'none'));
}

// 4. 查找封面区域中所有可点击的元素
results.push('\\n=== 封面区域可点击元素（含onclick或role=button） ===');
var allInCover = document.querySelectorAll('.article-cover-images-wrap *, .article-cover-images *, .article-cover-radio-group *');
for (var i = 0; i < allInCover.length; i++) {
    var el = allInCover[i];
    var rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && (el.onclick || el.getAttribute('role') === 'button' || el.tagName === 'BUTTON' || el.tagName === 'INPUT')) {
        results.push('tag=' + el.tagName + ' class=' + (el.className || 'none') + 
                     ' w=' + rect.width + ' h=' + rect.height +
                     ' text=' + (el.textContent || '').substring(0, 20));
    }
}

// 5. 查找所有div/span中的文本包含"添加"且在封面区域
results.push('\\n=== 封面区域中所有叶节点 ===');
var coverArea = document.querySelector('.article-cover-images-wrap');
if (coverArea) {
    var leaves = coverArea.querySelectorAll('*');
    for (var i = 0; i < leaves.length; i++) {
        var el = leaves[i];
        if (el.children.length === 0 && el.textContent && el.textContent.trim()) {
            var rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                results.push('tag=' + el.tagName + ' class=' + (el.className || 'none') + 
                             ' text=' + el.textContent.trim().substring(0, 30) +
                             ' w=' + rect.width + ' h=' + rect.height);
            }
        }
    }
}

return results.join('\\n');
""")

print(result)

page.quit()