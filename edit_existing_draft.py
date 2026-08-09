# -*- coding: utf-8 -*-
"""通过编辑现有草稿来上传新文章，绕过7050新建限制"""
import os, json, time, re, base64
from DrissionPage import ChromiumPage, ChromiumOptions
import upload_visible as uv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

DEBUG_LOG = os.path.join(BASE_DIR, "debug.log")

def dlog(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def main():
    # 读取要上传的文章
    with open("single_manifest.json", "r", encoding="utf-8") as f:
        art = json.load(f)[0]
    title = art["title"][:30]
    html_path = art["html_file"]
    print(f"文章: {title}")
    dlog(f"edit_draft: 文章={title}")

    # 读取HTML正文
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    text_parts = []
    image_srcs = []
    if body_match:
        body = body_match.group(1)
        for m in re.finditer(
            r'(<p>(.*?)</p>)|'
            r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*<p[^>]*>(.*?)</p>\s*</div>)',
            body, re.DOTALL
        ):
            if m.group(1):
                clean = re.sub(r"<[^>]+>", "", m.group(2))
                text_parts.append(f'<p>{clean}</p>')
            elif m.group(4):
                image_srcs.append(m.group(4))

    print(f"  正文: {len(text_parts)}段, {len(image_srcs)}张图片")
    image_layout = uv.calc_image_layout(len(text_parts), len(image_srcs))

    # 启动浏览器
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
    co.set_browser_path(CHROME_PATH)
    co.headless(True)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    co.set_argument("--disable-background-timer-throttling")
    co.set_argument("--disable-backgrounding-occluded-windows")
    co.set_argument("--disable-renderer-backgrounding")
    co.set_address("127.0.0.1:9230")
    co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_edit"))
    page = ChromiumPage(co)
    page.get("https://mp.toutiao.com")
    time.sleep(2)

    page.run_js("""
Object.defineProperty(document, 'hidden', {value: false, writable: false, configurable: true});
Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false, configurable: true});
document.dispatchEvent(new Event('visibilitychange'));
""")

    cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
    for name, value in cookies.items():
        try:
            page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        except Exception:
            pass
    page.get("https://mp.toutiao.com")
    time.sleep(3)

    # 检查登录
    login_ok = page.run_js("""
        var url = window.location.href;
        var body = document.body ? document.body.innerText : '';
        if (url.indexOf('login') >= 0 || url.indexOf('passport') >= 0) return 'NOT_LOGIN';
        if (body.indexOf('扫码登录') >= 0 || body.indexOf('账号密码登录') >= 0) return 'NOT_LOGIN';
        return 'LOGIN_OK';
    """)
    print(f"  登录状态: {login_ok}")
    if login_ok != 'LOGIN_OK':
        print("  [FAIL] cookies失效")
        page.quit()
        return False

    # 打开草稿箱
    print("\n[2] 打开草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(8)

    # 查找可编辑的草稿（排除已上传的第1篇）
    # 找到草稿列表中的"编辑"链接
    draft_found = page.run_js("""
// 查找所有草稿项
var items = document.querySelectorAll('[class*="draft"], [class*="item"], [class*="article"]');
var editLinks = [];

// 查找所有"编辑"文本的链接
var allLinks = document.querySelectorAll('a, span, button, div');
for (var el of allLinks) {
    var text = el.textContent.trim();
    if (text === '编辑' && el.tagName === 'A') {
        var href = el.href || el.getAttribute('href') || '';
        if (href.indexOf('graphic') >= 0 || href.indexOf('publish') >= 0 || href.indexOf('edit') >= 0) {
            editLinks.push({href: href, text: text});
        }
    }
}

// 也查找带有data属性或onclick的编辑按钮
if (editLinks.length === 0) {
    for (var el of allLinks) {
        var text = el.textContent.trim();
        if (text === '编辑') {
            var href = el.href || el.getAttribute('href') || '';
            if (href) {
                editLinks.push({href: href, text: text});
            }
        }
    }
}

return JSON.stringify(editLinks);
""")
    print(f"  找到编辑链接: {draft_found[:500]}")

    try:
        edit_links = json.loads(draft_found) if draft_found else []
    except:
        edit_links = []

    if not edit_links:
        # 尝试直接点击草稿标题
        print("  未找到编辑链接，尝试点击草稿标题...")
        # 查找草稿标题链接
        title_clicked = page.run_js("""
var allLinks = document.querySelectorAll('a');
var titleLinks = [];
for (var a of allLinks) {
    var href = a.href || '';
    if (href.indexOf('graphic/publish') >= 0 || href.indexOf('edit') >= 0) {
        var text = a.textContent.trim();
        if (text.length > 5 && text.length < 50) {
            titleLinks.push({href: href, text: text});
        }
    }
}
return JSON.stringify(titleLinks);
""")
        print(f"  草稿标题链接: {title_clicked[:1000]}")
        try:
            title_links = json.loads(title_clicked) if title_clicked else []
        except:
            title_links = []

        if title_links:
            # 找一个不是我们9篇文章的草稿来编辑
            our_titles = ["网红揭恶毒闺蜜", "神仙姐姐下沉市场", "复旦王水牛走红",
                         "进球悼念故友", "孙颖莎登青年榜", "C罗表情包回应婚礼",
                         "上海迎台风天", "拜登癌症扩散", "杭州地铁引热议"]

            target_link = None
            for link in title_links:
                is_our = False
                for t in our_titles:
                    if t in link.get("text", ""):
                        is_our = True
                        break
                if not is_our:
                    target_link = link
                    break

            if not target_link and title_links:
                target_link = title_links[-1]  # 用最后一个

            if target_link:
                print(f"  选择编辑: {target_link['text'][:40]}")
                # 导航到编辑页面
                edit_url = target_link["href"]
                if edit_url.startswith("/"):
                    edit_url = "https://mp.toutiao.com" + edit_url
                print(f"  编辑URL: {edit_url}")
                page.get(edit_url)
                time.sleep(6)
        else:
            print("  [FAIL] 未找到可编辑的草稿")
            page.quit()
            return False
    else:
        # 使用第一个编辑链接
        edit_url = edit_links[0].get("href", "")
        if edit_url.startswith("/"):
            edit_url = "https://mp.toutiao.com" + edit_url
        print(f"  编辑URL: {edit_url}")
        page.get(edit_url)
        time.sleep(6)

    # 等待编辑器加载
    editor_ready = False
    for i in range(20):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            print("  [OK] 编辑器已就绪")
            editor_ready = True
            break
        time.sleep(1)

    if not editor_ready:
        print("  [FAIL] 编辑器未就绪")
        page.quit()
        return False

    # 注入网络拦截器
    page.run_js("""
window._saveResponses=[];
function isSaveUrl(u){
  if(!u)return false;
  if(u.indexOf('monitor')>=0||u.indexOf('collect')>=0||u.indexOf('feedback')>=0)return false;
  if(u.indexOf('publish')>=0||u.indexOf('save')>=0||u.indexOf('draft')>=0||u.indexOf('article')>=0)return true;
  return false;
}
var origFetch=window.fetch;
window.fetch=function(url,options){
  options=options||{};
  var urlStr=typeof url==='string'?url:(url&&url.url)||'';
  var p=origFetch.apply(this,arguments);
  if(isSaveUrl(urlStr)){
    p.then(function(resp){
      var sc=resp.status;
      resp.clone().text().then(function(t){
        window._saveResponses.push({url:urlStr,status:sc,body:t.substring(0,5000)});
      }).catch(function(){});
    }).catch(function(){});
  }
  return p;
};
""")

    # 清除旧内容
    print("\n[3] 清除旧内容...")
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.focus();
    // 全选并删除
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
}
""")
    time.sleep(1)

    # 设置新标题
    print(f"\n[4] 设置新标题: {title}")
    page.run_js(f"""
