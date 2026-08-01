# -*- coding: utf-8 -*-
"""调试封面图区域的DOM结构"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TTWZ_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(TTWZ_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

# 加载Cookie
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
try:
    three_radio = page.ele('tag:input@type=radio@value=3', timeout=3)
    if three_radio:
        three_radio.click()
        time.sleep(2)
        print("[OK] 已选择三图模式（radio）")
    else:
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
        if result == 'clicked':
            time.sleep(2)
            print("[OK] 已选择三图模式（JS）")
except Exception as e:
    print(f"选择三图模式失败: {e}")

time.sleep(2)

# 探查封面区域DOM
result = page.run_js("""
var results = [];

// 1. 查找所有包含 "cover" 的class
var allElements = document.querySelectorAll('*');
var coverClasses = new Set();
for (var i = 0; i < allElements.length; i++) {
    var cls = allElements[i].className;
    if (typeof cls === 'string' && cls.toLowerCase().indexOf('cover') !== -1) {
        coverClasses.add(cls);
    }
}
results.push('=== 包含cover的class ===');
coverClasses.forEach(function(c) { results.push(c); });

// 2. 查找封面区域的所有input[type=file]
var fileInputs = document.querySelectorAll('input[type=file]');
results.push('\\n=== file inputs ===');
results.push('count: ' + fileInputs.length);
for (var i = 0; i < fileInputs.length; i++) {
    var inp = fileInputs[i];
    var parent = inp.parentElement;
    var parentClass = parent ? (parent.className || 'no-class') : 'no-parent';
    var rect = inp.getBoundingClientRect();
    results.push('input[' + i + ']: parent.class=' + parentClass + 
                 ' visible=' + (rect.width > 0 && rect.height > 0) +
                 ' accept=' + (inp.accept || 'none'));
}

// 3. 查找所有包含 "添加" 或 "上传" 文本的元素
var allElems = document.querySelectorAll('*');
results.push('\\n=== 包含添加/上传文本的元素 ===');
for (var i = 0; i < allElems.length; i++) {
    var el = allElems[i];
    if (el.children.length === 0) {
        var text = el.textContent || '';
        if (text.indexOf('添加') !== -1 || text.indexOf('上传') !== -1) {
            var rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                results.push('tag=' + el.tagName + ' class=' + (el.className || 'none') + 
                             ' text=' + text.substring(0, 30) +
                             ' visible=' + (rect.width > 0 && rect.height > 0));
            }
        }
    }
}

// 4. 查找封面区域附近的HTML结构
results.push('\\n=== 封面区域附近HTML ===');
var coverSection = document.querySelector('.article-cover-wrapper, .cover-wrapper, [class*=cover]');
if (coverSection) {
    results.push(coverSection.outerHTML.substring(0, 2000));
} else {
    // 尝试找发布页面中封面相关区域
    var body = document.body.innerHTML;
    var coverIdx = body.indexOf('封面');
    if (coverIdx !== -1) {
        var snippet = body.substring(Math.max(0, coverIdx - 200), coverIdx + 2000);
        results.push(snippet.substring(0, 3000));
    } else {
        results.push('未找到封面相关区域');
    }
}

return results.join('\\n');
""")

print(result)

page.quit()