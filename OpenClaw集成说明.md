# 觅 MIVI 如何基于 OpenClaw 开发

> 本文档对应赛题要求 **第 1 条（框架要求）** 与 **第 2 条（Skill 开发规范）**，
> 说明觅 MIVI 如何基于 OpenClaw 开源 Agent 框架构建，并给出可复现的验证步骤与实测证据。

---

## 一、采用的框架与版本

- **框架**：OpenClaw（开源、可自托管的多通道 AI Agent 框架，作者 Peter Steinberger）
- **实测版本**：`OpenClaw 2026.6.1 (2e08f0f)`
- **官方仓库 / 文档**：https://github.com/openclaw/openclaw ｜ https://docs.openclaw.ai
- **选型理由**：OpenClaw 通过 Gateway 统一连接 20+ 聊天通道与 30+ 模型，原生支持
  「IM 对话 + Skill 扩展」机制，与赛题「用自然语言对话重塑本地生活 App 交互」高度契合。
  其 Skill 系统（兼容 AgentSkills 规范）正是我们封装餐饮 / 出行 / 娱乐能力的理想载体。

---

## 二、觅 MIVI 与 OpenClaw 的关系（架构）

```
用户（自然语言）
   │
   ▼
OpenClaw Gateway ──加载──► <workspace>/skills/   ← 觅 MIVI 的 4 个 Skill 挂在这里
   │                         ├── smart-itinerary/      行程规划师
   │                         ├── user-profiling/       偏好画像（幕后服务）
   │                         ├── local-dining/         餐饮管家
   │                         └── local-entertainment/  娱乐顾问
   │
   ├─ Skill 的 SKILL.md 注入 Agent：人格、触发条件、调用逻辑
   │
   ▼
觅 MIVI 服务层（FastAPI 后端，14 接口）
   ├── 增量重排算法 / 8 维偏好向量（core.py）
   ├── 高德 Web 服务 API（真实 POI / 路线 / 天气）
   └── DeepSeek（意图理解 / 推荐编排）
   │
   ▼
对话式前端（mivi.html）：规划单栏对话 → 出发后切双栏（对话 + 行程面板）
```

**分工**：OpenClaw 负责「对话入口 + Skill 加载 / 路由 / 门控 + Agent 人格注入」；
觅 MIVI 的 Skill 声明能力契约与调用逻辑，后端作为 Skill 背后的服务层提供算法与真实数据。

---

## 三、4 个 Skill 严格遵循 OpenClaw 插件规范（对应赛题第 2 条）

每个 Skill 都是 `<workspace>/skills/<name>/` 目录，含 `SKILL.md` + `scripts/` 实现代码，
完全符合 OpenClaw 官方 SKILL.md 规范：

| Skill | 作用 | 关键规范点 |
|---|---|---|
| `smart-itinerary` 🗺️ | 全天动线编排、出发前检查、事中主动提醒、超时增量纠错 | 单行 metadata JSON、`{baseDir}` 引脚本 |
| `user-profiling` 👤 | 从对话提取偏好信号、维护 8 维偏好向量（幕后服务） | `requires.env`、`primaryEnv` 门控 |
| `local-dining` 🍜 | 餐厅推荐、点单建议、避雷、多人口味协调 | `description` 写成触发条件句 |
| `local-entertainment` 🎭 | 咖啡 / 商圈 / 展览 / 电影，天气自适应室内外 | `user-invocable`、kebab-case 命名 |

**逐条对齐官方规范**（依据 `docs.openclaw.ai/zh-CN/tools/skills`）：
- ✅ 目录含 `SKILL.md`，YAML frontmatter 以 `---` 包裹
- ✅ 必填 `name`（kebab-case）、`description`（触发条件句）
- ✅ **`metadata` 为单行 JSON 对象**（OpenClaw 解析器硬约束，兼容 Pi Agent 运行时）
- ✅ `metadata.openclaw` 含 `requires.env` / `primaryEnv` / `emoji`（加载时门控）
- ✅ `scripts/` 存放可执行实现；正文用 `{baseDir}` 引用脚本路径
- ✅ `user-invocable: true`（暴露为斜杠命令）

---

## 四、实测验证（可复现 + 证据）

### 复现步骤

```bash
# 1. 安装 OpenClaw（Node 22.19+ / 推荐 24）
npm install -g openclaw@latest
openclaw --version          # 期望输出：OpenClaw 2026.x.x

# 2. 初始化工作区
openclaw setup              # 生成 ~/.openclaw/workspace 等目录

# 3. 挂载觅 MIVI 的 4 个 Skill
mkdir -p ~/.openclaw/workspace/skills
cp -r ./skills/* ~/.openclaw/workspace/skills/

# 4. 验证 OpenClaw 是否识别并加载我们的 Skill
openclaw skills list
```

### 实测结果（证据）

实测环境 `OpenClaw 2026.6.1 (2e08f0f)`，`openclaw skills list` 显示 `Skills (18/61 ready)`，
其中觅 MIVI 的 4 个 Skill 全部为 **`✓ ready`** 状态，来源标注为 **`openclaw-workspace`**
（区别于官方自带的 `openclaw-bundled`），说明已被 OpenClaw 正确识别、解析并就绪：

```
│ Status   │ Skill                    │ Source             │
├──────────┼──────────────────────────┼────────────────────┤
│ ✓ ready  │ 🍜 local-dining          │ openclaw-workspace │
│ ✓ ready  │ 🎭 local-entertainment   │ openclaw-workspace │
│ ✓ ready  │ 🗺️ smart-itinerary       │ openclaw-workspace │
│ ✓ ready  │ 👤 user-profiling        │ openclaw-workspace │
```

说明：4 个 Skill 均通过 OpenClaw 的加载与依赖门控检查，状态为 **`✓ ready`**，
来源 `openclaw-workspace` 表明它们是从工作区 `skills/` 目录被框架加载的用户自定义 Skill，
与官方内置的 `openclaw-bundled` 区分开来。这证明 MIVI 的 Skill 完全符合 OpenClaw 插件规范、
可被框架正常装载与调度。

---

## 五、与赛题要求的对应

| 赛题要求 | 觅 MIVI 的落实 |
|---|---|
| **1. 必须基于 OpenClaw，文档说明** | 基于 OpenClaw 2026.6.1；本文档 + 实测截图为证 |
| **2. Skill 遵循 OpenClaw 规范，≥3 个核心技能** | 4 个 Skill（餐饮 / 出行 / 娱乐 / 画像），经官方规范逐条验证，已被框架成功加载 |
| **3. 不收集真实个人信息，偏好用模拟或显式输入** | 见 `README.md` 数据安全章节：零 PII、匿名内存、定位用完即焚 |
