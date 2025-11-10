# Agentic – LLM Agents for Sublime Text 🤖
A lightweight Sublime Text plugin that lets you concurrently command multiple local or remote LLMs.

## Introduction 🖊
```
Sublime breathes code,  
Agents speak in marked whispers,  
Chats rise, fall, then rest.
```
*~GPT-OSS-20b on Agentic/chat_stream.py using the "haiku" action*

This is a plugin that lets you run models over OpenAI-style chat completion APIs, tested with `llama-server`. You can use this plugin to send code snippets or files and get LLM results directly in Sublime Text. Chatting is supported through a simple markdown text file interface with hotkeys (`[ctrl/cmd]+[enter]`, `[esc]/[c]`). There is also support to easily build custom agent actions that you can quickly access from the command palette.

### Features 😍
**Highlight code and use `AI Agent` to launch a custom chat with relevant context:**
![Highlight a Code Section and Start a Chat](pics/highlight_chat.png)

**Define and quickly launch custom actions on code sections or whole files with `AI Agent Actions`:**
![Define and Run Custom Actions](pics/custom_actions.png)

**Fast and streamlined interactive markdown chat interface with fully editable history and prompts:**
![Markdown-formatted Documents are used for LLM Chat](pics/markdown_chat.png)

### Usage 🛠
This plugin currently has three major command pallet actions:
- `AI Agent` - takes highlighted text (or an entire file) and a command string to perform a custom action
- `AI Agent Action` - takes highlighted text (or an entire file) and starts a new chat based on a user-defined action (see `agentic.sublime-settings`)
- `AI Agent Chat Submit` - will send the contents of a chat file to an LLM for a chat-like interface (triggered with `[ctrl/cmd]+[enter]` from a chat file; `[c]` or `[esc]` to interrupt)

There are also several supplemental pallet actions to help control chats
- `AI Agent Clear Reasoning` - deletes model 'reasoning' output from chat files
- `AI Agent Clone Chat` - creates a copy of an existing chat
- `AI Agent New Chat` - creates a new chat file

For settings, there is a convenience command:
- `AI Agent Settings` which will open your configuration file `Agentic.sublime-settings`.

### Settings ✏
Configuring user-defined actions (`AI Agent Settings` / `Agentic.sublime-settings`):
```json
"actions": {
		// Each action has a key word (which shows up in the menu):
		"haiku": {
			"models": "models_high", // name of list of models to use
			"system": "You are an expert.", // system prompt
			"prompt": "Turn this into a haiku." // user prompt
		},
		...
}
```

Configuring models (`AI Agent Settings` / `Agentic.sublime-settings`):
```json
"models_high": ["high_1", "high_2"], // Named model list for capability family
"models": {
		"high_1": // Each model configuration has a name
		{
			"url": "http://127.0.0.1:8080/v1/chat/completions",
			"model": "gpt-oss-20b", // API model name
			"token": "000000000000",// API Token
			"options": {            // API parameters go in "options"
				"stream": true,
				"chat_template_kwargs": {"reasoning_effort": "high"},
				"temperature": 1.0,
				"top_p": 1.0,
				"min_p": 0,
				"top_k": 0
			},
			"context": 128000.0,  // Approximate usable context length
			"system": "my_gpu1",  // A unique resource id (for local systems)
			"workers": 3,         // Number of concurrent requests supported
			"speed": 120,         // Approximate tokens per second
			"effort": 32768.0     // Output tokens required on average to solve
		},
		"high_2":
		...
}
```

## Installation 📂
You can install this plugin by copying its contents to your `Packages` folder:
```cmd
cd "%APPDATA%\Sublime Text\Packages"               # on Windows
cd ~/Library/Application\ Support/Sublime\ Text    # on Mac
cd ~/.config/sublime-text/Packages                 # on Linux

git clone https://git.sr.ht/~alecgraves/agentic-sublime
```

