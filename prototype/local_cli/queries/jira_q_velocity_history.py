import os
import sys
import json
import argparse
from statistics import mean
from typing import Any, Dict, List, Optional
from pathlib import Path

# Use fully qualified import so tests can monkeypatch consistently
from prototype.local_cli.lib.jira_client import JiraClient  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Velocity history (past N sprints)")
    parser.add_argument("--n", type=int, default=int(os.getenv("N_SPRINTS", "6")))
    args = parser.parse_args()

    jc = JiraClient()

    # resolve board
    code_b, board, err_b = jc.resolve_board()
    if code_b != 200 or not board:
        print(err_b or "ボード解決に失敗", file=sys.stderr)
        return 1
    board_id = board.get("id")

    # list closed sprints
    code_s, data_s, err_s = jc.api_get(
        f"{jc.domain}/rest/agile/1.0/board/{board_id}/sprint",
        params={"state": "closed", "maxResults": args.n, "startAt": 0},
    )
    if code_s != 200 or not data_s:
        print(err_s or "スプリント一覧取得に失敗", file=sys.stderr)
        return 1
    sprints = (data_s.get("values") or [])[: args.n]

    sp_field = jc.resolve_story_points_field()

    points: List[Dict[str, Any]] = []

    for sp in sprints:
        sid = sp.get("id")
        sname = sp.get("name")
        # Done issues in sprint
        jql = f"Sprint={sid} AND statusCategory = Done"
        code_i, issues, err_i = jc.search_paginated(jql, fields=[sp_field], batch=100)
        if code_i != 200:
            print(err_i or f"スプリント {sid} の課題取得に失敗", file=sys.stderr)
            return 1
        total = 0.0
        for iss in issues:
            val = ((iss.get("fields") or {}).get(sp_field))
            try:
                total += float(val) if val is not None else 0.0
            except Exception:
                pass
        points.append({"sprintId": sid, "sprintName": sname, "points": total})

    avg = mean([p["points"] for p in points]) if points else 0.0

    out = {
        "board": {"id": board_id, "name": board.get("name")},
        "fieldId": sp_field,
        "points": points,
        "avgPoints": avg,
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
