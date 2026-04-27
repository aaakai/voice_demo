# Voice Interrupt Demo

这是一个独立实验 demo，用来验证“可主动抢话 / 可被打断 / 双链路并行决策”的实时语音 assistant 架构。

当前版本优先使用 mock transcript、mock LLM、mock TTS，不依赖真实麦克风或模型服务。重点是让行为清楚可观察：partial 阶段草拟、停顿时主动接话、缺槽时主动追问、纠正时强制抢话、assistant 播报中被用户打断后立即停播并重规划。

## 架构

主回复链路 `Dialogue Pipeline`：

- 消费 `partial_transcript` 和 `final_transcript`
- partial 阶段生成 `DialogueDraft`
- 输出 `intent_hypothesis`
- 输出 `short_reply_candidate`
- 输出 `clarification_candidate`
- 输出 `rough_full_reply_candidate`
- final 阶段生成完整回复

抢话/打断链路 `Floor-Taking Pipeline`：

- 独立轮询 `SharedContext`
- 读取 latest partial、pause duration、user/assistant speaking、draft candidates
- 输出结构化 `FloorDecision`
- 支持 `no_interrupt / backchannel / soft_take_floor / hard_take_floor / stop_assistant`

中心调度 `Orchestrator / Turn Manager`：

- 管理当前话轮所有权 `floor_owner`
- 批准或拒绝 assistant 主动抢话
- 播报中用户开口时撤销 assistant 话轮
- 触发 stop TTS 和 replan
- 输出状态机切换日志

状态机：

- `idle`
- `listening`
- `user_speaking`
- `user_paused`
- `assistant_preparing`
- `assistant_speaking`
- `interrupted`
- `replanning`

## 文件树

```text
experimental/voice_interrupt_demo/
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── scenarios/
│   ├── base.py
│   ├── scenario_1_normal.py
│   ├── scenario_2_pause_take_floor.py
│   ├── scenario_3_user_barge_in.py
│   ├── scenario_4_early_clarify.py
│   └── scenario_5_corrective_interrupt.py
├── core/
│   ├── context.py
│   ├── decisions.py
│   ├── events.py
│   ├── orchestrator.py
│   └── state_machine.py
├── asr/
│   ├── asr_interface.py
│   ├── mock_asr.py
│   └── mock_streaming_asr.py
├── dialogue/
│   ├── dialogue_interface.py
│   ├── dialogue_worker.py
│   ├── mock_llm.py
│   └── response_drafter.py
├── interrupt/
│   ├── barge_in_policy.py
│   ├── floor_taking_policy.py
│   ├── interrupt_worker.py
│   └── policies.py
├── tts/
│   ├── mock_tts.py
│   ├── playback_controller.py
│   └── tts_interface.py
└── utils/
    ├── clocks.py
    ├── ids.py
    ├── logger.py
    └── timers.py
```

## 运行

当前没有第三方运行依赖。

```bash
cd /Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo
python3 app.py --scenario 1 --log-level INFO
```

## Scenarios

Scenario 1: 正常完整问答

```bash
python3 app.py --scenario 1 --log-level INFO
```

预期看到：partial 阶段已经有 draft，final 后 assistant 获取话轮并完整回答。

Scenario 2: 用户停顿，assistant 主动提前短答

```bash
python3 app.py --scenario 2 --log-level INFO
```

预期看到：

- `[Intent hypothesis updated] intent=weather_query`
- `[Floor-taking decision emitted] action=soft_take_floor`
- `[Turn granted to assistant] type=soft_take_floor`
- assistant 在 final 前先说短回复

Scenario 3: assistant 说话时用户打断

```bash
python3 app.py --scenario 3 --log-level INFO
```

预期看到：

- assistant 先开始长回复
- 用户 `speech_started`
- `[Floor-taking decision emitted] action=stop_assistant`
- `[Turn revoked from assistant]`
- `[TTS STOPPED] during_chunk`
- 新输入 final 后重新规划回复

Scenario 4: 用户说到一半，assistant 提前追问

```bash
python3 app.py --scenario 4 --log-level INFO
```

预期看到：

- partial 是“我想问天气”
- draft 中 `missing=city,time`
- decision 为 `soft_take_floor`
- `candidate_type=clarify`
- assistant 主动追问“你是想问哪个城市、今天还是明天？”

Scenario 5: 用户纠正系统，assistant 强制抢话纠偏

```bash
python3 app.py --scenario 5 --log-level INFO
```

预期看到：

- partial 出现“不是 / 不对”
- decision 为 `hard_take_floor`
- `candidate_type=corrective`
- assistant 主动说“好，我先停一下，刚才那个理解可能不对。”

运行全部：

```bash
python3 app.py --scenario all --log-level INFO
```

## 关键日志

重点观察这些日志：

- `[ASR partial received]`
- `[ASR final received]`
- `[Intent hypothesis updated]`
- `[Dialogue draft updated]`
- `[Floor-taking decision emitted]`
- `[Turn granted to assistant]`
- `[Turn revoked from assistant]`
- `[TTS started]`
- `[TTS STOPPED]`
- `[Replan requested]`
- `[STATE]`

## 调策略

抢话阈值集中在 [config.py](/Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo/config.py)：

- `soft_take_floor_pause_ms`
- `hard_take_floor_pause_ms`
- `clarify_pause_ms`
- `soft_take_floor_min_confidence`
- `hard_take_floor_min_confidence`
- `proactive_cooldown_ms`

策略实现集中在：

- [floor_taking_policy.py](/Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo/interrupt/floor_taking_policy.py)
- [barge_in_policy.py](/Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo/interrupt/barge_in_policy.py)

候选回复生成集中在：

- [response_drafter.py](/Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo/dialogue/response_drafter.py)

## 浏览器测试页

保留了一个轻量 mock 页面：

```bash
open /Users/sunjingkai/Desktop/agentic/experimental/voice_interrupt_demo/web_demo.html
```

这个页面现在也使用同一套 mock 场景和决策结构，可直接观察：

- `DialogueDraft`
- `FloorDecision`
- `soft_take_floor`
- `hard_take_floor`
- `stop_assistant`
- 主 Agent / 抢话子 Agent / 播放控制器的状态切换

核心行为仍以 Python scenario 日志为准，网页适合做交互观察和演示。
