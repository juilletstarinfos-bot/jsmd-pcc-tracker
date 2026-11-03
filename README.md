# 政府採購案追蹤系統（原型 v0.1）

## 資料從哪來
- 官方「政府電子採購網」web.pcc.gov.tw 沒有公開的即時 API，查詢頁有驗證機制且禁止爬蟲（robots.txt）。
- 採用 g0v 社群維護的「標案資料 API」（https://pcc-api.openfun.app/ ，原 pcc.g0v.ronny.tw），它每天同步採購網的招標／決標公告，免費、有 JSON：
  - `GET /api/listbydate?date=YYYYMMDD`：某天所有公告（標案名稱、公告類型、標的分類、機關、廠商）
  - `GET /api/tender?unit_id=..&job_number=..`：單一標案完整內容（預算、截止日、履約地點…）
  - `GET /api/searchbytitle?query=..`、`/api/listbyunit?unit_id=..`、`/api/searchbycompanyname?query=..`
  - 未帶 token 會被限流；可到 https://data.openfun.tw/user 免費申請 token。商業用途請改用官方開放資料。
- 備案：官方開放資料（決標資料 XML，data.gov.tw）。

## 架構
```
GitHub Actions（每天 3 次）
  └─ fetch.py  → 呼叫 listbydate 抓最近 3 天公告
       └─ classify.py + industries.json → 依關鍵字 / CPC 碼分行業（一案可多行業）
            └─ data/tenders.json（保留 90 天）
GitHub Pages
  └─ index.html → 讀 tenders.json：搜尋、公告類型、日期、行業篩選
```
全部是靜態檔，不需要伺服器、不用付費。

## 檔案
- `fetch.py` 抓取與合併資料
- `classify.py` 分類邏輯；`industries.json` 暫定行業規則（等你的行業資料庫取代）
- `index.html` 網頁（欄位依「星傳禧政府標案記錄」表；標案狀態、備註之後做成可共用編輯）
- `data/tenders.json` 目前是**虛構的示範資料**
- `.github/workflows/update.yml` 排程更新

## 本機試跑
```
python fetch.py --days 3
python -m http.server 8000   # 開 http://localhost:8000
```
