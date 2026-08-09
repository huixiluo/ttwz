return (async function() {
var art = {"title": "台风白海豚逼近，登陆点预测，沿海该准备了", "text_parts": ["台风的名字起得再温柔，破坏力也不会打折。白海豚这个听起来无害的名字背后，是一场正在逼近沿海的强台风。气象部门持续更新登陆地点的预测，沿海各地的防台工作已经启动，对很多人来说，这又是一个紧张时段。", "预测登陆点这件事，比想象中复杂。台风的路径受大气环流、海温、周边天气系统等多重因素影响，稍有变化路径就会偏移。气象部门发布的\"最大可能登陆地点\"，是基于现有数据的概率判断，不是板上钉钉的结论。所以大家会看到预测点这几天来回调整，这不是预报不准，而是天气本身在变。", "对沿海居民来说，最该做的不是猜它到底从哪登陆，而是把该准备的准备好。手电筒、饮用水、收音机这些应急物资提前备齐，阳台上的花盆杂物该搬就搬，低洼地区的居民留意转移通知。这些事看着琐碎，真到了风大雨急的时候，每一样都可能用上。", "再看信息传递。每次台风来，朋友圈和群里总会传一些未经证实的消息，什么几级几级、几点登陆、哪里要淹。这些信息来源不明，容易引起不必要的恐慌。看天气预报认准官方渠道，转发前多核实一下，对别人对自己都是负责。", "农业和渔业受影响最大。临海的养殖户、渔民这几天都在抢收抢避，跟时间赛跑。作物成熟的也在赶着抢收，赶在风雨来之前把能收的收了。这些人的辛苦，城里人平时不太看得到，但台风一来他们就是承受最直接的一群。", "白海豚最终从哪登陆、有多强，过几天就清楚了。但不管怎样，防台这根弦从现在就得绷紧。天灾面前，宁可准备过度，也别心存侥幸。沿海的朋友多留意官方预警，平安比什么都重要。"], "image_layout": [1, 1, 1, 1, 1, 0], "word_cnt": 620};
var image_urls = window._imgUrls_9 || [];
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
