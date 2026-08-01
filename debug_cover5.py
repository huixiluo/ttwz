"""调试：填充内容后，先选三图再点上传按钮"""
import os, sys, json, time, re
sys.path.insert(0, r"C:\Users\huixi\Documents\trae_projects\ttwz")
from DrissionPage import ChromiumPage, ChromiumOptions

COOKIE_FILE = r"C:\Users\huixi\Documents\trae_projects\ttwz\toutiao_cookies.json"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
co.headless(True)
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
page.get(PUBLISH_URL)
time.sleep(4)

# Fill title
title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
if title_el:
    title_el.input("测试封面标题")
    print("Title filled")
time.sleep(1)

# Fill content
paragraphs = ["第一段", "第二段", "第三段", "第四段", "第五段"]
html_parts = "".join(f"<p>{p}</p>" for p in paragraphs)
page.run_js(f"""
const editor = document.querySelector('.ProseMirror');
if (editor) {{
    editor.innerHTML = {json.dumps(html_parts)};
    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
}}
""")
time.sleep(2)
print("Content filled")

# Now select "三图" mode
print("\n=== Selecting 三图 ===")
# Try clicking the label
labels = page.eles('tag:label')
for label in labels:
    if '三图' in (label.text or ''):
        label.click()
        time.sleep(1)
        print(f"Clicked label: {label.text}")
        break

# Check radio state
checked = page.run_js("""
const radio = document.querySelector('input[type=radio][value="3"]');
return radio ? radio.checked : 'not found';
""")
print(f"Radio checked: {checked}")

# Check article-cover-add
time.sleep(1)
add_btn = page.ele('@class:article-cover-add', timeout=5)
if add_btn:
    print(f"add_btn found, visible: {add_btn.states.is_displayed}")
    
    # Scroll to it
    page.run_js("document.querySelector('.article-cover-add').scrollIntoView({block: 'center'});")
    time.sleep(1)
    
    # Click
    add_btn.click()
    time.sleep(2)
    print("Clicked add_btn")
    
    # Check for file inputs
    time.sleep(2)
    inputs = page.eles('tag:input@type=file')
    print(f"File inputs: {len(inputs)}")
    for i, fi in enumerate(inputs):
        print(f"  [{i}] accept={fi.attr('accept')} visible={fi.states.is_displayed}")
else:
    print("add_btn NOT FOUND")
    
    # Try JS click instead
    print("\n=== Trying JS click ===")
    result = page.run_js("""
    const btn = document.querySelector('.article-cover-add');
    if (btn) {
        btn.scrollIntoView({block: 'center'});
        btn.click();
        return 'clicked';
    }
    return 'not found';
    """)
    print(f"JS click result: {result}")
    time.sleep(2)
    inputs = page.eles('tag:input@type=file')
    print(f"File inputs after JS click: {len(inputs)}")

page.quit()
print("\nDone")