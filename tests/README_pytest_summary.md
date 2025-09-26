# pytestによるテスト内容まとめ

このドキュメントは `tests/` ディレクトリに実装されているpytestテストの内容・目的を一覧でまとめたものです。

---

## test_output.py

- main.pyの出力生成（画像・JSON等）をテスト
- 外部Jira API呼び出しをモックし、ダッシュボード生成ロジックの正常動作を確認
- バーンダウン・ベロシティ・ステータス分布など各種データのダミー値で描画テスト

## test_processing.py

- 日付フォーマット変換（fmt_date）のテスト
- Gemini要約関数（maybe_gemini_summary）のAPIキー未設定時の挙動テスト
- 例外・異常系も含めて関数単体の動作確認

## test_queries.py

- queries配下の各Jira集計スクリプトの動作テスト
- JiraClientの各メソッド（resolve_board, resolve_active_sprint, search_paginated, api_get等）をモック
- バーンダウン・ベロシティ・ストーリーポイント等の集計スクリプトが正常終了するか確認
- JQLやAPIレスポンスのパターンごとに分岐テスト

---

## テストの特徴

- pytest + monkeypatchで外部依存（Jira API, Gemini API）を完全にモック
- 生成物（画像, Markdown, JSON）の有無や内容を検証
- 例外発生時や異常系もカバー
- テスト失敗時はどの関数・どのデータで問題が起きたか特定しやすい

---

## 実行方法

- `pytest tests/` で全テスト実行
- 個別ファイルは `pytest tests/test_output.py` などで実行可能

---

このドキュメントを見れば、現状のpytestテストの網羅範囲・目的・実行方法が一目で分かります。
