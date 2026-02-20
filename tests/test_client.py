#!/usr/bin/env python3
"""
Tests for Wan2GP Client

Run with: python tests/test_client.py

These tests require a running Wan2GP server at the configured URL.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from wan2gp_client import Wan2GPClient, Wan2GPConnectionError


async def test_health_check():
    """Test basic health check connection."""
    print("\n=== Testing Health Check ===")

    url = os.getenv("WAN2GP_URL", "http://localhost:7860")
    print(f"Connecting to: {url}")

    async with Wan2GPClient(base_url=url) as client:
        health = await client.health_check()
        print(f"Health status: {health['status']}")

        if health["status"] == "healthy":
            print(f"✓ Server is healthy!")
            print(f"  URL: {health['url']}")
            print(f"  Version: {health.get('version', 'unknown')}")
            return True
        else:
            print(f"✗ Server is unhealthy: {health.get('error', 'Unknown error')}")
            return False


async def test_list_models():
    """Test listing available models."""
    print("\n=== Testing List Models ===")

    url = os.getenv("WAN2GP_URL", "http://localhost:7860")

    async with Wan2GPClient(base_url=url) as client:
        models = await client.list_models()

        print(f"Found {len(models)} models:")
        for model in models:
            print(f"  - {model.get('name')} ({model.get('type')})")
            print(f"    Resolution: {model.get('resolution')}")
            print(f"    VRAM: {model.get('vram_requirement')}")

        return len(models) > 0


async def test_submit_t2v():
    """Test submitting a text-to-video generation."""
    print("\n=== Testing Text-to-Video Submission ===")

    url = os.getenv("WAN2GP_URL", "http://localhost:7860")

    async with Wan2GPClient(base_url=url) as client:
        print("Submitting test generation...")

        try:
            task = await client.submit_text_to_video(
                prompt="A serene mountain landscape at sunset",
                resolution="1280x720",
                video_length=49,
                num_inference_steps=20,
                guidance_scale=7.5,
                seed=42,
            )

            print(f"✓ Task submitted successfully!")
            print(f"  Task ID: {task.task_id}")
            print(f"  Status: {task.status}")
            print(f"  Progress: {task.progress}%")

            return True

        except Wan2GPConnectionError as e:
            print(f"✗ Connection error: {e}")
            return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def test_queue():
    """Test getting the current queue."""
    print("\n=== Testing Queue ===")

    url = os.getenv("WAN2GP_URL", "http://localhost:7860")

    async with Wan2GPClient(base_url=url) as client:
        queue = await client.get_queue()

        print(f"Queue length: {len(queue)}")
        for i, item in enumerate(queue[:5]):  # Show first 5
            print(f"  {i+1}. {item}")

        return True


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Wan2GP Client Tests")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Health Check", await test_health_check()))

    if results[-1][1]:  # Only run other tests if server is healthy
        results.append(("List Models", await test_list_models()))
        results.append(("Queue", await test_queue()))

        # Optional: Comment out to avoid actual generation
        # results.append(("Submit T2V", await test_submit_t2v()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
