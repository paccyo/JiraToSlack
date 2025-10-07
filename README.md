# JiraToSlack: Jira & Slack連携Bot

JiraとSlackを連携させるためのBotアプリケーションです。Slackのインターフェースを通じてJiraのタスクを操作・確認したり、定期的なタスク通知やレポートを自動化したりすることで、チームの生産性向上を支援します。

このアプリケーションはGoogle Cloud Platform (GCP) 上で動作するサーバーレスアーキテクチャを採用しています。

## 目次

- [アーキテクチャ](#アーキテクチャ)
- [ディレクトリ構造](#ディレクトリ構造)
- [主な機能（詳細）](#主な機能詳細)
- [セットアップとデプロイ](#セットアップとデプロイ)
- [環境変数](#環境変数)

## アーキテクチャ

本システムは、Cloud Functions (第2世代) を中心としたサーバーレスアーキテクチャで構築されています。

- **リクエスト処理**:
  1.  **Slackからのリクエスト**: ユーザーのスラッシュコマンドやボタン操作は、Cloud FunctionのHTTPエンドポイントに直接送信されます。
  2.  **スケジュール実行**: Cloud Schedulerが指定時刻にPub/Subトピックへメッセージを送信し、それをEventarcトリガーが検知してCloud Functionを呼び出します。
- **主要GCPサービス**:
  - **Cloud Functions (gen2)**: バックエンドロジックを実行します。内部的にはCloud Runで動作します。
  - **Slack Bolt Framework**: Slackとのインタラクションを処理します。
  - **Firestore**: ユーザー情報（Slack IDとJira Emailの紐付け）を永続化します。
  - **Secret Manager**: APIトークンなどの機密情報を安全に保管します。
  - **Cloud Scheduler / Pub/Sub / Eventarc**: 定期実行タスクの仕組みを実現します。
  - **Gemini API**: `/jira_get_tasks`コマンドで入力された自然言語をJQL (Jira Query Language) に変換するために利用します。

## ディレクトリ構造

```
.
├── actions/         # Slackのインタラクティブコンポーネント（ボタン等）のアクションを定義
├── commands/        # Slackのスラッシュコマンドを定義
├── events/          # Slackのイベント（未使用）
├── scheduler/       # 定期実行タスク（日次、週次）を定義
├── util/            # Jira/Slack APIのラッパーやデータ取得などの共通処理
├── main.py          # アプリケーションのエントリーポイント
├── requirements.txt # Pythonの依存パッケージリスト
├── setup.md         # GCPセットアップ手順書
└── design_spec.md   # システム設計書
```

## 主な機能（詳細）

### インタラクティブ機能 (Slackコマンド / アクション)

- **`/jira_get_tasks [自然言語テキスト]`**
  - **概要**: 自然言語でJiraタスクを検索します。
  - **処理**: Gemini APIを利用してユーザーの入力（例: 「昨日完了した自分のタスク」）をJQLに変換し、Jira APIで検索して結果を返します。

- **`/jira_backlog_report`**
  - **概要**: Jiraのバックログに関するレポートを画像として生成し、Slackに投稿します。
  - **処理**: `dashbord_orchestrator`がJiraからスプリント情報や課題データを取得・集計し、Pillowライブラリを使って画像を描画します。

- **`/add_user`, `/del_user`**
  - **概要**: SlackユーザーとJiraアカウントの紐付けを管理します。
  - **処理**: Firestoreの`slack_users`コレクションに対して、ユーザー情報の登録・削除を行います。この紐付け情報は、スケジュール機能で個々のユーザーに通知を送る際に使用されます。

- **ボタンによるステータス変更 (`change_status`)**
  - **概要**: Botが投稿したタスクメッセージ上のボタン（例: "ToDo", "完了"）をクリックすることで、Jira課題のステータスを直接変更できます。

### スケジュール機能

Cloud Schedulerによって定期的に実行されるタスクです。

- **`daily_reccomend` (毎日実行)**
  - **概要**: 登録されている全ユーザーに、その日の推奨タスクをDMで通知します。
  - **処理**: 各ユーザーの仕掛中タスクの中から、以下のカテゴリに分類して通知します。
    1.  **今日が期限のタスク**
    2.  **優先度の高いタスク** (上位3件)
    3.  **期日が近いタスク** (上位3件)

- **`weekly_aggregate_award` (毎週実行)**
  - **概要**: チームの週次パフォーマンスを集計し、ランキング形式で指定されたチャンネルに報告します。
  - **処理**: 先週1週間に完了したタスクをユーザーごとに集計し、以下の項目をランキング形式で投稿します。
    - 完了タスク総数
    - 合計ストーリーポイント
    - 期日内完了率
    - タスクサイズ毎の内訳

## セットアップとデプロイ

詳細な手順は `setup.md` を参照してください。

1. **GCPプロジェクトの準備とAPIの有効化**
   - `gcloud` CLIをセットアップし、課金が有効なプロジェクトを用意します。
   - `setup.md` に記載のコマンドを実行し、必要なAPIを有効化します。

2. **Secret Managerの設定**
   - [環境変数](#環境変数)セクションに記載されている全ての値を、Secret Managerにシークレットとして登録します。

3. **Firestoreのセットアップ**
   - GCPコンソールからFirestoreデータベースを「ネイティブモード」で作成します。

4. **アプリケーションのデプロイ**
   - `setup.md` に記載の `gcloud functions deploy` コマンドを実行します。
   - デプロイ後に出力される**トリガーURL**を、Slackアプリの `Request URL` に設定します。

5. **スケジューラ機能のセットアップ**
   - `setup.md` の手順に従い、Pub/Subトピック、Eventarcトリガー、Cloud Schedulerジョブを作成します。

## 環境変数

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
