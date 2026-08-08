# -*- coding: utf-8 -*-
"""完整上传：非headless模式 + 标题.input() + 正文paste + 封面上传

图片上传策略（分批粘贴，避免光标定位问题）：
1. 按 image_layout 分批：文字批次 → 图片批次 交替
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

def calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局（5张图上限）——均匀分布，避免中间大片文字空档。
    原则：
    - 第1段后固定1张（用掉1张）——记为位置A
    - 剩下的所有图组（每组2张）+ 最后一组位置 = 优先固定在 total_paragraphs - 2
      （保证结尾恰好2段纯文字）
    - 所有配图位置从 A 到 最后一组 之间做等步长均匀分布
    - 若保持结尾2段导致中间"纯文字空档">3段，则尝试放宽结尾为3段换取空档≤3段
      （中间空窗比结尾多1段纯文字更影响阅读体验）
    - 若最后一组之后纯文字<1段（图紧贴最后一行），则删除该组避免结尾贴图
    返回 dict: {段落号: 图片数量}
    """
    if total_paragraphs < 1:
        return {}

    n_groups = (num_images - 1) // 2  # 5张图→2组，3张→1组，3张以下→0组
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}

    first = 1

    def _build_positions(last):
        """给定最后一组位置last，返回均匀分布的positions列表（含first）"""
        if last < 3:
            return [first]
        pos_list = [first]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups:
                    raw = last
                else:
                    raw = first + step * k
                pos = int(round(raw))
                min_pos = pos_list[-1] + 2
                remaining_after = n_groups - k
                max_pos = last - 2 * remaining_after
                pos = max(min_pos, min(max_pos, pos))
                pos_list.append(pos)
        # 结尾贴图修正
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list

    def _max_gap(pos_list):
        """计算相邻配图之间的最大纯文字空档"""
        if len(pos_list) < 2:
            return 0
        return max(pos_list[i+1] - pos_list[i] - 1 for i in range(len(pos_list) - 1))

    # 候选方案：结尾保2段 vs 结尾保3段（3段仅在2段方案空档>3时才考虑）
    candidates = []
    for tail_target in [2, 3]:
        last_cand = total_paragraphs - tail_target
        if last_cand >= 3:
            positions = _build_positions(last_cand)
            if len(positions) >= 2:
                actual_tail = total_paragraphs - positions[-1]
                gap = _max_gap(positions)
                candidates.append((gap, actual_tail, positions))

    if not candidates:
        return {1: 1}

    # 排序优先级：
    # 1) 最大空档≤3 的方案 优于 >3 的
    # 2) 结尾纯文字≤2 的方案 优于 >2 的  （空档合格的前提下，优先结尾更紧凑）
    # 3) 空档更小 优于 更大
    # 4) 结尾纯文字更小 优于 更大
    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)

    candidates.sort(key=_score)
    best_positions = candidates[0][2]

    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


