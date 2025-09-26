# クエリスクリプト取得内容まとめ

このドキュメントは `prototype/local_cli/queries/` 配下の各 Python スクリプトが「何を取得するコードか」を簡潔にまとめたものです。

---

## 1. jira_count_issues.py

- プロジェクトやスプリント内の「課題（Issue）」の件数を取得します。

## 2. jira_count_project_sprints.py

- プロジェクトに紐づく「スプリント」の一覧と件数を取得します。

## 3. jira_count_project_subtasks.py

- プロジェクト全体の「サブタスク（subtask）」の総数・未完了数・完了数を取得します。

## 4. jira_count_sprint_issues.py

- スプリント内の「課題（Issue）」の件数を取得します。

## 5. jira_list_closed_sprints.py

- 現在のボードで「最近クローズされたスプリント」の一覧を取得します。

## 6. jira_list_project_sprints.py

- プロジェクトに紐づく「全スプリント」の一覧を取得します。

## 7. jira_list_sprint_subtasks.py

- スプリント内の「サブタスク」の一覧・詳細情報を取得します。

## 8. jira_q_assignee_workload.py

- 担当者ごとの「未完了/完了タスク数」を集計し、ワークロード分布を取得します。

## 9. jira_q_avg_lead_time.py

- 課題の「リードタイム（作成→完了までの平均時間）」を取得します。

## 10. jira_q_blocked_count.py

- 「ブロックされている課題（issue links）」の件数を取得します。

## 11. jira_q_burndown.py

- スプリントの「バーンダウン（未完了タスク推移）」データを取得します。

## 12. jira_q_closed_sprint_velocity.py

- クローズ済みスプリントごとの「ベロシティ（完了ポイント）」を取得します。

## 13. jira_q_due_soon_count.py

- 期限が「近い（例:7日以内）」課題の件数を取得します。

## 14. jira_q_issuetype_distribution.py

- 課題タイプ（バグ/ストーリー等）の「分布件数」を取得します。

## 15. jira_q_overdue_count.py

- 期限を「超過している課題」の件数を取得します。

## 16. jira_q_priority_distribution.py

- 課題の「優先度分布（High/Medium等）」を取得します。

## 17. jira_q_recently_created_count.py

- 最近「新規作成された課題」の件数を取得します。

## 18. jira_q_reopened_count.py

- 「再オープンされた課題」の件数を取得します。

## 19. jira_q_status_counts.py

- スプリント/プロジェクト内の「ステータスごとの課題件数」を取得します。

## 20. jira_q_storypoints_sum.py

- スプリント/プロジェクト内の「ストーリーポイント合計・完了・未完了」を取得します。

## 21. jira_q_time_in_status.py

- 各課題の「各ステータス滞在時間（平均/合計）」を取得します。

## 22. jira_q_unassigned_count.py

- 「担当者未定」の課題件数を取得します。

## 23. jira_q_velocity_history.py

- 過去スプリントの「ベロシティ履歴（完了ポイント推移）」を取得します。

---

各スクリプトはJira APIを活用し、プロジェクト・スプリント・課題の状態や統計情報を取得するためのものです。
