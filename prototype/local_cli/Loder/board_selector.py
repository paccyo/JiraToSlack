import json
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

Board = Dict[str, Any]
FetchFn = Callable[[str, Optional[Dict[str, Any]]], Tuple[int, Optional[Dict[str, Any]], str]]


def describe_board(board: Board) -> Dict[str, Any]:
    if not isinstance(board, dict):
        return {}
    location = board.get("location") or {}
    project = location.get("projectKey") or location.get("name") or location.get("displayName")
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "type": board.get("type"),
        "project": project,
        "locationType": location.get("type"),
    }


def log_board_candidates(context: str, boards: List[Board]) -> None:
    try:
        payload = [describe_board(b) for b in boards if isinstance(b, dict)]
        print(f"[DEBUG] {context} candidates ({len(payload)}): {json.dumps(payload, ensure_ascii=False)}")
    except Exception as exc:
        print(f"[WARN] {context} logging failed: {exc}", file=sys.stderr)


def _board_priority(board: Board) -> Tuple[int, str]:
    board_type = str(board.get("type", "")).lower()
    if board_type == "scrum":
        return 0, str(board.get("name", ""))
    if board_type == "kanban":
        return 1, str(board.get("name", ""))
    return 2, str(board.get("name", ""))


def _extract_error_message(data: Optional[Dict[str, Any]], err: str) -> str:
    if isinstance(data, dict):
        errors = data.get("errorMessages") or data.get("errors")
        if isinstance(errors, list) and errors:
            return " ".join(str(x) for x in errors if x)
        if isinstance(errors, dict) and errors:
            return json.dumps(errors, ensure_ascii=False)
    if err:
        try:
            parsed = json.loads(err)
            if isinstance(parsed, dict):
                errors = parsed.get("errorMessages") or parsed.get("errors")
                if isinstance(errors, list) and errors:
                    return " ".join(str(x) for x in errors if x)
                if isinstance(errors, dict) and errors:
                    return json.dumps(errors, ensure_ascii=False)
        except Exception:
            pass
        return err
    return ""


def board_supports_sprints(domain: str, fetch: FetchFn, board_id: Any) -> Tuple[bool, str]:
    try:
        bid = int(board_id)
    except (TypeError, ValueError):
        return False, "ボードIDが不正です"
    url = f"{domain}/rest/agile/1.0/board/{bid}/sprint"
    code, data, err = fetch(url, {"state": "active", "maxResults": 1})
    if code == 200:
        return True, ""
    message = _extract_error_message(data, err)
    lowered = message.lower()
    if "does not support sprints" in lowered or "スプリントをサポートしません" in message:
        return False, "このボードはスプリントをサポートしません"
    if code in (401, 403):
        return False, "スプリント情報取得の権限がありません"
    if code == 404:
        return False, "ボードが見つかりません"
    return False, f"スプリント情報取得に失敗 (code={code} message={message})"


def select_sprint_capable_board(domain: str, fetch: FetchFn, boards: List[Board], context: str) -> Optional[Board]:
    ordered = sorted([b for b in boards if isinstance(b, dict)], key=_board_priority)
    for board in ordered:
        supports, reason = board_supports_sprints(domain, fetch, board.get("id"))
        if supports:
            print(f"[INFO] {context} using board: {describe_board(board)}")
            return board
        print(f"[WARN] {context} skipping board {describe_board(board)}: {reason}")
    if ordered:
        print(f"[WARN] {context} no sprint-capable boards found; falling back to first candidate: {describe_board(ordered[0])}")
        return ordered[0]
    print(f"[WARN] {context} received empty board list")
    return None


def ensure_sprint_capable_board(domain: str, fetch: FetchFn, board: Board, context: str) -> Tuple[Optional[Board], bool, str]:
    supports, reason = board_supports_sprints(domain, fetch, board.get("id"))
    if supports:
        print(f"[DEBUG] {context} confirmed board supports sprints: {describe_board(board)}")
        return board, True, ""
    print(f"[WARN] {context} board unsupported, will try fallback: {describe_board(board)} ({reason})")
    return None, False, reason


