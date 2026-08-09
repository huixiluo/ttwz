# -*- coding: utf-8 -*-
"""获取草稿的pgc_id，用于直接导航到编辑页面"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
    cookies = json.load(f)

co = ChromiumOptions()
co.set_browser_path(CHROME_PATH)
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--window-size=1920,1080")
co.set_address("127.0.0.1:9236")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_ids"))

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass

page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(8)

# 获取草稿项的完整HTML和data属性
draft_data = page.run_js("""
var results = [];

// 查找所有草稿容器
var titleLinks = document.querySelectorAll('a.title');
for (var i = 0; i < titleLinks.length; i++) {
    var link = titleLinks[i];
    var titleText = link.textContent.trim();

    // 向上查找容器
    var container = link;
    for (var j = 0; j < 10; j++) {
        container = container.parentElement;
        if (!container) break;
    }

    // 获取容器的所有data属性
    var dataAttrs = {};
    if (container) {
        for (var attr of container.attributes || []) {
            if (attr.name.startsWith('data-')) {
                dataAttrs[attr.name] = attr.value;
            }
        }
    }

    // 也检查link本身的数据属性
    var linkAttrs = {};
    for (var attr of link.attributes || []) {
        linkAttrs[attr.name] = attr.value;
    }

    // 查找容器中的所有带有data属性的元素
    var allDataEls = [];
    if (container) {
        var els = container.querySelectorAll('[data-id], [data-pgc-id], [data-draft-id], [data-article-id]');
        for (var el of els) {
            allDataEls.push({
                tag: el.tagName,
                attrs: Object.fromEntries(el.attributes && el.attributes.length ?
                    Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => [a.name, a.value]) : [])
            });
        }
    }

    results.push({
        index: i,
        title: titleText,
        linkAttrs: linkAttrs,
        containerData: dataAttrs,
        dataElements: allDataEls
    });
}

return JSON.stringify(results, null, 2);
""")

print("草稿数据:")
print(draft_data[:5000])

# 也尝试获取页面HTML中的ID模式
print("\n\n=== 查找ID模式 ===")
id_patterns = page.run_js("""
var html = document.documentElement.outerHTML;
var results = [];

// 查找pgc_id模式
var pgcMatches = html.match(/pgc_id["\s:=]+["']?(\d+)["']?/gi) || [];
results.push('pgc_id matches: ' + pgcMatches.length);
for (var m of pgcMatches.slice(0, 5)) results.push('  ' + m);

// 查找article_id模式
var artMatches = html.match(/article_id["\s:=]+["']?(\d+)["']?/gi) || [];
results.push('article_id matches: ' + artMatches.length);
for (var m of artMatches.slice(0, 5)) results.push('  ' + m);

// 查找draft_id模式
var draftMatches = html.match(/draft_id["\s:=]+["']?(\d+)["']?/gi) || [];
results.push('draft_id matches: ' + draftMatches.length);

// 查找group_id模式
var groupMatches = html.match(/group_id["\s:=]+["']?(\d+)["']?/gi) || [];
results.push('group_id matches: ' + groupMatches.length);
for (var m of groupMatches.slice(0, 5)) results.push('  ' + m);

// 查找item_id模式
var itemMatches = html.match(/item_id["\s:=]+["']?(\d+)["']?/gi) || [];
results.push('item_id matches: ' + itemMatches.length);
for (var m of itemMatches.slice(0, 5)) results.push('  ' + m);

return results.join('\\n');
""")
print(id_patterns)

# 获取React props
print("\n\n=== React Props ===")
react_props = page.run_js("""
var results = [];
var titleLinks = document.querySelectorAll('a.title');
for (var i = 0; i < Math.min(titleLinks.length, 3); i++) {
    var link = titleLinks[i];
    var props = {};
    // 查找React fiber
    var fiberKey = Object.keys(link).find(k => k.startsWith('__reactProps') || k.startsWith('__reactFiber'));
    if (fiberKey) {
        var fiber = link[fiberKey];
        results.push('Link ' + i + ' fiber key: ' + fiberKey);
    }

    // 查找父容器的React props
    var container = link.parentElement;
    while (container && container.parentElement) {
        var containerFiberKey = Object.keys(container).find(k => k.startsWith('__reactProps'));
        if (containerFiberKey) {
            var props = container[containerFiberKey];
            var propKeys = Object.keys(props || {});
            results.push('Container ' + i + ' props keys: ' + propKeys.join(', '));
            // 尝试获取有意义的props
            for (var pk of propKeys) {
                var val = props[pk];
                if (typeof val === 'string' || typeof val === 'number') {
                    results.push('  ' + pk + ' = ' + val);
                } else if (val && typeof val === 'object' && !Array.isArray(val)) {
                    var subKeys = Object.keys(val).slice(0, 10);
                    results.push('  ' + pk + ' = {' + subKeys.join(', ') + '}');
                }
            }
            break;
        }
        container = container.parentElement;
    }
}
return results.join('\\n');
""")
print(react_props[:3000])

page.quit()
print("\nDONE")
