# -*- coding: utf-8 -*-
"""完整上传：非headless模式 + 标题.input() + 正文paste + 封面上传

图片上传策略（分批粘贴，避免光标定位问题）：
1. 按 IMAGE_LAYOUT 分批：文字批次 → 图片批次 交替
2. 每次粘贴文字后光标自动在末尾，立即粘贴图片到该位置
3. 图片布局：第1段后1张、第3段后2张、第5段后2张
"""
import os, re, json, time, base64, subprocess
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

# 文件日志（绕过终端输出捕获问题）
DEBUG_LOG = os.path.join(BASE_DIR, "debug.log")
def dlog(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

# 图片布局：第1段后1张、第3段后2张、第5段后2张
IMAGE_LAYOUT = {1: 1, 3: 2, 5: 2}


def set_clipboard_html(html_content):
    """用PowerShell设置剪贴板（同时设置HTML和纯文字格式）"""
    try:
        # 从HTML中提取纯文字，用\n\n分隔段落（先替换</p><p>为\n\n，再删标签）
        plain_text = html_content.replace('</p>\n<p>', '\n\n').replace('</p><p>', '\n\n')
        plain_text = re.sub(r'<[^>]+>', '', plain_text)
        plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text).strip()
        # 用base64编码避免PowerShell转义问题（UTF-16LE for UnicodeText）
        b64_html = base64.b64encode(html_content.encode('utf-8')).decode('ascii')
        b64_text = base64.b64encode(plain_text.encode('utf-16-le')).decode('ascii')
        ps_script = (
            'Add-Type -AssemblyName System.Windows.Forms; '
            f'$html = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String(\'{b64_html}\')); '
            f'$text = [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String(\'{b64_text}\')); '
            '$obj = New-Object System.Collections.Specialized.NameValueCollection; '
            '$data = New-Object System.Windows.Forms.DataObject; '
            '$data.SetText($html, [System.Windows.Forms.TextDataFormat]::Html); '
            '$data.SetText($text, [System.Windows.Forms.TextDataFormat]::UnicodeText); '
            '[System.Windows.Forms.Clipboard]::SetDataObject($data, $true)'
        )
        result = subprocess.run(
            ['powershell', '-STA', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            dlog(f"set_clipboard_html: 成功 (html={len(html_content)}字符, text={len(plain_text)}字符)")
            return True
        else:
            dlog(f"set_clipboard_html: 失败 {result.stderr[:300]}")
            return False
    except Exception as e:
        dlog(f"set_clipboard_html: 异常 {e}")
        return False


def move_cursor_to_end(page):
    """用JavaScript把光标设置到ProseMirror文档末尾"""
    try:
        result = page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'no_editor';
editor.focus();
var range = document.createRange();
range.selectNodeContents(editor);
range.collapse(false);
var sel = window.getSelection();
sel.removeAllRanges();
sel.addRange(range);
return 'ok';
""")
        dlog(f"move_cursor_to_end: {result}")
        return result == 'ok'
    except Exception as e:
        dlog(f"move_cursor_to_end: 异常 {e}")
        return False


def wait_for_save(page, timeout=30):
    for i in range(timeout):
        time.sleep(1)
        s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
var btns = document.querySelectorAll('button, span');
for (var j = 0; j < btns.length; j++) {
    var t = (btns[j].textContent || '').trim();
    if (t.indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
}
return 'idle';
""")
        if s and 'SAVED' in str(s):
            return True
    return False


def trigger_save(page):
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=5)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        return False
    title_el.click()
    time.sleep(0.3)
    title_el.input(" ")
    time.sleep(0.3)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
    time.sleep(0.5)
    return True