def resolve_board_with_preferences(
    domain: str,
    fetch: FetchFn,
    project_key: Optional[str],
    board_id: Optional[str],
    context: str = "resolve_board",
) -> Tuple[int, Optional[Board], str]:
    def list_boards(use_project: bool = True, max_results: int = 50) -> Tuple[int, List[Board], str]:
        params: Dict[str, Any] = {"maxResults": max_results}
        if use_project and project_key:
            params["projectKeyOrId"] = project_key
        code, data, err = fetch(f"{domain}/rest/agile/1.0/board", params)
        if code != 200 or not data:
            return code, [], err
        values = data.get("values", []) if isinstance(data, dict) else []
        return 200, list(values or []), ""

    if board_id and board_id.isdigit():
        code, data, err = fetch(f"{domain}/rest/agile/1.0/board/{board_id}", None)
        if code != 200 or not data:
            print(f"[WARN] {context}.explicit_id {board_id} failed: code={code} err={err}")
            return code, None, f"ボードID {board_id} の取得に失敗: {err}"
        selected, ok, reason = ensure_sprint_capable_board(domain, fetch, data, f"{context}.explicit_id")
        if ok and selected:
            print(f"[DEBUG] {context}.explicit_id match: {describe_board(selected)}")
            return 200, selected, ""
        fallback_code, boards, fallback_err = list_boards()
        if fallback_code == 200 and boards:
            remaining = [b for b in boards if str(b.get("id")) != board_id]
            log_board_candidates(f"{context}.explicit_id_fallback", remaining or boards)
            alt = select_sprint_capable_board(domain, fetch, remaining or boards, f"{context}.explicit_id_fallback")
            if alt:
                return 200, alt, ""
        return 409, None, reason or fallback_err or "指定ボードはスプリントを利用できません"

    if board_id and not board_id.isdigit():
        code, boards, err = list_boards()
        if code != 200:
            return code, None, f"ボード一覧取得に失敗: {err}"
        log_board_candidates(f"{context}.search_named", boards)
        lowered = board_id.lower()
        exact = [b for b in boards if str(b.get("name", "")).lower() == lowered]
        if exact:
            alt = select_sprint_capable_board(domain, fetch, exact, f"{context}.named_exact")
            if alt:
                return 200, alt, ""
        partial = [b for b in boards if lowered in str(b.get("name", "")).lower()]
        if partial:
            alt = select_sprint_capable_board(domain, fetch, partial, f"{context}.named_partial")
            if alt:
                return 200, alt, ""
        code2, boards2, err2 = list_boards(use_project=False)
        if code2 == 200 and boards2:
            log_board_candidates(f"{context}.search_named_retry", boards2)
            exact2 = [b for b in boards2 if str(b.get("name", "")).lower() == lowered]
            if exact2:
                alt = select_sprint_capable_board(domain, fetch, exact2, f"{context}.named_retry_exact")
                if alt:
                    return 200, alt, ""
            partial2 = [b for b in boards2 if lowered in str(b.get("name", "")).lower()]
            if partial2:
                alt = select_sprint_capable_board(domain, fetch, partial2, f"{context}.named_retry_partial")
                if alt:
                    return 200, alt, ""
            log_board_candidates(f"{context}.search_named_retry_nomatch", boards2)
        print(f"[WARN] {context} no match for '{board_id}'. project_key={project_key}")
        return 404, None, f"ボード名 '{board_id}' は見つかりませんでした"

    code, boards, err = list_boards()
    if code == 200 and boards:
        log_board_candidates(f"{context}.default_selection", boards)
        chosen = select_sprint_capable_board(domain, fetch, boards, f"{context}.default_selection")
        if chosen:
            return 200, chosen, ""
    if code != 200:
        return code, None, f"ボード一覧取得に失敗: {err}"
    code2, boards2, err2 = list_boards(use_project=False)
    if code2 == 200 and boards2:
        log_board_candidates(f"{context}.default_selection_retry", boards2)
        chosen = select_sprint_capable_board(domain, fetch, boards2, f"{context}.default_selection_retry")
        if chosen:
            return 200, chosen, ""
    print(f"[WARN] {context} exhausted all lookups without finding a board.")
    return 404, None, "ボードが見つかりませんでした"
