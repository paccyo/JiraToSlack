#!/usr/bin/env python
# coding: utf-8
"""
jira_list_assignees.py
Jiraプロジェクト/スプリント内の担当者名一覧を取得して表示するスクリプト
"""
import os
import sys
import argparse
from typing import Set, List, Dict, Any
from pathlib import Path
from requests.auth import HTTPBasicAuth

try:
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "prototype").exists():
            sys.path.append(str(parent))
            break
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded  # type: ignore
ensure_env_loaded()
# --- libディレクトリの絶対パスをsys.pathに追加（Pylanceのimportエラー対策） ---
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.abspath(os.path.join(current_dir, '..', 'lib'))
if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
from ..Loder.jira_client import JiraClient  # prototype/local_cli/lib/jira_client.py を明示的に参照

def main() -> int:
    parser = argparse.ArgumentParser(description="Jira課題から担当者名一覧を取得")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("ASSIGNEE_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    args = parser.parse_args()

    jc = JiraClient()

    # スコープ判定
    if args.scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        base_jql = f"Sprint={sprint.get('id')}"
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        base_jql = f"project={key}"

    # 課題取得
    code, issues, err = jc.search_paginated(base_jql, fields=["assignee"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    names: Set[str] = set()
    for iss in issues:
        f = iss.get("fields") or {}
        assignee = f.get("assignee") or None
        name = (assignee or {}).get("displayName") if assignee else None
        if name:
            names.add(name)

    # 結果表示
    print("担当者名一覧:")
    for n in sorted(names):
        print(f"- {n}")
    print(f"合計: {len(names)} 名")
    return 0

if __name__ == "__main__":
    sys.exit(main())
