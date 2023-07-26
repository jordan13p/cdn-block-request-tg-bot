# CDN Block Requests TG Bot

## 專案說明

此專案建立在 GCP Cloud Functions 上，透過 Telegram Bot 來取得 AWS WAF Rules 或 Cloudflare 的 Requests

操作說明：

1. 輸入 `/rules`，機器人會回應 WAF Rules 選單
2. 選取想要的 Rule 後，會收到 8 則 Sampled Requests 資訊

> <注意> 
> AWS WAF Rules 會取得三小時內的 Sampled Requests，但重複拉取會有機會出現重複訊息
> Cloudflare 會取得三小時內的最後 8 筆資料

Demo：

![CDN Block Requests TG Bot](https://imgur.com/Ngew6CA.png)

參考資料：

- <https://seminar.io/2018/09/03/building-serverless-telegram-bot/>
- <https://stackoverflow.com/questions/66391719/deploying-telegram-bot-to-production-along-with-django-web-site>
- <https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-firewall-events/>

## 架構說明

### CDN Block Requests TG Bot

![CDN Block Requests TG Bot](https://imgur.com/oeDe15l.png)

1. Telegram Bot 傳送訊息至 Cloud Functions
2. Cloud Functions 回傳訊息至 Telegram
3. Cloud Functions 會撈取 AWS 或 Cloudflare 的 Requests 資訊

## 資料夾結構

- `main.py`：接收 Telegram Bot command 訊息內容，並回傳訊息
- `requirements.txt`：Python 會使用到的套件版本

```bash
├── README.md
├── main.py
└── requirements.txt
```

## 專案設定

### Telegram Bot 設定

1. BotFather: `/mybots` > 選擇要修改的Bot，並選擇 Edit Bot > Edit Commands > 輸入 `rules - Get AWS WAF Rules`
2. 使用以下指令設定 Bot Webhook URL

    ```bash
    $ curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<CLOUD_FUNCTIONS_TRIGGER_URL>"
    ```

### Cloud Functions

- `waf_bot_webhook()` 為運行的主函式
- `create_dispatcher()` 初始化 telegram dispatcher
- `rules()` 接收 rules command 訊息，並回傳 WAF Rules 選單
- `handle_callback_query()` 接收選單 Callback 內容，再去 AWS or Cloudflare 撈取 Requests 資訊

在有程式碼的目錄下，執行以下指令上傳

```bash
# Entry point 設定為程式要運行的函式名稱
# 地區設定為臺灣
# Trigger 為 HTTP，會取得觸發網址
# Token & AWS Key 使用環境變數帶入，也可改用 Secret Manager

$ gcloud functions deploy telegram_bot_waf_rule \
--docker-registry=artifact-registry \
--entry-point=waf_bot_webhook \
--region=asia-east1 \
--runtime=python39 \
--trigger-http \
--set-env-vars='TELEGRAM_TOKEN=<TELEGRAM_BOT_TOKEN>,AWS_ACCESS_KEY_ID=<AWS_ACCESS_KEY_ID>,AWS_SECRET_ACCESS_KEY=<AWS_SECRET_ACCESS_KEY>,CLOUDFLARE_TOKEN=<CLOUDFLARE_TOKEN>,CLOUDFLARE_ZONE_TAG=<CLOUDFLARE_ZONE_TAG>'
```
