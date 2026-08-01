# -*- coding: utf-8 -*-
"""探索ProseMirror和React内部结构"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

co = ChromiumOptions()
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
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
page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(6)
for i in range(10):
    if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
        break
    time.sleep(1)

result = page.run_js("""
var editor = document.querySelector('.ProseMirror');
if (!editor) return 'no editor';
var info = [];

// 查找所有以__开头的key
info.push('Editor __ keys:');
for (var k in editor) {
    if (k.startsWith('__')) {
        info.push('  ' + k);
    }
}

// 查找React fiber
var fiberKey = Object.keys(editor).find(function(k) { return k.startsWith('__reactFiber'); });
if (fiberKey) {
    info.push('React fiber key: ' + fiberKey);
    var fiber = editor[fiberKey];
    info.push('Fiber tag: ' + fiber.tag);
    info.push('Fiber type: ' + (typeof fiber.type === 'string' ? fiber.type : (fiber.type ? fiber.type.name : 'null')));
    
    // 查找memoizedProps
    if (fiber.memoizedProps) {
        var mpKeys = Object.keys(fiber.memoizedProps);
        info.push('memoizedProps keys: ' + mpKeys.join(', '));
    }
    
    // 查找stateNode的属性
    if (fiber.stateNode) {
        info.push('stateNode constructor: ' + fiber.stateNode.constructor.name);
        var snKeys = Object.keys(fiber.stateNode).filter(function(k) { return !k.startsWith('_'); });
        info.push('stateNode public keys: ' + snKeys.join(', '));
    }
    
    // 遍历return链找父组件
    var parent = fiber.return;
    var depth = 0;
    while (parent && depth < 10) {
        var parentType = typeof parent.type === 'string' ? parent.type : (parent.type ? (parent.type.name || parent.type.displayName || 'unnamed') : 'null');
        if (parentType !== 'null' && parentType !== 'unnamed') {
            info.push('Parent[' + depth + ']: ' + parentType);
        }
        parent = parent.return;
        depth++;
    }
}

// 查找ProseMirror view
var pmView = editor.pmViewDesc;
if (pmView) {
    info.push('pmViewDesc found');
    info.push('pmViewDesc keys: ' + Object.keys(pmView).join(', '));
}

return info.join('\\n');
""")
print(result)
page.quit()
print("DONE")