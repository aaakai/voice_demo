# Voice Interrupt Demo (Experimental)

这是一个独立的 Python 实验项目，用于验证：

1. 主回复链路（Dialogue）和打断链路（Interrupt）并行运行。
2. 系统可基于 partial transcript 先产生草拟响应。
3. 用户停顿时，系统可短促接话（backchannel）。
4. 系统播报中用户插话时，可立即停播并重规划。

> 注意：当前版本是 mock-first，可直接运行观察事件流与状态机行为，不依赖真实 ASR/LLM/TTS。

## 模块结构

```text
experimental/voice_interrupt_demo/
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── audio/
│   ├── __init__.py
│   ├── input_stream.py
│   └── vad.py
├── asr/
│   ├── __init__.py
│   ├── asr_interface.py
│   └── mock_asr.py
├── core/
│   ├── __init__.py
│   ├── context.py
│   ├── events.py
│   ├── orchestrator.py
│   └── state_machine.py
├── dialogue/
│   ├── __init__.py
│   ├── dialogue_interface.py
│   ├── dialogue_worker.py
│   └── mock_llm.py
├── interrupt/
│   ├── __init__.py
│   ├── interrupt_worker.py
│   └── policies.py
├── tts/
│   ├── __init__.py
│   ├── mock_tts.py
│   ├── playback_controller.py
│   └── tts_interface.py
└── utils/
    ├── __init__.py
    ├── logger.py
    └── timers.py
```

## 事件流

- `mock_asr` 输出：
  - `user_speech_started`
  - `partial_transcript`
  - `final_transcript`
  - `user_speech_stopped`
- `orchestrator` 统一消费事件并更新状态。
- `dialogue_worker`（并行）消费 partial/final：
  - partial -> `response_draft_updated`
  - final -> `response_ready`
- `interrupt_worker`（并行）轮询共享上下文：
  - 触发 `interrupt_requested`（用户打断）
  - 或 `interrupt_approved`（主动 backchannel）
- `playback_controller` 处理播报：
  - `tts_started`
  - `tts_finished`

## 状态机

状态：`idle -> listening -> thinking -> speaking -> interrupted -> replanning`

`orchestrator` 统一输出状态切换日志，便于观察：

- 正常路径：`listening -> thinking -> speaking -> idle`
- 用户打断路径：`speaking -> interrupted -> replanning -> listening/thinking`

## 运行

### 1) 安装依赖

```bash
cd /Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) 启动

```bash
python app.py --scenario all --log-level INFO
```

可选场景：

```bash
python app.py --scenario a
python app.py --scenario b
python app.py --scenario c
```

## 如何验证 3 个核心场景

### 场景 A：正常对话
- 观察 `ASR partial` -> `ASR final` -> `Dialogue final reply` -> `TTS START/DONE`。

### 场景 B：用户停顿短接话
- 在用户 still speaking 且 partial 有停顿时，观察：
  - `Interrupt approved action=backchannel`
  - 随后有短 TTS 播放。

### 场景 C：用户打断系统
- 在 assistant 播报中用户再次开口时，观察：
  - `INTERRUPT requested`
  - `STOP TTS`
  - `PCM STOP`
  - 然后新一轮 `ASR final` 与回复生成。

## 后续替换建议

- 替换 `asr/mock_asr.py` 为真实 streaming ASR 实现。
- 替换 `dialogue/mock_llm.py` 为真实 LLM 客户端。
- 替换 `tts/mock_tts.py` 为真实 TTS 服务。

核心并行结构无需改动，只需替换接口实现。