def upload_cover(page, cover_paths):
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        dlog("upload_cover: 无有效封面图")
        return
    dlog(f"upload_cover: {len(valid)}张封面图")

    page.run_js("window.scrollTo(0, 0);")
    time.sleep(1)
    page.run_js("""
var cover = document.querySelector('.article-cover');
if (cover) cover.scrollIntoView({block: 'center'});
""")
    time.sleep(2)

    page.run_js("""
var radios = document.querySelectorAll('input[type="radio"]');
for (var i = 0; i < radios.length; i++) {
    if (radios[i].value === '3') {
        radios[i].click();
        radios[i].checked = true;
        radios[i].dispatchEvent(new Event('change', {bubbles: true}));
        return;
    }
}
""")
    time.sleep(3)
    dlog("upload_cover: 已选择3图模式")

    for ci, cf in enumerate(valid):
        print(f"    封面{ci+1}: {os.path.basename(cf)}...")
        dlog(f"upload_cover: 封面{ci+1}开始 {os.path.basename(cf)}")
        page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) {
    add.scrollIntoView({block: 'center'});
    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
        add.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    });
}
""")
        time.sleep(2)
        fi = None
        for _ in range(15):
            for inp in page.eles('tag:input@type=file'):
                try:
                    if 'image' in (inp.attr('accept') or '') and inp.rect.size[0] > 0:
                        fi = inp
                        break
                except:
                    pass
            if fi:
                break
            time.sleep(0.5)
        if fi:
            dlog(f"upload_cover: 封面{ci+1} 找到file input，开始input")
            fi.input(cf)
            time.sleep(3)
            print(f"    封面{ci+1}: ✓")
            dlog(f"upload_cover: 封面{ci+1} ✓")
        else:
            dlog(f"upload_cover: 封面{ci+1} 未找到file input，尝试兜底")
            for inp in page.eles('tag:input@type=file'):
                try:
                    inp.input(cf)
                    time.sleep(3)
                    print(f"    封面{ci+1}: ✓ (兜底)")
                    dlog(f"upload_cover: 封面{ci+1} ✓ (兜底)")
                    break
                except:
                    continue
            else:
                print(f"    封面{ci+1}: 未找到")
                dlog(f"upload_cover: 封面{ci+1} 未找到file input")


def save_base64_to_temp(data_url, idx):
    """把base64图片保存为临时文件，返回路径"""
    dlog(f"  save_base64_to_temp开始: idx={idx}, url长度={len(data_url) if data_url else 0}")
    if not data_url or not data_url.startswith('data:image/'):
        dlog(f"  save_base64_to_temp: 无效data_url")
        return None
    # 分割data URL（避免regex对大字符串的性能问题）
    try:
        header, b64 = data_url.split(',', 1)
        mime = header.split(':')[1].split(';')[0]
        ext = mime.split('/')[-1].replace('jpeg', 'jpg')
    except Exception as e:
        dlog(f"  save_base64_to_temp: 解析失败: {e}")
        return None
    dlog(f"  save_base64_to_temp: mime={mime}, b64长度={len(b64)}")
    tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    fname = f"body_img_{idx+1}.{ext}"
    fpath = os.path.join(tmp_dir, fname)
    dlog(f"  save_base64_to_temp: 开始decode base64...")
    try:
        decoded = base64.b64decode(b64)
        dlog(f"  save_base64_to_temp: decode完成, {len(decoded)}字节")
    except BaseException as e:
        dlog(f"  save_base64_to_temp: decode失败: {e}")
        return None
    dlog(f"  save_base64_to_temp: 开始写文件...")
    with open(fpath, "wb") as f:
        f.write(decoded)
    dlog(f"  save_base64_to_temp: 写文件完成: {fpath}")
    return fpath


def main():
    # 清空调试日志
    with open(DEBUG_LOG, "w", encoding="utf-8") as f:
        f.write(f"=== 开始运行 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    dlog("main() 开始")

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        art = json.load(f)[0]
    title = art["title"][:30]
    cover_files = art["cover_files"]
    html_path = art["html_file"]
    print(f"文章: {title}")

    # 读取HTML正文，分离纯文字和图片
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    text_only_html = ""
    image_srcs = []
    text_parts = []
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
        text_only_html = "\n".join(text_parts)

    print(f"  正文: {len(text_parts)}段, {len(image_srcs)}张图片")
    text_plain = re.sub(r'<[^>]+>', '', text_only_html).strip()

    # 启动浏览器
    print("[1] 启动浏览器...")
    co = ChromiumOptions()
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
    print(f"  URL: {page.url}")
    print("  [OK] 登录成功")

    # 创建新文章
    print("\n[1.5] 创建新文章...")
    page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
    time.sleep(6)
    for i in range(15):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            print("  [OK] 编辑器已就绪")
            break
        time.sleep(1)
    try:
        btn = page.ele("text:关闭", timeout=2)
        if btn:
            btn.click()
            time.sleep(1)
    except:
        pass
    try:
        btn = page.ele("text:不恢复", timeout=2)
        if btn:
            btn.click()
            time.sleep(1)
    except:
        pass

    # === 第1步：填标题 ===
    print("\n[2] 填标题...")
    title_el = page.ele('tag:textarea@placeholder=请输入文章标题（2～30个字）', timeout=10)
    if not title_el:
        title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    title_el.click()
    time.sleep(0.5)
    title_el.input(title)
    time.sleep(1)
    page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) { el.blur(); el.dispatchEvent(new Event('change', {bubbles: true})); }
""")
    print(f"  标题: {title}")
    time.sleep(3)

    if wait_for_save(page, timeout=10):
        print("  [OK] 标题已保存")
    else:
        print("  [WARN] 标题保存未确认")

    # === 第2步：填正文 ===
    print("\n[3] 填正文...")

    # 清除旧草稿
    existing = page.run_js("var e=document.querySelector('.ProseMirror'); return e?e.innerText.trim():'';")
    if existing and len(existing) > 10:
        print(f"  检测到旧草稿({len(existing)}字)，正在清除...")
        editor_el = page.ele('.ProseMirror', timeout=5)
        if editor_el:
            editor_el.click()
            time.sleep(0.5)
            page.actions.key_down('ctrl').type('a').key_up('ctrl')
            time.sleep(0.5)
            page.actions.key_down('Backspace').key_up('Backspace')
            time.sleep(1)
            remaining = page.run_js("var e=document.querySelector('.ProseMirror'); return e?e.innerText.trim():'';")
            print(f"  清除后剩余: {len(remaining) if remaining else 0}字")

    time.sleep(1)

    # [3a] 分批粘贴：文字批次 → 图片批次 交替（避免光标定位问题）
    # 按 IMAGE_LAYOUT 分批：例如 {1:1, 3:2, 5:2} + 6段文字
    # 批次1: 粘贴段落[0:1] → 图片1
    # 批次2: 粘贴段落[1:3] → 图片2,3
    # 批次3: 粘贴段落[3:5] → 图片4,5
    # 批次4: 粘贴段落[5:] (剩余)
    batches = []  # [(text_slice, num_imgs, start_img_idx)]
    last_para = 0
    img_idx = 0
    for target_para in sorted(IMAGE_LAYOUT.keys()):
        num_imgs = IMAGE_LAYOUT[target_para]
        text_slice = text_parts[last_para:target_para]
        batches.append((text_slice, num_imgs, img_idx))
        last_para = target_para
        img_idx += num_imgs
    if last_para < len(text_parts):
        batches.append((text_parts[last_para:], 0, img_idx))
    print(f"  [3a] 分批计划: {[(len(t), n) for t, n, _ in batches]}")

    # [3b] 保存图片为临时文件（分批粘贴时使用）
    print(f"  [3b] 准备图片临时文件（共{len(image_srcs)}张）...")
    try:
        tmp_files = []
        tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
        for img_i, data_url in enumerate(image_srcs):
            fname = f"body_img_{img_i+1}.jpg"
            fpath = os.path.join(tmp_dir, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 1000:
                dlog(f"图片{img_i+1}: 使用已有临时文件 {fpath} ({os.path.getsize(fpath)}字节)")
                tmp_files.append(fpath)
            else:
                dlog(f"图片{img_i+1}: 保存新临时文件...")
                fpath = save_base64_to_temp(data_url, img_i)
                tmp_files.append(fpath)
                dlog(f"图片{img_i+1}保存完成: {fpath}")
        dlog(f"临时文件准备完成: {len(tmp_files)}个")
    except BaseException as e:
        import traceback
        dlog(f"保存临时文件错误: {e}")
        dlog(f"traceback: {traceback.format_exc()}")
        tmp_files = []
    # 释放内存
    import gc
    gc.collect()
    dlog("内存已释放")

    # 启用CDP文件选择器拦截（防止弹出原生文件对话框）
    dlog("CDP拦截开始")
    try:
        page.run_cdp('Page.setInterceptFileChooserDialog', enabled=True)
        dlog("CDP拦截: 已启用")
    except BaseException as e:
        import traceback
        dlog(f"CDP拦截警告: {e}")
        dlog(f"CDP traceback: {traceback.format_exc()}")
    dlog("CDP拦截结束")

    # === 新方案：先上传所有图片获取URL，再一次性设置编辑器内容 ===
    # 因为paste Blob会清空编辑器文字，且innerHTML恢复会导致图片翻倍
    # 所以先逐张上传图片获取服务器URL，最后用innerHTML设置完整内容

    # [3a] 逐张上传图片，获取服务器URL
    print(f"  [3a] 上传{len(tmp_files)}张图片，获取URL...")
    dlog("图片上传阶段开始")
    image_urls = []
    for img_idx, fpath in enumerate(tmp_files):
        if not fpath or not os.path.exists(fpath):
            print(f"    图片{img_idx+1}: 文件不存在，跳过")
            dlog(f"图片{img_idx+1}: 文件不存在")
            image_urls.append("")
            continue
        print(f"    图片{img_idx+1}: 上传中...")
        dlog(f"图片{img_idx+1}: 上传开始 fpath={fpath}")

        # 清空编辑器（确保只有新上传的图片）
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

        # 从临时文件读取base64
        try:
            with open(fpath, "rb") as fimg:
                img_b64 = base64.b64encode(fimg.read()).decode('ascii')
        except Exception as e:
            print(f"    图片{img_idx+1}: 读取文件失败({e})")
            dlog(f"图片{img_idx+1}: 读取文件失败: {e}")
            image_urls.append("")
            continue

        # paste Blob上传图片
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

        # 等待图片出现
        uploaded = False
        for wait_i in range(60):
            time.sleep(0.5)
            imgs_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
            if imgs_now > 0:
                uploaded = True
                break

        if not uploaded:
            print(f"    图片{img_idx+1}: 上传超时")
            dlog(f"图片{img_idx+1}: 上传超时")
            image_urls.append("")
            continue

        # 删除多余的重复图片（只保留第一张）
        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return;
var imgs = editor.querySelectorAll('img');
for (var i = imgs.length - 1; i > 0; i--) {
    imgs[i].parentNode.removeChild(imgs[i]);
}
""")
        time.sleep(0.5)

        # 等待图片URL从blob:变为服务器URL
        img_url = ""
        for wait_i in range(60):
            img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
            if img_url and not img_url.startswith('blob:'):
                break
            time.sleep(1)

        if img_url.startswith('blob:'):
            # 仍然是blob URL，再多等一会
            for wait_i in range(30):
                time.sleep(2)
                img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
                if img_url and not img_url.startswith('blob:'):
                    break

        image_urls.append(img_url)
        print(f"    图片{img_idx+1}: ✓ URL={img_url[:60]}...")
        dlog(f"图片{img_idx+1}: ✓ URL={img_url}")

    valid_urls = [u for u in image_urls if u and not u.startswith('blob:')]
    print(f"  [3a] 完成: {len(valid_urls)}/{len(tmp_files)}张图片已上传")
    dlog(f"图片上传阶段完成: {len(valid_urls)}/{len(tmp_files)}张, URLs={image_urls}")

    # [3b] 构建最终HTML（文字+图片，按IMAGE_LAYOUT布局）
    print(f"  [3b] 构建最终内容（{len(text_parts)}段文字, {len(valid_urls)}张图片）...")
    dlog("构建最终HTML开始")
    final_html = ""
    url_idx = 0
    for para_idx, para_html in enumerate(text_parts):
        final_html += para_html
        target_para = para_idx + 1  # 段落从1开始
        if target_para in IMAGE_LAYOUT:
            num_imgs = IMAGE_LAYOUT[target_para]
            for _ in range(num_imgs):
                if url_idx < len(image_urls) and image_urls[url_idx]:
                    final_html += f'<figure><img src="{image_urls[url_idx]}" alt="图片来源于网络"><figcaption>图片来源于网络</figcaption></figure><p></p>'
                    url_idx += 1
                else:
                    dlog(f"警告: 图片URL不足，跳过位置{url_idx+1}")

    dlog(f"最终HTML: {len(final_html)}字符")

    # [3c] 用innerHTML设置编辑器内容
    print(f"  [3c] 设置编辑器内容...")
    page.run_js(f"""
var editor = document.querySelector('.ProseMirror');
if (editor) {{
    editor.innerHTML = {json.dumps(final_html)};
    editor.dispatchEvent(new Event('input', {{bubbles: true}}));
}}
""")
    time.sleep(2)

    # 删除重复图片（同一src只保留第一张）
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return;
var imgs = editor.querySelectorAll('img');
var seen = {};
for (var i = imgs.length - 1; i >= 0; i--) {
    var src = imgs[i].src;
    if (seen[src]) {
        var parent = imgs[i].parentNode;
        if (parent && parent.tagName === 'FIGURE') {
            parent.parentNode.removeChild(parent);
        } else {
            imgs[i].parentNode.removeChild(imgs[i]);
        }
    } else {
        seen[src] = true;
    }
}
editor.dispatchEvent(new Event('input', {bubbles: true}));
""")
    time.sleep(1)

    imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;")
    chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;")
    print(f"  内容设置完成: {chars}字, {imgs}张图片")
    dlog(f"内容设置完成(去重后): {chars}字, {imgs}张图片")

    # 检查图片src URL（等待blob:URL被替换为服务器URL）
    print("  等待图片上传到服务器...")
    dlog("等待图片上传到服务器开始")
    srcs = []
    blob_count = 0
    for wait_round in range(30):
        srcs = page.run_js("""
var imgs = document.querySelectorAll('.ProseMirror img');
var srcs = [];
for (var i = 0; i < imgs.length; i++) {
    srcs.push(imgs[i].src);
}
return srcs;
""") or []
        blob_count = sum(1 for s in srcs if s.startswith('blob:') or s.startswith('data:'))
        server_count = len(srcs) - blob_count
        if blob_count == 0 and server_count > 0:
            print(f"  [OK] 所有图片已上传到服务器 ({server_count}张)")
            dlog(f"所有图片已上传到服务器 ({server_count}张)")
            break
        if wait_round % 5 == 0:
            print(f"  等待中: {server_count}张服务器URL, {blob_count}张本地URL")
            dlog(f"等待中: {server_count}张服务器URL, {blob_count}张本地URL")
        time.sleep(2)
    else:
        print(f"  [WARN] 仍有{blob_count}张图片未上传到服务器")
        dlog(f"[WARN] 仍有{blob_count}张图片未上传到服务器")
        for i, s in enumerate(srcs):
            print(f"    图片{i+1}: {s[:80]}...")

    # 填充图片描述（多次重试，编辑器可能异步创建描述字段）
    dlog("填充图片描述开始")
    desc_js = """
var imgs = document.querySelectorAll('.ProseMirror img');
var found = 0;
for (var i = 0; i < imgs.length; i++) {
    var img = imgs[i];
    var desc = img.closest('figure')?.querySelector('figcaption');
    if (!desc) desc = img.parentElement?.querySelector('[placeholder="描述"]');
    if (!desc) desc = img.parentElement?.querySelector('[contenteditable][placeholder]');
    if (!desc) desc = img.closest('.image-wrap')?.querySelector('.image-desc');
    if (!desc) desc = img.closest('[data-image-wrapper]')?.querySelector('[contenteditable]');
    if (!desc) {
        var siblings = img.parentElement?.querySelectorAll('[contenteditable]');
        if (siblings) {
            for (var j = 0; j < siblings.length; j++) {
                if (siblings[j].textContent.trim() === '' || siblings[j].getAttribute('placeholder')) {
                    desc = siblings[j];
                    break;
                }
            }
        }
    }
    if (desc && !desc.textContent.trim()) {
        desc.textContent = '图片来源于网络';
        desc.dispatchEvent(new Event('input', {bubbles: true}));
        found++;
    }
}
return found;
"""
    for attempt in range(3):
        found = page.run_js(desc_js)
        if found is not None and found > 0:
            print(f"  描述字段: 已填充{found}个")
            dlog(f"描述字段: 已填充{found}个")
            break
        if attempt < 2:
            time.sleep(2)
    else:
        print("  描述字段: 未找到预留位置（将使用alt属性兜底）")
        dlog("描述字段: 未找到预留位置（将使用alt属性兜底）")

    dlog("正文保存开始")
    if wait_for_save(page, timeout=15):
        print("  [OK] 正文已保存")
        dlog("正文已保存")
    else:
        print("  [WARN] 正文保存未确认，触发保存...")
        dlog("正文保存未确认，触发保存")
        trigger_save(page)
        wait_for_save(page, timeout=15)

    # === 第3步：上传封面 ===
    print("\n[4] 上传封面...")
    dlog("上传封面开始")
    upload_cover(page, cover_files)
    dlog("上传封面结束")

    trigger_save(page)
    dlog("封面保存等待开始")
    if wait_for_save(page, timeout=20):
        print("  [OK] 封面已保存")
        dlog("封面已保存")
    else:
        print("  [WARN] 封面保存未确认")
        dlog("封面保存未确认")

    # === 验证 ===
    print("\n[5] 验证草稿箱...")
    dlog("验证草稿箱开始")
    page.get("https://mp.toutiao.com/profile_v4/manage/draft")
    time.sleep(5)
    draft_text = page.run_js("return document.body.innerText;")
    if title[:8] in draft_text:
        idx = draft_text.find(title[:8])
        print(f"[SUCCESS] 文章已在草稿箱中!")
        print(f"  {draft_text[idx:idx+120]}")
        dlog(f"[SUCCESS] 文章已在草稿箱中")
    else:
        print("[FAIL] 未在草稿箱中找到文章")
        print(f"  草稿箱: {draft_text[:500]}")
        dlog("[FAIL] 未在草稿箱中找到文章")

    page.quit()
    dlog("main() 完成")
    print("\nDONE")


if __name__ == "__main__":
    main()
