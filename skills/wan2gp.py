#!/usr/bin/env python3
"""
Wan2GP Video Generation Skill

This skill provides convenient access to Wan2GP video generation capabilities
through the MCP server, with automatic GPU detection and VRAM management.

Usage:
    skill: wan2gp-generate "A cat walking in a garden"
    skill: wan2gp-status <task_id>
    skill: wan2gp-gpu-info
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path

# Add MCP server to path
sys.path.insert(0, str(Path(__file__).parent))

from wan2gp_client import Wan2GPClient, Wan2GPConnectionError, GenerationError


# Default configuration
DEFAULT_URL = os.environ.get("WAN2GP_URL", "http://localhost:7861")
DEFAULT_RESOLUTION = "1280x720"
DEFAULT_STEPS = 20
DEFAULT_GUIDANCE = 7.5


def get_gpu_info():
    """
    Detect GPU and VRAM information.

    Returns dict with:
        - gpu_available: bool
        - gpu_name: str
        - vram_total_mb: int
        - vram_free_mb: int
        - recommended_profile: int
        - recommended_resolution: str
        - max_video_length: int
    """
    info = {
        "gpu_available": False,
        "gpu_name": "None",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
        "recommended_profile": 4,
        "recommended_resolution": "720x480",
        "max_video_length": 49
    }

    # Try nvidia-smi first (more reliable)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 3:
                info["gpu_available"] = True
                info["gpu_name"] = parts[0]
                info["vram_total_mb"] = int(parts[1])
                info["vram_free_mb"] = int(parts[2])
    except Exception as e:
        # Fall back to PyTorch
        try:
            import torch
            if torch.cuda.is_available():
                info["gpu_available"] = True
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["vram_total_mb"] = torch.cuda.get_device_properties(0).total_memory // (1024*1024)
                info["vram_free_mb"] = info["vram_total_mb"] - (torch.cuda.memory_allocated(0) // (1024*1024))
        except:
            pass

    # Determine safe settings based on VRAM
    vram = info["vram_total_mb"]

    if vram >= 24000:  # 24GB+ (high-end cards like RTX 4090, A6000, RTX 3090, etc.)
        info["recommended_profile"] = 0  # High quality
        info["recommended_resolution"] = "1920x1080"
        info["max_video_length"] = 169
    elif vram >= 16000:  # 16GB+ (RTX 4080, etc.)
        info["recommended_profile"] = 2  # Balanced
        info["recommended_resolution"] = "1280x720"
        info["max_video_length"] = 121
    elif vram >= 12000:  # 12GB+ (RTX 3080 Ti, etc.)
        info["recommended_profile"] = 3  # Medium
        info["recommended_resolution"] = "1280x720"
        info["max_video_length"] = 97
    elif vram >= 8000:  # 8GB+ (RTX 3070, etc.)
        info["recommended_profile"] = 4  # Low
        info["recommended_resolution"] = "720x480"
        info["max_video_length"] = 73
    elif vram >= 6000:  # 6GB+ (RTX 2060, etc.)
        info["recommended_profile"] = 5  # Very Low
        info["recommended_resolution"] = "512x512"
        info["max_video_length"] = 49
    else:  # < 6GB or CPU
        info["recommended_profile"] = 5
        info["recommended_resolution"] = "512x512"
        info["max_video_length"] = 25

    return info


def get_safe_settings_override(prompt: str, model_type: str = "t2v_2_2") -> dict:
    """
    Get safe generation settings based on GPU VRAM.

    Returns dict with recommended parameter overrides.
    """
    gpu_info = get_gpu_info()

    settings = {
        "override_profile": gpu_info["recommended_profile"],
        "resolution": gpu_info["recommended_resolution"],
        "video_length": min(49, gpu_info["max_video_length"]),
    }

    # For very low VRAM, reduce steps
    if gpu_info["vram_total_mb"] < 8000:
        settings["num_inference_steps"] = 10
        settings["guidance_scale"] = 4.0

    return settings


async def gpu_info() -> str:
    """
    Get GPU and VRAM information.

    Returns:
        GPU information string

    Examples:
        gpu_info()
    """
    info = get_gpu_info()

    return f"""GPU Information:
{'✅' if info['gpu_available'] else '❌'} GPU Available: {info['gpu_available']}
GPU Name: {info['gpu_name']}
VRAM Total: {info['vram_total_mb']} MB ({info['vram_total_mb']/1024:.1f} GB)
VRAM Free: {info['vram_free_mb']} MB ({info['vram_free_mb']/1024:.1f} GB)

Recommended Settings:
  Profile: {info['recommended_profile']} ({'High Quality' if info['recommended_profile'] <= 2 else 'Optimized'})
  Resolution: {info['recommended_resolution']}
  Max Video Length: {info['max_video_length']} frames
