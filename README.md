# JiraToSlack

## Jira 設定エクスポートと差分比較（Jira Cloud）

実環境の設定を取得し、開発環境と比較するための補助スクリプトを同梱しています。Windows PowerShell 5.1 前提。

### 1) 実行前準備（環境変数）

PowerShell で以下を設定してください（実行者が管理者権限を持つ環境で）:

```powershell
$env:JIRA_BASE_URL = "https://<your-domain>.atlassian.net"
$env:JIRA_EMAIL    = "admin@example.com"
$env:JIRA_API_TOKEN= "<API_TOKEN>"
```

APIトークンは Atlassian アカウントのセキュリティ設定から発行してください。

### 2) 接続テスト

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_jira_config.ps1 -TestConnection
```

"接続OK" が表示されれば準備完了です。

### 2.1) 課題件数の取得（JQL: プロジェクト単位）

環境変数に加えて、プロジェクトキーを設定します。

```powershell
$env:JIRA_PROJECT_KEY = "ABC"
python .\prototype\local_cli\jira_count_issues.py
```

出力例:

```
プロジェクト ABC のタスク総数: 123
```

### 3) 設定エクスポート

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_jira_config.ps1 -OutputDir .\jira-export-prod -IncludeBoards -IncludeFilters
```

開発環境でも同様に実行し、例えば `.\jira-export-dev` に保存します。

### 4) 差分比較

```powershell
python .\scripts\compare_jira_exports.py .\jira-export-prod .\jira-export-dev
```

出力には、ファイルの有無と、主要リスト（フィールド/優先度/ワークフロー/ボード/フィルターなど）の差分概要が表示されます。詳細差分は各JSONを直接比較してください。

### 注意事項

- 取得対象は設定情報であり、課題データは含みません。
- 連続呼び出しによる API 制限を避けるため、スクリプト内で短いスリープを入れています。
- Cloud のエンドポイント仕様変更により一部項目が欠落する場合があります。その際は対象JSONを個別に再取得してください。
