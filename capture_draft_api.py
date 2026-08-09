# -*- coding: utf-8 -*-
"""捕获草稿列表API，获取pgc_id"""
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
co.set_address("127.0.0.1:9237")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_api"))

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

# 注入网络拦截器
page.run_js("""
window._apiResponses = [];

var origFetch = window.fetch;
window.fetch = function(url, options) {
    options = options || {};
    var urlStr = typeof url === 'string' ? url : (url && url.url) || '';
    var p = origFetch.apply(this, arguments);
    p.then(function(resp) {
        var sc = resp.status;
        resp.clone().text().then(function(t) {
            if (t.length > 0 && t.length < 50000) {
                window._apiResponses.push({url: urlStr, status: sc, body: t});
            }
        }).catch(function(){});
    }).catch(function(){});
    return p;
};

var origXHRSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(body) {
    var xhr = this;
    this.addEventListener('load', function() {
        if (xhr.responseText && xhr.responseText.length > 0 && xhr.responseText.length < 50000) {
            window._apiResponses.push({url: xhr._url, status: xhr.status, body: xhr.responseText});
        }
    });
    return origXHRSend.apply(this, arguments);
};

var origXHROpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    return origXHROpen.apply(this, arguments);
};
""")

# 导航到草稿箱
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(10)

# 滚动加载
for i in range(3):
    page.run_js("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

# 获取所有API响应
api_data = page.run_js("""
var responses = window._apiResponses || [];
var results = [];
for (var r of responses) {
    var url = r.url || '';
    var body = r.body || '';
    // 过滤掉monitoring请求
    if (url.indexOf('monitor') >= 0 || url.indexOf('collect') >= 0) continue;
    if (body.indexOf('pgc_id') >= 0 || body.indexOf('group_id') >= 0 || body.indexOf('article_id') >= 0 || body.indexOf('draft') >= 0 || body.indexOf('item_id') >= 0 || url.indexOf('draft') >= 0 || url.indexOf('content') >= 0) {
        results.push({url: url.substring(0, 200), body: body.substring(0, 5000)});
    }
}
return JSON.stringify(results);
""")

print("包含草稿数据的API响应:")
try:
    results = json.loads(api_data)
    for i, r in enumerate(results):
        print(f"\n[{i}] URL: {r['url']}")
        print(f"    Body: {r['body'][:1000]}")
except:
    print(api_data[:3000])

# 也打印所有API URL
print("\n\n=== 所有API URL ===")
all_urls = page.run_js("""
var responses = window._apiResponses || [];
var urls = [];
for (var r of responses) {
    var url = r.url || '';
    if (url.indexOf('monitor') < 0 && url.indexOf('collect') < 0) {
        urls.push(url.substring(0, 150));
    }
}
return urls.join('\\n');
""")
print(all_urls[:3000])

page.quit()
print("\nDONE")
