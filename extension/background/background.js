console.log("[Travel Agent] Background service worker loaded");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("[Travel Agent] Background received:", message);

  if (message.type === "GET_ACTIVE_TAB") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      sendResponse({
        ok: true,
        tab: tabs[0]
      });
    });

    return true;
  }
});