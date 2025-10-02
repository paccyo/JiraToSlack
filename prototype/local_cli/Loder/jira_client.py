import os
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

try:
    from .env_loader import ensure_env_loaded
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from env_loader import ensure_env_loaded  # type: ignore

from .board_selector import resolve_board_with_preferences


ensure_env_loaded()


class JiraClient:
    def __init__(self) -> None:
        self.domain = self._load_env("JIRA_DOMAIN").rstrip("/")
        email = self._load_env("JIRA_EMAIL")
        token = self._load_env("JIRA_API_TOKEN")
        self.auth = HTTPBasicAuth(email, token)
        self.project_key = os.getenv("JIRA_PROJECT_KEY")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _load_env(self, key: str) -> str:
        v = os.getenv(key)
        if not v:
            print(f"環境変数が未設定です: {key}", file=sys.stderr)
            sys.exit(2)
        return v

    # --- HTTP helpers ---
    def api_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
        try:
            r = self.session.get(url, auth=self.auth, params=params, timeout=30)
        except requests.RequestException as e:
            return 0, None, str(e)
        if r.status_code == 200:
            try:
                return 200, r.json(), ""
            except json.JSONDecodeError:
                return 200, None, "JSON解析に失敗"
        return r.status_code, None, r.text

    def api_post(self, url: str, body: Dict[str, Any]) -> Tuple[int, Optional[Dict[str, Any]], str]:
        try:
            r = self.session.post(url, auth=self.auth, json=body, timeout=30)
        except requests.RequestException as e:
            return 0, None, str(e)
        if r.status_code == 200:
            try:
                return 200, r.json(), ""
            except json.JSONDecodeError:
                return 200, None, "JSON解析に失敗"
        return r.status_code, None, r.text

    # --- Resolve project/board ---
    def resolve_board(self) -> Tuple[int, Optional[Dict[str, Any]], str]:
        board_id = os.getenv("JIRA_BOARD_ID")

        def fetch(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
            return self.api_get(url, params=params)

        return resolve_board_with_preferences(self.domain, fetch, self.project_key, board_id, context="jira_client.resolve_board")

    def resolve_project_key(self) -> Optional[str]:
        if self.project_key:
            return self.project_key
        code, data, _ = self.api_get(f"{self.domain}/rest/api/3/project/recent")
        if code == 200 and isinstance(data, list) and data:
            key = (data[0] or {}).get("key")
            if key:
                self.project_key = str(key)
                return self.project_key
        code2, data2, _ = self.api_get(f"{self.domain}/rest/api/3/project/search", params={"expand": "lead"})
        if code2 == 200 and data2 and (data2.get("total", 0) > 0):
            values = data2.get("values") or data2.get("projects") or []
            if values:
                key = (values[0] or {}).get("key")
                if key:
                    self.project_key = str(key)
                    return self.project_key
        # Fallback: resolve via board's associated projects
        b_code, board, _ = self.resolve_board()
        if b_code == 200 and board and board.get("id"):
            b_id = board.get("id")
            p_code, p_data, _ = self.api_get(f"{self.domain}/rest/agile/1.0/board/{b_id}/project")
            if p_code == 200 and p_data and (p_data.get("values") or p_data.get("projects")):
                plist = p_data.get("values") or p_data.get("projects") or []
                if plist:
                    key = (plist[0] or {}).get("key")
                    if key:
                        self.project_key = str(key)
                        return self.project_key
        return None

    # --- Search helpers ---
    @staticmethod
    def _format_search_error(data: Optional[Dict[str, Any]], err: str) -> str:
        if isinstance(data, dict):
            messages = data.get("errorMessages") or data.get("errors")
            if isinstance(messages, list) and messages:
                return " ".join(str(m) for m in messages if m)
            if isinstance(messages, dict) and messages:
                try:
                    return json.dumps(messages, ensure_ascii=False)
                except Exception:
                    return str(messages)
        return err

    def _search_jql_page(
        self,
        jql: str,
        fields: Optional[List[str]],
        max_results: int,
        page_token: Optional[str],
    ) -> Tuple[int, Optional[Dict[str, Any]], str]:
        params: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max(1, min(max_results, 5000)),
        }
        if fields:
            params["fields"] = ",".join(fields)
        if page_token:
            params["pageToken"] = page_token
        code, data, err = self.api_get(f"{self.domain}/rest/api/3/search/jql", params=params)
        if code != 200 or not isinstance(data, dict):
            return code, None, self._format_search_error(data, err)
        return code, data, ""

    def approximate_count(self, jql: str) -> Tuple[int, Optional[int], str]:
        total = 0
        page_token: Optional[str] = None
        seen_tokens: set[str] = set()
        while True:
            code, data, err = self._search_jql_page(jql, ["id"], 500, page_token)
            if code != 200 or not data:
                return code, None, err
            issues = data.get("issues") or []
            total += len(issues)
            page_token = data.get("nextPageToken")
            is_last = data.get("isLast", True)
            if not issues or not page_token or page_token in seen_tokens or is_last:
                break
            seen_tokens.add(page_token)
        return 200, total, ""

    def search_paginated(self, jql: str, fields: List[str], batch: int = 100) -> Tuple[int, List[Dict[str, Any]], str]:
        results: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        seen_tokens: set[str] = set()
        while True:
            code, data, err = self._search_jql_page(jql, fields, batch, page_token)
            if code != 200 or not data:
                return code, results, err
            issues = data.get("issues") or []
            results.extend(issues)
            page_token = data.get("nextPageToken")
            is_last = data.get("isLast", True)
            if not issues or not page_token or page_token in seen_tokens or is_last:
                break
            seen_tokens.add(page_token)
        return 200, results, ""

    def count_jql(self, jql: str, batch: int = 500) -> Tuple[int, Optional[int], str]:
        total = 0
        page_token: Optional[str] = None
        seen_tokens: set[str] = set()
        while True:
            code, data, err = self._search_jql_page(jql, ["id"], batch, page_token)
            if code != 200 or not data:
                return code, None, err
            issues = data.get("issues") or []
            total += len(issues)
            page_token = data.get("nextPageToken")
            is_last = data.get("isLast", True)
            if not issues or not page_token or page_token in seen_tokens or is_last:
                break
            seen_tokens.add(page_token)
        return 200, total, ""

    # --- Story points field ---
    def resolve_story_points_field(self) -> str:
        sp_env = os.getenv("JIRA_STORY_POINTS_FIELD")
        if sp_env:
            return sp_env
        code, data, _ = self.api_get(f"{self.domain}/rest/api/3/field")
        if code == 200 and isinstance(data, list):
            for f in data:
                schema = f.get("schema") or {}
                if schema.get("custom") == "com.pyxis.greenhopper.jira:jsw-story-points":
                    return str(f.get("id"))
            for f in data:
                if str(f.get("id")) == "customfield_10016":
                    return "customfield_10016"
        return "customfield_10016"

    # --- Status helpers ---
    @staticmethod
    def is_done(status_field: Optional[Dict[str, Any]]) -> Optional[bool]:
        if not status_field:
            return None
        cat = (status_field or {}).get("statusCategory") or {}
        key = cat.get("key")
        if key == "done":
            return True
        if key in {"new", "indeterminate"}:
            return False
        return None

    # --- Sprint helpers ---
    def resolve_active_sprint(self, board_id: Optional[int] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
        b_id = board_id
        if b_id is None:
            code_b, board, err_b = self.resolve_board()
            if code_b != 200 or not board:
                return code_b, None, err_b
            b_id = board.get("id")
        code, data, err = self.api_get(
            f"{self.domain}/rest/agile/1.0/board/{b_id}/sprint",
            params={"state": "active", "maxResults": 50},
        )
        if code != 200 or not data:
            return code, None, err
        values = data.get("values") or []
        if not values:
            return 404, None, "アクティブなスプリントが見つかりません"
        return 200, values[0], ""
