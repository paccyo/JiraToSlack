# システム設計仕様書: Jira-Slack連携Bot

## 1. 概要

本システムは、JiraとSlackを連携させるためのBotアプリケーションである。主な目的は、Slackのインターフェースを通じてJiraのタスクを操作・確認し、定期的なタスクの通知や集計レポートを自動化することである。これにより、開発チームの生産性向上とコミュニケーションの円滑化を図る。

## 2. 全体アーキテクチャ

本システムは、Google Cloud Platform (GCP) 上で動作するサーバーレスアプリケーションであり、以下の主要コンポーネントで構成される。

-   **Slack App**: ユーザーインターフェースを提供。スラッシュコマンド、インタラクティブなボタン（Action）、およびBotメッセージを介してユーザーと対話する。
-   **Cloud Functions (gen2)**: アプリケーションのバックエンドロジックを実行するメインコンポーネント。SlackからのリクエストやPub/Subからのトリガーを受け取り、処理を振り分ける。内部的にはCloud Run上で動作する。
-   **Cloud Scheduler / Pub/Sub / Eventarc**: 定期実行タスク（スケジューラ）のトリガーと実行連携を担う。
-   **Firestore**: ユーザー情報（SlackとJiraのアカウント紐付け）を永続化するためのNoSQLデータベース。
-   **Secret Manager**: APIキーやトークンなどの機密情報を安全に保管する。
-   **Jira Cloud API**: タスク管理システム。本システムはJira APIを介してタスク情報を取得・更新する。
-   **Gemini API**: 自然言語処理モデル。ユーザーが自然言語で入力したテキストをJQL（Jira Query Language）に変換するために使用される。

### 処理フロー

1.  **Slackからのリクエスト**: ユーザーがスラッシュコマンドを実行するか、ボタンをクリックすると、リクエストがCloud FunctionsのHTTPエンドポイントに送信される。
2.  **Pub/Subからのトリガー**: Cloud Schedulerによって設定された時刻になると、Pub/Subトピックにメッセージが発行され、Eventarc経由でCloud Functionsのエンドポイントをトリガーする。
3.  **リクエストの振り分け (`main.py:main_handler`)**: Cloud Functionsはリクエストの種類（SlackかPub/Subか）を判別し、適切なハンドラに処理を委譲する。
4.  **ビジネスロジックの実行**: 各コマンドやスケジューラは、必要に応じてユーティリティモジュール (`/util`) を介してJira APIやFirestoreと通信し、ビジネスロジックを実行する。
5.  **Slackへの応答**: 処理結果は、Slack Block Kitを用いて整形され、ユーザーに応答として返される。

---

## 3. 主要コンポーネント詳細

### 3.1. エントリーポイント (`main.py`)

-   Slack App (`slack_bolt`) とFirestoreクライアントの初期化を行う。
-   SlackからのHTTPリクエストとPub/Subからのメッセージを単一のエンドポイント `main_handler` で受け取り、リクエスト内容に応じて `handle_pubsub_message` と `slack_handler` に処理を振り分ける。
-   `commands`, `actions`, `events` の各初期化関数を呼び出し、Slackのイベントハンドラを登録する。

### 3.2. Slackコマンド (`/commands`)

#### `/jira_get_tasks`
-   **機能**: 自然言語でJiraタスクを検索する。
-   **処理詳細**:
    1.  ユーザーが入力した自然言語のテキスト（例: 「昨日完了した自分のタスク」）を受け取る。
    2.  `prompts.py` に定義されたシステムプロンプトと `JQLQuerySchema` (Pydanticモデル) を使用して、Gemini APIにリクエストを送信する。
    3.  Gemini APIから返却された構造化JSONを `request_jira.py` の `build_jql_from_json` でJQLクエリに変換する。
    4.  生成されたJQLを用いてJiraを検索し、結果をBlock Kit形式に整形してユーザーに返信する。

