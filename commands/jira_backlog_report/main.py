
import subprocess
import os

def run_dashboard_and_get_image():
    # ダッシュボード生成スクリプトを実行
    try:
        subprocess.run([
            "python", "-X", "utf8", "prototype/local_cli/main.py"
        ], check=True)
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
