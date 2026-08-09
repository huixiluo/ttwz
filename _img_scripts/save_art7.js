return (async function() {
var art = {"title": "雅典娜闺蜜再惹争议，信任被利用，朋友还能信吗", "text_parts": ["网络上又一场关于友情的纠纷闹得沸沸扬扬。网红雅典娜和闺蜜之间的事被翻出来，双方的恩怨细节不断被添油加醋地传播，围观的人越来越多，说法也越来越乱。这种事看多了，难免让人对朋友这个词多想几分。", "事情的来龙去脉，外人很难说清楚。网络上流传的版本各有各的立场，有说是闺蜜背叛在先，有说是利益分配不均，还有各种真假难辨的截图和聊天记录。作为旁观者，看到的信息都是经过筛选和剪辑的，贸然站队容易被打脸。但有一点是确定的：曾经亲密的两个人，闹到公开对簿公堂，这份关系是真的碎了。", "网红之间的友情纠纷，这几年见了不少。表面上是感情问题，背后往往绕不开流量和钱。合作分成、账号归属、商业资源分配，这些利益一旦掺进来，再好的关系也经不起折腾。很多人把网红间的友谊想得太纯粹，其实这个圈子里的合作，本质上也是一种商业关系，边界模糊迟早出问题。", "再说围观心态。每出一次这种事，评论区就分成两派互相攻击，有人誓死挺一方，有人乐得看热闹。其实双方的具体恩怨，外人哪能真知道？多数人只是借别人的事发泄自己的情绪。这种狂欢式的围观，对当事人是二次伤害，对围观者也没什么营养。", "对普通人来说，看这类新闻最大的价值不是站队，而是对照自己。朋友之间如果涉及钱和合作，规矩提前讲清楚，比事后撕破脸强一百倍。感情归感情，账归账，这两样搅在一起，到头来往往是感情和钱一起没。", "至于雅典娜这件事本身，让子弹飞一会吧。网络上的是非，反转的次数多了去了。急着下结论的，到头来往往要收回话。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 614};
var image_urls = window._imgUrls_7 || [];
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
