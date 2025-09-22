# Prototype (Local CLI)

このディレクトリは、将来的にSlack Botへ統合予定の機能をローカルで検証するためのプロトタイプ置き場です。Slack Bot本体と分離しているため、既存のBot環境に影響を与えません。

## 実行方法 (Windows PowerShell)

依存は標準ライブラリのみです。リポジトリルートで以下を実行:

```powershell
# そのまま実行
python .\prototype\local_cli\main.py

# 名前を指定
python .\prototype\local_cli\main.py --name Taro
```

必要に応じて仮想環境を使う場合:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# 依存が増えたら requirements.txt を更新・インストール
# python -m pip install -r requirements.txt
```

## 目的

- プロトタイプを安全に反復開発
- 後にSlack Botへ移設しやすい形（CLI/関数分離）

## 仕様（暫定）

- エントリ: `prototype/local_cli/main.py`
- 引数: `--name` を指定すると挨拶の対象を変更
- 出力: `Hello, <name>! (prototype)`
