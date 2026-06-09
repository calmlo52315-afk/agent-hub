#!/usr/bin/env python3
"""测试 Claude Code 的 headless 模式"""

import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from runtime.skills.external_cli import ExternalCLIExecutor, _find_command
from runtime.skills.registry import SkillRegistry
from runtime.config.spec_loader import load_spec
from runtime.skills.base import SkillInvocationPlan
from pathlib import Path


def test_skill_definition():
    """测试技能定义是否正确加载"""
    print("=== 测试技能定义加载 ===")
    spec = load_spec()
    registry = SkillRegistry.from_spec(spec)
    
    claude_skill = registry.resolve_active("claude_code")
    print(f"技能名称: {claude_skill.skill_name}")
    print(f"模式: {claude_skill.mode}")
    print(f"输出格式: {claude_skill.output_format}")
    print(f"权限模式: {claude_skill.permission_mode}")
    print(f"命令: {claude_skill.command}")
    
    assert claude_skill.mode == "headless", f"期望模式为 headless，实际为 {claude_skill.mode}"
    assert claude_skill.output_format == "json", f"期望输出格式为 json，实际为 {claude_skill.output_format}"
    assert claude_skill.permission_mode == "bypassPermissions", f"期望权限模式为 bypassPermissions，实际为 {claude_skill.permission_mode}"
    
    print("✓ 技能定义加载成功\n")
    return claude_skill


def test_build_args():
    """测试参数构建"""
    print("=== 测试参数构建 ===")
    
    # 先创建一个简单的测试文件来验证
    test_file = project_root / "demo_workspace" / "test_headless_2.py"
    if test_file.exists():
        test_file.unlink()
    
    # 测试直接调用 Claude Code
    import subprocess
    
    instruction = f"创建一个简单的 Python 文件，打印 'Test Headless Mode Success' 到 demo_workspace/test_headless_2.py"
    
    print(f"指令: {instruction}")
    print("\n调用 Claude Code headless 模式...")
    
    cmd = [
        "claude",
        "-p",
        instruction,
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "json"
    ]
    
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120
    )
    
    print(f"退出码: {result.returncode}")
    print(f"\nSTDOUT:")
    print(result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout)
    
    if result.stderr:
        print(f"\nSTDERR:")
        print(result.stderr)
    
    # 检查文件是否创建成功
    print(f"\n检查文件: {test_file}")
    if test_file.exists():
        print(f"✓ 文件创建成功!")
        print(f"内容: {test_file.read_text().strip()}")
    else:
        print(f"✗ 文件未创建")
    
    return test_file.exists()


if __name__ == "__main__":
    print("开始测试 Claude Code headless 模式\n")
    
    try:
        # 测试 1: 技能定义
        claude_skill = test_skill_definition()
        
        # 测试 2: 直接调用参数
        success = test_build_args()
        
        if success:
            print("\n✓ 所有测试通过!")
        else:
            print("\n✗ 部分测试失败")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
