import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth


def load_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return value


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    script_dir = Path(__file__).resolve().parent
    # Prefer the local_cli/.env over workspace root
    candidates = [
        script_dir.parent / ".env",  # c:/.../prototype/local_cli/.env
        script_dir / ".env",         # c:/.../prototype/local_cli/queries/.env (fallback)
        Path.cwd() / ".env",          # current working dir
        Path(__file__).resolve().parents[2] / ".env",  # repo root
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)


def api_get(
    url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None
) -> Tuple[int, Optional[Dict[str, Any]], str]:
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


def api_post(
    url: str, auth: HTTPBasicAuth, json_body: Dict[str, Any]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    try:
        resp = requests.post(
            url,
            json=json_body,
            auth=auth,
            headers={"Accept": "application/json"},
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


def resolve_story_points_field(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth
) -> Optional[str]:
    sp_env = os.getenv("JIRA_STORY_POINTS_FIELD")
    if sp_env:
        return sp_env

    try:
        resp = requests.get(
            f"{JIRA_DOMAIN}/rest/api/3/field",
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException:
        return "customfield_10016"

    if resp.status_code != 200:
        return "customfield_10016"
    try:
        fields = resp.json()
    except json.JSONDecodeError:
        return "customfield_10016"

    chosen: Optional[str] = None
    if isinstance(fields, list):
        for f in fields:
            schema = f.get("schema") or {}
            if schema.get("custom") == "com.pyxis.greenhopper.jira:jsw-story-points":
                chosen = str(f.get("id"))
                break
        if not chosen:
            candidates: List[Dict[str, Any]] = []
            for f in fields:
                name = str(f.get("name", ""))
                if name and ("story point" in name.lower() or "ストーリーポイント" in name):
                    candidates.append(f)

            def priority(f: Dict[str, Any]) -> int:
                n = str(f.get("name", "")).lower()
                if "story points" in n:
                    return 0
                if "story point estimate" in n:
                    return 1
                return 2

            if candidates:
                candidates.sort(key=priority)
                chosen = str(candidates[0].get("id"))

        if not chosen:
            for f in fields:
                if str(f.get("id")) == "customfield_10016":
                    chosen = "customfield_10016"
                    break

    return chosen or "customfield_10016"


def resolve_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    if board_id and board_id.isdigit():
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"ボードID {board_id} の取得に失敗: {err}"

    if board_id and not board_id.isdigit():
        params = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        code_b, data_b, err_b = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
        items: List[Dict[str, Any]] = []
        if code_b == 200 and data_b:
            items.extend(data_b.get("values", []))
        else:
            return code_b, None, f"ボード一覧取得に失敗: {err_b}"

        exact = [x for x in items if str(x.get("name", "")).lower() == board_id.lower()]
        if exact:
            return 200, exact[0], ""
        partial = [x for x in items if board_id.lower() in str(x.get("name", "")).lower()]
        if partial:
            return 200, partial[0], ""

        code_b2, data_b2, err_b2 = api_get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50}
        )
        if code_b2 == 200 and data_b2:
            items2 = data_b2.get("values", [])
            exact = [x for x in items2 if str(x.get("name", "")).lower() == board_id.lower()]
            if exact:
                return 200, exact[0], ""
            partial = [x for x in items2 if board_id.lower() in str(x.get("name", "")).lower()]
            if partial:
                return 200, partial[0], ""
        else:
            return code_b2, None, f"ボード一覧取得に失敗: {err_b2}"
        return 404, None, f"ボード名 '{board_id}' は見つかりませんでした"

    params = {"maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code == 200 and data and data.get("values"):
        return 200, data.get("values")[0], ""

    code2, data2, err2 = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50}
    )
    if code2 == 200 and data2 and data2.get("values"):
        return 200, data2.get("values")[0], ""
    if code2 != 200:
        return code2, None, f"ボード一覧取得に失敗: {err2}"
    return 404, None, "ボードが見つかりませんでした"


def resolve_active_sprint(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"スプリントID {sprint_id_env} の取得に失敗: {err}"

    params = {"state": "active", "maxResults": 50}
    code, data, err = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params
    )
    if code != 200 or not data:
        return code, None, f"アクティブスプリントの取得に失敗: {err}"

    sprints = data.get("values", [])
    if not sprints:
        return 404, None, "アクティブなスプリントが見つかりません"
    return 200, sprints[0], ""


