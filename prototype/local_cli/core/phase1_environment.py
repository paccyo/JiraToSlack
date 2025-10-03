"""Phase 1: Environment and Authentication Setup"""
from typing import Optional, Tuple
from requests.auth import HTTPBasicAuth

from .types import EnvironmentConfig, AuthContext


class EnvironmentError(Exception):
    """環境設定に関するエラー"""
    pass


def setup_environment() -> Tuple[EnvironmentConfig, AuthContext]:
    """
    Phase 1: 環境変数の読み込みと認証コンテキストの構築
    
    Returns:
        (EnvironmentConfig, AuthContext): 設定と認証情報
        
    Raises:
        EnvironmentError: 必須環境変数が不足している場合
    """
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded
    
    # 1. .env ファイルの読み込み
    loaded = ensure_env_loaded()
    
    if loaded:
        print("[Phase 1] .env files loaded")
    
    # 2. 設定の検証と構築
    config = EnvironmentConfig.from_env()
    if not config:
        raise EnvironmentError(
            "必須の環境変数が設定されていません。\n"
            "JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN を .env ファイルに設定してください。"
        )
    
    # 3. 認証コンテキストの作成
    auth = HTTPBasicAuth(config.jira_email, config.jira_api_token)
    auth_ctx = AuthContext(domain=config.jira_domain, auth=auth)
    
    if config.dashboard_log:
        print(f"[Phase 1] Environment configured: {config.jira_domain}")
        print(f"[Phase 1] Output directory: {config.output_dir}")
        print(f"[Phase 1] Target done rate: {config.target_done_rate}")
        print(f"[Phase 1] Axis mode: {config.axis_mode}")
    
    return config, auth_ctx
