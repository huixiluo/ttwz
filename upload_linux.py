# -*- coding: utf-8 -*-
"""Linux headless 版 upload_visible.py
- 使用 playwright 下载的 chromium
- headless 模式（sandbox 无显示）
- 跳过 PowerShell 剪贴板（强制走 ProseMirror JS API / paste 事件）
"""
import os, re, json, time, base64, sys
from DrissionPage import ChromiumPage, ChromiumOptions

# 复用 upload_visible.py 中的工具函数
import upload_visible as uv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

# playwright chromium 路径
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

DEBUG_LOG = os.path.join(BASE_DIR, "debug.log")


def dlog(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def set_clipboard_html_noop(html_content):
    """Linux 无 PowerShell，直接返回 False 强制走 paste 事件兜底"""
    dlog("set_clipboard_html: 跳过（Linux 无 PowerShell），将走 paste 事件")
    return False


# 替换 uv 模块中的 PowerShell 版本
uv.set_clipboard_html = set_clipboard_html_noop


def force_save(page, timeout=60):
    """Linux headless 下等待自动保存完成

    关键修复：PM API 设置内容后，React 的保存状态可能未同步。
    通过在编辑器末尾模拟真实按键（输入空格再删除），
    触发完整的 ProseMirror input pipeline → React 状态同步 → 自动保存 debounce。
    之后安静等待保存完成，不再反复 dispatch 事件。
    """
    import time as _t
    dlog("force_save: 开始")
    print("  [save] 触发保存...")

    # 清空已捕获的网络请求
    page.run_js("window._savedBodies = [];")
    dlog("force_save: 清空已捕获请求")

    # 第1步：模拟真实按键，触发 React 状态同步
    # 在编辑器末尾输入一个空格再删除，模拟真实用户输入
    # 这会触发 ProseMirror 的 inputRules + transaction → React re-render → auto-save debounce
    dlog("force_save: 模拟真实按键触发 React 同步")
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.focus();
    // 将光标移到文档末尾
    var sel = window.getSelection();
    var range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
}
""")
    time.sleep(0.5)

    # 通过 CDP Input.dispatchKeyEvent 模拟真实按键
    # 这样 ProseMirror 的 editHandler 会处理 input 事件，触发完整的状态更新
    try:
        # 输入一个空格
        page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space',
                      windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
        page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space',
                      windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
        time.sleep(0.3)
        # 删除空格
        page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key='Backspace', code='Backspace',
                      windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
        page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key='Backspace', code='Backspace',
                      windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
        time.sleep(0.5)
        dlog("force_save: 已模拟空格输入+删除")
    except Exception as e:
        dlog(f"force_save: CDP按键失败({e})，回退到 dispatch input 事件")
        page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.dispatchEvent(new Event('input', {bubbles: true}));
    editor.dispatchEvent(new Event('change', {bubbles: true}));
}
""")

    # 第2步：安静等待自动保存完成
    dlog("force_save: 等待自动保存完成")
    print("  [save] 等待自动保存完成...")

    last_status = ""
    save_request_seen = False
    for i in range(timeout):
        _t.sleep(1)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('保存失败') !== -1) return 'FAIL';
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'IDLE';
""") or ""

        # 检查是否有保存API请求被捕获
        save_api_count = page.run_js("""