def search_issues_jql(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    jql: str,
    fields: Optional[List[str]] = None,
    batch_size: int = 100,
) -> Tuple[int, Optional[List[Dict[str, Any]]], str]:
    start_at = 0
    all_issues: List[Dict[str, Any]] = []
    fields = fields or ["summary", "issuetype", "status", "subtasks", "assignee"]

    while True:
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": start_at,
            "maxResults": batch_size,
        }
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/api/3/search", auth, params=params)
        if code != 200 or not data:
            body = {
                "jql": jql,
                "fields": fields,
                "startAt": start_at,
                "maxResults": batch_size,
            }
            code2, data2, err2 = api_post(f"{JIRA_DOMAIN}/rest/api/3/search", auth, body)
            if code2 != 200 or not data2:
                return code, None, f"JQL検索に失敗: {err or err2}"
            data = data2

        issues = data.get("issues") if isinstance(data, dict) else None
        if issues is None and isinstance(data, dict):
            issues = data.get("results") or data.get("data")
        if issues is None:
            return 200, [], ""

        total = int(data.get("total", len(issues))) if isinstance(data, dict) else len(issues)
        all_issues.extend(issues)

        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return 200, all_issues, ""


def agile_list_issues_in_sprint(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    sprint_id: int,
    project_key: Optional[str],
    fields: Optional[List[str]] = None,
    batch_size: int = 100,
) -> Tuple[int, Optional[List[Dict[str, Any]]], str]:
    start_at = 0
    all_issues: List[Dict[str, Any]] = []
    fields = fields or ["summary", "issuetype", "status", "subtasks", "assignee"]
    jql_parts: List[str] = ["type not in subTaskIssueTypes()"]
    if project_key:
        jql_parts.insert(0, f"project={project_key}")
    jql = " AND ".join(jql_parts)

    while True:
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": start_at,
            "maxResults": batch_size,
        }
        code, data, err = api_get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id}/issue", auth, params=params
        )
        if code != 200 or not data:
            return code, None, f"スプリント {sprint_id} の課題取得に失敗: {err}"

        issues = data.get("issues", [])
        total = int(data.get("total", 0))
        all_issues.extend(issues)

        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return 200, all_issues, ""


def _normalize_status_name(s: str) -> str:
    """Normalize a Jira status name for robust matching.
    - lowercases
    - replaces spaces/hyphens with underscores
    - maps common variants and Japanese synonyms to canonical keys
    """
    ss = (s or "").strip().lower()
    if not ss:
        return ss
    ss = ss.replace(" ", "_").replace("-", "_")
    # canonicalization map
    synonyms = {
        # in progress variants
        "in_progress": "in_progress",
        "inprogress": "in_progress",
        "doing": "in_progress",
        "進行中": "in_progress",
        "作業中": "in_progress",
        "対応中": "in_progress",
        # review/qa
        "in_review": "in_review",
        "review": "in_review",
        "レビュー": "in_review",
        "qa": "qa",
        # todo/new
        "to_do": "to_do",
        "todo": "to_do",
        "new": "to_do",
        "未着手": "to_do",
        # done/closed/resolved
        "done": "done",
        "closed": "done",
        "resolved": "done",
        "完了": "done",
    }
    return synonyms.get(ss, ss)


