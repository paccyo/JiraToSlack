import json

def build_jql_from_json(data: dict) -> str:
    """
    指定されたJSONオブジェクトからJQLクエリ文字列を構築します。
    Args:
        data: JQLの構成要素を含む辞書（JSONオブジェクト）。
    Returns:
        JQLクエリ文字列。
    """
    conditions = []
    # JQL内で引用符で囲む必要のない特別なキーワードや関数を定義
    jql_keywords = {
        "currentUser()", "isEmpty()", "now()", "endOfDay()", "endOfWeek()",
        "startOfMonth()", "Highest", "High", "Medium", "Low", "Lowest"
    }

    # キーの処理順を固定すると、テストなどで結果が安定します
    process_order = [
        "project", "reporter", "assignee", "issuetype", "status",
        "priority", "text", "duedate", "created"
    ]

    for field in process_order:
        value = data.get(field)
        # 値がnullの場合はスキップ
        if value is None:
            continue
        
        # 値が単純な文字列の場合の処理
        if isinstance(value, str):
            # 'text'フィールドは'~'演算子を使用
            if field == 'text':
                conditions.append(f'text ~ "{value}"')
            # その他のフィールドは'='演算子を使用
            else:
                # 値が特別なキーワードでなければ引用符で囲む
                formatted_value = value if value in jql_keywords else f'"{value}"'
                conditions.append(f'{field} = {formatted_value}')

        # 値が比較演算子を持つオブジェクトの場合の処理
        elif isinstance(value, dict):
            operator = value.get("operator", "=").upper()
            op_value = value.get("value")

            if op_value is None:
                continue
            
            # IN や NOT IN 演算子で、値がリストの場合
            if operator in ["IN", "NOT IN"] and isinstance(op_value, list):
                # リストの各要素を引用符で囲み、カンマで連結
                quoted_items = [f'"{item}"' for item in op_value]
                formatted_value = f'({", ".join(quoted_items)})'
                conditions.append(f'{field} {operator} {formatted_value}')
            
            # その他の演算子で、値が文字列の場合
            elif isinstance(op_value, str):
                formatted_value = op_value if op_value in jql_keywords else f'"{op_value}"'
                conditions.append(f'{field} {operator} {formatted_value}')

    # 全ての条件を " AND " で連結して返す
    return " AND ".join(conditions)

# --- ここからが実行とテストのコード ---
if __name__ == "__main__":
    # 前のステップで生成されたJSONの例
    example_json_1 = {
      "project": None, "reporter": "currentUser()", "assignee": None, "issuetype": "Task",
      "status": {"operator": "not in", "value": ["完了", "Done", "Closed", "Resolved"]},
      "priority": None, "text": None, "duedate": None, "created": None
    }

    example_json_2 = {
      "project": None, "reporter": None, "assignee": None, "issuetype": "Bug",
      "status": {"operator": "not in", "value": ["完了", "Done"]},
      "priority": {"operator": ">=", "value": "High"}, "text": None,
      "duedate": {"operator": "<=", "value": "endOfDay()"}, "created": None
    }

    example_json_3 = {
      "project": None, "reporter": None, "assignee": "isEmpty()", "issuetype": None,
      "status": {"operator": "not in", "value": ["完了"]},
      "priority": None, "text": "決済",
      "duedate": {"operator": "<", "value": "now()"}, "created": None
    }

    # --- 例1の実行 ---
    print("--- 例1: 「私が報告したタスク」 ---")
    print("入力JSON:")
    print(json.dumps(example_json_1, indent=2, ensure_ascii=False))
    jql_query_1 = build_jql_from_json(example_json_1)
    print("\n変換後JQL:")
    print(jql_query_1)
    print("-" * 40)

    # --- 例2の実行 ---
    print("--- 例2: 「今日が期限の、優先度が高いバグ」 ---")
    print("入力JSON:")
    print(json.dumps(example_json_2, indent=2, ensure_ascii=False))
    jql_query_2 = build_jql_from_json(example_json_2)
    print("\n変換後JQL:")
    print(jql_query_2)
    print("-" * 40)

    # --- 例3の実行 ---
    print("--- 例3: 「担当者がいない、\"決済\"関連の期限切れ課題」 ---")
    print("入力JSON:")
    print(json.dumps(example_json_3, indent=2, ensure_ascii=False))
    jql_query_3 = build_jql_from_json(example_json_3)
    print("\n変換後JQL:")
    print(jql_query_3)
    print("-" * 40)