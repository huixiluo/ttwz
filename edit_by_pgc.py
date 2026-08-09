# -*- coding: utf-8 -*-
"""通过pgc_id编辑现有草稿，绕过7050新建限制"""
import os, json, time, re, base64, sys
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

def wait_for_save(page, timeout=120):
    dlog("wait_for_save: 开始")
    print("  [save] 等待保存完成...")
    saved = False
    last_status = ""
    for i in range(timeout):
        time.sleep(2)
        status = page.run_js("""
var body = document.body.innerText;
if (body.indexOf('保存失败') !== -1) return 'FAIL';
if (body.indexOf('草稿已保存') !== -1) return 'SAVED';
if (body.indexOf('保存成功') !== -1) return 'SAVED';
if (body.indexOf('草稿保存中') !== -1) return 'SAVING';
return 'IDLE';
""") or ""

        responses = page.run_js("""
var responses = window._saveResponses || [];
for (var i = 0; i < responses.length; i++) {
    var b = responses[i].body || '';
    if (b.indexOf('"code":0') >= 0 || b.indexOf('"code": 0') >= 0) return 'SUCCESS';
}
return '';
""") or ""

        if responses == 'SUCCESS' or status == 'SAVED':
            print(f"  [save] 保存成功! (用时{i*2}s)")
            return True

        if status != last_status:
            print(f"  [save] [{i*2}s] status={status}")
            last_status = status

        if i % 10 == 0 and i > 0:
            print(f"  [save] [{i*2}s] status={status}")

    print(f"  [save] 保存超时 (status={status})")
    api_responses = page.run_js("return JSON.stringify(window._saveResponses||[]);") or "[]"
    try:
        rs = json.loads(api_responses)
        for r in rs[-3:]:
            print(f"  [save] API: {r.get('body','')[:300]}")
    except:
        pass
    return False

def set_prosemirror_content(page, text_parts, image_urls, image_layout):
    """通过ProseMirror API设置内容（复用upload_linux.py的逻辑）"""
    text_plain_parts = [re.sub(r'<[^>]+>', '', t).strip() for t in text_parts]
    data_json = json.dumps({"tp": text_plain_parts, "iu": image_urls, "il": image_layout}, ensure_ascii=False)
    page.run_js("window._pmData=" + data_json + ";")

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
var doc=schema.nodeFromJSON({type:dn,content:content});
view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
var wc=document.querySelector('[class*="word-count"],[class*="wordCount"]');
if(wc){wc.click();}
return JSON.stringify({status:'ok',imgs:ui,chars:content.length,pn:pn,in:im,urlAttr:urlAttr});
})();"""
    result = page.run_js(pm_js)
    dlog(f"set_prosemirror: {result}")
    return result

def main():
    # 读取要上传的文章
    with open("single_manifest.json", "r", encoding="utf-8") as f:
        art = json.load(f)[0]
    title = art["title"][:30]
    html_path = art["html_file"]
    print(f"文章: {title}")
    dlog(f"edit_by_pgc: 文章={title}")

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
    print(f"  图片布局: {image_layout}")

    # 读取草稿ID列表
    with open("draft_ids.json", "r", encoding="utf-8") as f:
        editable_drafts = json.load(f)

    if not editable_drafts:
        print("  [FAIL] 没有可编辑的草稿")
        return False

    # 使用第一个可编辑的草稿
    target_draft = editable_drafts[0]
    pgc_id = target_draft["gid"]
    print(f"  目标草稿: pgc_id={pgc_id}")
    print(f"  原标题: {target_draft['title'][:40]}")

    # 启动浏览器
    print("\n[1] 启动浏览器...")
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
    co.set_address("127.0.0.1:9240")
    co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_pgc"))
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
        except:
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
        page.quit()
        return False

    # 用pgc_id导航到编辑页面
    edit_url = f"{PUBLISH_URL}?pgc_id={pgc_id}&_t={int(time.time() * 1000)}"
    print(f"\n[2] 导航到编辑页面...")
    print(f"  URL: {edit_url}")
    page.get(edit_url)
    time.sleep(8)

    # 等待编辑器加载
    print("\n[3] 等待编辑器加载...")
    editor_ready = False
    for i in range(30):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            print(f"  [OK] 编辑器已就绪 (用时{i}s)")
            editor_ready = True
            break
        time.sleep(1)

    if not editor_ready:
        print(f"  当前URL: {page.url}")
        page_text = page.run_js("return document.body.innerText.substring(0, 500);") or ""
        print(f"  页面内容: {page_text[:300]}")
        print("  [FAIL] 编辑器未就绪")
        page.quit()
        return False

    # 关闭对话框
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
      resp.clone().text().then(function(t){
        window._saveResponses.push({url:urlStr,status:resp.status,body:t.substring(0,5000)});
      }).catch(function(){});
    }).catch(function(){});
  }
  return p;
};
""")

    # 清除旧内容
    print("\n[4] 清除旧内容...")
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.focus();
    var pmView = editor.pmViewDesc;
    if (pmView && pmView.view) {
        var view = pmView.view;
        var state = view.state;
        view.dispatch(view.state.tr.delete(0, state.doc.content.size));
    }
}
""")
    time.sleep(1)

    # 设置新标题
    print(f"\n[5] 设置新标题: {title}")
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
    print(f"\n[6] 上传{len(image_srcs)}张图片...")
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
    print(f"  [6] 完成: {len(valid_urls)}/{len(tmp_files)}张图片已上传")

    # 设置编辑器内容
    print(f"\n[7] 设置编辑器内容（ProseMirror API）...")
    pm_result = set_prosemirror_content(page, text_parts, image_urls, image_layout)
    print(f"  ProseMirror: {pm_result}")
    time.sleep(2)

    # 模拟按键触发保存
    print("\n[8] 触发保存...")
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

    saved = wait_for_save(page, timeout=90)

    # 验证草稿箱
    print("\n[9] 验证草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(5)
    draft_text = page.run_js("return document.body.innerText;") or ""
    if title[:10] in draft_text:
        print(f"  [SUCCESS] 文章已在草稿箱中!")
        page.quit()
        return True
    else:
        print(f"  [FAIL] 未在草稿箱中找到文章")
        print(f"  草稿箱前300字: {draft_text[:300]}")
        page.quit()
        return False

if __name__ == "__main__":
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n=== edit_by_pgc 开始 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    result = main()
    print(f"\n结果: {'成功' if result else '失败'}")
    sys.exit(0 if result else 1)
