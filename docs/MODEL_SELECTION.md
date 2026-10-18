# Local model selection

Phi-4-mini-instruct is the default model. Qwen2.5-Coder 7B Instruct remains an available alternative; no model weights are bundled. The tested files were Q4_K_M GGUF versions served by the existing local llama.cpp runtime.

Start your separately installed llama.cpp server with a local model path and a matching alias, for example:

```powershell
.\llama-server.exe --model "C:\your-models\Phi-4-mini-instruct-Q4_K_M.gguf" --host 127.0.0.1 --port 8080 --ctx-size 4096 --n-gpu-layers 99 --alias phi-4-mini-instruct
```

Copy `config.example.json` to the ignored `config.local.json`. Its `llm_model` must match the identifier served by llama.cpp; the default is `phi-4-mini-instruct`. Changing the config does not download weights or switch an already running server.

To use Qwen, restart your model server with the Qwen2.5-Coder 7B model and alias `qwen2.5-coder-7b-instruct`, then set `llm_model` to that same value in `config.local.json`. Other endpoint and RCON settings stay local. Existing explicit local overrides take precedence over defaults.

## Decision evidence

At normal character speed and game speed 1, each model completed 3/3 open and 3/3 blocked 40-tile, two-objective tasks in the same isolated test save. Both passed 2/2 recovery Stop checks, including awaiting approval and active walking. Each also recovered after a rejected detour proposal. Phi's median open/blocked task times were 18.0/19.5 seconds versus Qwen's 23.1/26.4 seconds. Both recorded zero post-Stop drift and stayed within five tiles per action. This supports the current default choice for bounded navigation, not general autonomy, combat or building competence.

See [full test report](PHI_QWEN_NAVIGATION_VALIDATION.md). The policy-v7 backend rebuild is required; [normal movement](NORMAL_MOVEMENT.md) explains the tested graphical-host setup and joined-client visual limitation. Human approvals, emergency stopping and the five-tile movement limit remain active. Fully Autonomous is still locked.