"""


async def generate_video(
    prompt: str,
    resolution: str = DEFAULT_RESOLUTION,
    video_length: int = 49,
    steps: int = DEFAULT_STEPS,
    guidance: float = DEFAULT_GUIDANCE,
    seed: int = -1,
    model: str = "wan",
    negative_prompt: str = "",
    base_url: str = DEFAULT_URL
) -> str:
    """
    Generate a video from a text description.

    Args:
        prompt: Text description of the video
        resolution: Video resolution (e.g., "1280x720", "1920x1080")
        video_length: Number of frames (49 ≈ 2 seconds)
        steps: Number of inference steps (20-50)
        guidance: How strongly to follow prompt (1-20)
        seed: Random seed (-1 for random)
        model: Model to use (wan, hunyuan, ltx)
        negative_prompt: Things to avoid
        base_url: MCP server URL

    Returns:
        Task ID and status message

    Examples:
        generate_video("A cat walking in a garden")
        generate_video("Sunset over mountains", resolution="1920x1080", steps=30)
    """
    client = Wan2GPClient(base_url=base_url)

    try:
        task = await client.submit_text_to_video(
            prompt=prompt,
            resolution=resolution,
            video_length=video_length,
            num_inference_steps=steps,
            guidance_scale=guidance,
            seed=seed,
            model_type=model,
            negative_prompt=negative_prompt
        )

        return f"""Video generation task submitted!

Task ID: {task.task_id}
Prompt: {prompt}
Resolution: {resolution}
Model: {model}

The video is being generated in the background.
Use: skill: wan2gp-status {task.task_id}
"""

    finally:
        await client.close()


async def check_status(task_id: str, base_url: str = DEFAULT_URL) -> str:
    """
    Check the status of a video generation task.

    Args:
        task_id: The task ID returned from wan2gp-generate
        base_url: MCP server URL

    Returns:
        Status information

    Examples:
        check_status("proxy_1739956800123")
    """
    client = Wan2GPClient(base_url=base_url)

    try:
        status = await client.get_task_status(task_id)

        if status.get("status") == "completed":
            return f"""✓ Generation completed!

Task ID: {task_id}
Output: {status.get('output_path', 'Unknown')}
"""
        elif status.get("status") == "failed":
            return f"""✗ Generation failed!

Task ID: {task_id}
Error: {status.get('error', 'Unknown error')}
"""
        elif status.get("status") == "processing":
            return f"""⏳ Processing...

Task ID: {task_id}
Progress: {status.get('progress', 0)}%
"""
        else:
            return f"""Task ID: {task_id}
Status: {status.get('status', 'unknown')}
"""

    finally:
        await client.close()


async def list_models(base_url: str = DEFAULT_URL) -> str:
    """
    List available video generation models.

    Args:
        base_url: MCP server URL

    Returns:
        List of available models

    Examples:
        list_models()
    """
    client = Wan2GPClient(base_url=base_url)

    try:
        models = await client.list_models()

        result = f"Available models ({len(models)}):\n\n"
        for m in models[:20]:  # Show first 20
            result += f"• {m.get('name', 'Unknown')} ({m.get('type', 'N/A')})\n"

        if len(models) > 20:
            result += f"\n... and {len(models) - 20} more"

        return result

    finally:
        await client.close()


async def health_check(base_url: str = DEFAULT_URL) -> str:
    """
    Check if Wan2GP server is healthy.

    Args:
        base_url: MCP server URL

    Returns:
        Health status

    Examples:
        health_check()
    """
    client = Wan2GPClient(base_url=base_url)

    try:
        health = await client.health_check()

        if health["status"] == "healthy":
            return f"""✓ Wan2GP is healthy!

Path: {health.get('wan2gp_path', 'Unknown')}
Version: {health.get('version', 'Unknown')}
"""
        else:
            return f"""✗ Wan2GP is unhealthy!

Error: {health.get('error', 'Unknown')}
"""

    finally:
        await client.close()


# Main entry point for skill execution
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Wan2GP Video Generation")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a video")
    gen_parser.add_argument("prompt", help="Video description")
    gen_parser.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    gen_parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    gen_parser.add_argument("--guidance", type=float, default=DEFAULT_GUIDANCE)
    gen_parser.add_argument("--seed", type=int, default=-1)
    gen_parser.add_argument("--model", default="wan")
    gen_parser.add_argument("--negative", default="")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check task status")
    status_parser.add_argument("task_id", help="Task ID to check")

    # Models command
    subparsers.add_parser("models", help="List available models")

    # GPU info command
    subparsers.add_parser("gpu-info", help="Show GPU and VRAM information")

    # Health command
    subparsers.add_parser("health", help="Check server health")

    args = parser.parse_args()

    # Execute command
    if args.command == "generate":
        result = asyncio.run(generate_video(
            prompt=args.prompt,
            resolution=args.resolution,
            steps=args.steps,
            guidance=args.guidance,
            seed=args.seed,
            model=args.model,
            negative_prompt=args.negative
        ))
    elif args.command == "status":
        result = asyncio.run(check_status(args.task_id))
    elif args.command == "models":
        result = asyncio.run(list_models())
    elif args.command == "gpu-info":
        result = asyncio.run(gpu_info())
    elif args.command == "health":
        result = asyncio.run(health_check())
    else:
        parser.print_help()
        sys.exit(1)

    print(result)
