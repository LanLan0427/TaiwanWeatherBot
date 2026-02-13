# 自動訂閱系統設定教學 (Google Apps Script)

這份教學將引導您建立一個「伺服器」，讓機器人能夠自動記錄加入的群組 ID，並讓 Python 機器人讀取。

## 步驟 1: 建立 Google Sheet
1. 前往 [Google Sheets](https://sheets.google.com/) 建立一個新的試算表。
2. 將標題命名為 `MyWeatherBot Subscribers` (方便您辨識)。
3. 將下方分頁名稱改為 `Subscribers` (注意大小寫)。
4. 在第一列 (Row 1) 建立標題：
   - A1: `ID`
   - B1: `Type`
   - C1: `Join Date`
5. **複製網址中的 ID** (在 `/d/` 和 `/edit` 之間的那串亂碼)，這是 `SHEET_ID`。

## 步驟 2: 設定 Google Apps Script (GAS)
1. 在試算表中，點擊上方的 **擴充功能 (Extensions)** -> **Apps Script**。
2. 將編輯器中的程式碼清空，貼上 `apps_script.js` 的內容 (若無此檔案，請參考下方附錄)。
3. **修改程式碼第 5 行**：
   ```javascript
   var SHEET_ID = "這裡填入剛剛複製的試算表 ID";
   ```
4. 按 `Ctrl+S` 儲存，專案名稱可隨意取 (如 `WeatherBotBackend`)。

## 步驟 3: 部署為 Web App
1. 點擊右上角的 **部署 (Deploy)** -> **新增部署 (New deployment)**。
2. 點擊左側齒輪 -> 選擇 **網頁應用程式 (Web app)**。
3. 設定如下：
   - **說明**：Auto Subscribe API
   - **執行身分 (Execute as)**：**我 (Me)**
   - **誰可以存取 (Who has access)**：**所有人 (Anyone)** (重要！因為 Line 和 GitHub Actions 需要存取)。
4. 點擊 **部署 (Deploy)** -> **授權存取權 (Authorize access)** -> 選擇您的 Google 帳號 -> 進階 -> 前往 (不安全)。
5. 複製 **網頁應用程式網址 (Web App URL)**，這就是您的 `SUBSCRIBER_API_URL`。

## 步驟 4: 設定 Line Webhook (讓 Line 通知 GAS)
1. 前往 [Line Developers Console](https://developers.line.biz/)。
2. 將 **Webhook URL** 修改為剛剛複製的 **GAS Web App URL**。
3. 點擊 **Verify** 測試 (可能會顯示錯誤不用管它，因為 GAS 預期收到的是 JSON)。
4. 確保 **Use webhook** 是開啟的。

> **注意**：現在 Line 的事件會先傳給 GAS (記錄 ID)，但因為我們要在 Python 廣播，所以這裡不需要把事件轉傳給 Python (Python 是主動廣播)。

## 步驟 5: 設定 Python 機器人
1. 本機 `.env` 新增：
   ```env
   SUBSCRIBER_API_URL="您的 GAS Web App URL"
   ```
2. GitHub Secrets 也新增同樣的變數 `SUBSCRIBER_API_URL`。

## 完成！驗證方式
1. 將機器人踢出群組，再重新邀請進入。
2. 查看 Google Sheet，應該會自動多出一列該群組的 ID。
3. 執行 Python 機器人，它會自動發送給 Sheet 中的所有 ID。

---

## 附錄：GAS 程式碼 (`apps_script.js`)

```javascript
/*
 * LINE Bot 自動訂閱系統 - Google Apps Script
 * 將此代碼貼到 Google Apps Script 編輯器中
 */

// 🔹 這裡一定要改！填入您的 Google Sheet ID
var SHEET_ID = "你的_SHEET_ID_填在這裡"; 

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName("Subscribers");
    var json = JSON.parse(e.postData.contents);
    var events = json.events;
    
    for (var i = 0; i < events.length; i++) {
      var event = events[i];
      var source = event.source;
      var userId = source.userId || "";
      var groupId = source.groupId || "";
      var roomId = source.roomId || "";
      var type = source.type;
      
      // 我們只在乎有人加入群組 (join) 或加好友 (follow) 或傳訊息 (message - 用來捕獲 ID)
      // 這裡簡單暴力，只要有 ID 傳過來，我們就檢查是不是新的
      
      var idToSave = "";
      if (type == "group") idToSave = groupId;
      else if (type == "user") idToSave = userId;
      else if (type == "room") idToSave = roomId;
      
      if (idToSave) {
        saveIdIfNotExists(sheet, idToSave, type);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({status: "success"})).setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({status: "error", message: error.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  // 讓 Python 機器人呼叫這個 GET 接口來取得所有訂閱者 ID
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName("Subscribers");
  var data = sheet.getDataRange().getValues(); // 取得所有資料
  var subscribers = [];
  
  // 從第 2 行開始讀 (第 1 行是標題)
  for (var i = 1; i < data.length; i++) {
    if (data[i][0]) { // 確保 ID 不為空
      subscribers.push(data[i][0]);
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify(subscribers)).setMimeType(ContentService.MimeType.JSON);
}

function saveIdIfNotExists(sheet, id, type) {
  var data = sheet.getDataRange().getValues();
  var exists = false;
  
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] == id) {
      exists = true;
      break;
    }
  }
  
  if (!exists) {
    var date = new Date();
    sheet.appendRow([id, type, date]);
  }
}
```
