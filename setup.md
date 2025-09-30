# Google Cloud セットアップ手順

このドキュメントは、JiraToSlackプロジェクトをGoogle Cloud Platform (GCP) 上にデプロイするための手順を記載します。

## 1. 前提条件

- Google Cloud SDK (`gcloud` CLI) がローカルマシンにインストールされ、認証済みであること。
- 課金が有効になっているGoogle Cloudプロジェクトが作成済みであること。
- プロジェクトに対する `Owner` または `Editor` のIAMロールを持っていること。
- JiraおよびSlackのAPIトークン（または認証情報）が用意できていること。

## 2. APIの有効化

はじめに、プロジェクトで必要なAPIを有効化します。

```bash
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com
```

## 3. Secret Managerにシークレットを保存

APIトークンなどの機密情報を安全に管理するため、Secret Managerを使用します。
以下の4つのシークレットを作成してください。

- `JIRA_API_TOKEN`: JiraのAPIトークン
- `JIRA_USER_EMAIL`: Jiraに登録しているメールアドレス
- `JIRA_SERVER_URL`: JiraサーバーのURL (例: `https://your-domain.atlassian.net`)
- `SLACK_BOT_TOKEN`: SlackアプリのBot User OAuth Token

**コマンド例:**

```bash
# シークレットの作成
gcloud secrets create JIRA_API_TOKEN
gcloud secrets create JIRA_USER_EMAIL
gcloud secrets create JIRA_SERVER_URL
gcloud secrets create SLACK_BOT_TOKEN

# シークレットに値を設定 (YOUR_... の部分を実際の値に置き換えてください)
echo -n "[YOUR_JIRA_API_TOKEN]" | gcloud secrets versions add JIRA_API_TOKEN --data-file=-
echo -n "[YOUR_JIRA_USER_EMAIL]" | gcloud secrets versions add JIRA_USER_EMAIL --data-file=-
echo -n "[YOUR_JIRA_SERVER_URL]" | gcloud secrets versions add JIRA_SERVER_URL --data-file=-
echo -n "[YOUR_SLACK_BOT_TOKEN]" | gcloud secrets versions add SLACK_BOT_TOKEN --data-file=-
```

## 4. Cloud Functionのデプロイ


```bash
gcloud functions deploy slack-jira-bot \
    --gen2 \
    --runtime=python311 \
    --region=asia-northeast1 \
    --source=. \
    --entry-point=main_handler \
    --trigger-http \
    --allow-unauthenticated \
    --set-secrets=SLACK_BOT_TOKEN=slack-bot-token:latest,SLACK_SIGNING_SECRET=slack-signing-secret:latest,GEMINI_API_KEY=gemini-api-key:latest,JIRA_DOMAIN=jira-domain:latest,JIRA_EMAIL=jira-email:latest,JIRA_API_TOKEN=jira-api-token:latest
```

**注意:**
- `--allow-unauthenticated` は、Cloud Schedulerからの呼び出しを許可するために設定していますが、よりセキュアにする場合は、サービスアカウント認証を構成してください。
- `runtime` は `requirements.txt` に適合するバージョンを選択してください。

デプロイが完了すると、関数のURL（`https://...`）が表示されます。このURLは次の手順で使用します。

## 5. Cloud Schedulerの設定

関数を定期的に実行するため、Cloud Schedulerジョブを作成します。

- `[JOB_NAME]`: `tick-jira-to-slack` など任意のジョブ名
- `[SCHEDULE]`: `0 9 * * 1-5` (月〜金の午前9時) など、実行したいスケジュール（cron形式）
- `[FUNCTION_URL]`: 前の手順で取得した関数のURL
- `[TIMEZONE]`: `Asia/Tokyo` など

```bash
gcloud scheduler jobs create http [JOB_NAME] \
    --schedule="[SCHEDULE]" \
    --uri="[FUNCTION_URL]" \
    --http-method=POST \
    --time-zone="[TIMEZONE]" \
    --description="Post Jira tasks to Slack"
```

## 6. サービスアカウントへの権限付与

Cloud FunctionがSecret Managerからシークレットを読み取れるように、権限を付与する必要があります。

1.  **サービスアカウントの特定**:
    Cloud Functionのデプロイに使用されたサービスアカウント（通常は `[PROJECT_ID]@appspot.gserviceaccount.com` またはデプロイ時に指定したアカウント）を特定します。

2.  **権限付与**:
    以下のコマンドで、特定したサービスアカウントに `Secret Manager のシークレット アクセサー` ロールを付与します。

    ```bash
    gcloud projects add-iam-policy-binding [PROJECT_ID] \
        --member="serviceAccount:[SERVICE_ACCOUNT_EMAIL]" \
        --role="roles/secretmanager.secretAccessor"
    ```

    - `[PROJECT_ID]`: あなたのGCPプロジェクトID
    - `[SERVICE_ACCOUNT_EMAIL]`: 手順1で特定したサービスアカウントのメールアドレス

以上でセットアップは完了です。指定したスケジュールでCloud Functionが実行され、JiraのタスクがSlackに通知されます。
