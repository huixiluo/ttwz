# -*- coding: utf-8 -*-
"""调试封面图上传 - 使用DrissionPage原生点击"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

# Login
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
print(f"Login: {page.url}")

# Go to publish page
page.get(PUBLISH_URL)
time.sleep(5)

# Close any popup
try:
    close_btn = page.ele("text:关闭", timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# Click three-image mode
print("\n=== 点击三图模式 ===")
page.run_js("""
var labels = document.querySelectorAll('label');
for (var i = 0; i < labels.length; i++) {
    if ((labels[i].textContent || '').indexOf('三图') !== -1) {
        labels[i].click();
        break;
    }
}
""")
time.sleep(3)

# Check existing file inputs before clicking add
before = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push('file[' + i + '] accept=' + (inp.accept || 'none') + 
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' w=' + rect.width + ' h=' + rect.height +
        ' style=' + (inp.getAttribute('style') || 'none'));
}
return result.join('\\n') || 'no file inputs';
""")
print(f"Before click add: {before}")

# Click add button using DrissionPage native click
print("\n=== 点击 .article-cover-add ===")
add_btn = page.ele('.article-cover-add', timeout=5)
if add_btn:
    print(f"Found add button: {add_btn}")
    add_btn.click()
    print("Clicked via DrissionPage")
else:
    print("Add button not found via DrissionPage")
    # Try JS
    page.run_js("""
    var btn = document.querySelector('.article-cover-add');
    if (btn) {
        btn.click();
        console.log('clicked via JS .click()');
    }
    """)
    print("Clicked via JS .click()")

time.sleep(3)

# Check file inputs after click
after = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push('file[' + i + '] accept=' + (inp.accept || 'none') + 
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' w=' + rect.width + ' h=' + rect.height +
        ' style=' + (inp.getAttribute('style') || 'none'));
}
return result.join('\\n') || 'no file inputs';
""")
print(f"After click add: {after}")

# Check all inputs (not just file)
all_inputs = page.run_js("""
var inputs = document.querySelectorAll('input');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push('input[' + i + '] type=' + inp.type + 
        ' accept=' + (inp.accept || 'none') + 
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' class=' + (inp.className || 'none').substring(0, 50));
}
return result.join('\\n') || 'no inputs';
""")
print(f"\nAll inputs after click:\n{all_inputs}")

# Check if there's a hidden input inside the add button
add_html = page.run_js("""
var btn = document.querySelector('.article-cover-add');
if (!btn) return 'no btn';
return 'innerHTML: ' + btn.innerHTML.substring(0, 500) + 
    '\\nchildren: ' + btn.children.length +
    '\\nouterHTML: ' + btn.outerHTML.substring(0, 500);
""")
print(f"\nAdd button HTML:\n{add_html}")

# Try clicking with dispatchEvent
print("\n=== Try dispatchEvent click ===")
page.run_js("""
var btn = document.querySelector('.article-cover-add');
if (btn) {
    ['mousedown', 'mouseup', 'click'].forEach(function(evtType) {
        btn.dispatchEvent(new MouseEvent(evtType, {bubbles: true, cancelable: true, view: window}));
    });
    console.log('dispatchEvent done');
}
""")
time.sleep(3)

after2 = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push('file[' + i + '] accept=' + (inp.accept || 'none') + 
        ' visible=' + (rect.width > 0 && rect.height > 0));
}
return result.join('\\n') || 'no file inputs';
""")
print(f"After dispatchEvent: {after2}")

# Check if cover-images-wrap has changed
wrap_html = page.run_js("""
var wrap = document.querySelector('.article-cover-images-wrap');
if (!wrap) return 'no wrap';
return 'innerHTML: ' + wrap.innerHTML.substring(0, 1000);
""")
print(f"\nCover images wrap HTML:\n{wrap_html}")

page.quit()
print("\nDONE")