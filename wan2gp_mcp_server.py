#!/usr/bin/env python3
"""
Wan2GP MCP Server

A Model Context Protocol server that provides access to Wan2GP video generation.
This server uses stdio transport for integration with Claude Desktop.

Environment Variables:
    WAN2GP_URL: Base URL of the Wan2GP Gradio server (default: http://localhost:7860)
    WAN2GP_TIMEOUT: Request timeout in seconds (default: 300)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from wan2gp_client import Wan2GPClient, Wan2GPConnectionError, GenerationError


# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wan2gp_mcp")

# Configuration
DEFAULT_CONFIG = {
    "wan2gp_url": "http://localhost:7860",
    "timeout": 300,
    "max_concurrent_tasks": 3,
    "default_model": "wan",
    "default_resolution": "1280x720",
    "output_directory": "./output",
}

# Load configuration
def load_config() -> dict[str, Any]:
    """Load configuration from file and environment variables."""
    config = DEFAULT_CONFIG.copy()

    # Load from config.json if it exists
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config.update(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load config.json: {e}")

    # Override with environment variables
    config["wan2gp_url"] = os.getenv("WAN2GP_URL", config["wan2gp_url"])
    config["timeout"] = int(os.getenv("WAN2GP_TIMEOUT", config["timeout"]))

    return config


CONFIG = load_config()

# Initialize MCP server
mcp = FastMCP("wan2gp-video-generator")

# Global client instance
_client: Optional[Wan2GPClient] = None


async def get_client() -> Wan2GPClient:
    """Get or create the Wan2GP client."""
    global _client
    if _client is None:
        _client = Wan2GPClient(
            base_url=CONFIG["wan2gp_url"],
            timeout=CONFIG["timeout"],
        )
    return _client


# =============================================================================
# Tools
# =============================================================================

@mcp.tool
async def generate_text_to_video(
    prompt: str = Field(description="Text description of the video to generate"),
    negative_prompt: str = Field(default="", description="Things to avoid in the video"),
    resolution: str = Field(default="1280x720", description="Video resolution (e.g., 1280x720, 1920x1080)"),
    video_length: int = Field(default=49, description="Number of frames (49 ≈ 2 seconds at 24fps)"),
    num_inference_steps: int = Field(default=20, description="Number of denoising steps (higher = better quality)"),
    guidance_scale: float = Field(default=7.5, description="How strongly to follow the prompt (1-20)"),
    seed: int = Field(default=-1, description="Random seed (-1 for random)"),
    model_type: str = Field(default="wan", description="Model to use (wan, hunyuan, ltx, etc.)"),
    output_filename: str = Field(default="", description="Custom output filename"),
) -> str:
    """
    Generate a video from a text description using Wan2GP.

    This tool submits a text-to-video generation task to the Wan2GP server.
    The generation runs asynchronously on the server. Check the server's output
    directory for the generated video.

    Common resolutions:
    - 1280x720 (720p) - Good quality, faster generation
    - 1920x1080 (1080p) - High quality, slower generation
    - 640x480 (480p) - Lower quality, fastest generation

    Args:
        prompt: Text description of the video to generate
        negative_prompt: Things to avoid in the video
        resolution: Video resolution (width x height)
        video_length: Number of frames (49 ≈ 2 seconds at 24fps)
        num_inference_steps: Number of denoising steps (20-50 recommended)
        guidance_scale: How strongly to follow the prompt (1-20)
        seed: Random seed (-1 for random)
        model_type: Model to use
        output_filename: Custom output filename

    Returns:
        str: Task ID and status message

    Example:
        generate_text_to_video(
            prompt="A cat walking through a sunny garden, slow motion",
            resolution="1280x720",
            num_inference_steps=25,
            guidance_scale=7.5
        )
    """
    try:
        client = await get_client()

        # Check server health first
        health = await client.health_check()
        if health["status"] != "healthy":
            return f"Error: Wan2GP server is not healthy. {health.get('error', 'Unknown error')}"

        # Submit generation
        task = await client.submit_text_to_video(
            prompt=prompt,
            negative_prompt=negative_prompt,
            resolution=resolution,
            video_length=video_length,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            model_type=model_type,
            output_filename=output_filename,
        )

        logger.info(f"Submitted T2V task: {task.task_id}")

        return (
            f"Video generation task submitted successfully.\n"
            f"Task ID: {task.task_id}\n"
            f"Prompt: {prompt}\n"
            f"Resolution: {resolution}\n"
            f"Model: {model_type}\n"
            f"\nThe video is being generated in the background. "
            f"Check the Wan2GP output directory for results."
        )

    except Wan2GPConnectionError as e:
        logger.error(f"Connection error: {e}")
        return (
            f"Error: Cannot connect to Wan2GP server at {CONFIG['wan2gp_url']}. "
            f"Please ensure Wan2GP is running."
        )
    except GenerationError as e:
        logger.error(f"Generation error: {e}")
        return f"Error: {e}"
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return f"Error: {str(e)}"


@mcp.tool
async def generate_image_to_video(
    image_path: str = Field(description="Path to the input image"),
    prompt: str = Field(description="How the image should animate/move"),
    negative_prompt: str = Field(default="", description="Things to avoid in the video"),
    motion_scale: float = Field(default=1.0, description="How much motion to generate (0.5-2.0)"),
    video_length: int = Field(default=49, description="Number of frames (49 ≈ 2 seconds at 24fps)"),
    num_inference_steps: int = Field(default=20, description="Number of denoising steps"),
    guidance_scale: float = Field(default=7.5, description="How strongly to follow the prompt (1-20)"),
    seed: int = Field(default=-1, description="Random seed (-1 for random)"),
    model_type: str = Field(default="wan_i2v", description="Model to use (typically an I2V variant)"),
) -> str:
    """
    Generate a video from an input image using Wan2GP.

    This tool takes a static image and animates it based on your prompt.
    The motion_scale parameter controls how much movement is generated.

    Args:
        image_path: Path to the input image
        prompt: How the image should animate/move
        negative_prompt: Things to avoid in the video
        motion_scale: How much motion to generate (0.5-2.0)
        video_length: Number of frames
        num_inference_steps: Number of denoising steps
        guidance_scale: How strongly to follow the prompt
        seed: Random seed (-1 for random)
        model_type: Model to use

    Returns:
        str: Task ID and status message

    Example:
        generate_image_to_video(
            image_path="/path/to/image.jpg",
            prompt="Camera slowly zooms in, clouds drift across the sky",
            motion_scale=1.2
        )
    """
    try:
        client = await get_client()

        # Check server health first
        health = await client.health_check()
        if health["status"] != "healthy":
            return f"Error: Wan2GP server is not healthy. {health.get('error', 'Unknown error')}"

        # Validate image path
        if not Path(image_path).exists():
            return f"Error: Image file not found: {image_path}"

        # Submit generation
        task = await client.submit_image_to_video(
            image_path=image_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            motion_scale=motion_scale,
            video_length=video_length,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            model_type=model_type,
        )

        logger.info(f"Submitted I2V task: {task.task_id}")

        return (
            f"Image-to-video generation task submitted successfully.\n"
            f"Task ID: {task.task_id}\n"
            f"Image: {image_path}\n"
            f"Prompt: {prompt}\n"
            f"Motion scale: {motion_scale}\n"
            f"\nThe video is being generated in the background. "
            f"Check the Wan2GP output directory for results."
        )

    except Wan2GPConnectionError as e:
        logger.error(f"Connection error: {e}")
        return (
            f"Error: Cannot connect to Wan2GP server at {CONFIG['wan2gp_url']}. "
            f"Please ensure Wan2GP is running."
        )
    except GenerationError as e:
        logger.error(f"Generation error: {e}")
        return f"Error: {e}"
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return f"Error: {str(e)}"


@mcp.tool
async def get_generation_status(
    task_id: str = Field(description="The task ID to check"),
) -> dict[str, Any]:
    """
    Check the status of a video generation task.

    Args:
        task_id: The task ID returned from generate_text_to_video or generate_image_to_video

    Returns:
        dict with keys: status, progress, output_path (if completed)

    Note: Task status tracking depends on Wan2GP's queue API availability.
    """
    try:
        client = await get_client()

        status = await client.get_task_status(task_id)

        return {
            "task_id": task_id,
            "status": status.get("status", "unknown"),
            "progress": status.get("progress", 0),
            "output_path": status.get("output_path"),
            "message": f"Task {task_id} is {status.get('status', 'unknown')}",
        }

    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
        }


@mcp.tool
async def list_models() -> list[dict[str, Any]]:
    """
    List all available video generation models in Wan2GP.

    Returns:
        List of model dicts with: name, type, resolution, vram_requirement

    Example output:
    [
        {
            "name": "Wan2.1 T2V",
            "id": "t2v_2_2",
            "type": "text_to_video",
            "resolution": "480p-8K",
            "vram_requirement": "16GB+"
        },
        ...
    ]
    """
    try:
        client = await get_client()

        health = await client.health_check()
        if health["status"] != "healthy":
            logger.warning(f"Server unhealthy when listing models: {health}")
            # Return cached models anyway
            return await client.list_models()

        models = await client.list_models()
        return models

    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return []


@mcp.tool
async def list_loras() -> list[dict[str, Any]]:
    """
    List available LoRA adapters for style transfer.

    Returns:
        List of LoRA dicts with: name, path, type
    """
    try:
        client = await get_client()

        health = await client.health_check()
        if health["status"] != "healthy":
            logger.warning(f"Server unhealthy when listing LoRAs: {health}")
            return []

        loras = await client.list_loras()
        return loras

    except Exception as e:
        logger.error(f"Error listing LoRAs: {e}")
        return []


@mcp.tool
async def get_queue() -> list[dict[str, Any]]:
    """
    Get the current generation queue from Wan2GP.

    Returns:
        List of queued tasks with their IDs and parameters
    """
    try:
        client = await get_client()

        queue = await client.get_queue()
        return queue

    except Exception as e:
        logger.error(f"Error getting queue: {e}")
        return []


@mcp.tool
async def cancel_task(
    task_id: str = Field(description="The task ID to cancel"),
) -> bool:
    """
    Cancel a queued generation task.

    Args:
        task_id: The task ID to cancel

    Returns:
        bool: True if cancelled successfully, False otherwise
    """
    try:
        client = await get_client()

        result = await client.cancel_task(task_id)
        return result

    except Exception as e:
        logger.error(f"Error cancelling task: {e}")
        return False


@mcp.tool
async def health_check() -> dict[str, Any]:
    """
    Check if Wan2GP server is running and accessible.

    Returns:
        dict with: status (healthy/unhealthy), url, version

    Example output:
    {
        "status": "healthy",
        "url": "http://localhost:7860",
        "version": "10.951"
    }
    """
    try:
        client = await get_client()

        health = await client.health_check()
        return health

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "url": CONFIG["wan2gp_url"],
            "error": str(e),
        }


# =============================================================================
# Resources
# =============================================================================

@mcp.resource("wan2gp://models")
async def resource_models() -> str:
    """List available models as a resource."""
    models = await list_models()
    return json.dumps(models, indent=2)


@mcp.resource("wan2gp://loras")
async def resource_loras() -> str:
    """List available LoRAs as a resource."""
    loras = await list_loras()
    return json.dumps(loras, indent=2)


@mcp.resource("wan2gp://queue")
async def resource_queue() -> str:
    """Get current queue as a resource."""
    queue = await get_queue()
    return json.dumps(queue, indent=2)


@mcp.resource("wan2gp://health")
async def resource_health() -> str:
    """Get server health status as a resource."""
    health = await health_check()
    return json.dumps(health, indent=2)


# =============================================================================
# Server Entry Point
# =============================================================================

def main():
    """Main entry point for the MCP server."""
    logger.info(f"Starting Wan2GP MCP Server")
    logger.info(f"Wan2GP URL: {CONFIG['wan2gp_url']}")
    logger.info(f"Timeout: {CONFIG['timeout']}s")

    # Run the MCP server with stdio transport
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
