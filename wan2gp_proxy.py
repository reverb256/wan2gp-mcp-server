#!/usr/bin/env python3
"""
Wan2GP HTTP Proxy Server

This server provides a simple HTTP API for Wan2GP by directly importing
the generate_video function, avoiding the complexity of Gradio's state
management.

Run this server alongside the Wan2GP Gradio interface.

Usage:
    python wan2gp_proxy.py

The proxy will run on http://localhost:7861 (default)
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

# Add Wan2GP to path
WAN2GP_PATH = os.environ.get(
    "WAN2GP_PATH",
    "/data/StabilityMatrix/Packages/Wan2GP"
)
if WAN2GP_PATH not in sys.path:
    sys.path.insert(0, WAN2GP_PATH)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("wan2gp_proxy")

# Configuration
PROXY_PORT = int(os.environ.get("WAN2GP_PROXY_PORT", 7861))
PROXY_HOST = os.environ.get("WAN2GP_PROXY_HOST", "127.0.0.1")

# Task storage
_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = asyncio.Lock()

# Initialize Flask
app = Flask(__name__)
CORS(app)


_wan2gp_imported = False
_generate_video_func = None

def import_wan2gp():
    """Import Wan2GP's generate_video function (cached)."""
    global _wan2gp_imported, _generate_video_func
    if _wan2gp_imported:
        return _generate_video_func

    try:
        # FIX: Disable setuptools distutils hack that conflicts with StabilityMatrix
        import sys
        if '_distutils_hack' in sys.modules:
            del sys.modules['_distutils_hack']
        if 'setuptools._distutils_hack' in sys.modules:
            del sys.modules['setuptools._distutils_hack']
        import os
        os.environ['SETUPTOOLS_USE_DISTUTILS'] = 'local'

        # Change to Wan2GP directory for imports
        old_cwd = os.getcwd()
        os.chdir(WAN2GP_PATH)

        # Import from wgp
        import wgp
        _generate_video_func = wgp.generate_video
        _wan2gp_imported = True

        # Restore working directory
        os.chdir(old_cwd)

        logger.info("Successfully imported generate_video from Wan2GP")
        return _generate_video_func
    except ImportError as e:
        logger.error(f"Failed to import Wan2GP: {e}")
        logger.error(f"Make sure WAN2GP_PATH is correct: {WAN2GP_PATH}")
        return None
    except Exception as e:
        # Import might have other issues during initialization
        logger.error(f"Error importing Wan2GP: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def get_output_directory():
    """Get Wan2GP's output directory."""
    config_path = Path(WAN2GP_PATH) / "wgp_config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
            return config.get("save_path", "outputs")
    return "outputs"


def list_models():
    """List available models in Wan2GP."""
    models = []

    # Check checkpoints directory
    ckpt_path = Path(WAN2GP_PATH) / "ckpts"
    if ckpt_path.exists():
        for file in ckpt_path.rglob("*.safetensors"):
            rel_path = file.relative_to(ckpt_path)
            models.append({
                "name": file.stem,
                "path": str(rel_path),
                "type": "checkpoint"
            })

    # Check models directory
    models_path = Path(WAN2GP_PATH) / "models"
    if models_path.exists():
        for file in models_path.rglob("*.safetensors"):
            rel_path = file.relative_to(models_path)
            models.append({
                "name": file.stem,
                "path": str(rel_path),
                "type": "model"
            })

    # Also check the defaults directory
    defaults_path = Path(WAN2GP_PATH) / "defaults"
    if defaults_path.exists():
        for file in defaults_path.rglob("*.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                    if "model" in data:
                        models.append({
                            "name": data.get("name", file.stem),
                            "model": data["model"],
                            "type": "preset"
                        })
            except:
                pass

    return models


def list_loras():
    """List available LoRAs."""
    loras = []

    # Check loras directory
    loras_path = Path(WAN2GP_PATH) / "loras"
    if loras_path.exists():
        for file in loras_path.rglob("*.safetensors"):
            rel_path = file.relative_to(loras_path)
            loras.append({
                "name": file.stem,
                "path": str(rel_path),
                "type": "lora"
            })

    return loras


async def run_generation(task_id: str, params: Dict[str, Any]):
    """Run generation in background task."""
    try:
        generate_video = import_wan2gp()
        if generate_video is None:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = "Could not import Wan2GP"
            return

        # Update task status
        _tasks[task_id]["status"] = "processing"
        _tasks[task_id]["progress"] = 0
        _tasks[task_id]["started_at"] = time.time()

        logger.info(f"Starting generation for task {task_id}")

        # Create a simple command sender to capture status
        status_updates = []

        def send_cmd(cmd, data=None):
            """Capture status updates from generation."""
            if cmd == "progress":
                status_updates.append(data)
                # Update progress in task
                if isinstance(data, list) and len(data) >= 2:
                    _tasks[task_id]["progress"] = data[0]  # progress value
            elif cmd == "status":
                logger.info(f"Task {task_id} status: {data}")

        # Create state dict with required fields
        state = {
            "gen": {
                "queue": [],
                "in_progress": False,
                "progress_phase": ("Initializing", 0),
                "file_list": [],
                "file_settings_list": [],
                "audio_file_list": [],
                "audio_file_settings_list": [],
                "selected": 0,
                "audio_selected": 0,
                "prompt_no": 0,
                "prompts_max": 0,
                "repeat_no": 0,
                "total_generation": 1,
                "window_no": 0,
                "total_windows": 0,
                "progress_status": "",
                "process_status": "process:main",
            },
            "loras": [],
        }

        # Call generate_video with parameters
        # Note: We need to map our simplified params to the full signature
        # image_mode: 0=T2V, 1=T2I/I2V, 2=inpaint
        image_mode_value = params.get("image_mode", "T2V")
        if isinstance(image_mode_value, str):
            image_mode_map = {"T2V": 0, "I2V": 1, "T2I": 1, "inpaint": 2}
            image_mode_value = image_mode_map.get(image_mode_value, 0)

        # Handle resolution - extract value from Gradio update dict if needed
        resolution_value = params.get("resolution", {"__type__": "update", "value": "1280x720"})
        if isinstance(resolution_value, dict) and "value" in resolution_value:
            resolution_value = resolution_value["value"]

        # WORKAROUND: Wan2GP expects a global 'app' object from Gradio
        # We inject a dummy object to prevent NameError
        import wgp
        if not hasattr(wgp, 'app'):
            # Create a dummy app with plugin_manager that has run_data_hooks method
            class DummyPluginManager:
                def run_data_hooks(self, hook_name, configs=None, plugin_data=None, model_type=None, **kwargs):
                    # Return configs unchanged - no plugins to process
                    return configs if configs is not None else {}

            class DummyApp:
                def __init__(self):
                    self.plugin_manager = DummyPluginManager()

            wgp.app = DummyApp()

        try:
            result = await asyncio.to_thread(
                generate_video,
                task=params.get("task", ""),
                send_cmd=send_cmd,
                image_mode=image_mode_value,
                prompt=params.get("prompt", ""),
                alt_prompt=params.get("alt_prompt", ""),
                negative_prompt=params.get("negative_prompt", ""),
                resolution=resolution_value,
                video_length=params.get("video_length", 49),
                duration_seconds=params.get("duration_seconds", 2.0),
                pause_seconds=params.get("pause_seconds", 0.0),
                batch_size=params.get("batch_size", 1),
                seed=params.get("seed", -1),
                force_fps=params.get("force_fps", ""),  # Empty string = Model Default
                num_inference_steps=params.get("num_inference_steps", 20),
                guidance_scale=params.get("guidance_scale", 7.5),
                guidance2_scale=params.get("guidance2_scale", 0.0),
                guidance3_scale=params.get("guidance3_scale", 0.0),
                switch_threshold=params.get("switch_threshold", 0.5),
                switch_threshold2=params.get("switch_threshold2", 0.5),
                guidance_phases=params.get("guidance_phases", 1),  # 1 = One Phase
                model_switch_phase=params.get("model_switch_phase", 0.5),
                alt_guidance_scale=params.get("alt_guidance_scale", 0.0),
                audio_guidance_scale=params.get("audio_guidance_scale", 0.0),
                audio_scale=params.get("audio_scale", 0.0),
                flow_shift=params.get("flow_shift", 0.0),
                sample_solver=params.get("sample_solver", "euler"),
                embedded_guidance_scale=params.get("embedded_guidance_scale", 0.0),
                repeat_generation=params.get("repeat_generation", 1),
                multi_prompts_gen_type=params.get("multi_prompts_gen_type", "sequential"),
                multi_images_gen_type=params.get("multi_images_gen_type", "sequential"),
                skip_steps_cache_type=params.get("skip_steps_cache_type", ""),  # Empty string = no cache
                skip_steps_multiplier=params.get("skip_steps_multiplier", 1.0),
                skip_steps_start_step_perc=params.get("skip_steps_start_step_perc", 0.0),
                activated_loras=params.get("activated_loras", []),
                loras_multipliers=params.get("loras_multipliers", {}),
                image_prompt_type=params.get("image_prompt_type", ""),  # Empty string = no image prompt
                image_start=params.get("image_start", None),
                image_end=params.get("image_end", None),
                model_mode=params.get("model_mode", "wan"),
                video_source=params.get("video_source", None),
                keep_frames_video_source=params.get("keep_frames_video_source", ""),  # Empty string = keep all frames
                input_video_strength=params.get("input_video_strength", 0.8),
                video_prompt_type=params.get("video_prompt_type", ""),  # Empty string = no video prompt
                image_refs=params.get("image_refs", []),
                frames_positions=params.get("frames_positions", []),
                video_guide=params.get("video_guide", None),
                image_guide=params.get("image_guide", None),
                keep_frames_video_guide=params.get("keep_frames_video_guide", ""),  # Empty string = keep all frames
                denoising_strength=params.get("denoising_strength", 0.8),
                masking_strength=params.get("masking_strength", 1.0),
                video_guide_outpainting=params.get("video_guide_outpainting", ""),  # Empty string = no outpainting
                video_mask=params.get("video_mask", None),
                image_mask=params.get("image_mask", None),
                control_net_weight=params.get("control_net_weight", 1.0),
                control_net_weight2=params.get("control_net_weight2", 1.0),
                control_net_weight_alt=params.get("control_net_weight_alt", 0.0),
                motion_amplitude=params.get("motion_amplitude", 1.0),
                mask_expand=params.get("mask_expand", 4),
                audio_guide=params.get("audio_guide", None),
                audio_guide2=params.get("audio_guide2", None),
                custom_guide=params.get("custom_guide", None),
                audio_source=params.get("audio_source", None),
                audio_prompt_type=params.get("audio_prompt_type", ""),  # Empty string = no audio prompt
                speakers_locations=params.get("speakers_locations", []),
                sliding_window_size=params.get("sliding_window_size", 0),
                sliding_window_overlap=params.get("sliding_window_overlap", 0),
                sliding_window_color_correction_strength=params.get("sliding_window_color_correction_strength", 0.0),
                sliding_window_overlap_noise=params.get("sliding_window_overlap_noise", 0.0),
                sliding_window_discard_last_frames=params.get("sliding_window_discard_last_frames", False),
                image_refs_relative_size=params.get("image_refs_relative_size", 1.0),
                remove_background_images_ref=params.get("remove_background_images_ref", False),
                temporal_upsampling=params.get("temporal_upsampling", ""),  # Empty string = Disabled
                spatial_upsampling=params.get("spatial_upsampling", ""),  # Empty string = Disabled
                film_grain_intensity=params.get("film_grain_intensity", 0.0),
                film_grain_saturation=params.get("film_grain_saturation", 0.0),
                MMAudio_setting=params.get("MMAudio_setting", 0),
                MMAudio_prompt=params.get("MMAudio_prompt", ""),
                MMAudio_neg_prompt=params.get("MMAudio_neg_prompt", ""),
                RIFLEx_setting=params.get("RIFLEx_setting", 0),
                NAG_scale=params.get("NAG_scale", 0.0),
                NAG_tau=params.get("NAG_tau", 1.0),
                NAG_alpha=params.get("NAG_alpha", 0.0),
                slg_switch=params.get("slg_switch", False),
                slg_layers=params.get("slg_layers", []),
                slg_start_perc=params.get("slg_start_perc", 0.0),
                slg_end_perc=params.get("slg_end_perc", 1.0),
                apg_switch=params.get("apg_switch", False),
                cfg_star_switch=params.get("cfg_star_switch", False),
                cfg_zero_step=params.get("cfg_zero_step", 0),
                prompt_enhancer=params.get("prompt_enhancer", 0),
                min_frames_if_references=params.get("min_frames_if_references", 0),
                override_profile=params.get("override_profile", -1),
                override_attention=params.get("override_attention", ""),  # Keep as empty string for now
                temperature=params.get("temperature", 1.0),
                custom_settings=params.get("custom_settings", {}),
                top_p=params.get("top_p", 1.0),
                top_k=params.get("top_k", 200),
                self_refiner_setting=params.get("self_refiner_setting", 0),  # 0 = Disabled
                self_refiner_plan=params.get("self_refiner_plan", []),
                self_refiner_f_uncertainty=params.get("self_refiner_f_uncertainty", 0.5),
                self_refiner_certain_percentage=params.get("self_refiner_certain_percentage", 50.0),
                output_filename=params.get("output_filename", f"proxy_{task_id}"),
                state=state,
                model_type=params.get("model_type", "t2v_2_2"),  # Valid default model type
                mode="generate_video",
            )

            # Task completed successfully
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["progress"] = 100
            _tasks[task_id]["completed_at"] = time.time()

            # Try to find the output file
            output_dir = get_output_directory()
            output_pattern = params.get("output_filename", f"proxy_{task_id}")

            # Search for matching output files
            output_path = None
            output_dir_path = Path(output_dir)
            if output_dir_path.exists():
                # Look for recent files matching the pattern
                for file in sorted(output_dir_path.rglob(f"*{output_pattern}*"), reverse=True):
                    if file.is_file():
                        output_path = str(file)
                        break

                # If not found, look for most recent video
                if not output_path:
                    for ext in ["*.mp4", "*.webm", "*.avi"]:
                        for file in sorted(output_dir_path.rglob(ext), reverse=True):
                            if file.is_file():
                                output_path = str(file)
                                break
                        if output_path:
                            break

            _tasks[task_id]["output_path"] = output_path
            logger.info(f"Task {task_id} completed: {output_path}")

        except Exception as e:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)
            _tasks[task_id]["traceback"] = traceback.format_exc()
            logger.error(f"Task {task_id} failed: {e}")

    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = f"Generation error: {e}"
        logger.error(f"Error in run_generation: {e}")


# =============================================================================
# HTTP Endpoints
# =============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    try:
        # Check if Wan2GP path exists
        if not Path(WAN2GP_PATH).exists():
            return jsonify({
                "status": "unhealthy",
                "error": "Wan2GP path does not exist",
                "wan2gp_path": WAN2GP_PATH
            }), 503

        # Check if wgp.py exists
        # Check if wgp.py exists
        wgp_file = Path(WAN2GP_PATH) / "wgp.py"
        if not wgp_file.exists():
            return jsonify({
                "status": "unhealthy",
                "error": "wgp.py not found in Wan2GP directory",
                "wan2gp_path": WAN2GP_PATH
            }), 503

        return jsonify({
            "status": "healthy",
            "wan2gp_path": WAN2GP_PATH,
            "version": "1.0.0",
            "note": "Wan2GP will be imported on first generation request"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503


@app.route("/generate", methods=["POST"])
def generate():
    """
    Submit a video generation task.

    Expects JSON body with generation parameters.
    Returns task_id for tracking.
    """
    try:
        params = request.json

        # Generate task ID
        task_id = f"proxy_{int(time.time() * 1000)}"

        # Create task record
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "created_at": time.time(),
            "params": {
                "prompt": params.get("prompt", ""),
                "resolution": params.get("resolution", "1280x720"),
                "model_type": params.get("model_type", "wan")
            }
        }

        # Start generation in background thread
        thread = threading.Thread(target=lambda: asyncio.run(run_generation(task_id, params)))
        thread.daemon = True
        thread.start()

        logger.info(f"Queued task {task_id} with prompt: {params.get('prompt', '')[:50]}")

        return jsonify({
            "task_id": task_id,
            "status": "queued",
            "message": "Task queued successfully"
        }), 202

    except Exception as e:
        logger.error(f"Error in /generate: {e}")
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/status/<task_id>", methods=["GET"])
def get_status(task_id: str):
    """Get the status of a generation task."""
    if task_id not in _tasks:
        return jsonify({
            "error": "Task not found"
        }), 404

    task = _tasks[task_id]
    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "output_path": task.get("output_path"),
        "error": task.get("error"),
        "traceback": task.get("traceback"),  # Include traceback for debugging
        "created_at": task.get("created_at"),
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at")
    })


