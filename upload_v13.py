#!/usr/bin/env python3
"""头条草稿箱上传 v13 - 键盘输入文字 + PM API插入图片 + 网络监听保存

核心策略：
1. 逐张上传图片到服务器获取URL
2. 键盘逐段输入文字（ProseMirror自动同步）
3. 通过ProseMirror view.dispatch()在正确位置插入图片（避免粘贴重复）
4. 填写标题
5. 监听网络请求确认保存成功
6. 验证草稿箱
"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"


def calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局——均匀分布，避免中间大片文字空档。"""
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
                if k == n_groups: raw = last
                else: raw = first + step * k
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
        if len(pos_list) < 2: return 0
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


def extract_html_text_and_images(html_path):
    """从HTML文件中提取段落文字和图片base64"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs, images = [], []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
        images.append(m.group(1))
    return paragraphs, images


def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        w, h = img.size
        if w > max_width: img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except: return None


async def remove_overlays(page):
    await page.evaluate("""
        () => { document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper, [class*="drawer-mask"], [class*="modal-mask"]').forEach(m => { if (m && m.parentNode) m.parentNode.removeChild(m); }); }
    """)
    await asyncio.sleep(0.3)


async def dismiss_notifications(page):
    await remove_overlays(page)
    for btn_text in ["关闭", "不恢复", "知道了", "确定", "取消"]:
        try:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await asyncio.sleep(0.3)
        except: pass


async def upload_images_get_urls(page, img_bytes_list):
    """逐张上传图片到服务器，返回服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_overlays(page)
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = '<p></p>'; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        b64 = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return;
                ed.focus();
                const bs = atob("{b64}");
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                Object.defineProperty(ev, 'clipboardData', {{
                    value: {{files: [file], items: [], types: ['Files'],
                        getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}}
                }});
                ed.dispatchEvent(ev);
            }}
        """)

        img_url = ""
        for _ in range(60):
            await asyncio.sleep(0.5)
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break
        ok = img_url and not img_url.startswith('blob:') and not img_url.startswith('data:')
        print("OK" if ok else "FAIL")
        image_urls.append(img_url if ok else "")
        await asyncio.sleep(0.3)
    return image_urls


async def insert_images_via_pm(page, valid_urls, image_layout, total_paragraphs):
    """通过ProseMirror view.dispatch()在正确位置插入图片节点"""
    print(f"    通过PM API插入{len(valid_urls)}张图片...")

    data_json = json.dumps({
        "iu": valid_urls,
        "il": image_layout,
        "tp_count": total_paragraphs
    }, ensure_ascii=False)

    await page.evaluate("window._pmImgData=" + data_json + ";")

    result = await page.evaluate("""(function(){
var data = window._pmImgData;

// 查找ProseMirror view
function findView(){
  var editor = document.querySelector('.ProseMirror');
  if (!editor) return null;
  var desc = editor.pmViewDesc;
  while (desc) { if (desc.view && desc.view.state) return desc.view; desc = desc.parent; }
  function sf(fiber, v) {
    if (!fiber || v.has(fiber) || v.size > 500) return null;
    v.add(fiber);
    if (fiber.stateNode && fiber.stateNode.view && fiber.stateNode.view.state) return fiber.stateNode.view;
    if (fiber.memoizedProps && fiber.memoizedProps.view && fiber.memoizedProps.view.state) return fiber.memoizedProps.view;
    if (fiber.memoizedState) {
      var s = fiber.memoizedState;
      while (s) { if (s.memoizedState && s.memoizedState.view && s.memoizedState.view.state) return s.memoizedState.view; s = s.next; }
    }
    var r = sf(fiber.child, v); if (r) return r;
    return sf(fiber.sibling, v);
  }
  var el = editor;
  for (var i = 0; i < 15 && el; i++) {
    var fk = Object.keys(el).find(function(k) { return k.indexOf('__reactFiber') === 0 || k.indexOf('__reactInternalInstance') === 0; });
    if (fk) { var v = new Set(); var r = sf(el[fk], v); if (r) return r; }
    el = el.parentElement;
  }
  return null;
}

var view = findView();
if (!view) return JSON.stringify({status: 'no_view'});

var schema = view.state.schema;
var nts = Object.keys(schema.nodes);

// 找到节点类型
var pn = null, im = null;
nts.forEach(function(k) {
  if (k === 'paragraph' || k === 'para') pn = k;
  if (k === 'image' || k === 'imageUpload' || k === 'media' || k === 'img') im = k;
});
if (!im) nts.forEach(function(k) { if (k.toLowerCase().indexOf('image') >= 0 || k.toLowerCase().indexOf('media') >= 0) im = k; });
if (!pn) nts.forEach(function(k) { if (k.toLowerCase().indexOf('para') >= 0) pn = k; });
if (!pn || !im) return JSON.stringify({status: 'no_types', nodes: nts});

// 找到图片节点的属性
var urlAttr = 'src';
var imAttrs = {};
var imSpec = schema.nodes[im];
if (imSpec && imSpec.spec && imSpec.spec.attrs) {
  Object.keys(imSpec.spec.attrs).forEach(function(an) {
    var a = imSpec.spec.attrs[an];
    if (an === 'src' || an === 'url' || an === 'href') urlAttr = an;
    imAttrs[an] = a && a.default !== undefined ? a.default : '[no-default]';
  });
}
var hasDataAttr = imAttrs && Object.keys(imAttrs).indexOf('data') >= 0;

// 获取当前文档中的所有段落节点位置
var doc = view.state.doc;
var paraPositions = [];
doc.descendants(function(node, pos) {
  if (node.type.name === pn) {
    paraPositions.push(pos);
  }
  return true;
});

if (paraPositions.length < data.tp_count) {
  return JSON.stringify({status: 'para_mismatch', expected: data.tp_count, actual: paraPositions.length});
}

// 构建插入事务：在每个布局位置对应的段落后插入图片
var tr = view.state.tr;
var imgIdx = 0;
var inserted = 0;

// 从后往前插入，避免位置偏移
var insertions = [];
var sortedKeys = Object.keys(data.il).map(Number).sort(function(a, b) { return b - a; });

for (var ki = 0; ki < sortedKeys.length; ki++) {
  var targetPara = sortedKeys[ki];  // 1-based
  var numImgs = data.il[targetPara];
  var paraIdx = targetPara - 1;  // 0-based

  if (paraIdx < paraPositions.length) {
    var paraPos = paraPositions[paraIdx];
    // 找到段落的结束位置
    var paraNode = doc.nodeAt(paraPos);
    if (paraNode) {
      var insertPos = paraPos + paraNode.nodeSize;
      for (var j = numImgs - 1; j >= 0; j--) {
        if (imgIdx + j < data.iu.length) {
          var imgUrl = data.iu[data.iu.length - 1 - (imgIdx + j)];
          // 检查是否已经被使用
          var alreadyUsed = false;
          // 简单检查：从当前URL在数组中的位置判断
          insertions.push({pos: insertPos, url: imgUrl, idx: data.iu.length - 1 - (imgIdx + j)});
        }
      }
      imgIdx += numImgs;
    }
  }
}

// 重新排序：从后往前插入
insertions.sort(function(a, b) { return b.pos - a.pos; });

// 执行插入
for (var ii = 0; ii < insertions.length; ii++) {
  var ins = insertions[ii];
  var attrs = {};
  if (hasDataAttr) {
    attrs.data = {url: ins.url, icUri: ins.url, catchErrorUrl: '', link: '', caption: '图片来源于网络', ic: false, naturalHeight: 0, naturalWidth: 0, srcType: '', captionLenErr: false, needCheck: false};
  } else {
    attrs[urlAttr] = ins.url;
    attrs.alt = '图片来源于网络';
  }
  var imgNode = schema.nodes[im].create(attrs);
  tr = tr.insert(ins.pos, imgNode);
  inserted++;
}

if (inserted > 0) {
  view.dispatch(tr);
}

// 验证
var finalImgs = 0;
view.state.doc.descendants(function(node) { if (node.type.name === im) finalImgs++; return true; });
return JSON.stringify({status: 'ok', inserted: inserted, totalImgs: finalImgs, nodes: nts, pn: pn, im: im, urlAttr: urlAttr, hasDataAttr: hasDataAttr, paraCount: paraPositions.length});
})()""")

    return result


async def fill_title(page, title):
    await page.evaluate(f"""
        () => {{
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.focus();
            const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            ns.call(el, {json.dumps(title)});
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
        }}
    """)


async def wait_for_save_indicator(page, timeout=20):
    for i in range(timeout):
        await asyncio.sleep(1)
        saved = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                return false;
            }
        """)
        if saved: return True
    return False


