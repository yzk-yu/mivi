"""
觅 MIVI · 后端主入口 (FastAPI)
------------------------------------------------------------------
实现 API_SPEC.md 里的 10 个接口。当前全部走 Mock，结构与前端 api.* 对齐。
启动：  uvicorn main:app --reload --port 8080
文档：  http://localhost:8080/docs   (FastAPI 自带交互式 API 文档)

合规：不收集真实个人信息；偏好向量仅以匿名 session_id 存于内存。
"""
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import core
import config
import llm_client
import amap_client
import mock_data as M
import plan_builder

app = FastAPI(title="觅 MIVI Backend", version="1.0.0")

# 开发期全开跨域；上线改成具体前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ── 会话级偏好向量（匿名，内存，合规）。key = 匿名 session_id ──
SESSIONS: dict[str, dict[str, float]] = {}

def get_vector(session_id: str) -> dict[str, float]:
    return SESSIONS.setdefault(session_id, dict(core.DEFAULT_VECTOR))


# ════════════════════════════════════════════════════════════════
# 接口 1 · 意图理解  POST /api/v1/intent/parse
# ════════════════════════════════════════════════════════════════
class IntentReq(BaseModel):
    message: str
    session_id: str = "demo"

@app.post("/api/v1/intent/parse")
def parse_intent(req: IntentReq):
    # LLM 语义提取（DeepSeek/Kimi/通义可切换）；不可用时自动回退关键词规则
    result = llm_client.parse_intent(req.message, get_vector(req.session_id))
    SESSIONS[req.session_id] = result["preference_vector"]
    entities = result["entities"]
    missing = [k for k in ("city",) if not entities.get(k)]
    return {
        "intent": "local_life_plan",
        "entities": entities,
        "missing_fields": missing,
        "follow_up_question": "你们在哪个城市？大概几点出发？" if missing else "你今天更想要哪种节奏？",
        "preference_vector": result["preference_vector"],
        "extract_source": result["source"],   # llm / keyword，方便演示时看走了哪条
    }


# ════════════════════════════════════════════════════════════════
# 接口 2 · 全天计划生成  POST /api/v1/plans/generate
# ════════════════════════════════════════════════════════════════
class PlanReq(BaseModel):
    city: str = "苏州"
    time_range: str | None = None
    party_size: int = 2
    scene: str = "date"
    budget: int = 500
    preference_vector: dict | None = None
    must_have: list[str] | None = None
    when: str | None = None
    origin: str | None = None   # 用户真实坐标"经,纬"(GPS授权时)，就近搜

@app.post("/api/v1/plans/generate")
def generate_plans(req: PlanReq):
    # 真实优先：高德搜 POI + DeepSeek 二次审查/编排；不可用或失败自动回退 Mock。
    return plan_builder.generate(req)


# ════════════════════════════════════════════════════════════════
# 接口 3 · 推荐理由  GET /api/v1/plans/{id}/reasoning
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/plans/{plan_id}/reasoning")
def reasoning(plan_id: str):
    return {
        "reasoning": [
            {"venue": "晴川日料", "decision": "selected", "reasons": [
                "步行 10 分钟就到，路线顺畅",
                "预计排队 15 分钟，在可接受范围内",
                "环境安静，差评率仅 3%，适合约会",
            ]},
            {"venue": "花见寿司", "decision": "rejected", "reasons": [
                "周六晚高峰排队通常 50+ 分钟",
                "位置在新区，从博物馆过去要打车 25 分钟，打乱路线",
                "差评中「排队久」「环境吵」高频出现",
            ]},
        ],
        "conclusion": "你们今天想轻松，所以稳定体验 > 极致评分。",
    }


