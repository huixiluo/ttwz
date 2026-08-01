"""测试 Shadow DOM 和 React fiber 中的 file input"""
import json, time, os
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
page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(4)

# fill title + content
title_el = page.ele("tag:textarea", timeout=10)
if title_el:
    title_el.input("shadow dom test")
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

# Search for file inputs in shadow DOM and React fiber
result = page.run_js("""
var result = [];

// 1. Normal file inputs
var normalInputs = document.querySelectorAll('input[type="file"]');
result.push({normal: normalInputs.length});

// 2. Search shadow DOM recursively
function findInShadow(root, depth) {
    if (depth > 10) return [];
    var found = [];
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) {
            var inputs = all[i].shadowRoot.querySelectorAll('input[type="file"]');
            for (var j = 0; j < inputs.length; j++) {
                found.push({tag: all[i].tagName, cls: all[i].className, depth: depth});
            }
            found = found.concat(findInShadow(all[i].shadowRoot, depth + 1));
        }
    }
    return found;
}
var shadowInputs = findInShadow(document.body, 0);
result.push({shadowInputs: shadowInputs.length, details: shadowInputs});

// 3. Check React fiber (__reactFiber or __reactInternalInstance)
function findReactFiber(dom) {
    var key = Object.keys(dom).find(function(k) {
        return k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance');
    });
    return key ? dom[key] : null;
}
var coverAdd = document.querySelector('.article-cover-add');
if (coverAdd) {
    var fiber = findReactFiber(coverAdd);
    if (fiber) {
        result.push({reactFiber: 'found', fiberType: fiber.type ? (fiber.type.name || typeof fiber.type) : 'no type'});
    } else {
        result.push({reactFiber: 'not found'});
    }
}

// 4. Check Vue instance (__vue__)
var coverEl = document.querySelector('.article-cover');
if (coverEl) {
    var vue = coverEl.__vue__;
    if (vue) {
        result.push({vue: 'found'});
    } else {
        result.push({vue: 'not found'});
    }
}

// 5. Check for iframes
var iframes = document.querySelectorAll('iframe');
result.push({iframes: iframes.length});
for (var k = 0; k < iframes.length; k++) {
    try {
        var iframeInputs = iframes[k].contentDocument.querySelectorAll('input[type="file"]');
        result.push({iframeInputs: iframeInputs.length});
    } catch(e) {
        result.push({iframeError: e.message});
    }
}

return JSON.stringify(result);
""")

print("DOM Analysis:")
print(result)

# Try clicking article-cover-add with JS click
print("\n--- JS click test ---")
r = page.run_js(
    "var add = document.querySelector('.article-cover-add');"
    "if (add) {"
    "  var evt = new MouseEvent('click', {bubbles: true, cancelable: true, view: window});"
    "  add.dispatchEvent(evt);"
    "  return 'clicked';"
    "}"
    "return 'not found';"
)
print(f"JS click: {r}")
time.sleep(2)

# Check if any file inputs appeared
inputs = page.run_js("return document.querySelectorAll('input[type=\"file\"]').length;")
print(f"File inputs after JS click: {inputs}")

page.quit()
print("Done")