// ① 点「统计字数」：问当前网页的 content script 要字数
document.getElementById("count").onclick = function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    chrome.tabs.sendMessage(tabs[0].id, { cmd: "getCount" }, function (response) {
      if (chrome.runtime.lastError) {
        // 页面里没有 content script（比如刚装完扩展，页面还没刷新）
        document.getElementById("result").innerText = "请刷新页面后重试";
        return;
      }
      document.getElementById("result").innerText = response.count + " 个字";
    });
  });
};

// ② 点「查看上次结果」：从共享存储里读
document.getElementById("history").onclick = function () {
  chrome.storage.local.get("history", function (items) {
    let h = items.history || [];
    document.getElementById("result").innerText =
      h.length ? "上次：" + h[h.length - 1].count + " 个字" : "还没有历史";
  });
};
