# Google Cloud セットアップ手順

このドキュメントは、JiraToSlackプロジェクトをGoogle Cloud Platform (GCP) 上にデプロイするための手順を記載します。

## 1. 前提条件

- Google Cloud SDK (`gcloud` CLI) がローカルマシンにインストールされ、認証済みであること。
- 課金が有効になっているGoogle Cloudプロジェクトが作成済みであること。
- プロジェクトに対する `Owner` または `Editor` のIAMロールを持っていること。
- JiraおよびSlackのAPIトークン（または認証情報）が用意できていること。
- Python 3.10 以降が利用可能であること。

## 2. APIの有効化

はじめに、プロジェクトで必要なGCPサービスを有効化します。

```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  eventarc.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com
```

## 3. Secret Managerにシークレットを保存

[環境変数](#環境変数)セクションに記載されている全ての値を、Secret Managerにシークレットとして登録します。

**コマンド例 (`SLACK_BOT_TOKEN` の場合):**
```bash
# シークレットの作成
gcloud secrets create SLACK_BOT_TOKEN --replication-policy="automatic"

# 値（バージョン）の追加
printf "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets versions add SLACK_BOT_TOKEN --data-file=-
```

## 4. Firestoreのセットアップ

1. GCPコンソールでFirestoreに移動します。
2. 「ネイティブモード」を選択してデータベースを作成します。
3. ロケーションを選択します (例: `asia-northeast1`)。

## 5. Cloud Functionのデプロイ

リポジトリのルートで以下のコマンドを実行し、アプリケーション本体をCloud Functionとしてデプロイします。

```bash
gcloud functions deploy jira-slack-bot \
  --gen2 \
  --runtime=python311 \
  --region=asia-northeast1 \
  --source=. \
  --entry-point=main_handler \
  --trigger-http \
  --allow-unauthenticated \
  --set-secrets='SLACK_BOT_TOKEN=SLACK_BOT_TOKEN:latest' \
  --set-secrets='SLACK_SIGNING_SECRET=SLACK_SIGNING_SECRET:latest' \
  --set-secrets='JIRA_DOMAIN=JIRA_DOMAIN:latest' \
  --set-secrets='JIRA_EMAIL=JIRA_EMAIL:latest' \
  --set-secrets='JIRA_API_TOKEN=JIRA_API_TOKEN:latest' \
  --set-secrets='GEMINI_API_KEY=GEMINI_API_KEY:latest'
```

**注意:**
- デプロイ後に出力される**トリガーURL**を、Slackアプリの管理画面 (`App Manifest` > `settings` > `Event Subscriptions`) の `Request URL` に設定してください。
- `--allow-unauthenticated` は、Slackからのリクエストを直接受け付けるために必要です。

## 6. スケジューラ機能のセットアップ

定期実行タスクのために、Pub/Sub, Eventarc, Cloud Schedulerを連携させます。このアーキテクチャにより、スケジューラと本体の関数を疎結合に保ちます。

### ステップ1: Pub/Sub トピックの作成

まず、Cloud Schedulerからのメッセージを受け取るための中継地点となるPub/Subトピックを作成します。

```bash
gcloud pubsub topics create scheduler-topic
```

### ステップ2: Eventarc トリガーの作成

次に、上記で作成した`scheduler-topic`にメッセージが発行されたことを検知し、デプロイ済みのCloud Function (`jira-slack-bot`) を呼び出すためのEventarcトリガーを作成します。

```bash
gcloud eventarc triggers create scheduler-trigger \
  --location=asia-northeast1 \
  --destination-run-service=jira-slack-bot \
  --destination-run-region=asia-northeast1 \
  --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" \
  --event-filters="topic=scheduler-topic"
```

*コマンド実行中に権限付与を求められた場合は `yes` と回答してください。これにより、EventarcがCloud Functionを呼び出すための適切なIAMロールが自動的に設定されます。*

### ステップ3: Cloud Scheduler ジョブの作成

最後に、指定した時間にPub/Subトピックへメッセージを送るCloud Schedulerジョブを作成します。以下の例では、毎日午前9時にタスクを実行します。

```bash
gcloud scheduler jobs create pubsub daily-task-scheduler \
  --schedule="0 9 * * *" \
  --topic="scheduler-topic" \
  --message-body='{"flag": "scheduler_events"}' \
  --time-zone="Asia/Tokyo"
```

## 7. 環境変数

以下の環境変数をSecret Managerに設定する必要があります。

| シークレット名 (SECRET_NAME) | 説明 |
| -------------------------- | -------------------------------------------------- |
| `SLACK_BOT_TOKEN`          | Slack BotのOAuthトークン (`xoxb-`で始まる)         |
| `SLACK_SIGNING_SECRET`     | SlackアプリのSigning Secret                        |
| `JIRA_DOMAIN`              | Jiraのドメイン (例: `your-domain.atlassian.net`)   |
| `JIRA_EMAIL`               | Jira APIの認証に使用するメールアドレス             |
| `JIRA_API_TOKEN`           | Jira APIトークン                                   |
| `GEMINI_API_KEY`           | Google AI Studioで発行したGemini APIキー           |
| `JIRA_PROJECT_KEY`         | (任意) 対象を特定のJiraプロジェクトに限定する場合のキー |
| `JIRA_STORY_POINTS_FIELD`  | (任意) ストーリーポイントが格納されているカスタムフィールドID (例: `customfield_10016`) |