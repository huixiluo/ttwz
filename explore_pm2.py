# -*- coding: utf-8 -*-
"""探索ProseMirror EditorView"""
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

// 查找所有属性
var allKeys = [];
for (var k in editor) {
    allKeys.push(k);
}
info.push('All keys: ' + allKeys.filter(function(k) { return k !== 'pmViewDesc'; }).join(', '));

// 查找parent上的ProseMirror view
var parent = editor.parentElement;
info.push('Parent tag: ' + parent.tagName);
info.push('Parent class: ' + parent.className);
for (var k in parent) {
    if (k.startsWith('__') || k.indexOf('View') !== -1 || k.indexOf('view') !== -1 || k.indexOf('pm') !== -1 || k.indexOf('editor') !== -1) {
        info.push('Parent key: ' + k);
    }
}

// 查找全局ProseMirror view - 可能在window上
var globalKeys = [];
for (var k in window) {
    if (k.toLowerCase().indexOf('view') !== -1 || k.toLowerCase().indexOf('editor') !== -1 || k.toLowerCase().indexOf('pm') !== -1) {
        globalKeys.push(k);
    }
}
if (globalKeys.length > 0) {
    info.push('Global keys: ' + globalKeys.join(', '));
}

// 尝试通过jQuery或data属性查找
var dataKeys = Object.keys(editor.dataset || {});
info.push('data-* keys: ' + dataKeys.join(', '));

// 检查是否有ProseMirror的EditorView实例
// 通过检查contentDOM的父节点
var contentDOM = editor.querySelector('[contenteditable]') || editor;
info.push('contentDOM: ' + (contentDOM === editor ? 'self' : 'child'));

// 尝试在编辑器的所有父节点上查找
var node = editor;
var depth = 0;
while (node && depth < 5) {
    var found = [];
    for (var k in node) {
        if (k.indexOf('View') !== -1 || k.indexOf('view') !== -1 || k === 'editorView') {
            found.push(k);
        }
    }
    if (found.length > 0) {
        info.push('Node[' + depth + '](' + node.tagName + '): ' + found.join(', '));
    }
    node = node.parentElement;
    depth++;
}

return info.join('\\n');
""")
print(result)
page.quit()
print("DONE")