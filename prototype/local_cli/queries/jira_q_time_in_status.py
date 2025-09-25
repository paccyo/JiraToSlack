import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Allow local imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from lib.jira_client import JiraClient  # type: ignore

JST = timezone(timedelta(hours=9))


def parse_iso(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Jira time-in-status (滞在時間集計)")
    parser.add_argument("--scope", choices=["sprint", "project"], default=os.getenv("TIS_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--unit", choices=["hours", "days"], default=os.getenv("TIS_UNIT", "hours"))
    parser.add_argument("--since", help="Override start ISO datetime (defaults sprint.startDate or project window)")
    parser.add_argument("--until", help="Override end ISO datetime (defaults sprint.endDate or now)")
    args = parser.parse_args()

    jc = JiraClient()

    # Resolve window and JQL
    since: Optional[datetime] = parse_iso(args.since)
    until: Optional[datetime] = parse_iso(args.until)
    sprint: Optional[Dict[str, Any]] = None

    if args.scope == "sprint":
        code, sprint, err = jc.resolve_active_sprint()
        if code != 200 or not sprint:
            print(err or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        jql = f"Sprint={sprint.get('id')}"
        if not since:
            since = parse_iso(sprint.get("startDate"))
        if not until:
            until = parse_iso(sprint.get("endDate")) or datetime.now(tz=JST)
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        jql = f"project={key}"
        if not since:
            since = datetime.now(tz=JST) - timedelta(days=14)
        if not until:
            until = datetime.now(tz=JST)

    tz = since.tzinfo if since and since.tzinfo else JST
    if not since:
        since = datetime.now(tz=tz) - timedelta(days=14)
    if not until:
        until = datetime.now(tz=tz)

    # Fetch issues (keys only first, then per-issue changelog fetch)
    code, issues, err = jc.search_paginated(jql, fields=["status"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    # Aggregate time in status per issue and overall
    per_issue: List[Dict[str, Any]] = []
    total_by_status: Dict[str, float] = {}
    
    # 完了ステータス（statusCategory="Done"）を除外するためのヘルパー関数
    def is_done_status(status_name: str) -> bool:
        """ステータス名が完了状態かどうか判定"""
        # 一般的な完了ステータス名をチェック
        done_statuses = {"完了", "Done", "Closed", "Resolved", "完成", "終了"}
        return status_name in done_statuses

    for iss in issues:
        iid = iss.get("id")
        ikey = iss.get("key")
        code_i, data_i, _ = jc.api_get(f"{jc.domain}/rest/api/3/issue/{iid}", params={"expand": "changelog"})
        if code_i != 200 or not data_i:
            continue
        histories = ((data_i.get("changelog") or {}).get("histories") or [])
        
        # 課題作成日時を取得
        created_date = parse_iso((data_i.get("fields") or {}).get("created"))
        
        # Build timeline of status with timestamps
        events: List[Tuple[datetime, str]] = []
        # initial: unknown until first status we see; we can derive current status at the end
        for h in histories:
            created = parse_iso(h.get("created"))
            if not created:
                continue
            for it in (h.get("items") or []):
                if it.get("field") == "status":
                    name = (it.get("toString") or it.get("to"))
                    if name:
                        events.append((created, str(name)))
        # Sort by time
        events.sort(key=lambda x: x[0])
        
        # If we have no events, take current status as single bucket for the window (完了ステータスは除外)
        if not events:
            cur = ((iss.get("fields") or {}).get("status") or {}).get("name") or "(unknown)"
            if not is_done_status(cur):
                # 課題作成日時とスプリント開始日時の遅い方から現在時刻まで計算
                effective_start = max(since, created_date) if created_date else since
                now = datetime.now(timezone.utc)
                # 現在時刻がスプリント終了前の場合は現在時刻、それ以降の場合はスプリント終了時刻を使用
                effective_end = min(now, until)
                dur = max(0.0, (effective_end - effective_start).total_seconds())
                total_by_status[cur] = total_by_status.get(cur, 0.0) + dur
                per_issue.append({"key": ikey, "byStatus": {cur: dur}})
            else:
                # 完了ステータスの場合は空のデータを追加
                per_issue.append({"key": ikey, "byStatus": {}})
            continue

        # Walk through events, compute durations clipped to [since, until]
        by_status: Dict[str, float] = {}
        prev_time = None
        prev_status = None

        # Assume first known status applies from window start or first event, whichever is later
        prev_time = max(since, events[0][0])
        prev_status = events[0][1]

        # If there is a gap before first event inside window, attribute it to that first status
        if events[0][0] > since:
            pass  # already covered as prev_time starts at since

        for t, st in events[1:]:
            if t < since:
                # transition before window; update baseline status
                prev_time = since
                prev_status = st
                continue
            if t > until:
                break
            # add duration for prev_status (完了ステータスは除外)
            dur = (t - prev_time).total_seconds()
            if dur > 0 and prev_status and not is_done_status(prev_status):
                by_status[prev_status] = by_status.get(prev_status, 0.0) + dur
            prev_time = t
            prev_status = st

        # tail from last change to current time or sprint end (完了ステータスは除外)
        if prev_time and prev_status and not is_done_status(prev_status):
            now = datetime.now(timezone.utc)
            effective_end = min(now, until)
            tail = (effective_end - max(prev_time, since)).total_seconds()
            if tail > 0:
                by_status[prev_status] = by_status.get(prev_status, 0.0) + tail

        # accumulate (完了ステータスは除外)
        for k, v in by_status.items():
            if not is_done_status(k):
                total_by_status[k] = total_by_status.get(k, 0.0) + v
        per_issue.append({"key": ikey, "byStatus": by_status})

    # Convert seconds to requested unit
    unit = (args.unit or "hours").lower()
    denom = 3600.0 if unit == "hours" else 86400.0

    total_conv = {k: v / denom for k, v in total_by_status.items()}
    per_issue_conv = []
    for row in per_issue:
        per_issue_conv.append({
            "key": row["key"],
            "byStatus": {k: v / denom for k, v in row["byStatus"].items()},
        })

    out = {
        "scope": args.scope,
        "sprint": {"id": sprint.get("id"), "name": sprint.get("name")} if sprint else None,
        "project": args.project if args.scope == "project" else None,
        "window": {"since": since.isoformat(), "until": until.isoformat(), "unit": unit},
        "totalByStatus": total_conv,
        "perIssue": per_issue_conv,
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