* This plugin works better with [Origami](https://github.com/SublimeText/Origami)

## LLM Model Installation and Running 🚀

`Agentic` uses the OpenAI API, so anything that supports it should work. Ollama and llama.cpp are popular programs to run local LLMs. llama.cpp is faster, so this guide covers its use.

### 1. Build llama.cpp (updated 2025)
To install [llama.cpp](https://github.com/ggml-org/llama.cpp), compile it for your platform. The llama-server file is located at `build/bin/llama-server`

NVIDIA (Makeflie):
```make
CC=clang
CXX=clang++
LLD=lld

LDLINKFLAGS=-flto -Wl,--gc-sections -Wl,-pie
LIBCFLAGS=-fstack-protector-all -D_FORTIFY_SOURCE=3 -ffunction-sections \
	-fdata-sections -fvisibility-inlines-hidden -O2 \
	-march=native -mtune=native \
	-funsafe-math-optimizations -ffast-math -fno-finite-math-only -flto -fpic

all:
	cmake -B build -DGGML_CUDA=ON -DGGML_CUDA_FA_ALL_QUANTS=true \
		-DGGML_CUDA_F16=true -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=MinSizeRel \
		-DBUILD_TESTING=OFF -DCMAKE_C_COMPILER=$(CC) -DCMAKE_CXX_COMPILER=$(CXX) \
		-DCMAKE_LINKER="$(LLD)" -DCMAKE_C_FLAGS="$(LIBCFLAGS)" -DCMAKE_CXX_FLAGS="$(LIBCFLAGS)" \
		-DCMAKE_C_FLAGS_MINSIZEREL="$(LIBCFLAGS)" -DCMAKE_CXX_FLAGS_MINSIZEREL="$(LIBCFLAGS)" \
		-DCMAKE_EXE_LINKER_FLAGS="$(LDLINKFLAGS)"
	LDLINKFLAGS="$(LDLINKFLAGS)" make -C build -j $$(nproc) llama-server
```

NVIDIA + Intel-CPU (ICX compiler) (shell):
```sh
{ . /opt/intel/oneapi/setvars.sh --force; } || { echo Already sourced...; }
git fetch --prune
git pull
cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF  \
	-DCMAKE_POSITION_INDEPENDENT_CODE=1 -DGGML_CUDA_F16=1 -DGGML_CUDA_FA_ALL_QUANTS=1 \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_CXX_FLAGS_RELEASE="-fPIE -march=native -mtune=native -ffunction-sections -fdata-sections -flto -fstack-protector-all -D_FORTIFY_SOURCE=3 -mshstk -fcf-protection=full -Wl,--gc-sections,-flto" \
	-DCMAKE_C_FLAGS_RELEASE="-fPIE -ffunction-sections -fdata-sections -flto -fstack-protector-all -D_FORTIFY_SOURCE=3 -mshstk -fcf-protection=full -march=native -mtune=native -Wl,--gc-sections,-flto" \
	-DGGML_BLAS=ON -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DGGML_NATIVE=ON
make -C build -j $(nproc) llama-server
```

AMDGPU (ROCm) (shell):
```sh
HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" \
    cmake -S . -B build -DGGML_HIP=ON -DLLAMA_CURL=OFF -DAMDGPU_TARGETS=gfx1200 -DCMAKE_BUILD_TYPE=Release \
    && make -C build -j $(nproc) llama-server
```

### 2. Download a good LLM
Download a good model like [Qwen-30b-A3b **IQ4-NL**](https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF) or [GPT-OSS-20b **F16**](https://huggingface.co/unsloth/gpt-oss-20b-GGUF).

### 3. Run llama.cpp with your LLM
Then, run llama-server:

- OSS 20B, 24GB vram, NVidia:
```sh
CUDA_VISIBLE_DEVICES=0 llama-server -m ~/models/gpt-oss-20b-F16.gguf -ctk f16 -ctv f16 -np 3 -fa on -c $((32768*4*3)) --top-k 0 --temp 1.0 --top-p 1.0  --min-p 0 --presence-penalty 0.5 --jinja -ngl 20000 --prio 3 --port 8080 --no-mmap --chat-template-kwargs '{\"reasoning_effort\": \"high\"}'"
```

- OSS 20B, 16GB vram, AMD ROCm:
```sh
HIP_VISIBLE_DEVICES=0 llama-server -m ~/models/gpt-oss-20b-F16.gguf -ctk f16 -ctv f16 -fa on -ngl 100 -c $((32768*3)) -np 1 --jinja --port 8080 --chat-template-kwargs '{\"reasoning_effort\": \"high\"}'
```

- OSS 20B, 2xT1000 8GB:
```sh
llama-server -ngl 99 -c $((32768*2)) -t 4 -fa on -ctk f16 -ctv f16 -m ~/models/gpt-oss-20b-F16.gguf --jinja  --prio 3 --top-k 0 --temp 1.0 --top-p 1.0 --min-p 0 --presence-penalty 0.5 -ngl 20000 -np 1 --port 8080 --split-mode row --tensor-split 7,8 --chat-template-kwargs '{\"reasoning_effort\": \"high\"}'
```

- OSS 120B (Intel CPU, 64GB RAM):
```sh
CUDA_VISIBLE_DEVICES='' llama-server -fa on -ctk q8_0 -ctv q8_0 -m ~/models/gpt-oss-120b-UD-Q4_K_XL-00001*.gguf --threads $(ncore) -np 1 --n-gpu-layers 99 -c $((32768*2)) --top-k 0 --temp 1.0 --top-p 1.0 --jinja  --min-p 0 --presence-penalty 0.5 -n 38912 --prio 2 --port 8081 --mlock --swa-full --chat-template-kwargs '{\"reasoning_effort\": \"high\"}'
```

### 4. Connect
Now you should be able to automatically connect and run Agent commands, or you can update your model configurations to match your local deployment.

run the `AI Agent Settings` command, or go to `Preferences > Package Settings > Agentic > Settings` to modify your llm configuration.

## Status ✅
Currently, this plugin supports chat incorporating user-highlighted code for context. This functionality has been tested with local LLMs running under [llama.cpp](https://github.com/ggml-org/llama.cpp). Future goals include implementation of DeepMind AlphaEvolve-like functionality for automated high-performance evolutionary code optimization.

- [x] Sublime chat interface
- [x] Submit query with context
- [x] User-defined chat actions
- [x] Multiple local LLM support
- [ ] Function calling
- [ ] Multi-agent workflows (e.g. generate then reduce/combine)
- [ ] Try accelerator APIs like [groq](https://groq.com/)

## License ⚖
This project is released under 🚀🔥 ⚖ The Unlicense ⚖ 🔥🚀