def _extract_times_from_changelog(changelog: Dict[str, Any], start_names: List[str], done_names: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (startedAt, completedAt) based on first status transition into start_names and into done_names.
    Times are ISO strings from history.created. If not found, returns (None, None).
    Uses normalized status names for robust matching (spaces/hyphens/case/Japanese)."""
    if not changelog:
        return None, None
    histories = changelog.get("histories") or []
    # Sort ascending by created
    try:
        histories.sort(key=lambda h: h.get("created") or "")
    except Exception:
        pass
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    sset = {_normalize_status_name(s) for s in start_names}
    dset = {_normalize_status_name(s) for s in done_names}
    for h in histories:
        items = h.get("items") or []
        for it in items:
            if (it.get("field") or "").lower() != "status":
                continue
            to_name = str(it.get("toString") or "").strip()
            lto = _normalize_status_name(to_name)
            ts = h.get("created")  # ISO-8601 string
            if not started_at and lto in sset:
                started_at = ts
            if not completed_at and lto in dset:
                completed_at = ts
        if started_at and completed_at:
            break
    return started_at, completed_at


def ensure_subtask_fields(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    subtask: Dict[str, Any],
    sp_field_id: Optional[str],
    include_changelog: bool,
    start_status_names: List[str],
    done_status_names: List[str],
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    fields = subtask.get("fields") or {}
    need_fetch = False
    # Check if required fields exist
    required = ["summary", "status", "assignee", "issuetype", "created", "resolutiondate"]
    for k in required:
        if fields.get(k) is None:
            need_fetch = True
            break
    if sp_field_id and sp_field_id not in fields:
        need_fetch = True

    sub_id = subtask.get("id") or subtask.get("key")
    if not sub_id:
        return 400, None, "サブタスクのID/Keyが取得できませんでした"

    data: Optional[Dict[str, Any]] = None
    if need_fetch or include_changelog:
        query_fields = [
            "summary",
            "status",
            "assignee",
            "issuetype",
            "created",
            "resolutiondate",
        ]
        if sp_field_id:
            query_fields.append(sp_field_id)
        params = {"fields": ",".join(query_fields)}
        if include_changelog:
            params["expand"] = "changelog"
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/api/3/issue/{sub_id}", auth, params=params)
        if code != 200 or not data:
            return code, None, f"サブタスク詳細取得に失敗: {err}"
        subtask["fields"] = fields = fields or {}
        fds = (data.get("fields") or {})
        fields.update({
            "summary": fds.get("summary"),
            "status": fds.get("status"),
            "assignee": fds.get("assignee"),
            "issuetype": fds.get("issuetype"),
            "created": fds.get("created"),
            "resolutiondate": fds.get("resolutiondate"),
        })
        if sp_field_id and sp_field_id in fds:
            fields[sp_field_id] = fds.get(sp_field_id)
        # Infer started/completed from changelog
        if include_changelog and isinstance(data.get("changelog"), dict):
            started_at, completed_at = _extract_times_from_changelog(data.get("changelog") or {}, start_status_names, done_status_names)
            # Attach under synthetic container to avoid clashing
            fields.setdefault("_times", {})
            fields["_times"].update({"startedAt": started_at, "completedAt": completed_at})

    return 200, subtask, ""


def is_done(status_field: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not status_field:
        return None
    cat = (status_field or {}).get("statusCategory") or {}
    key = cat.get("key")
    if key == "done":
        return True
    if key in {"new", "indeterminate"}:
        return False
    return None


def try_infer_project_key_from_board(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board: Dict[str, Any]
) -> Optional[str]:
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


def list_and_print_subtasks(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    issues_source: List[Dict[str, Any]] | None,
    header: str,
    sp_field_id: Optional[str],
) -> int:
    issues = issues_source or []

    output_json = os.getenv("OUTPUT_JSON") == "1"
    if not output_json:
        print(header)
        print("")

    total_parents = 0
    total_subtasks = 0
    total_done = 0
    agg_by_assignee: Dict[str, Dict[str, Any]] = {}

    results: List[Dict[str, Any]] = []
    # env knobs
    include_changelog = (os.getenv("INCLUDE_CHANGELOG", "1").lower() in ("1", "true", "yes"))
    start_names = [s.strip() for s in os.getenv("START_STATUS_NAMES", "In Progress,IN_progress,In Review,Doing,進行中,作業中,対応中").split(",") if s.strip()]
    done_names = [s.strip() for s in os.getenv("DONE_STATUS_NAMES", "Done,Closed,Resolved").split(",") if s.strip()]

    for issue in issues:
        fields = issue.get("fields", {})
        subtasks = fields.get("subtasks", []) or []
        if not subtasks:
            continue

        total_parents += 1
        parent_key = issue.get("key")
        parent_summary = fields.get("summary")
        assignee = (fields.get("assignee") or {}).get("displayName")
        if not output_json:
            print(f"親タスク {parent_key} - {parent_summary}{' / 担当: ' + assignee if assignee else ''}")
        parent_entry: Dict[str, Any] = {
            "parentKey": parent_key,
            "parentSummary": parent_summary,
            "assignee": assignee,
            "subtasks": [],
        }

        parent_done = 0
        for sub in subtasks:
            code_s, sub_full, err_s = ensure_subtask_fields(
                JIRA_DOMAIN,
                auth,
                sub,
                sp_field_id,
                include_changelog,
                start_names,
                done_names,
            )
            if code_s != 200 or not sub_full:
                print(f"  - {sub.get('key') or sub.get('id')} 取得失敗: {err_s}")
                continue

            sub_key = sub_full.get("key") or sub_full.get("id")
            sub_fields = sub_full.get("fields", {})
            sub_summary = sub_fields.get("summary")
            status = sub_fields.get("status")
            sub_assignee = (sub_fields.get("assignee") or {}).get("displayName") or assignee
            sub_type = (sub_fields.get("issuetype") or {}).get("name")
            created = sub_fields.get("created")
            resolutiondate = sub_fields.get("resolutiondate")
            times = sub_fields.get("_times") or {}
            started_at = times.get("startedAt")
            completed_at = times.get("completedAt") or resolutiondate
            sp_value: Optional[float] = None
            if sp_field_id:
                sp_raw = sub_fields.get(sp_field_id)
                if isinstance(sp_raw, (int, float)):
                    sp_value = float(sp_raw)
                else:
                    sp_value = None
            if sp_value is None:
                sp_value = 1.0
            done_flag = is_done(status)

            status_name = (status or {}).get("name") or "(不明)"
            badge = "Done" if done_flag else ("Not Done" if done_flag is False else "Unknown")
            if not output_json:
                extra = []
                if sub_assignee:
                    extra.append(f"担当:{sub_assignee}")
                if sub_type:
                    extra.append(f"タイプ:{sub_type}")
                if created:
                    extra.append(f"作成:{created}")
                if started_at:
                    extra.append(f"開始:{started_at}")
                if completed_at:
                    extra.append(f"完了:{completed_at}")
                extra_txt = (" | " + ", ".join(extra)) if extra else ""
                print(f"  - [{badge}] {sub_key} - {sub_summary} (Status: {status_name}, SP: {sp_value:g}){extra_txt}")
            parent_entry["subtasks"].append({
                "key": sub_key,
                "summary": sub_summary,
                "status": status_name,
                "done": bool(done_flag) if done_flag is not None else None,
                "storyPoints": sp_value,
                "assignee": sub_assignee,
                "typeName": sub_type,
                "created": created,
                "startedAt": started_at,
                "completedAt": completed_at,
            })

            who = sub_assignee or assignee or "(未割り当て)"
            cur = agg_by_assignee.get(who) or {"assignee": who, "subtasks": 0, "done": 0, "storyPoints": 0.0}
            cur["subtasks"] += 1
            cur["storyPoints"] += float(sp_value)
            if done_flag:
                cur["done"] += 1
            agg_by_assignee[who] = cur

            total_subtasks += 1
            if done_flag:
                total_done += 1
                parent_done += 1

        if not output_json:
            print(f"    小タスク完了: {parent_done}/{len(subtasks)}")
            print("")
        parent_entry["doneCount"] = parent_done
        parent_entry["totalSubtasks"] = len(subtasks)
        results.append(parent_entry)

    if output_json:
        payload = {
            "header": header,
            "parents": results,
            "totals": {
                "parents": total_parents,
                "subtasks": total_subtasks,
                "done": total_done,
                "notDone": total_subtasks - total_done,
            },
            "aggregates": {
                "assignees": sorted(list(agg_by_assignee.values()), key=lambda x: (-x["storyPoints"], x["assignee"]))
            },
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if total_subtasks == 0:
            print("小タスクは見つかりませんでした。")
        else:
            print("合計")
            print(f"  親タスク数: {total_parents}")
            print(f"  小タスク数: {total_subtasks}")
            print(f"  完了: {total_done} / 未完了: {total_subtasks - total_done}")
            if agg_by_assignee:
                print("\n担当者別 小タスク数 / 完了数 / SP合計")
                for item in sorted(agg_by_assignee.values(), key=lambda x: (-x["storyPoints"], x["assignee"])):
                    print(f"  - {item['assignee']}: {item['subtasks']} 件 / 完了 {item['done']} 件 / SP {item['storyPoints']:.1f}")

    return 0


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = load_env("JIRA_DOMAIN").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, api_token)

    sp_field_id = resolve_story_points_field(JIRA_DOMAIN, auth)
    if not sp_field_id:
        print("Story Points フィールドが見つかりませんでした。未設定扱い(=1)で出力します。", file=sys.stderr)

    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        header = f"スプリント '{sprint_id_env}' 内の小タスク一覧"
        code, sprint_info, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and sprint_info:
            header = f"スプリント '{sprint_info.get('name')}' 内の小タスク一覧"
        code_i, issues_i, err_i = agile_list_issues_in_sprint(
            JIRA_DOMAIN, auth, int(sprint_id_env), project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
        )
        if code_i != 200 or issues_i is None:
            print(err_i, file=sys.stderr)
            return 1
        return list_and_print_subtasks(JIRA_DOMAIN, auth, issues_i, header, sp_field_id)

    code_b, board, err_b = resolve_board(JIRA_DOMAIN, auth)
    if code_b != 200 or not board:
        print(err_b, file=sys.stderr)
        return 1

    board_id = int(board.get("id"))
    board_name = board.get("name")
    print(f"使用ボード: {board_name} (id={board_id})")

    if not project_key:
        inferred = try_infer_project_key_from_board(JIRA_DOMAIN, auth, board)
        if inferred:
            project_key = inferred
            print(f"推測したプロジェクトキー: {project_key}")

    code_s, sprint, err_s = resolve_active_sprint(JIRA_DOMAIN, auth, board_id)
    if code_s != 200 or not sprint:
        print(err_s, file=sys.stderr)
        return 1

    sprint_id = int(sprint.get("id"))
    sprint_name = sprint.get("name")

    code_i, issues_i, err_i = agile_list_issues_in_sprint(
        JIRA_DOMAIN, auth, sprint_id, project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
    )
    if code_i != 200 or issues_i is None:
        print(err_i, file=sys.stderr)
        return 1

    header = f"ボード '{board_name}' のアクティブスプリント '{sprint_name}' 内の小タスク一覧"
    return list_and_print_subtasks(JIRA_DOMAIN, auth, issues_i, header, sp_field_id)


if __name__ == "__main__":
    sys.exit(main())
