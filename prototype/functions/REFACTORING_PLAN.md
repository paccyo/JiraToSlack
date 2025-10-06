# main.py リファクタリング計画

## 📋 概要

現在の `main()` 関数（約500行）を、7つのフェーズに分割して関数化し、保守性・テスタビリティ・可読性を向上させる。

**生成日**: 2025年10月2日  
**対象**: `prototype/local_cli/main.py`  
**現在の行数**: 2655行（main関数: 約500行）

---

## 🎯 リファクタリングの目的

### 現状の課題
- ✗ main() が長大で可読性が低い
- ✗ 単体テストが困難（モック化しにくい）
- ✗ エラーハンドリングが散在
- ✗ 責務が明確でない（データ取得・加工・描画が混在）
- ✗ 部分的な再利用が困難

### 期待効果
- ✓ 各フェーズの責務が明確化
- ✓ 単体テスト可能な粒度
- ✓ エラーハンドリングの一元化
- ✓ 並列実行の最適化が容易
- ✓ デバッグ時の問題箇所の特定が容易
- ✓ 将来的な機能追加が容易

---

## 🔧 リファクタリング戦略

### 原則
1. **後方互換性の維持**: 既存の環境変数・入出力インターフェースは変更しない
2. **段階的リファクタリング**: 1フェーズずつテストしながら進める
3. **型ヒントの追加**: TypedDict や dataclass を活用
4. **依存性注入**: テスト容易性のため外部APIアクセスを注入可能に
5. **エラーハンドリングの統一**: Result型パターンまたは専用例外クラス

### アプローチ
- **抽出リファクタリング**: 既存コードから関数を抽出
- **インターフェース設計**: データクラスで入出力を定義
- **段階的置き換え**: main() 内で新関数を呼び出し、動作確認後に旧コード削除

---

## 📦 新しいファイル構成

```
prototype/local_cli/
├── main.py                          # エントリポイント（簡素化後）
├── core/                            # 新規ディレクトリ
│   ├── __init__.py
│   ├── types.py                     # データクラス・型定義
│   ├── phase1_environment.py        # Phase 1: 環境準備
│   ├── phase2_metadata.py           # Phase 2: メタデータ取得
│   ├── phase3_core_data.py          # Phase 3: コアデータ取得
│   ├── phase4_metrics.py            # Phase 4: メトリクス収集
│   ├── phase5_ai_summary.py         # Phase 5: AI要約
│   ├── phase6_rendering.py          # Phase 6: 画像描画
│   ├── phase7_output.py             # Phase 7: ファイル出力
│   └── orchestrator.py              # 統合オーケストレーター
├── Loder/                           # 既存（変更なし）
│   ├── dotenv_loader.py
│   ├── board_selector.py
│   ├── jira_client.py
│   └── __init__.py
└── queries/                         # 既存（変更なし）
    └── ...
```

---

## 🏗️ 詳細設計

### Phase 1: 環境と認証の準備

#### 新規ファイル: `core/phase1_environment.py`

```python
"""Phase 1: Environment and Authentication Setup"""
from dataclasses import dataclass
from typing import Optional
from requests.auth import HTTPBasicAuth
from ..Loder.dotenv_loader import ensure_env_loaded


@dataclass
class EnvironmentConfig:
    """環境設定を保持するデータクラス"""
    jira_domain: str
    jira_email: str
    jira_api_token: str
    output_dir: str
    target_done_rate: float = 0.8
    axis_mode: str = "percent"
    # その他の環境変数...
    
    @classmethod
    def from_env(cls) -> Optional['EnvironmentConfig']:
        """環境変数から設定を読み込む"""
        pass


@dataclass
class AuthContext:
    """認証情報を保持"""
    domain: str
    auth: HTTPBasicAuth
    
    def __repr__(self) -> str:
        """セキュアな文字列表現（トークンをマスク）"""
        return f"AuthContext(domain={self.domain}, auth=***)"


def setup_environment() -> tuple[EnvironmentConfig, AuthContext]:
    """
    Phase 1: 環境変数の読み込みと認証コンテキストの構築
    
    Returns:
        (EnvironmentConfig, AuthContext): 設定と認証情報
        
    Raises:
        EnvironmentError: 必須環境変数が不足している場合
    """
    # 1. .env ファイルの読み込み
    ensure_env_loaded()
    
    # 2. 設定の検証と構築
    config = EnvironmentConfig.from_env()
    if not config:
        raise EnvironmentError("必須の環境変数が設定されていません")
    
    # 3. 認証コンテキストの作成
    auth = HTTPBasicAuth(config.jira_email, config.jira_api_token)
    auth_ctx = AuthContext(domain=config.jira_domain, auth=auth)
    
    return config, auth_ctx
```