# ════════════════════════════════════════════════════════════════
# 接口 4 · 出发前检查  GET /api/v1/plans/{id}/precheck
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/plans/{plan_id}/precheck")
def precheck(plan_id: str, city: str = "苏州"):
    # 真实天气（高德），失败给中性兜底
    w = None
    if config.amap_available():
        wd = amap_client.weather(city)
        if wd:
            cond = wd.get("weather") or "晴"
            temp = wd.get("temperature")
            rainy = any(k in cond for k in ["雨", "雪", "雷"])
            w = {
                "venue": "天气",
                "status": "warning" if rainy else "ok",
                "note": f"{cond} {temp}°C，" + ("出门记得带伞" if rainy else "适合出行"),
            }
    if not w:
        w = {"venue": "天气", "status": "ok", "note": "天气信息暂不可用，出门前留意一下哦"}

    # 调用 local-entertainment skill：基于真实天气，判断户外活动要不要换室内
    weather_switch = None
    import skill_bridge
    cond = "晴"
    temp = None
    if config.amap_available():
        wd = amap_client.weather(city)
        if wd:
            cond = wd.get("weather") or "晴"
            try:
                temp = int(wd.get("temperature"))
            except (TypeError, ValueError):
                temp = None
    # 用方案里的活动(若后端有存)，否则用通用户外活动样例让 skill 给出天气建议
    plan = M.PLANS.get(plan_id)
    if plan and plan.get("slots"):
        acts = [{"name": s["venue"], "outdoor": s["kind"] in ("scenic", "walk"), "alt": "附近室内场所"}
                for s in plan["slots"]]
    else:
        acts = [{"name": "户外景点/散步", "outdoor": True, "alt": "附近室内场所(商场/书店/咖啡)"}]
    weather_switch = skill_bridge.entertainment_weather_switch(cond, temp, acts)

    return {
        "checks": [w],
        "overall": "pass",
        "planb_ready": True,
        "planb_summary": None,
        "weather_raw": w,
        "weather_switch": weather_switch,   # local-entertainment skill 的户外→室内决策(前端可选用)
    }


# ════════════════════════════════════════════════════════════════
# 接口 5 · 商家详情  GET /api/v1/venues/{name}
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/venues/{name}")
def venue_detail(name: str, city: str = "苏州"):
    v = M.VENUES.get(name)
    if v:
        return v
    # mock 里没有 → 真实店，去高德搜回详情
    if config.amap_available():
        pois = amap_client.place_text(name, city=city, page_size=1)
        if pois:
            p = pois[0]
            # 把高德富字段转成前端详情页要的结构（缺失字段优雅降级）
            rating = p.get("rating")
            cost = p.get("cost")
            vtype = (p.get("type") or "").split(";")[-1]
            # DeepSeek 生成评分细分 + 模拟评论（按需，失败则留空）
            gen = llm_client.gen_venue_detail(p.get("name") or name, vtype, rating, cost) or {}
            return {
                "type": "restaurant",
                "name": p.get("name") or name,
                "rating": float(rating) if rating else None,
                "reviewCount": None,
                "tags": [t for t in [vtype, f"人均 ¥{cost}" if cost else None] if t],
                "address": p.get("address"),
                "phone": (p.get("tel") or "").split(";")[0] or None,
                "hours": p.get("open_time"),
                "perCapita": float(cost) if cost else None,
                "currentQueue": None,
                "rating_detail": gen.get("rating_detail"),
                "recommend": gen.get("recommend", []),
                "avoid": [],
                "reviews": gen.get("reviews", []),
                "hero": {"color": "#FFB74D", "label": p.get("name") or name},
                "photos": [{"url": u} for u in p.get("photos", []) if u],
                "source": "amap",
                "review_note": "以下评分细分与评论由 AI 基于公开印象模拟生成，仅供参考，非真实平台用户评价。",
                "note": "信息来自高德地图公开数据。",
            }
    raise HTTPException(404, {"error": "VENUE_NOT_FOUND", "message": "未找到该商家"})


# ════════════════════════════════════════════════════════════════
# 接口 6 · 备选商家  GET /api/v1/venues/{name}/alternatives
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/venues/{name}/alternatives")
def alternatives(name: str):
    return {"original": name, "alternatives": M.ALTERNATIVES.get(name, [])}


# ════════════════════════════════════════════════════════════════
# 接口 7 · 到店辅助  GET /api/v1/venues/{name}/in-store-tips
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/venues/{name}/in-store-tips")
def in_store_tips(name: str):
    tips = M.IN_STORE_TIPS.get(name)
    if not tips:
        raise HTTPException(404, {"error": "VENUE_NOT_FOUND", "message": "暂无该商家的到店建议"})
    return tips


# ════════════════════════════════════════════════════════════════
# 接口 8 · 超时纠错  POST /api/v1/plans/{id}/reschedule
# ════════════════════════════════════════════════════════════════
class RescheduleReq(BaseModel):
    plan_id: str = "comfort"
    current_venue: str
    delay_minutes: int

