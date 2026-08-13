#!/usr/bin/env python3
"""获取1条头条热榜 → 抓取话题文本 → 撰写文章 → 4层图片获取 → 上传草稿箱
不依赖 DeepSeek API，直接编辑器撰写。
"""
import os, re, json, time, base64, sys
from DrissionPage import ChromiumPage, ChromiumOptions
import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"
IMAGE_COUNT = 5
IMAGE_LAYOUT = {1: 1, 3: 2, 5: 2}

def dlog(msg):
    print(f"  [{time.strftime('%H:%M:%S')}] {msg}")

def author_article(keyword, posts_text):
    """直接编辑器撰写文章（基于抓取的头条话题文本）"""
    # 从抓取的素材中提取关键信息
    snippets = []
    for p in (posts_text or []):
        t = p.get("text", "").strip()
        if t and len(t) > 15:
            snippets.append(t)

    # 组合素材摘要
    material = "\n".join(snippets[:5]) if snippets else keyword

    # 根据素材生成三段式标题（<=25字）
    kw = keyword.strip()
    if len(kw) <= 8:
        title = f"{kw}，细节曝光，你怎么看？"
    elif len(kw) <= 14:
        title = f"{kw}，背后真相来了，你怎么想？"
    else:
        title = f"{kw[:12]}，真相来了，你怎么看？"
    if len(title) > 25:
        title = title[:25]

    # 根据素材生成文章（>600字）
    p1 = f'刚才刷到一条消息，{kw}。说实话，第一眼看到这个标题，我愣了几秒，然后赶紧点进去看了详情。'

    if snippets:
        p2 = f'据了解，事情的经过大概是这样的。{snippets[0][:100]}'
        if len(snippets) > 1:
            p2 += f' 另有网友提到，{snippets[1][:80]}'
        p2 += ' 光看这些描述，就能感受到事情不简单。'
    else:
        p2 = f'说起来，{kw}这个话题，其实不是突然冒出来的。仔细了解之后才发现，里面的门道比想象中多得多。有网友分享了自己的经历，也有人从不同角度分析了这件事，评论区各种观点碰撞。'

    p3 = f'其实类似的事情，之前也不是没出现过。只不过这次热度更高，传播更广，引发了更多人的关注。从目前公开的信息来看，大家关注的点并不一致。有人在意过程，有人在意结果，还有人从这件事延伸到了更深层的话题讨论。这就导致评论区各种观点碰撞，谁也说服不了谁。'

    p4 = f'老实讲，现在热搜来得快去得也快。今天大家还在讨论{kw}，明天可能就被新的话题盖过去了。但这并不意味着这事不值得关注。恰恰相反，正因为信息更新太快，我们更应该在事情还没被淹没的时候，多了解一下背后的来龙去脉。毕竟，了解真相是形成判断的前提。'

    p5 = f'换个角度想，每个人看待事物的立场不同，得出的结论自然也不一样。有人觉得这事小题大做，有人认为值得深思。还有网友提出了一个很有意思的观点：很多事情表面看是个例，实际上反映的是普遍现象。你觉得呢？'

    p6 = f'不管怎样，{kw}能引发这么大的讨论量，说明它确实触动了大家的某个神经。也许是好奇，也许是共鸣，也许只是单纯想表达自己的看法。无论如何，能引发思考本身就是有价值的。欢迎在评论区聊聊你的看法，咱们一起探讨。'

    paragraphs = [p1, p2, p3, p4, p5, p6]
    article = "\n\n".join(paragraphs)

    # 确保超过600字
    total = sum(len(p) for p in paragraphs)
    if total < 600:
        p7 = f'另外，从以往类似事件的处理结果来看，公众的关注和讨论往往能推动事情的解决。所以，与其被动等待，不如主动发声。当然，发声的前提是了解事实，而不是道听途说。希望每个人在表达观点之前，都能先花几分钟看看事情的完整经过。'
        paragraphs.append(p7)
        article = "\n\n".join(paragraphs)

    # 清理儿化音
    article = ttw.clean_erhua(article)
    title = ttw.clean_erhua(title)

    return title, article

def save_b64_to_file(b64_data, idx):
    """base64保存为临时jpg文件"""
    if not b64_data:
        return None
    if b64_data.startswith('data:image/'):
        b64 = b64_data.split(',', 1)[1]
    else:
        b64 = b64_data
    tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    fpath = os.path.join(tmp_dir, f"body_img_{idx}.jpg")
    try:
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(b64))
        return fpath
    except:
        return None

