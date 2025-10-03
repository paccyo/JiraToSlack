"""Type definitions for dashboard generation."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from requests.auth import HTTPBasicAuth


@dataclass
class EnvironmentConfig:
    """環境設定を保持するデータクラス"""
    jira_domain: str
    jira_email: str
    jira_api_token: str
    output_dir: str
    target_done_rate: float = 0.8
    axis_mode: str = "percent"
    
    # オプション設定
    jira_board_id: Optional[str] = None
    jira_project_key: Optional[str] = None
    burndown_unit: str = "days"
    n_sprints: str = "6"
    status_counts_mode: str = "approx"
    tis_unit: str = "days"
    due_soon_days: str = "7"
    high_priorities: str = "Highest,High"
    evidence_top_n: int = 5
    
    # AI設定
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_disable: bool = False
    
    # ログ設定
    dashboard_log: bool = True
    
    @classmethod
    def from_env(cls) -> Optional['EnvironmentConfig']:
        """環境変数から設定を読み込む
        
        Returns:
            EnvironmentConfig または None（必須変数が不足している場合）
        """
        import os
        
        # 必須環境変数のチェック
        jira_domain = os.getenv("JIRA_DOMAIN", "").rstrip("/")
        jira_email = os.getenv("JIRA_EMAIL")
        jira_api_token = os.getenv("JIRA_API_TOKEN")
        
        if not all([jira_domain, jira_email, jira_api_token]):
            return None
        
        # 出力ディレクトリの決定
        from pathlib import Path
        output_dir = os.getenv("OUTPUT_DIR")
        if not output_dir:
            # デフォルトは main.py のあるディレクトリ
            output_dir = str(Path(__file__).resolve().parent.parent)
        
        # オプション環境変数の取得
        try:
            target_done_rate = float(os.getenv("TARGET_DONE_RATE", "0.8"))
        except (ValueError, TypeError):
            target_done_rate = 0.8
        
        axis_mode = os.getenv("AXIS_MODE", "percent").lower()
        
        # AI設定
        gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        gemini_disable = os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes")
        
        # ログ設定
        dashboard_log = os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes")
        
        try:
            evidence_top_n = int(os.getenv("EVIDENCE_TOP_N", "5"))
        except (ValueError, TypeError):
            evidence_top_n = 5
        
        return cls(
            jira_domain=jira_domain,
            jira_email=jira_email,
            jira_api_token=jira_api_token,
            output_dir=output_dir,
            target_done_rate=target_done_rate,
            axis_mode=axis_mode,
            jira_board_id=os.getenv("JIRA_BOARD_ID"),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY"),
            burndown_unit=os.getenv("BURNDOWN_UNIT", "days"),
            n_sprints=os.getenv("N_SPRINTS", "6"),
            status_counts_mode=os.getenv("STATUS_COUNTS_MODE", "approx"),
            tis_unit=os.getenv("TIS_UNIT", "days"),
            due_soon_days=os.getenv("DUE_SOON_DAYS", "7"),
            high_priorities=os.getenv("HIGH_PRIORITIES", "Highest,High"),
            evidence_top_n=evidence_top_n,
            gemini_api_key=gemini_api_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            gemini_disable=gemini_disable,
            dashboard_log=dashboard_log,
        )


@dataclass
class AuthContext:
    """認証情報を保持"""
    domain: str
    auth: HTTPBasicAuth
    
    def __repr__(self) -> str:
        """セキュアな文字列表現（トークンをマスク）"""
        return f"AuthContext(domain={self.domain}, auth=***)"


@dataclass
class BoardMetadata:
    """ボード情報"""
    board: Dict[str, Any]
    board_id: int
    project_key: Optional[str]
    boards_count: int
    
    @property
    def name(self) -> str:
        """ボード名を取得"""
        return self.board.get("name", "Unknown")
    
    @property
    def board_type(self) -> str:
        """ボードタイプを取得"""
        return self.board.get("type", "unknown")


@dataclass
class SprintMetadata:
    """スプリント情報"""
    sprint: Optional[Dict[str, Any]]
    sprint_id: Optional[int]
    sprint_name: Optional[str]
    sprint_start: Optional[str]
    sprint_end: Optional[str]
    active_sprints_count: int
    
    @property
    def name(self) -> Optional[str]:
        """スプリント名を取得"""
        return self.sprint_name
    
    @property
    def state(self) -> str:
        """スプリント状態を取得"""
        if self.sprint:
            return self.sprint.get("state", "unknown")
        return "unknown"


@dataclass
class JiraMetadata:
    """Jira メタデータの集約"""
    board: BoardMetadata
    sprint: SprintMetadata
    project_key: str
    story_points_field: str = "customfield_10016"
    
    def to_dict(self) -> Dict[str, Any]:
        """ログ・デバッグ用の辞書変換"""
        return {
            "board": {
                "id": self.board.board_id,
                "project_key": self.board.project_key,
                "boards_count": self.board.boards_count,
            },
            "sprint": {
                "id": self.sprint.sprint_id,
                "name": self.sprint.sprint_name,
                "start": self.sprint.sprint_start,
                "end": self.sprint.sprint_end,
                "active_count": self.sprint.active_sprints_count,
            },
            "project_key": self.project_key,
            "story_points_field": self.story_points_field,
        }


@dataclass
class TaskTotals:
    """タスク集計"""
    subtasks: int
    done: int
    not_done: int
    
    @property
    def completion_rate(self) -> float:
        """完了率を計算"""
        return self.done / max(1, self.subtasks)
    
    def to_dict(self) -> Dict[str, int]:
        """辞書形式に変換"""
        return {
            "subtasks": self.subtasks,
            "done": self.done,
            "notDone": self.not_done,
        }


@dataclass
class SubtaskData:
    """サブタスク情報"""
    key: str
    summary: str
    done: bool
    assignee: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    story_points: float = 1.0
    created: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 後方互換性のためのプロパティ
    @property
    def is_done(self) -> bool:
        """完了状態を返す（後方互換性）"""
        return self.done
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "key": self.key,
            "summary": self.summary,
            "done": self.done,
            "assignee": self.assignee,
            "status": self.status,
            "priority": self.priority,
            "storyPoints": self.story_points,
            "created": self.created,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
        }


@dataclass
class ParentTask:
    """親タスク情報"""
    key: str
    summary: str
    assignee: Optional[str]
    subtasks: List[SubtaskData] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "key": self.key,
            "summary": self.summary,
            "assignee": self.assignee,
            "subtasks": [st.to_dict() for st in self.subtasks],
        }


@dataclass
class CoreData:
    """コアデータの集約"""
    parents: List[ParentTask]
    totals: TaskTotals
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'CoreData':
        """JSONから構築"""
        parents_data = data.get("parents", [])
        parents = []
        
        for p in parents_data:
            subtasks_data = p.get("subtasks", [])
            subtasks = [
                SubtaskData(
                    key=st.get("key", ""),
                    summary=st.get("summary", ""),
                    done=bool(st.get("done")),
                    assignee=st.get("assignee"),
                    status=st.get("status"),
                    priority=st.get("priority"),
                )
                for st in subtasks_data
            ]
            
            parents.append(ParentTask(
                key=p.get("key", ""),
                summary=p.get("summary", ""),
                assignee=p.get("assignee"),
                subtasks=subtasks,
            ))
        
        totals_data = data.get("totals", {})
        totals = TaskTotals(
            subtasks=int(totals_data.get("subtasks", 0)),
            done=int(totals_data.get("done", 0)),
            not_done=int(totals_data.get("notDone", 0)),
        )
        
        return cls(parents=parents, totals=totals)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（既存形式との互換性）"""
        return {
            "parents": [p.to_dict() for p in self.parents],
            "totals": self.totals.to_dict(),
        }


