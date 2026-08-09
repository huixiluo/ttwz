return (async function() {
var art = {"title": "王楚钦入选青年榜，球技在线，商业价值也跟上了", "text_parts": ["过去说起运动员，大家第一反应是赛场成绩。现在榜单越来越多，衡量维度也宽了。王楚钦入选中国品牌青年榜，释放出一个信号：乒乓球运动员的商业价值，正在被更广泛地认可。", "王楚钦的实力不用多说，世界排名摆在那，关键比赛的发挥也稳。入选这类榜单，说明他不光球打得好，在品牌方眼里也具备号召力。年轻、形象正面、成绩过硬，这几样凑在一起，商业合作自然找上门。体育和商业挂钩不是坏事，反而说明项目本身的热度在涨。", "有人担心运动员过度接商业活动会影响训练。这个顾虑合理，但也要看具体情况。国乒对运动员的商业活动一直有管理，不是想接就接。合理的商业合作反而能帮助推广项目，让更多人关注乒乓球，对整个运动的发展是正向的。", "再看这类青年榜单的评选标准，通常比较综合，不光看成绩，还看社会影响力、公众形象、发展潜力。王楚钦能在多个维度上被认可，说明他作为公众人物的整体形象是站得住的。这对年轻运动员来说是个正面的示范——好好打比赛，场外的认可自然会来。", "横向看看其他项目的年轻选手，其实都在面临类似的关口。成绩是根基，但怎么在成绩和商业之间找平衡，是新一代运动员都要学的课题。有人处理得好，路越走越宽；有人分了心，成绩反而下滑。这个度，需要运动员和团队一起把控。", "对王楚钦来说，榜单是一份认可，也是一种提醒。还年轻，路还长，赛场上的硬成绩永远是最硬的底气。商业价值是成绩的副产品，主次别搞反了，一步一个脚印，路才能走得稳。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 592};
var image_urls = window._imgUrls_4 || [];
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