@app.post("/api/v1/plans/{plan_id}/reschedule")
def do_reschedule(plan_id: str, req: RescheduleReq):
    plan = M.PLANS.get(plan_id)
    if not plan or not plan["slots"]:
        raise HTTPException(404, {"error": "VENUE_NOT_FOUND", "message": "方案不存在或无明细"})

    # 把 mock dict 转成 Slot；当前及之前的标记 completed
    slots, passed = [], True
    for s in plan["slots"]:
        slot = core.Slot(time=s["time"], venue=s["venue"], kind=s["kind"],
                         duration=s["duration"], walk=s["walk"], price=s["price"])
        if passed:
            slot.status = "completed"
        if s["venue"] == req.current_venue:
            passed = False  # 之后的都是 pending
        slots.append(slot)

    # 优先：调用 smart-itinerary skill 做增量纠错；失败回退 core
    import skill_bridge
    slot_dicts = [{"venue": s.venue, "kind": s.kind, "duration": s.duration,
                   "walk": s.walk} for s in slots]
    sk = skill_bridge.itinerary_reschedule_overtime(
        slot_dicts, req.current_venue, req.delay_minutes, plan["buffer_minutes"])
    if sk is not None:
        return sk
    result = core.reschedule(slots, req.delay_minutes, plan["buffer_minutes"])
    return result


# ════════════════════════════════════════════════════════════════
# 接口 9 · 行程结束反馈  POST /api/v1/feedback
# ════════════════════════════════════════════════════════════════
class FeedbackReq(BaseModel):
    session_id: str = "demo"
    plan_id: str = "comfort"
    satisfaction: str = "happy"
    improvement: str | None = None  # e.g. more_photo_spots

@app.post("/api/v1/feedback")
def feedback(req: FeedbackReq):
    vec = get_vector(req.session_id)
    if req.improvement:
        vec, updates = core.apply_feedback(vec, req.improvement)
        SESSIONS[req.session_id] = vec
    else:
        updates = []
    return {
        "message": "感谢反馈！你的偏好已更新。",
        "preference_updates": [
            {**u, "reason": "根据你这次的反馈调整"} for u in updates
        ],
    }


# ════════════════════════════════════════════════════════════════
# 接口 10 · 偏好画像  GET /api/v1/preferences/profile
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/preferences/profile")
def profile(session_id: str = "demo"):
    vec = get_vector(session_id)
    return {
        "dimensions": core.vector_to_radar(vec),
        "summary": "你喜欢轻松约会、在意氛围和拍照、不想排队、预算适中，倾向让系统帮你做决定。",
        "session_count": 1,
    }


@app.get("/")
def root():
    return {"service": "觅 MIVI Backend", "endpoints": 10, "docs": "/docs"}


# ════════════════════════════════════════════════════════════════
# 接口 11 · 多方式路径规划  GET /api/v1/route
# 按距离自动选步行/公交/驾车，并用偏好向量(体力/预算)微调
# ════════════════════════════════════════════════════════════════
@app.get("/api/v1/route")
def route(origin: str, dest: str, city: str = "苏州", session_id: str = "demo"):
    """origin/dest 为 '经度,纬度'。真接口不可用时返回 Mock 步行估计。"""
    vec = get_vector(session_id)
    return amap_client.pick_transport(origin, dest, city, vec)


# ════════════════════════════════════════════════════════════════
# 接口 12 · 授权位置就近搜索  POST /api/v1/venues/nearby
# 用户显式点了「用我的大致位置」才会调到这；坐标用完即焚，绝不落盘
# ════════════════════════════════════════════════════════════════
class NearbyReq(BaseModel):
    lat: float
    lng: float
    keyword: str = "美食"
    city: str = "苏州"
    # location_source 仅用于审计展示，不存储：user_input / user_authorized / default
    location_source: str = "user_authorized"

@app.post("/api/v1/venues/nearby")
def nearby(req: NearbyReq):
    coord = f"{req.lng},{req.lat}"          # 高德是 经度,纬度
    # 先用逆地理编码把坐标转成城市名（坐标用完即焚，不存储）
    city = None
    if config.amap_available():
        city = amap_client.reverse_geocode_city(req.lng, req.lat)
    search_city = city or req.city
    pois = amap_client.place_text(req.keyword, search_city, location=coord)  # 按真实坐标就近搜
    # ↑ coord/city 仅作为本次请求的局部变量，函数结束即销毁。绝不写入 SESSIONS / 文件 / 日志。
    if pois is None:
        # Mock 兜底
        pois = [{"name": n, "address": M.VENUES[n]["address"]} for n in list(M.VENUES)[:3]]
    return {
        "results": pois,
        "city": city,                       # 返回真实城市，供前端出方案用（不存储）
        "location_source": req.location_source,
        "privacy_note": "坐标仅用于本次搜索，用完即焚，未存储、未与身份关联。",
    }


