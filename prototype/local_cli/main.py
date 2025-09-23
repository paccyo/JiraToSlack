import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import requests
from requests.auth import HTTPBasicAuth
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # type: ignore


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    script_dir = Path(__file__).resolve().parent
    for p in [script_dir / ".env", Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def get_json_from_script(script_path: str, env_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    env["OUTPUT_JSON"] = "1"
    env["PYTHONUTF8"] = "1"
    base_dir = Path(__file__).resolve().parent
    proc = __import__("subprocess").run(
        [sys.executable, "-X", "utf8", script_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(base_dir),
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError("データ取得に失敗しました")
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


def get_json_from_script_args(script_path: str, args: List[str], env_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    env["OUTPUT_JSON"] = "1"
    env["PYTHONUTF8"] = "1"
    base_dir = Path(__file__).resolve().parent
    proc = __import__("subprocess").run(
        [sys.executable, "-X", "utf8", script_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(base_dir),
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"データ取得に失敗しました: {script_path} {' '.join(args)}")
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


def api_get(url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
    try:
        resp = requests.get(
            url,
            auth=auth,
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            return 200, resp.json(), ""
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
    else:
        return resp.status_code, None, resp.text


def search_issue_keys(JIRA_DOMAIN: str, auth: HTTPBasicAuth, jql: str, limit: int = 10) -> List[str]:
    try:
        url = f"{JIRA_DOMAIN}/rest/api/3/search"
        params = {"jql": jql, "fields": "key", "maxResults": limit}
        code, data, _ = api_get(url, auth, params=params)
        if code == 200 and data:
            return [str(it.get("key")) for it in (data.get("issues") or [])]
    except Exception:
        pass
    return []


def resolve_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    if board_id and board_id.isdigit():
        return api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}", auth)

    if board_id and not board_id.isdigit():
        params: Dict[str, Any] = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
        if code != 200 or not data:
            return code, None, f"ボード一覧取得に失敗: {err}"
        items = data.get("values", [])
        exact = [x for x in items if str(x.get("name", "")).lower() == board_id.lower()]
        if exact:
            return 200, exact[0], ""
        partial = [x for x in items if board_id.lower() in str(x.get("name", "")).lower()]
        if partial:
            return 200, partial[0], ""
        code2, data2, err2 = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50})
        if code2 == 200 and data2:
            items2 = data2.get("values", [])
            exact = [x for x in items2 if str(x.get("name", "")).lower() == board_id.lower()]
            if exact:
                return 200, exact[0], ""
            partial = [x for x in items2 if board_id.lower() in str(x.get("name", "")).lower()]
            if partial:
                return 200, partial[0], ""
        return 404, None, f"ボード名 '{board_id}' は見つかりませんでした"

    params: Dict[str, Any] = {"maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code == 200 and data and data.get("values"):
        return 200, data.get("values")[0], ""
    if code != 200:
        return code, None, f"ボード一覧取得に失敗: {err}"
    code2, data2, err2 = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50})
    if code2 == 200 and data2 and data2.get("values"):
        return 200, data2.get("values")[0], ""
    return 404, None, "ボードが見つかりませんでした"


def try_infer_project_key_from_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth, board: Dict[str, Any]) -> Optional[str]:
    loc = (board or {}).get("location") or {}
    pkey = loc.get("projectKey")
    if pkey:
        return str(pkey)
    bid = board.get("id")
    try:
        bid_int = int(bid)
    except Exception:
        return None
    code, detail, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{bid_int}", auth)
    if code == 200 and detail:
        loc = (detail or {}).get("location") or {}
        pkey = loc.get("projectKey")
        if pkey:
            return str(pkey)
    return None


def count_boards_for_project(JIRA_DOMAIN: str, auth: HTTPBasicAuth, project_key: Optional[str]) -> int:
    params: Dict[str, Any] = {"maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code == 200 and data:
        return int(len(data.get("values", []) or []))
    return 1


def count_active_sprints_for_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int) -> int:
    code, data, _ = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint",
        auth,
        params={"state": "active", "maxResults": 50},
    )
    if code == 200 and data:
        n = int(len(data.get("values", []) or []))
        return n if n > 0 else 1
    return 1


def resolve_active_sprint(JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int) -> Optional[Dict[str, Any]]:
    code, data, _ = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint",
        auth,
        params={"state": "active", "maxResults": 50},
    )
    if code == 200 and data:
        vals = data.get("values", []) or []
        if vals:
            sid = vals[0].get("id")
            scode, sdata, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sid}", auth)
            if scode == 200 and sdata:
                return sdata
            return vals[0]
    return None


