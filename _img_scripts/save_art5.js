return (async function() {
var art = {"title": "王艺迪2比4落败，张本美和涨球了，国乒要警惕", "text_parts": ["输球的滋味不好受，尤其是输给主要对手。王艺迪2比4不敌张本美和，这个比分让不少球迷心里一沉。不是不能接受输球，而是对手越来越强这个事实，值得认真对待。", "比赛过程看，张本美和确实涨球了。无论是节奏控制还是关键分的把握，都比过去更成熟。她年纪还轻，技术框架已经相当完整，再加上比赛气质沉稳，未来几年会是一个持续性的威胁。国乒对她的研究肯定没停过，但对手也在进步，这种追赶和反追赶的较量，本身就是竞技体育的常态。", "王艺迪这场发挥有起伏，几局关键分没拿下来，节奏被打乱了。竞技比赛就是这样，一两个关键分的得失，往往决定整场走向。输一场不代表实力不行，但暴露出的问题值得复盘——是战术执行不到位，还是心理层面有波动，教练组会比外界看得更清楚。", "没必要因为一场失利就唱衰。国乒的厚度和调整能力是公认的，一场比赛的输赢不会动摇根基。但也不能因为整体强大就忽视个体的差距。张本美和这一代日本选手的成长速度，确实在缩短和国乒的差距，这是客观事实。", "女线的现在的竞争格局，比前几年复杂了。不只是张本美和，日本队整体在往上走，欧洲也有新人冒头。国乒的优势还在，但容错空间在变小。每一场都要认真打，每一个对手都不能轻视，这个心态比战术更重要。", "对球迷来说，理性看输赢也是一种成熟。赢了不捧杀，输了不唱衰，给运动员留出调整的空间。接下来的比赛还有很多，一场失利如果能换来更清醒的认识，那这学费就没白交，调整好心态再上场就是了。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 595};
var image_urls = window._imgUrls_5 || [];
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
