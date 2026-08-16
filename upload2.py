# -*- coding: utf-8 -*-
"""上传文章到头条号草稿箱（带flush输出）"""
import os, sys, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = r"C:\Users\huixi\Documents\trae_projects\ttwz"
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def log(msg):
    print(msg, flush=True)

log("=" * 50)
log("头条号文章上传")
log("=" * 50)

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    articles = json.load(f)
log(f"共 {len(articles)} 篇文章")

log("\n[1] 启动浏览器...")
co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)
log("浏览器已启动")

log("[2] 注入Cookie并验证登录...")
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
log(f"共 {len(cookies)} 个Cookie")

page.get("https://mp.toutiao.com")
time.sleep(2)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass

page.get("https://mp.toutiao.com")
time.sleep(3)
log(f"当前URL: {page.url}")

if "profile" not in page.url.lower() and "graphic" not in page.url.lower():
    log("[错误] Cookie登录失败")
    page.quit()
    sys.exit(1)
log("登录验证成功！")

log("\n[3] 开始上传...")
success = 0
for idx, art in enumerate(articles, 1):
    title = art.get("title", "")[:30]
    article_text = art.get("article", "")
    category = art.get("category", "")
    cover_files = art.get("cover_files", [])

    log(f"\n[{idx}/{len(articles)}] {category} | {title}")

    try:
        page.get(PUBLISH_URL)
        time.sleep(4)

        # 关闭弹窗
        try:
            close_btn = page.ele('text:关闭', timeout=2)
            if close_btn:
                close_btn.click()
                time.sleep(1)
        except:
            pass

        # 填标题
        title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
        if not title_el:
            title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
        if title_el:
            title_el.clear()
            title_el.input(title)
            log(f"  标题已填（{len(title)}字）")
        else:
            log("  [跳过] 找不到标题输入框")
            continue

        time.sleep(1)

        # 填正文
        paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
        html_parts = "".join(f"<p>{p}</p>" for p in paragraphs)
        js = f"""
        const editor = document.querySelector('.ProseMirror');
        if (editor) {{
            editor.innerHTML = {json.dumps(html_parts)};
            editor.dispatchEvent(new Event('input', {{bubbles: true}}));
            return 'ok';
        }}
        return 'not_found';
        """
        result = page.run_js(js)
        if result == "ok":
            chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
            log(f"  正文已填（约{chars}字）")
        else:
            log(f"  [跳过] 找不到编辑器: {result}")
            continue

        time.sleep(1)

        # 封面图
        valid_covers = [cf for cf in cover_files[:3] if os.path.exists(cf)]
        if valid_covers:
            log(f"  封面图: {len(valid_covers)}张")
            try:
                three_img = page.ele('text:三图', timeout=3)
                if three_img:
                    three_img.click()
                    time.sleep(1)
                for ci, cf in enumerate(valid_covers):
                    try:
                        file_input = page.ele('tag:input@type=file', timeout=5)
                        if file_input:
                            file_input.input(cf)
                            time.sleep(2)
                            log(f"    封面{ci+1}: {os.path.basename(cf)}")
                        else:
                            log(f"    封面{ci+1}: 找不到上传控件")
                    except Exception as e:
                        log(f"    封面{ci+1}: 失败 {e}")
            except Exception as e:
                log(f"  封面上传异常: {e}")

        # 等待保存
        time.sleep(5)
        save_tip = page.ele('text:已保存', timeout=3) or page.ele('text:保存成功', timeout=3)
        if save_tip:
            log("  [OK] 草稿已保存")
        else:
            log("  [提示] 内容已填写，应自动保存")

        success += 1
    except Exception as e:
        log(f"  [错误] {e}")

    time.sleep(2)

log(f"\n{'='*50}")
log(f"完成: {success}/{len(articles)} 篇")
log(f"{'='*50}")
page.quit()
log("浏览器已关闭")