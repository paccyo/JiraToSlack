import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Use fully qualified import so tests can monkeypatch consistently
from prototype.local_cli.lib.jira_client import JiraClient  # type: ignore

JST = timezone(timedelta(hours=9))

def parse_iso(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # Jira dates are ISO8601; handle both with and without timezone
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def start_of_day(dt: datetime, tz: timezone) -> datetime:
    return datetime(dt.year, dt.month, dt.day, tzinfo=tz)


def main() -> int:
    parser = argparse.ArgumentParser(description="Jira burndown JSON for sprint")
    parser.add_argument("--sprint", type=int, help="Sprint ID (defaults to active)"
                        )
    parser.add_argument("--unit", choices=["points", "issues"], default=os.getenv("BURNDOWN_UNIT", "points"))
    args = parser.parse_args()

    jc = JiraClient()

    # Resolve sprint
    sprint: Optional[Dict[str, Any]] = None
    if args.sprint:
        code, data, err = jc.api_get(f"{jc.domain}/rest/agile/1.0/sprint/{args.sprint}")
        if code != 200 or not data:
            print(err or "スプリント取得に失敗", file=sys.stderr)
            return 1
        sprint = data
    else:
        code, data, err = jc.resolve_active_sprint()
        if code != 200 or not data:
            print(err or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        sprint = data

    sprint_id = sprint.get("id")
    sprint_name = sprint.get("name")
    start_date = parse_iso(sprint.get("startDate"))
    end_date = parse_iso(sprint.get("endDate"))

    # Fetch sprint issues with needed fields
    fields = ["summary", "status", "issuetype"]
    unit = (args.unit or "points").lower()
    if unit == "points":
        sp_field = jc.resolve_story_points_field()
        fields.append(sp_field)
    else:
        sp_field = None

    code, issues, err = jc.search_paginated(f"Sprint={sprint_id}", fields=fields, batch=100)
    if code != 200:
        print(err or "スプリントの課題取得に失敗", file=sys.stderr)
        return 1

    # Build per-issue weights and done dates
    done_dates: List[Tuple[datetime, float]] = []
    total_capacity = 0.0
    for iss in issues:
        f = iss.get("fields") or {}
        # weight by story points or 1 per issue
        if unit == "points":
            val = f.get(sp_field) if sp_field else None
            try:
                w = float(val) if val is not None else 0.0
            except Exception:
                w = 0.0
        else:
            w = 1.0
        total_capacity += w

        # Determine done date: use statusCategory=done now; for historical, try changelog
        st = f.get("status") or {}
        cat = (st.get("statusCategory") or {}).get("key")
        if cat == "done":
            # If it's done now but we don't know when, fallback to endDate or today
            done_dt = datetime.now(tz=JST)
        else:
            done_dt = None

        # Try to refine done date via changelog
        # Requires expand=changelog; fetch per issue to avoid huge payload
        code_i, data_i, _ = jc.api_get(f"{jc.domain}/rest/api/3/issue/{iss.get('id')}", params={"expand": "changelog"})
        if code_i == 200 and data_i:
            try:
                hist = ((data_i.get("changelog") or {}).get("histories") or [])
                for h in hist:
                    items = h.get("items") or []
                    for it in items:
                        if (it.get("field") == "status" and
                            (it.get("toString") or it.get("to"))):
                            to_name = it.get("toString") or ""
                            if to_name:
                                # If transitioned into a Done category status, mark date
                                # Unfortunately statusCategory isn't in changelog items; accept any status that is Done now
                                if to_name.lower() in {"done", "resolved", "fixed", "完成", "完了"}:
                                    changed = parse_iso(h.get("created"))
                                    if changed:
                                        done_dt = changed
                                        raise StopIteration
            except StopIteration:
                pass
            except Exception:
                pass

        if done_dt:
            done_dates.append((done_dt, w))

    # Build time axis
    tz = start_date.tzinfo if start_date and start_date.tzinfo else JST
    if not start_date:
        # fallback: earliest of done dates or today-10
        if done_dates:
            start_date = min(d for d, _ in done_dates)
        else:
            start_date = datetime.now(tz=tz) - timedelta(days=10)
    if not end_date:
        end_date = datetime.now(tz=tz)

    s0 = start_of_day(start_date.astimezone(tz), tz)
    e0 = start_of_day(end_date.astimezone(tz), tz)

    # Accumulate burn per day
    # remaining = total_capacity - cumulative(done up to that day)
    daily = []
    day = s0
    while day <= e0:
        burned = 0.0
        for d, w in done_dates:
            dd = start_of_day(d.astimezone(tz), tz)
            if dd <= day:
                burned += w
        remaining = max(0.0, total_capacity - burned)
        daily.append({
            "date": day.date().isoformat(),
            "remaining": remaining,
        })
        day += timedelta(days=1)

    # Ideal line (straight from start to zero at end)
    ideal = []
    total_days = max(1, (e0 - s0).days)
    for i, d in enumerate(range((e0 - s0).days + 1)):
        t = s0 + timedelta(days=i)
        rem = total_capacity * max(0.0, 1.0 - (i / total_days))
        ideal.append({"date": t.date().isoformat(), "remaining": rem})

    out = {
        "sprint": {"id": sprint_id, "name": sprint_name,
                    "startDate": start_date.isoformat() if start_date else None,
                    "endDate": end_date.isoformat() if end_date else None},
        "unit": unit,
        "total": total_capacity,
        "timeSeries": daily,
        "ideal": ideal,
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
