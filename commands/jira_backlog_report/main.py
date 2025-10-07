import os
import subprocess
import sys
from pathlib import Path

from commands.jira_backlog_report.get_image.dashbord_orchestrator.dashbord_orchestrator import DashboardOrchestrator

# try:
#     from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded, build_process_env
# except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
#     current = Path(__file__).resolve()
#     for parent in current.parents:
#         if (parent / "prototype").exists():
#             sys.path.append(str(parent))
#             break
#     from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded, build_process_env  # type: ignore


# ensure_env_loaded()

def run_dashboard_and_get_image():
    # ダッシュボード生成スクリプトを実行
    try:
        # repo_root = Path(__file__).resolve().parents[2]
        # base_env = build_process_env()
        # subprocess.run(
        #     [sys.executable, "-X", "utf8", "-m", "prototype.local_cli.main"],
        #     check=True,
        #     cwd=str(repo_root),
        #     env=base_env,
        # )
        dashboard_orchestrator = DashboardOrchestrator(enable_logging=True)
        image_bytes = dashboard_orchestrator.run()
    except Exception as e:
        print(f"ダッシュボード生成に失敗しました: {e}")
        return None

    # 画像ファイルのパス
    # image_path = os.path.join("prototype", "local_cli", "sprint_overview.png")

    return image_bytes

# if __name__ == "__main__":
#     image = run_dashboard_and_get_image()
#     if image:
#         print(f"画像ファイルのパス: {image}")
