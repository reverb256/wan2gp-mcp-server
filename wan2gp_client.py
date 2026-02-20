"""
Wan2GP Proxy Client

This module provides an async HTTP client for communicating with the Wan2GP Proxy server.
The proxy server handles the complex Wan2GP Gradio interface, providing a simple REST API.
"""

import asyncio
import time
from typing import Any, Optional
from dataclasses import dataclass

import httpx


class GenerationError(Exception):
    """Exception raised when generation fails."""
    pass


class Wan2GPConnectionError(Exception):
    """Exception raised when connection to Wan2GP proxy fails."""
    pass


@dataclass
class GenerationTask:
    """Represents a video generation task."""
    task_id: str
    status: str  # queued, processing, completed, failed
    progress: float  # 0-100
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = None

    # Memory-safe defaults for 32GB RAM systems
    DEFAULT_RESOLUTION = "720x480"  # Instead of 1280x720
    DEFAULT_VIDEO_LENGTH = 49       # ~2 seconds
    DEFAULT_STEPS = 15              # Instead of 20
    DEFAULT_GUIDANCE = 5.0          # Instead of 7.5
    DEFAULT_PROFILE = 4             # Low quality profile - saves RAM

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class Wan2GPClient:
    """
    Async HTTP client for Wan2GP Proxy server.

    The proxy server provides a simple REST API that wraps Wan2GP's
    generate_video function, avoiding the complexity of Gradio's
    state management.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7861",
        timeout: float = 300.0,
    ):
        """
        Initialize the Wan2GP client.

        Args:
            base_url: Base URL of the Wan2GP Proxy server (default: localhost:7861)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> dict[str, Any]:
        """
        Check if Wan2GP proxy server is accessible.

        Returns:
            dict with: status (healthy/unhealthy), url, version
        """
        try:
            await self._ensure_client()
            response = await self._client.get(f"{self.base_url}/health")

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "unhealthy",
                    "url": self.base_url,
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "url": self.base_url,
                "error": str(e),
            }

    async def submit_text_to_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        resolution: str = "1280x720",
        video_length: int = 49,
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        seed: int = -1,
        model_type: str = "wan",
        output_filename: str = "",
        **kwargs
    ) -> GenerationTask:
        """
        Submit a text-to-video generation task.

        Args:
            prompt: Text description of the video
            negative_prompt: Things to avoid in the video
            resolution: Video resolution (e.g., "1280x720")
            video_length: Number of frames
            num_inference_steps: Number of denoising steps
            guidance_scale: How strongly to follow the prompt
            seed: Random seed (-1 for random)
            model_type: Model to use
            output_filename: Custom output filename
            **kwargs: Additional generation parameters

        Returns:
            GenerationTask with task_id and initial status

        Raises:
            Wan2GPConnectionError: If server is unreachable
            GenerationError: If submission fails
        """
        await self._ensure_client()

        # Build request payload for proxy
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "resolution": resolution,
            "video_length": video_length,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "model_type": model_type,
            "image_mode": "T2V",
            "output_filename": output_filename or f"t2v_{int(time.time())}",
            # Merge additional kwargs
            **kwargs
        }

        try:
            response = await self._client.post(
                f"{self.base_url}/generate",
                json=payload,
            )

            if response.status_code == 202:
                # Task accepted
                result = response.json()
                return GenerationTask(
                    task_id=result["task_id"],
                    status="queued",
                    progress=0.0,
                )
            else:
                raise GenerationError(
                    f"Failed to submit T2V generation: HTTP {response.status_code} - {response.text}"
                )

        except httpx.ConnectError as e:
            raise Wan2GPConnectionError(
                f"Cannot connect to Wan2GP proxy server at {self.base_url}. "
                f"Please ensure the proxy server is running."
            ) from e
        except Exception as e:
            raise GenerationError(f"Failed to submit T2V generation: {e}") from e

    async def submit_image_to_video(
        self,
        image_path: str,
        prompt: str,
        negative_prompt: str = "",
        motion_scale: float = 1.0,
        video_length: int = 49,
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        seed: int = -1,
        model_type: str = "wan_i2v",
        **kwargs
    ) -> GenerationTask:
        """
        Submit an image-to-video generation task.

        Args:
            image_path: Path to the input image
            prompt: How the image should animate/move
            negative_prompt: Things to avoid in the video
            motion_scale: How much motion to generate (0.5-2.0)
            video_length: Number of frames
            num_inference_steps: Number of denoising steps
            guidance_scale: How strongly to follow the prompt
            seed: Random seed (-1 for random)
            model_type: Model to use (typically an I2V variant)
            **kwargs: Additional generation parameters

        Returns:
            GenerationTask with task_id and initial status
        """
        await self._ensure_client()

        # Build request payload for proxy
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "resolution": kwargs.get("resolution", "1280x720"),
            "video_length": video_length,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "model_type": model_type,
            "image_mode": "I2V_Start",
            "input_video_strength": motion_scale,
            "motion_amplitude": motion_scale,
            "image_start": image_path,
            "output_filename": kwargs.get("output_filename", f"i2v_{int(time.time())}"),
            # Merge additional kwargs
            **{k: v for k, v in kwargs.items() if k != "output_filename"}
        }

        try:
            response = await self._client.post(
                f"{self.base_url}/generate",
                json=payload,
            )

            if response.status_code == 202:
                # Task accepted
                result = response.json()
                return GenerationTask(
                    task_id=result["task_id"],
                    status="queued",
                    progress=0.0,
                )
            else:
                raise GenerationError(
                    f"Failed to submit I2V generation: HTTP {response.status_code} - {response.text}"
                )

        except httpx.ConnectError as e:
            raise Wan2GPConnectionError(
                f"Cannot connect to Wan2GP proxy server at {self.base_url}"
            ) from e
        except Exception as e:
            raise GenerationError(f"Failed to submit I2V generation: {e}") from e

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Get the status of a generation task.

        Args:
            task_id: The task ID to check

        Returns:
            dict with: status, progress, output_path (if completed)
        """
        await self._ensure_client()

        try:
            response = await self._client.get(f"{self.base_url}/status/{task_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {
                    "task_id": task_id,
                    "status": "unknown",
                    "error": "Task not found"
                }
            else:
                return {
                    "task_id": task_id,
                    "status": "error",
                    "error": f"HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e)
            }

    async def get_queue(self) -> list[dict[str, Any]]:
        """
        Get the current generation queue.

        Returns:
            List of all tasks with their status
        """
        await self._ensure_client()

        try:
            response = await self._client.get(f"{self.base_url}/queue")

            if response.status_code == 200:
                data = response.json()
                return data.get("tasks", [])
            else:
                return []

        except Exception as e:
            return []

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a queued generation task.

        Note: This is not currently implemented in the proxy.

        Args:
            task_id: The task ID to cancel

        Returns:
            True if cancelled successfully
        """
        # TODO: Implement cancel endpoint in proxy
        return False

    async def list_models(self) -> list[dict[str, Any]]:
        """
        List available video generation models.

        Returns:
            List of model dicts with name, type, path
        """
        await self._ensure_client()

        try:
            response = await self._client.get(f"{self.base_url}/models")

            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
            else:
                # Return default models if endpoint fails
                return [
                    {
                        "name": "Wan2.1 T2V",
                        "type": "checkpoint",
                        "path": "wan2.1"
                    },
                    {
                        "name": "Hunyuan Video",
                        "type": "checkpoint",
                        "path": "hunyuan"
                    },
                ]

        except Exception:
            # Return defaults on error
            return [
                {
                    "name": "Wan2.1 T2V",
                    "type": "checkpoint",
                    "path": "wan2.1"
                }
            ]

    async def list_loras(self) -> list[dict[str, Any]]:
        """
        List available LoRA adapters.

        Returns:
            List of LoRA dicts with name, path, type
        """
        await self._ensure_client()

        try:
            response = await self._client.get(f"{self.base_url}/loras")

            if response.status_code == 200:
                data = response.json()
                return data.get("loras", [])
            else:
                return []

        except Exception:
            return []

    async def download_result(self, file_path: str, output_path: str) -> str:
        """
        Download a generated video from the server.

        Note: For the proxy, videos are saved locally, so this is
        just a pass-through or file copy operation.

        Args:
            file_path: Path on the server
            output_path: Local path to save the file

        Returns:
            Local path to the downloaded file
        """
        # For local proxy, files are already on disk
        # Just verify the file exists
        from pathlib import Path

        if Path(file_path).exists():
            return file_path
        else:
            raise GenerationError(f"File not found: {file_path}")
