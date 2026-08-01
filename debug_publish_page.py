# -*- coding: utf-8 -*-
"""快速调试：检查发布页面结构"""
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
print(f"Publish URL: {page.url}")

# Close any popup
try:
    close_btn = page.ele("text:关闭", timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# Check for ProseMirror
pm_count = page.run_js("return document.querySelectorAll('.ProseMirror').length;")
print(f"ProseMirror: {pm_count}")

# Check for title textarea
title_count = page.run_js("return document.querySelectorAll('textarea[placeholder*=\"文章标题\"]').length;")
print(f"Title textarea: {title_count}")

# Check for any textarea
all_textareas = page.run_js("""
var tas = document.querySelectorAll('textarea');
var result = [];
for (var i = 0; i < tas.length; i++) {
    result.push('textarea[' + i + '] placeholder=' + (tas[i].placeholder || 'none') + 
        ' visible=' + (tas[i].getBoundingClientRect().width > 0));
}
return result.join('\\n') || 'no textareas';
""")
print(f"All textareas:\n{all_textareas}")

# Check for editor-related elements
editor_info = page.run_js("""
var selectors = ['.ProseMirror', '[class*="editor"]', '[class*="Editor"]', 
    '[contenteditable="true"]', '.ql-editor', '.ace-editor', '[role="textbox"]'];
var result = [];
for (var i = 0; i < selectors.length; i++) {
    var els = document.querySelectorAll(selectors[i]);
    if (els.length > 0) {
        result.push(selectors[i] + ': ' + els.length + ' found');
        for (var j = 0; j < Math.min(els.length, 2); j++) {
            var rect = els[j].getBoundingClientRect();
            result.push('  tag=' + els[j].tagName + ' visible=' + (rect.width > 0));
        }
    }
}
return result.join('\\n') || 'none';
""")
print(f"Editor elements:\n{editor_info}")

# Check page title
page_title = page.run_js("return document.title;")
print(f"Page title: {page_title}")

# Check if there's a redirect or different page
body_text = page.run_js("return document.body.innerText.substring(0, 500);")
print(f"Body text (first 500):\n{body_text}")

page.quit()
print("DONE")