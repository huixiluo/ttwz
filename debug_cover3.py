"""测试拦截 file input click"""
import json, time, os
from DrissionPage import ChromiumPage, ChromiumOptions

PROJ = r"C:\Users\huixi\Documents\trae_projects\ttwz"
with open(f"{PROJ}\\toutiao_cookies.json", "r") as f:
    cookies = json.load(f)

covers_dir = f"{PROJ}\\output\\covers"
cover_files = [f for f in os.listdir(covers_dir) if f.endswith('.jpg')]
if cover_files:
    test_cover = os.path.join(covers_dir, cover_files[0])
    print(f"Test cover: {test_cover}")
else:
    print("No cover files")
    exit()

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
    title_el.input("test interceptor")
    print("Title ok")

page.run_js(
    "var editor = document.querySelector('.ProseMirror');"
    "if (editor) { editor.innerHTML = '<p>test</p>';"
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

# Intercept: override HTMLInputElement click to capture file inputs
page.run_js(
    "window.__capturedInputs = [];"
    "var _origClick = HTMLInputElement.prototype.click;"
    "HTMLInputElement.prototype.click = function() {"
    "  if (this.type === 'file') {"
    "    window.__capturedInputs.push({"
    "      accept: this.accept,"
    "      visible: this.getBoundingClientRect().width > 0,"
    "      parent: this.parentElement ? this.parentElement.className : ''"
    "    });"
    "    window.__lastFileInput = this;"
    "  }"
    "  return _origClick.apply(this, arguments);"
    "};"
    "return 'interceptor set';"
)
print("Interceptor set")

# Intercept: watch for DOM additions
page.run_js(
    "window.__addedInputs = [];"
    "var _observer = new MutationObserver(function(mutations) {"
    "  mutations.forEach(function(mutation) {"
    "    mutation.addedNodes.forEach(function(node) {"
    "      if (node.nodeType === 1) {"
    "        if (node.tagName === 'INPUT' && node.type === 'file') {"
    "          window.__addedInputs.push({accept: node.accept});"
    "          window.__lastAddedInput = node;"
    "        }"
    "        var inputs = node.querySelectorAll ? node.querySelectorAll('input[type=\"file\"]') : [];"
    "        for (var i = 0; i < inputs.length; i++) {"
    "          window.__addedInputs.push({accept: inputs[i].accept, inSubtree: true});"
    "          window.__lastAddedInput = inputs[i];"
    "        }"
    "      }"
    "    });"
    "  });"
    "});"
    "_observer.observe(document.body, {childList: true, subtree: true});"
    "return 'observer set';"
)
print("MutationObserver set")

# Now click the add button
add_btn = page.ele(".article-cover-add", timeout=5)
if add_btn:
    print("Clicking add_btn...")
    add_btn.click()
    time.sleep(3)
    
    # Check captured inputs
    captured = page.run_js("return JSON.stringify(window.__capturedInputs);")
    print(f"Captured inputs: {captured}")
    
    added = page.run_js("return JSON.stringify(window.__addedInputs);")
    print(f"Added inputs: {added}")
    
    # Check if lastFileInput exists
    has_last = page.run_js("return window.__lastFileInput ? 'yes' : 'no';")
    print(f"Has lastFileInput: {has_last}")
    
    if has_last == 'yes':
        # Try to upload
        last_input = page.run_js("return window.__lastFileInput;")
        print(f"lastFileInput: {last_input}")
        
        # Get the element as DrissionPage element and upload
        try:
            # Try finding by the captured reference
            file_inputs = page.eles('tag:input@type=file')
            print(f"All file inputs: {len(file_inputs)}")
            for fi in file_inputs:
                print(f"  accept={fi.attr('accept')}, visible={fi.attr('style')}")
        except Exception as e:
            print(f"Error finding inputs: {e}")
else:
    print("No add_btn")

page.quit()
print("Done")