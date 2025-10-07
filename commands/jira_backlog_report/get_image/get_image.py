from commands.jira_backlog_report.get_image.dashbord_orchestrator.dashbord_orchestrator import DashboardOrchestrator


def run_dashboard_generation(enable_logging: bool = True) -> int:
    """
    ダッシュボード生成を実行（エラーハンドリング付き）
    
    Args:
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        int: 終了コード（0=成功、1=失敗）
    """
    try:
        orchestrator = DashboardOrchestrator(enable_logging=enable_logging)
        image_path = orchestrator.run()
        
        # 画像パスを出力（既存のmain.pyとの互換性）
        print(str(image_path))
        
        return 0
    
    
    except Exception as e:
        if enable_logging:
            print(f"❌ Unexpected error: {e}")
        return 1


def get_image() -> int:
    """
    Dashboard generation entry point (refactored).
    
    新しいオーケストレーターを使用してダッシュボード生成を実行します。
    既存のヘルパー関数(draw_png, get_json_from_script等)は後方互換性のため維持されています。
    
    Returns:
        int: 終了コード（0=成功、1=失敗）
    """
    return run_dashboard_generation()


