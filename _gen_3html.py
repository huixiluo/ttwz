# -*- coding: utf-8 -*-
"""生成3篇文章HTML（新开头规则测试：第一段2句以上自然段落，钩子融入叙事）"""
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
        "keyword": "披荆斩棘排名",
        "title": "披哥排名引争议，小沈阳829票登顶，实力输给人气",
        "article": """选秀节目的票数，从来不只是实力的投票器。《披荆斩棘2026》初舞台8月15日到16日完成直播竞演，27位哥哥的火力值总排名一出炉，围绕情怀和实力的争论就没停过。

榜首的位置被小沈阳拿下，829票，断层领先。他唱的是当年的经典曲目《我只是个传说》，全开麦不说，最后9秒的高音直接把现场气氛顶到最高点。有网友感慨，谁能红过09年的小沈阳，那是真火，第二天全网都在模仿他。

争议出在排名的另一头。曹骏线上人气断层、体能挑战破纪录，国风武打舞台《关山酒》却只拿到772票；张睿全开麦稳定发挥，755票直接排在倒数位置。两人在短视频平台收获大量好评，跟现场排名形成巨大落差，"人气压倒实力"的讨论一下子刷了屏。

替他们不平的声音里，还夹着对其他选手的疑惑。米卡的排名被粉丝直呼不至于此，孙楠那样的唱将也只有826票，比小沈阳还低3票。有人把票数摆在一起对比，越看越觉得现场的投票逻辑看不懂。

平心而论，小沈阳的第一不算爆冷。他这些年开了两年半演唱会，舞台功底是实打实磨出来的，rap和高音都能兜住，情怀只是加分项。真正让人意难平的，是那些实力在线却票数垫底的哥哥，努力没换来相应的回报。

初舞台的投票机制本身也有局限。现场观众的第一印象、情怀滤镜、临场气氛，都会左右手里的票。线上观众看的是完整舞台和细节回放，两边评价体系不一样，落差自然就出现了。节目播到后面，公演舞台会重新洗牌，初舞台的排名未必是终局。

这几年类似的声音在选秀综艺里反复出现，观众一边喊着要看实力，一边用票数把情怀送上高位。节目组要的热度有了，选手的公平感却成了悬案。说白了，竞技类综艺的投票规则，一直没真正解决过这个问题。

对垫底的哥哥们来说，初舞台只是一张起点牌。翻盘的剧本在往季节目里演过很多次，只要后面的公演稳住，排名随时可能改写。观众与其纠结这一场的票数，不如把期待留给接下来的舞台。""",
    },
    {
        "category": "体育",
        "keyword": "吴艳妮13秒12夺冠",
        "title": "黄牌警告后二次起跑，13秒12夺冠，吴艳妮三连冠",
        "article": """起跑前举手示意没准备好，裁判的黄牌先到了，冠军随后也到了。8月16日晚的2026全国田径锦标赛女子100米栏决赛，吴艳妮顶住黄牌警告的压力，二次起跑后跑出13秒12，强势撞线夺冠。

这块金牌的分量不轻。凭借这个成绩，她实现了全国锦标赛的三连冠，同时加冕赛事史无前例的六冠王。从被质疑的网红选手，到国内赛场上独一档的存在，她用一栏一栏的硬成绩，把争议一个个跨了过去。

熟悉吴艳妮的人都知道，这一路她跨过的栏，远不止赛道上那十个。爱化妆、爱表达、性格张扬，这些特质放在娱乐行业是加分项，放在运动员身上却常年招黑。有人盯着她的妆造说三道四，有人拿着她赛场外的言行攻击她的职业态度。

支持她的网友说得很直白：化最浓的妆，跨最快的栏，这有什么问题。成绩单摆在那里，13秒12的夺冠成绩在国内赛场具有统治力，训练水平和比赛能力没有任何水分。用运动员的旗号去约束一个爱自己爱漂亮的女孩子，本身就是一种苛刻。

这次决赛的小插曲也侧面说明了她的大心脏。起跑前举手示意没准备好，被出示黄牌，这种情况下很多选手会乱了节奏。她反而在二次起跑里调动出最佳状态，把压力转化成了爆发力，这种临场素质是顶级选手的标配。

接下来的目标很明确，备战亚运会。国内赛场的荣誉柜已经装满，更大的考验在洲际赛场。她的个人最好成绩距离亚洲顶尖水平还有提升空间，亚运会正是检验冬训成果和竞技状态的最好舞台。

从更大的视角看，吴艳妮的存在让女子跨栏项目的关注度肉眼可见地提高了。以前田径比赛的直播弹幕稀稀拉拉，现在她出场，讨论度不输任何热门赛事。有争议有关注，总比没人看强，这是竞技体育走向大众的必经之路。

看台上的欢呼和平板上的质疑，她都收下了，然后把答案写进成绩里。下一个赛场见分晓，希望这股劲头能一路跨到亚运会的领奖台上。""",
    },
    {
        "category": "社会",
        "keyword": "女主播希望停止榜一大哥病态折磨",
        "title": "女主播被诉诈骗2500万，自曝遭胁迫，真相成罗生门",
        "article": """一边是检察机关的诈骗罪指控，一边是当事人自述长期被胁迫的控诉，这起涉案约2500万元的案子，如今成了一场各执一词的罗生门。拥有近200万粉丝的女主播魏莹被检方提起公诉，她本人随后公开发声，喊话希望停止榜一大哥的病态折磨，双方说法完全对立。

检方的指控很具体。起诉书称魏莹自2019年起虚构单身未婚人设，以建立恋爱暧昧关系为由，诱使三名已婚被害人刷高额虚拟礼物，累计骗取约2500万元。如果指控成立，这就是一起典型的借感情包装实施的诈骗案。

女主播这边给出了完全不同的版本。她表示自己长期遭到榜一大哥以"陪睡还是坐牢"相要挟的病态折磨，打赏的甜蜜期过后，对方的控制欲逐步升级，从要求私下来往到以举报相威胁，她一直活在恐惧里。此前网传的报案人关联14家企业、担任9家法定代表人的信息，也让这层关系多了几分微妙。

两种叙事摆在一起，各自的漏洞也很明显。如果打赏纯粹出于自愿，为何事后反复施压索要超出直播范畴的回报；如果真是被胁迫，虚构单身人设诱导已婚人士刷礼物的行为，又该如何自圆其说。真相大概率在两个版本之间，具体如何，只能等证据说话。

法律层面有一条底线需要厘清。有评论指出，直播打赏本质是粉丝自愿的娱乐消费，不能等同于购买情感、支配他人的契约。金钱可以支持主播的内容，但无权逼迫对方接受交往、服从自己的要求，感情和人身自由，永远不能被重金定价。反过来说，主播若靠虚构人设收割打赏，同样越过了法律的边界。

网上的态度分成好几派。有人觉得双方都不值得同情，一个图钱一个图色，闹掰了才互撕；有人坚持疑罪从无，判决前不该舆论定罪；还有人关注事件背后的直播生态，榜一大哥文化把打赏变成了情感勒索的工具，这种畸形关系早该被审视。

这起案件之所以受关注，还因为它戳中了直播行业的灰色地带。打赏金额越滚越大，主播的人设越包装越完美，观众的情感投入越来越深，三条线缠在一起，出事只是时间问题。2500万的数字是极端案例，小额版本的纠纷每天都在发生。

是非对错，最终要由法庭依据证据裁决。在判决落下之前，不妨让子弹再飞一会儿。不管哪一方的说法成立，这起案子都值得整个行业反思：流量和金钱纠缠的地方，边界感是最后的护栏。""",
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
    # 开头规则校验：第一段必须2句以上（句号/问号/感叹号计数>=2），且非单句成段
    first_para = paragraphs[0]
    sentence_marks = sum(first_para.count(m) for m in "。！？")
    print(f"  第一段：{len(first_para)}字，{sentence_marks}个句末标点 -> {'OK(多句段落)' if sentence_marks >= 2 else 'FAIL(疑似单句成段)'}")
    assert sentence_marks >= 2, f"第一段疑似单句成段: {first_para}"
    assert hnw._is_three_part_title(title), f"标题非三段式: {title}"
    assert len(title) <= 25, f"标题超25字: {len(title)}"
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