async def trigger_save(page):
    """触发自动保存（通过修改标题再改回来）"""
    await page.evaluate("""
        () => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.focus();
            el.dispatchEvent(new KeyboardEvent('keydown', {key: ' ', bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }
    """)
    await asyncio.sleep(0.3)
    await page.evaluate("""
        () => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]');
            if (!el) return;
            el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.blur();
        }
    """)


async def upload_cover(page, cover_paths):
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("    无有效封面图，跳过")
        return
    print(f"    上传{len(valid)}张封面...")
    await page.evaluate("window.scrollTo(0, 0);")
    await asyncio.sleep(1)
    await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if (r.value === '3') { r.click(); r.dispatchEvent(new Event('change', {bubbles: true})); return; }
            }
        }
    """)
    await asyncio.sleep(2)
    for ci, cf in enumerate(valid):
        print(f"      封面{ci+1}: {os.path.basename(cf)}...", end=" ", flush=True)
        await page.evaluate("""
            () => { const add = document.querySelector('.article-cover-add'); if (add) { add.scrollIntoView({block: 'center'}); add.click(); } }
        """)
        await asyncio.sleep(1.5)
        uploaded = False
        try:
            file_input = page.locator('input[type="file"][accept*="image"]').first
            await file_input.set_input_files(cf, timeout=5000)
            await asyncio.sleep(2)
            uploaded = True
        except:
            try:
                all_inputs = page.locator('input[type="file"]')
                count = await all_inputs.count()
                for i in range(count):
                    inp = all_inputs.nth(i)
                    if await inp.is_visible():
                        await inp.set_input_files(cf, timeout=3000)
                        await asyncio.sleep(2)
                        uploaded = True
                        break
            except: pass
        print("OK" if uploaded else "FAIL")


async def process_article(context, art, index, total):
    title = art["title"]
    html_path = art["html_file"]
    cover_files = art.get("cover_files", [])

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  内容: {len(paragraphs)}段文字, {len(images)}张图片")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    print(f"  压缩: {len(img_bytes_list)}/{len(images)}张有效")

    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")
    print(f"  布局图数: {sum(image_layout.values())}, 实际图数: {len(img_bytes_list)}")

    page = await context.new_page()

    # 拦截保存API响应
    save_results = []
    async def on_response(response):
        url = response.url
        if "mp.toutiao.com" in url and ("save" in url.lower() or "draft" in url.lower() or "publish" in url.lower()):
            try:
                body = await response.text()
                body = body[:500]
            except: body = "[err]"
            save_results.append({"url": url[:200], "status": response.status, "body": body})
    page.on("response", on_response)

    try:
        print(f"  [1/6] 打开发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_notifications(page)

        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }
            """)
            if ready: break
        else:
            print("  [ERROR] 编辑器未就绪")
            return False
        print("  [OK] 编辑器就绪")

        # [2] 上传图片到服务器
        image_urls = []
        if img_bytes_list:
            print(f"  [2/6] 上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid_count = len([u for u in image_urls if u])
            print(f"  上传完成: {valid_count}/{len(img_bytes_list)}张成功")
        else:
            print(f"  [2/6] 无图片，跳过")

        valid_urls = [u for u in image_urls if u]

        # [3] 键盘逐段输入文字
        print(f"  [3/6] 键盘输入{len(paragraphs)}段文字...")
        await remove_overlays(page)
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        for pi, para_text in enumerate(paragraphs):
            await remove_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=0)
            await asyncio.sleep(0.1)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.1)
            if (pi + 1) % 3 == 0:
                print(f"    已输入 {pi+1}/{len(paragraphs)} 段...")

        print(f"  文字输入完成")
        await asyncio.sleep(1)

        # [4] 通过PM API插入图片
        if valid_urls:
            print(f"  [4/6] 插入{len(valid_urls)}张图片...")
            pm_result = await insert_images_via_pm(page, valid_urls, image_layout, len(paragraphs))
            print(f"  PM结果: {pm_result}")
            await asyncio.sleep(2)

            # 验证DOM图片数
            dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
            print(f"  DOM图片数: {dom_imgs}")
        else:
            print(f"  [4/6] 无图片，跳过")

        # [5] 填写标题
        print(f"  [5/6] 填写标题...")
        await fill_title(page, title)
        await asyncio.sleep(3)

        # [6] 触发保存
        print(f"  [6/6] 触发保存...")
        await remove_overlays(page)

        # 先触发自动保存
        await trigger_save(page)
        saved = await wait_for_save_indicator(page, timeout=15)
        if saved:
            print(f"  [OK] 自动保存成功")
        else:
            print(f"  自动保存未确认，尝试预览触发...")
            try:
                preview_btn = page.locator("text=预览").first
                await preview_btn.click(timeout=5000)
                print(f"  已点击预览按钮")
                await asyncio.sleep(5)
                pages = context.pages
                if len(pages) > 1:
                    for p in pages:
                        if p != page:
                            await p.close()
                            await asyncio.sleep(1)
            except:
                print(f"  预览按钮不可用，尝试JS触发...")
                await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if ((b.textContent || '').indexOf('预览') !== -1) { b.click(); return; }
                        }
                    }
                """)
                await asyncio.sleep(5)

            if await wait_for_save_indicator(page, timeout=10):
                print(f"  [OK] 预览保存成功")

        # 打印保存API响应
        for resp in save_results:
            body_str = resp.get('body', '')
            has_img = 'image' in body_str.lower() or 'tos-cn' in body_str.lower() or 'img' in body_str.lower()
            print(f"  Save API: {resp['status']} 含图片={has_img} body={body_str[:200]}")

        # 上传封面
        await upload_cover(page, cover_files)
        await asyncio.sleep(3)
        await trigger_save(page)
        await wait_for_save_indicator(page, timeout=10)

        await page.screenshot(path=f"/workspace/v13_art{index}.png")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v13_art{index}_err.png")
        except: pass
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传\n")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:35]}... | {len(paragraphs)}段 {len(images)}图 | 布局={layout}")
        else:
            print(f"  [{i}] {art['title'][:35]}... | 文件不存在: {html_path}")

    print(f"\n启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        print("验证登录状态...")
        test_page = await context.new_page()
        await test_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await test_page.title()):
            print("[ERROR] Cookie已过期，请更新 toutiao_cookies.json")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await test_page.close()

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                if await process_article(context, art, i, len(articles)):
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [FATAL] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        print(f"\n{'='*60}")
        print("验证草稿箱...")
        verify_page = await context.new_page()
        await verify_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await verify_page.evaluate("() => document.body.innerText.substring(0, 8000)")

        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            status = "[OK]" if found else "[MISS]"
            print(f"  {status} {art['title'][:45]}")

        # 打印草稿箱内容摘要
        print(f"\n  草稿箱内容摘要:")
        draft_lines = [l.strip() for l in draft_text.split('\n') if l.strip() and len(l.strip()) > 5]
        for line in draft_lines[:30]:
            print(f"    {line[:100]}")

        await verify_page.screenshot(path="/workspace/draft_v13_final.png")
        await verify_page.close()
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇成功")
    print(f"请打开 https://mp.toutiao.com/profile_v4/manage/draft 检查草稿箱")


if __name__ == "__main__":
    asyncio.run(main())