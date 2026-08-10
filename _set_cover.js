
(function() {
    // 找到"三图"选项并点击
    var allElements = document.querySelectorAll('*');
    var clicked = false;
    for (var i = 0; i < allElements.length; i++) {
        var el = allElements[i];
        if (el.children.length === 0 && el.innerText === '三图') {
            el.click();
            clicked = true;
            break;
        }
    }
    return JSON.stringify({clicked: clicked});
})()