**影響範囲**: main() の冒頭20行程度  
**テスト方法**: モック環境変数でのユニットテスト  
**リスク**: 低（既存の dotenv_loader をラップするだけ）

---

### Phase 2: Jira メタデータ取得

#### 新規ファイル: `core/phase2_metadata.py`

```python
"""Phase 2: Jira Board and Sprint Metadata Retrieval"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from .phase1_environment import AuthContext


@dataclass
class BoardMetadata:
    """ボード情報"""
    board: Dict[str, Any]
    board_id: int
    project_key: Optional[str]
    boards_count: int


@dataclass
class SprintMetadata:
    """スプリント情報"""
    sprint: Optional[Dict[str, Any]]
    sprint_id: Optional[int]
    sprint_name: Optional[str]
    sprint_start: Optional[str]
    sprint_end: Optional[str]
    active_sprints_count: int


@dataclass
class JiraMetadata:
    """Jira メタデータの集約"""
    board: BoardMetadata
    sprint: SprintMetadata
    
    def to_dict(self) -> Dict[str, Any]:
        """ログ・デバッグ用の辞書変換"""
        pass


def fetch_jira_metadata(auth_ctx: AuthContext) -> JiraMetadata:
    """
    Phase 2: Jira のボード・スプリント情報を取得
    
    Args:
        auth_ctx: 認証コンテキスト
        
    Returns:
        JiraMetadata: ボード・スプリント情報
        
    Raises:
        JiraAPIError: API呼び出しに失敗した場合
    """
    from ..Loder.board_selector import resolve_board_with_preferences
    # ... 既存のresolve_board等を使用
    
    # 1. ボード解決
    board_data = _resolve_board(auth_ctx)
    
    # 2. プロジェクトキー推定
    project_key = _infer_project_key(auth_ctx, board_data.board)
    
    # 3. ボード数カウント
    boards_count = _count_boards(auth_ctx, project_key)
    
    # 4. スプリント情報取得
    sprint_data = _fetch_sprint_info(auth_ctx, board_data.board_id)
    
    return JiraMetadata(board=board_data, sprint=sprint_data)


def _resolve_board(auth_ctx: AuthContext) -> BoardMetadata:
    """ボード解決のヘルパー"""
    pass


def _fetch_sprint_info(auth_ctx: AuthContext, board_id: int) -> SprintMetadata:
    """スプリント情報取得のヘルパー"""
    pass
```

**影響範囲**: main() の40行程度  
**テスト方法**: モックHTTPレスポンスでのユニットテスト  
**リスク**: 中（APIレスポンス形式の変更に注意）

---

### Phase 3: コアデータ取得

#### 新規ファイル: `core/phase3_core_data.py`

```python
"""Phase 3: Core Data Acquisition (Subtasks)"""
from dataclasses import dataclass
from typing import List, Dict, Any
from pathlib import Path


@dataclass
class SubtaskData:
    """サブタスク情報"""
    key: str
    summary: str
    done: bool
    assignee: Optional[str]
    # その他のフィールド...


@dataclass
class ParentTask:
    """親タスク情報"""
    key: str
    summary: str
    assignee: Optional[str]
    subtasks: List[SubtaskData]


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


@dataclass
class CoreData:
    """コアデータの集約"""
    parents: List[ParentTask]
    totals: TaskTotals
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'CoreData':
        """JSONから構築"""
        pass


def fetch_core_data(base_dir: Path) -> CoreData:
    """
    Phase 3: スプリントのサブタスク一覧を取得
    
    Args:
        base_dir: クエリスクリプトのベースディレクトリ
        
    Returns:
        CoreData: サブタスク情報と集計
        
    Raises:
        ScriptExecutionError: クエリ実行に失敗した場合
    """
    from . import get_json_from_script  # 既存関数を再利用
    
    script_path = base_dir / "queries" / "jira_list_sprint_subtasks.py"
    raw_data = get_json_from_script(str(script_path))
    
    return CoreData.from_json(raw_data)
```

