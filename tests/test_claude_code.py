#!/usr/bin/env python3
"""测试 Claude Code 技能的执行流程"""

import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from runtime.orchestrator import Orchestrator

def test_claude_code_flow():
    """测试使用 claude_code 技能的完整流程"""
    print("[DEBUG] 初始化 Orchestrator...")
    orch = Orchestrator.load()
    
    print("[DEBUG] 执行测试任务...")
    result = orch.run_task(
        instruction="创建一个简单的 Python 脚本，打印 'Hello from Claude Code!' 到 demo_workspace/test_claude.py",
        mentioned_agent="claude_code"
    )
    
    print("\n[DEBUG] 结果:")
    print(f"  ok: {result.get('ok')}")
    print(f"  task_id: {result.get('task_id')}")
    print(f"  status: {result.get('status')}")
    
    if "result" in result:
        res = result["result"]
        coding = res.get("coding", {})
        print(f"\n[DEBUG] 编码结果:")
        print(f"  applied_changes: {len(coding.get('applied_changes', []))}")
        for change in coding.get('applied_changes', []):
            print(f"    - {change.get('action')}: {change.get('path')}")
        
        artifact = res.get("artifact")
        print(f"\n[DEBUG] 产物结果:")
        if artifact:
            print(f"  artifact_dir: {artifact.get('artifact_dir')}")
            print(f"  created_files: {artifact.get('created_files')}")
        else:
            print(f"  (无产物，使用 package_strategy='none')")
    
    if "diagnostics" in result:
        print(f"\n[DEBUG] 诊断信息（前 20 条）:")
        for diag in result["diagnostics"][:20]:
            print(f"  {diag.get('kind')}: {diag.get('message', '')}")

if __name__ == "__main__":
    test_claude_code_flow()
