# 桌面联动协议

## 内置联动

右键桌宠 → **Agent 联动 → ChatGPT 工作状态（Work / Codex）** 开启监听，
ChatGPT 桌面端由玩家自行打开。开关默认关闭，保存到现有
`agent_link.codex` 键，升级后无需转换该键。Cursor 和用户定义的事件通道继续可用。

ChatGPT Work/Codex 本机任务使用 `${CODEX_HOME}/sessions` 下的
`rollout-*.jsonl`；未设置 `CODEX_HOME` 时使用 `~/.codex/sessions`。
桌宠只读这些文件，不修改 ChatGPT 设置、会话或审批结果，不需要 API Key。
本机日志也可能包含 Codex CLI 任务，因此该入口感知同一目录下的 Work/Codex 任务。

日志格式是桌面端的内部实现细节，并非官方稳定 API。普通 Chat 的对话内容和
云端任务不在此监听范围内；格式变化后需更新解析器。官方桌面端背景说明：
[ChatGPT Windows app](https://learn.chatgpt.com/docs/windows/windows-app)。

| 日志事件 | 桌宠状态 |
| --- | --- |
| `task_started` | working，播放工作动作 |
| `response_item/reasoning` | thinking，播放思考动作 |
| 工具调用和工具结果 | working，按概率显示过程气泡 |
| `request_user_input` 工具调用或审批请求 | attention，提示回应用处理 |
| `task_complete` | idle，稳定 800 毫秒后显示完成提醒 |
| `turn_aborted` | idle，中断结果显示中性提醒 |
| `task_failed` / `error` | error，错误提醒 |

会话身份取自 `session_meta`；回合身份由 `task_started` 或 `turn_context` 更新，
后续不带身份的记录沿用该文件的上下文。不同文件相互隔离。初次启用跳过历史工作
记录，只读取首行元数据与末尾最多 256 KiB 中的回合标识；启用后新建的会话从头读取。
停用后再次启用重新跳过历史。保留最近已结束会话，超过 256 条后清理旧的已结束会话。
最多跟踪近期 50 个文件，单次单文件读取最多 1 MiB，单行限制 64 KiB，目录发现每 15 秒进行一次，
已发现文件每 1.5 秒读取增量。复杂事件可能超过单行上限而被跳过。
只向气泡模块传递来源、会话、回合、工具名和项目名称，不传递提示词、推理或工具输出。

桌宠不启动或激活 ChatGPT；联动仅消费本机工作状态。

## 自定义事件通道

配置条目示例：

```json
{
  "agent_link": {
    "custom_agents": [
      {"key": "sidekick", "name": "小助手", "path": "C:/my-agent/events.jsonl"}
    ],
    "sidekick": true
  }
}
```

每行一个 UTF-8 JSON 对象，必须以换行结尾。支持 BOM、部分行缓冲、文件截断和轮转。
初次发现已有文件时跳过历史行。修改通道条目后重启桌宠。

```json
{"event":"task_started","state":"working","sessionId":"s1","turnId":"t1"}
{"event":"tool/call","tool":"read","sessionId":"s1","turnId":"t1"}
{"event":"task_complete","state":"idle","sessionId":"s1","turnId":"t1"}
```

`state` 取值：`idle / thinking / working / attention / sleeping / error`。
未知事件若没有合法 `state` 则忽略。审批和问题可用
`approval/requested / approval/resolved / question/requested / question/resolved`，
需携带稳定 `rpcId / approvalId / requestId / callId` 和 `sessionId` 以精确关闭提醒。
桌宠显示提醒，决策与回答在原应用完成。

会话和回合标识用于并发聚合与迟到完成事件过滤；写入方应始终使用稳定标识，
保证一个会话结束不会让另一个仍在工作的会话停止动画。
