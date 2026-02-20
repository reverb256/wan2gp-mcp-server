# RAM Management Guide for Wan2GP Video Generation

## Problem

Wan2GP video models (14B parameters) are extremely memory-intensive. With 32GB DDR4 RAM, the system can run out of memory during generation.

## Symptoms

- High swap usage (>50GB)
- System slowdown/freezing
- Only 1-2GB RAM available during generation
- Potential OOM (Out of Memory) errors

## Solutions

### 1. **Use Lower Memory Profiles** (Most Effective)

Wan2GP has memory profiles 0-5. Higher numbers = less VRAM/RAM usage:

| Profile | Quality | Resolution | Max Frames | Est. RAM Usage |
|---------|---------|------------|------------|----------------|
| 0 | High | 1920x1080 | 169 | ~28GB |
| 2 | Balanced | 1280x720 | 121 | ~24GB |
| 3 | Medium | 1280x720 | 97 | ~20GB |
| 4 | Low | 720x480 | 73 | **~16GB** ✅ |
| 5 | Very Low | 512x512 | 49 | **~12GB** ✅ |

**Recommended:** Use Profile 4 or 5 for 32GB RAM systems.

### 2. **Reduce Resolution**

```json
{
  "resolution": "720x480",  // Instead of 1920x1080
  "video_length": 49         // ~2 seconds instead of longer
}
```

### 3. **Reduce Inference Steps**

```json
{
  "num_inference_steps": 15  // Instead of 20-30
}
```

### 4. **Enable CPU Offloading**

In `wan2gp_proxy.py`, ensure:
- `cpu_offload=True` in model loading
- `attention_mode="sdpa"` for efficient attention
- Model components offloaded to CPU when not in use

### 5. **Monitor Memory Usage**

```bash
# Before generation
free -h

# Monitor during generation
watch -n 2 'free -h && nvidia-smi'
```

### 6. **Clear Cache Between Generations**

```python
# In proxy server
import torch
torch.cuda.empty_cache()
```

## Recommended Settings for 32GB RAM

```json
{
  "resolution": "720x480",
  "video_length": 49,
  "num_inference_steps": 15,
  "guidance_scale": 5.0,
  "override_profile": 4,
  "batch_size": 1
}
```

## Emergency Actions

If system becomes unresponsive:

```bash
# 1. Check memory usage
free -h

# 2. If swap is full, stop generation
pkill -f wan2gp

# 3. Clear Python caches
pkill -9 python

# 4. Restart with lower settings
```

## Prevention

1. **Always use Profile 4 or 5** for 32GB systems
2. **Keep video length short** (49 frames = ~2 seconds)
3. **Close other applications** before generation
4. **Monitor swap usage** - stop if >50GB used
5. **Use audio generation** as alternative (much lower RAM usage)

## Alternative: Audio Generation

Audio generation uses ~4GB RAM vs ~20GB for video:

```bash
python skills/wan2gp.py generate "Your prompt here" \
  --model ace_step_v1_5_turbo_lm_4b
```

## System Optimization

```bash
# Add swap if needed (for safety)
sudo fallocate -l 32G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2

# Set swappiness to prefer RAM over swap
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

## Memory-Safe API Call

```bash
curl -X POST http://localhost:7861/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Your prompt",
    "resolution": "720x480",
    "video_length": 49,
    "num_inference_steps": 15,
    "guidance_scale": 5.0,
    "override_profile": 4,
    "model_type": "t2v_2_2"
  }'
```

## Key Takeaway

**With 32GB RAM, you MUST use Profile 4 or 5.** The default Profile 0 will exhaust your RAM and cause heavy swap usage.
