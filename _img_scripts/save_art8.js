return (async function() {
var art = {"title": "老人想验孙子血缘，儿媳拒了，这家账怎么算", "text_parts": ["一个家庭里儿子走了，留下老人、儿媳和年幼的孙子。老人提出要给孙子做一次血缘鉴定，儿媳拒绝了。这件事一曝光，网上的讨论就没停过，每个人都能从自己的角度说出几分道理，但也都没法替当事人做决定。", "老人的心思能理解。儿子不在了，想知道孙子是不是自家的血脉，这种念头说不上多高尚，但放在失独的背景下，不算过分。老人怕的是辛辛苦苦养大的孙子，万一跟自家没血缘，那份传承就断了。这种担忧，根子上是对儿子离去后自己位置的不安。", "儿媳这边也有她的立场。丈夫刚走，公公就提出要验孩子的血缘，换谁心里都不好受。这不光是个技术问题，更是一种信任的考验。验了，等于承认了怀疑；不验，又会被解读成心里有鬼。怎么选都难。何况孩子还小，这种事对孩子将来的影响，做母亲的不能不考虑。", "法律层面其实有说法。近亲之间的血缘鉴定，如果一方不同意，法院一般不会强制，但可能会在证据上作不利于拒方推定。也就是说，拒绝对儿媳不一定有利。但法律归法律，亲情归亲情，赢了官司输了感情的事，在这个家里恐怕已经发生了。", "真正难的是孩子。大人吵来吵去，最终受影响最深的是那个还不懂事的小孩。将来长大知道了这些事，他会怎么看待这个家？老人的焦虑可以理解，儿媳的抵触也能共情，但双方是不是该把孩子的感受放在前面想一想？", "这类家务事，外人很难评出个绝对的对错。家家有本难念的账，这本账里掺着失去亲人的痛、对未来的不安、还有信任的裂痕。能坐下来好好谈，比争个输赢重要得多。实在谈不拢，走法律程序也是一种选择，但走到那一步，这个家基本也就散了。"], "image_layout": [1, 0, 0, 0, 0, 0], "word_cnt": 634};
var image_urls = window._imgUrls_8 || [];
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
