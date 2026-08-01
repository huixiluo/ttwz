# -*- coding: utf-8 -*-
"""深度调试封面图上传机制：CDP拦截 + DOM监控 + 多种点击方式"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "single_manifest.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    art = json.load(f)[0]
cover_files = art["cover_files"]
valid = [cf for cf in cover_files[:3] if os.path.exists(cf)]
if not valid:
    print("No valid cover files!")
    exit(1)
print(f"测试封面: {os.path.basename(valid[0])}", flush=True)

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
print("[OK] 登录", flush=True)

page.get(PUBLISH_URL)
time.sleep(6)
for i in range(10):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        break
    time.sleep(1)
try:
    btn = page.ele("text:关闭", timeout=2)
    if btn:
        btn.click()
        time.sleep(1)
except:
    pass

# 选三图模式
page.run_js("window.scrollTo(0, 0);")
time.sleep(1)
page.run_js("""
var labels = document.querySelectorAll('label');
for (var i = 0; i < labels.length; i++) {
    if (labels[i].textContent.indexOf('三图') !== -1 && labels[i].textContent.indexOf('广告') === -1) {
        labels[i].click();
        return;
    }
}
""")
time.sleep(3)
print("已选三图模式", flush=True)

# === 方法1: 用CDP拦截文件选择器 ===
print("\n=== 方法1: CDP Page.setInterceptFileChooserDialog ===", flush=True)
try:
    # 启用文件选择器拦截
    page.run_cdp('Page.setInterceptFileChooserDialog', enabled=True)
    print("  CDP拦截已启用", flush=True)
except Exception as e:
    print(f"  CDP拦截失败: {e}", flush=True)

# 点击add按钮
print("  点击add按钮...", flush=True)
try:
    add_btn = page.ele('.article-cover-add', timeout=5)
    if add_btn:
        add_btn.click()
        print("  DrissionPage点击成功", flush=True)
    else:
        print("  add按钮未找到", flush=True)
except Exception as e:
    print(f"  DrissionPage点击失败: {e}", flush=True)

time.sleep(3)

# 检查是否有文件选择器事件
print("  检查文件输入...", flush=True)
all_inputs = page.run_js("""
var inputs = document.querySelectorAll('input[type="file"]');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push({
        accept: inp.accept || 'none',
        visible: rect.width > 0 && rect.height > 0,
        width: rect.width,
        height: rect.height,
        parent: inp.parentElement ? inp.parentElement.className : 'none'
    });
}
return JSON.stringify(result);
""")
print(f"  file inputs: {all_inputs}", flush=True)

# === 方法2: 注入MutationObserver监控DOM变化 ===
print("\n=== 方法2: MutationObserver监控 ===", flush=True)
page.run_js("""
window.__coverDebug = {addedNodes: [], removedNodes: []};
window.__coverObserver = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
        mutation.addedNodes.forEach(function(node) {
            if (node.tagName === 'INPUT' || (node.querySelectorAll && node.querySelectorAll('input').length)) {
                window.__coverDebug.addedNodes.push({
                    tag: node.tagName,
                    class: node.className,
                    time: Date.now()
                });
            }
        });
        mutation.removedNodes.forEach(function(node) {
            if (node.tagName === 'INPUT') {
                window.__coverDebug.removedNodes.push({
                    tag: node.tagName,
                    class: node.className,
                    time: Date.now()
                });
            }
        });
    });
});
window.__coverObserver.observe(document.body, {childList: true, subtree: true});
window.__coverDebug.addedNodes = [];
window.__coverDebug.removedNodes = [];
""")
print("  MutationObserver已启动", flush=True)

# 再次点击add按钮
print("  再次点击add按钮...", flush=True)
page.run_js("""
var add = document.querySelector('.article-cover-add');
if (add) { add.click(); }
""")
time.sleep(3)

mutations = page.run_js("return JSON.stringify(window.__coverDebug);")
print(f"  DOM变化: {mutations}", flush=True)

# === 方法3: 直接查找所有input（包括隐藏的）===
print("\n=== 方法3: 全面搜索input ===", flush=True)
all_inputs_detailed = page.run_js("""
var inputs = document.querySelectorAll('input');
var result = [];
for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    var rect = inp.getBoundingClientRect();
    result.push({
        index: i,
        type: inp.type,
        accept: inp.accept || 'none',
        className: inp.className,
        visible: rect.width > 0 && rect.height > 0,
        size: rect.width + 'x' + rect.height,
        parentClass: inp.parentElement ? inp.parentElement.className.substring(0, 50) : 'none',
        parentTag: inp.parentElement ? inp.parentElement.tagName : 'none'
    });
}
return JSON.stringify(result);
""")
print(f"  所有input: {all_inputs_detailed}", flush=True)

# === 方法4: 尝试通过React fiber找到上传组件 ===
print("\n=== 方法4: React fiber探索 ===", flush=True)
react_info = page.run_js("""
var result = [];
// 查找article-cover相关元素的React fiber
var coverEl = document.querySelector('.article-cover');
if (coverEl) {
    var key = Object.keys(coverEl).find(k => k.startsWith('__reactFiber'));
    if (key) {
        result.push('Found React fiber key: ' + key);
        var fiber = coverEl[key];
        var depth = 0;
        while (fiber && depth < 10) {
            var type = fiber.type;
            var typeName = typeof type === 'function' ? type.name : (typeof type === 'string' ? type : 'unknown');
            var stateNode = fiber.stateNode;
            var snType = stateNode ? (stateNode.tagName || stateNode.constructor?.name || 'unknown') : 'null';
            result.push('  depth=' + depth + ' type=' + typeName + ' stateNode=' + snType);
            fiber = fiber.return;
            depth++;
        }
    } else {
        result.push('No React fiber key found');
    }
} else {
    result.push('.article-cover not found');
}

