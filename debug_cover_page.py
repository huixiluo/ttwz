# -*- coding: utf-8 -*-
"""调试：检查当前头条号发布页面结构，特别是封面图区域"""
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

# Check cover area
print("\n=== 封面区域调试 ===")

# 1. Check for article-cover-add
add_count = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
print(f".article-cover-add: {add_count}")

# 2. Check for any cover-related elements
cover_info = page.run_js("""
var result = [];
var selectors = [
    '.article-cover-add', '.article-cover-images-wrap', '.article-cover-images',
    '.cover-image', '.cover-upload', '.cover-add', '.upload-cover',
    '[class*="cover"]', '[class*="Cover"]'
];
for (var i = 0; i < selectors.length; i++) {
    var els = document.querySelectorAll(selectors[i]);
    if (els.length > 0) {
        result.push(selectors[i] + ': ' + els.length + ' found');
        for (var j = 0; j < Math.min(els.length, 3); j++) {
            var el = els[j];
            var rect = el.getBoundingClientRect();
            result.push('  [' + j + '] tag=' + el.tagName + 
                ' class="' + (el.className || '').substring(0, 80) + '"' +
                ' visible=' + (rect.width > 0 && rect.height > 0) +
                ' text="' + (el.textContent || '').trim().substring(0, 30) + '"');
        }
    }
}
return result.join('\\n');
""")
print(f"Cover elements:\n{cover_info}")

# 3. Check three-image mode radio
radio_info = page.run_js("""
var radios = document.querySelectorAll('input[type="radio"]');
var result = [];
for (var i = 0; i < radios.length; i++) {
    var r = radios[i];
    result.push('radio[' + i + '] value=' + r.value + ' checked=' + r.checked + 
        ' label=' + (r.parentElement ? r.parentElement.textContent.trim().substring(0, 30) : ''));
}
return result.join('\\n') || 'no radios';
""")
print(f"\nRadio buttons:\n{radio_info}")

# 4. Check for file inputs near cover area
file_info = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    result.push('file[' + i + '] accept=' + (inp.accept || 'none') + 
        ' visible=' + (inp.getBoundingClientRect().width > 0));
}
return result.join('\\n') || 'no file inputs';
""")
print(f"\nFile inputs:\n{file_info}")

# 5. Try clicking three-image label
print("\n=== 尝试点击三图模式 ===")
click_result = page.run_js("""
var labels = document.querySelectorAll('label');
for (var i = 0; i < labels.length; i++) {
    var text = labels[i].textContent || '';
    if (text.indexOf('三图') !== -1) {
        labels[i].click();
        return 'clicked label: ' + text.substring(0, 30);
    }
}
// Try clicking radio directly
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    if (radios[i].value === '3') {
        radios[i].click();
        radios[i].checked = true;
        radios[i].dispatchEvent(new Event('change', {bubbles: true}));
        return 'clicked radio value=3';
    }
}
return 'not found';
""")
print(f"Click result: {click_result}")
time.sleep(3)

# 6. Check again after click
add_count2 = page.run_js("return document.querySelectorAll('.article-cover-add').length;")
print(f".article-cover-add after click: {add_count2}")

# Re-check all cover elements
cover_info2 = page.run_js("""
var result = [];
var all = document.querySelectorAll('[class*="cover"], [class*="Cover"], [class*="upload"]');
for (var i = 0; i < Math.min(all.length, 20); i++) {
    var el = all[i];
    var rect = el.getBoundingClientRect();
    result.push('tag=' + el.tagName + ' class="' + (el.className || '') + '"' +
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' text="' + (el.textContent || '').trim().substring(0, 40) + '"');
}
return result.join('\\n') || 'none';
""")
print(f"\nAll cover/upload elements after click:\n{cover_info2}")

# 7. Screenshot the page
page.save_screenshot(os.path.join(BASE_DIR, "debug_cover_page.png"))
print("\nScreenshot saved: debug_cover_page.png")

page.quit()
print("DONE")