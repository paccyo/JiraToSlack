"""
Phase 5: AI要約生成
Gemini APIを使用してスプリントの要約とエビデンスの理由を生成する。
"""

import logging
import os
import json
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from textwrap import dedent
from datetime import datetime, date

if TYPE_CHECKING:
    import google.generativeai as genai_type

from .types import (
    JiraMetadata,
    CoreData,
    MetricsCollection,
    AISummary,
    EnvironmentConfig,
)

logger = logging.getLogger(__name__)

# Gemini設定
GEMINI_TIMEOUT = os.getenv("GEMINI_TIMEOUT", "12")
GEMINI_RETRIES = os.getenv("GEMINI_RETRIES", "1")
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "").lower() in ("1", "true", "yes")


class SummaryError(Exception):
    """AI要約生成時のエラー"""
    pass


def _try_import_genai() -> Optional[Any]:
    """google-generativeaiのインポートを試行"""
    try:
        import google.generativeai as genai
        return genai
    except ImportError:
        if GEMINI_DEBUG:
            logger.warning("google-generativeai がインストールされていません")
        return None


def _sanitize_api_key(raw_key: Optional[str]) -> Optional[str]:
    """
    APIキーをサニタイズ。
    末尾に#コメントがある場合は除去する。
    """
    if not raw_key:
        return None
    
    key = raw_key.strip()
    
    # #以降をコメントとして除去
    if "#" in key:
        key = key.split("#")[0].strip()
    
    return key if key else None


def _build_context(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection
) -> Dict[str, Any]:
    """
    AI要約用のコンテキストを構築する。
    
    Args:
        config: 環境設定
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
    
    Returns:
        Dict[str, Any]: コンテキスト辞書
    """
    # スプリント情報
    sprint_name = metadata.sprint.sprint_name or "現在のスプリント"
    sprint_start = metadata.sprint.sprint_start
    sprint_end = metadata.sprint.sprint_end
    
    # 残日数計算
    remaining_days = 0
    if sprint_end:
        try:
            if isinstance(sprint_end, str):
                end_date = datetime.fromisoformat(sprint_end.replace('Z', '+00:00')).date()
            else:
                end_date = sprint_end
            
            today = date.today()
            remaining_days = max(0, (end_date - today).days)
        except Exception:
            remaining_days = 0
    
    # 完了率
    done_percent = core_data.totals.completion_rate * 100
    target_percent = int(config.target_done_rate * 100)
    
    # 担当者リスト
    assignees = sorted(set(
        subtask.assignee
        for parent in core_data.parents
        for subtask in parent.subtasks
        if subtask.assignee
    ))
    
    # コンテキスト構築
    context = {
        "sprint_name": sprint_name,
        "sprint_start": sprint_start,
        "sprint_end": sprint_end,
        "remaining_days": remaining_days,
        "target_done_rate": target_percent,
        "done_percent": round(done_percent, 1),
        "subtasks_total": core_data.totals.subtasks,
        "subtasks_done": core_data.totals.done,
        "subtasks_not_done": core_data.totals.not_done,
        "assignees": assignees,
        "parents": [p.to_dict() for p in core_data.parents],
        "kpis": metrics.kpis,
        "risks": metrics.risks,
    }
    
    return context


