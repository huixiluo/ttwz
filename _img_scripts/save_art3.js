return (async function() {
var art = {"title": "披荆斩棘官宣阵容，老将新面孔齐了，你期待谁", "text_parts": ["综艺节目的阵容永远是开播前最热的话题。披荆斩棘这季的名单一出来，社交平台上讨论就没停过，老面孔带来情怀，新面孔带来悬念，这种搭配本身就自带流量。", "看公布的名单，有几位是观众等了好几季的，终于肯来了。也有几位属于跨界尝试，之前不在大众的综艺认知里。这种混搭的好处是话题层次丰富——老选手之间有交情有故事，新选手能不能融入、会不会有化学反应，都是看点。节目还没开录，观众的期待值已经被拉起来了。", "其实这类节目的核心从来不是单纯比唱跳。真人秀嘛，看的是人在压力下的真实反应，是兄弟情、竞争心、合作中的摩擦和默契。阵容越多元，碰撞的可能就越大。全是熟人容易腻，全是新人又缺抓手，所以老带新是最稳妥的结构。", "每季开播前都有人质疑，是不是该停了、是不是审美疲劳了。但数据说明观众还是买账的，讨论度年年都在。这说明题材本身有生命力，关键看怎么做。阵容只是一道开胃菜，真正决定口碑的还是赛制设计和后期剪辑。把人凑齐不难，难的是让这群人在镜头前真实地碰撞出火花，而不是按剧本走流程。", "从官宣到现在，已经有粉丝开始给自己喜欢的人拉票造势了。这也正常，综艺本来就有互动属性。不过理性看，比赛结果到底怎样谁也说不准，过早押宝容易失望。不如放平心态，看哥哥们怎么把舞台撑起来。", "阵容摆在这了，接下来就看节目组怎么排兵布阵。能把这么多性格各异的人放到一个舞台上，本身就挺考验调度功力的。期待开播之后，这些名字能碰撞出点让人意外的东西。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 598};
var image_urls = window._imgUrls_3 || [];
var results = [];
var content_parts = [];
var img_idx = 0;
for (var t = 0; t < art.text_parts.length; t++) {
    content_parts.push('<p>' + art.text_parts[t] + '</p>');
    if (art.image_layout[t] && art.image_layout[t] > 0) {
        for (var k = 0; k < art.image_layout[t]; k++) {
            if (img_idx < image_urls.length && image_urls[img_idx]) {
                content_parts.push('<img src="' + image_urls[img_idx] + '" alt="图片来源于网络">');
                img_idx++;
            }
        }
    }
}
var content = content_parts.join('\n');
var extra = {content_source: '100000000402', content_word_cnt: art.word_cnt, is_multi_title: 0, sub_titles: [], gd_ext: {entrance: '', from_page: 'publisher_mp', enter_from: 'PC', device_platform: 'mp', is_message: 0}, tuwen_wtt_transfer_switch: '1'};
var formData = new URLSearchParams();
formData.append('source', '29');
formData.append('extra', JSON.stringify(extra));
formData.append('content', content);
formData.append('title', art.title);
formData.append('search_creation_info', JSON.stringify({searchTopOne:0, abstract:'', clue_id:''}));
formData.append('title_id', Date.now() + '_' + Math.floor(Math.random() * 1e16));
formData.append('mp_editor_stat', '{}');
formData.append('is_refute_rumor', '0');
formData.append('save', '0');
formData.append('entrance', '');
formData.append('timer_status', '0');
formData.append('timer_time', '');
formData.append('educluecard', '');
formData.append('draft_form_data', JSON.stringify({coverType:2}));
formData.append('pgc_feed_covers', '[]');
formData.append('article_ad_type', '3');
formData.append('claim_exclusive', '0');
formData.append('is_fans_article', '0');
formData.append('govern_forward', '0');
formData.append('praise', '0');
formData.append('disable_praise', '0');
formData.append('tree_plan_article', '0');
formData.append('star_order_id', '');
formData.append('star_order_name', '');
formData.append('customer_nick_name', '');
formData.append('activity_tag', '0');
formData.append('trends_writing_tag', '0');
var saveResp = await fetch('https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: formData.toString()
});
var saveData = await saveResp.json();
return JSON.stringify({title: art.title, code: saveData.code, message: saveData.message, pgc_id: saveData.data ? saveData.data.pgc_id : null, img_count: image_urls.filter(function(u){return u;}).length, content_length: content.length});
})();