@app.route("/models", methods=["GET"])
def models():
    """List available models."""
    try:
        models = list_models()
        return jsonify({
            "models": models,
            "count": len(models)
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route("/loras", methods=["GET"])
def loras():
    """List available LoRAs."""
    try:
        loras = list_loras()
        return jsonify({
            "loras": loras,
            "count": len(loras)
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route("/queue", methods=["GET"])
def queue():
    """Get current queue/status of all tasks."""
    return jsonify({
        "tasks": list(_tasks.values()),
        "count": len(_tasks)
    })


@app.route("/", methods=["GET"])
def index():
    """Root endpoint with API info."""
    return jsonify({
        "name": "Wan2GP HTTP Proxy",
        "version": "1.0.0",
        "endpoints": {
            "GET /health": "Health check",
            "POST /generate": "Submit generation task",
            "GET /status/<task_id>": "Get task status",
            "GET /models": "List available models",
            "GET /loras": "List available LoRAs",
            "GET /queue": "Get all tasks"
        }
    })


def main():
    """Start the proxy server."""
    logger.info("=" * 60)
    logger.info("Wan2GP HTTP Proxy Server")
    logger.info("=" * 60)
    logger.info(f"Wan2GP Path: {WAN2GP_PATH}")
    logger.info(f"Server: http://{PROXY_HOST}:{PROXY_PORT}")
    logger.info("")

    # Check if Wan2GP exists
    if not Path(WAN2GP_PATH).exists():
        logger.error(f"Wan2GP path does not exist: {WAN2GP_PATH}")
        logger.error("Set WAN2GP_PATH environment variable to correct path")
        sys.exit(1)

    logger.info("✓ Wan2GP directory found")
    logger.info("✓ Wan2GP will be imported on first use (lazy loading)")
    logger.info("")
    logger.info("Starting server...")
    logger.info("")

    app.run(
        host=PROXY_HOST,
        port=PROXY_PORT,
        debug=False
    )


if __name__ == "__main__":
    main()