**影響範囲**: main() の10行程度  
**テスト方法**: モックサブプロセス実行でのユニットテスト  
**リスク**: 低（既存の get_json_from_script をラップ）

---

### Phase 4: 追加メトリクス収集

#### 新規ファイル: `core/phase4_metrics.py`

```python
"""Phase 4: Additional Metrics Collection"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


logger = logging.getLogger(__name__)


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
        }


class MetricsCollector:
    """メトリクス収集を管理"""
    
    def __init__(self, base_dir: Path, auth_ctx: 'AuthContext', 
                 jira_metadata: 'JiraMetadata', core_data: 'CoreData'):
        self.base_dir = base_dir
        self.auth_ctx = auth_ctx
        self.jira_metadata = jira_metadata
        self.core_data = core_data
        
    def collect_all(self, parallel: bool = True) -> MetricsCollection:
        """
        全メトリクスを収集
        
        Args:
            parallel: 並列実行するかどうか
            
        Returns:
            MetricsCollection: 収集したメトリクス
        """
        metrics = MetricsCollection()
        
        if parallel:
            metrics = self._collect_parallel()
        else:
            metrics = self._collect_sequential()
        
        # KPI・リスク指標の統合
        self._compute_kpis(metrics)
        self._compute_risks(metrics)
        
        # エビデンス生成
        metrics.evidence = self._generate_evidence(metrics)
        
        return metrics
    
    def _collect_parallel(self) -> MetricsCollection:
        """並列でメトリクスを収集"""
        metrics = MetricsCollection()
        tasks = [
            ("burndown", self._fetch_burndown),
            ("velocity", self._fetch_velocity),
            ("project_sprint_count", self._fetch_project_sprint_count),
            ("status_counts", self._fetch_status_counts),
            ("time_in_status", self._fetch_time_in_status),
            ("workload", self._fetch_workload),
        ]
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_name = {
                executor.submit(func): name 
                for name, func in tasks
            }
            
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result()
                    setattr(metrics, name, result)
                    logger.info(f"✓ {name} collected")
                except Exception as e:
                    logger.warning(f"✗ {name} failed: {e}")
                    setattr(metrics, name, None)
        
        return metrics
    
    def _fetch_burndown(self) -> Optional[Dict[str, Any]]:
        """バーンダウンデータ取得"""
        pass
    
    def _fetch_velocity(self) -> Optional[Dict[str, Any]]:
        """ベロシティデータ取得"""
        pass
    
    # ... 他のメトリクス取得メソッド
    
    def _compute_kpis(self, metrics: MetricsCollection) -> None:
        """KPI指標を計算して metrics に格納"""
        pass
    
    def _compute_risks(self, metrics: MetricsCollection) -> None:
        """リスク指標を計算"""
        pass
    
    def _generate_evidence(self, metrics: MetricsCollection) -> List[Dict[str, Any]]:
        """エビデンステーブルを生成"""
        pass


def collect_metrics(
    base_dir: Path,
    auth_ctx: 'AuthContext',
    jira_metadata: 'JiraMetadata',
    core_data: 'CoreData',
    parallel: bool = True
) -> MetricsCollection:
    """
    Phase 4: 追加メトリクスを収集
    
    Args:
        base_dir: クエリスクリプトのベースディレクトリ
        auth_ctx: 認証コンテキスト
        jira_metadata: Phase 2で取得したメタデータ
        core_data: Phase 3で取得したコアデータ
        parallel: 並列実行フラグ
        
    Returns:
        MetricsCollection: 収集したメトリクス
    """
    collector = MetricsCollector(base_dir, auth_ctx, jira_metadata, core_data)
    return collector.collect_all(parallel=parallel)
```

