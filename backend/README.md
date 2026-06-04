# 觅 MIVI · 后端

FastAPI 实现 12 个接口（10 个核心 + 多方式路径 + 授权就近搜索），对齐 `API_SPEC.md`。
支持 Mock / 真实接口一键切换；LLM 三家（DeepSeek/Kimi/通义）可切换。

## 启动
```bash
pip install -r requirements.txt
cp .env.example .env        # 填入自己的 key（没有也能跑，自动走 Mock）
set -a; source .env; set +a # 加载环境变量
uvicorn main:app --reload --port 8080
```
交互式 API 文档：http://localhost:8080/docs

## Mock / 真实切换
- `MIVI_USE_MOCK=true`：全程假数据，演示最稳，**无需任何 key**
- `MIVI_USE_MOCK=false`：走真实接口（高德 + DeepSeek）；某项缺 key 时该项自动回退 Mock，不影响其余

## 数据来源与合规
| 数据 | 来源 |
|------|------|
| POI/路径/天气/地理编码 | 高德官方 API（真） |
| 意图理解/推荐理由 | DeepSeek/Kimi/通义（真，可切换） |
| 电影/演唱会、点评评价 | Mock（无公开 API，禁爬取） |
| 用户偏好 | 用户对话输入 → 8 维向量，匿名 session 存内存 |

- 位置：仅来自「用户说的地名(geocode)」或「用户授权的 GPS」；GPS 坐标**用完即焚**，绝不落盘、绝不和身份绑定。
- 偏好向量里只有 8 维数字，无任何身份字段。会话结束即清。

## 文件
- `main.py`        — 12 个接口 + CORS + 匿名会话
- `core.py`        — 核心算法：增量纠错状态机 + 8 维偏好向量（技术亮点）
- `llm_client.py`  — 可切换 LLM 层（DeepSeek/Kimi/通义），失败回退关键词
- `amap_client.py` — 高德客户端 + 智能选交通（按距离+画像选步行/公交/驾车）
- `mock_data.py`   — 苏州约会场景演示数据（全部虚构/合规）
- `config.py`      — 开关与密钥（从环境变量读）

---

## 事中陪伴接口（in-trip，第 11–14 号）

出发后进入"事中"，以下接口支撑：进度、临时调整、提醒。
所有状态按 `trip_id` 存于内存 `TRIPS`，匿名、不落库、行程结束即可丢弃。

| # | 方法 | 路径 | 作用 |
|---|------|------|------|
| 11 | POST | `/api/v1/trips/{trip_id}/progress` | 上报/查询当前到哪站（completed / current / upcoming） |
| 12 | POST | `/api/v1/trips/{trip_id}/adjust` | 事中调整：`action` = skip/add/move/extend，自动重排（含路上时间） |
| 13 | POST | `/api/v1/trips/{trip_id}/reminders` | 用户自定义提醒规则（被动兜底） |
| 14 | GET | `/api/v1/trips/{trip_id}/check-reminders` | 主动提醒判断：返回该触发的 time/weather/queue/late 提醒 + 建议动作 |

**主动提醒（14 号）数据源**：天气走高德 `weather()`（真实，需 key）；排队可接高德实时/估算。
判断逻辑在 `core.check_reminders()`，纯函数，可被轮询或事件驱动调用。

**真实接入**：填 `AMAP_API_KEY` + `DEEPSEEK_API_KEY` 到 `.env`，设 `MIVI_USE_MOCK=false`，
天气等即走真实高德；其余事中逻辑与 Mock 一致。