def upload_image_via_paste(page, fpath, img_idx):
    """通过paste Blob上传单张图片，返回服务器URL"""
    with open(fpath, "rb") as f:
        raw_b64 = base64.b64encode(f.read()).decode('ascii')

    # 清空编辑器并聚焦
    page.run_js("""
        var editor = document.querySelector('.ProseMirror');
        if (editor) { editor.innerHTML = '<p></p>'; editor.dispatchEvent(new Event('input', {bubbles: true})); }
    """)
    time.sleep(0.3)
    page.run_js("var e=document.querySelector('.ProseMirror'); if(e) e.focus();")
    time.sleep(0.3)

    # paste Blob 上传
    page.run_js(f"""
        var editor = document.querySelector('.ProseMirror');
        if (!editor) return;
        editor.focus();
        var b64 = {json.dumps(raw_b64)};
        var byteString = atob(b64);
        var ab = new ArrayBuffer(byteString.length);
        var ia = new Uint8Array(ab);
        for (var i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
        var blob = new Blob([ab], {{type: 'image/jpeg'}});
        var file = new File([blob], 'image_{img_idx}.jpg', {{type: 'image/jpeg'}});
        var pasteEvent = new ClipboardEvent('paste', {{
            bubbles: true, cancelable: true
        }});
        var fakeData = {{
            files: [file], items: [], types: ['Files'],
            getData: function() {{ return ''; }},
            setData: function() {{}}, clearData: function() {{}}
        }};
        Object.defineProperty(pasteEvent, 'clipboardData', {{
            value: fakeData, writable: false, configurable: true
        }});
        editor.dispatchEvent(pasteEvent);
    """)

    # 等待图片出现
    for _ in range(30):
        time.sleep(1)
        imgs_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
        if imgs_now > 0:
            break
    else:
        return ""

    # 删除多余重复图片
    page.run_js("""
        var editor = document.querySelector('.ProseMirror');
        if (!editor) return;
        var imgs = editor.querySelectorAll('img');
        for (var i = imgs.length - 1; i > 0; i--) imgs[i].parentNode.removeChild(imgs[i]);
    """)
    time.sleep(1)

    # 等待blob:变为服务器URL
    img_url = ""
    for _ in range(30):
        img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
        if img_url and not img_url.startswith('blob:'):
            break
        time.sleep(1)
    if img_url.startswith('blob:'):
        for _ in range(15):
            time.sleep(2)
            img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
            if img_url and not img_url.startswith('blob:'):
                break
    return img_url

def wait_for_save(page, timeout=30):
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

def trigger_save(page):
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