// 查找 .article-cover-add 的React fiber
var addEl = document.querySelector('.article-cover-add');
if (addEl) {
    var key2 = Object.keys(addEl).find(k => k.startsWith('__reactFiber'));
    if (key2) {
        result.push('\\nAdd button React fiber:');
        var fiber2 = addEl[key2];
        var depth2 = 0;
        while (fiber2 && depth2 < 5) {
            var type2 = fiber2.type;
            var typeName2 = typeof type2 === 'function' ? type2.name : (typeof type2 === 'string' ? type2 : 'unknown');
            result.push('  depth=' + depth2 + ' type=' + typeName2);
            // Check for props that might reveal upload handler
            if (fiber2.memoizedProps) {
                var props = fiber2.memoizedProps;
                var propKeys = Object.keys(props).filter(k => k !== 'children');
                if (propKeys.length > 0) {
                    result.push('    props: ' + propKeys.join(', '));
                }
            }
            fiber2 = fiber2.return;
            depth2++;
        }
    }
}

return result.join('\\n');
""")
print(f"  React info:\n{react_info}", flush=True)

# 断开observer
page.run_js("if (window.__coverObserver) window.__coverObserver.disconnect();")

# === 方法5: 尝试直接触发文件选择器 ===
print("\n=== 方法5: 直接创建file input并触发 ===", flush=True)
page.run_js("""
// 创建一个可见的file input
var fi = document.createElement('input');
fi.type = 'file';
fi.accept = 'image/*';
fi.style.cssText = 'position: fixed; top: 100px; left: 100px; z-index: 99999; width: 200px; height: 50px;';
fi.id = '__debug_cover_input';
document.body.appendChild(fi);

// 标记
window.__debugInput = fi;
""")
print("  已创建调试用file input", flush=True)

# 尝试用DrissionPage找到它
try:
    debug_input = page.ele('#__debug_cover_input', timeout=3)
    if debug_input:
        print(f"  DrissionPage找到了调试input", flush=True)
        # 尝试上传
        page.set.upload_files(valid[0])
        debug_input.click()
        time.sleep(3)
        print(f"  已点击调试input", flush=True)
    else:
        print(f"  DrissionPage未找到调试input", flush=True)
except Exception as e:
    print(f"  调试input操作失败: {e}", flush=True)

# 清理
page.run_js("""
var fi = document.getElementById('__debug_cover_input');
if (fi) fi.remove();
""")

page.quit()
print("\nDONE", flush=True)