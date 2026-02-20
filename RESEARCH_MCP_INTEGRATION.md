# MCP Server Integration Research: ComfyUI & Video Generation Tools

**Date:** 2025-02-19
**Purpose:** Research existing MCP servers for AI generation tools (ComfyUI, video generation) to inform Wan2GP MCP server implementation

---

## Executive Summary

After researching multiple MCP implementations for AI generation tools, **three primary integration patterns** have emerged:

1. **Direct REST/WebSocket API** (ComfyUI) - Simple, reliable
2. **Workflow-based abstraction** (Pixelle-MCP) - Flexible, powerful
3. **State-based Gradio wrappers** - Complex, requires reverse-engineering

**Recommendation:** Use **Pattern #1 or #2** for Wan2GP integration.

---

## Key Findings

### 1. ComfyUI MCP Server (`joenorton/comfyui-mcp-server`)

**Architecture:**
```
Claude Desktop → MCP Server (WebSocket) → ComfyUI Client → ComfyUI REST API
```

**Key Implementation Details:**

#### Communication Method (from `comfyui_client.py`):
```python
# 1. POST workflow to ComfyUI's /prompt endpoint
response = requests.post(
    f"{self.base_url}/prompt",
    json={"prompt": workflow}  # workflow is a JSON dict
)

# 2. Poll /history/{prompt_id} for completion
for _ in range(max_attempts):
    history = requests.get(f"{self.base_url}/history/{prompt_id}").json()
    if prompt_id in history:
        # Extract image URL from outputs
        image_filename = history[prompt_id]["outputs"][node_id]["images"][0]["filename"]
        return f"{base_url}/view?filename={image_filename}"
    time.sleep(1)
```

**Critical Insight:** ComfyUI provides a **clean REST API**:
- `POST /prompt` - Submit workflow
- `GET /history/{prompt_id}` - Check status/results
- `GET /view?filename=...` - Access output files
- `GET /object_info/...` - Query available models/nodes

**Why This Works:**
- No complex state management
- Direct workflow JSON submission
- Simple polling for results
- Predictable output structure

---

### 2. Pixelle-MCP (`AIDC-AI/Pixelle-MCP`)

**Architecture:**
```
LLM → MCP Server → ComfyUI Facade → {WebSocket|HTTP|RunningHub} Executor
```

**Key Innovation:** **Workflow-as-Tool** automatic conversion

#### Workflow Registration Pattern (from docs):
1. Export ComfyUI workflow in **API format** (not UI format)
2. Parse workflow JSON to extract metadata
3. Generate Python function dynamically:
```python
def image_blur(image: ImageURL) -> Image:
    """对输入图像进行高斯模糊处理"""
    # Dynamically generated from workflow
```
4. Register with MCP using `@mcp.tool()`

#### Executor Types (from `facade.py`):
```python
class ComfyUIClient:
    def _get_executor(self):
        if self.executor_type == 'websocket':
            return WebSocketExecutor(self.base_url)  # Real-time updates
        elif self.executor_type == 'http':
            return HttpExecutor(self.base_url)        # REST polling
        elif is_runninghub_workflow(workflow_file):
            return RunningHubExecutor(self.base_url)  # Cloud execution
```

**Critical Features:**
- **Hot-reload**: New workflows auto-register as MCP tools
- **Multi-backend**: Local ComfyUI + cloud (RunningHub)
- **Type-safe**: Auto-generates typed function signatures
- **Zero-code**: No manual wrapper functions needed

---

### 3. Wan2GP Gradio Interface (Current Challenge)

**Architecture Discovered:**
```
Gradio UI → State Management → init_generate (btn click) → generate_video()
```

**The Problem:**
```python
# Wan2GP's Gradio interface stores parameters in internal state
# The "Generate" button (id 492) triggers init_generate which:
# 1. Reads from state component (not direct parameters)
# 2. Has 5 inputs, not the 100+ generation parameters

{
  "id": 141,
  "api_name": "init_generate",
  "inputs": [404, 410, 535, 413, 414],  # State refs, not params!
  "outputs": [494, 397]
}
```

**Why Gradio API is Hard:**
- 471 dependencies, 1589 components
- State-based architecture (not functional)
- Parameters embedded in Gradio State objects
- Would need to reverse-engineer entire state structure

**This is why we can't just call `/api/predict` with parameters.**

---

## Comparative Analysis

| Aspect | ComfyUI MCP | Pixelle-MCP | Wan2GP (Current) |
|--------|-------------|-------------|------------------|
| **API Type** | REST + WebSocket | REST/WebSocket/Cloud | Gradio HTTP |
| **State Management** | Stateless (workflow JSON) | Stateless (workflow JSON) | Stateful (Gradio State) |
| **Complexity** | Low (workflow dict) | Medium (executor abstraction) | High (reverse-engineer state) |
| **Flexibility** | Workflow templates | Dynamic tool generation | Limited by Gradio UI |
| **Integration Effort** | ~200 lines | ~1000 lines (full framework) | Unknown (complex) |
| **Maintenance** | Low | Medium | High (UI changes break API) |