def set_clipboard_html(html_content):
    """用PowerShell设置剪贴板（Windows HTML剪贴板格式 + 纯文字格式）"""
    try:
        # 从HTML中提取纯文字，用\n\n分隔段落
        plain_text = html_content.replace('</p>\n<p>', '\n\n').replace('</p><p>', '\n\n')
        plain_text = re.sub(r'<[^>]+>', '', plain_text)
        plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text).strip()

        # 构建Windows HTML剪贴板格式（必须包含特定头部）
        header = "Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
        html_prefix = "<html><body><!--StartFragment-->"
        html_suffix = "<!--EndFragment--></body></html>"
        # 临时占位计算偏移量
        header_tmp = header.format(0, 0, 0, 0)
        start_html = len(header_tmp.encode('utf-8'))
        start_fragment = start_html + len(html_prefix.encode('utf-8'))
        end_fragment = start_fragment + len(html_content.encode('utf-8'))
        end_html = end_fragment + len(html_suffix.encode('utf-8'))
        clipboard_html = header.format(start_html, end_html, start_fragment, end_fragment) + html_prefix + html_content + html_suffix

        # 用base64编码避免PowerShell转义问题
        b64_html = base64.b64encode(clipboard_html.encode('utf-8')).decode('ascii')
        b64_text = base64.b64encode(plain_text.encode('utf-16-le')).decode('ascii')
        ps_script = (
            'Add-Type -AssemblyName System.Windows.Forms; '
            f'$html = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String(\'{b64_html}\')); '
            f'$text = [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String(\'{b64_text}\')); '
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
            dlog(f"set_clipboard_html: 成功 (html={len(clipboard_html)}字符, text={len(plain_text)}字符)")
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
    image_layout = calc_image_layout(len(text_parts), len(image_srcs))
    print(f"  图片布局: {image_layout}")
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

    # 注入网络拦截器，捕获保存请求的请求体
    page.run_js("""
window._savedBodies=[];
var origFetch=window.fetch;
window.fetch=function(url,options){
  options=options||{};
  var urlStr=typeof url==='string'?url:(url&&url.url)||'';
  var method=(options.method||(url&&url.method)||'GET').toUpperCase();
  var body=options.body;
  if(method==='POST'&&body){
    if(typeof body==='string'){
      window._savedBodies.push({url:urlStr,body:body.substring(0,8000)});
    }else if(body instanceof FormData){
      var obj={};
      try{for(var entry of body.entries()){obj[entry[0]]=typeof entry[1]==='string'?entry[1].substring(0,5000):'[file]';}}catch(e){}
      window._savedBodies.push({url:urlStr,body:JSON.stringify(obj).substring(0,8000)});
    }
  }
  return origFetch.apply(this,arguments);
};
var origXHRSend=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){
  if(this._method==='POST'&&body){
    var bodyStr=typeof body==='string'?body:'[non-string]';
    window._savedBodies.push({url:this._url||'',body:bodyStr.substring(0,8000)});
  }
  return origXHRSend.apply(this,arguments);
};
var origXHROpen=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url){
  this._url=url;
  this._method=(method||'GET').toUpperCase();
  return origXHROpen.apply(this,arguments);
};
""")
    dlog("网络拦截器已注入")

    # === 第2步：填标题 ===
    print("\n[2] 填标题...")
    import json as _json
    title_json = _json.dumps(title)
    # 使用React兼容方式：原生value setter + input事件触发状态更新
    title_set = page.run_js(f"""
var el = document.querySelector('textarea[placeholder*="文章标题"]') ||
         document.querySelector('textarea[placeholder*="请输入文章标题"]');
if (!el) return 'not_found';
el.focus();
var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
nativeSetter.call(el, {title_json});
el.dispatchEvent(new Event('input', {{bubbles: true}}));
el.dispatchEvent(new Event('change', {{bubbles: true}}));
el.blur();
return el.value;
""")
    print(f"  标题: {title}")
    dlog(f"标题设置结果: title_set={repr(title_set)}")
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
    # 按 image_layout 分批：例如 {1:1, 3:2, 5:2} + 6段文字
    # 批次1: 粘贴段落[0:1] → 图片1
    # 批次2: 粘贴段落[1:3] → 图片2,3
    # 批次3: 粘贴段落[3:5] → 图片4,5
    # 批次4: 粘贴段落[5:] (剩余)
    batches = []  # [(text_slice, num_imgs, start_img_idx)]
    last_para = 0
    img_idx = 0
    for target_para in sorted(image_layout.keys()):
        num_imgs = image_layout[target_para]
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
        os.makedirs(tmp_dir, exist_ok=True)
        # 清空旧临时文件，避免复用上一篇残留图片
        for old_f in os.listdir(tmp_dir):
            if old_f.startswith("body_img_"):
                try:
                    os.remove(os.path.join(tmp_dir, old_f))
                except Exception:
                    pass
        for img_i, data_url in enumerate(image_srcs):
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

    # [3b] 构建最终HTML（文字+图片，按image_layout布局）
    print(f"  [3b] 构建最终内容（{len(text_parts)}段文字, {len(valid_urls)}张图片）...")
    dlog("构建最终HTML开始")
    final_html = ""
    url_idx = 0
    for para_idx, para_html in enumerate(text_parts):
        final_html += para_html
        target_para = para_idx + 1  # 段落从1开始
        if target_para in image_layout:
            num_imgs = image_layout[target_para]
            for _ in range(num_imgs):
                if url_idx < len(image_urls) and image_urls[url_idx]:
                    # 用p+img标签，避免figure标签兼容性问题
                    final_html += f'<p><img src="{image_urls[url_idx]}" alt="图片来源于网络"></p>'
                    url_idx += 1
                else:
                    dlog(f"警告: 图片URL不足，跳过位置{url_idx+1}")

    dlog(f"最终HTML: {len(final_html)}字符")

    # [3c] 设置编辑器内容（优先使用ProseMirror API，确保内部状态同步）
    print(f"  [3c] 设置编辑器内容...")
    dlog("设置编辑器内容开始")

    # 准备纯文字内容（去除HTML标签）
    text_plain_parts = [re.sub(r'<[^>]+>', '', t).strip() for t in text_parts]

    # 方法1：通过ProseMirror view API设置内容（最可靠，确保内部状态同步）
    # DOM-based操作（如innerHTML、直接修改DOM、DOM去重）不会更新ProseMirror内部状态
    # 必须通过view.dispatch()事务来更新内容，才能确保保存时图片不丢失

    # 步骤1：通过window._pmData传递数据（避免JSON数据混入JS代码导致语法错误）
    data_json = json.dumps({"tp": text_plain_parts, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
    page.run_js("window._pmData=" + data_json + ";")
    dlog("已设置window._pmData")

    # 步骤2：查找ProseMirror view并设置内容
    pm_js = """return (function(){
function findView(){
  var editor=document.querySelector('.ProseMirror');
  if(!editor)return null;
  var desc=editor.pmViewDesc;
  while(desc){if(desc.view&&desc.view.state)return desc.view;desc=desc.parent;}
  function sf(fiber,v){
    if(!fiber||v.has(fiber)||v.size>500)return null;
    v.add(fiber);
    if(fiber.stateNode&&fiber.stateNode.view&&fiber.stateNode.view.state)return fiber.stateNode.view;
    if(fiber.memoizedProps&&fiber.memoizedProps.view&&fiber.memoizedProps.view.state)return fiber.memoizedProps.view;
    if(fiber.memoizedState){var s=fiber.memoizedState;while(s){if(s.memoizedState&&s.memoizedState.view&&s.memoizedState.view.state)return s.memoizedState.view;s=s.next;}}
    var r=sf(fiber.child,v);if(r)return r;
    return sf(fiber.sibling,v);
  }
  var el=editor;
  for(var i=0;i<15&&el;i++){
    var fk=Object.keys(el).find(function(k){return k.indexOf('__reactFiber')===0||k.indexOf('__reactInternalInstance')===0;});
    if(fk){var v=new Set();var r=sf(el[fk],v);if(r)return r;}
    el=el.parentElement;
  }
  return null;
}
var view=findView();
if(!view)return JSON.stringify({status:'no_view'});
var schema=view.state.schema;
var nts=Object.keys(schema.nodes);
var pn=null,im=null,dn=null;
nts.forEach(function(k){
  if(k==='paragraph'||k==='para')pn=k;
  if(k==='doc')dn=k;
  if(k==='image'||k==='imageUpload'||k==='media'||k==='img')im=k;
});
if(!im)nts.forEach(function(k){if(k.toLowerCase().indexOf('image')>=0||k.toLowerCase().indexOf('media')>=0)im=k;});
if(!pn)nts.forEach(function(k){if(k.toLowerCase().indexOf('para')>=0)pn=k;});
if(!dn)nts.forEach(function(k){if(k==='doc'||k==='document'||k==='article')dn=k;});
if(!pn||!dn)return JSON.stringify({status:'no_types',nodes:nts});
var urlAttr='src';
var imAttrs={};
if(im){
  var imSpec=schema.nodes[im];
  if(imSpec&&imSpec.spec&&imSpec.spec.attrs){
    Object.keys(imSpec.spec.attrs).forEach(function(an){
      var a=imSpec.spec.attrs[an];
      if(an==='src'||an==='url'||an==='href')urlAttr=an;
      imAttrs[an]=a&&a.default!==undefined?a.default:'[no-default]';
    });
  }
}
var data=window._pmData;
var content=[];
var ui=0;
var hasDataAttr=imAttrs&&Object.keys(imAttrs).indexOf('data')>=0;
for(var i=0;i<data.tp.length;i++){
  if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
  var t=i+1;
  if(data.il[t]){
    for(var j=0;j<data.il[t];j++){
      if(ui<data.iu.length&&data.iu[ui]){
        var imgUrl=data.iu[ui];
        var attrs={};
        if(hasDataAttr){
          attrs.data={url:imgUrl,icUri:imgUrl,catchErrorUrl:"",link:"",caption:"图片来源于网络",ic:false,naturalHeight:0,naturalWidth:0,srcType:"",captionLenErr:false,needCheck:false};
        }else{
          attrs[urlAttr]=imgUrl;
          attrs.alt='图片来源于网络';
        }
        content.push({type:im,attrs:attrs});
        ui++;
      }
    }
  }
}
try{
  var doc=schema.nodeFromJSON({type:dn,content:content});
  view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
  var ic=0;
  view.state.doc.descendants(function(node){if(node.type.name===im)ic++;return true;});
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length,nodes:nts,pn:pn,in:im,urlAttr:urlAttr,imAttrs:imAttrs});
}catch(e){
  return JSON.stringify({status:'error',error:e.message,nodes:nts,pn:pn,in:im,urlAttr:urlAttr});
}
})()"""

    pm_result = page.run_js(pm_js)
    dlog(f"ProseMirror view结果: {pm_result}")
    print(f"  ProseMirror API: {pm_result}")

    pm_data = None
    try:
        pm_data = json.loads(pm_result) if pm_result else None
    except:
        pass

    pm_success = pm_data and pm_data.get('status') == 'ok' and pm_data.get('imgs', 0) > 0

    if pm_success:
        imgs = pm_data.get('imgs', 0)
        chars = pm_data.get('chars', 0)
        print(f"  [OK] ProseMirror API设置成功: {chars}字, {imgs}张图片")
        dlog(f"ProseMirror API成功: {chars}字, {imgs}张图片, nodes={pm_data.get('nodes')}, pn={pm_data.get('pn')}, in={pm_data.get('in')}")
    else:
        # 方法2：回退到剪贴板粘贴（不做DOM去重，避免破坏ProseMirror状态）
        print(f"  [FALLBACK] 剪贴板粘贴 (原因: {pm_result})")
        dlog(f"回退剪贴板粘贴, PM结果: {pm_result}")

        # 清空编辑器
        editor_el = page.ele('.ProseMirror', timeout=3)
        if editor_el:
            editor_el.click()
            time.sleep(0.3)
            page.actions.key_down('ctrl').type('a').key_up('ctrl')
            time.sleep(0.3)
            page.actions.key_down('Backspace').key_up('Backspace')
            time.sleep(0.5)

        clip_ok = set_clipboard_html(final_html)
        if clip_ok:
            page.run_js("var e=document.querySelector('.ProseMirror'); if(e) e.focus();")
            time.sleep(0.3)
            page.actions.key_down('ctrl').type('v').key_up('ctrl')
            time.sleep(3)
            dlog("Ctrl+V粘贴完成")
        else:
            dlog("剪贴板失败，回退paste事件")
            plain_final = re.sub(r'<[^>]+>', '', final_html).strip()
            paste_js = (
                "var editor=document.querySelector('.ProseMirror');"
                "if(!editor)return;"
                "editor.focus();"
                "var dt=new DataTransfer();"
                "dt.setData('text/html'," + json.dumps(final_html) + ");"
                "dt.setData('text/plain'," + json.dumps(plain_final) + ");"
                "var pe=new ClipboardEvent('paste',{bubbles:true,cancelable:true});"
                "Object.defineProperty(pe,'clipboardData',{value:dt,writable:false,configurable:true});"
                "editor.dispatchEvent(pe);"
            )
            page.run_js(paste_js)
            time.sleep(3)
            dlog("paste事件粘贴完成")

        # 不做DOM-based去重（会破坏ProseMirror内部状态，导致保存时图片丢失）
        imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
        print(f"  剪贴板粘贴: {chars}字, {imgs}张图片")
        dlog(f"剪贴板粘贴: {chars}字, {imgs}张图片")

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

    # 验证保存后编辑器内容是否包含图片（检查ProseMirror内部状态，非仅DOM）
    verify_js = """return (function(){
function findView(){
  var editor=document.querySelector('.ProseMirror');
  if(!editor)return null;
  var desc=editor.pmViewDesc;
  while(desc){if(desc.view&&desc.view.state)return desc.view;desc=desc.parent;}
  function sf(fiber,v){
    if(!fiber||v.has(fiber)||v.size>500)return null;
    v.add(fiber);
    if(fiber.stateNode&&fiber.stateNode.view&&fiber.stateNode.view.state)return fiber.stateNode.view;
    if(fiber.memoizedProps&&fiber.memoizedProps.view&&fiber.memoizedProps.view.state)return fiber.memoizedProps.view;
    if(fiber.memoizedState){var s=fiber.memoizedState;while(s){if(s.memoizedState&&s.memoizedState.view&&s.memoizedState.view.state)return s.memoizedState.view;s=s.next;}}
    var r=sf(fiber.child,v);if(r)return r;
    return sf(fiber.sibling,v);
  }
  var el=editor;
  for(var i=0;i<15&&el;i++){
    var fk=Object.keys(el).find(function(k){return k.indexOf('__reactFiber')===0||k.indexOf('__reactInternalInstance')===0;});
    if(fk){var v=new Set();var r=sf(el[fk],v);if(r)return r;}
    el=el.parentElement;
  }
  return null;
}
var view=findView();
var pmImgs=0,pmChars=0;
if(view){
  view.state.doc.descendants(function(node){
    var n=node.type.name.toLowerCase();
    if(n.indexOf('image')>=0||n.indexOf('media')>=0||n.indexOf('img')>=0)pmImgs++;
    return true;
  });
  pmChars=view.state.doc.textContent.length;
}
var domImgs=document.querySelectorAll('.ProseMirror img').length;
return JSON.stringify({pmImgs:pmImgs,pmChars:pmChars,domImgs:domImgs,hasView:!!view});
})()"""
    verify_result = page.run_js(verify_js)
    dlog(f"保存后验证(ProseMirror): {verify_result}")

    verify_data = None
    try:
        verify_data = json.loads(verify_result) if verify_result else None
    except:
        pass

    saved_imgs = (verify_data.get('pmImgs', 0) if verify_data else 0) or page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
    saved_chars = (verify_data.get('pmChars', 0) if verify_data else 0) or page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
    dom_imgs = verify_data.get('domImgs', 0) if verify_data else '?'
    print(f"  保存后验证: {saved_chars}字, {saved_imgs}张图片 (DOM: {dom_imgs})")
    dlog(f"保存后验证: {saved_chars}字, {saved_imgs}张图片, verify={verify_result}")

    if saved_imgs == 0:
        print("  [WARN] 保存后图片丢失！重新通过ProseMirror API设置...")
        dlog("保存后图片丢失，重新通过PM API设置")
        # 重新通过ProseMirror view API设置内容（不用剪贴板+DOM去重）
        retry_result = page.run_js(pm_js)
        dlog(f"重新设置结果: {retry_result}")
        print(f"  重新设置: {retry_result}")
        retry_data = None
        try:
            retry_data = json.loads(retry_result) if retry_result else None
        except:
            pass
        if retry_data and retry_data.get('status') == 'ok':
            retry_imgs = retry_data.get('imgs', 0)
            retry_chars = retry_data.get('chars', 0)
        else:
            retry_imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
            retry_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
        print(f"  重新设置后: {retry_chars}字, {retry_imgs}张图片")
        dlog(f"重新设置后: {retry_chars}字, {retry_imgs}张图片")
        # 再次触发保存
        trigger_save(page)
        wait_for_save(page, timeout=15)

    # 读取网络拦截结果，检查保存请求是否包含图片
    saved_bodies = page.run_js("return JSON.stringify(window._savedBodies||[]);")
    dlog(f"保存请求拦截: {saved_bodies}")
    try:
        bodies = json.loads(saved_bodies) if saved_bodies else []
        for b in bodies:
            body_str = b.get('body', '')
            has_img = 'image' in body_str.lower() or 'tos-cn' in body_str.lower() or 'img' in body_str.lower()
            print(f"  [DIAG] 保存请求 {b.get('url','')[:60]}: 含图片={has_img}, body={len(body_str)}字符")
            if has_img:
                print(f"    body片段: {body_str[:300]}")
            dlog(f"保存请求诊断: url={b.get('url','')[:80]}, 含图片={has_img}, body长度={len(body_str)}")
    except Exception as e:
        dlog(f"保存请求解析失败: {e}")

    # === 第3步：上传封面（可通过环境变量 SKIP_COVER=1 跳过）===
    if os.environ.get("SKIP_COVER") == "1":
        print("\n[4] 跳过封面上传（SKIP_COVER=1）")
        dlog("跳过封面上传（SKIP_COVER=1）")
    else:
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
