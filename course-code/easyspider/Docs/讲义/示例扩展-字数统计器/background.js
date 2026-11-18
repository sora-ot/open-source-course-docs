// 后台 service worker：唯一的职责是维护"历史记录"

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.cmd === "record") {
    chrome.storage.local.get("history", function (items) {
      let h = items.history || [];
      h.push({
        url: sender.tab.url,        // sender 参数里自带"从哪个页面发来的"
        count: request.count,
        time: Date.now()
      });
      chrome.storage.local.set({ history: h });
    });
  }
});