**影響範囲**: main() の200行程度（最大の改善箇所）  
**テスト方法**: 各メトリクス取得をモック化したユニットテスト  
**リスク**: 中（並列実行の導入により予期しない競合の可能性）

---

### Phase 5: AI要約生成

#### 新規ファイル: `core/phase5_ai_summary.py`

```python
"""Phase 5: AI Summary Generation with Gemini"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
from .phase4_metrics import MetricsCollection


@dataclass
class AIContext:
    """AI要約用のコンテキスト"""
    sprint_label: str
    sprint_total: int
    sprint_done: int
    done_percent: float
    target_percent: int
    remaining_days: int
    # ... その他のコンテキスト
    
    @classmethod
    def build(cls, 
              jira_metadata: 'JiraMetadata',
              core_data: 'CoreData',
              metrics: MetricsCollection,
              target_done_rate: float) -> 'AIContext':
        """メタデータ・データからコンテキストを構築"""
        pass


@dataclass
class AISummary:
    """AI生成要約"""
    full_text: Optional[str]
    evidence_reasons: Dict[str, str]  # 課題キー → 理由
    
    def is_available(self) -> bool:
        """要約が利用可能か"""
        return self.full_text is not None


class GeminiClient:
    """Gemini API クライアント"""
    
    def __init__(self, api_key: Optional[str]):
        self.api_key = self._sanitize_key(api_key)
        self.enabled = self._check_enabled()
        
    @staticmethod
    def _sanitize_key(raw_key: Optional[str]) -> Optional[str]:
        """APIキーをサニタイズ"""
        # 既存の _sanitize_api_key ロジック
        pass
    
    def _check_enabled(self) -> bool:
        """Geminiが有効かチェック"""
        if os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes"):
            return False
        return self.api_key is not None
    
    def generate_summary(self, context: AIContext) -> Optional[str]:
        """要約を生成"""
        if not self.enabled:
            return None
        
        # 既存の maybe_gemini_summary ロジック
        pass
    
    def justify_evidences(self, evidences: List[Dict[str, Any]]) -> Dict[str, str]:
        """エビデンスの理由を生成"""
        if not self.enabled:
            return {}
        
        # 既存の maybe_gemini_justify_evidences ロジック
        pass


def generate_ai_summary(
    jira_metadata: 'JiraMetadata',
    core_data: 'CoreData',
    metrics: MetricsCollection,
    target_done_rate: float
) -> AISummary:
    """
    Phase 5: Geminiを使用してAI要約を生成
    
    Args:
        jira_metadata: Phase 2のメタデータ
        core_data: Phase 3のコアデータ
        metrics: Phase 4のメトリクス
        target_done_rate: 目標達成率
        
    Returns:
        AISummary: AI生成要約
    """
    # APIキー取得
    raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = GeminiClient(raw_key)
    
    # コンテキスト構築
    context = AIContext.build(jira_metadata, core_data, metrics, target_done_rate)
    
    # 要約生成
    full_text = client.generate_summary(context)
    
    # エビデンス理由生成
    evidence_reasons = {}
    if metrics.evidence:
        evidence_reasons = client.justify_evidences(metrics.evidence)
    
    return AISummary(full_text=full_text, evidence_reasons=evidence_reasons)
```

**影響範囲**: main() の50行程度  
**テスト方法**: モックGemini APIレスポンスでのユニットテスト  
**リスク**: 低（既存ロジックのカプセル化）

---

### Phase 6: ダッシュボード描画

#### 新規ファイル: `core/phase6_rendering.py`

