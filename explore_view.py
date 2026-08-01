# -*- coding: utf-8 -*-
"""探索ProseMirror编辑器，查找view对象的位置"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

def main():
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
    page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
    time.sleep(6)
    for i in range(15):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            print("  [OK] 编辑器已就绪")
            break
        time.sleep(1)

    # 填一些测试文字
    page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (editor) {
    editor.focus();
    var dt = new DataTransfer();
    dt.setData('text/plain', '第一段\\n\\n第二段\\n\\n第三段\\n\\n第四段\\n\\n第五段');
    var pasteEvent = new ClipboardEvent('paste', {bubbles: true, cancelable: true});
    Object.defineProperty(pasteEvent, 'clipboardData', {value: dt, writable: false, configurable: true});
    editor.dispatchEvent(pasteEvent);
}
""")
    time.sleep(2)

    # 探索view对象
    print("\n[2] 探索view对象...")
    result = page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return {error: 'no editor'};

var findings = {};

// 方法1: pmViewDesc
findings.pmViewDesc = !!editor.pmViewDesc;
if (editor.pmViewDesc) {
    findings.pmViewDesc_view = !!editor.pmViewDesc.view;
}

// 方法2: 遍历editor自身的属性
findings.ownProps = [];
for (var key in editor) {
    if (key.startsWith('__') || key.startsWith('_')) {
        var val = editor[key];
        if (val && typeof val === 'object') {
            if (val.view && typeof val.view.dispatch === 'function') {
                findings.ownProps.push({key: key, hasView: true});
            }
            if (val.state && typeof val.dispatch === 'function') {
                findings.ownProps.push({key: key, isView: true});
            }
        }
    }
}

// 方法3: 遍历editor所有属性（包括非__开头的）
findings.allPropsWithView = [];
var keys = Object.getOwnPropertyNames(editor);
for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    try {
        var v = editor[k];
        if (v && typeof v === 'object') {
            if (v.view && typeof v.view.dispatch === 'function') {
                findings.allPropsWithView.push(k);
            }
            if (v.state && typeof v.dispatch === 'function') {
                findings.allPropsWithView.push(k + '(isView)');
            }
        }
    } catch(e) {}
}

// 方法4: 查找React Fiber
findings.reactFibers = [];
var fiberKeys = [];
for (var key in editor) {
    if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
        fiberKeys.push(key);
    }
}
findings.fiberKeys = fiberKeys;

// 方法5: 深度遍历React Fiber树查找view
findings.viewFromFiber = null;
function findViewInFiber(obj, depth, path) {
    if (depth > 5 || !obj || typeof obj !== 'object') return null;
    // 检查是否是view对象
    if (obj.state && typeof obj.dispatch === 'function' && obj.dom) {
        return path;
    }
    // 检查props.view
    if (obj.props && obj.props.view && typeof obj.props.view.dispatch === 'function') {
        return path + '.props.view';
    }
    // 检查children
    if (obj.children) {
        var childKeys = Object.keys(obj.children);
        for (var i = 0; i < childKeys.length; i++) {
            var r = findViewInFiber(obj.children[childKeys[i]], depth + 1, path + '.children.' + childKeys[i]);
            if (r) return r;
        }
    }
    // 检查memoizedProps
    if (obj.memoizedProps) {
        if (obj.memoizedProps.view && typeof obj.memoizedProps.view.dispatch === 'function') {
            return path + '.memoizedProps.view';
        }
        if (obj.memoizedProps.children && typeof obj.memoizedProps.children === 'object') {
            var r = findViewInFiber(obj.memoizedProps.children, depth + 1, path + '.memoizedProps.children');
            if (r) return r;
        }
    }
    // 检查stateNode
    if (obj.stateNode && obj.stateNode !== editor) {
        var r = findViewInFiber(obj.stateNode, depth + 1, path + '.stateNode');
        if (r) return r;
    }
    return null;
}

for (var key in editor) {
    if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
        var path = findViewInFiber(editor[key], 0, key);
        if (path) {
            findings.viewFromFiber = path;
            break;
        }
    }
}