#### `/jira_backlog_report`
-   **機能**: 現在のスプリント状況やバックログを分析し、画像形式のレポートを生成・投稿する。
-   **処理詳細**:
    1.  `DashboardOrchestrator` を呼び出す。
    2.  OrchestratorはJira APIを通じてアクティブスプリント、課題、ストーリーポイントなどの情報を収集する。
    3.  収集したデータを分析・集計し、Pillowライブラリを用いて `sprint_overview.png` という画像に描画する。
    4.  生成された画像をSlackにアップロードする。

#### `/add_user`, `/del_user`
-   **機能**: SlackユーザーとJiraアカウントの紐付けを管理する。
-   **処理詳細**: Firestoreの `slack_users` コレクションに対して、ユーザー情報の追加または削除を行う。この紐付けは、特にスケジュールタスクが個々のユーザーにDMを送信する際に不可欠である。

### 3.3. Slackアクション (`/actions`)

#### `change_status`
-   **機能**: Slackメッセージ上のボタンクリックに応じて、Jiraタスクのステータスを変更する。
-   **処理詳細**:
    1.  ユーザーがタスクメッセージ上のボタン（例: "In Progress", "完了"）をクリックするとトリガーされる。
    2.  アクションID (`move_in_progress`, `move_compleated`など) に応じて、変更先のステータスが決定される。
    3.  `request_jira.py` の `issue_change_status` 関数を呼び出し、対象タスクのステータスを更新する。
    4.  更新後のタスク情報を再度取得し、Slackメッセージを更新する。

### 3.4. スケジュール実行タスク (`/scheduler`)

#### `daily_reccomend` (毎日実行)
-   **機能**: 各ユーザーに、その日の推奨タスクをSlackのDMで通知する。
-   **処理詳細**:
    1.  Firestoreから全ユーザーのJiraメールアドレスを取得する。
    2.  各ユーザーの "To Do" または "In Progress" のタスクをJiraから取得する。
    3.  以下のカテゴリに基づいてタスクを整理し、DMで送信する。
        -   今日が期限のタスク
        -   優先度の高いタスク（上位3件）
        -   期日が近いタスク（上位3件）

#### `weekly_aggregate_award` (毎週実行)
-   **機能**: 全ユーザーの週次パフォーマンスを集計し、ランキング形式で報告する。
-   **処理詳細**:
    1.  Firestoreから全ユーザーを取得する。
    2.  各ユーザーについて、先週一週間に完了したタスクをJiraから取得する。
    3.  以下の項目を集計する。
        -   合計完了タスク数
        -   合計ストーリーポイント
        -   期日内に完了したタスクの数
        -   ストーリーポイントごとのタスク内訳
    4.  完了タスク数が多い順にユーザーをソートし、ランキング形式のSlack Blockを作成して指定のチャンネルに投稿する。

### 3.5. ユーティリティ (`/util`)

-   **`request_jira.py`**: Jira APIとの通信を抽象化するリポジトリクラス。Jiraクライアントの初期化、JQLの実行、タスクのステータス変更、Slack Block Kit形式への整形など、Jira関連のコア機能を提供する。
-   **`get_jira_data.py`**: Firestoreにアクセスし、SlackのメールアドレスからJiraのメールアドレスを取得するなど、ユーザーデータの変換・取得を行う。
-   **`get_slack_data.py`**: Slack APIを呼び出すためのユーティリティ。ユーザーIDからメールアドレスを取得したり、チャンネル名からチャンネルIDを取得したりする機能を提供する。

---

## 4. データモデル (Firestore)

-   **コレクション**: `slack_users`
-   **ドキュメントID**: SlackのユーザーID
-   **フィールド**:
    -   `user_name` (string): Slackのユーザー名
    -   `slack_email` (string): Slackのメールアドレス
    -   `jira_email` (string): ユーザーのJiraアカウントに登録されているメールアドレス
    -   `created_at` (timestamp): ドキュメント作成日時

## 5. 設定 (環境変数)

本システムは、以下の環境変数をSecret Managerに設定する必要がある。

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