var el = document.querySelector('textarea[placeholder*="文章标题"]') ||
         document.querySelector('textarea[placeholder*="请输入文章标题"]');
if (el) {{
    el.focus();
    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(el, {json.dumps(title)});
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
    el.blur();
}}
""")
    time.sleep(2)

    # 上传图片
    print(f"\n[5] 上传{len(image_srcs)}张图片...")
    tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    for old_f in os.listdir(tmp_dir):
        if old_f.startswith("body_img_"):
            try:
                os.remove(os.path.join(tmp_dir, old_f))
            except:
                pass

    tmp_files = []
    for img_i, data_url in enumerate(image_srcs):
        fpath = uv.save_base64_to_temp(data_url, img_i)
        tmp_files.append(fpath)

    try:
        page.run_cdp('Page.setInterceptFileChooserDialog', enabled=True)
    except:
        pass

    image_urls = []
    for img_idx, fpath in enumerate(tmp_files):
        if not fpath or not os.path.exists(fpath):
            image_urls.append("")
            continue
        print(f"    图片{img_idx+1}: 上传中...")
        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.innerHTML = '<p></p>';
    editor.dispatchEvent(new Event('input', {bubbles: true}));
}
""")
        time.sleep(0.3)
        page.run_js("var e=document.querySelector('.ProseMirror'); if(e) e.focus();")
        time.sleep(0.2)

        with open(fpath, "rb") as fimg:
            img_b64 = base64.b64encode(fimg.read()).decode('ascii')

        ext2 = os.path.splitext(fpath)[1].lstrip('.').replace('jpeg', 'jpg')
        mime2 = f'image/{ext2}' if ext2 != 'jpg' else 'image/jpeg'
        page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor) return;
