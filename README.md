# Wan2GP MCP Server

A Model Context Protocol (MCP) server that provides AI assistants (like Claude Desktop) with access to [Wan2GP](https://github.com/Wan-Video/Wan2GP) video generation capabilities.

## Overview

This MCP server communicates with a running Wan2GP Gradio instance to generate videos from text prompts and images. It's designed to work with Wan2GP installations via [StabilityMatrix](https://github.com/LykosAI/StabilityMatrix) or standalone setups.

## Features

- **Text-to-Video**: Generate videos from text descriptions
- **Image-to-Video**: Animate static images with text prompts
- **Queue Management**: View and manage generation queue
- **Model Listing**: Discover available video generation models
- **LoRA Support**: List available LoRA adapters
- **Health Monitoring**: Check Wan2GP server status

## Architecture

```
Claude Desktop (MCP Client)
    ↓ stdio (JSON-RPC 2.0)
Wan2GP MCP Server
    ↓ HTTP requests
Wan2GP Gradio Server (localhost:7860)
```

## Prerequisites

1. **Wan2GP Server**: A running Wan2GP Gradio instance
   - Install via [StabilityMatrix](https://github.com/LykosAI/StabilityMatrix) or manually
   - Start the Gradio server: `python wgp.py --server-name 0.0.0.0 --server-port 7860`

2. **Python 3.10+**: Required for the MCP server

3. **Claude Desktop** (optional): For MCP integration

## Installation

### 1. Clone or Download

```bash
cd /path/to/your/projects
git clone <this-repo> wan2gp-mcp-server
cd wan2gp-mcp-server
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Server URL

Edit `config.json` to match your Wan2GP server URL:

```json
{
  "wan2gp_url": "http://localhost:7860",
  "timeout": 300,
  "max_concurrent_tasks": 3,
  "default_model": "wan",
  "default_resolution": "1280x720",
  "output_directory": "./output"
}
```

Or set via environment variable:

```bash
export WAN2GP_URL="http://localhost:7860"
export WAN2GP_TIMEOUT="300"
```

## Usage

### Standalone Testing

Test the MCP server directly:

```bash
python wan2gp_mcp_server.py
```

In another terminal, test with an MCP client or inspect the logs.

### Claude Desktop Integration

1. **Add to Claude Desktop Config**

   Locate Claude Desktop's config file:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Merge the Configuration**

   Add the `wan2gp` server to the `mcpServers` section:

   ```json
   {
     "mcpServers": {
       "wan2gp": {
         "command": "python",
         "args": [
           "/absolute/path/to/wan2gp-mcp-server/wan2gp_mcp_server.py"
         ],
         "env": {
           "WAN2GP_URL": "http://localhost:7860",
           "WAN2GP_TIMEOUT": "300",
           "LOG_LEVEL": "INFO"
         }
       }
     }
   }
   ```

   **Important**: Use absolute paths in the `args` section.

3. **Restart Claude Desktop**

   Claude will load the MCP server on startup.

4. **Use in Claude**

   Now you can ask Claude to generate videos:

   ```
   Generate a 5-second video of a cat walking through a sunny garden
   ```

   Claude will use the MCP server to submit the generation task.

## MCP Tools

The server provides the following tools:

### `generate_text_to_video`

Generate a video from text description.

**Parameters:**
- `prompt` (required): Text description of the video
- `negative_prompt`: Things to avoid in the video
- `resolution`: Video resolution (e.g., "1280x720", "1920x1080")
- `video_length`: Number of frames (49 ≈ 2 seconds at 24fps)
- `num_inference_steps`: Number of denoising steps (20-50 recommended)
- `guidance_scale`: How strongly to follow the prompt (1-20)
- `seed`: Random seed (-1 for random)
- `model_type`: Model to use (wan, hunyuan, ltx, etc.)
- `output_filename`: Custom output filename

**Example:**
```python
generate_text_to_video(
    prompt="A cat walking through a sunny garden, slow motion",
    resolution="1280x720",
    num_inference_steps=25,
    guidance_scale=7.5
)
```

### `generate_image_to_video`

Animate a static image based on a text prompt.

**Parameters:**
- `image_path` (required): Path to the input image
- `prompt` (required): How the image should animate/move
- `negative_prompt`: Things to avoid in the video
- `motion_scale`: How much motion to generate (0.5-2.0)
- `video_length`: Number of frames
- `num_inference_steps`: Number of denoising steps
- `guidance_scale`: How strongly to follow the prompt
- `seed`: Random seed (-1 for random)
- `model_type`: Model to use

**Example:**
```python
generate_image_to_video(
    image_path="/path/to/image.jpg",
    prompt="Camera slowly zooms in, clouds drift across the sky",
    motion_scale=1.2
)
```

### `health_check`

Check if Wan2GP server is running and accessible.

**Returns:**
```json
{
  "status": "healthy",
  "url": "http://localhost:7860",
  "version": "10.951"
}
```

### `list_models`

List all available video generation models.

**Returns:**
```json
[
  {
    "name": "Wan2.1 T2V",
    "id": "t2v_2_2",
    "type": "text_to_video",
    "resolution": "480p-8K",
    "vram_requirement": "16GB+"
  }
]
```

### `list_loras`

List available LoRA adapters.

### `get_queue`

Get the current generation queue.

### `cancel_task`

Cancel a queued generation task.

## MCP Resources

The server provides the following resources:

- `wan2gp://models` - List available models (JSON)
- `wan2gp://loras` - List available LoRAs (JSON)
- `wan2gp://queue` - Current generation queue (JSON)
- `wan2gp://health` - Server health status (JSON)

## Troubleshooting

### "Cannot connect to Wan2GP server"

- Ensure Wan2GP Gradio server is running
- Check the URL in `config.json` matches your server
- Verify the server port (default: 7860)

### "Flash-Attention version conflict"

This is a Wan2GP environment issue, not related to the MCP server. Ensure Wan2GP's dependencies are correctly installed:

```bash
# In Wan2GP environment
pip install flash-attn==2.7.4
```

### Claude Desktop doesn't show MCP tools

1. Check Claude Desktop logs: `Help > Developer > Show Logs`
2. Verify absolute paths in config
3. Ensure Python is in system PATH
4. Test the server manually: `python wan2gp_mcp_server.py`

## Development

### Running Tests

```bash
# Test client
python tests/test_client.py

# Test with MCP inspector
npx @modelcontextprotocol/inspector python wan2gp_mcp_server.py
```

### Adding New Tools

Edit `wan2gp_mcp_server.py` and add a new tool using the `@mcp.tool` decorator:

```python
@mcp.tool
async def my_new_tool(param: str) -> str:
    """Tool description."""
    client = await get_client()
    # ... implementation
    return "result"
```

## Configuration Reference

### config.json

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `wan2gp_url` | string | `http://localhost:7860` | Wan2GP Gradio server URL |
| `timeout` | number | `300` | Request timeout in seconds |
| `max_concurrent_tasks` | number | `3` | Maximum concurrent generations |
| `default_model` | string | `wan` | Default model to use |
| `default_resolution` | string | `1280x720` | Default video resolution |
| `output_directory` | string | `./output` | Where to save generated videos |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WAN2GP_URL` | Override Wan2GP server URL | `http://localhost:7860` |
| `WAN2GP_TIMEOUT` | Override request timeout | `300` |
| `LOG_LEVEL` | Logging level | `INFO` |

## License

This MCP server is provided as-is for use with Wan2GP.

## Credits

- [Wan2GP](https://github.com/Wan-Video/Wan2GP) - Video generation models and Gradio interface
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [Anthropic](https://www.anthropic.com/) - Model Context Protocol