var bodies = window._savedBodies || [];
var count = 0;
for (var i = 0; i < bodies.length; i++) {
    var u = bodies[i].url || '';
    if (u.indexOf('save') >= 0 || u.indexOf('draft') >= 0 || u.indexOf('article') >= 0) {
        if (u.indexOf('monitor') < 0 && u.indexOf('collect') < 0 && u.indexOf('feedback') < 0) {
            count++;
        }
    }
}
return count;
""") or 0
        if save_api_count > 0 and not save_request_seen:
            save_request_seen = True
            dlog(f"force_save: [{i}s] 检测到保存API请求 ({save_api_count}个)")
            print(f"  [save] [{i}s] 检测到保存API请求")

        if i % 10 == 0:
            print(f"  [save] [{i}s] status={status} save_apis={save_api_count}")
            dlog(f"force_save: [{i}s] status={status} save_apis={save_api_count}")
        if status != last_status:
            dlog(f"force_save: 状态变化 {last_status} -> {status} (at {i}s)")
            last_status = status
        if status == 'SAVED':
            dlog(f"force_save: 保存确认 (status={status}, 用时{i}s)")
            print(f"  [save] 保存确认 (用时{i}s)")
            return True
        if status == 'FAIL':
            dlog(f"force_save: 保存失败")
            print(f"  [save] 保存失败！")
            fail_detail = page.run_js("""
var msg = document.querySelector('.byte-message-error');
return msg ? msg.innerText : 'no_detail';
""") or ""
            print(f"  [save] 失败详情: {fail_detail}")
            dlog(f"保存失败详情: {fail_detail}")
            # 捕获保存API响应
            save_resp = page.run_js("return JSON.stringify(window._saveResponses||[]);") or "[]"
            dlog(f"force_save: 保存API响应: {save_resp}")
            try:
                srs = json.loads(save_resp)
                for sr in srs:
                    print(f"  [save] 响应: HTTP {sr.get('status','?')} - {sr.get('body','')[:300]}")
            except Exception:
                pass
            return False
    dlog(f"force_save: 保存超时 (最后status={status}, save_apis={save_api_count})")
    print(f"  [save] 保存超时 (最后status={status}, save_apis={save_api_count})")
    return False


def main():
    with open(DEBUG_LOG, "w", encoding="utf-8") as f:
        f.write(f"=== Linux headless 上传开始 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    dlog("main() 开始")

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        art = json.load(f)[0]
    title = art["title"][:30]
    cover_files = art["cover_files"]
    html_path = art["html_file"]
    print(f"文章: {title}")
    dlog(f"文章: {title}, html={html_path}")

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
    image_layout = uv.calc_image_layout(len(text_parts), len(image_srcs))
    print(f"  图片布局: {image_layout}")
    dlog(f"正文: {len(text_parts)}段, {len(image_srcs)}张图, 布局={image_layout}")

    # 启动浏览器（headless + playwright chromium）
    print("[1] 启动浏览器 (Linux headless)...")
    dlog(f"浏览器路径: {CHROME_PATH}, exists={os.path.exists(CHROME_PATH)}")
    co = ChromiumOptions()
    co.set_browser_path(CHROME_PATH)
    co.headless(True)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--window-size=1920,1080")
    # 防止 headless 模式下后台节流（自动保存依赖定时器）
    co.set_argument("--disable-background-timer-throttling")
    co.set_argument("--disable-backgrounding-occluded-windows")
    co.set_argument("--disable-renderer-backgrounding")
    co.set_address("127.0.0.1:9225")
    co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile"))
    page = ChromiumPage(co)
    page.get("https://mp.toutiao.com")
    time.sleep(2)

    # 覆盖 visibility API，防止 headless 模式下页面被判定为隐藏导致定时器节流
    page.run_js("""
