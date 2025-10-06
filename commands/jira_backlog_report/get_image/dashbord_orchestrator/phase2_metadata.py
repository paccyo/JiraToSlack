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
    

def _extract_board_metadata(board_data: dict) -> BoardMetadata:
    """
    Jira APIのボードレスポンスからBoardMetadataを抽出する。
    
    Args:
        board_data: Jira APIのボードレスポンス
    
    Returns:
        BoardMetadata: 抽出したボードメタデータ
    """
    board_id = board_data.get("id")
    if board_id is None:
        raise MetadataError("ボードIDが取得できませんでした")
    
    try:
        board_id = int(board_id)
    except (TypeError, ValueError) as e:
        raise MetadataError(f"ボードIDが不正です: {board_id}") from e
    
    # ボードのロケーション情報を取得
    location = board_data.get("location", {})
    project_key = location.get("projectKey")
    
    return BoardMetadata(
        board=board_data,
        board_id=board_id,
        project_key=project_key,
        boards_count=1  # 単一ボード取得の場合
    )


def _extract_sprint_metadata(sprint_data: dict) -> SprintMetadata:
    """
    Jira APIのスプリントレスポンスからSprintMetadataを抽出する。
    
    Args:
        sprint_data: Jira APIのスプリントレスポンス
    
    Returns:
        SprintMetadata: 抽出したスプリントメタデータ
    """
    sprint_id = sprint_data.get("id")
    if sprint_id is None:
        raise MetadataError("スプリントIDが取得できませんでした")
    
    try:
        sprint_id = int(sprint_id)
    except (TypeError, ValueError) as e:
        raise MetadataError(f"スプリントIDが不正です: {sprint_id}") from e
    
    sprint_name = sprint_data.get("name", "")
    
    # 日付情報を取得（オプショナル）
    start_date = sprint_data.get("startDate")
    end_date = sprint_data.get("endDate")
    
    return SprintMetadata(
        sprint=sprint_data,
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        sprint_start=start_date,
        sprint_end=end_date,
        active_sprints_count=1  # 単一スプリント取得の場合
    )


def _infer_project_key_from_board(board_data: dict) -> Optional[str]:
    """
    ボードデータからプロジェクトキーを推論する。
    
    Args:
        board_data: Jira APIのボードレスポンス
    
    Returns:
        Optional[str]: プロジェクトキー、取得できない場合はNone
    """
    location = board_data.get("location", {})
    project_key = location.get("projectKey")
    
    if project_key:
        return str(project_key)
    
    # projectKeyが直接取得できない場合は、nameやdisplayNameから推論を試みる
    project_name = location.get("projectName") or location.get("name") or location.get("displayName")
    if project_name:
        # プロジェクトキーは通常大文字の略称
        # ただし、nameから確実に推論できるわけではないのでNoneを返す
        logger.warning(f"プロジェクトキーが取得できませんでした。プロジェクト名: {project_name}")
    
    return None