```python
"""Phase 6: Dashboard Image Rendering"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from .phase2_metadata import JiraMetadata
from .phase3_core_data import CoreData
from .phase4_metrics import MetricsCollection
from .phase5_ai_summary import AISummary


@dataclass
class RenderConfig:
    """描画設定"""
    output_path: Path
    axis_mode: str
    target_done_rate: float
    width: int = 1400
    height: int = 980
    
    @classmethod
    def from_env(cls, output_path: Path) -> 'RenderConfig':
        """環境変数から描画設定を構築"""
        pass


def render_dashboard(
    config: RenderConfig,
    jira_metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None
) -> Path:
    """
    Phase 6: ダッシュボードPNG画像を生成
    
    Args:
        config: 描画設定
        jira_metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクスコレクション
        ai_summary: AI要約（任意）
        
    Returns:
        Path: 生成した画像ファイルのパス
        
    Raises:
        RenderError: 描画に失敗した場合
    """
    # AI要約をメトリクスに統合（後方互換性のため）
    extras = metrics.to_dict()
    if ai_summary:
        extras["ai_full_text"] = ai_summary.full_text
    
    # 既存の draw_png を呼び出し
    from . import draw_png  # 既存関数
    
    draw_png(
        output_path=str(config.output_path),
        data=core_data.to_dict(),  # 既存形式に変換
        boards_n=jira_metadata.board.boards_count,
        sprints_n=jira_metadata.sprint.active_sprints_count,
        sprint_name=jira_metadata.sprint.sprint_name,
        sprint_start=jira_metadata.sprint.sprint_start,
        sprint_end=jira_metadata.sprint.sprint_end,
        axis_mode=config.axis_mode,
        target_done_rate=config.target_done_rate,
        extras=extras
    )
    
    return config.output_path
```

**影響範囲**: main() の10行程度  
**テスト方法**: モック画像生成でのユニットテスト  
**リスク**: 低（既存の draw_png をラップ）

---

### Phase 7: 追加出力

#### 新規ファイル: `core/phase7_output.py`

```python
"""Phase 7: Additional File Output"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any
import json
from .phase2_metadata import JiraMetadata
from .phase3_core_data import CoreData
from .phase4_metrics import MetricsCollection
from .phase5_ai_summary import AISummary


@dataclass
class OutputPaths:
    """出力ファイルパス"""
    report_md: Path
    tasks_json: Path
    data_json: Path


def generate_markdown_report(
    output_path: Path,
    jira_metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary],
    target_done_rate: float
) -> None:
    """
    Markdownレポートを生成
    
    Args:
        output_path: 出力先パス
        jira_metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約
        target_done_rate: 目標達成率
    """
    # 既存のMarkdown生成ロジック
    pass


def export_tasks_json(
    output_path: Path,
    jira_metadata: JiraMetadata,
    core_data: CoreData
) -> None:
    """
    タスクJSONをエクスポート
    
    Args:
        output_path: 出力先パス
        jira_metadata: Jiraメタデータ
        core_data: コアデータ
    """
    enriched = {
        "sprint": {
            "name": jira_metadata.sprint.sprint_name,
            "startDate": jira_metadata.sprint.sprint_start,
            "endDate": jira_metadata.sprint.sprint_end,
        },
        "parents": [p.to_dict() for p in core_data.parents],
        "totals": core_data.totals.to_dict(),
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)


def export_metrics_json(
    output_path: Path,
    jira_metadata: JiraMetadata,
    core_data: CoreData,
    target_done_rate: float,
    axis_mode: str
) -> None:
    """
    メトリクスJSONをエクスポート（Slack連携用）
    
    Args:
        output_path: 出力先パス
        jira_metadata: Jiraメタデータ
        core_data: コアデータ
        target_done_rate: 目標達成率
        axis_mode: 軸モード
    """
    metrics = {
        "sprint": {
            "name": jira_metadata.sprint.sprint_name,
            "startDate": jira_metadata.sprint.sprint_start,
            "endDate": jira_metadata.sprint.sprint_end,
        },
        "totals": core_data.totals.to_dict(),
        "doneRate": core_data.totals.completion_rate,
        "targetDoneRate": target_done_rate,
        "axis": axis_mode,
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def generate_all_outputs(
    base_dir: Path,
    jira_metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary],
    target_done_rate: float,
    axis_mode: str
) -> OutputPaths:
    """
    Phase 7: すべての追加出力ファイルを生成
    
    Args:
        base_dir: 出力ディレクトリ
        jira_metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約
        target_done_rate: 目標達成率
        axis_mode: 軸モード
        
    Returns:
        OutputPaths: 生成したファイルのパス
    """
    paths = OutputPaths(
        report_md=base_dir / "sprint_overview_report.md",
        tasks_json=base_dir / "sprint_overview_tasks.json",
        data_json=base_dir / "sprint_overview_data.json"
    )
    
    # Markdownレポート
    generate_markdown_report(
        paths.report_md,
        jira_metadata,
        core_data,
        metrics,
        ai_summary,
        target_done_rate
    )
    
    # タスクJSON
    export_tasks_json(paths.tasks_json, jira_metadata, core_data)
    
    # メトリクスJSON
    export_metrics_json(
        paths.data_json,
        jira_metadata,
        core_data,
        target_done_rate,
        axis_mode
    )
    
    return paths
```

