#!/usr/bin/env python3
"""
Test the Wan2GP Proxy Server

This script tests that the proxy server is working correctly.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from wan2gp_client import Wan2GPClient, Wan2GPConnectionError, GenerationError


async def test_proxy():
    """Test the proxy server."""
    print("=" * 60)
    print("Testing Wan2GP Proxy Server")
    print("=" * 60)

    # Test health check
    print("\n1. Testing Health Check...")
    async with Wan2GPClient(base_url="http://localhost:7861") as client:
        health = await client.health_check()
        print(f"   Status: {health['status']}")
        if health['status'] == 'healthy':
            print(f"   ✓ Proxy is running!")
            print(f"   Wan2GP Path: {health.get('wan2gp_path', 'N/A')}")
        else:
            print(f"   ✗ Proxy unhealthy: {health.get('error', 'Unknown')}")
            return False

    # Test models list
    print("\n2. Testing Models List...")
    async with Wan2GPClient(base_url="http://localhost:7861") as client:
        models = await client.list_models()
        print(f"   Found {len(models)} models")
        for m in models[:5]:
            print(f"   - {m.get('name', 'Unknown')} ({m.get('type', 'N/A')})")

    # Test task submission (without actually generating - just check API)
    print("\n3. Testing Task Submission API...")
    async with Wan2GPClient(base_url="http://localhost:7861") as client:
        try:
            # This will submit to the queue but might fail if Wan2GP isn't fully loaded
            task = await client.submit_text_to_video(
                prompt="A test video",  # Minimal prompt
                resolution="640x480",
                video_length=49,
                num_inference_steps=5,  # Very low for quick test
                seed=42,
            )
            print(f"   ✓ Task submitted: {task.task_id}")
            print(f"   Status: {task.status}")

            # Wait a bit then check status
            await asyncio.sleep(2)
            status = await client.get_task_status(task.task_id)
            print(f"   Current status: {status.get('status')}")
            print(f"   Progress: {status.get('progress', 0)}%")

        except Wan2GPConnectionError as e:
            print(f"   ✗ Connection error: {e}")
            return False
        except GenerationError as e:
            # This might fail if Wan2GP isn't loaded properly
            print(f"   ⚠ Generation failed (this is OK if Wan2GP isn't fully set up):")
            print(f"      {e}")

    print("\n" + "=" * 60)
    print("✓ Proxy API tests completed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_proxy())
    sys.exit(0 if success else 1)
