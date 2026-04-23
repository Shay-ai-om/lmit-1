# Session / Cookie 固化復用策略

## 目前建議

LMIT 第一版先保留 Playwright storage state 作為登入頁面抓取的基線方案。

原因：

- 它是程式庫層級方案，容易包成 CLI、Docker 任務與排程服務。
- storage state 可保存 cookies、local storage 等登入狀態，符合「先手動登入，後續批次復用」的需求。
- 不需要把整個個人瀏覽器 session 暴露給 agent。
- 適合 Unraid / Docker 這種長期背景服務環境。

目前程式已將 Playwright 做成選配：

- 不需要登入頁面時，只安裝核心依賴即可。
- 需要登入頁面時，再安裝 `.[session]` 並執行 `playwright install chromium`。
- session state 存在 `sessions/`，已加入 `.gitignore`。
- session 抓取已拆成 provider/strategy：`PlaywrightBrowserProvider` 是預設 provider，Facebook 的 desktop/mobile/mbasic 特例集中在 `FacebookSessionStrategy`。

## 可替代方案比較

### 1. Playwright storage state

適合做本專案預設方案。

優點：

- 可程式化、可部署、可測試。
- 和現有範本程式相容。
- 容易支援多站點設定，例如 Facebook、Reddit、X 等。
- 可在 Docker 中穩定運行。

限制：

- 某些網站會偵測自動化瀏覽器。
- session storage 不一定完整持久化，必要時需額外注入保存邏輯。
- 登入狀態過期後仍需重新登入。

參考：Playwright 官方 authentication 文件建議將 authenticated browser state 存成檔案，並提醒該檔案包含敏感 cookies/headers，不應提交到版本控制。

### 2. OpenClaw / Chrome DevTools MCP existing-session

適合做「人正在電腦前、希望直接使用既有 Chrome 登入狀態」的互動模式，不建議作為本專案第一個背景服務基線。

優點：

- 可連到使用者既有 Chrome session，直接沿用已登入狀態。
- 對某些會阻擋 WebDriver/自動化登入的網站更自然。
- OpenClaw 文件也支援 openclaw-managed profile、remote CDP、existing-session profile 等模式。

限制：

- 需要使用者啟用/允許 remote debugging 或 Chrome DevTools MCP auto connect。
- 會暴露目前瀏覽器內容與登入狀態，安全風險較高。
- 更像 agent 操作介面，不像單純批次轉 Markdown 的後端元件。
- 在 Unraid Docker 背景服務中較不自然，尤其當容器沒有桌面瀏覽器 session。

建議定位：

- 後續可做成 `browser_provider = "openclaw"` 或 `browser_provider = "chrome-devtools-mcp"` 的進階 fetcher。
- 不取代 Playwright baseline。
- 僅在明確需要「接管既有瀏覽器」時啟用。

### 3. 遠端持久瀏覽器服務：Browserless / Kernel 等

適合做進階部署或付費外部服務選項。

優點：

- 可保存更完整的瀏覽器狀態，例如 cookies、local storage、session storage、cache，甚至整個瀏覽器 instance。
- 適合人機協作登入、稍後自動化接手的流程。
- 可以減少本機 Docker 內安裝瀏覽器的維護成本。

限制：

- 多半是外部服務，涉及成本、隱私與網路依賴。
- 對個人知識庫專案而言，初期複雜度偏高。

建議定位：

- 等本地 pipeline 穩定後，再做成可選 remote browser provider。

## 建議演進路線

1. 短期：使用 Playwright storage state，完成穩定的本地批次抓取。
2. 中期：在既有 provider 介面下新增 `chrome-devtools-mcp`、`openclaw` 等 provider。
3. 長期：若部署到 Unraid 後仍常遇到反自動化或登入失效，再評估 Browserless / Kernel 這類持久瀏覽器服務。

目前的程式結構已先拆出 `fetchers/session_url.py`、`sessions/browser_provider.py`、`sessions/strategies/` 與 `sessions/manager.py`，後續要替換 provider 時不需要重寫 scanner、manifest 或轉換管線。
