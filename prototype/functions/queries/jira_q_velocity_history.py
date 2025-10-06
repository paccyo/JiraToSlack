import os
import sys
import json
import argparse
from statistics import mean
from pathlib import Path
from typing import Any, Dict, List

try:
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "prototype").exists():
            sys.path.append(str(parent))
            break
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded  # type: ignore

# Use fully qualified import so tests can monkeypatch consistently
try:
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore
except ModuleNotFoundError:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "prototype").exists():
            sys.path.append(str(parent))
            break
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore


ensure_env_loaded()


def calc_velocity_for_sprint(jc: 'JiraClient', sprint_id: int, sp_field: str) -> Dict[str, Any]:
    """Return dict with metrics for a sprint.
    Priority of metric used for points:
      1. Sum of story points of done stories (non-subtasks) + done subtasks (1pt each if unpointed) if any > 0
      2. Count of done parent issues (stories/bugs etc) if story point sum == 0
      3. Count of done subtasks (fallback)
    """
    # 1. Story points on done issues (non-subtasks and subtasks)
    # For subtasks without story points, count as 1 point each
    jql_done_non_sub = f"Sprint={sprint_id} AND statusCategory = Done AND (type not in subTaskIssueTypes() OR parent is EMPTY)"
    code1, issues1, _ = jc.search_paginated(jql_done_non_sub, fields=[sp_field], batch=200)
    sp_total = 0.0
    if code1 == 200:
        for iss in issues1:
            try:
                val = (iss.get("fields") or {}).get(sp_field)
                if val is not None:
                    sp_total += float(val)
            except Exception:
                pass

    # Also include done subtasks, counting unpointed ones as 1 point each
    jql_done_sub = f"Sprint={sprint_id} AND statusCategory = Done AND type in subTaskIssueTypes()"
    code1_sub, issues1_sub, _ = jc.search_paginated(jql_done_sub, fields=[sp_field], batch=200)
    if code1_sub == 200:
        for iss in issues1_sub:
            try:
                val = (iss.get("fields") or {}).get(sp_field)
                if val is not None and val > 0:
                    sp_total += float(val)
                else:
                    # Subtask without story points: count as 1
                    sp_total += 1.0
            except Exception:
                # If there's an error parsing, count as 1 for subtasks
                sp_total += 1.0

    metric_type = "story_points"
    value = sp_total

    # If we have any story points (including from subtasks), use that
    if sp_total > 0.0:
        metric_type = "story_points"
        value = sp_total
    elif sp_total <= 0.0:
        # 2. Count of done parent issues (exclude subtasks)
        jql_done_parents = f"Sprint={sprint_id} AND statusCategory = Done AND (type not in subTaskIssueTypes() OR parent is EMPTY)"
        code2, issues2, _ = jc.search_paginated(jql_done_parents, fields=["id"], batch=200)
        if code2 == 200:
            cnt_parent = len(issues2)
        else:
            cnt_parent = 0
        if cnt_parent > 0:
            metric_type = "parent_issues"
            value = float(cnt_parent)
        else:
            # 3. Fallback: done subtasks count
            jql_done_sub = f"Sprint={sprint_id} AND type in subTaskIssueTypes() AND statusCategory = Done"
            code3, issues3, _ = jc.search_paginated(jql_done_sub, fields=["id"], batch=200)
            cnt_sub = len(issues3) if code3 == 200 else 0
            metric_type = "subtasks_done"
            value = float(cnt_sub)

    return {"metric": metric_type, "value": value, "storyPoints": sp_total}


def main() -> int:
    parser = argparse.ArgumentParser(description="Velocity based on closed sprints with fallback metrics")
    parser.add_argument("--n", type=int, default=int(os.getenv("VELOCITY_SPRINT_HISTORY", os.getenv("N_SPRINTS", "5"))), help="Number of past closed sprints")
    args = parser.parse_args()

    jc = JiraClient()
    code_b, board, err_b = jc.resolve_board()
    if code_b != 200 or not board:
        print(err_b or "ボード解決に失敗", file=sys.stderr)
        return 1
    board_id = board.get("id")

    # Closed sprints
    code_s, data_s, err_s = jc.api_get(
        f"{jc.domain}/rest/agile/1.0/board/{board_id}/sprint",
        params={"state": "closed", "maxResults": args.n, "startAt": 0},
    )
    if code_s != 200 or not data_s:
        print(err_s or "スプリント一覧取得に失敗", file=sys.stderr)
        return 1
    sprints = (data_s.get("values") or [])[: args.n]

    sp_field = jc.resolve_story_points_field()

    history: List[Dict[str, Any]] = []
    for sp in sprints:
        sid = int(sp.get("id"))
        metrics = calc_velocity_for_sprint(jc, sid, sp_field)
        history.append({
            "id": sid,
            "name": sp.get("name"),
            "start": sp.get("startDate"),
            "end": sp.get("endDate"),
            "points": metrics["value"],
            "metric": metrics["metric"],
            "storyPointsRaw": metrics["storyPoints"],
        })

    avg = mean([h["points"] for h in history]) if history else 0.0
    last_points = history[0]["points"] if history else 0.0  # list already limited to n recent

    out = {
        "board": {"id": board_id, "name": board.get("name")},
        "history": history,
        "avg": avg,
        "last_points": last_points,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
