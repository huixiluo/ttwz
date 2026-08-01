# -*- coding: utf-8 -*-
"""检查草稿箱 - 滚动查看完整列表"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

print("[1] 启动浏览器...")
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
    except Exception:
        pass

# 直接访问草稿箱
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(8)
print(f"URL: {page.url}")

# 滚动加载更多并搜索目标文章
result = page.run_js("""
var results = [];
var found = [];

// 先获取当前可见的文章标题
var bodyText = document.body.innerText;
results.push('=== 搜索目标文章 ===');

// 搜索"退货"关键词
if (bodyText.indexOf('退货') !== -1) {
    var idx = bodyText.indexOf('退货');
    results.push('找到"退货": ' + bodyText.substring(idx, idx + 50));
    found.push('退货');
} else {
    results.push('未找到"退货"');
}

// 搜索"取件码"关键词
if (bodyText.indexOf('取件码') !== -1) {
    results.push('找到"取件码"');
    found.push('取件码');
} else {
    results.push('未找到"取件码"');
}

// 搜索"坠楼"或"男友"关键词
if (bodyText.indexOf('坠楼') !== -1) {
    results.push('找到"坠楼"');
    found.push('坠楼');
}
if (bodyText.indexOf('男友') !== -1) {
    results.push('找到"男友"');
    found.push('男友');
}

// 获取所有可见的文章标题（在列表中的文本）
results.push('\\n=== 草稿列表前20条 ===');
var draftItems = bodyText.split('\\n');
var count = 0;
for (var i = 0; i < draftItems.length; i++) {
    var line = draftItems[i].trim();
    if (line && line.length > 3 && line.length < 50 && 
        line.indexOf('头条号') === -1 && line.indexOf('消息') === -1 &&
        line.indexOf('编辑') === -1 && line.indexOf('删除') === -1 &&
        line.indexOf('草稿箱') === -1 && line.indexOf('共') === -1 &&
        line.indexOf('全部') === -1 && line.indexOf('状态') === -1 &&
        line.indexOf('体裁') === -1 && line.indexOf('~') === -1) {
        results.push('  ' + (count+1) + '. ' + line);
        count++;
        if (count >= 20) break;
    }
}

results.push('\\n找到目标: ' + (found.length > 0 ? found.join(', ') : '无'));
return results.join('\\n');
""")
print(f"\n{result}")

# 如果没找到，尝试滚动加载
if '未找到"退货"' in result:
    print("\n[2] 滚动加载更多草稿...")
    for i in range(5):
        page.run_js("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
    
    # 再次搜索
    result2 = page.run_js("""
var bodyText = document.body.innerText;
var results = [];
if (bodyText.indexOf('退货') !== -1) {
    var idx = bodyText.indexOf('退货');
    results.push('找到"退货": ' + bodyText.substring(idx, idx + 50));
} else {
    results.push('滚动后仍未找到"退货"');
}

// 获取所有列表项
results.push('\\n总字符数: ' + bodyText.length);
var totalItems = (bodyText.match(/编辑删除/g) || []).length;
results.push('编辑删除按钮数: ' + totalItems);

return results.join('\\n');
""")
    print(f"\n{result2}")

page.quit()