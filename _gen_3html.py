# -*- coding: utf-8 -*-
"""生成3篇文章HTML（新开头规则：第一段2句以上自然段落，钩子融入叙事）"""
import os
import json
import base64
from datetime import datetime
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config = hnw.load_config()
output_dir = os.path.join(BASE_DIR, config.get("output_dir", "./output"))
os.makedirs(output_dir, exist_ok=True)
os.makedirs(os.path.join(output_dir, "covers"), exist_ok=True)

ARTICLES = [
    {
        "category": "娱乐",
        "keyword": "Jennie不得不用头发遮挡",
        "title": "舞台服装突发移位，她坚持唱完，道歉原因出人意料",
        "article": """东京盛夏的露天音乐节，高温烤着舞台，高强度唱跳进行到一半，Jennie的服装突然移位。台下几万双眼睛盯着，她没有中断演出，靠着长发遮挡，咬牙把剩下的舞台全部完成。

事情发生在8月14日。这个几秒钟的意外瞬间传遍全网，热搜词条里写的是她不得不用头发遮挡。完整演出的视频没什么人看，那一帧尴尬却被反复放大，一场舞台意外硬是演变成了舆论狂欢。

真正让这事出圈的，是接下来的道歉环节。返场时她手抖着，含着泪向观众鞠躬。很多人以为她是为走光道歉，其实不是——她自责的是设备故障导致少唱了两首歌，觉得对不起专程赶来的粉丝。

这个细节让不少围观者转变了态度。舞台出了状况，艺人第一反应不是解释自己的窘迫，而是惦记演出缩水对不起观众，这份职业素养没什么可挑的。没有卖惨，没有甩锅，整个处理方式都挑不出毛病。

争议的另一半集中在服装本身。有网友翻出她过往的舞台造型，质疑这类设计走光风险太高，一次是失误，次次如此就是选择问题。什么时候女爱豆才能穿上正常的衣服跳舞，这条评论获得了大量点赞。

也有声音认为该就事论事。音乐节是表演现场，服装要配合唱跳动作和舞台氛围，跟日常穿衣本来就是两套标准。观众可以不喜欢这个造型，但拿逛街的标准去卡演出服，多少有点偷换场景的意思。

说到底，舞台安全和表演效果不该是对立关系。服装设计再大胆，也得把高强度动作下的风险算进去，这是团队该做的专业功课。艺人在台上已经用临场反应兜了底，幕后该补的课不能少。

一场意外，两种讨论，一个道歉圈了粉，一个疑问留给了行业。观众想看的从来不是完美无缺的机器，而是真正把舞台当回事的人。""",
    },
    {
        "category": "体育",
        "keyword": "国乒GQ封面C位争议",
        "title": "国乒拍GQ封面，C位安排惹争议，成绩才是硬通货",
        "article": """一组时尚大片的C位，怎么就吵起来了？国乒登上GQ封面，本是一次体坛和时尚圈的破圈联动，照片发布后，谁站中间的争论反而盖过了大片本身，一路吵上热搜。

争议的焦点很直白。部分网友对封面站位提出了自己的排序标准，认为按成绩和资历，中间位置不该是照片里的人。粉丝各执一词，路人看得一头雾水，竞技体育的杂志封面，什么时候也开始讲究番位了。

反对的声音占了上风。有人说得直接，运动员不是靠成绩说话吗，有本事多去争怎么让国旗在大赛上站到最中间、站得最高。这条评论获得大量转发，在竞技体育的评价体系里，站位的分量确实比不过奖牌。

还有人拿其他项目举例。按成绩论，射击队的盛李豪16岁拿奥运银牌，19岁奥运双冠，真要排C位也未必轮到别人。这个类比抬杠的成分居多，倒也说明了一个问题：真按成绩排座次，各个项目都能找出理由，永远吵不出结果。

更尖锐的批评指向了流量逻辑。有网友讽刺，奖牌像白给的，C位倒是势在必得，竞技体育学娱乐圈搞番位那一套，本身就是走偏了。运动员的价值在赛场上，不在杂志封面的站位上，这是评论区大多数人的共识。

平心而论，杂志拍摄不是官方合影，站位安排要考虑构图、身高、服装搭配，跟运动员的江湖地位没有必然关系。把娱乐圈的番位文化套到体育大片上，是粉丝入戏太深，不能全怪拍摄方。

这件事真正值得警惕的，是饭圈思维对竞技体育的持续渗透。运动员比的是成绩，观众看的是比赛，杂志封面拍得好看是加分项，拍得不满意也无伤大雅。一旦开始用番位衡量运动员的价值，关注点就彻底跑偏了。

赛场上的C位从来只有一个，就是领奖台的最高处。那上面的位置，靠一板一板的训练去争，比任何大片站位都有说服力。""",
    },
    {
        "category": "社会",
        "keyword": "榴莲价格彻底崩了",
        "title": "榴莲价格崩了，19块9一斤随便挑，自由真来了",
        "article": """往年站在水果店柜台前，一颗榴莲标价两三百，拿起来又放下，反复几次还是舍不得下手。今年同样的位置，四五斤的金枕七八十块就能抱走，批发市场拿货价跌到15元一斤，曾经的水果刺客，这回是真绷不住了。

价格崩盘的直接原因在供给端。前几年榴莲行情好，东南亚种植园批量扩种，今年新种的榴莲树集体进入结果期，货源多到卖不完。再加上铁路冷链运输提速、关税减免落地，运输和进口成本一降，零售价格直接跌到近几年谷底。

消费者的感受最直观。以前买榴莲像开盲盒，一颗下去肉多肉少全凭运气，价格还贵得肉疼。现在超市里19块9一斤随便挑，不少网友晒出购物小票，一颗整果花费不到一百元，实现了搁以前想都不敢想的榴莲自由。

这条降价路径其实并不陌生。阳光玫瑰葡萄走过一模一样的剧本，从刚进入市场时的高价奢侈品，一路跌到如今的平民水果，价格掉到个位数后反而成了日常消费品。农产品扩种之后集中上市，供应放量压低价格，是市场规律的一次次重演。

不过低价之下也有需要留心的地方。有商家提醒，超低价摊位容易出畸形果和熟过头的果子，图便宜买回去，开出来是生包或者过熟发苦，反而闹心。也有网友发现，部分地区十多块一斤的榴莲并不标金枕，品种和品质都要擦亮眼睛分辨。

对榴莲爱好者来说，这波行情是实打实的福利。评论区一片真香，好吃爱吃下次还吃的声音刷了屏。趁着供应高峰入场，用以前一半的预算实现整颗自由，这笔账怎么算都划算。

至于价格会不会一直低位走下去，还真不好说。农产品价格有周期，眼下供大于求的局面短期难改，但种植端一旦开始砍树减产，几年后供需反转，价格回升也是常有的事。眼下的榴莲自由，能享受多久就享受多久。

水果自由清单上又划掉一项，这是普通人对市场波动最直接的体感。趁着行情好多吃两颗，比任何宏观分析都实在。""",
    },
]

