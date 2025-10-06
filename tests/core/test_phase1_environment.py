"""Unit tests for Phase 1: Environment Setup"""
import pytest
import os
from unittest.mock import patch
from prototype.local_cli.core.phase1_environment import setup_environment, EnvironmentError
from prototype.local_cli.core.types import EnvironmentConfig, AuthContext


class TestEnvironmentConfig:
    """EnvironmentConfig のテスト"""
    
    def test_from_env_success(self, monkeypatch):
        """必須環境変数が揃っている場合、正常に構築される"""
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net/")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        monkeypatch.setenv("OUTPUT_DIR", "/tmp/output")
        
        config = EnvironmentConfig.from_env()
        
        assert config is not None
        assert config.jira_domain == "https://example.atlassian.net"  # 末尾スラッシュ除去
        assert config.jira_email == "test@example.com"
        assert config.jira_api_token == "token123"
        assert config.output_dir == "/tmp/output"
    
    def test_from_env_missing_required(self, monkeypatch):
        """必須環境変数が不足している場合、None を返す"""
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        # JIRA_EMAIL と JIRA_API_TOKEN を設定しない
        
        config = EnvironmentConfig.from_env()
        
        assert config is None
    
    def test_from_env_with_defaults(self, monkeypatch):
        """オプション環境変数のデフォルト値が適用される"""
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        
        config = EnvironmentConfig.from_env()
        
        assert config is not None
        assert config.target_done_rate == 0.8
        assert config.axis_mode == "percent"
        assert config.n_sprints == "6"
    
    def test_from_env_with_custom_values(self, monkeypatch):
        """カスタム環境変数が正しく反映される"""
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        monkeypatch.setenv("TARGET_DONE_RATE", "0.9")
        monkeypatch.setenv("AXIS_MODE", "count")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaTest123")
        monkeypatch.setenv("GEMINI_DISABLE", "true")
        
        config = EnvironmentConfig.from_env()
        
        assert config is not None
        assert config.target_done_rate == 0.9
        assert config.axis_mode == "count"
        assert config.gemini_api_key == "AIzaTest123"
        assert config.gemini_disable is True
    
    def test_from_env_invalid_numeric_value(self, monkeypatch):
        """不正な数値はデフォルト値にフォールバック"""
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        monkeypatch.setenv("TARGET_DONE_RATE", "invalid")
        
        config = EnvironmentConfig.from_env()
        
        assert config is not None
        assert config.target_done_rate == 0.8  # デフォルト値


class TestAuthContext:
    """AuthContext のテスト"""
    
    def test_repr_masks_token(self):
        """__repr__ がトークンをマスクする"""
        from requests.auth import HTTPBasicAuth
        
        auth = HTTPBasicAuth("user@example.com", "secret_token")
        ctx = AuthContext(domain="https://example.atlassian.net", auth=auth)
        
        repr_str = repr(ctx)
        
        assert "secret_token" not in repr_str
        assert "***" in repr_str
        assert "https://example.atlassian.net" in repr_str


class TestSetupEnvironment:
    """setup_environment 関数のテスト"""
    
    @patch('prototype.local_cli.Loder.dotenv_loader.ensure_env_loaded')
    def test_setup_environment_success(self, mock_ensure_env, monkeypatch):
        """正常ケース: 設定と認証コンテキストが返される"""
        mock_ensure_env.return_value = True
        
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        monkeypatch.setenv("DASHBOARD_LOG", "0")  # ログ無効化
        
        config, auth_ctx = setup_environment()
        
        assert isinstance(config, EnvironmentConfig)
        assert isinstance(auth_ctx, AuthContext)
        assert config.jira_domain == "https://example.atlassian.net"
        assert auth_ctx.domain == "https://example.atlassian.net"
        mock_ensure_env.assert_called_once()
    
    @patch('prototype.local_cli.Loder.dotenv_loader.ensure_env_loaded')
    def test_setup_environment_missing_required(self, mock_ensure_env, monkeypatch):
        """必須環境変数が不足している場合、EnvironmentError が発生"""
        mock_ensure_env.return_value = False
        
        monkeypatch.delenv("JIRA_DOMAIN", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        
        with pytest.raises(EnvironmentError) as exc_info:
            setup_environment()
        
        assert "必須の環境変数" in str(exc_info.value)
    
    @patch('prototype.local_cli.Loder.dotenv_loader.ensure_env_loaded')
    def test_setup_environment_logs_when_enabled(self, mock_ensure_env, monkeypatch, capsys):
        """DASHBOARD_LOG=1 の場合、ログが出力される"""
        mock_ensure_env.return_value = True
        
        monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "token123")
        monkeypatch.setenv("DASHBOARD_LOG", "1")
        
        config, auth_ctx = setup_environment()
        
        captured = capsys.readouterr()
        assert "[Phase 1]" in captured.out
        assert "Environment configured" in captured.out
