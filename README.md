# JiraToSlack

Jiraと連携し、SlackからJiraのタスクを検索したり、定期的にタスクを通知したりするためのBotです。
Google Cloud Platform (GCP) 上で動作します。

## 目次

- [アーキテクチャ概要](#アーキテクチャ概要)
- [前提条件](#前提条件)
- [GCPセットアップ手順](#gcpセットアップ手順)
  - [1. gcloud CLI のインストールと設定](#1-gcloud-cli-のインストールと設定)
  - [2. GCPプロジェクトと課金のセットアップ](#2-gcpプロジェクトと課金のセットアップ)
  - [3. APIの有効化](#3-apiの有効化)
  - [4. Secret Manager の設定](#4-secret-manager-の設定)
  - [5. Firestore の設定](#5-firestore-の設定)
- [アプリケーションのデプロイ](#アプリケーションのデプロイ)
- [スケジューラ機能のセットアップ](#スケジューラ機能のセットアップ)
  - [ステップ1: Pub/Sub トピックの作成](#ステップ1-pubsub-トピックの作成)
  - [ステップ2: Eventarc トリガーの作成](#ステップ2-eventarc-トリガーの作成)
  - [ステップ3: Cloud Scheduler の設定](#ステップ3-cloud-scheduler-の設定)
- [環境変数](#環境変数)

## アーキテクチャ概要

このアプリケーションは、主に単一の**Cloud Function (第2世代)** としてデプロイされます。Cloud Functions (第2世代) は内部的にCloud Run上で動作するため、スケーラビリティと柔軟性に優れています。

主な処理の流れは以下の2通りです。

1.  **Slackからの対話的リクエスト**:
    -   ユーザーがSlackでスラッシュコマンド (`/jira_get_tasks`など) を実行します。
    -   SlackがCloud FunctionのHTTPエンドポイントを直接呼び出します。
    -   Cloud Function内の**Slack Bolt**フレームワークがリクエストを処理し、必要に応じてJira APIを叩き、結果をSlackに返信します。

2.  **スケジュールされたタスク通知**:
    -   **Cloud Scheduler**が設定されたスケジュール（例: 毎日午前9時）になると、ジョブを実行します。
    -   ジョブは、特定のメッセージを**Pub/Sub**トピックに送信（Publish）します。
    -   **Eventarc**がこのPub/Subへのメッセージ発行を検知し、トリガーとして設定されたCloud FunctionのHTTPエンドポイントを呼び出します。このとき、Pub/Subメッセージがリクエストボディに含まれます。
    -   Cloud Functionはリクエストボディを解析し、スケジューラタスク（全ユーザーのJiraタスクを取得してDMで通知）を実行します。

**その他の主要サービス:**
- **Firestore**: ユーザー情報（Slack IDとJiraのメールアドレス）を保存するNoSQLデータベース。
- **Secret Manager**: SlackやJiraのAPIキー、トークンなどの機密情報を安全に保管します。
- **Cloud Build**: `gcloud functions deploy`コマンドを実行すると、裏側でCloud Buildがソースコードをコンテナイメージにビルドし、Cloud Runにデプロイします。

## 前提条件

- Google Cloud Platform (GCP) アカウント
- `gcloud` CLI がインストールされていること
- Python 3.10 以降

## GCPセットアップ手順

### 1. gcloud CLI のインストールと設定

1.  **インストール**:
    公式ドキュメントに従って、お使いのOSに`gcloud` CLIをインストールしてください。
    [gcloud CLI インストールガイド](https://cloud.google.com/sdk/docs/install)

2.  **初期化とログイン**:
    ```bash
    gcloud init
    ```

3.  **プロジェクト設定**:
    ```bash
    gcloud config set project YOUR_PROJECT_ID
    ```
    `YOUR_PROJECT_ID` は実際のプロジェクトIDに置き換えてください。

### 2. GCPプロジェクトと課金のセットアップ

- GCP Consoleで新しいプロジェクトを作成し、課金アカウントをリンクしてください。

### 3. APIの有効化

以下のコマンドを実行して、プロジェクトで必要なAPIを有効化します。

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

### 4. Secret Manager の設定

[環境変数](#環境変数)セクションにリストされている各変数に対して、シークレットの作成と値の設定を行います。

```bash
# シークレットを作成 (例: SLACK_BOT_TOKEN)
gcloud secrets create SLACK_BOT_TOKEN --replication-policy="automatic"

# シークレットに値を設定
printf "xoxb-YOUR-SLACK-BOT-TOKEN" | gcloud secrets versions add SLACK_BOT_TOKEN --data-file=-
```

### 5. Firestore の設定

1.  GCP ConsoleでFirestoreに移動します。
2.  「ネイティブモード」を選択してデータベースを作成します。
3.  ロケーションを選択します（例: `asia-northeast1`）。

## アプリケーションのデプロイ

以下のコマンドで、アプリケーション本体をCloud Functionとしてデプロイします。この時点では、Slackからのリクエストのみを受け付けます。

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

デプロイが完了すると、HTTPトリガーURLが発行されます。このURLをSlackアプリの管理画面 (Request URL) に設定してください。

## スケジューラ機能のセットアップ

次に、定期実行タスクのための連携を設定します。

### ステップ1: Pub/Sub トピックの作成

まず、Cloud Schedulerからのメッセージを受け取るための中継地点となるPub/Subトピックを作成します。

```bash
gcloud pubsub topics create scheduler-topic
```

### ステップ2: Eventarc トリガーの作成

次に、上記で作成した`scheduler-topic`にメッセージが発行されたことを検知し、デプロイ済みのCloud Function (`jira-slack-bot`) を呼び出すためのEventarcトリガーを作成します。これがPub/SubとCloud Functionを繋ぐ「接着剤」の役割を果たします。

```bash
# 環境変数を設定
export TRIGGER_NAME=scheduler-trigger
export LOCATION=asia-northeast1 # デプロイしたリージョン
export FUNCTION_NAME=jira-slack-bot
export TOPIC_NAME=scheduler-topic

# Eventarcトリガーを作成
gcloud eventarc triggers create $TRIGGER_NAME \
  --location=$LOCATION \
  --destination-run-service=$FUNCTION_NAME \
  --destination-run-region=$LOCATION \
  --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" \
  --event-filters="topic=$TOPIC_NAME"
```

**重要**: 初回作成時に、Eventarcが使用するサービスアカウントに必要な権限を付与するよう求められる場合があります。指示に従って権限を付与してください。

### ステップ3: Cloud Scheduler の設定

最後に、指定した時間にPub/Subトピックへメッセージを送るCloud Schedulerジョブを作成します。以下の例では、毎日午前9時にタスクを実行します。

```bash
gcloud scheduler jobs create pubsub daily-task-scheduler \
  --schedule="0 9 * * *" \
  --topic="scheduler-topic" \
  --message-body='{"message": "flag","data": "nothing","flag": "execute_special_task"}' \
  --time-zone="Asia/Tokyo"
```

これで、毎日午前9時に`daily-task-scheduler`が`scheduler-topic`にメッセージを送信し、それをEventarcが検知して`jira-slack-bot`関数が実行される、という一連の流れが完成しました。

## 環境変数

以下の環境変数をSecret Managerに設定する必要があります。

| シークレット名 (SECRET_NAME) | 説明 |
| -------------------------- | -------------------------------------------------- |
| `SLACK_BOT_TOKEN`          | Slack BotのOAuthトークン (`xoxb-`で始まる)         |
| `SLACK_SIGNING_SECRET`     | SlackアプリのSigning Secret                        |
| `JIRA_DOMAIN`              | Jiraのドメイン (例: `your-domain.atlassian.net`)   |
| `JIRA_EMAIL`               | Jiraに登録しているメールアドレス                   |
| `JIRA_API_TOKEN`           | Jira APIトークン                                   |
| `GEMINI_API_KEY`           | Google AI Studioで発行したGemini APIキー           |