# SlackBotへのJiraダッシュボード組み込み手順（詳細版）

---

## 1. 確認事項

- SlackBotの開発環境（Python, Node.js等）を決定
- Botトークン・認証情報（Slack API, Jira API）を.envで管理
- main.pyが単体で正常にダッシュボード画像・レポートを生成できること
- Botがファイルアップロード権限を持つこと（Slack管理画面で設定）
- 生成物（画像/Markdown/JSON）の保存先・一時ファイル管理
- Jira APIが `/rest/api/3/search/jql` で正常応答すること（旧 `/search` は410 Gone）
- `pytest -q` がグリーンになること（回帰テスト）

---

### 【現状調査・確認結果】

1. SlackBotの開発環境

   - Python（slack_bolt/slack_sdk）での実装例・推奨あり。
   - main.pyやBot起動例もPythonベース。

2. Botトークン・認証情報の管理

   - .envファイルで `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `JIRA_API_TOKEN` などを管理。
   - main.pyやBotサンプルも `os.getenv()` で認証情報取得。

3. main.pyのダッシュボード生成

    - `python -X utf8 prototype/local_cli/main.py` で `sprint_overview.png`・`sprint_overview_report.md` などが正常生成されることを確認済み。
    - 画像・Markdown・JSON出力は正常。
    - 課題検索は `/rest/api/3/search/jql` + `nextPageToken` ページネーションで全件取得する実装に更新済み。

4. Botのファイルアップロード権限

   - 実装例で `files_upload` APIを使用。Botに `files:write` 権限が必要。
   - Slack管理画面で権限追加が必要（未設定の場合はアップロード不可）。

5. 生成物の保存先・一時ファイル管理
   - 生成物は `prototype/local_cli/` 配下に保存。
   - 一時ファイル管理や古いファイル削除は運用設計次第（拡張ポイントとして記載あり）。

---

【結論】

- すべての確認事項は現状の設計・コードで対応可能。
- Bot権限（files:write等）はSlack管理画面で事前設定が必要。
- 生成物の保存先・一時ファイル管理は運用設計に応じて追加可能。

---

## 2. 実装内容（全体像）

### 2-1. SlackBotの基本構築

- Pythonで `slack_bolt` または `slack_sdk` を使いBotアプリを新規作成
- .envに `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` などを記載
- Bot起動用の main_bot.py などを用意

### 2-2. Botコマンド/イベント設計

- 例: `/dashboard` コマンドや「ダッシュボード生成して」等のメッセージでトリガー
- コマンド受信時にJiraダッシュボード生成処理を呼び出す

### 2-3. main.pyの呼び出し方法

- コマンドハンドラ内で `subprocess.run(["python", "-X", "utf8", "prototype/local_cli/main.py"], check=True)` で実行
- 実行後、`sprint_overview.png` や `sprint_overview_report.md` を取得
- 必要に応じて.envやコマンド引数でパラメータを渡す

### 2-4. Slackへのファイル送信・メッセージ投稿

- Slack APIで画像やMarkdownをアップロード
- 例: `client.files_upload(channels=channel_id, file="prototype/local_cli/sprint_overview.png", title="Sprint Dashboard")`
- Markdown要約やリスク情報をテキストで投稿も可能

### 2-5. Botの応答・エラー処理

- 生成失敗時は `respond("ダッシュボード生成に失敗しました: ...")` で通知
- 進捗やログをBot経由で確認できるようにする
- 生成物の一時保存・クリーンアップも考慮

---

## 3. 実装例（Python: slack_bolt）

```python
from slack_bolt import App
import subprocess
import os

app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))

@app.command("/dashboard")
def handle_dashboard(ack, respond, command):
    ack()
    try:
        # main.pyを実行してダッシュボード生成
        subprocess.run(["python", "-X", "utf8", "prototype/local_cli/main.py"], check=True)
        # 画像をSlackにアップロード
        respond("ダッシュボード画像を生成しました。")
        app.client.files_upload(
            channels=command["channel_id"],
            file="prototype/local_cli/sprint_overview.png",
            title="Sprint Dashboard"
        )
        # Markdownレポートも投稿可能
        with open("prototype/local_cli/sprint_overview_report.md", "r", encoding="utf-8") as f:
            report = f.read()
        app.client.chat_postMessage(
            channel=command["channel_id"],
            text=report[:3000]  # Slackの文字数制限に注意
        )
    except Exception as e:
        respond(f"ダッシュボード生成に失敗しました: {e}")

# Bot起動
if __name__ == "__main__":
    app.start(port=int(os.getenv("PORT", 3000)))
```

---

## 4. 拡張・運用ポイント

- コマンド引数でプロジェクトやスプリントIDを指定できるようにする
- 生成画像の一時保存・古いファイルの自動削除
- 生成失敗時の詳細ログをSlackに通知
- 複数チャンネル対応やDM対応
- 生成物の保存先をS3等に変更も可能
- Botの権限（files:write, chat:write, commands等）を事前に確認
- Jira APIの仕様変更時は `prototype/local_cli/lib/jira_client.py` の共通ヘルパーを更新し、`pytest -q` と手動実行でリグレッションを確認

---

## 5. まとめ

- main.pyのダッシュボード生成機能はSlackBotのコマンド/イベントから簡単に呼び出し可能
- 画像・Markdown・JSONをSlackに投稿することで、チームの進捗・リスク・重要課題を即座に共有できる
- Botの権限・エラー処理・一時ファイル管理に注意し、運用しやすい設計にする

---

この手順で「Jiraダッシュボード生成」をSlackBotの機能として安全・柔軟に組み込めます。