---

## Recommended Implementation Options for Wan2GP

### ✅ **Option 1: Direct Python Import** (RECOMMENDED)

Create a lightweight HTTP proxy that imports `generate_video` directly:

```python
# wan2gp_proxy.py - Runs alongside Wan2GP
from wgp import generate_video
from flask import Flask, request, jsonify
import asyncio

app = Flask(__name__)

@app.route('/generate', methods=['POST'])
def generate():
    """Simple HTTP endpoint that wraps generate_video"""
    params = request.json

    # Call generate_video with the parameters
    # Using the same signature as in wgp.py line 5673
    result = asyncio.run(generate_video(
        task=params.get('task', ''),
        send_cmd=lambda cmd, data: None,  # Dummy for CLI
        image_mode=params.get('image_mode', 'T2V'),
        prompt=params['prompt'],
        # ... map all 100+ parameters
    ))

    return jsonify({
        'status': 'completed',
        'output_path': result.get('output_path')
    })

if __name__ == '__main__':
    app.run(port=7861)
```

**Pros:**
- Direct access to all generation parameters
- No Gradio state reverse-engineering
- Simple HTTP interface
- Works with existing Wan2GP installation

**Cons:**
- Need to run separate process
- Need to map all parameters

---

### ✅ **Option 2: ComfyUI-Style REST API** (ALTERNATIVE)

If Wan2GP has a hidden REST API (similar to ComfyUI's `/prompt`):

1. Check for existing endpoints:
   - `/api/generate` or `/generate`
   - Queue management endpoints
   - WebSocket for status updates

2. Use the ComfyUI MCP pattern:
```python
# Submit generation
POST /api/generate
{
  "prompt": "A cat in space",
  "resolution": "1280x720",
  "num_inference_steps": 20
}
→ {"task_id": "12345"}

# Check status
GET /api/status/12345
→ {"status": "processing", "progress": 45}

# Get result
GET /api/result/12345
→ {"output_path": "/path/to/video.mp4"}
```

**Pros:**
- Follows proven pattern
- Clean separation of concerns
- Easy to test

**Cons:**
- Requires Wan2GP to have such endpoints (unlikely given Gradio wrapper)

---

### ✅ **Option 3: Queue File Integration** (SIMPLEST)

Leverage Wan2GP's existing `queue.zip` system:

```python
# Write task to queue.zip
def queue_generation(params):
    import zipfile
    import json

    task = {
        "id": str(int(time.time())),
        "params": params,
        "status": "queued"
    }

    # Add to queue.zip
    with zipfile.ZipArchive('queue.zip', 'a') as zf:
        zf.writestr(f'task_{task["id"]}.json', json.dumps(task))

    # Wan2GP will process it automatically
    return task["id"]
```

**Pros:**
- Uses existing Wan2GP mechanism
- No API changes needed
- Persistent across restarts

**Cons:**
- Not real-time
- Need to poll for results
- File I/O overhead

---

## Implementation Strategy

### Phase 1: Quick Win (1-2 hours)
1. **Test Option 3** - Queue file integration
2. Verify Wan2GP picks up queued tasks
3. Poll for completion

### Phase 2: Robust Solution (4-6 hours)
1. **Implement Option 1** - Python import proxy
2. Add comprehensive parameter mapping
3. Package as standalone server

### Phase 3: Full Featured (Future)
1. Add WebSocket for real-time progress
2. Implement queue management
3. Add model/LoRA listing

---

## Key Takeaways

### What Works for ComfyUI:
1. **Clean API** - `/prompt`, `/history`, `/view` endpoints
2. **Workflow JSON** - Self-contained execution graph
3. **Stateless** - No session management complexity
4. **Predictable outputs** - Consistent response structure

### What Makes Wan2GP Hard:
1. **Gradio abstraction** - UI-centric, not API-centric
2. **State dependencies** - 100+ params in state object
3. **Complex UI** - 471 dependencies, 1589 components
4. **No documented REST API** - Built as GUI application

### The Path Forward:
**Don't fight the Gradio architecture.** Instead:
1. Import `generate_video` directly (Option 1)
2. Or use queue files (Option 3)
3. Treat Wan2GP as a Python library, not HTTP service

---

## References

- [joenorton/comfyui-mcp-server](https://github.com/joenorton/comfyui-mcp-server) - Simple ComfyUI MCP implementation
- [AIDC-AI/Pixelle-MCP](https://github.com/AIDC-AI/Pixelle-MCP) - Advanced workflow-based MCP framework
- [ComfyUI API Documentation](https://docs.comfyanonymous.com/ComfyUI_API) - REST endpoints reference
- [Model Context Protocol Spec](https://modelcontextprotocol.io/) - MCP standard

---

## Conclusion

The research clearly shows that **successful MCP servers for generation tools** follow the **Direct REST API** pattern, not Gradio state manipulation.

**Recommended Action:** Implement Option 1 (Python import proxy) for Wan2GP. This follows the proven pattern from ComfyUI MCP while avoiding the complexity of reverse-engineering Wan2GP's Gradio state system.
