import os
import sys
import json
import argparse
from typing import Any, Dict
from pathlib import Path

# Allow local imports
try:
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "prototype").exists():
            sys.path.append(str(parent))
            break
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded  # type: ignore
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore


ensure_env_loaded()


def main() -> int:
    parser = argparse.ArgumentParser(description="Due soon issues count")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("DS_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--days", type=int, default=int(os.getenv("DUE_SOON_DAYS", "7")))
    args = parser.parse_args()

    jc = JiraClient()

    if args.scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        base = f"Sprint={sprint.get('id')}"
        meta = {"scope": "sprint", "sprint": {"id": sprint.get("id"), "name": sprint.get("name")}}
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        base = f"project={key}"
        meta = {"scope": "project", "project": key}

    jql = f"{base} AND due >= now() AND due <= {args.days}d AND statusCategory != Done"
    code_c, cnt, err_c = jc.approximate_count(jql)
    if code_c != 200 or cnt is None:
        print(err_c or "件数取得に失敗", file=sys.stderr)
        return 1

    out = {**meta, "dueSoonCount": int(cnt), "days": args.days}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
