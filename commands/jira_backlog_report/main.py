
import os
import subprocess
import sys
from pathlib import Path

def run_dashboard_and_get_image():
    # ダッシュボード生成スクリプトを実行
    try:
        repo_root = Path(__file__).resolve().parents[2]
        base_env = os.environ.copy()
        search_paths = [str(repo_root), str(repo_root / "prototype"), str(repo_root / "prototype" / "local_cli")]
        existing_py_path = base_env.get("PYTHONPATH")
        base_env["PYTHONPATH"] = os.pathsep.join(
            [p for p in search_paths if p] + ([existing_py_path] if existing_py_path else [])
        )
        subprocess.run(
            [sys.executable, "-X", "utf8", "prototype/local_cli/main.py"],
            check=True,
            cwd=str(repo_root),
            env=base_env,
        )
    except Exception as e:
        print(f"ダッシュボード生成に失敗しました: {e}")
        return None

    # 画像ファイルのパス
    image_path = os.path.join("prototype", "local_cli", "sprint_overview.png")
    if not os.path.exists(image_path):
        print("画像ファイルが生成されていません")
        return None
    return image_path

if __name__ == "__main__":
    image = run_dashboard_and_get_image()
    if image:
        print(f"画像ファイルのパス: {image}")
