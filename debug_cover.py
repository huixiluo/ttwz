"""探测封面区域"""
import json, time
from DrissionPage import ChromiumPage, ChromiumOptions

PROJ = r"C:\Users\huixi\Documents\trae_projects\ttwz"
with open(f"{PROJ}\\toutiao_cookies.json", "r") as f:
    cookies = json.load(f)

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
    except: pass

page.get("https://mp.toutiao.com")
time.sleep(3)
print(f"Login: {page.url}")

page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(4)

# fill title
title_el = page.ele("tag:textarea", timeout=10)
if title_el:
    title_el.input("test cover")
    print("Title ok")

page.run_js(
    "var editor = document.querySelector('.ProseMirror');"
    "if (editor) { editor.innerHTML = '<p>test content</p>';"
    " editor.dispatchEvent(new Event('input', {bubbles: true})); return 'ok'; }"
    "return 'no';"
)
time.sleep(2)

# select 3-image mode
page.run_js(
    "var labels = document.querySelectorAll('label');"
    "for (var i = 0; i < labels.length; i++) {"
    "  if (labels[i].textContent.indexOf('三图') !== -1) {"
    "    labels[i].click(); return 'clicked';"
    "  }"
    "}"
    "return 'no';"
)
time.sleep(2)

# Check file inputs BEFORE click
info = page.run_js(
    "var result = [];"
    "var inputs = document.querySelectorAll('input[type=\"file\"]');"
    "for (var i = 0; i < inputs.length; i++) {"
    "  result.push({i:i, accept: inputs[i].accept, v: inputs[i].getBoundingClientRect().width > 0});"
    "}"
    "var addDiv = document.querySelector('.article-cover-add');"
    "if (addDiv) { result.push({addHTML: addDiv.innerHTML.substring(0, 300)}); }"
    "return JSON.stringify(result);"
)
print(f"BEFORE click: {info}")

# click add button
add_btn = page.ele(".article-cover-add", timeout=5)
if add_btn:
    add_btn.click()
    time.sleep(2)
    info2 = page.run_js(
        "var inputs = document.querySelectorAll('input[type=\"file\"]');"
        "var result = [];"
        "for (var i = 0; i < inputs.length; i++) {"
        "  result.push({v: inputs[i].getBoundingClientRect().width > 0, a: inputs[i].accept});"
        "}"
        "return JSON.stringify(result);"
    )
    print(f"AFTER click: {info2}")
else:
    print("No add btn")

page.quit()
print("Done")