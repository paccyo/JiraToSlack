
"""
Phase 6: ダッシュボード描画
Pdef render_dashboard(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None,
    enable_logging: bool = False,
    _draw_png_func=None,  # テスト用のインジェクションポイント
) -> Path:してダッシュボードPNG画像を生成する。
"""
import os
import io
import logging
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

from commands.jira_backlog_report.get_image.dashbord_orchestrator.types import (
    JiraMetadata,
    CoreData,
    MetricsCollection,
    AISummary,
)
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class DashboardError(Exception):
    """ダッシュボード描画時のエラー"""
    pass


def render_dashboard(
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None,
    enable_logging: bool = False,
):
    """
    Phase 6: ダッシュボードPNG画像を生成する。
    
    Args:
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約（任意）
        enable_logging: ログ出力を有効化するかどうか
        _draw_png_func: テスト用の描画関数（通常はNone）
    
    Returns:
        Path: 生成した画像ファイルのパス
    
    Raises:
        DashboardError: 描画に失敗した場合
    """
    if enable_logging:
        logger.info("[Phase 6] ダッシュボード描画を開始します")
    
    # try:        
    # メトリクスをextras辞書形式に変換
    extras = metrics.to_dict()
    
    # AI要約を統合（後方互換性のため）
    if ai_summary and ai_summary.full_text:
        extras["ai_full_text"] = ai_summary.full_text
    
    if ai_summary and ai_summary.evidence_reasons:
        extras["ai_reasons"] = ai_summary.evidence_reasons
    

    if enable_logging:
        logger.info(f"[Phase 6] 画像を生成中")


    # draw_pngを呼び出し
    # try:
    image_bytes = draw_png(
        data=core_data.to_dict(),
        boards_n=metadata.board["boards_count"],
        sprints_n=metadata.sprint["active_sprints_count"],
        sprint_name=metadata.sprint["name"],
        sprint_start=metadata.sprint["startDate"],
        sprint_end=metadata.sprint["endDate"],
        axis_mode="percent",
        target_done_rate=0.8,
        extras=extras,
    )
    # except Exception as e:
    #     raise DashboardError(f"ダッシュボード描画エラー: {e}") from e
    
    if enable_logging:
        logger.info(f"[Phase 6] ダッシュボード描画が完了しました")
    
    return image_bytes
        
    # except DashboardError:
    #     raise
    # except Exception as e:
    #     raise DashboardError(f"予期しないエラー: {e}") from e


