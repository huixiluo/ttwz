"""测试 set.upload_files 上传封面"""
import json, time, os
from DrissionPage import ChromiumPage, ChromiumOptions

PROJ = r"C:\Users\huixi\Documents\trae_projects\ttwz"
with open(f"{PROJ}\\toutiao_cookies.json", "r") as f:
    cookies = json.load(f)

# 找一张封面图测试
covers_dir = f"{PROJ}\\output\\covers"
cover_files = [f for f in os.listdir(covers_dir) if f.endswith('.jpg')]
if cover_files:
    test_cover = os.path.join(covers_dir, cover_files[0])
    print(f"Test cover: {test_cover}")
else:
    print("No cover files found")
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
    title_el.input("test cover upload")
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

# Method 1: Use set.upload_files then click
print("\n=== Method 1: set.upload_files + click ===")
try:
    page.set.upload_files(test_cover)
    print("set.upload_files done")
    
    add_btn = page.ele(".article-cover-add", timeout=5)
    if add_btn:
        add_btn.click()
        time.sleep(5)
        print("Clicked add_btn, waiting...")
        
        # Check if file was uploaded
        imgs = page.run_js("return document.querySelectorAll('.article-cover-images img').length;")
        print(f"Cover images after upload: {imgs}")
    else:
        print("No add_btn")
except Exception as e:
    print(f"Method 1 error: {e}")

# Method 2: Create file input via JS and append to cover area
print("\n=== Method 2: JS create file input ===")
try:
    result = page.run_js(
        "var input = document.createElement('input');"
        "input.type = 'file';"
        "input.accept = 'image/*';"
        "input.id = '__debug_file_input';"
        "input.style.cssText = 'position:fixed;top:0;left:0;z-index:99999;opacity:1;width:100px;height:30px;';"
        "document.body.appendChild(input);"
        "return 'created';"
    )
    print(f"Created input: {result}")
    
    # Try to find and upload
    file_input = page.ele("#__debug_file_input", timeout=3)
    if file_input:
        file_input.input(test_cover)
        time.sleep(2)
        print("File input done")
    else:
        print("No file input found")
except Exception as e:
    print(f"Method 2 error: {e}")

page.quit()
print("Done")