Object.defineProperty(document, 'hidden', {value: false, writable: false, configurable: true});
Object.defineProperty(document, 'visibilityState', {value: 'visible', writable: false, configurable: true});
document.dispatchEvent(new Event('visibilitychange'));
""")
    dlog("visibility API 已覆盖")
    cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
    for name, value in cookies.items():
        try:
            page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        except Exception:
            pass
    page.get("https://mp.toutiao.com")
    time.sleep(3)
    print(f"  URL: {page.url}")
    dlog(f"登录后URL: {page.url}")

    # 检查登录状态
    login_ok = page.run_js("""
        var url = window.location.href;
        var body = document.body ? document.body.innerText : '';
        if (url.indexOf('login') >= 0 || url.indexOf('passport') >= 0) return 'NOT_LOGIN';
        if (body.indexOf('扫码登录') >= 0 || body.indexOf('账号密码登录') >= 0) return 'NOT_LOGIN';
        return 'LOGIN_OK';
    """)
    print(f"  登录状态: {login_ok}")
    dlog(f"登录状态: {login_ok}")
    if login_ok != 'LOGIN_OK':
        print("  [FAIL] cookies 已失效，无法登录头条")
        dlog("cookies 已失效，无法登录头条")
        page.quit()
        return False

    # 创建新文章
    print("\n[1.5] 创建新文章...")
    page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
    time.sleep(6)
    editor_ready = False
    for i in range(20):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            print("  [OK] 编辑器已就绪")
            editor_ready = True
            break
        time.sleep(1)
    if not editor_ready:
        print("  [FAIL] 编辑器未就绪")
        dlog("编辑器未就绪")
        page.quit()
        return False
    dlog("编辑器已就绪")

    try:
        btn = page.ele("text:关闭", timeout=2)
        if btn:
            btn.click()
            time.sleep(1)
    except Exception:
        pass
    try:
        btn = page.ele("text:不恢复", timeout=2)
        if btn:
            btn.click()
            time.sleep(1)
    except Exception:
        pass

    # 注入网络拦截器（捕获请求+响应）
    page.run_js("""
