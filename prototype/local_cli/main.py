import importlib
import os
import sys
import json
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import requests
from requests.auth import HTTPBasicAuth
# Ensure the repository root is on sys.path when executed as a script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from prototype.local_cli.lib.env_loader import ensure_env_loaded, build_process_env
    from prototype.local_cli.lib.board_selector import resolve_board_with_preferences
except ModuleNotFoundError:  # pragma: no cover - fallback when package import fails
    alt_lib_dir = Path(__file__).resolve().parent / "lib"
    if str(alt_lib_dir) not in sys.path:
        sys.path.insert(0, str(alt_lib_dir))
    from env_loader import ensure_env_loaded, build_process_env  # type: ignore
    from board_selector import resolve_board_with_preferences  # type: ignore
try:
    import google.generativeai as genai  # type: ignore
    from google.generativeai import types
except Exception:
    genai = None  # type: ignore
from textwrap import dedent


# Local configuration defaults (managed within code instead of environment variables)
BURNDOWN_UNIT = "issues"
GEMINI_DEBUG = True
GEMINI_TIMEOUT = 40.0
GEMINI_RETRIES = 2
AI_OVERLAY_IN_IMAGE = True
AI_OVERLAY_MAX_LINES = 18


ensure_env_loaded()


def _log_deployment_diagnostics() -> None:
    """Emit detailed diagnostics so Cloud Run / container logs capture environment state."""

    def _safe_print(header: str, lines: Iterable[str]) -> None:
        print(header)
        for line in lines:
            print(line)

    def _list_dir(path: Path, limit: int = 60) -> List[str]:
        rows: List[str] = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: p.name)
        except FileNotFoundError:
            return ["(not found)"]
        except PermissionError:
            return ["(permission denied)"]
        except Exception as exc:  # pragma: no cover - defensive
            return [f"(failed to list: {exc})"]
        for idx, entry in enumerate(entries):
            if idx >= limit:
                rows.append(f"... ({len(entries) - limit} more entries omitted)")
                break
            try:
                info = entry.stat()
                mode = stat.filemode(info.st_mode)
                size = info.st_size
            except Exception:
                mode = "??????????"
                size = 0
            rows.append(f"{mode} {size:>10} {entry.name}")
        if not rows:
            rows.append("(empty directory)")
        return rows

    def _dump_file(path: Path, max_bytes: int = 2000) -> List[str]:
        try:
            data = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ["(file not found)"]
        except PermissionError:
            return ["(permission denied)"]
        except Exception as exc:  # pragma: no cover - defensive
            return [f"(failed to read: {exc})"]
        if len(data) > max_bytes:
            snippet = data[:max_bytes] + "\n... (truncated)"
        else:
            snippet = data
        return snippet.splitlines() or ["(file is empty)"]

    def _log_sys_path() -> None:
        print("$ python -c 'import os,sys; ...' (captured via runtime)")
        print(f"cwd = {os.getcwd()}")
        print("--- sys.path ---")
        for entry in sys.path:
            print(entry)

    def _log_import(name: str) -> None:
        print(f"$ python -c 'import {name}' (captured via runtime)")
        try:
            module = importlib.import_module(name)
            location = getattr(module, "__file__", None) or "(namespace package)"
            print(f"import succeeded: {name} -> {location}")
        except Exception as exc:  # pragma: no cover - import diagnostics only
            print(f"import failed: {name} -> {exc}")

    print("=== deployment diagnostics: start ===")

    candidate_roots = [Path(p) for p in ("/workspace", "/app", str(REPO_ROOT))]
    for root in candidate_roots:
        _safe_print(f"$ ls -la {root}", _list_dir(root))
        _safe_print(f"$ ls -la {root / 'prototype'}", _list_dir(root / "prototype"))
        _safe_print(f"$ ls -la {root / 'prototype' / 'local_cli'}", _list_dir(root / "prototype" / "local_cli"))

    target_file = Path("/workspace/prototype/local_cli/__init__.py")
    if not target_file.exists():
        target_file = REPO_ROOT / "prototype" / "local_cli" / "__init__.py"
    _safe_print(f"$ cat {target_file}", _dump_file(target_file))

    _log_sys_path()
    _log_import("prototype")
    _log_import("prototype.local_cli")
    _log_import("prototype.local_cli.lib")

    print("=== deployment diagnostics: end ===")


_log_deployment_diagnostics()

