"""
Phase 2: Jiraメタデータ取得
ボード選択、スプリント解決、プロジェクトキー取得を実行する。
"""

import logging
from typing import Optional, Tuple

from commands.jira_backlog_report.get_image.dashbord_orchestrator.types import JiraMetadata, BoardMetadata, SprintMetadata
from util.request_jira import RequestJiraRepository

logger = logging.getLogger(__name__)


class MetadataError(Exception):
    """メタデータ取得時のエラー"""
    pass


def get_jira_artifacts():
    """
    Jiraからボード、スプリント、プロジェクトキー、ストーリーポイントフィールドを取得する
    """
    try:
        
        get_jira_data = RequestJiraRepository()

        # --- . 最初のScrumボードを探す ---
        board_data = get_jira_data.get_scrum_board(1)
        
        print(f"  -> 発見: '{board_data.get('name')}' (ID: {board_data.get('id')})")

        # --- 3. アクティブなスプリントを探す ---
        print("🔎 アクティブなスプリントを検索中...")
        active_sprint_data = None
        active_sprint_data = get_jira_data.get_board_active_sprint(board_id=board_data.get("id"))
        
        # --- 4. プロジェクトキーを取得 ---
        project_key = board_data.get("location", {}).get("projectKey")
        if project_key:
            print(f"🔑 プロジェクトキーを取得しました: {project_key}")
        else:
            print("⚠️ ボードにプロジェクトキーが関連付けられていません。")


        # --- 5. ストーリーポイントフィールドIDを解決 ---
        print("🔎 ストーリーポイントフィールドIDを検索中...")
        story_points_field_id = None
        story_points_field_id = get_jira_data.get_story_point_field()
        
        if story_points_field_id:
            print(f"  -> 発見: {story_points_field_id}")
        else:
            story_points_field_id = "customfield_10016" # フォールバック
            print(f"  -> 自動検出できず、デフォルトIDを使用: {story_points_field_id}")

        # --- 6. 全ての情報をまとめて返す ---
        metadata = JiraMetadata(
            board=board_data,
            sprint=active_sprint_data,
            project_key=project_key,
            story_points_field=story_points_field_id
        )
        
        return metadata

    except KeyError as e:
        print(f"❌ エラー: 環境変数 {e} が設定されていません。プログラムを終了します。")
        return None
    except Exception as e:
        print(f"❌ 予期せぬエラーが発生しました: {e}")
        return None        