def _generate_summary(
    genai: Any,
    api_key: str,
    context: Dict[str, Any]
) -> Optional[str]:
    """
    Gemini APIを使用して要約を生成する。
    
    Args:
        genai: google.generativeai モジュール
        api_key: サニタイズ済みAPIキー
        context: コンテキスト辞書
    
    Returns:
        Optional[str]: 生成された要約。失敗時はNone
    """
    try:
        # Configuration
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        
        timeout_s = float(GEMINI_TIMEOUT)
        retries = int(GEMINI_RETRIES)
        temp = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
        top_p = float(os.getenv("GEMINI_TOP_P", "0.9"))

        # Use REST transport to avoid gRPC plugin metadata issues
        genai.configure(api_key=api_key, transport="rest")
        generation_config = {
            "temperature": temp,
            "top_p": top_p,
            "max_output_tokens": 640
        }
        
        # プロンプト構築
        assignee_str = ", ".join(context["assignees"]) if context["assignees"] else "(担当者なし)"
        
        intro = dedent(
            """
            あなたは経験豊富なアジャイルコーチ兼データアナリストです。提示するコンテキスト(JSON)のみを唯一の事実情報源として分析し、
            仮定や想像の数値は用いず、[出力形式]に厳密に従って、実務に直結する洞察とアクションを提示してください。
            """
        )
        
        output_format = dedent(
            f"""
            ## 🎯 結論（1行断言）
            完了率[X%] - [順調✅/注意⚠️/危険🚨] 残[Y]日で目標[Z%]（[理由5字以内]）
            
            ## 🚨 即実行アクション（重要順3つ）
            ※担当者名は必ず以下のリストから選択してください: {assignee_str}
            1. [担当者] → [タスク] （[期限]）
            2. [担当者] → [タスク] （[期限]） 
            3. [担当者] → [タスク] （[期限]）
            
            ## 📊 根拠（2行以内）
            • データ: 完了[X]/全[Y]件、必要消化[Z]件/日（実績[W]件/日）
            • 問題: [最大リスク] + [ボトルネック] = [影響度数値]
            """
        )
        
        constraints = dedent(
            """
            【厳守制約】
            - 曖昧語禁止（推測・可能性・おそらく等）
            - 専門語→平易語（実装→作成、レビュー→確認、アサイン→割当）
            - 全数値必須、担当者名・期限必須
            - 各セクション規定行数厳守（結論1行、アクション3行、根拠2行）
            - 文字数300字以内、Markdown形式
            - JSONデータ以外の情報使用禁止
            """
        )
        
        format_specs = dedent(
            """
            【出力仕様】
            • ステータス判定: 完了率80%以上→✅順調、60-79%→⚠️注意、60%未満→🚨危険
            • アクション優先順位: 1)期限超過 2)期限間近 3)高優先度未着手 4)確認待ち 5)未割当
            • 数値必須項目: 完了率%、残日数、完了件数/全件数、必要消化件数/日、実績件数/日
            • 担当者表記: フルネーム不要、姓のみ可（田中、佐藤等）
            • 期限表記: 相対表現（今日、明日、X日後）または具体日時
            """
        )
        
        example_output = dedent(
            """
            【出力例】
            ## 🎯 結論（1行断言）
            完了率65% - 注意⚠️ 残3日で目標80%（遅延有）

            ## 🚨 即実行アクション（重要順3つ）
            1. 田中 → API作成完了 （明日17時）
            2. 佐藤 → UI確認完了 （明日12時）
            3. 山田 → DB設計割当 （今日中）

            ## 📊 根拠（2行以内）
            • データ: 完了13/20件、必要消化3件/日（実績2.1件/日）
            • 問題: API遅延2日 + 確認待ち5件 = 目標未達リスク40%
            """
        )
        
        prompt = (
            intro
            + "\n[出力形式]\n"
            + output_format
            + "\n" + constraints
            + "\n" + format_specs
            + "\n" + example_output
            + f"\n\n【分析対象データ】\nコンテキスト(JSON): {json.dumps(context, ensure_ascii=False, indent=2)}\n"
            + "\n上記JSONデータのみを根拠として、出力形式に厳密に従い分析結果を出力してください。"
        )
        
        # API呼び出しロジック
        def _call(model_id: str) -> Optional[str]:
            m = genai.GenerativeModel(model_id, generation_config=generation_config)
            last_err: Optional[Exception] = None
            
            for attempt in range(retries + 1):
                try:
                    out = m.generate_content(prompt, request_options={"timeout": timeout_s})
                    text = (getattr(out, "text", None) or "").strip()
                    
                    if not text:
                        # try concatenating from candidates
                        cand_texts = []
                        for c in getattr(out, "candidates", []) or []:
                            parts = getattr(getattr(c, "content", None), "parts", []) or []
                            frag = "".join(getattr(p, "text", "") for p in parts)
                            if frag:
                                cand_texts.append(frag)
                        text = "\n".join(t for t in cand_texts if t).strip()
                    
                    if text:
                        return text
                        
                except Exception as e:
                    last_err = e
                    if GEMINI_DEBUG:
                        logger.warning(f"Gemini API 試行 {attempt+1}/{retries+1} 失敗: {e}")
                
                # backoff
                if attempt < retries:
                    import time
                    time.sleep(0.6 * (attempt + 1))
            
            # if all attempts failed
            if GEMINI_DEBUG and last_err:
                logger.warning(f"Gemini API エラー (model={model_id}): {last_err}")
            
            return None
        
        # Try primary model
        text = _call(model_name)
        
        if not text and GEMINI_DEBUG:
            logger.warning("Gemini API: 空の応答")
        
        return text
        
    except Exception as e:
        if GEMINI_DEBUG:
            logger.error(f"要約生成エラー: {e}")
        return None


