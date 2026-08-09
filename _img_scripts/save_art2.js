return (async function() {
var art = {"title": "没刘海判若两人，田曦薇变了，还是滤镜惹的祸", "text_parts": ["一个发型能改变多少？看到田曦薇没刘海的照片，这个问题突然有了答案。平时习惯了她刘海遮额头的模样，露出额头之后整个人的气质都变了，眉眼间的英气一下子凸显出来，难怪网友直呼差点没认出来。", "其实这事挺有意思的。一个演员的长相明明没变，只是换了个发型，给人的感觉却完全不同。这说明很多时候我们记住的并不是一张脸本身，而是某种固定的造型搭配。刘海一摘，像是换了个人，这种反差感本身就是一种新鲜的视觉体验。", "有讨论说这是不是造型团队的刻意安排，让公众看到她更多面的可塑性。也有人说不过是日常随手一拍，没必要过度解读。两种猜测都有可能，毕竟演员的形象管理本就是工作的一部分，但也不必每张照片都往战略层面去想。", "再看观众审美这件事。一个人好不好看，很多时候不是五官决定的，而是整体造型、气质、甚至当天的状态共同塑造的。刘海这种小细节，在不同人脸上效果天差地别。放在田曦薇身上，露出额头反而显出几分凌厉的气场，跟过去偏甜的风格形成对比。", "当然也有人觉得没必要为一张照片讨论这么久，明星换个造型太正常了。这话也没错。但公众对明星外表的关注度一直很高，这也是行业现实，不算什么坏事，说明大家确实在看、在关注。", "说起来，演员能驾驭多种风格其实是优势。今天露出额头有气场，明天换个造型又能走温婉路线，这种可变性对角色塑造是加分项。比起一成不变的标签，能让人看到不同侧面的演员路子更宽。至于田曦薇在新作品里会是什么造型，留到播出那天揭晓也不迟。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 603};
var image_urls = window._imgUrls_2 || [];
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
