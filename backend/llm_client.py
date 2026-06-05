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
    "你是本地生活助手的意图解析器。从用户中文输入里提取结构化信息，只输出 JSON，不要多余文字。\n"
    "字段：\n"
    "- city：城市或null\n"
    "- party_size：人数或null\n"
    "- scene：date/friends/family/solo 或 null\n"
    "- budget：数字或null\n"
    "- preferences：字符串数组，描述偏好风格，如 拍照/美食/安静/小众/热闹\n"
    "- must_have：用户想做的活动 → 归纳成【最适合在地图App里搜索的实体场所类型词】，字符串数组，可多个。\n"
    "  这是关键：把口语化的「动作/心情/需求」翻译成可以直接搜到店的【地点类型】。例如：\n"
    "  喝酒/小酌/微醺/想喝两杯/续摊 → \"酒吧\"；唱歌/K歌/想吼两嗓子 → \"KTV\"；\n"
    "  看电影/想看个片 → \"电影院\"；看展/逛美术馆/艺术 → \"美术馆\"；\n"
    "  喝咖啡/找个地方坐坐/办公 → \"咖啡馆\"；喝茶/品茶 → \"茶馆\"；\n"
    "  密室/剧本杀 → 原词；想运动/出出汗 → \"健身房\"；按摩/放松身体/做spa → \"按摩SPA\"；\n"
    "  带孩子/亲子 → \"亲子乐园\"；逛街购物 → \"商场\"；看书 → \"书店\"；\n"
    "  夜宵/宵夜 → \"夜宵\"；甜品/下午茶 → \"甜品店\"；遛弯/散步/透气 → \"公园\"。\n"
    "  规则：①输出的是【名词性的场所类型】不是动作（要\"酒吧\"不要\"喝酒\"）；"
    "②遇到没列举的需求，也要自己归纳成一个最贴切、能在地图上搜到的场所类型词；"
    "③用户没点名任何具体活动时给空数组[]；④最多3个，按用户语气里的重视程度排序。\n"
    "- when：用户说的日期 today/tomorrow/weekend，或具体如\"周六\"\"6月8日\"；没提到则\"today\"。"
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
            # must_have：LLM 已归纳成场所类型词，保留其顺序，仅规整格式（去重/限长/兜底类型）
            entities["must_have"] = _clean_must(entities.get("must_have"))
            return {"entities": entities, "preference_vector": vector, "source": "llm"}
        except json.JSONDecodeError:
            pass
    # 兜底：关键词规则提取
    return {"entities": _keyword_entities(text), "preference_vector": vector, "source": "keyword"}



def _clean_must(labels) -> list[str]:
    """规整 LLM 返回的 must_have：统一成列表、去重、最多3个，原样保留 LLM 归纳的场所类型词。"""
    if not labels:
        return []
    if isinstance(labels, str):
        labels = [labels]
    out = []
    for l in labels:
        l = (l or "").strip()
        if l and l not in out:
            out.append(l)
    return out[:3]

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
