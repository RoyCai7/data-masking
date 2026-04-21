#!/usr/bin/env python3
"""
Usage: python3 mask_file.py <input_file> [output_file]
"""
import sys
import json
import time
import subprocess

API_BASE = "http://10.146.15.188:8080/api/v1"
API_KEY  = "dms_3be8006031f045d3aafdc6c78282f2e4"

def curl(args):
    result = subprocess.run(["curl", "-s"] + args, capture_output=True, text=True)
    return result.stdout

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mask_file.py <input_file> [output_file]")
        sys.exit(1)

    input_file  = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file + ".masked.txt"

    # Step 1: 上传文件
    print(f"[1] 上传文件: {input_file}")
    resp = curl([
        "-X", "POST", f"{API_BASE}/mask",
        "-H", f"X-API-Key: {API_KEY}",
        "-F", f"file=@{input_file}"
    ])
    data = json.loads(resp)
    task_id = data["task_id"]
    session_id = data["session_id"]
    print(f"    Task ID:    {task_id}")
    print(f"    Session ID: {session_id}")

    session_id = json.loads(curl([
        "-X", "POST", f"{API_BASE}/mask",
        "-H", f"X-API-Key: {API_KEY}",
        "-F", f"file=@{input_file}"
    ]))["session_id"]

    # Step 2: 等待完成
    print("[2] 等待处理...")
    for _ in range(30):
        resp = curl([f"{API_BASE}/task/{task_id}",
                     "-H", f"X-API-Key: {API_KEY}",
                     "-H", f"X-Session-ID: {session_id}"])
        data = json.loads(resp)
        status = data["status"]
        print(f"    状态: {status}")
        if status == "completed":
            report = data.get("report", {})
            print(f"    匹配项: {report.get('total_matches', 0)}, 风险等级: {report.get('risk_level', '-')}")
            break
        if status == "failed":
            print(f"    错误: {data.get('error')}")
            sys.exit(1)
        time.sleep(0.5)

    # Step 3: 下载结果
    print(f"[3] 下载结果 → {output_file}")
    curl([
        f"{API_BASE}/download/{task_id}",
        "-H", f"X-API-Key: {API_KEY}",
        "-H", f"X-Session-ID: {session_id}",
        "-o", output_file
    ])

    print("\n--- 脱敏结果 ---")
    with open(output_file) as f:
        print(f.read())

if __name__ == "__main__":
    main()
