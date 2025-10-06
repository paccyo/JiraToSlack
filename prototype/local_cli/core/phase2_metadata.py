"""
Phase 2: Jiraメタデータ取得
ボード選択、スプリント解決、プロジェクトキー取得を実行する。
"""

import logging
from typing import Optional, Tuple

try:  # Prefer absolute so tests that inject sys.modules['Loder'] still work
    from Loder.jira_client import JiraClient  # type: ignore
except Exception:  # pragma: no cover
    from ..Loder.jira_client import JiraClient  # type: ignore
from .types import AuthContext, JiraMetadata, BoardMetadata, SprintMetadata


logger = logging.getLogger(__name__)


class MetadataError(Exception):
    """メタデータ取得時のエラー"""
    pass


def fetch_jira_metadata(
    auth: AuthContext,
    enable_logging: bool = False
) -> JiraMetadata:
    """
    Jiraのメタデータ(ボード、スプリント、プロジェクトキー)を取得する。
    
    Args:
        auth: 認証コンテキスト
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        JiraMetadata: 取得したメタデータ
    
    Raises:
        MetadataError: メタデータ取得に失敗した場合
    """
    if enable_logging:
        logger.info("[Phase 2] Jiraメタデータ取得を開始します")
    
    try:
        # JiraClientを初期化
        client = JiraClient()
        
        # ボード解決
        board_code, board_data, board_error = client.resolve_board()
        if board_code != 200 or not board_data:
            raise MetadataError(f"ボード解決に失敗しました: {board_error}")
        
        board = _extract_board_metadata(board_data)
        if enable_logging:
            logger.info(f"[Phase 2] ボード解決成功: {board.name} (ID: {board.board_id}, Type: {board.board_type})")
        
        # アクティブスプリント解決
        sprint_code, sprint_data, sprint_error = client.resolve_active_sprint(board.board_id)
        if sprint_code != 200 or not sprint_data:
            raise MetadataError(f"アクティブスプリント解決に失敗しました: {sprint_error}")
        
        sprint = _extract_sprint_metadata(sprint_data)
        if enable_logging:
            logger.info(f"[Phase 2] スプリント解決成功: {sprint.name} (ID: {sprint.sprint_id}, State: {sprint.state})")
        
        # プロジェクトキー解決
        project_key = client.resolve_project_key()
        if not project_key:
            # ボードから推論を試みる
            project_key = _infer_project_key_from_board(board_data)
            if not project_key:
                raise MetadataError("プロジェクトキーの解決に失敗しました")
        
        if enable_logging:
            logger.info(f"[Phase 2] プロジェクトキー解決成功: {project_key}")
        
        # ストーリーポイントフィールドを解決
        story_points_field = client.resolve_story_points_field()
        if enable_logging:
            logger.info(f"[Phase 2] ストーリーポイントフィールド: {story_points_field}")
        
        metadata = JiraMetadata(
            board=board,
            sprint=sprint,
            project_key=project_key,
            story_points_field=story_points_field
        )
        
        if enable_logging:
            logger.info("[Phase 2] Jiraメタデータ取得が完了しました")
        
        return metadata
        
    except MetadataError:
        raise
    except Exception as e:
        raise MetadataError(f"予期しないエラーが発生しました: {str(e)}") from e


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
