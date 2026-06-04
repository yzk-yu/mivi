"""
觅 MIVI · 可切换 LLM 层
------------------------------------------------------------------
DeepSeek / Kimi / 通义 都兼容 OpenAI 的 /chat/completions，所以一套代码三家通用，
靠 config.LLM_PROVIDER 切换。任何失败都不抛给用户——回退到关键词兜底。
"""
from __future__ import annotations
import json
import requests

import config
import core

TIMEOUT = 20


def chat(messages: list[dict], temperature: float = 0.3, json_mode: bool = False,
         timeout: int = TIMEOUT) -> str | None:
    """统一的 LLM 调用。返回文本；不可用或出错返回 None（让调用方走兜底）。"""
    if not config.llm_available():
        return None
    cfg = config.active_llm()
    try:
        body = {"model": cfg["model"], "messages": messages, "temperature": temperature, "stream": False}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            json=body, timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # 网络/限流/格式都在此兜底
        print(f"[llm] 调用失败，回退兜底：{e}")
        return None


# ── 意图理解：LLM 语义提取（关键词表兜底）──
INTENT_SYS = (
    "你是本地生活助手的意图解析器。从用户中文输入里提取结构化信息，"
    "只输出 JSON，字段：city(城市或null)、party_size(人数或null)、"
    "scene(date/friends/family/solo或null)、budget(数字或null)、"
    "preferences(字符串数组，如拍照/美食/安静)、"
    "must_have(用户明确点名要做的活动或要去的地点类型，字符串数组，可多个；"
    "如看电影→[\"电影院\"]、又看电影又喝咖啡→[\"电影院\",\"咖啡\"]、唱歌→[\"KTV\"]、"
    "看展→[\"展览\"]；没有明确点名则为空数组[])、"
    "when(用户说的日期：today/tomorrow/weekend，或具体如\"周六\"\"6月8日\"；"
    "没提到则\"today\")。不要多余文字。"
)


def parse_intent(text: str, prev_vector: dict | None = None) -> dict:
    """返回 {entities, preference_vector}。LLM 优先，失败回退关键词。"""
    # 偏好向量：优先调用 user-profiling skill 提取；失败回退后端 core
    import skill_bridge
    # 先用 core 拿到一个合法的基准向量(含默认值)，再交给 skill 在此基础上提取
    base_vec = core.extract_signals(text, prev_vector)
    vector = skill_bridge.profiling_extract(text, prev_vector or base_vec)
    if vector is None:
        vector = base_vec   # skill 失败 → 用 core 的结果

    content = chat(
        [{"role": "system", "content": INTENT_SYS}, {"role": "user", "content": text}],
        json_mode=True,
    )
    if content:
        try:
            entities = json.loads(content)
            import activities
            # must_have 规整成按强度排序的 label 列表（DeepSeek 可能返回字符串或数组）
            entities["must_have"] = activities.normalize(entities.get("must_have"))
            return {"entities": entities, "preference_vector": vector, "source": "llm"}
        except json.JSONDecodeError:
            pass
    # 兜底：关键词规则提取
    return {"entities": _keyword_entities(text), "preference_vector": vector, "source": "keyword"}


def _keyword_entities(text: str) -> dict:
    import re
    import activities
    nums = [int(n) for n in re.findall(r"\d+", text)]
    return {
        "city": "苏州" if "苏州" in text else None,
        "party_size": 2 if ("女朋友" in text or "两个人" in text or "情侣" in text) else None,
        "scene": "date" if ("约会" in text or "女朋友" in text) else None,
        "budget": next((n for n in nums if 50 <= n <= 5000), None),
        "preferences": [p for p in ["拍照", "美食", "安静", "探索"] if p in text],
        "must_have": activities.detect_activities(text),   # 多个，按强度排序
        "when": ("tomorrow" if "明天" in text else
                 "weekend" if ("周末" in text or "周六" in text or "周日" in text or "星期六" in text or "星期日" in text) else
                 "today"),
    }


# ── 推荐理由：LLM 生成（模板兜底）──
def gen_reasoning(venue: str, context: str) -> list[str] | None:
    content = chat([
        {"role": "system", "content": "你是觅狐，用亲切口吻给出选择某地点的 3 条简短理由，每条一句话，输出 JSON 数组。"},
        {"role": "user", "content": f"地点：{venue}。背景：{context}"},
    ], json_mode=True)
    if content:
        try:
            data = json.loads(content)
            return data if isinstance(data, list) else data.get("reasons")
        except (json.JSONDecodeError, AttributeError):
            return None
    return None


# ── 详情页：为真实店生成评分细分 + 模拟评论（点详情时按需调用）──
VENUE_DETAIL_SYS = (
    "你是本地生活点评助手。根据给定的店名、类型、评分、人均，"
    "生成合理的评分细分和 2-3 条模拟用户评论。评论要自然、有细节、像真实点评，"
    "但你必须知道这些是 AI 模拟生成的示例，不是真实用户评价。\n"
    "只输出 JSON：{\"rating_detail\":{\"taste\":数字,\"env\":数字,\"service\":数字}(都在3.5-5之间),"
    "\"recommend\":[\"招牌菜1\",\"招牌菜2\"],"
    "\"reviews\":[{\"name\":\"用户***\",\"date\":\"2025-XX-XX\",\"stars\":数字,\"text\":\"评论内容\"}]}。"
    "餐厅给招牌菜，咖啡/景点 recommend 可为空数组。"
)

def gen_venue_detail(name: str, vtype: str, rating, cost) -> dict | None:
    """为真实店生成评分细分 + 模拟评论。失败返回 None。"""
    user = f"店名：{name}；类型：{vtype}；评分：{rating or '未知'}；人均：{cost or '未知'}元。请生成。"
    raw = chat(
        [{"role": "system", "content": VENUE_DETAIL_SYS}, {"role": "user", "content": user}],
        temperature=0.7, json_mode=True, timeout=30,
    )
    if not raw:
        return None
    try:
        import json as _json
        return _json.loads(raw)
    except Exception:
        return None
