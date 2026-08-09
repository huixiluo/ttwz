# -*- coding: utf-8 -*-
"""Linux headless 单篇文章上传到头条草稿箱
用法: python upload_one.py <article_index>  (1-based)
基于 upload_visible.py 的 ProseMirror API 方案，适配 Linux headless 环境。
"""
import os, re, json, time, base64, sys, gc
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_LIST_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

DEBUG_LOG = os.path.join(BASE_DIR, "debug.log")
def dlog(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局（5张图上限）——均匀分布，避免中间大片文字空档。"""
    if total_paragraphs < 1:
        return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}
    first = 1
    def _build_positions(last):
        if last < 3:
            return [first]
        pos_list = [first]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                raw = last if k == n_groups else first + step * k
                pos = int(round(raw))
                min_pos = pos_list[-1] + 2
                remaining_after = n_groups - k
                max_pos = last - 2 * remaining_after
                pos = max(min_pos, min(max_pos, pos))
                pos_list.append(pos)
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list
    def _max_gap(pos_list):
        if len(pos_list) < 2:
            return 0
        return max(pos_list[i+1] - pos_list[i] - 1 for i in range(len(pos_list) - 1))
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
    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)
    candidates.sort(key=_score)
    best_positions = candidates[0][2]
    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


def wait_for_save(page, timeout=30):
    """等待自动保存完成（检测'草稿已保存'文字）"""
    for i in range(timeout):
        time.sleep(1)
        s = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
return 'idle';
""")
        if s and 'SAVED' in str(s):
            return True
    return False


