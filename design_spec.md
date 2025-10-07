# システム設計仕様書: Jira-Slack連携Bot

## 1. 概要

本システムは、JiraとSlackを連携させるためのBotアプリケーションである。主な目的は、Slackのインターフェースを通じてJiraのタスクを操作・確認し、定期的なタスクの通知や集計レポートを自動化することである。これにより、開発チームの生産性向上とコミュニケーションの円滑化を図る。

## 2. 全体アーキテクチャ

本システムは、以下の主要コンポーネントで構成されるサーバーレスアプリケーションである。

-   **Slack App**: ユーザーインターフェースを提供。スラッシュコマンド、インタラクティブなボタン（Action）、およびBotメッセージを介してユーザーと対話する。
-   **Cloud Functions / Cloud Run**: アプリケーションのバックエンドロジックを実行するメインコンポーネント。SlackからのリクエストやPub/Subからのトリガーを受け取り、処理を振り分ける。
-   **Google Cloud Pub/Sub**: 定期実行タスク（スケジューラ）をトリガーするために使用される。
-   **Google Cloud Firestore**: ユーザー情報（SlackとJiraのアカウント紐付けなど）を永続化するためのデータベース。
-   **Jira Cloud**: タスク管理システム。本システムはJira APIを介してタスク情報を取得・更新する。
-   **Gemini API**: 自然言語処理モデル。ユーザーが自然言語で入力したテキストをJQL（Jira Query Language）に変換するために使用される。

### 処理フロー

1.  **Slackからのリクエスト**: ユーザーがスラッシュコマンドを実行するか、ボタンをクリックすると、リクエストがCloud Functionsのエンドポイントに送信される。
2.  **Pub/Subからのトリガー**: Google Cloud Schedulerによって設定された時刻になると、Pub/Subトピックにメッセージが発行され、Cloud Functionsのエンドポイントをトリガーする。
3.  **リクエストの振り分け (`main_handler`)**: Cloud Functionsはリクエストの種類（SlackかPub/Subか）を判別し、適切なハンドラに処理を委譲する。
4.  **ビジネスロジックの実行**: 各コマンドやスケジューラは、必要に応じてJira APIやFirestoreと通信し、ビジネスロジックを実行する。
5.  **Slackへの応答**: 処理結果は、Slack Block Kitを用いて整形され、ユーザーに応答として返される。

---

## 3. 主要コンポーネント詳細

### 3.1. エントリーポイント (`main.py`)

-   Slack App (`slack_bolt`) とFirestoreクライアントの初期化を行う。
-   SlackからのHTTPリクエストとPub/Subからのメッセージを単一のエンドポイントで受け取り、`handle_pubsub_message` と `slack_handler` に処理を振り分ける。
-   各機能（コマンド、アクション、スケジューラ）のハンドラを登録・初期化する。

### 3.2. Slackコマンド (`/commands`)

#### `/jira_get_tasks`
-   **機能**: 自然言語でJiraタスクを検索する。
-   **処理詳細**:
    1.  ユーザーが入力した自然言語のテキスト（例: 「昨日完了した自分のタスク」）を受け取る。
    2.  Gemini APIにテキストを送信し、JQLクエリに変換する。
    3.  生成されたJQLを用いて `request_jira.py` 経由でJiraを検索する。
    4.  検索結果をSlack Block Kit形式に整形し、ユーザーに返信する。

#### `/add_user`, `/del_user`
-   **機能**: SlackユーザーとJiraアカウントの紐付けを管理する。
-   **処理詳細**: Firestoreの `slack_users` コレクションに対して、ユーザー情報の追加または削除を行う。

#### `/jira`
-   **機能**:汎用的なJiraコマンド。現在は受け取ったテキストをそのまま返すダミー実装となっている。

### 3.3. Slackアクション (`/actions`)

#### `change_status`
-   **機能**: Slackメッセージ上のボタンクリックに応じて、Jiraタスクのステータスを変更する。
-   **処理詳細**:
    1.  ユーザーがタスクメッセージ上のボタン（例: "In Progress", "完了"）をクリックするとトリガーされる。
    2.  `request_jira.py` の `issue_change_status` 関数を呼び出し、対象タスクのステータスを更新する。

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
    4.  完了タスク数が多い順にユーザーをソートし、ランキング形式のSlack Blockを作成して返す。

### 3.5. ユーティリティ (`/util`)

#### `request_jira.py`
-   Jira APIとの通信を抽象化するリポジトリクラス。
-   Jiraクライアントの初期化、JQLの実行、タスクのステータス変更、Slack Block Kit形式への整形など、Jira関連のコア機能を提供する。
-   プロジェクトで利用されているタスクサイズ（ストーリーポイント）のユニークな値を取得する関数も含まれる。

#### `get_jira_data.py`, `get_slack_email.py`
-   JiraやSlackからのデータ取得に特化した補助的な関数群。

---

## 4. データモデル (Firestore)

-   **コレクション**: `slack_users`
-   **ドキュメントID**: SlackのユーザーID（推測）
-   **フィールド**:
    -   `jira_email` (string): ユーザーのJiraアカウントに登録されているメールアドレス。

## 5. 設定 (環境変数)

本システムは、以下の環境変数を必要とする。

-   `SLACK_BOT_TOKEN`: Slack Botの認証トークン。
-   `SLACK_SIGNING_SECRET`: Slackリクエストの署名検証用シークレット。
-   `JIRA_DOMAIN`: Jira Cloudのドメイン名 (例: `your-company.atlassian.net`)。
-   `JIRA_EMAIL`: Jira APIへの認証に使用するメールアドレス。
-   `JIRA_API_TOKEN`: Jira APIトークン。
-   `JIRA_PROJECT_KEY`: メインで利用するJiraプロジェクトのキー。
-   `GEMINI_API_KEY`: Gemini APIの認証キー。