**影響範囲**: main() の80行程度  
**テスト方法**: 生成ファイルの内容検証  
**リスク**: 低（既存のファイル出力ロジックの抽出）

---

### オーケストレーター: 統合管理

#### 新規ファイル: `core/orchestrator.py`

```python
"""Dashboard Generation Orchestrator"""
from pathlib import Path
from typing import Optional
import logging

from .phase1_environment import setup_environment, EnvironmentConfig, AuthContext
from .phase2_metadata import fetch_jira_metadata, JiraMetadata
from .phase3_core_data import fetch_core_data, CoreData
from .phase4_metrics import collect_metrics, MetricsCollection
from .phase5_ai_summary import generate_ai_summary, AISummary
from .phase6_rendering import render_dashboard, RenderConfig
from .phase7_output import generate_all_outputs, OutputPaths


logger = logging.getLogger(__name__)


class DashboardOrchestrator:
    """ダッシュボード生成を統括"""
    
    def __init__(self):
        self.config: Optional[EnvironmentConfig] = None
        self.auth_ctx: Optional[AuthContext] = None
        self.jira_metadata: Optional[JiraMetadata] = None
        self.core_data: Optional[CoreData] = None
        self.metrics: Optional[MetricsCollection] = None
        self.ai_summary: Optional[AISummary] = None
        
    def run(self) -> Path:
        """
        全フェーズを実行してダッシュボードを生成
        
        Returns:
            Path: 生成した画像ファイルのパス
        """
        logger.info("🚀 Dashboard generation started")
        
        # Phase 1: 環境準備
        logger.info("📋 Phase 1: Environment setup")
        self.config, self.auth_ctx = setup_environment()
        
        # Phase 2: メタデータ取得
        logger.info("🔍 Phase 2: Fetching Jira metadata")
        self.jira_metadata = fetch_jira_metadata(self.auth_ctx)
        
        # Phase 3: コアデータ取得
        logger.info("📊 Phase 3: Fetching core data")
        base_dir = Path(self.config.output_dir)
        self.core_data = fetch_core_data(base_dir)
        
        # Phase 4: メトリクス収集
        logger.info("📈 Phase 4: Collecting metrics")
        self.metrics = collect_metrics(
            base_dir,
            self.auth_ctx,
            self.jira_metadata,
            self.core_data,
            parallel=True
        )
        
        # Phase 5: AI要約生成
        logger.info("🤖 Phase 5: Generating AI summary")
        self.ai_summary = generate_ai_summary(
            self.jira_metadata,
            self.core_data,
            self.metrics,
            self.config.target_done_rate
        )
        
        # Phase 6: 画像描画
        logger.info("🎨 Phase 6: Rendering dashboard")
        render_config = RenderConfig(
            output_path=base_dir / "sprint_overview.png",
            axis_mode=self.config.axis_mode,
            target_done_rate=self.config.target_done_rate
        )
        image_path = render_dashboard(
            render_config,
            self.jira_metadata,
            self.core_data,
            self.metrics,
            self.ai_summary
        )
        
        # Phase 7: 追加出力
        logger.info("📄 Phase 7: Generating additional outputs")
        output_paths = generate_all_outputs(
            base_dir,
            self.jira_metadata,
            self.core_data,
            self.metrics,
            self.ai_summary,
            self.config.target_done_rate,
            self.config.axis_mode
        )
        
        logger.info(f"✅ Dashboard generation completed: {image_path}")
        logger.info(f"   Report: {output_paths.report_md}")
        logger.info(f"   Tasks: {output_paths.tasks_json}")
        logger.info(f"   Metrics: {output_paths.data_json}")
        
        return image_path


def run_dashboard_generation() -> int:
    """
    ダッシュボード生成を実行（エラーハンドリング付き）
    
    Returns:
        int: 終了コード（0=成功、1=失敗）
    """
    try:
        orchestrator = DashboardOrchestrator()
        image_path = orchestrator.run()
        print(str(image_path))
        return 0
    except Exception as e:
        logger.error(f"❌ Dashboard generation failed: {e}", exc_info=True)
        return 1
```

