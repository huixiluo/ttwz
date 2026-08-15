# -*- coding: utf-8 -*-
"""复现批量流程：PM_JS设置内容+标题触发，捕获autosave响应"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

PM_JS = """return (function(){
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
var pn=null,dn=null;
nts.forEach(function(k){if(k==='paragraph'||k==='para')pn=k;if(k==='doc')dn=k;});
if(!pn)nts.forEach(function(k){if(k.toLowerCase().indexOf('para')>=0)pn=k;});
if(!dn)nts.forEach(function(k){if(k==='doc'||k==='document')dn=k;});
if(!pn||!dn)return JSON.stringify({status:'no_types'});
var data=window._pmData;var content=[];
for(var i=0;i<data.tp.length;i++){
    if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
}
try{
    var doc=schema.nodeFromJSON({type:dn,content:content});
    view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
    return JSON.stringify({status:'ok',chars:view.state.doc.textContent.length});
}catch(e){return JSON.stringify({status:'error',error:e.message});}
})()"""

co = ChromiumOptions()
chrome_path = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
if os.path.exists(chrome_path):
    co.set_browser_path(chrome_path)
co.auto_port()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.headless()
page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass
page.get(PUBLISH_URL)
time.sleep(8)

for text in ["不恢复", "关闭"]:
    try:
        btn = page.ele(f"text:{text}", timeout=2)
        if btn:
            btn.click(); time.sleep(1)
    except Exception:
        pass
page.run_js("""
var mask = document.querySelector('.byte-drawer-mask');
if (mask) { mask.click(); mask.remove(); }
""")

# XHR hook
page.run_js("""
window._saveResults = [];
var OrigXHR = window.XMLHttpRequest;
function HookedXHR() {
    var xhr = new OrigXHR();
    var origOpen = xhr.open, origSend = xhr.send, _url = '';
    xhr.open = function(m, u) { _url = u; return origOpen.apply(xhr, arguments); };
    xhr.send = function(body) {
        var u = String(_url);
        if (u.indexOf('/article/publish') >= 0 || u.indexOf('save') >= 0) {
            var entry = {url: u.substring(0, 120)};
            window._saveResults.push(entry);
            xhr.addEventListener('load', function() {
                entry.status = xhr.status;
                entry.resp = String(xhr.responseText || '').substring(0, 400);
                // 提取关键字段
                try {
                    var d = JSON.parse(xhr.responseText);
                    entry.code = d.code; entry.msg = d.message;
                    var bodyStr = String(body || '');
                    var m = bodyStr.match(/save=([^&]*)/);
                    if (m) entry.save_param = m[1];
                    var wc = bodyStr.match(/content_word_cnt%22%3A(\d+)/);
                    if (wc) entry.word_cnt = wc[1];
                    var hasContent = bodyStr.match(/content=([^&]{0,60})/);
                    if (hasContent) entry.content_head = decodeURIComponent(hasContent[1]).substring(0, 80);
                } catch(e) {}
            });
        }
        return origSend.apply(xhr, arguments);
    };
    return xhr;
}
window.XMLHttpRequest = HookedXHR;
return 'hooked';
""")

# 1) PM_JS 设置正文（同批量流程）
paras = [
    "测试文章第一段内容，用来验证保存流程是否正常工作，这段文字超过三十个字以确保有效。",
    "第二段内容，补充说明事情的背景和相关细节，让文章看起来更完整一些，继续增加字数。",
    "第三段内容，分析各方的观点和立场，给出一些有深度的思考，确保内容足够充实完整。",
    "第四段内容，总结全文并引导读者互动，提出问题让大家在评论区讨论，形成完整闭环。",
]
page.run_js("window._pmData=" + json.dumps({"tp": paras}, ensure_ascii=False) + ";")
r = page.run_js(PM_JS)
print("PM设置结果:", r)

# 2) 设置标题触发autosave（同批量流程）
title_json = json.dumps("流程复现测试-可删除")
title_js = """
var el = document.querySelector('textarea[placeholder*="文章标题"]');
if (el) {
    el.focus();
    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(el, TITLE);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.blur();
}
""".replace("TITLE", title_json)
page.run_js(title_js)
print("标题已设置，等待40秒...")
time.sleep(40)

print("\n=== save请求及响应 ===")
results = page.run_js("return JSON.stringify(window._saveResults, null, 1);")
print(results[:3000] if results else "无save请求")

ui_text = page.run_js("""
var t = document.body.innerText;
var m = t.match(/.{0,40}(草稿|保存).{0,40}/g);
return m ? m.slice(0, 6).join('\\n') : '无';
""")
print("\n=== UI提示 ===")
print(ui_text)

page.quit()