def _sanitize_api_key(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return raw
    s = str(raw).strip().strip('"').strip("'")
    # Prefer substring starting at 'AIza' if present
    start = s.find('AIza')
    if start >= 0:
        s = s[start:]
    # Allowed chars for Google API keys (alnum, '-', '_')
    # このファイルはJiraデータを取得し、スプリントダッシュボード画像を生成するメインスクリプトです。
    # 各関数・主要処理の内部ロジックや目的を日本語コメントで詳細に記述しています。

    allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
    out = []
    for ch in s:
        if ch in allowed:
            out.append(ch)
        else:
            # stop at first invalid char to drop trailing comments like '#API'
            break
    filtered = ''.join(out)
    return filtered or None


def _run_python_script(
    script_path: str,
    args: Optional[List[str]],
    env: Dict[str, str],
) -> Tuple[subprocess.CompletedProcess[str], bool]:
    """Execute a Python script preferring module execution for reliable imports.

    Returns (completed_process, used_module_flag)."""
    script = Path(script_path).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    base_dir = Path(__file__).resolve().parent
    module_cmd: Optional[List[str]] = None
    try:
        rel = script.relative_to(repo_root)
        module_name = ".".join(rel.with_suffix("").parts)
        module_cmd = [sys.executable, "-X", "utf8", "-m", module_name]
        if args:
            module_cmd.extend(args)
    except ValueError:
        module_cmd = None

    direct_cmd = [sys.executable, "-X", "utf8", str(script)]
    if args:
        direct_cmd.extend(args)

    def _exec(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(cwd),
        )

    if module_cmd:
        proc = _exec(module_cmd, repo_root)
        if proc.returncode == 0:
            return proc, True
        print(
            f"[DEBUG] module execution failed (rc={proc.returncode}) for {script_path}, falling back to direct path",
            file=sys.stderr,
        )

    proc = _exec(direct_cmd, base_dir)
    return proc, False


def get_json_from_script(script_path: str, env_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    import traceback
    import os
    print(f"[DEBUG] get_json_from_script called with: {script_path}")
    print(f"[DEBUG] CWD: {os.getcwd()}")
    print(f"[DEBUG] ENV: JIRA_DOMAIN={os.environ.get('JIRA_DOMAIN')}, JIRA_EMAIL={os.environ.get('JIRA_EMAIL')}, JIRA_API_TOKEN={os.environ.get('JIRA_API_TOKEN')}")
    try:
        env = build_process_env()
        if env_extra:
            # .envファイルを複数パスから読み込む。Jira認証や各種設定値を環境変数としてセット。
            # ログ出力が有効な場合は読み込んだ.envパスを表示。
            env.update(env_extra)
        env["OUTPUT_JSON"] = "1"
        env["PYTHONUTF8"] = "1"
        proc, used_module = _run_python_script(script_path, None, env)
        print(f"[DEBUG] subprocess returncode={proc.returncode}")
        if used_module:
            print(f"[DEBUG] executed via module import for {script_path}")
        if proc.stdout:
            preview = proc.stdout[-1000:]
            print(f"[DEBUG] subprocess stdout (tail 1000 chars)=\n{preview}")
        if proc.stderr:
            preview_err = proc.stderr[-1000:]
            print(f"[DEBUG] subprocess stderr (tail 1000 chars)=\n{preview_err}", file=sys.stderr)

        if proc.returncode != 0:
            raise RuntimeError(f"サブプロセス終了コード異常: rc={proc.returncode}")

        stripped = proc.stdout.strip().splitlines()
        if not stripped:
            raise RuntimeError("サブプロセス出力が空です")
        line = stripped[-1]
        try:
            return json.loads(line)
        except json.JSONDecodeError as json_err:
            print("[ERROR] JSON decode failed. Full stdout follows:")
            print(proc.stdout)
            raise RuntimeError("サブプロセスのJSON出力解析に失敗しました") from json_err
    except Exception as e:
        print(f"[ERROR] データ取得エラー: {e}")
        print(f"[ERROR] script_path: {script_path}")
        print(f"[ERROR] ファイル存在: {os.path.exists(script_path)}")
        print(f"[ERROR] ファイル一覧: {os.listdir(os.path.dirname(script_path)) if os.path.exists(os.path.dirname(script_path)) else 'ディレクトリなし'}")
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        raise RuntimeError("データ取得に失敗しました") from e


def get_json_from_script_args(script_path: str, args: List[str], env_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = build_process_env()
    # Google APIキーの正規化。不要な記号やコメントを除去し、'AIza'以降の有効部分のみ抽出。
    if env_extra:
        env.update(env_extra)
    env["OUTPUT_JSON"] = "1"
    env["PYTHONUTF8"] = "1"
    proc, used_module = _run_python_script(script_path, args, env)
    print(f"[DEBUG] get_json_from_script_args returncode={proc.returncode} path={script_path} args={args}")
    if used_module:
        print(f"[DEBUG] executed via module import for {script_path}")
    if proc.stdout:
        print(f"[DEBUG] subprocess stdout (tail 1000 chars)=\n{proc.stdout[-1000:]}")
    if proc.stderr:
        print(f"[DEBUG] subprocess stderr (tail 1000 chars)=\n{proc.stderr[-1000:]}", file=sys.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"データ取得に失敗しました: {script_path} {' '.join(args)} (rc={proc.returncode})")
    stripped = proc.stdout.strip().splitlines()
    if not stripped:
        raise RuntimeError(f"サブプロセス出力が空です: {script_path} {' '.join(args)}")
    line = stripped[-1]
    try:
        return json.loads(line)
    except json.JSONDecodeError as json_err:
        print("[ERROR] JSON decode failed. Full stdout follows:")
        print(proc.stdout)
        raise RuntimeError(f"サブプロセスJSON解析に失敗しました: {script_path} {' '.join(args)}") from json_err

    # 指定Pythonスクリプトをサブプロセスで実行し、JSON出力を取得。
    # env_extraで追加環境変数を渡せる。失敗時は例外。

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


    # 引数付きPythonスクリプトをサブプロセスで実行し、JSON出力を取得。
    # env_extraで追加環境変数を渡せる。失敗時は例外。
def _format_search_error(data: Optional[Dict[str, Any]], err: str) -> str:
    if isinstance(data, dict):
        messages = data.get("errorMessages") or data.get("errors")
        if isinstance(messages, list) and messages:
            return " ".join(str(m) for m in messages if m)
        if isinstance(messages, dict) and messages:
            try:
                return json.dumps(messages, ensure_ascii=False)
            except Exception:
                return str(messages)
    return err


def search_jql_page(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    jql: str,
    fields: Optional[List[str]],
    max_results: int,
    page_token: Optional[str] = None,
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    params: Dict[str, Any] = {
        "jql": jql,
        "maxResults": max(1, min(max_results, 5000)),
    }
    if fields:
        params["fields"] = ",".join(fields)
    if page_token:
        params["pageToken"] = page_token
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/api/3/search/jql", auth, params=params)
    if code != 200 or not isinstance(data, dict):
        return code, None, _format_search_error(data, err)
    return code, data, ""


def collect_issue_count(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    jql: str,
    batch: int = 500,
) -> Tuple[int, Optional[int], str]:
    total = 0
    page_token: Optional[str] = None
    seen_tokens: set[str] = set()
    while True:
        code, data, err = search_jql_page(JIRA_DOMAIN, auth, jql, ["id"], batch, page_token)
        if code != 200 or not data:
            return code, None, err
        issues = data.get("issues") or []
        total += len(issues)
        page_token = data.get("nextPageToken")
        is_last = data.get("isLast", True)
        if not issues or not page_token or page_token in seen_tokens or is_last:
            break
        seen_tokens.add(page_token)
    return 200, total, ""


def search_issue_keys(JIRA_DOMAIN: str, auth: HTTPBasicAuth, jql: str, limit: int = 10) -> List[str]:
    keys: List[str] = []
    page_token: Optional[str] = None
    seen_tokens: set[str] = set()
    while len(keys) < limit:
        remaining = max(1, limit - len(keys))
        code, data, _ = search_jql_page(JIRA_DOMAIN, auth, jql, ["key"], remaining, page_token)
        if code != 200 or not data:
            break
        issues = data.get("issues") or []
        for it in issues:
            if "key" in it:
                keys.append(str(it.get("key")))
                if len(keys) >= limit:
                    break
        page_token = data.get("nextPageToken")
        is_last = data.get("isLast", True)
        if not page_token or page_token in seen_tokens or is_last or not issues:
            break
        seen_tokens.add(page_token)
    return keys


def resolve_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    domain = (JIRA_DOMAIN or "").rstrip("/")
    if not domain:
        return 400, None, "JIRA_DOMAIN が未設定です"

    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    def fetch(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
        return api_get(url, auth, params=params)

    return resolve_board_with_preferences(domain, fetch, project_key, board_id)


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

    # ボード情報からプロジェクトキーを推定。location.projectKey優先、なければAPIで詳細取得。

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


    # プロジェクトに紐づくボード数を取得。
def approximate_count(JIRA_DOMAIN: str, auth: HTTPBasicAuth, jql: str) -> Tuple[int, Optional[int], str]:
    return collect_issue_count(JIRA_DOMAIN, auth, jql, batch=500)


def search_count(JIRA_DOMAIN: str, auth: HTTPBasicAuth, jql: str) -> Tuple[int, Optional[int], str]:
    return collect_issue_count(JIRA_DOMAIN, auth, jql, batch=500)


    # JQLで近似件数を取得（高速）。
def agile_sprint_count(JIRA_DOMAIN: str, auth: HTTPBasicAuth, sprint_id: int, jql_filter: Optional[str] = None) -> Tuple[int, Optional[int], str]:
    """Count issues in a sprint via Agile API without fetching items.
    Uses maxResults=0 for efficiency. Optional JQL filter applies on top.
    """
    params: Dict[str, Any] = {"maxResults": 0}
    if jql_filter:
        params["jql"] = jql_filter
    try:
        resp = requests.get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{int(sprint_id)}/issue",
            auth=auth,
    # JQLで正確な件数を取得（maxResults=0で高速）。
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"
    if resp.status_code != 200:
        return resp.status_code, None, resp.text
    try:
        data = resp.json()
        total = int(data.get("total", 0))
        return 200, total, ""
    except Exception as e:
        return 200, None, f"JSON解析失敗: {e}"


def try_load_font(size: int) -> ImageFont.ImageFont:
    candidates: List[str] = []
    if os.name == "nt":
        candidates = [
            r"C:\\Windows\\Fonts\\meiryo.ttc",       # Meiryo (日本語)
            r"C:\\Windows\\Fonts\\YuGothR.ttc",      # Yu Gothic Regular
            r"C:\\Windows\\Fonts\\YuGothM.ttc",      # Yu Gothic Medium
    # Agile APIでスプリント内件数を取得。JQLフィルタも指定可。
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


def maybe_gemini_summary(api_key: Optional[str], context: Dict[str, Any]) -> Optional[str]:
    # Allow forced disable to avoid network calls
    if os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes"):
        return None
    if not api_key:
        return None
    if not genai:
        if GEMINI_DEBUG:
            print("[Gemini] google-generativeai not installed or failed to import")
        return None
    try:
        # Configuration
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        
        timeout_s = float(GEMINI_TIMEOUT)
        retries = int(GEMINI_RETRIES)
        temp = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
        top_p = float(os.getenv("GEMINI_TOP_P", "0.9"))

        # Use REST transport to avoid gRPC plugin metadata issues
        genai.configure(api_key=api_key, transport="rest")
        generation_config = {"temperature": temp, "top_p": top_p, "max_output_tokens": 640}
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
                        print(f"[Gemini] attempt {attempt+1}/{retries+1} failed: {e}")
                # backoff
                try:
                    import time as _t
                    _t.sleep(0.6 * (attempt + 1))
                except Exception:
                    pass
            # if all attempts failed
            if GEMINI_DEBUG and last_err:
                print(f"[Gemini] error on model {model_id}: {last_err}")
            return None
        # --- プロンプト（出力形式を整形） ---
        intro = dedent(
            """
            あなたは経験豊富なアジャイルコーチ兼データアナリストです。提示するコンテキスト(JSON)のみを唯一の事実情報源として分析し、
            仮定や想像の数値は用いず、[出力形式]に厳密に従って、実務に直結する洞察とアクションを提示してください。
            """
        )
        
        # 担当者名リストをcontextから抽出（例: context["assignees"]）
        assignees = context.get("assignees")
        if not assignees:
            # サブタスクや親タスクから担当者名を抽出
            names = set()
            for parent in context.get("parents", []):
                if parent.get("assignee"):
                    names.add(parent["assignee"])
                for sub in parent.get("subtasks", []):
                    if sub.get("assignee"):
                        names.add(sub["assignee"])
            assignees = sorted(names)
            context["assignees"] = assignees
        assignee_str = ", ".join(assignees) if assignees else "(担当者なし)"
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
        
        # プロンプト組み立て
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
        # Try primary then fallback model
        text = _call(model_name)

        if not text and GEMINI_DEBUG:
            print("[Gemini] empty response from both primary and fallback models")
        return text
    except Exception as e:
        if GEMINI_DEBUG:
            print(f"[Gemini] error: {e}")
        return None


def maybe_gemini_justify_evidences(
    api_key: Optional[str], evidences: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    各エビデンスの「重要な理由」をGeminiで1文生成し、{key: reason} を返す。
    - 環境変数 GEMINI_EVIDENCE_REASON=0 で無効化（既定: 有効）
    - 失敗時は空dictを返し、呼び出し元で元の理由を維持
    - 長さ上限: EVIDENCE_REASON_MAX_CHARS（既定 38 文字、超過時は省略）
    """
    try:
        if os.getenv("GEMINI_EVIDENCE_REASON", "1").lower() in ("0", "false", "no"):
            return {}
        if os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes"):
            return {}
        if not api_key or not genai:
            return {}

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
        generation_config = {"temperature": temp, "top_p": top_p, "max_output_tokens": 256}

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

        text = _call(model_name)  or None
        if not text:
            if GEMINI_DEBUG:
                print("- AI要約: evidence reasons 空応答（元の理由を使用）")
            return {}

        # JSON抽出
        result: Dict[str, str] = {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                result = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            try:
                import re as _re
                m = _re.search(r"\{[\s\S]*\}", text)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        result = {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                result = {}

        # 文字数制限を適用
        clipped: Dict[str, str] = {}
        for e in evidences:
            k = e.get("key")
            if not k:
                continue
            v = (result.get(k) or "").strip()
            if v:
                if len(v) > max_chars:
                    # keep room for ellipsis if needed
                    clipped[k] = (v[: max(1, max_chars - 1)] + "…")
                else:
                    clipped[k] = v

        if GEMINI_DEBUG and clipped:
            print(f"- AI要約: evidence reasons {len(clipped)}件 生成")
        return clipped
    except Exception as e:
        if GEMINI_DEBUG:
            print(f"[Gemini] evidence reasons error: {e}")
        return {}

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
    W, H = 1400, 980
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

    # (title drawn later after burndown)
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

    # (Removed prominent banner to avoid overlap with title area)

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
        pad_left = 10
        pad_right = 10
        pad_bottom = 10
        pad_top = 28  # 上部余白を拡大（タイトル＋ラベル分）
        pad = 10  # 予測部分で使用
        gx0, gy0 = x0, y0
        gx1, gy1 = x0 + w, y0 + h
        g.rectangle([gx0, gy0, gx1, gy1], outline=col_outline, fill=(250, 250, 250))
        # axes
        g.line([gx0 + pad_left, gy1 - pad_bottom, gx1 - pad_right, gy1 - pad_bottom], fill=col_outline)
        g.line([gx0 + pad_left, gy0 + pad_top, gx0 + pad_left, gy1 - pad_bottom], fill=col_outline)
        # scale
        # 実績データは全てのtimeSeriesデータをグラフに反映
        filtered_series = series
        rems = [float(x.get("remaining") or 0.0) for x in filtered_series]
        maxv = max(rems) if rems else 1.0
        maxv = max(maxv, 1.0)
        n = len(filtered_series)
        def _get_date(i: int) -> Optional[str]:
            d = filtered_series[i].get("date") or filtered_series[i].get("day") or filtered_series[i].get("time")
            return fmt_date(str(d)) if d else None
        def pt(idx: int, val: float) -> Tuple[int, int]:
            if n <= 1:
                t = 0.0
            else:
                t = idx / (n - 1)
            X = int((gx0 + pad_left) + t * (w - pad_left - pad_right))
            Y = int((gy1 - pad_bottom) - (val / maxv) * (h - pad_top - pad_bottom))
            return X, Y
        # ideal dotted (legend: gray dotted); compute when missing
        if not ideal and n >= 2:
            start_rem = rems[0]
            ideal = [{"remaining": start_rem * (1 - i / (n - 1))} for i in range(n)]
        # build points
        pts_i = [pt(i, float(v.get("remaining") or 0.0)) for i, v in enumerate(ideal[:n])] if ideal else []
        pts = [pt(i, float(v.get("remaining") or 0.0)) for i, v in enumerate(filtered_series)]
        # shade gap between ideal and actual (red when behind => actual above ideal)
        if pts_i and pts and len(pts) == len(pts_i):
            for i in range(1, len(pts)):
                ax0, ay0 = pts[i-1]
                ax1, ay1 = pts[i]
                ix0, iy0 = pts_i[i-1]
                ix1, iy1 = pts_i[i]
                # vertical quads per segment
                poly = [(ax0, ay0), (ax1, ay1), (ix1, iy1), (ix0, iy0)]
                # determine if behind (actual remaining > ideal -> higher Y)
                behind = ((ay0 + ay1) / 2.0) > ((iy0 + iy1) / 2.0)
                shade = (255, 200, 200, 128) if behind else (200, 240, 200, 128)
                try:
                    # use separate overlay for alpha
                    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    og = ImageDraw.Draw(overlay)
                    og.polygon([(px - gx0, py - gy0) for (px, py) in poly], fill=shade, outline=None)
                    img.paste(overlay, (gx0, gy0), overlay)
                except Exception:
                    pass
        # draw ideal dotted
        if pts_i:
            for i in range(1, len(pts_i)):
                if i % 2 == 0:
                    g.line([pts_i[i-1], pts_i[i]], fill=(120, 120, 120), width=2)
        # actual solid
        for i in range(1, len(pts)):
            g.line([pts[i-1], pts[i]], fill=(0, 120, 210), width=3)
        # Title and its bbox for collision checks
        title_pos = (gx0 + pad_left, gy0 + 2)  # 上部余白内にタイトルを描画
        title_txt = "バーンダウン（未完了タスク推移）"
        g.text(title_pos, title_txt, font=font_md, fill=col_text)
        try:
            title_bb = g.textbbox(title_pos, title_txt, font=font_md)
        except Exception:
            title_bb = (title_pos[0], title_pos[1], title_pos[0] + int(g.textlength(title_txt, font=font_md)), title_pos[1] + getattr(font_md, "size", 14))
        # axis labels (Y ticks and X dates)
        for frac in (0.0, 0.5, 1.0):
            x = gx0 + pad_left
            y = int((gy1 - pad_bottom) - frac * (h - pad_top - pad_bottom))
            g.line([x - 4, y, x + 4, y], fill=col_outline)
            val = int(round(maxv * frac))
            g.text((x - 8 - g.textlength(str(val), font=font_sm), y - 6), str(val), font=font_sm, fill=col_text)
        if n >= 2:
            labels = [0, n // 2, n - 1]
            for idx in labels:
                lx, _ = pt(idx, 0)
                dlab = _get_date(idx)
                if dlab:
                    g.text((lx - 10, gy1 - pad_bottom + 2), dlab, font=font_sm, fill=col_text)
        # latest remaining label
        try:
            if pts:
                last_val = float(filtered_series[-1].get("remaining") or 0.0)
                lx, ly = pts[-1]
                lbl = f"残: {last_val:.1f}"
                g.text((lx + 6, ly - 10), lbl, font=font_sm, fill=(0, 120, 210))
        except Exception:
            pass
        # forecast: simple linear regression on (i, remaining) -> predict zero
        try:
            import statistics as _stats
            xs = list(range(n))
            ys = rems
            # compute slope and intercept
            x_mean = sum(xs) / n
            y_mean = sum(ys) / n
            denom = sum((x - x_mean) ** 2 for x in xs) or 1.0
            slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
            intercept = y_mean - slope * x_mean
            # predict index where remaining ~ 0
            if slope < 0:
                t0 = -intercept / slope
            else:
                t0 = float('inf')
            # draw dashed forecast line from last index to t0
            if t0 != float('inf'):
                # sample M points between last and t0 (clamped)
                start = n - 1
                M = 20
                prev = None
                for j in range(M + 1):
                    t = start + (t0 - start) * (j / M)
                    yv = max(0.0, slope * t + intercept)
                    px, py = pt(int(round(t)), yv)
                    if prev is not None and j % 2 == 0:
                        g.line([prev, (px, py)], fill=(120, 0, 160), width=2)
                    prev = (px, py)
                # label predicted date and delay
                from datetime import datetime, timedelta
                # try to parse last date
                last_date_raw = series[-1].get("date") or series[-1].get("day") or series[-1].get("time")
                if last_date_raw and t0 != float('inf'):
                    try:
                        # assume daily cadence
                        base = datetime.strptime(str(series[0].get("date")), "%Y-%m-%d") if series[0].get("date") else datetime.today()
                        pred_date = base + timedelta(days=int(round(t0)))
                        status = "遅延予測" if t0 > (n - 1) else "間に合う予測"
                        pred_txt = f"予測完了: {pred_date.strftime('%Y/%m/%d')} ({status})"
                        pred_pos = (gx0 + pad + 2, gy0 + 2)
                        # Avoid overlapping title; if intersect, move below title
                        try:
                            pred_bb = g.textbbox(pred_pos, pred_txt, font=font_sm)
                        except Exception:
                            pred_bb = (pred_pos[0], pred_pos[1], pred_pos[0] + int(g.textlength(pred_txt, font=font_sm)), pred_pos[1] + getattr(font_sm, "size", 12))
                        def _inter(a, b):
                            ax0, ay0, ax1, ay1 = a
                            bx0, by0, bx1, by1 = b
                            return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)
                        if _inter(title_bb, pred_bb):
                            g.text((gx0 + pad + 2, title_bb[3] + 2), pred_txt, font=font_sm, fill=(120, 0, 160))
                        else:
                            g.text(pred_pos, pred_txt, font=font_sm, fill=(120, 0, 160))
                    except Exception:
                        alt_txt = "予測完了: 計算不可"
                        alt_pos = (gx0 + pad + 2, gy0 + 2)
                        try:
                            alt_bb = g.textbbox(alt_pos, alt_txt, font=font_sm)
                        except Exception:
                            alt_bb = (alt_pos[0], alt_pos[1], alt_pos[0] + int(g.textlength(alt_txt, font=font_sm)), alt_pos[1] + getattr(font_sm, "size", 12))
                        if not (alt_bb[1] < title_bb[3] and alt_bb[3] > title_bb[1] and alt_bb[2] > title_bb[0] and alt_bb[0] < title_bb[2]):
                            g.text(alt_pos, alt_txt, font=font_sm, fill=(120, 0, 160))
                        else:
                            g.text((gx0 + pad + 2, title_bb[3] + 2), alt_txt, font=font_sm, fill=(120, 0, 160))
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
            max_statuses = int(os.getenv("TIS_MAX_STATUSES", "6"))
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
    right_x0 = bd_box_x0
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
        # header
        # 課題列にサマリーも併記するため幅を広げる
        # 課題/担当者/ステータス/理由/リンクの比率を調整してリンク列の開始位置を左へ寄せる
        # リンクは短縮表示するが、開始位置が左に来るよう最後の2列を縮める
        # 列幅: リンクを最左・最大幅、他は最小限
        col_w = [int(w*0.40), int(w*0.18), int(w*0.12), int(w*0.18), int(w*0.12)]
        headers = ["リンク", "課題", "担当者", "ステータス", "重要な理由"]
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
        # data rows
        for e in ev:
            cx = x0 + 8
            # リンク（全表示、はみ出し時は末尾...）
            raw_link = str(e.get('link', '')).replace('https://', '').replace('http://', '')
            link = raw_link
            while g.textlength(link, font=font_sm) > (col_w[0] - 12) and len(link) > 4:
                link = link[:-1]
            if g.textlength(link, font=font_sm) > (col_w[0] - 12):
                link = link[:max(0, len(link)-3)] + '...'
            g.text((cx, y_row), link, font=font_sm, fill=col_text)
            cx += col_w[0]
            # 課題: key + summary (truncated)
            key_sum = f"{e.get('key', '')} {e.get('summary', '')[:20]}".strip()
            g.text((cx, y_row), key_sum, font=font_sm, fill=col_text)
            cx += col_w[1]
            # 担当者
            assignee = e.get('assignee', '')[:10]
            g.text((cx, y_row), assignee, font=font_sm, fill=col_text)
            cx += col_w[2]
            # ステータス
            status = e.get('status', '')[:10]
            g.text((cx, y_row), status, font=font_sm, fill=col_text)
            cx += col_w[3]
            # 重要な理由
            why = e.get('why', '')[:20]
            g.text((cx, y_row), why, font=font_sm, fill=col_text)
            cx += col_w[4]
            y_row += 16
            if y_row > y0 + h - 10:
                break  # prevent overflow
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
        
        # 実績日次消化数（直近3日の平均）
        actual_daily_burn = None
        burndown_data = (extras or {}).get("burndown") if extras else None
        if burndown_data:
            time_series = burndown_data.get("timeSeries", [])
            if len(time_series) >= 4:  # 最低4日分のデータが必要
                try:
                    burn_lookback_days = int(os.getenv("BURN_LOOKBACK_DAYS", "3"))
                    recent_series = time_series[-burn_lookback_days-1:]  # 最新N+1日分
                    if len(recent_series) >= 2:
                        total_burned = 0.0
                        for i in range(len(recent_series) - 1):
                            prev_remaining = float(recent_series[i].get("remaining", 0.0))
                            curr_remaining = float(recent_series[i+1].get("remaining", 0.0))
                            daily_burn = max(0.0, prev_remaining - curr_remaining)
                            total_burned += daily_burn
                        actual_daily_burn = total_burned / max(1, len(recent_series) - 1)
                except Exception:
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
    raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    gemini_key = _sanitize_api_key(raw_key)
    # Gemini diagnostics
    _log_on = (os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes"))
    _gemini_disabled = os.getenv("GEMINI_DISABLE", "").lower() in ("1", "true", "yes")
    ai = None
    if gemini_key and not _gemini_disabled and genai is not None:
        if GEMINI_DEBUG and _log_on:
            masked = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) >= 8 else "(set)"
            if raw_key and raw_key != gemini_key:
                print("- AI要約: APIキーを正規化しました（非ASCIIや余分な記号を除去）")
            print(f"- AI要約: キー検出 {masked}")
        ai = maybe_gemini_summary(gemini_key, context_for_ai)
        if _log_on:
            if ai:
                print("- AI要約: Gemini 成功 (全文取得)")
            else:
                print("- AI要約: Gemini 呼び出し失敗または空応答")
        try:
            if isinstance(extras, dict):
                extras["ai_full_text"] = ai if isinstance(ai, str) else None
        except Exception:
            pass
    else:
        if _log_on:
            if _gemini_disabled:
                print("- AI要約: 無効化 (GEMINI_DISABLE)")
            elif not gemini_key:
                print("- AI要約: 未設定 (GEMINI_API_KEY/GOOGLE_API_KEY なし)")
            else:
                print("- AI要約: ライブラリ未導入 (google-generativeai)")
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

    img.save(output_path, format="PNG", dpi=(150, 150))


def main() -> int:
    ensure_env_loaded()
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
    subtasks_script = str(base_dir / "queries" / "jira_list_sprint_subtasks.py")
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
        bd_args = ["--unit", BURNDOWN_UNIT]
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
    except Exception as e:
        print(f"Error getting velocity data: {e}")
        extras["velocity"] = None
    try:
        # B2. Project sprint count (all states)
        extras["project_sprint_count"] = get_json_from_script_args(str(base_dir / "queries" / "jira_count_project_sprints.py"), [])
    except Exception:
        extras["project_sprint_count"] = None
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
    kpis: Dict[str, int] = {"projectTotal": 0, "sprintTotal": 0, "sprintOpen": 0, "sprintDone": 0, "unassignedCount": 0, "overdue": 0, "dueSoon": 0, "highPriorityTodo": 0}
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
        # High priority unstarted count
        if auth and sprint and JIRA_DOMAIN:
            sid = sprint.get("id")
            pri = os.getenv("HIGH_PRIORITIES", "Highest,High")
            pri_list = ",".join([f'"{p.strip()}"' for p in pri.split(",") if p.strip()])
            jql = f"Sprint={sid} AND type in subTaskIssueTypes() AND priority in ({pri_list}) AND statusCategory = \"To Do\""
            code_c, cnt, _ = approximate_count(JIRA_DOMAIN, auth, jql)
            if not (code_c == 200 and cnt is not None):
                code_c, cnt, _ = search_count(JIRA_DOMAIN, auth, jql)
            if code_c == 200 and cnt is not None:
                risks["highPriorityTodo"] = int(cnt)
    except Exception:
        pass
    # Unassigned count
    try:
        unassigned_data = get_json_from_script_args(str(base_dir / "queries" / "jira_q_unassigned_count.py"), ["--scope", "sprint"])
        if isinstance(unassigned_data, dict):
            kpis["unassignedCount"] = int(unassigned_data.get("unassignedCount", 0))
    except Exception:
        pass
    # Enforce risks to be subtask-based (override with subtask-only JQL when possible)
    try:
        if auth and sprint and JIRA_DOMAIN:
            sid = sprint.get("id")
            # Overdue (subtasks only)
            jql_od = f"Sprint={sid} AND type in subTaskIssueTypes() AND duedate < endOfDay() AND statusCategory != \"Done\""
            code_od, cnt_od, _ = approximate_count(JIRA_DOMAIN, auth, jql_od)
            if not (code_od == 200 and cnt_od is not None):
                code_od, cnt_od, _ = search_count(JIRA_DOMAIN, auth, jql_od)
            if code_od == 200 and cnt_od is not None:
                risks["overdue"] = int(cnt_od)
                kpis["overdue"] = risks["overdue"]
            # Due soon (subtasks only)
            ds_days = os.getenv("DUE_SOON_DAYS", "7")
            jql_ds = (
                f"Sprint={sid} AND type in subTaskIssueTypes() "
                f"AND duedate >= startOfDay() AND duedate <= endOfDay(+{ds_days}d) "
                f"AND statusCategory != \"Done\""
            )
            code_ds, cnt_ds, _ = approximate_count(JIRA_DOMAIN, auth, jql_ds)
            if not (code_ds == 200 and cnt_ds is not None):
                code_ds, cnt_ds, _ = search_count(JIRA_DOMAIN, auth, jql_ds)
            if code_ds == 200 and cnt_ds is not None:
                risks["dueSoon"] = int(cnt_ds)
    except Exception:
        pass
    # projectTotal / sprintTotal counts (subtask-based for sprint)
    try:
        # Sprint totals from aggregated data (subtasks only)
        try:
            totals_obj = (data or {}).get("totals", {}) if isinstance(data, dict) else {}
            kpis["sprintTotal"] = int(totals_obj.get("subtasks", 0))
            kpis["sprintDone"] = int(totals_obj.get("done", 0))
            kpis["sprintOpen"] = int(totals_obj.get("notDone", 0))  # 未完了タスク数
        except Exception:
            pass
        if auth and JIRA_DOMAIN:
            # Prefer dedicated query script for project subtasks
            try:
                ps = get_json_from_script_args(str(base_dir / "queries" / "jira_count_project_subtasks.py"), [])
                if isinstance(ps, dict):
                    extras["project_subtask_count"] = ps
                    kpis["projectTotal"] = int(ps.get("total", 0))
                    kpis["projectOpenTotal"] = int(ps.get("openTotal", 0))  # 未完了タスク数
                    # projectAllSubtasksを保持（グラフ非表示、データのみ）
                    extras["projectAllSubtasks"] = int(ps.get("total", 0))
            except Exception:
                # Fallback to inline JQL if script fails
                proj_key = os.getenv("JIRA_PROJECT_KEY") or try_infer_project_key_from_board(JIRA_DOMAIN, auth, board) or None
                if proj_key:
                    jql_proj_sub = f"project={proj_key} AND type in subTaskIssueTypes()"
                    code_pt, cnt_pt, _ = approximate_count(JIRA_DOMAIN, auth, jql_proj_sub)
                    if not (code_pt == 200 and cnt_pt is not None):
                        code_pt, cnt_pt, _ = search_count(JIRA_DOMAIN, auth, jql_proj_sub)
                    if code_pt == 200 and cnt_pt is not None:
                        kpis["projectTotal"] = int(cnt_pt)
                        extras["projectAllSubtasks"] = int(cnt_pt)  # 全タスク数保持
                        # フォールバック：未完了数も取得
                        jql_proj_open = f"project={proj_key} AND type in subTaskIssueTypes() AND statusCategory != \"Done\""
                        code_po, cnt_po, _ = approximate_count(JIRA_DOMAIN, auth, jql_proj_open)
                        if not (code_po == 200 and cnt_po is not None):
                            code_po, cnt_po, _ = search_count(JIRA_DOMAIN, auth, jql_proj_open)
                        if code_po == 200 and cnt_po is not None:
                            kpis["projectOpenTotal"] = int(cnt_po)
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
            fields = "summary,status,assignee,priority,duedate"
            fields_list = [f.strip() for f in fields.split(",")]
            code_s, data_s, _ = search_jql_page(
                JIRA_DOMAIN,
                auth,
                f"key in ({keys_csv})",
                fields_list,
                max_results=max(1, topn),
            )
            detail_map: Dict[str, Dict[str, Any]] = {}
            if code_s == 200 and data_s:
                for iss in (data_s.get("issues") or []):
                    flds = iss.get("fields") or {}
                    detail_map[iss.get("key")] = {
                        "summary": flds.get("summary") or "",
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
                e["summary"] = det.get("summary", "")
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
        # Optionally enhance 'why' with Gemini (one-liner) while keeping safe fallback
        try:
            raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            gemini_key = _sanitize_api_key(raw_key)
            if gemini_key and ev_list:
                ai_reasons = maybe_gemini_justify_evidences(gemini_key, ev_list)
                if ai_reasons:
                    for e in ev_list:
                        k = e.get("key")
                        if k and ai_reasons.get(k):
                            e["why"] = ai_reasons[k]
        except Exception:
            pass
        extras["evidence"] = ev_list
    except Exception:
        extras["evidence"] = None

    # --- Logging (concise summaries) ---
    try:
        log_enabled = (os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes"))
        if log_enabled:
            print("[Dashboard] データ取得サマリー")
            try:
                totals = data.get("totals", {}) if isinstance(data, dict) else {}
                print(f"- 小タスク: 合計 {int(totals.get('subtasks', 0))}, 完了 {int(totals.get('done', 0))}, 未完了 {int(totals.get('subtasks', 0)) - int(totals.get('done', 0))}")
            except Exception:
                pass
            # Burndown
            bd = extras.get("burndown")
            if isinstance(bd, dict):
                try:
                    ts = bd.get("timeSeries") or []
                    first = float((ts[0] or {}).get("remaining", 0.0)) if ts else 0.0
                    last = float((ts[-1] or {}).get("remaining", 0.0)) if ts else 0.0
                    print(f"- Burndown: unit={bd.get('unit')}, total={bd.get('total')}, days={len(ts)}, 残(始→終) {first:.1f}→{last:.1f}")
                except Exception:
                    print("- Burndown: 取得失敗またはデータなし")
            else:
                print("- Burndown: データなし")
            # Velocity
            vel = extras.get("velocity")
            if isinstance(vel, dict):
                try:
                    # Handle new velocity format directly for display
                    if "history" in vel:
                        # New format: convert for display
                        history = vel.get("history", [])
                        avg_points = vel.get("avg", 0.0)
                        tail = [float(h.get("points", 0.0)) for h in history[-3:]]
                        print(f"- Velocity: avg={avg_points}, sprints={len(history)}, last={tail}")
                    else:
                        # Old format: use directly
                        pts = vel.get("points") or []
                        tail = [float(p.get("points") or 0.0) for p in pts[-3:]]
                        print(f"- Velocity: avg={vel.get('avgPoints')}, sprints={len(pts)}, last={tail}")
                except Exception as e:
                    print(f"- Velocity: 取得失敗またはデータなし ({e})")
            else:
                print("- Velocity: データなし")
            # Status counts
            sc = extras.get("status_counts")
            if isinstance(sc, dict):
                try:
                    total = int(sc.get("total", 0))
                    bys = sc.get("byStatus") or []
                    print(f"- ステータス分布: total={total}, 種類={len(bys)}")
                except Exception:
                    print("- ステータス分布: 取得失敗")
            else:
                print("- ステータス分布: データなし")
            # Time in Status
            tis = extras.get("time_in_status")
            if isinstance(tis, dict):
                try:
                    per_issue = tis.get("perIssue") or []
                    print(f"- 工程滞在時間: issues={len(per_issue)}")
                except Exception:
                    print("- 工程滞在時間: 取得失敗")
            else:
                print("- 工程滞在時間: データなし")
            # Workload
            wl = extras.get("workload")
            if isinstance(wl, dict):
                try:
                    rows = wl.get("byAssignee") or []
                    names = [str(r.get("name")) for r in rows[:3]]
                    print(f"- ワークロード: 担当者={len(rows)}, top3={names}")
                except Exception:
                    print("- ワークロード: 取得失敗")
            else:
                print("- ワークロード: データなし")
            # KPIs / Risks
            k = extras.get("kpis") or {}
            r = extras.get("risks") or {}
            try:
                print(f"- KPI: projectTotal={k.get('projectTotal')}, sprintTotal={k.get('sprintTotal')}, sprintOpen={k.get('sprintOpen')}, unassignedCount={k.get('unassignedCount')}")
                print(f"- リスク: overdue={r.get('overdue')}, dueSoon={r.get('dueSoon')}, highPriorityTodo={r.get('highPriorityTodo')}")
            except Exception:
                pass
            # Project subtasks (detailed)
            psc2 = extras.get("project_subtask_count")
            if isinstance(psc2, dict):
                try:
                    print(f"- プロジェクト(小タスク): total={psc2.get('total')}, done={psc2.get('done')}, notDone={psc2.get('notDone')}")
                except Exception:
                    pass
            # Project sprint counts
            psc = extras.get("project_sprint_count")
            if isinstance(psc, dict):
                try:
                    bys = psc.get("byState", {}) or {}
                    print(f"- プロジェクトのスプリント数: total={psc.get('total')} (active={bys.get('active')}, future={bys.get('future')}, closed={bys.get('closed')})")
                except Exception:
                    pass
            # Evidence
            ev = extras.get("evidence")
            if isinstance(ev, list):
                try:
                    keys = [e.get("key") for e in ev[:5] if e.get("key")]
                    print(f"- エビデンスTopN: {len(ev)} 件, keys={keys}")
                except Exception:
                    print("- エビデンス: 取得失敗")
            elif ev is None:
                print("- エビデンス: データなし")
    except Exception:
        # ログは失敗してもダッシュボード生成を継続
        pass

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
                overdue_keys = search_issue_keys(
                    JIRA_DOMAIN,
                    auth,
                    f"Sprint={sid} AND type in subTaskIssueTypes() AND duedate < endOfDay() AND statusCategory != \"Done\"",
                    10,
                )
            if due_soon_cnt:
                days = os.getenv("DUE_SOON_DAYS", "7")
                due_soon_keys = search_issue_keys(
                    JIRA_DOMAIN,
                    auth,
                    f"Sprint={sid} AND type in subTaskIssueTypes() AND duedate >= startOfDay() AND duedate <= endOfDay(+{days}d) AND statusCategory != \"Done\"",
                    10,
                )
            if hp_cnt:
                pri = os.getenv("HIGH_PRIORITIES", "Highest,High")
                pri_list = ",".join([f'"{p.strip()}"' for p in pri.split(",") if p.strip()])
                hp_keys = search_issue_keys(
                    JIRA_DOMAIN,
                    auth,
                    f"Sprint={sid} AND type in subTaskIssueTypes() AND priority in ({pri_list}) AND statusCategory = \"To Do\"",
                    10,
                )
        # Evidence topN
        ev_rows = extras.get("evidence", []) or []
        # Markdown compose
        md = []
        md.append(f"## 要約 | {ts}")
        md.append(f"What: {sprint_label} — {sprint_total} tasks, Done {sprint_done} ({int((sprint_done/max(1,sprint_total))*100)}%). (data: sprint_total={sprint_total}, sprint_done={sprint_done})")
        if (sprint_done / max(1, sprint_total)) < target_done_rate:
            if review_avg is not None:
                md.append(f"So what: 目標{target_done_rate*100}%未達、レビュー滞留 (data: time_in_status[Review].avg={review_avg:.1f}d)")
            else:
                md.append(f"So what: 目標{target_done_rate*100}%未達")
        else:
            md.append("So what: 目標達成ペース")
        md.append(f"Next: 高優先度未完了{hp_cnt}件の即時割当、レビュー担当の増員検討")
        md.append("")
        # If AI full summary exists, append as-is under its own section
        _ai_full = extras.get("ai_full_text") if isinstance(extras, dict) else None
        if isinstance(_ai_full, str) and _ai_full.strip():
            md.append("## AI要約 (Gemini)")
            md.append("")
            md.append(_ai_full.strip())
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
            _k = str(e.get('key') or '')
            _s = str(e.get('summary') or '').strip()
            if _s:
                ks = f"{_k} {_s}"
            else:
                ks = _k
            md.append(f"- {ks} | {e.get('status')} | {e.get('days'):.1f}d | assignee: {e.get('assignee','')} | why: {e.get('why','')} | {e.get('link')}")
        # Short actions
        md.append("")
        md.append("## 短期アクション")
        md.append("1) レビュー担当を1名追加 — 期待: Review平均を2日短縮")
        md.append("2) 期限超過の優先割当とエスカレーション")
        with open(str(base_dir / "sprint_overview_report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md))
    except Exception:
        pass
    # Write enriched tasks JSON for analysis
    try:
        enriched = {
            "sprint": {
                "name": sprint_name,
                "startDate": sprint_start,
                "endDate": sprint_end,
            },
            "parents": data.get("parents", []),
            "totals": data.get("totals", {}),
        }
        path_tasks = Path(base_dir) / "sprint_overview_tasks.json"
        with open(str(path_tasks), "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
        if os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes"):
            print(str(path_tasks))
    except Exception as e:
        if os.getenv("DASHBOARD_LOG", "1").lower() in ("1", "true", "yes"):
            print(f"[warn] enriched tasks JSON の書き出しに失敗: {e}")
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
