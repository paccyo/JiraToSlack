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
  - [6. Pub/Sub の設定](#6-pubsub-の設定)
  - [7. Cloud Function のデプロイ](#7-cloud-function-のデプロイ)
  - [8. Cloud Scheduler の設定](#8-cloud-scheduler-の設定)
- [環境変数](#環境変数)
- [デプロイ](#デプロイ)

## アーキテクチャ概要

- **Cloud Functions**: Slackからのイベント受信と、Pub/Subからのメッセージ受信を処理するメインアプリケーション。
- **Slack Bolt**: Slackアプリのフレームワーク。
- **Firestore**: ユーザー情報を保存するデータベース。
- **Secret Manager**: APIキーやトークンなどの機密情報を安全に保管。
- **Cloud Scheduler & Pub/Sub**: スケジューラ機能を実装。Cloud Schedulerが定期的にPub/Subトピックにメッセージを送信し、それをトリガーにCloud Functionが実行されます。
- **Cloud Build**: デプロイを自動化。

## 前提条件

- Google Cloud Platform (GCP) アカウント
- `gcloud` CLI がインストールされていること
- Python 3.10 以降

## GCPセットアップ手順

### 1. gcloud CLI のインストールと設定

1.  **インストール**:
    公式ドキュメントに従って、お使いのOSに`gcloud` CLIをインストールしてください。
    [gcloud CLI インストールガイド](https://cloud.google.com/sdk/docs/install)

2.  **初期化**:
    ターミナルで以下のコマンドを実行し、GCPアカウントへのログインとプロジェクトの選択を行います。
    ```bash
    gcloud init
    ```

3.  **プロジェクト設定**:
    以降のコマンドで対象となるGCPプロジェクトIDを設定します。
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

プロジェクトで必要となるAPIキーやトークンをSecret Managerに保存します。

1.  **シークレットの作成と値の設定**:
    [環境変数](#環境変数)セクションにリストされている各変数に対して、以下のコマンドを実行します。

    ```bash
    # シークレットを作成
    gcloud secrets create SECRET_NAME --replication-policy="automatic"

    # シークレットに値を設定 (値はファイルからも読み込めます)
    printf "YOUR_SECRET_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=-
    ```
    `SECRET_NAME`と`YOUR_SECRET_VALUE`を実際の値に置き換えてください。

### 5. Firestore の設定

1.  GCP ConsoleでFirestoreに移動します。
2.  「ネイティブモード」を選択してデータベースを作成します。
3.  ロケーションを選択します（例: `asia-northeast1`）。
4.  `slack_users` という名前のコレクションが自動的に作成されますが、手動で作成する必要はありません。

### 6. Pub/Sub の設定

スケジューラ用のPub/Subトピックを作成します。

```bash
gcloud pubsub topics create scheduler-topic
```

### 7. Cloud Function のデプロイ

アプリケーションをCloud Functionとしてデプロイします。詳細は[デプロイ](#デプロイ)セクションを参照してください。

### 8. Cloud Scheduler の設定

毎日午前9時に定期実行するスケジューラを設定する例です。

```bash
gcloud scheduler jobs create pubsub daily-task-scheduler \
  --schedule="0 9 * * *" \
  --topic="scheduler-topic" \
  --message-body='{"flag":"execute_special_task"}' \
  --time-zone="Asia/Tokyo"
```

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

## デプロイ

以下のコマンドを使用して、Cloud Functionをデプロイします。`YOUR_PROJECT_ID`とリージョンは適宜変更してください。

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

**注意**:
- `--set-secrets` フラグでは、`環境変数名=Secret Managerの名前:バージョン` の形式で指定します。
- このアプリケーションはPub/Subからも呼び出されるため、Cloud Function作成後にサービスアカウントにPub/Sub関連の権限を付与する必要がある場合があります。
