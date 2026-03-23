#!/usr/bin/env python3
"""
API Key Management CLI Tool

Usage:
  python generate_key.py create --name "Roy Cai" [--role admin] [--expires 365]
  python generate_key.py list
  python generate_key.py disable --key dms_xxxxxxxx
"""
import sys
import os
import argparse

# Add backend to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.auth import add_key, load_keys, disable_key, _load_keys_file


def cmd_create(args):
    """Create a new API key"""
    key_data = add_key(
        name=args.name,
        role=args.role,
        expires_days=args.expires,
    )
    print()
    print("=" * 60)
    print("  ✅ API Key Created Successfully")
    print("=" * 60)
    print()
    print(f"  Name:       {key_data['name']}")
    print(f"  Role:       {key_data['role']}")
    print(f"  API Key:    {key_data['key']}")
    print(f"  Created:    {key_data['created_at']}")
    print(f"  Expires:    {key_data['expires_at']}")
    print()
    print("  Usage:")
    print(f'  curl -H "X-API-Key: {key_data["key"]}" http://10.146.15.188:8080/api/v1/tasks')
    print()
    print("  ⚠️  Save this key now — it cannot be retrieved later!")
    print("=" * 60)
    print()


def cmd_list(args):
    """List all API keys"""
    data = _load_keys_file()
    keys = data.get("keys", [])

    if not keys:
        print("No API keys found. Create one with: python generate_key.py create --name 'Your Name'")
        return

    print()
    print(f"{'Name':<20} {'Role':<10} {'Status':<10} {'Created':<12} {'Expires':<12} {'Key (last 8)':<12}")
    print("-" * 76)
    for k in keys:
        status = "✅ Active" if k.get("enabled", True) else "❌ Disabled"
        key_preview = "..." + k["key"][-8:]
        print(f"{k['name']:<20} {k.get('role', 'user'):<10} {status:<10} {k['created_at']:<12} {k.get('expires_at', 'never'):<12} {key_preview:<12}")
    print()
    print(f"Total: {len(keys)} key(s)")
    print()


def cmd_disable(args):
    """Disable an API key"""
    if disable_key(args.key):
        print(f"✅ API key disabled: ...{args.key[-8:]}")
    else:
        print(f"❌ API key not found: {args.key}")


def main():
    parser = argparse.ArgumentParser(
        description="DMS API Key Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_key.py create --name "Roy Cai" --role admin
  python generate_key.py create --name "CI Pipeline" --role user --expires 90
  python generate_key.py list
  python generate_key.py disable --key dms_abc123...
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--name", required=True, help="Key owner name (e.g. 'Roy Cai')")
    create_parser.add_argument("--role", default="user", choices=["admin", "user"], help="Key role (default: user)")
    create_parser.add_argument("--expires", type=int, default=365, help="Days until expiry (default: 365)")

    # list
    subparsers.add_parser("list", help="List all API keys")

    # disable
    disable_parser = subparsers.add_parser("disable", help="Disable an API key")
    disable_parser.add_argument("--key", required=True, help="The API key to disable")

    args = parser.parse_args()

    if args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "disable":
        cmd_disable(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
