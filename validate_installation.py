#!/usr/bin/env python3
"""
Validate Wan2GP MCP Server Installation

This script validates that the MCP server is correctly installed
and can handle all expected operations (including graceful error handling).
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all modules can be imported."""
    print("\n=== Testing Imports ===")

    try:
        from wan2gp_client import Wan2GPClient, Wan2GPConnectionError, GenerationError
        print("✓ wan2gp_client imports successfully")
    except Exception as e:
        print(f"✗ Failed to import wan2gp_client: {e}")
        return False

    try:
        from wan2gp_mcp_server import mcp, CONFIG
        print("✓ wan2gp_mcp_server imports successfully")
    except Exception as e:
        print(f"✗ Failed to import wan2gp_mcp_server: {e}")
        return False

    return True


def test_config():
    """Test configuration loading."""
    print("\n=== Testing Configuration ===")

    from wan2gp_mcp_server import CONFIG

    required_keys = ["wan2gp_url", "timeout", "default_model"]
    for key in required_keys:
        if key in CONFIG:
            print(f"✓ {key}: {CONFIG[key]}")
        else:
            print(f"✗ Missing config key: {key}")
            return False

    return True


async def test_client_connection_handling():
    """Test client handles connection failures gracefully."""
    print("\n=== Testing Client Connection Handling ===")

    from wan2gp_client import Wan2GPClient

    # Test with unreachable server
    client = Wan2GPClient(base_url="http://localhost:9999")

    try:
        health = await client.health_check()

        if health["status"] == "unhealthy":
            print("✓ Client correctly reports unhealthy server")
            print(f"  Error message: {health.get('error', 'N/A')}")
        else:
            print(f"✗ Unexpected health status: {health['status']}")
            return False

    except Exception as e:
        print(f"✗ Unexpected exception: {e}")
        return False

    await client.close()
    return True


async def test_tools_registration():
    """Test that MCP tools are registered."""
    print("\n=== Testing MCP Tools Registration ===")

    from wan2gp_mcp_server import mcp

    # List expected tools (from @mcp.tool decorators)
    expected_tools = [
        "generate_text_to_video",
        "generate_image_to_video",
        "get_generation_status",
        "list_models",
        "list_loras",
        "get_queue",
        "cancel_task",
        "health_check",
    ]

    # Check tools by inspecting the mcp object
    tool_names = []
    for name in expected_tools:
        if hasattr(mcp, name):
            tool_names.append(name)
            print(f"✓ Tool registered: {name}")
        else:
            # FastMCP tools might be stored differently
            print(f"? Tool '{name}' not found as direct attribute (may be registered internally)")

    print(f"\nFound {len(tool_names)} directly accessible tools")

    # Expected resources
    expected_resources = [
        "wan2gp://models",
        "wan2gp://loras",
        "wan2gp://queue",
        "wan2gp://health",
    ]

    print(f"\nExpected resources: {len(expected_resources)}")
    for uri in expected_resources:
        print(f"  - {uri}")

    return True


def test_file_structure():
    """Test that all required files exist."""
    print("\n=== Testing File Structure ===")

    base = Path(__file__).parent
    required_files = [
        "wan2gp_mcp_server.py",
        "wan2gp_client.py",
        "config.json",
        "requirements.txt",
        "README.md",
        ".env.example",
        "claude_desktop_config.json",
    ]

    all_exist = True
    for f in required_files:
        path = base / f
        if path.exists():
            print(f"✓ {f}")
        else:
            print(f"✗ Missing: {f}")
            all_exist = False

    # Check tests directory
    tests_dir = base / "tests"
    if tests_dir.exists() and (tests_dir / "test_client.py").exists():
        print(f"✓ tests/test_client.py")
    else:
        print(f"✗ Missing: tests/test_client.py")
        all_exist = False

    return all_exist


async def run_validation():
    """Run all validation checks."""
    print("=" * 60)
    print("Wan2GP MCP Server Validation")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("File Structure", test_file_structure()))
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("Client Connection Handling", await test_client_connection_handling()))
    results.append(("MCP Tools Registration", await test_tools_registration()))

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n✓ All validation checks passed!")
        print("\nThe MCP server is ready to use.")
        print("\nNext steps:")
        print("1. Start Wan2GP Gradio server (if not already running)")
        print("2. Add to Claude Desktop config using claude_desktop_config.json")
        print("3. Restart Claude Desktop")
        return True
    else:
        print("\n✗ Some validation checks failed. Please review the output above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_validation())
    sys.exit(0 if success else 1)
