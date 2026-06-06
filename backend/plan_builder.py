"""
觅 MIVI · 真实出方案构建器
------------------------------------------------------------------
流程：高德分类搜 POI → 代码粗筛去杂物 → DeepSeek 二次审查+编排 → 兜底。
任何一步失败都优雅降级，最终不会让前端白屏（回退到 Mock 方案）。

合规：城市/坐标仅用于本次搜索，不存储；POI 来自高德公开 API。
"""
from __future__ import annotations
import json

import config
import amap_client
import llm_client
import scorer
import mock_data as M

# 每个场景要搜的 POI 类别：(关键词, 高德分类码前缀白名单, 该类在方案里的 kind)
# 分类码：050000=餐饮 060000=购物 080000=体育休闲 110000=风景名胜 100000=住宿
DINING_CODES = ("05",)
CAFE_KW = "咖啡"
SCENIC_CODES = ("11", "14")   # 风景名胜 / 科教文化(博物馆等)
ENTERTAIN_CODES = ("08", "06")  # 体育休闲 / 购物商圈

# 明确要剔除的杂物类型码前缀（加油站/停车场/公交站/政府机构等）
JUNK_CODES = ("0101", "1509", "1507", "1508", "1900", "1300", "1classroom")
JUNK_WORDS = ("加油站", "停车场", "公交", "地铁站", "管理处", "管委会", "派出所",
              "政府", "服务区", "收费站", "充电站", "汽车")


def _is_junk(poi: dict) -> bool:
    code = (poi.get("typecode") or "")
    name = (poi.get("name") or "")
    if any(code.startswith(j) for j in JUNK_CODES):
        return True
    if any(w in name for w in JUNK_WORDS):
        return True
    return False


def _search_category(keyword: str, city: str, location: str, types: str = "", n: int = 5, lenient: bool = False) -> list[dict]:
    """搜一类 POI，去杂物，最多留 n 个。失败返回 []。
    lenient=True（用户点名的活动）：少过滤 + 搜空时去掉坐标偏置重试一次。"""
    pois = amap_client.place_text(keyword, city=city, page_size=n + 5, types=types, location=location)
    # 宽松模式：带坐标偏置搜空 → 去掉偏置，全城再搜一次
    if lenient and not pois and location:
        pois = amap_client.place_text(keyword, city=city, page_size=n + 5, types=types)
    if not pois:
        return []
    if lenient:
        # 用户点名要的，只去掉最明显的杂物（加油站/停车场等），不按 typecode 狠筛
        clean = [p for p in pois if p.get("name") and not any(w in (p.get("name") or "") for w in JUNK_WORDS)]
    else:
        clean = [p for p in pois if p.get("name") and not _is_junk(p)]
    return clean[:n]


def gather_pois(city: str, location: str = "", must_have=None) -> dict:
    """搜齐四类候选 POI（咖啡/景点/餐厅/娱乐）。
    must_have 是用户点名的活动 label 列表，为每个额外搜店，放进 must_{label}。
    返回的 dict 里 _missing_must 记录没搜到店的活动，供前端跟用户沟通。"""
    import activities
    pois = {
        "cafe": _search_category(CAFE_KW, city, location, n=4),
        "scenic": _search_category("景点 博物馆 公园", city, location, n=5),
        "dining": _search_category("餐厅", city, location, types="050000", n=6),
        "entertain": _search_category("商圈 展览 书店", city, location, n=4),
    }
    missing = []
    for label in (must_have or []):
        kw = activities.search_word(label)
        found = _search_category(kw, city, location, n=5, lenient=True)
        print(f"[plan] 点名活动「{label}」搜索词「{kw}」→ 搜到 {len(found)} 个")
        if found:
            pois[f"must_{label}"] = found
        else:
            missing.append(label)
    pois["_missing_must"] = missing
    return pois


# DeepSeek 二次审查 + 编排：一次调用同时做"质检筛选"和"排成时间线"
REVIEW_SYS = (
    "你是本地生活行程规划专家，也是 POI 质检员。我会给你一批从地图搜来的真实候选地点"
    "（可能含噪声）。你要：1) 剔除不适合休闲约会/游玩的点（如批发市场、连锁快餐、"
    "无关机构）；2) 从优质点里编排一套带时间线的半天到一天行程，结构合理"
    "（如 咖啡→景点→正餐→夜游 的节奏，按用户场景和偏好调整）；"
    "3) 每个选中点给一句『为什么排在这』。\n"
    "只输出 JSON，格式：{\"title\":\"方案名\",\"summary\":\"一句话描述\","
    "\"slots\":[{\"time\":\"HH:MM\",\"venue\":\"店名(必须来自候选)\",\"kind\":\"cafe/scenic/dining/entertain/walk\","
    "\"duration\":分钟,\"price\":人均估算数字,\"reason\":\"为什么排这\"}],"
    "\"budget\":总预算数字,\"tags\":[\"标签\"]}。venue 必须严格来自候选列表，不要编造。"
)