---

### 新しい main.py

#### 更新ファイル: `main.py`

```python
"""Dashboard Generator Entry Point (Refactored)"""
import sys
from pathlib import Path

# 既存のヘルパー関数・定数は維持（draw_png, get_json_from_script等）
# ... (既存のimportと関数定義)

def main() -> int:
    """
    エントリポイント（リファクタリング後）
    
    新しいオーケストレーターを使用してダッシュボード生成を実行
    """
    from prototype.local_cli.core.orchestrator import run_dashboard_generation
    return run_dashboard_generation()


if __name__ == "__main__":
    raise SystemExit(main())
```

**影響範囲**: main() を20行程度に短縮  
**テスト方法**: エンドツーエンドテスト  
**リスク**: 低（オーケストレーターへの単純な委譲）

---

## 🧪 テスト戦略

### 1. ユニットテスト

```python
# tests/core/test_phase1_environment.py
def test_environment_config_from_env(monkeypatch):
    """環境変数からの設定読み込みテスト"""
    monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token123")
    
    config = EnvironmentConfig.from_env()
    assert config.jira_domain == "https://example.atlassian.net"
    assert config.jira_email == "test@example.com"


# tests/core/test_phase4_metrics.py
def test_parallel_metrics_collection(mock_scripts):
    """並列メトリクス収集のテスト"""
    collector = MetricsCollector(...)
    metrics = collector.collect_all(parallel=True)
    
    assert metrics.burndown is not None
    assert metrics.velocity is not None
```

### 2. 統合テスト

```python
# tests/integration/test_orchestrator.py
def test_full_dashboard_generation(tmp_path, mock_jira_api):
    """エンドツーエンドのダッシュボード生成テスト"""
    orchestrator = DashboardOrchestrator()
    image_path = orchestrator.run()
    
    assert image_path.exists()
    assert image_path.suffix == ".png"
```

### 3. リグレッションテスト

- 既存の `test_main_check.py` を実行
- 出力ファイルのフォーマット検証
- 生成画像の基本要素チェック

---

## 📅 実装スケジュール

### Week 1: 基盤整備
- [ ] `core/` ディレクトリ作成
- [ ] `core/types.py` でデータクラス定義
- [ ] Phase 1 実装（環境準備）
- [ ] Phase 1 のユニットテスト作成

### Week 2: データ取得層
- [ ] Phase 2 実装（メタデータ取得）
- [ ] Phase 3 実装（コアデータ取得）
- [ ] Phase 2-3 のユニットテスト作成
- [ ] 統合テスト（Phase 1-3）

### Week 3: メトリクス収集
- [ ] Phase 4 実装（メトリクス収集）
- [ ] 並列実行機構の実装
- [ ] Phase 4 のユニットテスト作成
- [ ] パフォーマンステスト

### Week 4: AI統合と描画
- [ ] Phase 5 実装（AI要約）
- [ ] Phase 6 実装（描画）
- [ ] Phase 5-6 のユニットテスト作成