def approximate_count(JIRA_DOMAIN: str, auth: HTTPBasicAuth, jql: str) -> Tuple[int, Optional[int], str]:
    url = f"{JIRA_DOMAIN}/rest/api/3/search/approximate/count"
    code, data, err = api_get(url, auth, params={"jql": jql})
    if code == 200 and isinstance(data, dict):
        try:
            cnt = int((data.get("approximate") or {}).get("total") or 0)
            return 200, cnt, ""
        except Exception:
            pass
    return code, None, err


def try_load_font(size: int) -> ImageFont.ImageFont:
    candidates: List[str] = []
    if os.name == "nt":
        candidates = [
            r"C:\\Windows\\Fonts\\meiryo.ttc",       # Meiryo (日本語)
            r"C:\\Windows\\Fonts\\YuGothR.ttc",      # Yu Gothic Regular
            r"C:\\Windows\\Fonts\\YuGothM.ttc",      # Yu Gothic Medium
            r"C:\\Windows\\Fonts\\msgothic.ttc",     # MS Gothic
            r"C:\\Windows\\Fonts\\msmincho.ttc",     # MS Mincho
            r"C:\\Windows\\Fonts\\segoeui.ttf",      # Fallback (英数字)
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
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def fmt_date(dt_str: Optional[str]) -> Optional[str]:
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


def maybe_gemini_summary(api_key: Optional[str], context: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not api_key or not genai:
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "以下のJiraスプリント状況から、3行の要約テキストを日本語で生成してください。\n"
            "要件:\n"
            "1) What: スプリント名と期間、合計/完了件数と完了率。括弧で (data: sprint_total=, sprint_done=) を付記。\n"
            "2) So what: 目標達成状況とボトルネックの推測。Top Evidenceの長期滞留や 'To Do'滞留、Review平均日数等を根拠に具体課題を名指し。括弧で (data: metric=value) を1つ以上付記。\n"
            "3) Next: 具体アクション。高優先度未着手の割当/レビュー増員など、数と対象を具体化。\n"
            "制約: 各行は1文。冗長な繰り返しは避ける。\n"
            f"コンテキスト(JSON): {json.dumps(context, ensure_ascii=False)}\n"
        )
        out = model.generate_content(prompt)
        text = (getattr(out, "text", None) or "").strip()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 3:
            return {"what": lines[0], "sowhat": lines[1], "next": lines[2]}
        if len(lines) == 2:
            return {"what": lines[0], "sowhat": lines[1], "next": "Next: 高優先度項目の割当・レビュー増員"}
        if len(lines) == 1:
            return {"what": lines[0], "sowhat": "So what: 課題のボトルネックを精査", "next": "Next: 高優先度項目の割当・レビュー増員"}
    except Exception:
        return None
    return None


def draw_png(
    output_path: str,
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
    W, H = 1400, 920
    bg = (255, 255, 255)
    img = Image.new("RGB", (W, H), bg)
    g = ImageDraw.Draw(img)

    # Colorblind-friendly palette
    col_bg = (255, 255, 255)
    col_project = (230, 230, 230)
    col_board_focus = (200, 200, 200)
    col_board_other = (215, 215, 215)
    col_sprint_focus = (210, 210, 210)
    col_sprint_other = (235, 235, 235)
    col_task_done = (27, 158, 119)     # green
    col_task_todo = (217, 95, 2)       # orange
    col_outline = (80, 80, 80)
    col_text = (40, 40, 40)
    col_grid = (220, 220, 220)
    col_benchmark = (50, 50, 200)

    padding = 20
    project_bar_h = 40
    board_bar_h = 28
    sprint_bar_h = 22
    gap = 8
    font_sm = try_load_font(12)
    font_md = try_load_font(14)
    font_lg = try_load_font(18)
    # Project bar (Header left)
    proj_x0, proj_y0 = padding, padding
    header_right_w = int(W * 0.42)
    proj_x1, proj_y1 = W - padding - header_right_w - 12, proj_y0 + project_bar_h

    # (title drawn later after burndown)
    boards_n = max(1, boards_n)
    board_gap = 2
    board_seg_w = (proj_x1 - proj_x0 - (boards_n - 1) * board_gap) // boards_n
    bx = proj_x0
    focus_board_idx = 0
    focus_board_x0 = proj_x0
    focus_board_x1 = proj_x0 + board_seg_w
    # Timestamp at top-right
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("生成: %Y/%m/%d %H:%M")
        tw = g.textlength(ts, font=font_sm)
        g.text((W - padding - tw, proj_y0 - 20), ts, font=font_sm, fill=(100, 100, 100))
    except Exception:
        pass
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
    spr_seg_w = (spr_total_w - (sprints_n - 1) * sprint_gap) // sprints_n
    sx = focus_board_x0
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

    # Summary bar (Done vs Not Done) with labels
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
    # Headline above summary bar
    headline = f"Sprint: {total_cnt} tasks | Done: {done_cnt} ({int(done_rate*100)}%)"
    g.text((focus_s_x0, sum_y0 - 18), headline, font=font_md, fill=col_text)

    # Numeric labels on segments
    def center_text(x0: int, x1: int, y: int, text: str, font: ImageFont.ImageFont, fill=col_text):
        tw, th = g.textlength(text, font=font), font.size
        cx = (x0 + x1) // 2 - int(tw // 2)
        g.text((cx, y), text, font=font, fill=fill)

    label_y = sum_y0 + 5
    center_text(focus_s_x0, focus_s_x0 + done_w, label_y, f"{done_cnt} tasks ({int(done_rate*100)}%)", font_sm, fill=(255,255,255))
    center_text(focus_s_x0 + done_w, focus_s_x1, label_y, f"{not_done_cnt} tasks ({int((1-done_rate)*100)}%)", font_sm, fill=(255,255,255))

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
    g.text((bx + 4, sum_y0 - 18), f"Target {int(target_done_rate*100)}%", font=font_sm, fill=col_benchmark)

    # Header right: Burndown sparkline
    def draw_burndown_sparkline(x0: int, y0: int, w: int, h: int, bd: Optional[Dict[str, Any]]) -> None:
        if not bd:
            g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
            g.text((x0 + 8, y0 + 8), "データなし", font=font_sm, fill=(120, 120, 120))
            return
        series = bd.get("timeSeries") or []
        ideal = bd.get("ideal") or []
        if not series:
            g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
            g.text((x0 + 8, y0 + 8), "データなし", font=font_sm, fill=(120, 120, 120))
            return
        pad = 10
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        # axes
        g.line([gx0 + pad, gy1 - pad, gx1 - pad, gy1 - pad], fill=col_outline)
        g.line([gx0 + pad, gy0 + pad, gx0 + pad, gy1 - pad], fill=col_outline)
        # scale
        rems = [float(x.get("remaining") or 0.0) for x in series]
        maxv = max(rems) if rems else 1.0
        maxv = max(maxv, 1.0)
        n = len(series)
        def _get_date(i: int) -> Optional[str]:
            d = series[i].get("date") or series[i].get("day") or series[i].get("time")
            return fmt_date(str(d)) if d else None
        def pt(idx: int, val: float) -> Tuple[int, int]:
            if n <= 1:
                t = 0.0
            else:
                t = idx / (n - 1)
            X = int((gx0 + pad) + t * (w - 2 * pad))
            Y = int((gy1 - pad) - (val / maxv) * (h - 2 * pad))
            return X, Y
        # ideal dotted (legend: gray dotted); compute when missing
        if not ideal and n >= 2:
            start_rem = rems[0]
            ideal = [{"remaining": start_rem * (1 - i / (n - 1))} for i in range(n)]
        if ideal:
            pts_i = [pt(i, float(v.get("remaining") or 0.0)) for i, v in enumerate(ideal[:n])]
            for i in range(1, len(pts_i)):
                if i % 2 == 0:
                    g.line([pts_i[i-1], pts_i[i]], fill=(120, 120, 120), width=2)
        # actual (legend: blue solid)
        pts = [pt(i, float(v.get("remaining") or 0.0)) for i, v in enumerate(series)]
        for i in range(1, len(pts)):
            g.line([pts[i-1], pts[i]], fill=(0, 120, 210), width=3)
        g.text((gx0 + pad, gy0), "バーンダウン（実績/理想）", font=font_md, fill=col_text)
        # axis labels (Y ticks and X dates)
        for frac in (0.0, 0.5, 1.0):
            x = gx0 + pad
            y = int((gy1 - pad) - frac * (h - 2 * pad))
            g.line([x - 4, y, x + 4, y], fill=col_outline)
            val = int(round(maxv * frac))
            g.text((x - 8 - g.textlength(str(val), font=font_sm), y - 6), str(val), font=font_sm, fill=col_text)
        if n >= 2:
            labels = [0, n // 2, n - 1]
            for idx in labels:
                lx, _ = pt(idx, 0)
                dlab = _get_date(idx)
                if dlab:
                    g.text((lx - 10, gy1 - pad + 2), dlab, font=font_sm, fill=col_text)
        # latest remaining label
        try:
            last_val = float(series[-1].get("remaining") or 0.0)
            lx, ly = pts[-1]
            lbl = f"残: {last_val:.1f}"
            g.text((lx + 6, ly - 10), lbl, font=font_sm, fill=(0, 120, 210))
        except Exception:
            pass

    # Position burndown and mini velocity side-by-side in header right
    bd_box_x0 = proj_x1 + 12
    bd_box_y0 = padding
    bd_box_h = 110
    bd_box_w = header_right_w // 2 - 6
    velmini_box_x0 = bd_box_x0 + bd_box_w + 12
    velmini_box_w = header_right_w - bd_box_w - 12
    bd_data = (extras or {}).get("burndown") if extras else None
    draw_burndown_sparkline(bd_box_x0, bd_box_y0, bd_box_w, bd_box_h, bd_data)
    # mini velocity chart
    def draw_velocity_mini(x0: int, y0: int, w: int, h: int, vel: Optional[Dict[str, Any]]) -> None:
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
            bh = int((v / maxv) * (h - 2 * pad))
            g.rectangle([bx, by - bh, bx + bar_w, by], fill=(80, 170, 240), outline=col_outline)
        # avg line
        if maxv > 0:
            y_avg = int((gy1 - pad) - (avg / maxv) * (h - 2 * pad))
            g.line([gx0 + pad, y_avg, gx1 - pad, y_avg], fill=(120, 0, 120), width=2)
        g.text((gx0 + pad, gy0), "Velocity", font=font_md, fill=col_text)

    vel_data_hdr = (extras or {}).get("velocity") if extras else None
    draw_velocity_mini(velmini_box_x0, bd_box_y0, velmini_box_w, bd_box_h, vel_data_hdr)
    # header metrics (Project/Sprint/Done%/Target) inside mini velocity box, top-right area
    try:
        kpis_hdr = (extras or {}).get("kpis", {}) if extras else {}
        proj_total = int(kpis_hdr.get("projectTotal", 0))
        sprint_total = int(kpis_hdr.get("sprintTotal", 0))
        sprint_done = int(kpis_hdr.get("sprintDone", 0))
        done_pct = int(round(100 * (sprint_done / max(1, sprint_total))))
        tgt_pct = int(round(100 * target_done_rate))
        line1 = f"Project:{proj_total} | Sprint:{sprint_total}"
        line2 = f"Done:{done_pct}% | Target:{tgt_pct}%"
        tx = velmini_box_x0 + 10
        ty = bd_box_y0 + 18
        g.text((tx, ty), line1, font=font_sm, fill=col_text)
        g.text((tx, ty + 16), line2, font=font_sm, fill=col_text)
    except Exception:
        pass
    # Timestamp at top-right
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("生成: %Y/%m/%d %H:%M")
        tw = g.textlength(ts, font=font_sm)
        g.text((W - padding - tw, proj_y0 - 20), ts, font=font_sm, fill=(100, 100, 100))
    except Exception:
        pass

    # Title with sprint name and date range (Japanese formatting)
    title = "スプリント"
    if sprint_name:
        title = f"スプリント {sprint_name}"
    d0 = fmt_date(sprint_start) if sprint_start else None
    d1 = fmt_date(sprint_end) if sprint_end else None
    if d0 and d1:
        title = f"{title} ({d0} - {d1})"
    g.text((proj_x0, proj_y0 - 22), title, font=font_lg, fill=col_text)

    # Annotation for high not-done ratio
    if (1 - done_rate) >= 0.4:
        ann_text = f"未完了が{int((1-done_rate)*100)}%と高い"
        g.text((focus_s_x0, sum_y1 + 36), ann_text, font=font_md, fill=(180, 20, 20))

    # Left column blocks below header: Velocity and Status Distribution
    left_col_x0 = proj_x0
    left_col_y0 = grid_y0 + 40
    left_col_w = proj_x1 - proj_x0
    # Velocity bars
    def draw_velocity(x0: int, y0: int, w: int, h: int, vel: Optional[Dict[str, Any]]) -> int:
        if not vel:
            return y0
        pts = vel.get("points") or []
        avg = float(vel.get("avgPoints") or 0.0)
        if not isinstance(pts, list):
            return y0
        g.text((x0, y0 - 18), "Velocity (last sprints)", font=font_md, fill=col_text)
        pad = 10
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
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
            target = float(os.getenv("VELOCITY_TARGET", ""))
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
            label = f"{row.get('status')} ({int(frac*100)}%)"
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
        for row in per_issue:
            by = row.get("byStatus") or {}
            for st, days in by.items():
                try:
                    d = float(days)
                except Exception:
                    d = 0.0
                sum_map[st] = sum_map.get(st, 0.0) + d
                cnt_map[st] = cnt_map.get(st, 0) + 1
                vals_map.setdefault(st, []).append(d)
        if not sum_map:
            return y0
        items = [(k, (sum_map[k] / max(1, cnt_map.get(k, 1)))) for k in sum_map.keys()]
        # sort by avg days desc
        items.sort(key=lambda x: -x[1])
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
    right_x0 = bd_box_x0
    right_y0 = bd_box_y0 + bd_box_h + 16
    right_w = header_right_w

    def draw_kpi_cards(x0: int, y0: int, w: int, h: int, kpis: Dict[str, int]) -> int:
        pad = 8
        cols = 3
        rows = 2
        gap = 8
        card_w = (w - (cols - 1) * gap)
        card_w = card_w // cols
        card_h = h
        # six KPI cards
        order = [
            ("projectTotal", "プロジェクト総件数", (40, 100, 200)),
            ("sprintTotal", "スプリント件数", (60, 160, 60)),
            ("sprintDone", "スプリント完了", (27, 158, 119)),
            ("overdue", "期限切れ", (200, 50, 50)),
            ("dueSoon", "7日以内期限", (230, 140, 0)),
            ("highPriorityTodo", "高優先度未着手", (50, 120, 50)),
        ]
        x = x0
        y = y0
        for idx, (key, title, col) in enumerate(order):
            v = int(kpis.get(key, 0))
            g.rectangle([x, y, x + card_w, y + card_h], outline=col_outline, fill=(245, 245, 245))
            g.text((x + 8, y + 6), title, font=font_sm, fill=col_text)
            g.text((x + 8, y + 28), str(v), font=try_load_font(22), fill=col)
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

    wl_h = 200
    wl_data = (extras or {}).get("workload") if extras else None
    wl_y1 = draw_workload(right_x0, kpi_y1 + 20, right_w, wl_h, wl_data)

    # Footer: Evidence table
    def draw_evidence(x0: int, y0: int, w: int, h: int, ev: Optional[List[Dict[str, Any]]]) -> None:
        g.text((x0, y0 - 18), "重要エビデンス（Top）", font=font_md, fill=col_text)
        if not ev:
            return
        # header
        col_w = [int(w*0.12), int(w*0.14), int(w*0.14), int(w*0.42), int(w*0.18)]
        headers = ["課題", "担当者", "ステータス", "重要な理由", "リンク"]
        cx = x0
        y = y0
        g.rectangle([x0, y0, x0 + w, y0 + h], outline=col_outline, fill=(250, 250, 250))
        # header row
        y_row = y + 6
        cx = x0 + 8
        for i, head in enumerate(headers):
            g.text((cx, y_row), head, font=font_sm, fill=col_text)
            cx += col_w[i]
        y_row += 20
        # rows
        for row in ev:
            cx = x0 + 8
            vals = [row.get("key"), row.get("assignee"), row.get("status"), row.get("why"), row.get("link")]
            for i, val in enumerate(vals):
                g.text((cx, y_row), str(val or ""), font=font_sm, fill=(30, 30, 30))
                cx += col_w[i]
            y_row += 20

    ev_box_x0 = left_col_x0
    ev_box_y0 = max(tis_y1, st_y1) + 40
    ev_box_w = W - padding - ev_box_x0
    ev_box_h = 140
    evidence = (extras or {}).get("evidence") if extras else None
    draw_evidence(ev_box_x0, ev_box_y0, ev_box_w, ev_box_h, evidence)

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
    sprint_total = int(kpi_data.get("sprintTotal", total_cnt))
    sprint_done = int(kpi_data.get("sprintDone", done_cnt))
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
    context_for_ai = {
        "sprint_label": sprint_label,
        "sprint_total": sprint_total,
        "sprint_done": sprint_done,
        "target_percent": int(target_done_rate * 100),
        "review_avg_days": review_avg,
        "overdue": int(risks_data.get("overdue", 0)),
        "due_soon": int(risks_data.get("dueSoon", 0)),
        "high_priority_unstarted": int(risks_data.get("highPriorityTodo", 0)),
        "top_evidence": (extras or {}).get("evidence", []) or [],
    }
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    ai = maybe_gemini_summary(gemini_key, context_for_ai) if gemini_key else None
    if ai:
        what, sowhat, nexta = ai.get("what", ""), ai.get("sowhat", ""), ai.get("next", "")
    else:
        what = f"What: {sprint_label} — {sprint_total}件, 完了 {sprint_done} ({int((sprint_done/max(1,sprint_total))*100)}%). (data: sprint_total={sprint_total}, sprint_done={sprint_done})"
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

    img.save(output_path, format="PNG", dpi=(150, 150))


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = os.getenv("JIRA_DOMAIN", "").rstrip("/")
    email = os.getenv("JIRA_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")
    boards_n = 1
    sprints_n = 1
    sprint_name = None
    sprint_start = None
    sprint_end = None
    board = None
    sprint = None
    auth: Optional[HTTPBasicAuth] = None
    if JIRA_DOMAIN and email and api_token:
        auth = HTTPBasicAuth(email, api_token)
        code_b, board, _ = resolve_board(JIRA_DOMAIN, auth)
        if code_b == 200 and board:
            proj_key = os.getenv("JIRA_PROJECT_KEY") or try_infer_project_key_from_board(JIRA_DOMAIN, auth, board) or None
            boards_n = max(1, count_boards_for_project(JIRA_DOMAIN, auth, proj_key))
            try:
                bid = int(board.get("id"))
                sprints_n = max(1, count_active_sprints_for_board(JIRA_DOMAIN, auth, bid))
                sprint = resolve_active_sprint(JIRA_DOMAIN, auth, bid)
                if sprint:
                    sprint_name = sprint.get("name")
                    sprint_start = sprint.get("startDate")
                    sprint_end = sprint.get("endDate")
            except Exception:
                sprints_n = 1
    base_dir = Path(os.getenv("OUTPUT_DIR") or Path(__file__).resolve().parent)
    subtasks_script = str(base_dir / "jira_list_sprint_subtasks.py")
    data = get_json_from_script(subtasks_script)
    out_path = str(base_dir / "sprint_overview.png")
    axis_mode = os.getenv("AXIS_MODE", "percent").lower()  # 'percent' or 'count'
    try:
        target_done_rate = float(os.getenv("TARGET_DONE_RATE", "0.8"))
    except Exception:
        target_done_rate = 0.8
    # Fetch extra metrics for dashboard
    extras: Dict[str, Any] = {}
    try:
        # A. Burndown
        bd_args = ["--unit", os.getenv("BURNDOWN_UNIT", "issues")]
        extras["burndown"] = get_json_from_script_args(str(base_dir / "queries" / "jira_q_burndown.py"), bd_args)
    except Exception:
        extras["burndown"] = None
    try:
        # B. Velocity
        vel_args: List[str] = []
        n_sprints = os.getenv("N_SPRINTS", "6")
        if n_sprints:
            vel_args += ["--n", n_sprints]
        extras["velocity"] = get_json_from_script_args(str(base_dir / "queries" / "jira_q_velocity_history.py"), vel_args)
    except Exception:
        extras["velocity"] = None
    try:
        # C. Status distribution (sprint scope, approx)
        sc_args = ["--scope", "sprint", "--mode", os.getenv("STATUS_COUNTS_MODE", "approx")]
        extras["status_counts"] = get_json_from_script_args(str(base_dir / "queries" / "jira_q_status_counts.py"), sc_args)
    except Exception:
        extras["status_counts"] = None
    try:
        # D. Time-in-Status (for evidence calc; unit days)
        tis_args = ["--scope", "sprint", "--unit", os.getenv("TIS_UNIT", "days")]
        tis = get_json_from_script_args(str(base_dir / "queries" / "jira_q_time_in_status.py"), tis_args)
        extras["time_in_status"] = tis
    except Exception:
        extras["time_in_status"] = None
    try:
        # E. Assignee workload
        wl_args = ["--scope", "sprint"]
        extras["workload"] = get_json_from_script_args(str(base_dir / "queries" / "jira_q_assignee_workload.py"), wl_args)
    except Exception:
        extras["workload"] = None
    # F. KPI cards and risks
    kpis: Dict[str, int] = {"projectTotal": 0, "sprintTotal": 0, "sprintDone": 0, "overdue": 0, "dueSoon": 0, "highPriorityTodo": 0}
    risks: Dict[str, int] = {"overdue": 0, "dueSoon": 0, "highPriorityTodo": 0}
    try:
        od_args = ["--scope", "sprint"]
        overdue = get_json_from_script_args(str(base_dir / "queries" / "jira_q_overdue_count.py"), od_args)
        risks["overdue"] = int(overdue.get("overdueCount") or 0)
        kpis["overdue"] = risks["overdue"]
    except Exception:
        pass
    try:
        ds_days = os.getenv("DUE_SOON_DAYS", "7")
        ds_args = ["--scope", "sprint", "--days", ds_days]
        due_soon = get_json_from_script_args(str(base_dir / "queries" / "jira_q_due_soon_count.py"), ds_args)
        risks["dueSoon"] = int(due_soon.get("dueSoonCount") or 0)
    except Exception:
        pass
    try:
        # High priority unstarted (approximate count via Search Approximate)
        if auth and sprint and JIRA_DOMAIN:
            sid = sprint.get("id")
            pri = os.getenv("HIGH_PRIORITIES", "Highest,High")
            # Quote priorities for JQL
            pri_list = ",".join([f'"{p.strip()}"' for p in pri.split(",") if p.strip()])
            jql = f"Sprint={sid} AND priority in ({pri_list}) AND statusCategory = \"To Do\""
            code_c, cnt, _ = approximate_count(JIRA_DOMAIN, auth, jql)
            if code_c == 200 and cnt is not None:
                risks["highPriorityTodo"] = int(cnt)
    except Exception:
        pass
    # projectTotal / sprintTotal counts
    try:
        if auth and JIRA_DOMAIN:
            # project total
            proj_key = os.getenv("JIRA_PROJECT_KEY") or try_infer_project_key_from_board(JIRA_DOMAIN, auth, board) or None
            if proj_key:
                code_pt, cnt_pt, _ = approximate_count(JIRA_DOMAIN, auth, f"project={proj_key}")
                if code_pt == 200 and cnt_pt is not None:
                    kpis["projectTotal"] = int(cnt_pt)
            # sprint total
            if sprint:
                sid = sprint.get("id")
                code_st, cnt_st, _ = approximate_count(JIRA_DOMAIN, auth, f"Sprint={sid}")
                if code_st == 200 and cnt_st is not None:
                    kpis["sprintTotal"] = int(cnt_st)
                # sprint done
                code_sd, cnt_sd, _ = approximate_count(JIRA_DOMAIN, auth, f"Sprint={sid} AND statusCategory = \"Done\"")
                if code_sd == 200 and cnt_sd is not None:
                    kpis["sprintDone"] = int(cnt_sd)
    except Exception:
        pass
    # carry risks into KPI deck as well
    kpis["overdue"] = max(kpis.get("overdue", 0), risks.get("overdue", 0))
    kpis["dueSoon"] = risks.get("dueSoon", 0)
    kpis["highPriorityTodo"] = risks.get("highPriorityTodo", 0)
    extras["kpis"] = kpis
    extras["risks"] = risks

    # G. Evidence table: Top N by longest time-in-status (days)
    try:
        ev_list: List[Dict[str, Any]] = []
        tis = extras.get("time_in_status") or {}
        unit = ((tis.get("window") or {}).get("unit") or "days")
        denom = 1.0  # already in days
        per_issue = tis.get("perIssue") or []
        for row in per_issue:
            key = row.get("key")
            by = row.get("byStatus") or {}
            days = sum(float(v) for v in by.values()) / (1.0 if unit == "days" else 24.0)
            ev_list.append({"key": key, "days": days})
        # sort and take top N
        ev_list = [e for e in ev_list if e.get("key")]
        ev_list.sort(key=lambda r: -float(r.get("days") or 0.0))
        topn = int(os.getenv("EVIDENCE_TOP_N", "5"))
        ev_list = ev_list[:topn]
        # fetch current status for these keys
        if auth and JIRA_DOMAIN and ev_list:
            keys_csv = ",".join([str(e["key"]) for e in ev_list])
            url = f"{JIRA_DOMAIN}/rest/api/3/search"
            fields = "status,assignee,priority,duedate"
            params = {"jql": f"key in ({keys_csv})", "fields": fields, "maxResults": topn}
            code_s, data_s, _ = api_get(url, auth, params=params)
            detail_map: Dict[str, Dict[str, Any]] = {}
            if code_s == 200 and data_s:
                for iss in (data_s.get("issues") or []):
                    flds = iss.get("fields") or {}
                    detail_map[iss.get("key")] = {
                        "status": ((flds.get("status") or {}).get("name") or ""),
                        "assignee": ((flds.get("assignee") or {}).get("displayName") or ""),
                        "priority": ((flds.get("priority") or {}).get("name") or ""),
                        "duedate": flds.get("duedate") or "",
                    }
            # attach status, assignee, why and link
            dom = JIRA_DOMAIN.rstrip("/")
            for e in ev_list:
                k = e.get("key")
                det = detail_map.get(k, {})
                e["status"] = det.get("status", "")
                e["assignee"] = det.get("assignee", "")
                # why heuristic
                why = []
                try:
                    dd = det.get("duedate")
                    if dd:
                        # overdue if past today
                        import datetime as _dt
                        today = _dt.date.today()
                        ddd = _dt.datetime.strptime(dd, "%Y-%m-%d").date()
                        if ddd < today:
                            why.append("overdue")
                        elif (ddd - today).days <= int(os.getenv("DUE_SOON_DAYS", "7")):
                            why.append("due soon")
                except Exception:
                    pass
                pr = str(det.get("priority", ""))
                if pr.lower() in [p.strip().lower() for p in (os.getenv("HIGH_PRIORITIES", "Highest,High").split(","))]:
                    why.append("high priority")
                if float(e.get("days") or 0) >= 5.0:
                    why.append("long stay")
                e["why"] = ", ".join(why)
                e["link"] = f"{dom}/browse/{k}"
        extras["evidence"] = ev_list
    except Exception:
        extras["evidence"] = None

    draw_png(out_path, data, boards_n, sprints_n, sprint_name, sprint_start, sprint_end, axis_mode, target_done_rate, extras)
    # Also emit a concise Markdown report with evidence and risks
    try:
        ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
        kpis = extras.get("kpis", {})
        risks = extras.get("risks", {})
        tis = extras.get("time_in_status", {}) or {}
        # compute review avg again for text
        review_avg = None
        try:
            per_issue = (tis or {}).get("perIssue") or []
            sum_map: Dict[str, float] = {}
            cnt_map: Dict[str, int] = {}
            for row in per_issue:
                by = row.get("byStatus") or {}
                for st, days in by.items():
                    d = float(days) if days is not None else 0.0
                    sum_map[st] = sum_map.get(st, 0.0) + d
                    cnt_map[st] = cnt_map.get(st, 0) + 1
            if sum_map:
                key_candidates = [k for k in sum_map.keys() if str(k).lower() == "review"] or [k for k in sum_map.keys() if "review" in str(k).lower()]
                if key_candidates:
                    k0 = key_candidates[0]
                    review_avg = sum_map[k0] / max(1, cnt_map.get(k0, 1))
        except Exception:
            pass
        sprint_label = sprint.get("name") if sprint else "Sprint"
        if sprint and sprint.get("startDate") and sprint.get("endDate"):
            sprint_label = f"{sprint_label} ({sprint.get('startDate')}—{sprint.get('endDate')})"
        sprint_total = int(kpis.get("sprintTotal", 0))
        sprint_done = int(kpis.get("sprintDone", 0))
        target_pct = int(target_done_rate * 100)
        overdue_cnt = int(risks.get("overdue", 0))
        due_soon_cnt = int(risks.get("dueSoon", 0))
        hp_cnt = int(risks.get("highPriorityTodo", 0))
        # Risk keys
        overdue_keys: List[str] = []
        due_soon_keys: List[str] = []
        hp_keys: List[str] = []
        if auth and JIRA_DOMAIN and sprint:
            sid = sprint.get("id")
            if overdue_cnt:
                overdue_keys = search_issue_keys(JIRA_DOMAIN, auth, f"Sprint={sid} AND duedate < endOfDay() AND statusCategory != \"Done\"", 10)
            if due_soon_cnt:
                days = os.getenv("DUE_SOON_DAYS", "7")
                due_soon_keys = search_issue_keys(JIRA_DOMAIN, auth, f"Sprint={sid} AND duedate >= startOfDay() AND duedate <= endOfDay(+{days}d) AND statusCategory != \"Done\"", 10)
            if hp_cnt:
                pri = os.getenv("HIGH_PRIORITIES", "Highest,High")
                pri_list = ",".join([f'"{p.strip()}"' for p in pri.split(",") if p.strip()])
                hp_keys = search_issue_keys(JIRA_DOMAIN, auth, f"Sprint={sid} AND priority in ({pri_list}) AND statusCategory = \"To Do\"", 10)
        # Evidence topN
        ev_rows = extras.get("evidence", []) or []
        # Markdown compose
        md = []
        md.append(f"## 要約 | {ts}")
        md.append(f"What: {sprint_label} — {sprint_total} tasks, Done {sprint_done} ({int((sprint_done/max(1,sprint_total))*100)}%). (data: sprint_total={sprint_total}, sprint_done={sprint_done})")
        if (sprint_done / max(1, sprint_total)) < target_done_rate:
            if review_avg is not None:
                md.append(f"So what: 目標{target_pct}%未達、レビュー滞留 (data: time_in_status[Review].avg={review_avg:.1f}d)")
            else:
                md.append(f"So what: 目標{target_pct}%未達")
        else:
            md.append("So what: 目標達成ペース")
        md.append(f"Next: 高優先度未完了{hp_cnt}件の即時割当、レビュー担当の増員検討")
        md.append("")
        md.append("## リスク")
        if overdue_cnt:
            md.append(f"- 期限超過: {overdue_cnt}件 ({', '.join(overdue_keys)}) — 優先割当要")
        if due_soon_cnt:
            md.append(f"- 7日以内期限: {due_soon_cnt}件 ({', '.join(due_soon_keys)})")
        if hp_cnt:
            md.append(f"- 高優先度未着手: {hp_cnt}件 ({', '.join(hp_keys)})")
        if not (overdue_cnt or due_soon_cnt or hp_cnt):
            md.append("- 特筆すべきリスクなし")
        md.append("")
        md.append("## エビデンス (Top)")
        for e in ev_rows:
            md.append(f"- {e.get('key')} | {e.get('status')} | {e.get('days'):.1f}d | assignee: {e.get('assignee','')} | why: {e.get('why','')} | {e.get('link')}")
        # Short actions
        md.append("")
        md.append("## 短期アクション")
        md.append("1) レビュー担当を1名追加 — 期待: Review平均を2日短縮")
        md.append("2) 期限超過の優先割当とエスカレーション")
        with open(str(base_dir / "sprint_overview_report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
    except Exception:
        pass
    # Write metrics JSON for Slack integration
    try:
        totals = data.get("totals", {})
        done_cnt = int(totals.get("done", 0))
        total_cnt = int(totals.get("subtasks", 0))
        metrics = {
            "sprint": {
                "name": sprint_name,
                "startDate": sprint_start,
                "endDate": sprint_end,
            },
            "totals": totals,
            "doneRate": (done_cnt / total_cnt) if total_cnt else None,
            "targetDoneRate": target_done_rate,
            "axis": axis_mode,
            "extrasAvailable": {k: (v is not None) for k, v in (extras or {}).items()},
        }
        with open(str(base_dir / "sprint_overview_data.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