def upload_to_draft(page, title, text_parts, image_urls, image_layout):
    """上传单篇文章到草稿箱"""
    dlog(f"文章: {title}")
    dlog(f"正文: {len(text_parts)}段, {sum(len(t) for t in text_parts)}字")
    dlog(f"图片: {len([u for u in image_urls if u])}张")

    # 打开发布页
    page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
    time.sleep(6)

    for i in range(15):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            break
        time.sleep(1)
    else:
        dlog("编辑器加载超时")
        return False

    # 关闭弹窗
    for text in ["不恢复", "关闭"]:
        try:
            btn = page.ele(f"text:{text}", timeout=2)
            if btn:
                btn.click()
                time.sleep(1)
        except:
            pass
    page.run_js("""
        var mask = document.querySelector('.byte-drawer-mask');
        if (mask) { mask.click(); mask.remove(); }
        var drawer = document.querySelector('.ai-assistant-drawer');
        if (drawer) drawer.remove();
    """)
    time.sleep(1)

    # 填标题（React兼容方式）
    title_json = json.dumps(title)
    page.run_js(f"""
        var el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                 document.querySelector('textarea[placeholder*="请输入文章标题"]');
        if (!el) return;
        el.focus();
        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(el, {title_json});
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.blur();
    """)
    time.sleep(3)
    wait_for_save(page, timeout=10)

    # === 图片上传阶段 ===
    valid_urls = []
    if image_urls:
        dlog(f"上传{len(image_urls)}张图片...")
        for img_idx, img_b64 in enumerate(image_urls):
            if not img_b64:
                valid_urls.append("")
                continue
            dlog(f"  图片{img_idx+1}/{len(image_urls)}: 上传中...")
            fpath = save_b64_to_file(img_b64, img_idx)
            if not fpath:
                dlog(f"  图片{img_idx+1}: 保存失败")
                valid_urls.append("")
                continue
            img_url = upload_image_via_paste(page, fpath, img_idx+1)
            if img_url and not img_url.startswith('blob:'):
                valid_urls.append(img_url)
                dlog(f"  图片{img_idx+1}: OK ({img_url[:60]}...)")
            else:
                dlog(f"  图片{img_idx+1}: 上传失败")
                valid_urls.append("")
            time.sleep(0.5)
        valid = [u for u in valid_urls if u]
        dlog(f"图片上传完成: {len(valid)}/{len(image_urls)}张")

    # === ProseMirror API 设置正文+图片 ===
    dlog("设置正文内容（文字+图片）...")
    data_json = json.dumps({"tp": text_parts, "iu": valid_urls, "il": image_layout}, ensure_ascii=False)
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
    var urlAttr='src';var imAttrs={};
    if(im){var imSpec=schema.nodes[im];if(imSpec&&imSpec.spec&&imSpec.spec.attrs){Object.keys(imSpec.spec.attrs).forEach(function(an){var a=imSpec.spec.attrs[an];if(an==='src'||an==='url'||an==='href')urlAttr=an;imAttrs[an]=a&&a.default!==undefined?a.default:'[no-default]';});}}
    var data=window._pmData;var content=[];var ui=0;
    var hasDataAttr=imAttrs&&Object.keys(imAttrs).indexOf('data')>=0;
    for(var i=0;i<data.tp.length;i++){
        if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
        var t=i+1;
        if(data.il[t]){for(var j=0;j<data.il[t];j++){if(ui<data.iu.length&&data.iu[ui]){var imgUrl=data.iu[ui];var attrs={};if(hasDataAttr){attrs.data={url:imgUrl,icUri:imgUrl,catchErrorUrl:"",link:"",caption:"图片来源于网络",ic:false,naturalHeight:0,naturalWidth:0,srcType:"",captionLenErr:false,needCheck:false};}else{attrs[urlAttr]=imgUrl;attrs.alt='图片来源于网络';}content.push({type:im,attrs:attrs});ui++;}}}
    }
    try{
        var doc=schema.nodeFromJSON({type:dn,content:content});
        view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
        var ic=0;view.state.doc.descendants(function(node){if(node.type.name===im)ic++;return true;});
        return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length});
    }catch(e){return JSON.stringify({status:'error',error:e.message});}
    })()"""

    pm_result = page.run_js(pm_js)
    try:
        pm_data = json.loads(pm_result) if pm_result else {}
    except:
        pm_data = {}

    if pm_data.get('status') == 'ok':
        dlog(f"正文+图片设置成功: {pm_data.get('chars', 0)}字, {pm_data.get('imgs', 0)}张图")
    else:
        dlog(f"PM API失败({pm_result})，键盘输入回退...")
        editor_el = page.ele('.ProseMirror', timeout=3)
        if editor_el:
            editor_el.click()
            time.sleep(0.3)
            for j, para in enumerate(text_parts):
                if j > 0:
                    page.actions.key_down('Enter').key_up('Enter')
                    time.sleep(0.2)
                page.actions.type(para)
                time.sleep(0.3)

    time.sleep(2)
    trigger_save(page)
    if wait_for_save(page, timeout=20):
        dlog("正文已自动保存")
    else:
        dlog("保存未确认，再触发一次...")
        trigger_save(page)
        wait_for_save(page, timeout=15)
    return True

def main():
    print("=" * 60)
    print("获取1条头条热榜 → 生成文章 → 上传草稿箱")
    print("=" * 60)

    # 1. 获取头条热榜
    print("\n[1] 获取头条热榜...")
    session = ttw.get_tt_session()
    hot_list = ttw.get_toutiao_hot_board(session)
    print(f"  共获取 {len(hot_list)} 条热榜")

    # 取排名最高的1条
    hot = hot_list[0]
    keyword = hot["word"]
    category = ttw.classify_tt_topic(hot)
    print(f"  选中: {hot['title']}（排名{hot['rank']}, {category}, 热度{hot.get('num', '?')}）")

    # 2. 抓取头条话题文本
    print("\n[2] 抓取头条话题文本...")
    posts = ttw.fetch_toutiao_posts_text(session, keyword, topic_url=hot.get("url", ""), count=8)
    print(f"  获取到 {len(posts)} 条素材")
    for i, p in enumerate(posts[:3]):
        print(f"    [{i+1}] {p['text'][:60]}...")

    # 3. 撰写文章
    print("\n[3] 撰写文章...")
    title, article = author_article(keyword, posts)
    print(f"  标题: {title}（{len(title)}字）")
    print(f"  正文: {len(article)}字")

    # 4. 获取配图（4层管线）
    print("\n[4] 获取配图（头条→微博→百度）...")
    images, source = ttw.fetch_images_unified(
        session, keyword,
        topic_image_url=hot.get("image", ""),
        topic_url=hot.get("url", ""),
        count=IMAGE_COUNT
    )
    print(f"  成功获取 {len(images)} 张配图（来源: {source}）")

    # 5. 上传草稿箱
    print("\n[5] 上传草稿箱...")
    text_parts = [p.strip() for p in article.split("\n") if p.strip()]

    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    co = ChromiumOptions()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    page = ChromiumPage(co)
    page.get("https://mp.toutiao.com")
    time.sleep(2)
    for name, value in cookies.items():
        try:
            page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        except:
            pass
    page.get("https://mp.toutiao.com")
    time.sleep(3)
    print(f"  登录: {page.url}")

    ok = upload_to_draft(page, title, text_parts, images, IMAGE_LAYOUT)
    print(f"\n  >>> {'成功' if ok else '失败'}")

    # 6. 验证草稿箱
    print("\n[6] 验证草稿箱...")
    page.get(DRAFT_URL)
    time.sleep(5)
    draft_text = page.run_js("return document.body.innerText;") or ""
    title_prefix = title[:6]
    if title_prefix in draft_text:
        print(f"  [OK] 草稿箱中找到文章")
    else:
        print(f"  [MISS] 草稿箱中未找到")

    page.quit()
    print("\nDONE")

if __name__ == "__main__":
    main()