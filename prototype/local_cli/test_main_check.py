import subprocess
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MAIN_PATH = BASE_DIR / "main.py"
IMG_PATH = BASE_DIR / "sprint_overview.png"
MD_PATH = BASE_DIR / "sprint_overview_report.md"
JSON_PATH = BASE_DIR / "sprint_overview_data.json"


def run_main():
    print("[1] main.py 実行開始...")
    try:
        result = subprocess.run([
            "python", "-X", "utf8", str(MAIN_PATH)
        ], capture_output=True, text=True, encoding="utf-8", cwd=str(BASE_DIR))
        print("[2] main.py 実行完了 (exit code:", result.returncode, ")")
        if result.stdout:
            print("[stdout]\n", result.stdout)
        if result.stderr:
            print("[stderr]\n", result.stderr)
        if result.returncode != 0:
            print("[ERROR] main.py 実行失敗。上記stderrを確認してください。")
            return False
    except Exception as e:
        print(f"[EXCEPTION] main.py 実行時に例外: {e}")
        return False
    return True


def check_outputs():
    print("[3] 生成物の存在確認...")
    ok = True
    for path, label in [
        (IMG_PATH, "画像"),
        (MD_PATH, "Markdown"),
        (JSON_PATH, "JSON")
    ]:
        if path.exists():
            print(f"[OK] {label}ファイル生成: {path}")
        else:
            print(f"[NG] {label}ファイル未生成: {path}")
            ok = False
    return ok


def main():
    print("==== main.py 動作確認テスト ====")
    success = run_main()
    if not success:
        print("[FAIL] main.py 実行に失敗しました。stderr/例外を確認してください。")
        return
    outputs_ok = check_outputs()
    if not outputs_ok:
        print("[FAIL] 生成物の一部が見つかりません。main.pyの出力処理を確認してください。")
    else:
        print("[PASS] main.py の動作・出力に問題ありません。")

if __name__ == "__main__":
    main()