def force_save_via_api(page, timeout=90):
    """通过监控网络请求等待保存API返回成功（容忍7050限流，平台会自动重试）"""
    # 注入网络响应拦截器，监控保存API的响应
    page.run_js("""
window._saveResults = [];
var origFetch = window.fetch;
window.fetch = function(url, options) {
    var urlStr = typeof url === 'string' ? url : (url && url.url) || '';
    var promise = origFetch.apply(this, arguments);
    if (urlStr.indexOf('/article/publish') !== -1 || urlStr.indexOf('/save') !== -1) {
        promise.then(function(resp) {
            resp.clone().json().then(function(data) {
                window._saveResults.push({url: urlStr, code: data.code, message: data.message || ''});
            }).catch(function(){});
        }).catch(function(){});
    }
    return promise;
};
""")
    dlog("force_save: 网络拦截器已注入")
    success_seen = False
    fail_count = 0
    for i in range(timeout):
        time.sleep(1)
        results = page.run_js("return JSON.stringify(window._saveResults || []);")
        try:
            save_results = json.loads(results) if results else []
        except:
            save_results = []
        for r in save_results:
            code = r.get("code", -1)
            msg = r.get("message", "")
            if code == 0:
                success_seen = True
                dlog(f"force_save: [{i}s] 保存成功 code=0")
                return True
            elif code == 7050 or "7050" in str(msg):
                fail_count += 1
                if fail_count % 10 == 1:
                    dlog(f"force_save: [{i}s] 7050限流，等待平台重试 (fail_count={fail_count})")
            else:
                fail_count += 1
                dlog(f"force_save: [{i}s] code={code}, message={msg}")
        # 每20次失败重新触发保存
        if fail_count > 0 and fail_count % 20 == 0:
            dlog(f"force_save: [{i}s] 重新触发保存")
            try:
                page.run_js("var e=document.querySelector('.ProseMirror'); if(e){e.focus();}")
                time.sleep(0.3)
                page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key='End', code='End',
                            windowsVirtualKeyCode=35, nativeVirtualKeyCode=35)
                page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key='End', code='End',
                            windowsVirtualKeyCode=35, nativeVirtualKeyCode=35)
                time.sleep(0.2)
                page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space',
                            windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
                page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space',
                            windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
                time.sleep(0.2)
                page.run_cdp('Input.dispatchKeyEvent', type='keyDown', key='Backspace', code='Backspace',
                            windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
                page.run_cdp('Input.dispatchKeyEvent', type='keyUp', key='Backspace', code='Backspace',
                            windowsVirtualKeyCode=8, nativeVirtualKeyCode=8)
            except Exception:
                pass
        if fail_count >= 60 and not success_seen:
            dlog(f"force_save: 连续FAIL {fail_count}次，放弃")
            return False
    dlog(f"force_save: 超时({timeout}s), success={success_seen}")
    return success_seen


def trigger_save(page):
    """触发自动保存（在标题框输入空格再删除）"""
    try:
        page.run_js("""
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.focus();
    el.dispatchEvent(new KeyboardEvent('keydown', {key: ' ', bubbles: true}));
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.blur();
    el.dispatchEvent(new Event('change', {bubbles: true}));
}
""")
        time.sleep(0.5)
    except Exception:
        pass


def save_base64_to_temp(data_url, idx):
    """把base64图片保存为临时文件"""
    if not data_url or not data_url.startswith('data:image/'):
        return None
    try:
        header, b64 = data_url.split(',', 1)
        mime = header.split(':')[1].split(';')[0]
        ext = mime.split('/')[-1].replace('jpeg', 'jpg')
    except Exception:
        return None
    tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    fname = f"body_img_{idx+1}.{ext}"
    fpath = os.path.join(tmp_dir, fname)
    try:
        decoded = base64.b64decode(b64)
        with open(fpath, "wb") as f:
            f.write(decoded)
    except Exception:
        return None
    return fpath


# ProseMirror view 查找 + 内容设置 JS
PM_SET_JS = """return (function(){
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
  return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length});
}catch(e){
  return JSON.stringify({status:'error',error:e.message});
}
})()"""


def upload_article(art):
    """上传单篇文章到草稿箱，返回 (success: bool, title: str)"""
    title = art["title"][:30]
    html_path = art["html_file"]

    # 清空调试日志
    with open(DEBUG_LOG, "w", encoding="utf-8") as f:
        f.write(f"=== 开始上传: {title} {time.strftime('%H:%M:%S')} ===\n")

    # 读取HTML正文，分离纯文字和图片
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

    print(f"  正文: {len(text_parts)}段, {len(image_srcs)}张图片", flush=True)
    image_layout = calc_image_layout(len(text_parts), len(image_srcs))
    print(f"  图片布局: {image_layout}", flush=True)

    # 启动headless浏览器
    print("[1] 启动headless浏览器...", flush=True)
    co = ChromiumOptions()
    co.headless(True)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    page = ChromiumPage(co)

    try:
        page.get("https://mp.toutiao.com")
        time.sleep(2)
        cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
        for name, value in cookies.items():
            try:
                page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
            except Exception:
                pass
        page.get("https://mp.toutiao.com")
        time.sleep(3)
        print("  [OK] 登录成功", flush=True)

        # 创建新文章
        print("[2] 打开publish页面...", flush=True)
        page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
        time.sleep(6)
        for i in range(15):
            if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
                print(f"  [OK] 编辑器已就绪", flush=True)
                break
            time.sleep(1)
        # 关闭弹窗
        for btn_text in ["关闭", "不恢复"]:
            try:
                btn = page.ele(f"text:{btn_text}", timeout=2)
                if btn:
                    btn.click()
                    time.sleep(1)
            except Exception:
                pass

        # 填标题
        print("[3] 填标题...", flush=True)
        title_json = json.dumps(title)
        page.run_js(f"""
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
        print(f"  标题: {title}", flush=True)
        time.sleep(3)

        # 清除旧草稿内容
        existing = page.run_js("var e=document.querySelector('.ProseMirror'); return e?e.innerText.trim():'';")
        if existing and len(existing) > 10:
            page.run_js("""
var e=document.querySelector('.ProseMirror');
if(e){e.innerHTML='<p></p>';e.dispatchEvent(new Event('input',{bubbles:true}));}
""")
            time.sleep(1)

        # 准备图片临时文件
        print(f"[4] 准备图片临时文件（{len(image_srcs)}张）...", flush=True)
        tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        for old_f in os.listdir(tmp_dir):
            if old_f.startswith("body_img_"):
                try:
                    os.remove(os.path.join(tmp_dir, old_f))
                except Exception:
                    pass
        tmp_files = []
        for img_i, data_url in enumerate(image_srcs):
            fpath = save_base64_to_temp(data_url, img_i)
            tmp_files.append(fpath)
        gc.collect()

        # 启用CDP文件选择器拦截
        try:
            page.run_cdp('Page.setInterceptFileChooserDialog', enabled=True)
        except Exception:
            pass

        # 逐张上传图片，获取服务器URL
        print(f"[5] 上传{len(tmp_files)}张图片...", flush=True)
        image_urls = []
        for img_idx, fpath in enumerate(tmp_files):
            if not fpath or not os.path.exists(fpath):
                image_urls.append("")
                continue
            print(f"  图片{img_idx+1}: 上传中...", flush=True)
            # 清空编辑器
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

            # 等待图片出现
            uploaded = False
            for wait_i in range(60):
                time.sleep(0.5)
                imgs_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
                if imgs_now > 0:
                    uploaded = True
                    break
            if not uploaded:
                print(f"  图片{img_idx+1}: 上传超时", flush=True)
                image_urls.append("")
                continue

            # 删除多余重复图片
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
                for wait_i in range(30):
                    time.sleep(2)
                    img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
                    if img_url and not img_url.startswith('blob:'):
                        break
            image_urls.append(img_url)
            print(f"  图片{img_idx+1}: OK", flush=True)

        valid_urls = [u for u in image_urls if u and not u.startswith('blob:')]
        print(f"  图片上传完成: {len(valid_urls)}/{len(tmp_files)}张", flush=True)

        # 通过ProseMirror API设置完整内容
        print("[6] 设置编辑器内容（ProseMirror API）...", flush=True)
        text_plain_parts = [re.sub(r'<[^>]+>', '', t).strip() for t in text_parts]
        data_json = json.dumps({"tp": text_plain_parts, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
        page.run_js("window._pmData=" + data_json + ";")
        pm_result = page.run_js(PM_SET_JS)
        dlog(f"ProseMirror结果: {pm_result}")
        print(f"  ProseMirror: {pm_result}", flush=True)

        try:
            pm_data = json.loads(pm_result) if pm_result else None
        except:
            pm_data = None

        if pm_data and pm_data.get('status') == 'ok':
            imgs = pm_data.get('imgs', 0)
            chars = pm_data.get('chars', 0)
            print(f"  [OK] 设置成功: {chars}字, {imgs}张图片", flush=True)
        else:
            print(f"  [WARN] ProseMirror设置失败: {pm_result}", flush=True)

        # 等待图片上传到服务器
        print("[7] 等待图片同步到服务器...", flush=True)
        for wait_round in range(30):
            srcs = page.run_js("""
var imgs = document.querySelectorAll('.ProseMirror img');
var srcs = [];
for (var i = 0; i < imgs.length; i++) srcs.push(imgs[i].src);
return srcs;
""") or []
            blob_count = sum(1 for s in srcs if s.startswith('blob:') or s.startswith('data:'))
            server_count = len(srcs) - blob_count
            if blob_count == 0 and server_count > 0:
                print(f"  [OK] 所有图片已同步 ({server_count}张)", flush=True)
                break
            if wait_round % 5 == 0:
                print(f"  等待中: {server_count}张服务器, {blob_count}张本地", flush=True)
            time.sleep(2)

        # 触发保存并等待
        print("[8] 触发保存...", flush=True)
        trigger_save(page)
        time.sleep(2)

        # 等待保存API返回成功
        saved = force_save_via_api(page, timeout=90)
        if saved:
            print("  [OK] 保存API返回成功", flush=True)
        else:
            print("  [WARN] 保存API未确认成功，尝试文字提示检测...", flush=True)
            saved = wait_for_save(page, timeout=20)
            if saved:
                print("  [OK] 检测到保存成功提示", flush=True)

        # 验证草稿箱
        print("[9] 验证草稿箱...", flush=True)
        page.get(DRAFT_LIST_URL)
        time.sleep(5)
        draft_text = page.run_js("return document.body.innerText;") or ""
        if title[:8] in draft_text:
            idx = draft_text.find(title[:8])
            print(f"  [SUCCESS] 文章已在草稿箱中!", flush=True)
            print(f"  {draft_text[idx:idx+80]}", flush=True)
            return True, title
        else:
            # 通过API再次验证
            print("  页面未找到，通过API验证...", flush=True)
            import requests
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            csrf = cookies.get("passport_csrf_token", "")
            r = requests.get(
                "https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=50&app_id=1231",
                headers={"Cookie": cookie_str, "X-CSRFToken": csrf, "User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            drafts = r.json().get("draft_list", [])
            for d in drafts:
                dt = d.get("title", "")
                da = d.get("abstract", "")
                if title[:8] in dt or title[:8] in da:
                    print(f"  [SUCCESS] API验证: 文章已在草稿箱中!", flush=True)
                    return True, title
            print(f"  [FAIL] 未在草稿箱中找到文章", flush=True)
            return False, title

    except Exception as e:
        import traceback
        dlog(f"异常: {e}\n{traceback.format_exc()}")
        print(f"  [ERROR] {e}", flush=True)
        return False, title
    finally:
        try:
            page.quit()
        except Exception:
            pass
        time.sleep(1)


def main():
    if len(sys.argv) < 2:
        print("用法: python upload_one.py <article_index>  (1-based)")
        sys.exit(1)
    idx = int(sys.argv[1])

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if idx < 1 or idx > len(manifest):
        print(f"索引超出范围: {idx} (共{len(manifest)}篇)")
        sys.exit(1)

    art = manifest[idx - 1]
    print(f"上传第{idx}篇: {art['title'][:30]}", flush=True)
    print("=" * 60, flush=True)

    success, title = upload_article(art)
    if success:
        print(f"\n[DONE] 第{idx}篇上传成功: {title}", flush=True)
        sys.exit(0)
    else:
        print(f"\n[FAIL] 第{idx}篇上传失败: {title}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
