return (async function() {
var art = {"title": "饭局被偷拍流出，贾冰没发火，网友却吵翻了", "text_parts": ["贾冰这人，平时演小品演得乐呵，私底下到底是啥样，外界其实了解不多。一组私人饭局的照片这两天在网上流传，画面里他正和朋友吃饭，姿态随意，跟舞台上那个收放自如的喜剧人没两样。几张照片不算清晰，但能看出桌上没什么排场，就是一桌人聊天吃饭的氛围。", "说实话，偷拍这件事确实不太地道。人家关起门来和朋友吃饭聊天，本就是私事，没招谁没惹谁，结果镜头一伸就给拍下来传开了。换谁心里都不舒服。可贵的是贾冰本人没公开动怒，没发长文控诉，态度挺克制。这种不动声色的反应，反而让人觉得他活得通透。", "不过网友的反应分成两拨。一拨觉得，明星既然吃了公众人物这碗饭，私下被关注也是代价之一，没什么大惊小怪，想图清静就别干这行。另一拨则认为，私人场合就是私人场合，不能因为他是演员就理所当然被偷窥，这跟明星身份没关系，是基本的边界问题，普通人被偷拍还能报警呢。", "这两种说法都有道理，也都没法完全说服对方。关键在于，公众人物这个身份的边界到底划在哪——是只限工作场合，还是连吃顿饭都得算在内。不光娱乐圈在吵，普通网友也各有各的看法，谁也没法给谁下定论。", "其实类似的事这些年挺多。从饭局被拍到机场被围，再到餐厅被认出来要求合影，明星的私人时间越来越像奢侈品。有人习惯了，有人还在适应。这次贾冰的处理方式反而圈了点好感，没闹大，没让事态升级，挺有分寸感。", "喜欢一个演员，最好的方式还是看作品。他在舞台上能让人笑出来，这份本事比私下一顿饭的镜头值得琢磨多了。至于偷拍那件事，权当是给所有人提个醒：边界这两个字，谁都得守，不管是镜头前的人还是镜头后的人。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 651};
var image_urls = window._imgUrls_1 || [];
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