window._savedBodies=[];
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
  var method=(options.method||(url&&url.method)||'GET').toUpperCase();
  var body=options.body;
  if(method==='POST'&&body){
    if(typeof body==='string'){
      window._savedBodies.push({url:urlStr,body:body.substring(0,20000)});
    }else if(body instanceof FormData){
      var obj={};
      try{for(var entry of body.entries()){obj[entry[0]]=typeof entry[1]==='string'?entry[1].substring(0,15000):'[file]';}}catch(e){}
      window._savedBodies.push({url:urlStr,body:JSON.stringify(obj).substring(0,20000)});
    }
  }
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
var origXHRSend=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){
  if(this._method==='POST'&&body){
    var bodyStr=typeof body==='string'?body:'[non-string]';
    window._savedBodies.push({url:this._url||'',body:bodyStr.substring(0,20000)});
  }
  var xhr=this;
  var origOnLoad=this.onload;
  this.addEventListener('load',function(){
    if(isSaveUrl(xhr._url)){
      try{
        window._saveResponses.push({url:xhr._url,status:xhr.status,body:(xhr.responseText||'').substring(0,5000)});
      }catch(e){}
    }
  });
  return origXHRSend.apply(this,arguments);
};
var origXHROpen=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url){
  this._url=url;
  this._method=(method||'GET').toUpperCase();
  return origXHROpen.apply(this,arguments);
};
""")
    dlog("网络拦截器已注入（含响应捕获）")

    # 填标题
    print("\n[2] 填标题...")
    import json as _json
    title_json = _json.dumps(title)
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
    dlog(f"标题设置结果: {repr(title_set)}")
    time.sleep(3)

    if uv.wait_for_save(page, timeout=10):
        print("  [OK] 标题已保存")
    else:
        print("  [WARN] 标题保存未确认")

    # 填正文
    print("\n[3] 填正文...")
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

    time.sleep(1)

    # 保存图片为临时文件
    print(f"  [3b] 准备图片临时文件（共{len(image_srcs)}张）...")
    try:
        tmp_files = []
        tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        for old_f in os.listdir(tmp_dir):
            if old_f.startswith("body_img_"):
                try:
                    os.remove(os.path.join(tmp_dir, old_f))
                except Exception:
                    pass
        for img_i, data_url in enumerate(image_srcs):
            dlog(f"图片{img_i+1}: 保存临时文件...")
            fpath = uv.save_base64_to_temp(data_url, img_i)
            tmp_files.append(fpath)
            dlog(f"图片{img_i+1}保存完成: {fpath}")
        dlog(f"临时文件准备完成: {len(tmp_files)}个")
    except BaseException as e:
        import traceback
        dlog(f"保存临时文件错误: {e}")
        dlog(f"traceback: {traceback.format_exc()}")
        tmp_files = []
    import gc
    gc.collect()

    try:
        page.run_cdp('Page.setInterceptFileChooserDialog', enabled=True)
        dlog("CDP拦截: 已启用")
    except BaseException as e:
        dlog(f"CDP拦截警告: {e}")

    # 逐张上传图片获取URL
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

        try:
            with open(fpath, "rb") as fimg:
                img_b64 = base64.b64encode(fimg.read()).decode('ascii')
        except Exception as e:
            print(f"    图片{img_idx+1}: 读取文件失败({e})")
            dlog(f"图片{img_idx+1}: 读取文件失败: {e}")
            image_urls.append("")
            continue

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
            dlog(f"图片{img_idx+1}: 上传超时")
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

        if img_url.startswith('blob:'):
            for wait_i in range(30):
                time.sleep(2)
                img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
                if img_url and not img_url.startswith('blob:'):
                    break

        image_urls.append(img_url)
        print(f"    图片{img_idx+1}: OK URL={img_url[:60]}...")
        dlog(f"图片{img_idx+1}: OK URL={img_url}")

    valid_urls = [u for u in image_urls if u and not u.startswith('blob:')]
    print(f"  [3a] 完成: {len(valid_urls)}/{len(tmp_files)}张图片已上传")
    dlog(f"图片上传阶段完成: {len(valid_urls)}/{len(tmp_files)}张, URLs={image_urls}")

    # 构建最终HTML
    print(f"  [3b] 构建最终内容（{len(text_parts)}段文字, {len(valid_urls)}张图片）...")
    dlog("构建最终HTML开始")
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
                else:
                    dlog(f"警告: 图片URL不足，跳过位置{url_idx+1}")

    dlog(f"最终HTML: {len(final_html)}字符")

    # 通过 ProseMirror view API 设置内容
    print(f"  [3c] 设置编辑器内容（ProseMirror API）...")
    dlog("设置编辑器内容开始")

    text_plain_parts = [re.sub(r'<[^>]+>', '', t).strip() for t in text_parts]

    data_json = json.dumps({"tp": text_plain_parts, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
    page.run_js("window._pmData=" + data_json + ";")
    dlog("已设置window._pmData")

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
  // 关键：dispatch后立即在DOM上触发input事件，让React组件感知内容变化
  // 否则React的word count显示0字，自动保存会因"空内容"失败
  var editorEl=document.querySelector('.ProseMirror');
  if(editorEl){
    editorEl.dispatchEvent(new Event('input',{bubbles:true}));
    editorEl.dispatchEvent(new Event('change',{bubbles:true}));
    // 有些React封装监听ProseMirror特有的selectionupdate
    editorEl.dispatchEvent(new Event('selectionupdate',{bubbles:true}));
  }
  // 也通过view.dom触发
  if(view.dom){
    view.dom.dispatchEvent(new Event('input',{bubbles:true}));
  }
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
    except Exception:
        pass

    pm_success = pm_data and pm_data.get('status') == 'ok' and pm_data.get('imgs', 0) > 0

    if pm_success:
        imgs = pm_data.get('imgs', 0)
        chars = pm_data.get('chars', 0)
        print(f"  [OK] ProseMirror API设置成功: {chars}字, {imgs}张图片")
        dlog(f"ProseMirror API成功: {chars}字, {imgs}张图片")

        # 检查React组件的word count是否更新（关键诊断）
        time.sleep(2)
        wc = page.run_js("""
            var footer = document.querySelector('.publish-footer, .garr-footer-publish-content');
            if (!footer) return 'no_footer';
            var text = footer.innerText;
            var m = text.match(/共\\s*(\\d+)\\s*字/);
            return m ? parseInt(m[1]) : 'no_match:' + text.substring(0, 100);
        """)
        print(f"  [WC] React word count: {wc}")
        dlog(f"React word count: {wc}")
        if isinstance(wc, int) and wc > 0:
            print(f"  [OK] React已感知内容变化")
        else:
            print(f"  [WARN] React未感知内容变化，再触发input事件...")
            dlog(f"React word count异常: {wc}，再触发input事件")
            # 多次触发input事件
            for _ in range(3):
                page.run_js("""
                    var editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                        editor.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                """)
                time.sleep(1)
            # 再次检查
            wc2 = page.run_js("""
                var footer = document.querySelector('.publish-footer, .garr-footer-publish-content');
                if (!footer) return -1;
                var m = footer.innerText.match(/共\\s*(\\d+)\\s*字/);
                return m ? parseInt(m[1]) : -1;
            """)
            print(f"  [WC] 再次检查word count: {wc2}")
            dlog(f"再次检查word count: {wc2}")
    else:
        # paste 事件兜底（纯JS，无需 PowerShell）
        print(f"  [FALLBACK] paste 事件粘贴 (PM结果: {pm_result})")
        dlog(f"回退paste事件, PM结果: {pm_result}")
        editor_el = page.ele('.ProseMirror', timeout=3)
        if editor_el:
            editor_el.click()
            time.sleep(0.3)
            page.actions.key_down('ctrl').type('a').key_up('ctrl')
            time.sleep(0.3)
            page.actions.key_down('Backspace').key_up('Backspace')
            time.sleep(0.5)

        # 走 paste 事件（uv.set_clipboard_html 已被替换为返回 False）
        clip_ok = uv.set_clipboard_html(final_html)
        if not clip_ok:
            dlog("走 paste 事件兜底")
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

        imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
        chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
        print(f"  paste事件: {chars}字, {imgs}张图片")
        dlog(f"paste事件: {chars}字, {imgs}张图片")

    # 等待图片上传到服务器
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

    # 填充图片描述
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
        print("  描述字段: 未找到预留位置（使用alt属性兜底）")
        dlog("描述字段: 未找到预留位置（使用alt属性兜底）")

    dlog("正文保存开始")
    print("  [save] 触发保存...")
    force_save(page, timeout=60)

    # 验证保存后内容
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
    except Exception:
        pass

    saved_imgs = (verify_data.get('pmImgs', 0) if verify_data else 0) or page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
    saved_chars = (verify_data.get('pmChars', 0) if verify_data else 0) or page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
    dom_imgs = verify_data.get('domImgs', 0) if verify_data else '?'
    print(f"  保存后验证: {saved_chars}字, {saved_imgs}张图片 (DOM: {dom_imgs})")
    dlog(f"保存后验证: {saved_chars}字, {saved_imgs}张图片, verify={verify_result}")

    if saved_imgs == 0:
        print("  [WARN] 保存后图片丢失！重新通过ProseMirror API设置...")
        dlog("保存后图片丢失，重新通过PM API设置")
        retry_result = page.run_js(pm_js)
        dlog(f"重新设置结果: {retry_result}")
        print(f"  重新设置: {retry_result}")
        retry_data = None
        try:
            retry_data = json.loads(retry_result) if retry_result else None
        except Exception:
            pass
        if retry_data and retry_data.get('status') == 'ok':
            retry_imgs = retry_data.get('imgs', 0)
            retry_chars = retry_data.get('chars', 0)
        else:
            retry_imgs = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
            retry_chars = page.run_js("return document.querySelector('.ProseMirror').innerText.length;") or 0
        print(f"  重新设置后: {retry_chars}字, {retry_imgs}张图片")
        dlog(f"重新设置后: {retry_chars}字, {retry_imgs}张图片")
        force_save(page, timeout=30)

    # 跳过封面上传（Linux headless下封面上传不稳定）
    if os.environ.get("SKIP_COVER") == "1":
        print("\n[4] 跳过封面上传（SKIP_COVER=1）")
        dlog("跳过封面上传（SKIP_COVER=1）")
    else:
        print("\n[4] 跳过封面上传（Linux headless 模式下不稳定，建议后续手动补）")
        dlog("跳过封面上传（Linux headless 不稳定）")

    print("  [save] 最终保存...")
    force_save(page, timeout=30)

    # 验证草稿箱
    print("\n[5] 验证草稿箱...")
    dlog("验证草稿箱开始")
    # 先在当前页（publish页）捕获保存请求和响应（导航后会丢失JS状态）
    saved_bodies_str = page.run_js("return JSON.stringify(window._savedBodies||[]);") or "[]"
    dlog(f"最终保存请求（publish页）: {saved_bodies_str}")
    try:
        saved_bodies = json.loads(saved_bodies_str)
        print(f"  [save] 捕获到 {len(saved_bodies)} 个保存请求")
        for b in saved_bodies:
            url = b.get('url', '')[:80]
            body_len = len(b.get('body', ''))
            has_img = 'image' in b.get('body', '').lower() or 'tos-cn' in b.get('body', '').lower()
            print(f"    {url} (body={body_len}字符, 含图片={has_img})")
    except Exception as e:
        dlog(f"解析保存请求失败: {e}")

    # 捕获保存API响应
    save_responses_str = page.run_js("return JSON.stringify(window._saveResponses||[]);") or "[]"
    dlog(f"保存API响应: {save_responses_str}")
    try:
        save_responses = json.loads(save_responses_str)
        if save_responses:
            print(f"  [save] 捕获到 {len(save_responses)} 个保存API响应")
            for sr in save_responses:
                print(f"    URL: {sr.get('url','')[:80]}")
                print(f"    HTTP状态: {sr.get('status','?')}")
                print(f"    响应体: {sr.get('body','')[:500]}")
        else:
            print(f"  [save] 未捕获到保存API响应")
    except Exception as e:
        dlog(f"解析保存响应失败: {e}")

    page.get("https://mp.toutiao.com/profile_v4/manage/draft")
    time.sleep(8)

    # 滚动加载并搜索
    found = False
    for retry in range(3):
        # 滚动加载
        for _ in range(3):
            page.run_js("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        draft_text = page.run_js("return document.body.innerText;") or ""
        # 用标题前8字匹配
        match_key = title[:8]
        if match_key in draft_text:
            idx = draft_text.find(match_key)
            print(f"[SUCCESS] 文章已在草稿箱中!")
            print(f"  {draft_text[idx:idx+120]}")
            dlog(f"[SUCCESS] 文章已在草稿箱中")
            found = True
            break
        # 也尝试用关键词匹配
        if "互扇巴掌" in draft_text:
            idx = draft_text.find("互扇巴掌")
            print(f"[SUCCESS] 文章已在草稿箱中（关键词匹配）!")
            print(f"  {draft_text[idx:idx+120]}")
            dlog(f"[SUCCESS] 文章已在草稿箱中（关键词匹配）")
            found = True
            break
        print(f"  [retry {retry+1}/3] 未找到，刷新重试...")
        dlog(f"验证重试 {retry+1}/3")
        page.get("https://mp.toutiao.com/profile_v4/manage/draft")
        time.sleep(5)

    if not found:
        print("[FAIL] 未在草稿箱中找到文章")
        draft_text = page.run_js("return document.body.innerText;") or ""
        print(f"  草稿箱前500字: {draft_text[:500]}")
        dlog("[FAIL] 未在草稿箱中找到文章")

    # 打印捕获的保存请求
    page.quit()
    return found


if __name__ == "__main__":
    ok = main()
    print("\nDONE")
    sys.exit(0 if ok else 1)