def _generate_evidence_reasons(
    genai: Any,
    api_key: str,
    evidences: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    各エビデンスの重要な理由をGemini APIで生成する。
    
    Args:
        genai: google.generativeai モジュール
        api_key: サニタイズ済みAPIキー
        evidences: エビデンスのリスト
    
    Returns:
        Dict[str, str]: {課題キー: 理由} のマップ
    """
    if os.getenv("GEMINI_EVIDENCE_REASON", "1").lower() in ("0", "false", "no"):
        return {}
    
    if not evidences:
        return {}
    
    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        timeout_s = float(GEMINI_TIMEOUT)
        temp = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
        top_p = float(os.getenv("GEMINI_TOP_P", "0.9"))
        
        try:
            max_chars = int(os.getenv("EVIDENCE_REASON_MAX_CHARS", "38"))
        except Exception:
            max_chars = 38
        
        # 生成に必要な最小情報を構築
        items = []
        for e in evidences:
            items.append({
                "key": e.get("key"),
                "summary": e.get("summary"),
                "status": e.get("status"),
                "assignee": e.get("assignee"),
                "priority": e.get("priority"),
                "duedate": e.get("duedate") or e.get("due"),
                "days": e.get("days"),
            })
        
        prompt = dedent(
            f"""
            あなたはスクラムチームのアジャイルコーチです。以下の各小タスクについて、なぜ重要かを日本語で1文ずつ作成してください。
            制約:
            - 各行は最大{max_chars}文字以内で簡潔に。
            - 根拠は滞留日数/期限/優先度/状態/担当など入力から導ける事実のみ。
            - 断言的で実務的な表現（例: 期限差し迫り、優先度高、レビュー滞留 等）。
            出力形式はJSONのみで、キーを課題キー、値を理由文字列としたオブジェクトで返してください。

            入力: {json.dumps(items, ensure_ascii=False)}
            出力: {{ "KEY": "理由" }} のマップのみを返してください。
            """
        ).strip()
        
        genai.configure(api_key=api_key, transport="rest")
        generation_config = {
            "temperature": temp,
            "top_p": top_p,
            "max_output_tokens": 256
        }
        
        def _call(model_id: str) -> Optional[str]:
            try:
                m = genai.GenerativeModel(model_id, generation_config=generation_config)
                out = m.generate_content(prompt, request_options={"timeout": timeout_s})
                text = (getattr(out, "text", None) or "").strip()
                
                if not text:
                    # candidates fallback
                    cand_texts = []
                    for c in getattr(out, "candidates", []) or []:
                        parts = getattr(getattr(c, "content", None), "parts", []) or []
                        frag = "".join(getattr(p, "text", "") for p in parts)
                        if frag:
                            cand_texts.append(frag)
                    text = "\n".join(t for t in cand_texts if t).strip()
                
                return text or None
            except Exception:
                return None
        
        text = _call(model_name)
        
        if not text:
            if GEMINI_DEBUG:
                logger.info("AI要約: evidence reasons 空応答（元の理由を使用）")
            return {}
        
        # JSON抽出
        result: Dict[str, str] = {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                result = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            try:
                import re
                m = re.search(r"\{[\s\S]*\}", text)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        result = {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                result = {}
        
        # 文字数制限を適用
        clipped: Dict[str, str] = {}
        for e in evidences:
            key = e.get("key")
            if key and key in result:
                reason = result[key]
                if len(reason) > max_chars:
                    reason = reason[:max_chars-1] + "…"
                clipped[key] = reason
        
        return clipped
        
    except Exception as e:
        if GEMINI_DEBUG:
            logger.error(f"エビデンス理由生成エラー: {e}")
        return {}


def generate_ai_summary(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    enable_logging: bool = False
) -> AISummary:
    """
    Phase 5: Gemini APIを使用してAI要約を生成する。
    
    Args:
        config: 環境設定
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        AISummary: AI生成要約
    
    Raises:
        SummaryError: 要約生成に失敗した場合（ただし、無効化時は例外を発生させない）
    """
    if enable_logging:
        logger.info("Phase 5: AI要約生成を開始します")
    
    # Gemini無効化チェック
    if os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes"):
        if enable_logging:
            logger.info("Gemini APIは無効化されています")
        return AISummary(full_text=None, evidence_reasons={})
    
    # APIキー取得とサニタイズ
    raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or config.gemini_api_key
    api_key = _sanitize_api_key(raw_key)
    
    if not api_key:
        if enable_logging:
            logger.info("Gemini APIキーが設定されていません")
        return AISummary(full_text=None, evidence_reasons={})
    
    # google-generativeaiのインポート
    genai = _try_import_genai()
    if not genai:
        if enable_logging:
            logger.warning("google-generativeai がインストールされていません")
        return AISummary(full_text=None, evidence_reasons={})
    
    try:
        # コンテキスト構築
        context = _build_context(config, metadata, core_data, metrics)
        
        if enable_logging:
            logger.info("AI要約を生成中...")
        
        # 要約生成
        full_text = _generate_summary(genai, api_key, context)
        
        # エビデンス理由生成
        evidence_reasons = {}
        # メトリクスからエビデンスを取得（存在する場合）
        if hasattr(metrics, 'evidence') and metrics.evidence:
            if enable_logging:
                logger.info(f"{len(metrics.evidence)} 件のエビデンスの理由を生成中...")
            evidence_reasons = _generate_evidence_reasons(genai, api_key, metrics.evidence)
        
        if enable_logging:
            if full_text:
                logger.info("Phase 5: AI要約生成が完了しました")
            else:
                logger.info("Phase 5: AI要約は生成されませんでした")
        
        return AISummary(full_text=full_text, evidence_reasons=evidence_reasons)
        
    except Exception as e:
        if enable_logging:
            logger.error(f"AI要約生成エラー: {e}")
        # エラーが発生しても続行できるようにNoneを返す
        return AISummary(full_text=None, evidence_reasons={})
