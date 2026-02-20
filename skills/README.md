# Wan2GP Skills

This directory contains Skills for interacting with the Wan2GP MCP server.

## Available Skills

### wan2gp.py
Main skill for Wan2GP video generation with automatic GPU detection and VRAM management.

**Usage from CLI:**
```bash
python skills/wan2gp.py generate "A cat walking in a garden"
python skills/wan2gp.py status <task_id>
python skills/wan2gp.py models
python skills/wan2gp.py gpu-info
python skills/wan2gp.py health
```

**Usage from compatible clients:**
```
skill: wan2gp-generate "A cat in space"
skill: wan2gp-status <task_id>
skill: wan2gp-models
skill: wan2gp-gpu-info
skill: wan2gp-health
```

**Features:**
- ✅ **Automatic GPU Detection** - Detects GPU and VRAM availability
- ✅ **Smart VRAM Management** - Automatically adjusts settings based on available memory
- ✅ **Safe Settings Override** - Prevents OOM errors with conservative defaults
- Generate videos from text descriptions
- Generate videos from images (image-to-video)
- Check generation status/progress
- List available models and LoRAs
- Health check functionality

**GPU Detection:**
The skill automatically detects:
- GPU availability (CUDA/nvidia-smi)
- VRAM total and free memory
- Optimal settings for your hardware
- Recommended profile and resolution

**VRAM Management:**
| VRAM | Profile | Resolution | Max Frames |
|------|--------|------------|-------------|
| 24GB+ | High Quality | 1920x1080 | 169 |
| 16GB+ | Balanced | 1280x720 | 121 |
| 12GB+ | Medium | 1280x720 | 97 |
| 8GB+ | Low | 720x480 | 73 |
| 6GB+ | Very Low | 512x512 | 49 |

## Installation

Skills are standalone Python scripts that can be invoked directly or through compatible skill host systems.

## Requirements

- Python 3.10+
- Wan2GP MCP server running
- CUDA-capable GPU (recommended)
- Dependencies from requirements.txt installed
