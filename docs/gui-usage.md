# LMIT GUI 操作說明

這份文件說明 `lmit-gui` / `run.bat` 開啟的 Raw Markdown 監控台怎麼使用，以及幾個容易誤解的選項優先順序。

## 啟動方式

在專案根目錄執行：

```powershell
.\run.bat
```

或直接用 Python module：

```powershell
.\.venv\Scripts\python -m lmit.gui
```

GUI 設定會儲存在 `config/gui.settings.json`。這個檔案是本機個人設定，預設不進 git。

## 基本路徑

- 輸入資料夾：要掃描的來源資料夾，可以加入多個。
- 輸出 raw Markdown：轉換後 Markdown 的輸出位置。
- 工作資料夾：manifest、暫存檔、瀏覽器 profile 等工作狀態。
- 報告資料夾：每輪轉換報告會寫在這裡。
- TOML 設定：可指定 `config/config.example.toml` 或自己的 TOML。GUI 右側選項會覆蓋部分 TOML 設定。

LMIT 不會修改、移動或刪除輸入資料夾裡的原始檔案。

## 主要按鈕

- 儲存設定：只儲存 GUI 畫面上的設定，不執行轉換。
- 立即執行一次：依目前 GUI 設定跑一輪轉換，跑完就停止。
- 開始監控：依輪詢秒數持續掃描輸入資料夾。
- 停止 / 中止：送出取消要求。正在進行的工作會在下一個安全中斷點停止。
- 開啟輸出資料夾：開啟 raw Markdown 輸出位置。
- 開啟最近報告：開啟最近一次 conversion report。

## 立即執行一次與監控

`立即執行一次` 不代表強制重做所有檔案。它會照目前設定跑一輪，是否跳過已處理檔案由 `跳過未變更檔案` 和 `覆寫既有輸出` 決定。

`開始監控` 也是同一套轉換邏輯，只是每隔一段時間重跑掃描。監控模式會使用 `穩定秒數` 避免處理還在同步或寫入中的檔案。

## 跳過未變更檔案

勾選 `跳過未變更檔案` 時，LMIT 會用工作資料夾裡的 manifest 判斷檔案能不能跳過。必須同時符合下列條件才會跳過：

- 來源檔案大小未變。
- 來源檔案修改時間未變。
- 來源檔案 SHA-256 未變。
- 上次狀態是 `success` 或 `partial`。
- 上次輸出的 Markdown 檔仍存在。
- 本次的轉換設定 key 與上次一致。
- `覆寫既有輸出` 沒有勾選。

成功跳過時，log 會出現：

```text
[SKIP-UNCHANGED] ...
```

## 覆寫既有輸出

`覆寫既有輸出` 的優先權高於 `跳過未變更檔案`。

實際邏輯是：

```python
if skip_unchanged and not overwrite:
    # 才會檢查 manifest 並跳過
```

所以：

| 跳過未變更檔案 | 覆寫既有輸出 | 結果 |
| --- | --- | --- |
| 勾選 | 不勾選 | 只處理新增、變更、設定 key 改變、失敗或缺輸出的檔案 |
| 勾選 | 勾選 | 不跳過，重新處理所有符合掃描條件的檔案 |
| 不勾選 | 不勾選 | 不看 manifest skip，會重新處理符合掃描條件的檔案 |
| 不勾選 | 勾選 | 重新處理並覆寫符合掃描條件的檔案 |

日常增量使用建議：

- 勾選 `跳過未變更檔案`
- 不勾選 `覆寫既有輸出`

需要全部重建時才勾選 `覆寫既有輸出`。

## 為什麼檔案沒變還是重跑

LMIT 不只看檔案內容，也會看轉換設定 key。只要轉換設定 key 改變，就會視為需要重新產生 Markdown。

目前 key 會受到這些設定影響：

- 是否抓取 `.txt` 裡的 URL content。
- Public URL provider 與 Scrapling 設定。
- Public browser / CDP-first 設定。
- 百度驗證等待設定。
- MarkItDown LLM 圖片描述設定。
- 檔名 enrichment 設定。