# ════════════════════════════════════════════════════════════════
# 事中陪伴（in-trip）接口 —— 真实逻辑 + Mock 回退，匿名内存态不落库
# 进度/调整/提醒都按 session_id + trip_id 暂存于内存 TRIPS，结束即可丢弃。
# ════════════════════════════════════════════════════════════════
TRIPS: dict[str, dict] = {}   # key = trip_id；值含 slots / current / reminder_rules（匿名，内存）

def _trip(trip_id: str) -> dict:
    return TRIPS.setdefault(trip_id, {
        "slots": [dict(s) for s in M.PLANS["comfort"]["slots"]],
        "current": M.PLANS["comfort"]["slots"][0]["venue"],
        "reminder_rules": [],
    })


# ── 接口 11 · 进度推进：上报/查询当前进行到哪站 ──
class ProgressReq(BaseModel):
    trip_id: str = "demo-trip"
    current_venue: str | None = None   # 不传则只查询

@app.post("/api/v1/trips/{trip_id}/progress")
def trip_progress(trip_id: str, req: ProgressReq):
    t = _trip(trip_id)
    if req.current_venue:
        t["current"] = req.current_venue
    names = [s["venue"] for s in t["slots"]]
    idx = names.index(t["current"]) if t["current"] in names else 0
    return {
        "trip_id": trip_id,
        "current_venue": t["current"],
        "current_index": idx,
        "completed": names[:idx],
        "upcoming": names[idx + 1:],
        "slots": t["slots"],
    }


# ── 接口 12 · 事中调整：跳过/加站/改时间/延长，复用 core 重排 ──
class AdjustReq(BaseModel):
    trip_id: str = "demo-trip"
    action: str                      # skip | add | move | extend
    target: str | None = None
    new_time: str | None = None
    add_slot: dict | None = None     # {time,venue,kind,duration,price}
    extra_minutes: int = 0

@app.post("/api/v1/trips/{trip_id}/adjust")
def trip_adjust(trip_id: str, req: AdjustReq):
    t = _trip(trip_id)
    result = core.apply_adjust(
        t["slots"], req.action, target=req.target, new_time=req.new_time,
        add_slot=req.add_slot, extra_minutes=req.extra_minutes,
    )
    t["slots"] = result["slots"]
    return {
        "trip_id": trip_id,
        "changes": result["changes"],
        "slots": result["slots"],
        "end_time": result["end_time"],
        "budget": result["budget"],
        "fox_note": "好嘞，按你改的重新顺了一遍，路上时间也算进去啦～",
    }


# ── 接口 13 · 提醒规则：用户自定义"到点/还有多久叫我"（被动兜底）──
class ReminderRuleReq(BaseModel):
    trip_id: str = "demo-trip"
    kind: str = "before_leave"       # before_leave | at_time
    minutes_before: int | None = None
    at_time: str | None = None

@app.post("/api/v1/trips/{trip_id}/reminders")
def set_reminder(trip_id: str, req: ReminderRuleReq):
    t = _trip(trip_id)
    rule = {"kind": req.kind, "minutes_before": req.minutes_before, "at_time": req.at_time}
    t["reminder_rules"].append(rule)
    return {"trip_id": trip_id, "rules": t["reminder_rules"],
            "fox_note": "记下啦，到点我准时喊你，安心玩～"}


# ── 接口 14 · 主动提醒判断：轮询该不该提醒（时间/天气/排队/太晚）──
# 这是"主动提醒"的真实数据源：天气取高德，排队可接高德实时/估算。
@app.get("/api/v1/trips/{trip_id}/check-reminders")
def check_reminders(trip_id: str, now: str = "16:50", city_adcode: str = "320500"):
    t = _trip(trip_id)
    # 天气：真实走高德，否则 Mock
    wx = amap_client.weather(city_adcode) if config.amap_available() else {"weather": "多云", "temperature": "27"}
    # 排队：演示用估算（真实可接高德热度/商家接口）
    queue = {"晴川日料": 40}
    reminders = core.check_reminders(
        t["slots"], t["current"], core._to_min(now),
        weather=wx, queue_minutes=queue,
    )
    return {"trip_id": trip_id, "now": now, "weather": wx, "reminders": reminders}
