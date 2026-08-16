# -*- coding: utf-8 -*-
"""生成1篇文章HTML并上传草稿箱"""
import os, json, base64
from datetime import datetime
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config = hnw.load_config()
output_dir = os.path.join(BASE_DIR, config.get("output_dir", "./output"))
os.makedirs(output_dir, exist_ok=True)
os.makedirs(os.path.join(output_dir, "covers"), exist_ok=True)

TITLE = "台风走出诡异拐弯，杭州刮起十五级风，周末还能出门吗"
ARTICLE = """台风"白海豚"的走位，连气象预报员都得愣一下。9日傍晚先后在玉环、乐清两次登陆，随后没有按常规路线往西北直冲，而是沿着温州城区一路西偏南缓慢穿行，经瑞安、平阳、泰顺，进入福建寿宁后又折回浙江庆元，画出一道罕见的慢弧线。

这条Z字形大拐弯轨迹，在浙闽之间来回折返，走得又慢又拧巴。台风这种"赖着不走"的走法最让人头疼，影响时间拉长，降雨量叠加，沿途城市承受的压力成倍增加。

杭州出现了15级大风，这个数字放在内陆城市相当罕见。强风裹挟暴雨，市区不少树木被连根拔起，临时搭建物受损，部分路段积水严重。有网友原本计划去杭州找妹妹玩，看到预报后默默打消了念头，这个判断很明智。

"白海豚"在浙江境内停留时间远超预期，缓慢穿行导致持续性强降雨。温州、丽水等多个城市出现暴雨到大暴雨，防汛应急响应接连升级。气象部门反复提醒，影响至少持续到本周末，不可掉以轻心。

11日中午，"白海豚"已减弱为热带风暴，中心附近最大风力8级，位于丽水龙泉市境内。以每小时15到20公里的速度向西北方向移动，强度变化不大。拐弯之后直冲武汉，预计凌晨以热带低压强度从黄冈南部进入湖北。

台风减弱不等于危险解除。热带低压仍携带大量水汽，进入湖北后可能引发新一轮强降雨。武汉及周边地区需要提前做好防范，尤其是低洼地带和山区，防范山洪和地质灾害。

这几天尽量减少外出，确实需要出门的，避开积水路段和广告牌密集区域。原计划周末出行的，不妨推迟几天，安全比什么都重要。密切关注当地气象部门发布的最新预报和预警信息，提前做好准备。

天灾面前，谨慎一点永远没错。各路救援力量已经在一线坚守，普通市民管好自己就是最大的帮忙。希望这轮台风影响尽快消散，所有人平平安安。"""

title = hnw.clean_erhua(TITLE)
article = hnw.clean_erhua(ARTICLE)
paragraphs = [p.strip() for p in article.split("\n") if p.strip()]
keyword = "白海豚突然大拐弯"
cat = "社会"

print(f"标题：{title}（{len(title)}字，逗号{title.count('，')}个）")
print(f"正文：{len(article)}字，{len(paragraphs)}段")
assert hnw._is_three_part_title(title), "标题非三段式!"
assert len(article) > 600, f"正文不足600字: {len(article)}"

session = hnw.get_visitor_session()
print("获取配图...")
images = hnw.fetch_images_from_weibo(session, keyword, count=5)
source = f"微博{len(images)}"
if len(images) < 5:
    fb = hnw.fetch_images_baidu(keyword, count=5-len(images))
    images.extend(fb)
    source = f"微博{len(images)-len(fb)}+百度{len(fb)}"
print(f"配图：{len(images)}张（{source}）")

html = hnw.build_html(title, article, images)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
prefix = f"{cat}_1_{timestamp}"
html_path = os.path.join(output_dir, f"hot_{prefix}.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"HTML：{html_path}")

cover_paths = []
for ci, b64 in enumerate(images[:3]):
    img_bytes = base64.b64decode(b64)
    fp = os.path.join(output_dir, "covers", f"{prefix}_cover_{ci+1}.jpg")
    with open(fp, "wb") as f:
        f.write(img_bytes)
    cover_paths.append(fp)
print(f"封面：{len(cover_paths)}张")

layout = hnw._calc_image_layout(len(paragraphs), len(images))
positions = sorted(layout.keys())
gaps = [positions[j+1]-positions[j]-1 for j in range(len(positions)-1)]
tail = len(paragraphs) - positions[-1] if positions else len(paragraphs)
print(f"布局：{layout}  空档={gaps}  最大空档={max(gaps) if gaps else 0}  结尾={tail}段")

manifest = [{"category": cat, "keyword": keyword, "title": title,
             "article": article, "html_file": html_path, "cover_files": cover_paths}]
mp = os.path.join(BASE_DIR, "batch_manifest.json")
with open(mp, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
import shutil
shutil.copy(mp, os.path.join(output_dir, "batch_manifest.json"))
print(f"\n完成！清单已保存")