### Week 5: 出力とオーケストレーション
- [ ] Phase 7 実装（追加出力）
- [ ] Orchestrator 実装
- [ ] エンドツーエンドテスト作成
- [ ] main.py の更新

### Week 6: テストと文書化
- [ ] リグレッションテスト実行
- [ ] パフォーマンスベンチマーク
- [ ] ドキュメント更新
- [ ] レビューとマージ

---

## ⚠️ リスク管理

### 高リスク項目

1. **Phase 4: 並列実行**
   - **リスク**: 競合状態やデッドロックの可能性
   - **対策**: ThreadPoolExecutor の適切な設定、タイムアウト設定
   - **検証**: 並列実行のストレステスト

2. **Phase 6: 描画処理**
   - **リスク**: Pillow の描画ロジックが複雑で予期しないバグ
   - **対策**: 段階的リファクタリング、視覚的リグレッションテスト
   - **検証**: 既存出力との画像比較

### 中リスク項目

1. **Phase 2: API レスポンス形式**
   - **リスク**: Jira API のレスポンス形式変更
   - **対策**: 柔軟な型定義、バージョンチェック
   - **検証**: 複数のJiraバージョンでのテスト

2. **データクラスの互換性**
   - **リスク**: 既存コードとの型不一致
   - **対策**: to_dict() メソッドで後方互換性を確保
   - **検証**: 既存テストの実行

---

## 🎯 成功基準

### 必須要件
- ✅ すべての既存テストがパスする
- ✅ 出力ファイル（PNG, JSON, MD）が既存と同一フォーマット
- ✅ パフォーマンスが既存より10%以上劣化しない
- ✅ 環境変数インターフェースが変更されない

### 推奨要件
- ✅ 並列実行により30%以上の高速化
- ✅ ユニットテストカバレッジ80%以上
- ✅ 各Phaseの処理時間がログ出力される
- ✅ エラー時のスタックトレースが明瞭

---

## 📚 参考資料

### 設計パターン
- **Strategy Pattern**: 各Phaseで処理戦略を切り替え可能に
- **Builder Pattern**: データクラスの段階的構築
- **Facade Pattern**: Orchestrator が複雑な処理を隠蔽

### 推奨ライブラリ
- **pytest**: ユニットテスト
- **pytest-mock**: モック化
- **pytest-asyncio**: 非同期テスト（将来的な拡張用）
- **pydantic**: データバリデーション（オプション）

---

## 🔄 マイグレーション戦略

### Option A: ビッグバンアプローチ
全フェーズを一度に実装し、一括でmain()を置き換え

**メリット**: 一度の変更で完了  
**デメリット**: リスクが高い、デバッグが困難

### Option B: 段階的アプローチ（推奨）
1フェーズずつ実装し、main()内で徐々に置き換え

```python
# main.py（移行期間中）
def main() -> int:
    # Phase 1: 新実装
    config, auth_ctx = setup_environment()
    
    # Phase 2: 新実装
    jira_metadata = fetch_jira_metadata(auth_ctx)
    
    # Phase 3-7: 旧実装（段階的に置き換え）
    # ... 既存コード
    
    return 0
```

**メリット**: リスク分散、早期フィードバック  
**デメリット**: 実装期間が長い

---

## ✅ チェックリスト

### 実装前
- [ ] チーム内でリファクタリング計画をレビュー
- [ ] 既存テストの実行環境を確認
- [ ] ブランチ戦略を決定（feature/refactoring-phase1 等）

### 各Phase実装後
- [ ] ユニットテストをパス
- [ ] コードレビュー完了
- [ ] ドキュメント更新
- [ ] パフォーマンス測定

### 完了後
- [ ] すべてのリグレッションテストがパス
- [ ] パフォーマンスベンチマーク合格
- [ ] ドキュメント完全版公開
- [ ] マージとデプロイ

---

## 📞 問い合わせ先

質問・提案がある場合は以下まで：

- **担当**: チーム開発者
- **Slack**: #jira-to-slack-dev
- **Issue Tracker**: GitHub Issues

---

**最終更新**: 2025年10月2日  
**バージョン**: 1.0  
**ステータス**: 承認待ち