@dataclass
class MetricsCollection:
    """全メトリクスを保持"""
    burndown: Optional[Dict[str, Any]] = None
    velocity: Optional[Dict[str, Any]] = None
    project_sprint_count: Optional[Dict[str, Any]] = None
    status_counts: Optional[Dict[str, Any]] = None
    time_in_status: Optional[Dict[str, Any]] = None
    workload: Optional[Dict[str, Any]] = None
    kpis: Dict[str, int] = field(default_factory=dict)
    risks: Dict[str, int] = field(default_factory=dict)
    evidence: Optional[List[Dict[str, Any]]] = None
    project_subtask_count: Optional[Dict[str, Any]] = None
    assignee_workload: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """extras辞書形式に変換（既存コードとの互換性）"""
        return {
            "burndown": self.burndown,
            "velocity": self.velocity,
            "project_sprint_count": self.project_sprint_count,
            "status_counts": self.status_counts,
            "time_in_status": self.time_in_status,
            "workload": self.workload,
            "kpis": self.kpis,
            "risks": self.risks,
            "evidence": self.evidence,
            "project_subtask_count": self.project_subtask_count,
            "assignee_workload": self.assignee_workload,
        }


@dataclass
class AISummary:
    """AI生成要約"""
    full_text: Optional[str]
    evidence_reasons: Dict[str, str] = field(default_factory=dict)
    
    def is_available(self) -> bool:
        """要約が利用可能か"""
        return self.full_text is not None