print("=" * 60)
print(f"开始生成 {len(ARTICLES)} 篇文章HTML")
print("=" * 60)

session = hnw.get_visitor_session()
results = []

for i, art in enumerate(ARTICLES, 1):
    cat = art["category"]
    keyword = art["keyword"]
    title = hnw.clean_erhua(art["title"])
    article = hnw.clean_erhua(art["article"])
    paragraphs = [p.strip() for p in article.split("\n") if p.strip()]

    print(f"\n[{i}/{len(ARTICLES)}] [{cat}] {title}")
    print(f"  标题：{len(title)}字，逗号{title.count('，')}个，{len(paragraphs)}段，{len(article)}字")
    # 开头规则校验：第一段必须2句以上，且非单句成段
    first_para = paragraphs[0]
    sentence_marks = sum(first_para.count(m) for m in "。！？")
    print(f"  第一段：{len(first_para)}字，{sentence_marks}个句末标点 -> {'OK(多句段落)' if sentence_marks >= 2 else 'FAIL(疑似单句成段)'}")
    assert sentence_marks >= 2, f"第一段疑似单句成段: {first_para}"
    assert hnw._is_three_part_title(title), f"标题非三段式: {title}"
    assert len(title) <= 30, f"标题超30字: {len(title)}"
    assert len(article) > 600, f"正文不足600字: {len(article)}"
    assert all(len(p) <= 150 for p in paragraphs), "存在超150字的段落"

    print(f"  获取配图（关键词：{keyword}）...")
    images = hnw.fetch_images_from_weibo(session, keyword, count=5)
    source = f"微博{len(images)}"
    if len(images) < 5:
        fb = hnw.fetch_images_baidu(keyword, count=5 - len(images))
        images.extend(fb)
        source = f"微博{len(images)-len(fb)}+百度{len(fb)}"
    print(f"  配图：{len(images)}张（{source}）")

    html = hnw.build_html(title, article, images)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{cat}_{i}_{timestamp}"
    html_path = os.path.join(output_dir, f"hot_{prefix}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML：{html_path}")

    cover_paths = []
    for ci, b64 in enumerate(images[:3]):
        img_bytes = base64.b64decode(b64)
        fp = os.path.join(output_dir, "covers", f"{prefix}_cover_{ci+1}.jpg")
        with open(fp, "wb") as f:
            f.write(img_bytes)
        cover_paths.append(fp)
    print(f"  封面：{len(cover_paths)}张")

    layout = hnw._calc_image_layout(len(paragraphs), len(images))
    positions = sorted(layout.keys())
    gaps = [positions[j+1]-positions[j]-1 for j in range(len(positions)-1)]
    tail = len(paragraphs) - positions[-1] if positions else len(paragraphs)
    print(f"  布局：{layout}  空档={gaps}  最大空档={max(gaps) if gaps else 0}  结尾={tail}段")

    results.append({
        "category": cat,
        "keyword": keyword,
        "title": title,
        "article": article,
        "html_file": html_path,
        "cover_files": cover_paths,
    })

manifest_path = os.path.join(BASE_DIR, "batch_manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
import shutil
shutil.copy(manifest_path, os.path.join(output_dir, "batch_manifest.json"))

print(f"\n{'='*60}")
print(f"完成！共 {len(results)} 篇文章，清单已保存")
print(f"{'='*60}")