def draw_png(
    data: Dict[str, Any],
    boards_n: int,
    sprints_n: int,
    sprint_name: Optional[str],
    sprint_start: Optional[str],
    sprint_end: Optional[str],
    axis_mode: str,
    target_done_rate: float,
    extras: Optional[Dict[str, Any]] = None,
) -> None:
    W, H = 1400, 980
    bg = (250, 250, 250)
    img = Image.new("RGB", (W, H), bg)
    g = ImageDraw.Draw(img)

    # Colorblind-friendly palette
    col_bg = (255, 255, 255)
    col_project = (230, 230, 230)
    col_board_focus = (200, 200, 200)
    col_board_other = (215, 215, 215)
    col_sprint_focus = (210, 210, 210)
    col_sprint_other = (235, 235, 235)
    # Unified palette (traffic-light + neutrals)
    col_task_done = (27, 158, 119)     # green
    col_task_todo = (217, 95, 2)       # orange
    col_outline = (80, 80, 80)
    col_text = (40, 40, 40)
    col_grid = (220, 220, 220)
    col_benchmark = (50, 50, 200)
    col_ok = (32, 158, 84)
    col_warn = (230, 170, 0)
    col_danger = (204, 32, 38)

    padding = 20
    project_bar_h = 40
    board_bar_h = 28
    sprint_bar_h = 22
    gap = 8
    
    def try_load_font(size: int) -> ImageFont.ImageFont:
        # --- Bundled Font Path ---
        try:
            from pathlib import Path
            
            # Assumes phase6_dashboard.py is 4 levels deep from the project root
            project_root = Path(__file__).resolve().parents[4]
            font_dir = project_root / "assets" / "fonts"
            
            logger.info(f"[Font Debug] Calculated project root: {project_root}")
            logger.info(f"[Font Debug] Checking for fonts in: {font_dir}")

            bundled_font_path_otf = font_dir / "NotoSansJP-Regular.otf"
            bundled_font_path_ttf = font_dir / "NotoSansJP-Regular.ttf"

            logger.info(f"[Font Debug] Checking for OTF: {bundled_font_path_otf}")
            logger.info(f"[Font Debug] OTF exists: {bundled_font_path_otf.exists()}")
            
            if bundled_font_path_otf.exists():
                logger.info("[Font Debug] Attempting to load OTF font.")
                return ImageFont.truetype(str(bundled_font_path_otf), size)

            logger.info(f"[Font Debug] Checking for TTF: {bundled_font_path_ttf}")
            logger.info(f"[Font Debug] TTF exists: {bundled_font_path_ttf.exists()}")

            if bundled_font_path_ttf.exists():
                logger.info("[Font Debug] Attempting to load TTF font.")
                return ImageFont.truetype(str(bundled_font_path_ttf), size)
            
            logger.warning("[Font Debug] Bundled font not found.")

        except Exception as e:
            logger.error(f"[Font Debug] Error loading bundled font: {e}", exc_info=True)
            pass
        # --- End Bundled Font Path ---

        logger.info("[Font Debug] Bundled font not found or failed, trying system fonts.")
        candidates: List[str] = []
        if os.name == "nt":
            candidates = [
                r"C:\Windows\Fonts\meiryo.ttc",
                r"C:\Windows\Fonts\YuGothR.ttc",
                r"C:\Windows\Fonts\YuGothM.ttc",
                r"C:\Windows\Fonts\msgothic.ttc",
                r"C:\Windows\Fonts\msmincho.ttc",
                r"C:\Windows\Fonts\segoeui.ttf",
            ]
        else:
            candidates = [
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                "/Library/Fonts/ヒラギノ角ゴ ProN W3.otf",
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.otf",
            ]
        # Generic fallbacks
        candidates += ["NotoSansCJKjp-Regular.otf", "NotoSansCJKJP-Regular.otf", "NotoSansJP-Regular.otf", "DejaVuSans.ttf", "arial.ttf"]

        for path in candidates:
            try:
                logger.info(f"[Font Debug] Trying system font: {path}")
                return ImageFont.truetype(path, size)
            except Exception:
                logger.warning(f"[Font Debug] Failed to load system font: {path}")
                continue
        
        logger.error("[Font Debug] All font loading attempts failed. Falling back to default.")
        return ImageFont.load_default()




    font_xs = try_load_font(11)
    font_sm = try_load_font(12)
    font_md = try_load_font(14)
    font_lg = try_load_font(20)
    font_xl = try_load_font(28)



    def text_wh(text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
        try:
            bbox = g.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            return int(g.textlength(text, font=font)), getattr(font, "size", 14)

    def fit_font_for_width(text: str, max_width: int, base_font: ImageFont.ImageFont, min_size: int = 10) -> ImageFont.ImageFont:
        size = getattr(base_font, "size", 14) or 14
        size = int(size)
        while size >= min_size:
            f = try_load_font(size)
            if g.textlength(text, font=f) <= max_width:
                return f
            size -= 1
        return try_load_font(min_size)

    def draw_text_fit(text: str, x: int, y: int, max_width: int, base_font: ImageFont.ImageFont, fill: Tuple[int, int, int]) -> ImageFont.ImageFont:
        f = fit_font_for_width(text, max_width, base_font)
        g.text((x, y), text, font=f, fill=fill)
        return f

    def trim_to_width(text: str, max_width: int, font: ImageFont.ImageFont) -> str:
        if g.textlength(text, font=font) <= max_width:
            return text
        ell = "…"
        if g.textlength(ell, font=font) > max_width:
            return ""
        lo, hi = 0, len(text)
        ans = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = text[:mid] + ell
            if g.textlength(cand, font=font) <= max_width:
                ans = cand
                lo = mid + 1
            else:
                hi = mid - 1
        return ans
    # Project bar (Header left)
    proj_x0, proj_y0 = padding, padding
    header_right_w = int(W * 0.42)
    proj_x1, proj_y1 = W - padding - header_right_w - 12, proj_y0 + project_bar_h

    # (title drawn later)
    boards_n = max(1, boards_n)
    board_gap = 2
    board_seg_w = (proj_x1 - proj_x0 - (boards_n - 1) * board_gap) // boards_n
    bx = proj_x0
    focus_board_idx = 0
    focus_board_x0 = proj_x0
    focus_board_x1 = proj_x0 + board_seg_w
    # (timestamp drawn later once; avoid duplicate here)
    focus_board_x0 = proj_x0
    for i in range(boards_n):
        fill = col_board_focus if i == focus_board_idx else col_board_other
        g.rectangle([bx, proj_y0 + 6, bx + board_seg_w, proj_y1 - 6], fill=fill, outline=col_outline)
        if i == focus_board_idx:
            focus_board_x0, focus_board_x1 = bx, bx + board_seg_w
        bx += board_seg_w + board_gap

    # Sprints row constrained to the focused board x-range
    spr_y0 = proj_y1 + gap
    spr_y1 = spr_y0 + board_bar_h
    g.rectangle([focus_board_x0, spr_y0, focus_board_x1, spr_y1], fill=col_board_focus, outline=(60, 60, 60))

    sprints_n = max(1, sprints_n)
    sprint_gap = 2
    spr_total_w = focus_board_x1 - focus_board_x0
    # Precompute sprint total from data for ratio calc (avoid undefined total_cnt)
    try:
        _dtot = (data or {}).get("totals", {}) if isinstance(data, dict) else {}
        sprint_total_data = int(_dtot.get("subtasks", 0))
    except Exception:
        sprint_total_data = 0
    # Try to draw sprint width proportional to subtasks share (sprint vs project)
    spr_ratio: Optional[float] = None
    try:
        kpi_data = (extras or {}).get("kpis", {}) if extras else {}
        # current sprint subtasks total (prefer KPI, fallback to data)
        if isinstance(kpi_data, dict):
            sprint_total = int(kpi_data.get("sprintTotal") or sprint_total_data)
        else:
            sprint_total = sprint_total_data
        proj_total = None
        if extras and isinstance(extras.get("project_subtask_count"), dict):
            proj_total = int(extras["project_subtask_count"].get("total") or 0)
        if not proj_total:
            proj_total = int(kpi_data.get("projectTotal") or 0) if isinstance(kpi_data, dict) else 0
        if proj_total and proj_total > 0:
            spr_ratio = max(0.0, min(1.0, float(sprint_total) / float(proj_total)))
    except Exception:
        spr_ratio = None

    sx = focus_board_x0
    focus_s_x0 = sx
    focus_s_x1 = sx + spr_total_w
        # アクティブスプリントが1件のみ → 帯を1本（Active Sprint Done/Remaining の2色積み棒）
    if sprints_n == 1:
        # 1本の帯で完了/未完了を表示
        g.rectangle([sx, spr_y0 + 4, sx + spr_total_w, spr_y1 - 4], fill=col_sprint_focus, outline=col_outline)
        focus_s_x0, focus_s_x1 = sx, sx + spr_total_w
        
        # Backlogを別の小さな横バーに表示
        try:
            kpi_data = (extras or {}).get("kpis", {}) if extras else {}
            project_open_total = int(kpi_data.get("projectOpenTotal", 0))
            sprint_open = int(kpi_data.get("sprintOpen", 0))  # 直接sprintOpenを使用
            backlog_open = max(0, project_open_total - sprint_open)
            
            if backlog_open > 0:
                # Backlog表示用の小さなバー（左上スプリント帯の下）
                backlog_y0 = spr_y1 + 2
                backlog_y1 = backlog_y0 + 12
                backlog_w = min(200, spr_total_w // 3)  # 幅は制限
                g.rectangle([sx, backlog_y0, sx + backlog_w, backlog_y1], fill=(230, 230, 230), outline=col_outline)
                g.text((sx + 4, backlog_y0 + 1), f"Backlog: {backlog_open}", font=font_xs, fill=col_text)
        except Exception:
            pass
    elif spr_ratio is not None:
        # 複数アクティブ（将来拡張）の場合のみ割合分割
        cur_w = max(2, int(round(spr_total_w * spr_ratio)))
        other_w = max(0, spr_total_w - cur_w)
        g.rectangle([sx, spr_y0 + 4, sx + cur_w, spr_y1 - 4], fill=col_sprint_focus, outline=col_outline)
        if other_w > 0:
            g.rectangle([sx + cur_w, spr_y0 + 4, sx + cur_w + other_w, spr_y1 - 4], fill=col_sprint_other, outline=col_outline)
        focus_s_x0, focus_s_x1 = sx, sx + cur_w
    else:
        # Fallback to equal segments when ratio is unknown
        spr_seg_w = (spr_total_w - (sprints_n - 1) * sprint_gap) // sprints_n
        focus_s_idx = 0
        focus_s_x0 = sx
        focus_s_x1 = sx + spr_seg_w
        for i in range(sprints_n):
            fill = col_sprint_focus if i == focus_s_idx else col_sprint_other
            g.rectangle([sx, spr_y0 + 4, sx + spr_seg_w, spr_y1 - 4], fill=fill, outline=col_outline)
            if i == focus_s_idx:
                focus_s_x0, focus_s_x1 = sx, sx + spr_seg_w
            sx += spr_seg_w + sprint_gap

    # Tasks row constrained to the focused sprint x-range
    parents = data.get("parents", [])
    tasks: List[Dict[str, Any]] = []
    for p in parents:
        for st in p.get("subtasks", []) or []:
            tasks.append(st)

    task_y0 = spr_y1 + gap
    task_y1 = task_y0 + sprint_bar_h
    g.rectangle([focus_s_x0, task_y0, focus_s_x1, task_y1], fill=col_sprint_focus, outline=(60, 60, 60))

    n = max(1, len(tasks))
    task_gap = 2
    task_total_w = focus_s_x1 - focus_s_x0
    task_seg_w = (task_total_w - (n - 1) * task_gap) // n
    tx = focus_s_x0
    for t in tasks:
        done = bool(t.get("done")) if t.get("done") is not None else False
        fill = col_task_done if done else col_task_todo
        g.rectangle([tx, task_y0 + 3, tx + task_seg_w, task_y1 - 3], fill=fill, outline=None)
        tx += task_seg_w + task_gap

    # Summary bar (Done vs Not Done) with labels — use data-based totals (consistency)
    totals = data.get("totals", {})
    done_cnt = int(totals.get("done", 0))
    total_cnt = int(totals.get("subtasks", max(1, len(tasks))))
    not_done_cnt = max(0, total_cnt - done_cnt)
    done_rate = (done_cnt / total_cnt) if total_cnt > 0 else 0.0

    sum_y0 = task_y1 + 14
    sum_y1 = sum_y0 + 26
    g.rectangle([focus_s_x0, sum_y0, focus_s_x1, sum_y1], fill=(245, 245, 245), outline=col_outline)
    done_w = int((focus_s_x1 - focus_s_x0) * done_rate)
    g.rectangle([focus_s_x0, sum_y0, focus_s_x0 + done_w, sum_y1], fill=col_task_done)
    g.rectangle([focus_s_x0 + done_w, sum_y0, focus_s_x1, sum_y1], fill=col_task_todo)
    # Headline above summary bar — clarify unit (小タスク)
    headline = f"スプリント(小タスク): {total_cnt}件 | 完了: {done_cnt} ({int(done_rate*100)}%)"
    head_x, head_y = focus_s_x0, sum_y0 - 20
    g.text((head_x, head_y), headline, font=font_md, fill=col_text)
    # Compute headline bounding box for collision checks
    try:
        hb = g.textbbox((head_x, head_y), headline, font=font_md)
    except Exception:
        hb = (head_x, head_y, head_x + int(g.textlength(headline, font=font_md)), head_y + getattr(font_md, "size", 14))

    # Numeric labels on segments
    def center_text(x0: int, x1: int, y: int, text: str, font: ImageFont.ImageFont, fill=col_text):
        tw, th = g.textlength(text, font=font), font.size
        cx = (x0 + x1) // 2 - int(tw // 2)
        g.text((cx, y), text, font=font, fill=fill)

    label_y = sum_y0 + 5
    done_label = f"{done_cnt} tasks ({int(done_rate*100)}%)"
    not_label = f"{not_done_cnt} tasks ({int((1-done_rate)*100)}%)"
    if done_w > g.textlength(done_label, font=font_sm) + 8:
        center_text(focus_s_x0, focus_s_x0 + done_w, label_y, done_label, font_sm, fill=(255,255,255))
    if (focus_s_x1 - (focus_s_x0 + done_w)) > g.textlength(not_label, font=font_sm) + 8:
        center_text(focus_s_x0 + done_w, focus_s_x1, label_y, not_label, font_sm, fill=(255,255,255))

    # Axis grid and labels (0,25,50,75,100)
    grid_y0 = sum_y1 + 10
    grid_y1 = grid_y0 + 1
    g.line([focus_s_x0, grid_y0, focus_s_x1, grid_y0], fill=col_outline, width=1)
    ticks = [0, 25, 50, 75, 100]
    for t in ticks:
        x = focus_s_x0 + int((focus_s_x1 - focus_s_x0) * (t / 100.0))
        g.line([x, grid_y0 - 5, x, grid_y0 + 5], fill=col_outline, width=1)
        # light vertical grid lines
        g.line([x, spr_y0, x, sum_y1], fill=col_grid, width=1)
        if axis_mode == "percent":
            g.text((x - 10, grid_y0 + 6), f"{t}%", font=font_sm, fill=col_text)
        else:
            # Convert percent into counts scale
            count_at_t = int(round(total_cnt * (t / 100.0)))
            g.text((x - 10, grid_y0 + 6), str(count_at_t), font=font_sm, fill=col_text)

    # Benchmark line (target done %)
    bx = focus_s_x0 + int((focus_s_x1 - focus_s_x0) * target_done_rate)
    g.line([bx, sum_y0 - 10, bx, sum_y1 + 10], fill=col_benchmark, width=2)
    # Place benchmark label; avoid collision with headline
    tgt_label = f"目標 {int(target_done_rate*100)}%"
    tgt_pos_top = (bx + 4, sum_y0 - 18)
    try:
        tb = g.textbbox(tgt_pos_top, tgt_label, font=font_sm)
    except Exception:
        tw = int(g.textlength(tgt_label, font=font_sm))
        th = getattr(font_sm, "size", 12)
        tb = (tgt_pos_top[0], tgt_pos_top[1], tgt_pos_top[0] + tw, tgt_pos_top[1] + th)
    # Simple AABB intersect
    def _intersects(a, b):
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)
    if _intersects(hb, tb):
        # Move below the bar if colliding
        g.text((bx + 4, sum_y1 + 4), tgt_label, font=font_sm, fill=col_benchmark)
    else:
        g.text(tgt_pos_top, tgt_label, font=font_sm, fill=col_benchmark)

    # 右ヘッダー領域をミニVelocity専用に利用
    velmini_box_x0 = proj_x1 + 12
    velmini_box_w = header_right_w
    bd_box_y0 = padding
    bd_box_h = 110
    # mini velocity chart (reserved_h is dynamic based on KPI text height)
    def draw_velocity_mini(x0: int, y0: int, w: int, h: int, vel: Optional[Dict[str, Any]], reserved_h: int) -> None:
        # Apply adapter to handle both new and old velocity formats
        vel = adapt_velocity_data(vel)
        if not vel:
            g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
            g.text((x0 + 8, y0 + 8), "データなし", font=font_sm, fill=(120, 120, 120))
            return
        pts = vel.get("points") or []
        if not isinstance(pts, list) or len(pts) < 2:
            g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
            g.text((x0 + 8, y0 + 8), "ベロシティはスプリント2以降に表示", font=font_sm, fill=(120, 120, 120))
            return
        pad = 10
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        # bars
        n = max(1, len(pts))
        bar_gap = 4
        bar_w = max(4, (w - 2 * pad - (n - 1) * bar_gap) // max(1, n))
        values = [float(p.get("points") or 0.0) for p in pts]
        avg = float(vel.get("avgPoints") or 0.0)
        maxv = max(values + [avg, 1.0])
        for i, v in enumerate(values):
            bx = gx0 + pad + i * (bar_w + bar_gap)
            by = gy1 - pad
            bh = int((v / maxv) * (h - 2 * pad - max(0, reserved_h)))
            g.rectangle([bx, by - bh, bx + bar_w, by], fill=(80, 170, 240), outline=col_outline)
        # avg line
        if maxv > 0:
            y_avg = int((gy1 - pad) - (avg / maxv) * (h - 2 * pad - max(0, reserved_h)))
            g.line([gx0 + pad, y_avg, gx1 - pad, y_avg], fill=(120, 0, 120), width=2)
        # draw a small caption at bottom-left to avoid header overlap
        g.text((gx0 + pad, gy1 - pad - 14), "Velocity", font=font_sm, fill=col_text)

    vel_data_hdr = (extras or {}).get("velocity") if extras else None
    # header metrics — emphasize progress vs target, avoid zero by falling back to data totals
    try:
        kpis_hdr = (extras or {}).get("kpis", {}) if extras else {}
        proj_total = int(kpis_hdr.get("projectTotal", 0))
        # fallback to subtask totals for sprint numbers to ensure consistency
        sprint_total_kpi = int(kpis_hdr.get("sprintTotal", 0))
        sprint_done_kpi = int(kpis_hdr.get("sprintDone", 0))
        sprint_total = sprint_total_kpi 
        sprint_done = sprint_done_kpi 
        done_pct = int(round(100 * (sprint_done / max(1, sprint_total))))
        tgt_pct = int(round(100 * target_done_rate))
        tx = velmini_box_x0 + 10
        ty = bd_box_y0 + 6
        label = f"進捗 {done_pct}% / 目標 {tgt_pct}%"
        max_text_w = velmini_box_w - 18
        # Pre-fit fonts to compute reserved height for chart
        f1 = fit_font_for_width(label, max_text_w, font_lg)
        f2 = fit_font_for_width(
            f"プロジェクト:{proj_total} | スプリント(小タスク):{sprint_total} 完了:{sprint_done}",
            max_text_w,
            font_sm,
        )
        h1 = text_wh(label, f1)[1]
        line2 = f"プロジェクト:{proj_total} | スプリント(小タスク):{sprint_total} 完了:{sprint_done}"
        h2 = text_wh(line2, f2)[1]
        # Dedicated KPI panel above mini-velocity
        reserved_h = h1 + 4 + h2 + 10  # inner paddings
        # Ensure we leave room for the mini velocity chart
        min_vel_h = 40
        if reserved_h > bd_box_h - min_vel_h:
            reserved_h = max(28, bd_box_h - min_vel_h)
        # Draw KPI panel box
        g.rectangle([velmini_box_x0, bd_box_y0, velmini_box_x0 + velmini_box_w, bd_box_y0 + reserved_h], outline=col_outline, fill=(255, 255, 255))
        used_font = draw_text_fit(label, tx, ty, max_text_w, font_lg, (col_danger if done_pct < tgt_pct else col_ok))
        ty2 = ty + text_wh(label, used_font)[1] + 4
        draw_text_fit(line2, tx, ty2, max_text_w, font_sm, col_text)
        # Draw mini velocity below KPI panel
        mv_y0 = bd_box_y0 + reserved_h + 6
        mv_h = max(min_vel_h, bd_box_h - reserved_h - 6)
        draw_velocity_mini(velmini_box_x0, mv_y0, velmini_box_w, mv_h, vel_data_hdr, 0)
    except Exception:
        pass
    # Timestamp will be drawn at footer (moved from header to avoid collisions)
    
    def fmt_date(dt_str: Optional[str]) -> Optional[str]:
        # OSごとに日本語フォントを優先してロード。見つからなければデフォルト。
        if not dt_str:
            return None
        try:
            from datetime import datetime
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
                try:
                    d = datetime.strptime(dt_str, fmt)
                    return d.strftime("%Y/%m/%d")
                except Exception:
                    continue
        except Exception:
            pass
        return dt_str.replace("-", "/")
    
    # Title with sprint name and date range (Japanese formatting)
    title = "スプリント"
    if sprint_name:
        title = f"スプリント {sprint_name}"
    d0 = fmt_date(sprint_start) if sprint_start else None
    d1 = fmt_date(sprint_end) if sprint_end else None
    if d0 and d1:
        title = f"{title} ({d0} - {d1})"
    # draw safely within canvas (avoid negative y)
    g.text((proj_x0, max(4, proj_y0 - 2)), title, font=font_lg, fill=col_text)

    # Annotation for high not-done ratio and remember its bottom to avoid overlap with next blocks
    annotation_bottom = sum_y1
    if (1 - done_rate) >= 0.4:
        ann_text = f"未完了が{int((1-done_rate)*100)}%と高い"
        ann_x = focus_s_x0
        ann_y = sum_y1 + 36
        g.text((ann_x, ann_y), ann_text, font=font_md, fill=col_danger)
        annotation_bottom = ann_y + text_wh(ann_text, font_md)[1]

    # Left column blocks below header: Velocity and Status Distribution
    left_col_x0 = proj_x0
    # Push left column below annotation if needed
    left_col_y0 = max(grid_y0 + 40, annotation_bottom + 8)
    left_col_w = proj_x1 - proj_x0
    
    # Adapter function to handle both old and new velocity data formats
    def adapt_velocity_data(vel: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert new velocity format to old format for backward compatibility."""
        if not vel:
            return None
        
        # If already in old format, return as-is
        if "points" in vel and "avgPoints" in vel:
            return vel
        
        # New metrics format: current sprint summary + historical samples
        hist_block = vel.get("historical") if isinstance(vel, dict) else None
        if isinstance(hist_block, dict):
            samples = hist_block.get("samples") or []
            points: List[Dict[str, Any]] = []
            for sample in samples:
                completed = sample.get("completedSP", 0.0)
                try:
                    completed_val = float(completed)
                except Exception:
                    completed_val = 0.0
                entry = {
                    "points": completed_val,
                    "sprintId": sample.get("sprintId"),
                    "sprintName": sample.get("name"),
                    "planned": sample.get("plannedSP"),
                    "rate": sample.get("rate"),
                }
                points.append(entry)

            # Optionally include current sprint as the first item if not already present
            if not points:
                try:
                    current_points = float(vel.get("completedSP", 0.0))
                except Exception:
                    current_points = 0.0
                points.append({
                    "points": current_points,
                    "sprintId": None,
                    "sprintName": vel.get("currentSprintName") or "Current Sprint",
                    "planned": vel.get("plannedSP"),
                    "rate": vel.get("completionRate"),
                })

            avg_completed = hist_block.get("averageCompletedSP")
            try:
                avg_points = float(avg_completed)
            except Exception:
                avg_points = 0.0

            return {
                "points": points,
                "avgPoints": avg_points,
            }

        # Convert new format to old format
        if "history" in vel and "avg" in vel:
            points = []
            for h in vel.get("history", []):
                points.append({
                    "sprintId": h.get("id"),
                    "sprintName": h.get("name"),
                    "points": h.get("points", 0.0)
                })
            
            return {
                "board": vel.get("board"),
                "fieldId": vel.get("fieldId", "customfield_10016"),  # fallback
                "points": points,
                "avgPoints": vel.get("avg", 0.0)
            }
        
        return vel
    
    # Velocity bars
    def draw_velocity(x0: int, y0: int, w: int, h: int, vel: Optional[Dict[str, Any]]) -> int:
        # Apply adapter to handle both new and old velocity formats
        vel = adapt_velocity_data(vel)
        if not vel:
            return y0
        pts = vel.get("points") or []
        avg = float(vel.get("avgPoints") or 0.0)
        if not isinstance(pts, list):
            return y0
        pad = 10
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        g.text((gx0 + pad, gy0 + 2), "Velocity (last sprints)", font=font_md, fill=col_text)
        # bars
        n = max(1, len(pts))
        bar_gap = 6
        bar_w = max(6, (w - 2 * pad - (n - 1) * bar_gap) // max(1, n))
        maxv = max([float(p.get("points") or 0.0) for p in pts] + [avg, 1.0])
        for i, p in enumerate(pts):
            v = float(p.get("points") or 0.0)
            bx = gx0 + pad + i * (bar_w + bar_gap)
            by = gy1 - pad
            bh = int((v / maxv) * (h - 2 * pad))
            g.rectangle([bx, by - bh, bx + bar_w, by], fill=(80, 170, 240), outline=col_outline)
        # avg line
        if maxv > 0:
            y_avg = int((gy1 - pad) - (avg / maxv) * (h - 2 * pad))
            g.line([gx0 + pad, y_avg, gx1 - pad, y_avg], fill=(120, 0, 120), width=2)
            g.text((gx0 + pad + 4, y_avg - 14), f"avg {avg:.1f}", font=font_sm, fill=(120, 0, 120))
        # target line (dashed)
        try:
            target = ""
        except Exception:
            target = None  # type: ignore
        if maxv > 0 and target:
            y_t = int((gy1 - pad) - (float(target) / maxv) * (h - 2 * pad))
            # dashed line
            x = gx0 + pad
            while x < gx1 - pad:
                x2 = min(x + 10, gx1 - pad)
                g.line([x, y_t, x2, y_t], fill=(200, 0, 0), width=2)
                x += 16
            g.text((gx0 + pad + 4, y_t + 2), f"target {float(target):.1f}", font=font_sm, fill=(200, 0, 0))
        return gy1

    vel_box_h = 140
    vel_data = (extras or {}).get("velocity") if extras else None
    vel_y1 = draw_velocity(left_col_x0, left_col_y0, left_col_w, vel_box_h, vel_data)

    # Status distribution stacked bar
    def draw_status_dist(x0: int, y0: int, w: int, h: int, st: Optional[Dict[str, Any]]) -> int:
        if not st:
            return y0
        bys = st.get("byStatus") or []
        total = float(st.get("total") or 0.0)
        if total <= 0 or not bys:
            return y0
        g.text((x0, y0 - 18), "ステータス分布", font=font_md, fill=col_text)
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        # palette rotate
        palette = [
            (200, 200, 200),
            (253, 174, 97),
            (44, 162, 95),
            (49, 130, 189),
            (141, 160, 203),
            (230, 85, 13),
        ]
        x = gx0 + 10
        y = gy0 + 10
        hbar = h - 20
        for i, row in enumerate(bys):
            cnt = float(row.get("count") or 0.0)
            frac = cnt / total
            wseg = int((w - 20) * frac)
            col = palette[i % len(palette)]
            g.rectangle([x, y, x + wseg, y + hbar], fill=col, outline=col_outline)
            label_full = f"{row.get('status')} ({int(frac*100)}%)"
            # If label doesn't fit, fallback to percentage only
            label = label_full if (wseg >= g.textlength(label_full, font=font_sm) + 8) else f"{int(frac*100)}%"
            g.text((x + 4, y + hbar//2 - 8), label, font=font_sm, fill=(30, 30, 30))
            x += wseg
        return gy1

    st_box_y0 = vel_y1 + 24
    st_box_h = 60
    st_data = (extras or {}).get("status_counts") if extras else None
    st_y1 = draw_status_dist(left_col_x0, st_box_y0, left_col_w, st_box_h, st_data)

    # Time-in-Status heatmap (avg days per status)
    def draw_time_in_status_heatmap(x0: int, y0: int, w: int, h: int, tis: Optional[Dict[str, Any]]) -> int:
        if not tis:
            return y0
        per_issue = tis.get("perIssue") or []
        if not per_issue:
            return y0
        # aggregate average days per status
        sum_map: Dict[str, float] = {}
        cnt_map: Dict[str, int] = {}
        vals_map: Dict[str, List[float]] = {}

        # normalize function to merge same meanings (e.g., IN_PROGRESS vs In Progress)
        def norm_status(name: str) -> str:
            s = str(name or "").strip()
            if not s:
                return s
            key = s.lower().replace(" ", "_")
            # common mappings
            aliases = {
                "in_progress": "In Progress",
                "inprogress": "In Progress",
                "in-progress": "In Progress",
                "todo": "To Do",
                "to_do": "To Do",
                "to-do": "To Do",
                "in_review": "In Review",
                "inreview": "In Review",
                "qa": "QA",
                "quality_assurance": "QA",
                "done": "Done",
                "review": "Review",
            }
            return aliases.get(key, s)
        for row in per_issue:
            by = row.get("byStatus") or {}
            for st, days in by.items():
                try:
                    d = float(days)
                except Exception:
                    d = 0.0
                label = norm_status(st)
                sum_map[label] = sum_map.get(label, 0.0) + d
                cnt_map[label] = cnt_map.get(label, 0) + 1
                vals_map.setdefault(label, []).append(d)
        if not sum_map:
            return y0
        items = [(k, (sum_map[k] / max(1, cnt_map.get(k, 1)))) for k in sum_map.keys()]
        # sort by avg days desc
        items.sort(key=lambda x: -x[1])
        # limit to max statuses for display (default 6)
        try:
            max_statuses = 6
        except Exception:
            max_statuses = 6
        items = items[:max(1, max_statuses)]
        g.text((x0, y0 - 18), "工程滞在時間（日）(avg | median)", font=font_md, fill=col_text)
        # layout grid 1 row, N columns (small heatmap)
        pad = 8
        n = len(items)
        if n <= 0:
            return y0
        cell_w = max(60, (w - 2 * pad) // n)
        cell_h = h - 2 * pad - 18
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        # color scale (green -> yellow -> red)
        max_days = max([v for _, v in items] + [1.0])
        def color_for(value: float) -> Tuple[int, int, int]:
            t = min(1.0, value / max_days)
            # 0 -> green(44,162,95), 1 -> red(215,48,39) via yellow
            # simple linear blend green->red
            g0 = (44, 162, 95)
            r1 = (215, 48, 39)
            r = int(g0[0] + (r1[0] - g0[0]) * t)
            gch = int(g0[1] + (r1[1] - g0[1]) * t)
            b = int(g0[2] + (r1[2] - g0[2]) * t)
            return (r, gch, b)
        x = x0 + pad
        y = y0 + pad + 12
        for name, avgd in items:
            col = color_for(avgd)
            g.rectangle([x, y, x + cell_w - 6, y + cell_h], fill=col, outline=col_outline)
            # median label
            try:
                vals = vals_map.get(name, [])
                med = 0.0
                if vals:
                    svals = sorted(vals)
                    m = len(svals)
                    med = (svals[m//2] if m % 2 == 1 else (svals[m//2 - 1] + svals[m//2]) / 2.0)
                g.text((x + 4, y - 14), f"{avgd:.1f}/{med:.1f}d", font=font_sm, fill=col_text)
            except Exception:
                g.text((x + 4, y - 14), f"{avgd:.1f}d", font=font_sm, fill=col_text)
            # label (status name) under cell ifスペース
            g.text((x + 4, y + cell_h + 2), name[:12], font=font_sm, fill=col_text)
            x += cell_w
        return gy1

    tis_box_y0 = st_y1 + 24
    tis_box_h = 100
    tis_data = (extras or {}).get("time_in_status") if extras else None
    tis_y1 = draw_time_in_status_heatmap(left_col_x0, tis_box_y0, left_col_w, tis_box_h, tis_data)

    # Right column: KPI cards and Assignee workload
    right_x0 = velmini_box_x0
    right_y0 = bd_box_y0 + bd_box_h + 16
    right_w = header_right_w

    def draw_kpi_cards(x0: int, y0: int, w: int, h: int, kpis: Dict[str, int]) -> int:
        pad = 8
        cols = 3
        rows = 2
        gap = 10
        card_w = (w - (cols - 1) * gap)
        card_w = card_w // cols
        card_h = h
        # six KPI cards
        order = [
            ("projectOpenTotal", "プロジェクト内未完了タスク数", (200, 100, 40)),  # 未完了タスク数に変更
            ("sprintOpen", "スプリント内未完了タスク数", (60, 160, 60)),  # 総タスク数から未完了タスク数に変更
            ("unassignedCount", "担当者未定タスク数", (27, 158, 119)),  # 完了タスク数から担当者未定タスク数に変更
            ("overdue", "期限遵守中✅", (60, 140, 60)),
            ("dueSoon", "注意:7日以内期限", (230, 140, 0)),
            ("highPriorityTodo", "要注意タスク(高優先度)", (200, 120, 60)),
        ]
        x = x0
        y = y0
        for idx, (key, title, col) in enumerate(order):
            v = int(kpis.get(key, 0))
            g.rectangle([x, y, x + card_w, y + card_h], outline=col_outline, fill=(245, 245, 245))
            g.text((x + 8, y + 6), title, font=font_sm, fill=col_text)
            # Positive phrasing for zero overdue
            if key == "overdue" and v == 0:
                txt = "0"
                col_draw = col_ok
            elif key == "sprintOpen":
                # 未完了 / 総数 の形式で表示
                sprint_total = int(kpis.get("sprintTotal", 0))
                txt = f"{v}/{sprint_total}"
                col_draw = col
            elif key == "projectOpenTotal":
                # プロジェクト内未完了 / 総数 の形式で表示
                project_total = int(kpis.get("projectTotal", 0))
                txt = f"{v}/{project_total}"
                col_draw = col
            else:
                txt = str(v)
                col_draw = col
            g.text((x + 8, y + 28), txt, font=try_load_font(24), fill=col_draw)
            # advance grid
            if (idx + 1) % cols == 0:
                x = x0
                y += card_h + gap
            else:
                x += card_w + gap
        return y

    kpi_h = 64
    kpi_data = (extras or {}).get("kpis") if extras else {}
    kpi_y1 = draw_kpi_cards(right_x0, right_y0, right_w, kpi_h, kpi_data or {})

    def draw_workload(x0: int, y0: int, w: int, h: int, wl: Optional[Dict[str, Any]]) -> int:
        if not wl:
            return y0
        rows = wl.get("byAssignee") or []
        if not rows:
            return y0
        g.text((x0, y0 - 18), "担当者別ワークロード（未完了）", font=font_md, fill=col_text)
        pad = 8
        topn = min(8, len(rows))
        rows = sorted(rows, key=lambda r: -int(r.get("notDone") or 0))[:topn]
        maxv = max([int(r.get("notDone") or 0) for r in rows] + [1])
        bar_h = max(14, (h - 2 * pad - (topn - 1) * 6) // max(1, topn))
        y = y0
        for r in rows:
            name = str(r.get("name"))
            v = int(r.get("notDone") or 0)
            bw = int((w - 2 * pad) * (v / maxv))
            g.rectangle([x0, y, x0 + bw, y + bar_h], fill=(255, 180, 70), outline=col_outline)
            g.text((x0 + 6, y + 2), f"{name} ({v})", font=font_sm, fill=(20, 20, 20))
            y += bar_h + 6
        return y

    wl_h = 220
    wl_data = (extras or {}).get("workload") if extras else None
    wl_y1 = draw_workload(right_x0, kpi_y1 + 20, right_w, wl_h, wl_data)
    wl_y2 = wl_y1 + wl_h

    # Footer: Evidence table
    def draw_evidence(x0: int, y0: int, w: int, h: int, ev: Optional[List[Dict[str, Any]]]) -> None:
        g.text((x0, y0 - 18), "重要エビデンス（Top）", font=font_md, fill=col_text)
        if not ev:
            return

        def _fit(text: Optional[str], width: int) -> str:
            raw = (text or "").strip()
            if not raw:
                return "-"
            candidate = raw
            ellipsis = "…"
            max_width = max(0, width - 10)
            while candidate and g.textlength(candidate, font=font_sm) > max_width:
                candidate = candidate[:-1]
            if not candidate:
                return raw[:1]
            if candidate != raw and g.textlength(candidate + ellipsis, font=font_sm) <= max_width:
                candidate = candidate + ellipsis
            return candidate

        ratios = [0.16, 0.30, 0.12, 0.10, 0.12]
        col_w = [int(w * r) for r in ratios]
        col_w.append(w - sum(col_w))
        headers = ["カテゴリ", "課題", "期限", "滞留", "担当者", "要注意ポイント"]
        due_colors = {
            "overdue": (255, 210, 210),
            "due_today": (255, 235, 210),
            "due_soon": (255, 246, 210),
            "future": (232, 246, 255),
        }
        row_h = 20
        header_h = 24
        start_x = x0 + 6
        g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
        g.rectangle([x0, y0, x0 + w, y0 + header_h], outline=col_outline, fill=(238, 238, 238))

        # header texts
        cx = start_x
        head_y = y0 + 4
        for i, head in enumerate(headers):
            g.text((cx, head_y), head, font=font_sm, fill=col_text)
            cx += col_w[i]

        y_row = y0 + header_h + 4
        max_rows = max(1, (h - header_h - 6) // row_h)
        for e in ev[:max_rows]:
            cx = start_x
            category = e.get("category") or e.get("type") or "-"
            g.text((cx, y_row), _fit(category, col_w[0]), font=font_sm, fill=col_text)
            cx += col_w[0]

            key_summary = f"{e.get('key', '')} {e.get('summary', '')}".strip()
            g.text((cx, y_row), _fit(key_summary, col_w[1]), font=font_sm, fill=col_text)
            cx += col_w[1]

            due_label_raw = e.get("dueLabel")
            if due_label_raw:
                due_text = str(due_label_raw)
            else:
                due_raw = e.get("due") or e.get("duedate")
                if isinstance(due_raw, str) and due_raw:
                    due_text = due_raw.split("T")[0]
                else:
                    due_text = "-"
            due_status = e.get("dueStatus") or ""
            cell_left = cx
            cell_right = cx + col_w[2] - 6
            fill = due_colors.get(str(due_status), (242, 242, 242))
            g.rectangle([cell_left - 2, y_row - 2, cell_right, y_row + row_h - 6], fill=fill, outline=None)
            g.text((cx, y_row), _fit(due_text, col_w[2]), font=font_sm, fill=col_text)
            cx += col_w[2]

            days = e.get("days")
            if isinstance(days, (int, float)) and days >= 0:
                days_text = f"{days:.1f}日"
            else:
                days_text = "-"
            g.text((cx, y_row), _fit(days_text, col_w[3]), font=font_sm, fill=col_text)
            cx += col_w[3]

            assignee = e.get("assignee") or "(未割り当て)"
            g.text((cx, y_row), _fit(assignee, col_w[4]), font=font_sm, fill=col_text)
            cx += col_w[4]

            reason = e.get("reason") or e.get("why") or ""
            g.text((cx, y_row), _fit(reason, col_w[5]), font=font_sm, fill=col_text)

            y_row += row_h
            if y_row + row_h > y0 + h:
                break
    ev_box_x0 = left_col_x0
    ev_box_y0 = max(tis_y1, st_y1) + 40
    ev_box_w = W - padding - ev_box_x0
    ev_box_h = 140
    evidence = (extras or {}).get("evidence") if extras else None
    draw_evidence(ev_box_x0, ev_box_y0, ev_box_w, ev_box_h, evidence)

    # (moved overlay panel below after caption lines are drawn)

    # Caption (What / So what / Next action) — compact 3 lines with data provenance
    cap_y = ev_box_y0 + ev_box_h + 16
    # sprint meta
    sprint_label = (f"スプリント {sprint_name}" if sprint_name else "スプリント")
    d0 = fmt_date(sprint_start) if sprint_start else None
    d1 = fmt_date(sprint_end) if sprint_end else None
    if d0 and d1:
        sprint_label = f"{sprint_label} ({d0}-{d1})"
    # KPI numbers if available
    kpi_data = (extras or {}).get("kpis", {}) if extras else {}
    sprint_total = int(kpi_data.get("sprintTotal", 0))
    sprint_done = int(kpi_data.get("sprintDone", 0))
    # time-in-status Review avg (days)
    review_avg = None
    tis_obj = (extras or {}).get("time_in_status") if extras else None
    try:
        per_issue = (tis_obj or {}).get("perIssue") or []
        sum_map: Dict[str, float] = {}
        cnt_map: Dict[str, int] = {}
        for row in per_issue:
            by = row.get("byStatus") or {}
            for st, days in by.items():
                d = float(days) if days is not None else 0.0
                sum_map[st] = sum_map.get(st, 0.0) + d
                cnt_map[st] = cnt_map.get(st, 0) + 1
        # find Review-like key
        if sum_map:
            # pick exact 'Review' else any containing 'Review'
            key_candidates = [k for k in sum_map.keys() if str(k).lower() == "review"] or [k for k in sum_map.keys() if "review" in str(k).lower()]
            if key_candidates:
                k0 = key_candidates[0]
                review_avg = sum_map[k0] / max(1, cnt_map.get(k0, 1))
    except Exception:
        pass
    # Build context for Gemini summary
    risks_data = (extras or {}).get("risks", {}) if extras else {}
    # Action recommendations based on data
    action_suggestions = []
    hp = int(risks_data.get("highPriorityTodo", 0))
    od = int(risks_data.get("overdue", 0))
    ds = int(risks_data.get("dueSoon", 0))
    if done_rate < target_done_rate:
        action_suggestions.append("レビュー担当の増員/並列化でスループット改善")
    if hp > 0:
        action_suggestions.append(f"高優先度未着手 {hp}件に即時担当割当")
    if od > 0:
        action_suggestions.append(f"期限超過 {od}件のエスカレーション")
    if ds > 0:
        action_suggestions.append(f"期限接近 {ds}件の優先順位再確認")
    
    # 新しいcontextキーの計算
    try:
        kpi_data = (extras or {}).get("kpis", {}) if extras else {}
        project_open_total = int(kpi_data.get("projectOpenTotal", 0))
        sprint_open = int(kpi_data.get("sprintOpen", 0))  # 直接sprintOpenを使用
        backlog_open = max(0, project_open_total - sprint_open)
        
        # Velocity関連の計算
        velocity_data = (extras or {}).get("velocity") if extras else None
        velocity_avg = 0.0
        last_velocity = 0.0
        if velocity_data:
            if "avg" in velocity_data:  # 新形式
                velocity_avg = float(velocity_data.get("avg", 0.0))
                history = velocity_data.get("history", [])
                if history:
                    last_velocity = float(history[0].get("points", 0.0))
            else:  # 旧形式
                velocity_avg = float(velocity_data.get("avgPoints", 0.0))
                points = velocity_data.get("points", [])
                if points:
                    last_velocity = float(points[0].get("points", 0.0))
        
        # 残日数の計算（スプリント終了日から）
        remaining_days = 0
        if sprint_end:
            try:
                from datetime import datetime, date
                if "T" in sprint_end:
                    end_date = datetime.fromisoformat(sprint_end.replace("Z", "+00:00")).date()
                else:
                    end_date = datetime.strptime(sprint_end, "%Y-%m-%d").date()
                today = date.today()
                remaining_days = max(0, (end_date - today).days)
            except Exception:
                remaining_days = 0
        
        # 必要な日次消化数の計算
        required_daily_burn = None
        if remaining_days > 0:
            import math
            target_remaining = max(0, int(target_done_rate * sprint_total) - sprint_done)
            required_daily_burn = math.ceil(target_remaining / remaining_days) if target_remaining > 0 else 0
        
        # 実績日次消化数（Burndown廃止により算出不可）
        actual_daily_burn = None
        
        # ボトルネック工程の特定
        bottleneck_status = None
        bottleneck_days = 0.0
        tis_data = (extras or {}).get("time_in_status") if extras else None
        if tis_data:
            per_issue = tis_data.get("perIssue", [])
            if per_issue:
                # 各ステータスの平均滞在時間を計算
                status_totals = {}
                status_counts = {}
                for issue in per_issue:
                    by_status = issue.get("byStatus", {})
                    for status, days in by_status.items():
                        try:
                            days_float = float(days)
                            status_totals[status] = status_totals.get(status, 0.0) + days_float
                            status_counts[status] = status_counts.get(status, 0) + 1
                        except Exception:
                            continue
                
                # 最も時間がかかるステータスを特定
                max_avg_days = 0.0
                for status in status_totals:
                    avg_days = status_totals[status] / max(1, status_counts[status])
                    if avg_days > max_avg_days:
                        max_avg_days = avg_days
                        bottleneck_status = status
                        bottleneck_days = avg_days
        
    except Exception:
        project_open_total = 0
        sprint_open = sprint_total - sprint_done
        backlog_open = 0
        velocity_avg = 0.0
        last_velocity = 0.0
        remaining_days = 0
        required_daily_burn = None
        actual_daily_burn = None
        bottleneck_status = None
        bottleneck_days = 0.0

    context_for_ai = {
        "sprint_label": sprint_label,
        "sprint_total": sprint_total,
        "sprint_done": sprint_done,
        "done_percent": round(done_rate * 100, 1),
        "target_percent": int(target_done_rate * 100),
        "remaining_days": remaining_days,
        "required_daily_burn": required_daily_burn,
        "actual_daily_burn": actual_daily_burn,
        "sprint_open": sprint_open,
        "backlog_open": backlog_open,
        "velocity_avg": velocity_avg,
        "last_velocity": last_velocity,
        "bottleneck_status": bottleneck_status,
        "bottleneck_days": bottleneck_days,
        "review_avg_days": review_avg,
        "overdue": int(risks_data.get("overdue", 0)),
        "due_soon": int(risks_data.get("dueSoon", 0)),
        "high_priority_unstarted": int(risks_data.get("highPriorityTodo", 0)),
        "suggested_actions": action_suggestions,
        "top_evidence": (extras or {}).get("evidence", []) or [],
        "project_open_total": project_open_total,
    }

    
    # raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    # gemini_key = _sanitize_api_key(raw_key)
    # # Gemini diagnostics
    # _log_on = (os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes"))
    # _gemini_disabled = os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes")
    # ai = None
    # existing_ai_text = extras.get("ai_full_text") if isinstance(extras, dict) else None
    # if existing_ai_text:
    #     ai = existing_ai_text
    #     if _log_on:
    #         print("- AI要約: Phase5生成テキストを再利用")
    # elif gemini_key and not _gemini_disabled and genai is not None:
    #     if GEMINI_DEBUG and _log_on:
    #         masked = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) >= 8 else "(set)"
    #         if raw_key and raw_key != gemini_key:
    #             print("- AI要約: APIキーを正規化しました（非ASCIIや余分な記号を除去）")
    #         print(f"- AI要約: キー検出 {masked}")
    #     ai = maybe_gemini_summary(gemini_key, context_for_ai)
    #     used_fallback = False
    #     if not ai:
    #         ai = _build_fallback_gemini_summary(context_for_ai)
    #         used_fallback = True if ai else False
    #     if _log_on:
    #         if ai and not used_fallback:
    #             print("- AI要約: Gemini 成功 (全文取得)")
    #         elif ai and used_fallback:
    #             print("- AI要約: Gemini 失敗→フォールバック文生成")
    #         else:
    #             print("- AI要約: Gemini 呼び出し失敗または空応答")
    #     try:
    #         if isinstance(extras, dict):
    #             extras["ai_full_text"] = ai if isinstance(ai, str) else None
    #     except Exception:
    #         pass
    # else:
    #     if _log_on:
    #         if _gemini_disabled:
    #             print("- AI要約: 無効化 (GEMINI_DISABLE)")
    #         elif not gemini_key:
    #             print("- AI要約: 未設定 (GEMINI_API_KEY/GOOGLE_API_KEY なし)")
    #         else:
    #             print("- AI要約: ライブラリ未導入 (google-generativeai)")
    #     fallback_text = _build_fallback_gemini_summary(context_for_ai)
    #     if _log_on and fallback_text:
    #         print("- AI要約: フォールバック文生成（Gemini未利用）")
    #     try:
    #         if isinstance(extras, dict):
    #             extras["ai_full_text"] = fallback_text
    #     except Exception:
    #         pass


    # Image caption remains deterministic and data-driven; AI full text goes to markdown
    what = f"What: {sprint_label} — 小タスク {total_cnt}件, 完了 {done_cnt} ({int((done_cnt/max(1,total_cnt))*100)}%). (data: sprint_subtasks_total={total_cnt}, sprint_subtasks_done={done_cnt})"
    if done_rate < target_done_rate:
        if review_avg is not None:
            sowhat = f"So what: 目標{int(target_done_rate*100)}%未達、レビュー滞留 (data: time_in_status[Review].avg={review_avg:.1f}d)"
        else:
            sowhat = f"So what: 目標{int(target_done_rate*100)}%未達"
    else:
        sowhat = "So what: ベロシティ安定、計画通り"
    hp = int(risks_data.get("highPriorityTodo", 0))
    nexta = f"Next: 高優先度未完了{hp}件の割当とレビュー担当増員"
    g.text((proj_x0, cap_y), what, font=font_sm, fill=col_text)
    g.text((proj_x0, cap_y + 16), sowhat, font=font_sm, fill=col_text)
    g.text((proj_x0, cap_y + 32), nexta, font=font_sm, fill=col_text)

    # AI summary overlay panel (wrapped text in image) — runs after caption to avoid NameError
    try:
        AI_OVERLAY_IN_IMAGE = True
        overlay_enabled = AI_OVERLAY_IN_IMAGE
        ai_text = (extras or {}).get("ai_full_text") if extras else None
        if overlay_enabled and isinstance(ai_text, str) and ai_text.strip():
            # Keep the full AI summary content without truncation
            try:
                import re as _re
                # Remove excessive whitespace but keep all content
                ai_text = _re.sub(r"\r", "", ai_text)
                ai_text = _re.sub(r"\n[ \t]*\n+", "\n", ai_text)
            except Exception:
                pass
            panel_x0 = proj_x0
            panel_w = W - padding - panel_x0
            # Place directly under evidence to guarantee space
            panel_y0 = ev_box_y0 + ev_box_h + 12
            footer_reserve = 28
            panel_h = max(72, H - padding - footer_reserve - panel_y0)
            if panel_h >= 24:
                g.rectangle([panel_x0, panel_y0, panel_x0 + panel_w, panel_y0 + panel_h], outline=col_outline, fill=(245, 245, 245))
                title = "AI要約 (Gemini)"
                g.text((panel_x0 + 8, panel_y0 + 6), title, font=font_md, fill=col_text)

                def wrap_text(text: str, max_width: int, font: ImageFont.ImageFont) -> List[str]:
                    lines: List[str] = []
                    for raw in text.split("\n"):
                        s = raw.rstrip("\r")
                        if not s:
                            lines.append("")
                            continue
                        buf = ""
                        for ch in s:
                            cand = buf + ch
                            try:
                                # 絵文字や特殊文字の描画幅を安全に計算
                                if g.textlength(cand, font=font) <= max_width:
                                    buf = cand
                                else:
                                    if buf:
                                        lines.append(buf)
                                        buf = ch
                                    else:
                                        lines.append(ch)
                                        buf = ""
                            except Exception:
                                # 文字幅計算に失敗した場合は安全に処理
                                if len(buf) > 0:
                                    lines.append(buf)
                                    buf = ch
                                else:
                                    buf = ch
                        if buf != "":
                            lines.append(buf)
                    return lines



                content_x = panel_x0 + 8
                content_y = panel_y0 + 6 + text_wh(title, font_md)[1] + 4
                content_w = panel_w - 16
                content_font = font_sm
                line_h = max(14, text_wh("A", content_font)[1])
                max_lines_by_height = max(1, (panel_h - (content_y - panel_y0) - 8) // line_h)
                try:
                    AI_OVERLAY_MAX_LINES = 18
                    max_lines_cap = int(AI_OVERLAY_MAX_LINES)
                except Exception:
                    max_lines_cap = 18
                max_lines = max(1, min(max_lines_by_height, max_lines_cap))
                total_wrapped = wrap_text(ai_text.strip(), content_w, content_font)
                # Draw within one image; truncate with ellipsis if overflow
                y = content_y
                shown = 0
                for ln in total_wrapped:
                    if shown + 1 < max_lines:
                        g.text((content_x, y), ln, font=content_font, fill=col_text)
                        y += line_h
                        shown += 1
                    else:
                        # last visible line with ellipsis
                        last = ln
                        ell = "…"
                        while last and g.textlength(last + ell, font=content_font) > content_w:
                            last = last[:-1]
                        g.text((content_x, y), (last + ell) if last else "…", font=content_font, fill=col_text)
                        break
    except Exception:
        pass

    # Footer timestamp (bottom-right)
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("生成: %Y/%m/%d %H:%M")
        tw = g.textlength(ts, font=font_sm)
        g.text((W - padding - tw, H - padding - getattr(font_sm, "size", 12)), ts, font=font_sm, fill=(120, 120, 120))
    except Exception:
        pass

    image_buffer = io.BytesIO()
    # バッファにPNG形式で画像を保存
    img.save(image_buffer, format='PNG')
    # バッファからバイトデータを取得
    image_bytes = image_buffer.getvalue()

    return image_bytes