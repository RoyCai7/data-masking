import sqlite3

db_path = "/opt/data-masking/backend/rules.db"

def replace_rules():
    with sqlite3.connect(db_path) as conn:
        rules = [
            {
                "id": "standalone_16_hex",
                "name": "16-Char Hex Token",
                "category": "token",
                "pattern": r"\b[a-fA-F0-9]{16}\b",
                "strategy": "placeholder",
                "placeholder": "[MASKED_HEX]",
                "flags": "IGNORECASE",
                "weight": 10,
                "enabled": True,
                "is_builtin": False
            },
            {
                "id": "full_ssh_private_key",
                "name": "Full SSH Private Key",
                "category": "secret",
                "pattern": r"-----BEGIN [a-zA-Z ]*PRIVATE KEY-----[\s\S]+?-----END [a-zA-Z ]*PRIVATE KEY-----",
                "strategy": "placeholder",
                "placeholder": "[REDACTED_FULL_PRIVATE_KEY]",
                "flags": "IGNORECASE|DOTALL",
                "weight": 14,
                "enabled": True,
                "is_builtin": False
            }
        ]
        
        for new_rule in rules:
            conn.execute("""
                INSERT OR REPLACE INTO rules
                (id, name, category, pattern, strategy, placeholder, flags, weight, enabled, is_builtin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_rule["id"], new_rule["name"], new_rule["category"],
                new_rule["pattern"], new_rule["strategy"], new_rule["placeholder"],
                new_rule["flags"], new_rule["weight"], new_rule["enabled"], new_rule["is_builtin"]
            ))
            print("Added rule: " + new_rule["id"])

    print("Fix rules added to remote DB.")

if __name__ == "__main__":
    replace_rules()