def _compose_with_llm(pois: dict, req) -> dict | None:
    """把候选 POI 交给 DeepSeek 审查+编排。失败返回 None。"""
    # 候选清单压缩成精简文本，省 token
    # A 提速：候选已按匹配分降序，每类只取前 5 个高分店给 DeepSeek（低分的它也不会选）
    TOP_N = 5
    def brief(items):
        return [
            {"name": p["name"], "type": (p.get("type") or "").split(";")[-1],
             "rating": p.get("rating"), "cost": p.get("cost"),
             "match": p.get("match_score")}
            for p in items[:TOP_N]
        ]
    candidates = {k: brief(v) for k, v in pois.items()}
    prefs = req.preference_vector or {}
    must_list = getattr(req, "must_have", None) or []
    must_hint = ""
    if must_list:
        joined = "、".join(f"「{m}」" for m in must_list)
        must_hint = (f"【重要】用户明确点名要：{joined}，这些是硬性要求，方案里必须各包含一个对应地点"
                     f"（候选里 must_ 开头的类别就是为这些活动搜的）。按用户给的强弱顺序，越靠前越重要。\n")
    # 真实当前时间（中国时区 UTC+8），让 DeepSeek 从合理的起点排
    from datetime import datetime, timezone, timedelta
    now_cn = datetime.now(timezone(timedelta(hours=8)))
    now_str = now_cn.strftime("%H:%M")
    hour = now_cn.hour
    when = getattr(req, "when", None) or "today"
    if when == "today":
        # 今天：从现在之后就近开始
        start_hint = f"现在是中国时间 {now_str}。请安排从现在之后能马上出发的时间开始（第一站开始时间设在 {now_str} 之后的就近时段，比如再过 20-40 分钟），不要排已经过去的时间。"
        if hour >= 21 or hour < 6:
            start_hint = f"现在是中国时间 {now_str}，已经比较晚了。今天剩下时间不多，请安排一个简短的夜间行程，或建议改到明天。"
    elif when == "tomorrow":
        start_hint = "用户要安排【明天】的行程，不受现在时间限制。请从明天上午合理时间（如 9:30-10:30）开始，安排一整天/半天的行程。"
    elif when == "weekend":
        start_hint = "用户要安排【周末】的行程，不受现在时间限制。请从上午合理时间（如 10:00 左右）开始，安排一整天的行程。"
    else:
        start_hint = f"用户指定的日期是「{when}」，不受现在时间限制。请从该日上午合理时间开始，安排一整天/半天的行程。"
    user_msg = (
        f"城市：{req.city}；场景：{req.scene}；人数：{req.party_size}；预算：约{req.budget}元。\n"
        f"{must_hint}"
        f"{start_hint}\n"
        f"偏好向量(0-1，越高越在意)：{json.dumps(prefs, ensure_ascii=False)}\n"
        f"候选地点（按类别，match 是系统按用户画像算的匹配分0-100，match_why 是匹配理由）：{json.dumps(candidates, ensure_ascii=False)}\n"
        f"请优先选择 match 分高的店（这是按用户画像算好的匹配度），结合时间线合理性审查并编排出一套行程。"
    )
    raw = llm_client.chat(
        [{"role": "system", "content": REVIEW_SYS}, {"role": "user", "content": user_msg}],
        temperature=0.4, json_mode=True, timeout=60,
    )
    if not raw:
        return None
    try:
        plan = json.loads(raw)
        if not plan.get("slots"):
            return None
        # 按 kind 映射图标 emoji（前端 slot 要 icon 字段）
        ICON = {"cafe": "☕", "scenic": "🏛️", "dining": "🍽️", "entertain": "🎭",
                "walk": "🚶", "indoor": "📖", "scene": "🌆", "night": "🌙"}
        for s in plan["slots"]:
            s.setdefault("walk", 10)
            s.setdefault("price", 0)
            s.setdefault("duration", 60)
            s["icon"] = ICON.get(s.get("kind"), "📍")
        plan["id"] = "real"
        plan["source"] = "amap+deepseek"
        plan["recommended"] = True          # 前端靠这个挑推荐方案
        plan["checked"] = [True] * len(plan["slots"])  # 默认全勾选
        plan["buffer_minutes"] = 60         # 缓冲池，重排算法要
        plan.setdefault("title", "为你定制")
        plan.setdefault("summary", "根据你的偏好实时编排")
        plan["name"] = plan.get("title", "为你定制")  # 前端标题用 plan.name
        # 补 metrics（前端方案卡底部的指标）
        total_budget = plan.get("budget") or sum(s.get("price", 0) for s in plan["slots"])
        plan["metrics"] = {
            "comfort": plan.get("comfort", 85),
            "fatigue": "低" if len(plan["slots"]) <= 4 else "中",
            "budget": total_budget,
            "queue_risk": "低",
        }
        return plan
    except Exception as e:
        print(f"[plan] DeepSeek 返回解析失败：{e}")
        return None