// 方法6: 查找父元素的Fiber
findings.viewFromParent = null;
var parent = editor.parentElement;
var parentDepth = 0;
while (parent && parentDepth < 10) {
    for (var key in parent) {
        if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
            var path = findViewInFiber(parent[key], 0, 'parent[' + parentDepth + '].' + key);
            if (path) {
                findings.viewFromParent = path;
                break;
            }
        }
    }
    if (findings.viewFromParent) break;
    parent = parent.parentElement;
    parentDepth++;
}

// 方法7: 全局变量查找
findings.globalView = null;
if (window.view && typeof window.view.dispatch === 'function') {
    findings.globalView = 'window.view';
}
if (window.editor && window.editor.view) {
    findings.globalView = 'window.editor.view';
}

// 方法8: 遍历所有带有ProseMirror类名的元素
findings.prosemirrorElements = [];
var pmEls = document.querySelectorAll('.ProseMirror');
for (var i = 0; i < pmEls.length; i++) {
    var el = pmEls[i];
    var info = {tag: el.tagName, cls: el.className};
    if (el.pmViewDesc) {
        info.hasPmViewDesc = true;
        info.hasView = !!el.pmViewDesc.view;
    }
    findings.prosemirrorElements.push(info);
}

return findings;
""")
    print(f"探索结果: {json.dumps(result, indent=2, ensure_ascii=False)}")

    # 方法9: 更深度的Fiber遍历
    print("\n[3] 深度Fiber遍历...")
    result2 = page.run_js("""
var editor = document.querySelector('.ProseMirror');
var found = [];

function deepFindView(obj, depth, path, visited) {
    if (depth > 8 || !obj || typeof obj !== 'object') return;
    if (visited.indexOf(obj) !== -1) return;
    visited.push(obj);

    // 检查是否是view对象
    if (obj.state && typeof obj.dispatch === 'function') {
        found.push({path: path, type: 'view', hasDom: !!obj.dom});
        return;
    }

    // 遍历所有属性
    try {
        var keys = Object.keys(obj);
        for (var i = 0; i < Math.min(keys.length, 50); i++) {
            var k = keys[i];
            if (k === 'window' || k === 'document' || k === 'global' || k === 'self') continue;
            try {
                deepFindView(obj[k], depth + 1, path + '.' + k, visited);
            } catch(e) {}
        }
    } catch(e) {}
}

// 从editor的React Fiber开始
for (var key in editor) {
    if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
        deepFindView(editor[key], 0, key, []);
    }
}

// 从父元素开始
var parent = editor.parentElement;
var pDepth = 0;
while (parent && pDepth < 3) {
    for (var key in parent) {
        if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
            deepFindView(parent[key], 0, 'parent' + pDepth + '.' + key, []);
        }
    }
    parent = parent.parentElement;
    pDepth++;
}

return {found: found.slice(0, 10), count: found.length};
""")
    print(f"深度遍历结果: {json.dumps(result2, indent=2, ensure_ascii=False)}")

    # 方法10: 检查ProseMirror实例的其他挂载方式
    print("\n[4] 检查其他挂载方式...")
    result3 = page.run_js("""
var editor = document.querySelector('.ProseMirror');
var findings = {};

// 检查editor是否有EditorView的实例属性
findings.editorViewProps = [];
var allKeys = Object.getOwnPropertyNames(editor);
for (var i = 0; i < allKeys.length; i++) {
    var k = allKeys[i];
    if (k === 'style' || k === 'class' || k === 'id') continue;
    try {
        var v = editor[k];
        if (v && typeof v === 'object' && typeof v.dispatch === 'function') {
            findings.editorViewProps.push(k);
        }
    } catch(e) {}
}

// 检查editor.cmView (CodeMirror集成)
findings.cmView = !!editor.cmView;

// 检查editor.editView
findings.editView = !!editor.editView;

// 检查editor.view
findings.view = !!editor.view;

// 检查docView
findings.docView = !!editor.docView;

// 检查pmViewDesc的详细信息
if (editor.pmViewDesc) {
    findings.pmViewDescKeys = Object.keys(editor.pmViewDesc).slice(0, 20);
    if (editor.pmViewDesc.view) {
        findings.pmViewDescViewKeys = Object.keys(editor.pmViewDesc.view).slice(0, 20);
    }
}

return findings;
""")
    print(f"其他挂载方式: {json.dumps(result3, indent=2, ensure_ascii=False)}")

    page.quit()
    print("\nDONE")

if __name__ == "__main__":
    main()
