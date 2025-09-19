# JiraToSlack

## development
### gcloud CLIのインストール:
[こちらのガイド](https://cloud.google.com/sdk/docs/install?hl=ja) に従って、gcloud コマンドラインツールをPCにインストールします。

インストール後、ターミナルで以下のコマンドを実行して初期設定を行います。
gcloud auth login
gcloud init

### deploy
以下のコマンドをカレントディレクトリ上で実行
gcloud functions deploy slack-jira-bot --gen2 --runtime=python311 --region=asia-northeast1 --source=. --entry-point=handle_slack_events --trigger-http --allow-unauthenticated --set-secrets=SLACK_BOT_TOKEN=slack-bot-token:latest,SLACK_SIGNING_SECRET=slack-signing-secret:latest
