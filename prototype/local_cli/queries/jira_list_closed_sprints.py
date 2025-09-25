import os
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List

# Allow local imports whether run as module or script
try:
    from prototype.local_cli.lib.jira_client import JiraClient  # type: ignore
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from lib.jira_client import JiraClient  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="List recent closed sprints for the current board")
    parser.add_argument("--n", type=int, default=int(os.getenv("VELOCITY_SPRINT_HISTORY", os.getenv("N_SPRINTS", "5"))), help="Number of recent closed sprints to fetch")
    args = parser.parse_args()

    jc = JiraClient()

    code_b, board, err_b = jc.resolve_board()
    if code_b != 200 or not board:
        print(err_b or "ボード解決に失敗", file=sys.stderr)
        return 1
    board_id = board.get("id")

    code_s, data_s, err_s = jc.api_get(
        f"{jc.domain}/rest/agile/1.0/board/{board_id}/sprint",
        params={"state": "closed", "maxResults": args.n, "startAt": 0},
    )
    if code_s != 200 or not data_s:
        print(err_s or "スプリント一覧取得に失敗", file=sys.stderr)
        return 1

    values = (data_s.get("values") or [])[: args.n]
    out: Dict[str, Any] = {
        "board": {"id": board_id, "name": board.get("name")},
        "sprints": [
            {
                "id": sp.get("id"),
                "name": sp.get("name"),
                "startDate": sp.get("startDate"),
                "endDate": sp.get("endDate"),
                "completeDate": sp.get("completeDate"),
            }
            for sp in values
        ],
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