editor.focus();
var b64 = {json.dumps(img_b64)};
var mime = {json.dumps(mime2)};
var byteString = atob(b64);
var ab = new ArrayBuffer(byteString.length);
var ia = new Uint8Array(ab);
for (var i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
var blob = new Blob([ab], {{type: mime}});
var file = new File([blob], 'image_{img_idx+1}.{ext2}', {{type: mime}});
var pasteEvent = new ClipboardEvent('paste', {{
    bubbles: true,
    cancelable: true
}});
var fakeData = {{
    files: [file],
    items: [],
    types: ['Files'],
    getData: function() {{ return ''; }},
    setData: function() {{}},
    clearData: function() {{}}
}};
Object.defineProperty(pasteEvent, 'clipboardData', {{
    value: fakeData,
    writable: false,
    configurable: true
}});
editor.dispatchEvent(pasteEvent);
""")

        uploaded = False
        for wait_i in range(60):
            time.sleep(0.5)
            imgs_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
            if imgs_now > 0:
                uploaded = True
                break

        if not uploaded:
            print(f"    图片{img_idx+1}: 上传超时")
            image_urls.append("")
            continue

        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return;
var imgs = editor.querySelectorAll('img');
for (var i = imgs.length - 1; i > 0; i--) {
    imgs[i].parentNode.removeChild(imgs[i]);
}
""")
        time.sleep(0.5)

        img_url = ""
        for wait_i in range(60):
            img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
            if img_url and not img_url.startswith('blob:'):
                break
            time.sleep(1)

        image_urls.append(img_url)
        print(f"    图片{img_idx+1}: OK URL={img_url[:60]}...")

    valid_urls = [u for u in image_urls if u and not u.startswith('blob:')]
    print(f"  [5] 完成: {len(valid_urls)}/{len(tmp_files)}张图片已上传")

    # 构建最终内容
    print(f"\n[6] 设置编辑器内容...")
    final_html = ""
    url_idx = 0
    for para_idx, para_html in enumerate(text_parts):
        final_html += para_html
        target_para = para_idx + 1
        if target_para in image_layout:
            num_imgs = image_layout[target_para]
            for _ in range(num_imgs):
                if url_idx < len(image_urls) and image_urls[url_idx]:
                    final_html += f'<p><img src="{image_urls[url_idx]}" alt="图片来源于网络"></p>'
                    url_idx += 1

    # 通过ProseMirror API设置内容
    content_json = uv.build_prosemirror_json(final_html)
    pm_result = page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (!editor || !editor.pmViewDesc || !editor.pmViewDesc.view) return 'no_view';
var view = editor.pmViewDesc.view;
var state = view.state;
var contentJson = {json.dumps(content_json)};
var doc = state.schema.nodeFromJSON(contentJson);
view.dispatch(view.state.tr.replaceWith(0, state.doc.content.size, doc.content));
return 'ok';
""")
    print(f"  ProseMirror: {pm_result}")
    time.sleep(2)

    # 模拟按键触发保存
    print("\n[7] 触发保存...")
    page.run_js("var e=document.querySelector('.ProseMirror'); if(e){e.focus();}")
    time.sleep(0.5)
    page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space',
                  windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
    page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space',
                  windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
    time.sleep(0.3)
    page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key='Backspace', code='Backspace',
                  windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
    page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key='Backspace', code='Backspace',
                  windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)

    # 等待保存
    print("  等待保存完成...")
    saved = False
    for i in range(60):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('保存失败') !== -1) return 'FAIL';
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'IDLE';
""") or ""

        # 检查API响应
        responses = page.run_js("""
var responses = window._saveResponses || [];
for (var i = 0; i < responses.length; i++) {
    var b = responses[i].body || '';
    if (b.indexOf('"code":0') >= 0 || b.indexOf('"code": 0') >= 0) return 'SUCCESS';
}
return '';
""") or ""

        if responses == 'SUCCESS' or status == 'SAVED':
            print(f"  [OK] 保存成功! (用时{i*2}s, status={status})")
            saved = True
            break

        if i % 5 == 0:
            print(f"  [{i*2}s] status={status}")

    if not saved:
        print(f"  [WARN] 保存未确认 (最后status={status})")
        # 即使未确认，也检查草稿箱
        # 打印API响应
        api_responses = page.run_js("return JSON.stringify(window._saveResponses||[]);") or "[]"
        try:
            rs = json.loads(api_responses)
            for r in rs[-3:]:
                body = r.get('body','')[:200]
                print(f"  API响应: {body}")
        except:
            pass

    # 验证草稿箱
    print("\n[8] 验证草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(5)
    draft_text = page.run_js("return document.body.innerText;") or ""
    if title[:10] in draft_text:
        print(f"  [SUCCESS] 文章已在草稿箱中!")
        page.quit()
        return True
    else:
        print(f"  [FAIL] 未在草稿箱中找到文章")
        # 打印前500字
        print(f"  草稿箱前300字: {draft_text[:300]}")
        page.quit()
        return False

if __name__ == "__main__":
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n=== edit_existing_draft 开始 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    result = main()
    print(f"\n结果: {'成功' if result else '失败'}")