因此，如果最近修改了 Baidu、Reddit、Cloudflare、`search.app`、`share.google` 等 public URL 抓取設定，即使 `.pptx` 或 `.pdf` 本身沒變，也可能因 key 改變而重新處理。這是目前設計，用來避免舊 Markdown 沿用不同規則產生的內容。

## 抓取文字檔中的 Link Content

`抓取文字檔中的 link content` 主要作用在 `.txt` 檔：

- LMIT 會先把原始文字轉成 Markdown。
- 解析文字中的 URL。
- 對每個 URL 抓取頁面內容並附在 Markdown 後方。

一般 `.pptx`、`.docx`、`.pdf` 的主要內容轉換由 MarkItDown 完成，不會走 `.txt` 的 URL fetch 附加流程。

Public URL 抓取大致流程：

1. 對 `search.app`、`share.google` 等短鏈先解析到真實 URL。
2. `provider = auto` 時先用 Scrapling static。
3. 內容空白、過短或疑似 blocked 時升級到 Scrapling dynamic。
4. 偵測 Cloudflare 類挑戰時可升級 StealthyFetcher。
5. 最後 fallback 到 MarkItDown 或 Playwright HTML。

## Public URL Mode

GUI 裡的 `Public URL mode` 對應 TOML 的 `[public_fetch].provider`：

- `auto`：使用 Scrapling-first pipeline，必要時 fallback。
- `legacy`：使用較舊的 MarkItDown-first 流程。

日常建議保留 `auto`。如果某些網站在新 pipeline 表現不穩，可以暫時改成 `legacy` 做比較。

## 百度、Cloudflare 與真人瀏覽器

預設設定會讓 `baidu.com` / `tieba.baidu.com` 優先使用 CDP-first 真人瀏覽器流程。

遇到百度安全驗證頁時，LMIT 會開出瀏覽器讓你操作。你完成驗證後，程式會輪詢同一頁，等安全驗證文字消失後再抓內容。

相關 TOML 設定：

```toml
[public_fetch]
public_browser_auto_launch = true
public_browser_profile_dir = ".lmit_work/browser_profiles/public"
public_browser_verification_timeout_seconds = 180
public_browser_verification_poll_seconds = 3
cdp_first_domains = ["baidu.com"]
```

如果瀏覽器頁面跳出來但最後仍 partial，可查看報告中是否有：

```text
[PUBLIC-BROWSER-VERIFY-WAIT]
[PUBLIC-BROWSER-VERIFY-CLEARED]
[PUBLIC-BROWSER-VERIFY-TIMEOUT]
```

## 停止 / 中止的行為

按下 `停止 / 中止` 後，GUI 會送出取消要求，但不一定會立刻停在當下那一行。LMIT 會在下一個安全中斷點停止，避免留下半寫入檔案或破壞 manifest。

常見 log：

```text
已送出停止要求，會在下一個安全中斷點停止目前這輪執行。
[CANCELLED] conversion aborted before next item
```

如果是在 `.txt` URL 抓取中取消，已完成的部分仍可能保存為 partial output。

## 報告與狀態

每輪執行後可用 `開啟最近報告` 查看 Markdown report。常見狀態：

- `[OK]`：成功轉換。
- `[PARTIAL]`：主檔產出成功，但 URL 抓取有失敗、空白、blocked 或被取消。
- `[FAIL]`：該檔轉換失敗。
- `[SKIP-UNCHANGED]`：符合未變更條件，已跳過。
- `[URL_FETCH_FAILED]`：文字檔中的 URL 抓取失敗。
- `[URL_CONTENT_BLOCKED]`：抓到的是驗證頁、登入牆或 blocked 頁。

## 建議操作組合

日常增量轉換：

- `跳過未變更檔案`：勾選
- `覆寫既有輸出`：不勾選
- `抓取文字檔中的 link content`：依需求，通常可勾選
- `Public URL mode`：`auto`

完整重建：

- `跳過未變更檔案`：可勾可不勾，會被覆寫選項蓋過
- `覆寫既有輸出`：勾選

只想快速把檔案本體轉 Markdown、不抓連結內容：

- `抓取文字檔中的 link content`：不勾選
- `跳過未變更檔案`：勾選
- `覆寫既有輸出`：不勾選
