// 被 manifest 注入到每个网页里
// 这里可以直接用 document —— 因为它就"活在"网页里

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.cmd === "getCount") {
    let text = document.body.innerText;            // ① 拿整页文字
    let count = text.replace(/\s+/g, "").length;   // ② 去掉空白，数字符

    sendResponse({ count: count });                // ③ 回给 popup

    // ④ 顺手告诉后台：记一笔
    chrome.runtime.sendMessage({ cmd: "record", count: count });
  }
});
