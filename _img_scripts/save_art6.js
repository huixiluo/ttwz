return (async function() {
var art = {"title": "U17国足并列夺冠，小将争气了，中国足球有戏吗", "text_parts": ["中国足球听到好消息，总觉得有点不真实。U17国足以东道主身份和阿森纳青年队并列拿下一项赛事的冠军，这个消息传开，足球圈里难得地热闹了一回。不夸张地说，这种久违的振奋感，很多球迷已经等了很久。", "先说成绩本身。能和英超豪门阿森纳的青年梯队并列冠军，说明这批小球员在同龄段是具备竞争力的。比赛细节外界了解有限，但并列冠军不是随便能拿的，背后是训练、战术执行和比赛气质的综合体现。对长期在低谷里打转的中国足球来说，这是一束难得的光。", "当然要冷静。青年队的成绩和成年队之间，隔着一道不小的坎。世界范围内，青少年赛事出彩、成年后泯然众人的例子太多了。身体发育、战术理解的深化、心理成熟度，每一个阶段都有人掉队。所以这个冠军值得高兴，但不宜过度拔高，把它当成什么转折点还为时过早。", "不过话说回来，正视困难不代表否定成绩。这批球员能走到这一步，说明青训体系里是有好苗子的，关键看后续怎么培养。训练质量、比赛机会、留洋通道，这些环节跟上了，小苗才能长成大树。跟不上的话，再好的天赋也会被浪费。", "还有一点，和强队交手本身就是学习。能跟阿森纳青年队真刀真枪地比，对球员的眼界和自信心都是锻炼。这种高水平对抗的机会，对年轻球员来说比国内的一些低强度比赛有价值得多。希望以后这样的交流赛能多一些。", "中国足球这些年让球迷失望太多，所以一点好消息出来，有人不敢信，有人急着唱衰，都正常。但这批小将的成绩是实打实的，给他们一点耐心和掌声不过分。至于将来能走多远，走着看吧，至少这一步是往前的。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 625};
var image_urls = window._imgUrls_6 || [];
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