def build_real_plan(req) -> dict | None:
    """
    真实出方案主流程。任一步失败返回 None（调用方回退 Mock）。
    需要：高德可用（搜 POI）+ DeepSeek 可用（审查编排）。
    """
    if not config.amap_available():
        return None  # 没有真实高德，直接走 Mock

    # 1. 坐标偏置：优先级 GPS坐标 > 具体地点(anchor) > 城市中心
    location = ""
    user_origin = getattr(req, "origin", None)
    anchor = getattr(req, "anchor", None)   # 用户说的具体地点，如"杭州万象城"
    if user_origin and "," in str(user_origin):
        location = user_origin   # 用户授权了GPS，就搜其附近
    elif anchor:
        # 用户指定了具体地点 → geocode 成坐标，以它为中心就近安排
        pt = amap_client.geocode(anchor, req.city)
        if pt:
            location = pt
            print(f"[plan] 以指定地点「{anchor}」为中心 → {pt}")
        else:
            center = amap_client.geocode(req.city, req.city)
            if center: location = center
    else:
        center = amap_client.geocode(req.city, req.city)
        if center:
            location = center

    # 2. 搜齐候选 POI
    pois = gather_pois(req.city, location, getattr(req, "must_have", None))
    missing_must = pois.pop("_missing_must", [])   # 取出"没搜到的点名活动"，不参与打分
    total = sum(len(v) for v in pois.values())
    if total < 3:
        print(f"[plan] 候选 POI 太少({total})，回退 Mock")
        return None

    # 2.5 显式偏好匹配打分：给每个候选算匹配分并按 kind 内降序
    budget_total = float(getattr(req, "budget", 0) or 0)
    pois = scorer.rank_pois(pois, req.preference_vector or {}, budget_total)

    # 3. DeepSeek 二次审查 + 编排
    plan = _compose_with_llm(pois, req)
    if not plan:
        return None

    # 4. 附上候选 POI 的富信息（照片/电话/地址），供详情页用
    flat = {p["name"]: p for cat in pois.values() for p in cat}
    plan["poi_detail"] = {
        s["venue"]: flat.get(s["venue"], {}) for s in plan["slots"]
    }
    # 把匹配分 / 匹配理由写进每个 slot（前端可显示「匹配度」）
    for s in plan["slots"]:
        cand = flat.get(s["venue"], {})
        if "match_score" in cand:
            s["match_score"] = cand["match_score"]
            s["match_reasons"] = cand.get("match_reasons", [])

    # 5. 用相邻两站真实坐标补算高德路线（步行/公交/骑行自动选），写进 slot.transport
    slots = plan["slots"]
    for i in range(len(slots) - 1):
        a = flat.get(slots[i]["venue"], {})
        b = flat.get(slots[i + 1]["venue"], {})
        loc_a, loc_b = a.get("location"), b.get("location")
        if loc_a and loc_b:
            try:
                t = amap_client.pick_transport(loc_a, loc_b, req.city, req.preference_vector)
                rec = t.get("recommended", {})
                slots[i]["transport"] = {
                    "label": rec.get("label", "🚶 步行"),
                    "mode": rec.get("mode", "walking"),
                    "duration_min": rec.get("duration_min", 10),
                    "options": t.get("options", []),
                }
                slots[i]["walk"] = rec.get("duration_min", slots[i].get("walk", 10))
            except Exception as e:
                print(f"[plan] 站间路线计算失败({slots[i]['venue']}→{slots[i+1]['venue']}): {e}")

    if missing_must:
        plan["missing_must"] = missing_must   # 用户点名但没搜到的活动，前端告知用户
    plan["when"] = getattr(req, "when", None) or "today"   # 哪天的行程，前端事中提醒据此判断
    return plan


def generate(req) -> dict:
    """
    对外入口：返回 {plans:[...], source:...}。
    真实优先；不可用/失败时回退 Mock 三方案，保证前端永远有结果。
    """
    real = None
    try:
        real = build_real_plan(req)
    except Exception as e:
        print(f"[plan] 真实出方案异常，回退 Mock：{e}")
        real = None

    if real:
        # 真实方案放首位（推荐），再附 Mock 的另两套作为节奏对比备选
        return {"plans": [real], "source": "amap+deepseek"}

    # 兜底：Mock 三方案
    return {"plans": [M.PLANS["comfort"], M.PLANS["efficient"], M.PLANS["surprise"]],
            "source": "mock"}
