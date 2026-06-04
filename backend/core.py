"""
觅 MIVI · 核心算法层
------------------------------------------------------------------
这里放两个"技术亮点"里真正可落地、纯确定性的算法：

  1. 增量纠错 (reschedule)   —— slot 状态机 + 按延误分级的最小化重排
  2. 8 维偏好向量 (profiling) —— 信号提取 / 衰减更新 / 反馈学习

之所以单独拆成一个模块：
  - 后端 FastAPI 直接 import 它
  - OpenClaw 的 skill 脚本 (skills/*/scripts/) 也 import 它
  两边共用同一份逻辑，演示时"前端→接口→算法"是同一条真链路。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

# ────────────────────────────────────────────────────────────────
# 1. 增量纠错：slot 状态机
# ────────────────────────────────────────────────────────────────

SlotStatus = Literal["pending", "active", "completed", "overrun", "replaced", "cancelled"]

# 活动优先级：数值越大越"核心"，重排时最后才被牺牲
PRIORITY = {
    "dining": 100,      # 用餐 = 核心体验，最后才动
    "scenic": 70,       # 主要景点
    "entertainment": 60,
    "cafe": 40,
    "walk": 20,         # 散步 = 最先被压缩/跳过
    "transit": 10,
}


@dataclass
class Slot:
    time: str           # "HH:MM"
    venue: str
    kind: str           # dining / scenic / cafe / walk ...
    duration: int       # 计划停留分钟
    walk: int = 0       # 到达此点的步行分钟
    price: int = 0
    status: SlotStatus = "pending"
    alt_venues: list[str] = field(default_factory=list)

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.kind, 50)


def reschedule(slots: list[Slot], delay_minutes: int, total_buffer: int) -> dict:
    """
    增量纠错核心：只动未开始的 slot，已完成的 locked 不碰。
    按延误程度分四档，对应产品文档里的策略表。
    """
    locked = [s for s in slots if s.status in ("completed", "active")]
    affected = [s for s in slots if s.status == "pending"]
    buffer_left = total_buffer - delay_minutes

    changes: list[dict] = []

    # 已完成的标记锁定（不参与重排）
    for s in locked:
        if s.status == "completed":
            changes.append({"venue": s.venue, "change": "marked_completed", "note": "已完成，锁定不动"})

    if buffer_left >= 0:
        strategy = "absorb_buffer"
        summary = f"缓冲池还够（剩 {buffer_left} 分钟），后续不用调整，放心继续。"

    elif abs(buffer_left) <= 40:
        strategy = "compress_non_core"
        need = abs(buffer_left)
        # 从优先级最低的未开始活动里压缩停留时间
        for s in sorted(affected, key=lambda x: x.priority):
            if need <= 0:
                break
            cut = min(need, max(0, s.duration - 15))  # 最多压到剩 15 分钟
            if cut > 0:
                changes.append({
                    "venue": s.venue, "change": "duration_compressed",
                    "old_duration": s.duration, "new_duration": s.duration - cut,
                    "note": f"停留从 {s.duration} 分钟压到 {s.duration - cut} 分钟，路线不变",
                })
                need -= cut
        summary = "压缩了几个非核心活动的停留时间，用餐和主要景点完全保留。"

    else:
        strategy = "skip_lowest_priority"
        need = abs(buffer_left)
        for s in sorted(affected, key=lambda x: x.priority):
            if need <= 0:
                break
            if s.priority >= PRIORITY["dining"]:  # 核心活动绝不跳过
                continue
            s.status = "cancelled"
            need -= s.duration + s.walk
            changes.append({
                "venue": s.venue, "change": "cancelled",
                "note": f"延误较多，建议跳过『{s.venue}』，优先保住后面的核心安排",
            })
        summary = "延误比较多，跳过了优先级最低的活动，核心体验（用餐）保住了。"

    return {
        "strategy": strategy,
        "delay_minutes": delay_minutes,
        "buffer_remaining": buffer_left,
        "changes": changes,
        "impact_summary": summary,
    }


# ────────────────────────────────────────────────────────────────
# 2. 8 维偏好向量
# ────────────────────────────────────────────────────────────────

DIMENSIONS = ["pace", "budget", "energy", "aesthetic", "adventure", "patience", "social", "decision_load"]
DIM_LABELS = {
    "pace": "节奏", "budget": "预算", "energy": "体力", "aesthetic": "颜值",
    "adventure": "探索", "patience": "耐心", "social": "社交", "decision_load": "决策",
}
DEFAULT_VECTOR = {
    "pace": 0.5, "budget": 0.5, "energy": 0.6, "aesthetic": 0.3,
    "adventure": 0.4, "patience": 0.4, "social": 0.5, "decision_load": 0.5,
}

# 自然语言信号 → 向量增量（产品文档信号映射表的代码化）
SIGNAL_MAP: dict[str, dict[str, float]] = {
    "想轻松": {"pace": +0.3, "energy": -0.2},
    "轻松": {"pace": +0.3, "energy": -0.2},
    "不想太贵": {"budget": +0.3},
    "便宜": {"budget": +0.3},
    "省钱": {"budget": +0.3},
    "拍照": {"aesthetic": +0.4},
    "打卡": {"aesthetic": +0.3},
    "不想排队": {"patience": -0.3},
    "不排队": {"patience": -0.3},
    "约会": {"social": +0.2, "aesthetic": +0.2},
    "女朋友": {"social": +0.2, "aesthetic": +0.2},
    "随便": {"decision_load": -0.3},
    "你帮我": {"decision_load": -0.3},
    "探索": {"adventure": +0.3},
    "新地方": {"adventure": +0.3},
    "新鲜": {"adventure": +0.2},
    "老地方": {"adventure": -0.3},
    "累": {"energy": -0.3, "pace": +0.2},
    "充实": {"pace": -0.2, "energy": +0.2},
}

# 反馈选项 → 向量调整
FEEDBACK_MAP: dict[str, dict[str, float]] = {
    "too_rushed": {"pace": +0.2, "energy": -0.1},
    "too_tired": {"energy": -0.2, "pace": +0.1},
    "too_expensive": {"budget": +0.2},
    "more_relaxed": {"pace": +0.2},
    "more_packed": {"pace": -0.2, "energy": +0.2},
    "more_budget": {"budget": +0.2},
    "more_photo_spots": {"aesthetic": +0.2},
    "dislike_queue": {"patience": -0.2},
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, round(x, 3)))


def extract_signals(text: str, vector: dict[str, float] | None = None) -> dict[str, float]:
    """从一句话里提取偏好信号，用衰减公式更新向量：新 = 旧×0.3 + 提取×0.7"""
    v = dict(vector or DEFAULT_VECTOR)
    for keyword, deltas in SIGNAL_MAP.items():
        if keyword in text:
            for dim, d in deltas.items():
                target = _clamp(v[dim] + d)               # 本次"目标值"
                v[dim] = _clamp(v[dim] * 0.3 + target * 0.7)  # 衰减更新
    return v


def apply_feedback(vector: dict[str, float], feedback_key: str) -> tuple[dict[str, float], list[dict]]:
    """行程结束反馈 → 更新向量，并返回可解释的变更记录"""
    v = dict(vector)
    updates = []
    for dim, d in FEEDBACK_MAP.get(feedback_key, {}).items():
        old = v[dim]
        v[dim] = _clamp(old + d)
        updates.append({"dimension": dim, "old": old, "new": v[dim]})
    return v, updates


def vector_to_radar(vector: dict[str, float]) -> list[dict]:
    """转成前端雷达图要的 8 维结构"""
    def label(val: float) -> str:
        if val >= 0.7: return "很在意"
        if val >= 0.55: return "比较在意"
        if val >= 0.4: return "适中"
        return "不太在意"
    return [
        {"name": DIM_LABELS[k], "key": k, "value": vector[k], "label": label(vector[k])}
        for k in DIMENSIONS
    ]


# ════════════════════════════════════════════════════════════════
# 事中陪伴（in-trip）：进度推进 + 主动提醒判断 + 事中调整
# 全部纯函数，便于被 main.py 接口与单测复用。
# ════════════════════════════════════════════════════════════════

def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)

def _to_hhmm(total: int) -> str:
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def retime_chain(slots: list[dict], walk_default: int = 10) -> list[dict]:
    """
    把一串 slot 从第一站的开始时间起，按 开始→停留→路上 顺推重排时间。
    这是"按计划往后顺"的统一实现，事中加站/跳过/改时间后都调用它。
    slots: [{time,venue,duration,price,kind,walk?}, ...]（已是最终保留+排序的列表）
    """
    if not slots:
        return slots
    cur = _to_min(slots[0]["time"])
    for i, s in enumerate(slots):
        s["time"] = _to_hhmm(cur)
        walk = s.get("walk", walk_default) if i < len(slots) - 1 else 0
        cur += s["duration"] + walk
    return slots


def trip_end_minute(slots: list[dict], walk_default: int = 10) -> int:
    """整天结束时间（分钟）= 最后一站开始 + 其停留。用于'太晚'判断。"""
    if not slots:
        return 0
    retime_chain(slots, walk_default)
    last = slots[-1]
    return _to_min(last["time"]) + last["duration"]


def check_reminders(slots: list[dict],
                    current_venue: str,
                    now_minute: int,
                    weather: dict | None = None,
                    queue_minutes: dict | None = None,
                    late_threshold: int = 22 * 60) -> list[dict]:
    """
    主动提醒判断（管家的"主动盯着"）。返回该触发的提醒列表，每条带建议动作。
    输入都是真实可得的数据：当前时间、天气（高德）、各店实时排队（高德/估算）。
    纯判断、无副作用，便于后端轮询或事件驱动调用。
    """
    out: list[dict] = []
    names = [s["venue"] for s in slots]
    idx = names.index(current_venue) if current_venue in names else -1

    # 1) 时间提醒：当前站预计结束时间已过 → 该走了
    if idx >= 0:
        cur = slots[idx]
        end = _to_min(cur["time"]) + cur["duration"]
        if now_minute >= end and idx < len(slots) - 1:
            nxt = slots[idx + 1]
            out.append({
                "type": "time",
                "venue": cur["venue"],
                "message": f"{cur['venue']}逛得差不多啦，再不走下一站可能要赶咯",
                "suggest": {"action": "reschedule", "next": nxt["venue"]},
            })

    # 2) 天气提醒：下雨 且 后面有露天项目 → 建议换室内
    if weather and str(weather.get("weather", "")).find("雨") >= 0:
        outdoor = [s for s in slots[idx + 1:] if s.get("kind") in ("walk", "scenic")]
        if outdoor:
            out.append({
                "type": "weather",
                "venue": outdoor[0]["venue"],
                "message": f"外面下雨了，你后面的「{outdoor[0]['venue']}」是露天的，要不要换成室内的？",
                "suggest": {"action": "swap_indoor", "target": outdoor[0]["venue"]},
            })

    # 3) 排队提醒：某未到店实时排队超阈值 → 建议换备选
    if queue_minutes:
        for s in slots[max(idx, 0):]:
            q = queue_minutes.get(s["venue"])
            if q and q >= 30:
                out.append({
                    "type": "queue",
                    "venue": s["venue"],
                    "message": f"{s['venue']}现在排队约 {q} 分钟，比预计久，要不要换家不用等的？",
                    "suggest": {"action": "swap_alternative", "target": s["venue"]},
                })
                break

    # 4) 太晚提醒：整体结束时间过晚
    end_min = trip_end_minute([dict(s) for s in slots])
    if end_min > late_threshold:
        out.append({
            "type": "late",
            "venue": None,
            "message": f"这样排下来要到 {_to_hhmm(end_min)} 才结束，有点赶哦，要我帮你紧凑一下吗？",
            "suggest": {"action": "compact"},
        })

    return out


def apply_adjust(slots: list[dict], action: str, target: str | None = None,
                 new_time: str | None = None, add_slot: dict | None = None,
                 extra_minutes: int = 0, walk_default: int = 10) -> dict:
    """
    事中调整的统一入口。支持：
      - skip      跳过 target 站
      - add       新增一站（add_slot，插到 dining 之前或末尾）
      - move      改 target 站开始时间为 new_time
      - extend    target 站延长 extra_minutes
    调整后统一 retime_chain 重排，返回 {slots, changes, end_time}。
    """
    changes: list[dict] = []

    if action == "skip" and target:
        slots = [s for s in slots if s["venue"] != target]
        changes.append({"venue": target, "note": "已跳过"})

    elif action == "add" and add_slot:
        dine_i = next((i for i, s in enumerate(slots) if s.get("kind") == "dining"), len(slots))
        slots.insert(dine_i, add_slot)
        changes.append({"venue": add_slot["venue"], "note": "已加入行程"})

    elif action == "move" and target and new_time:
        for s in slots:
            if s["venue"] == target:
                s["time"] = new_time
                changes.append({"venue": target, "note": f"开始时间改为 {new_time}"})
                break

    elif action == "extend" and target:
        for s in slots:
            if s["venue"] == target:
                s["duration"] += extra_minutes
                changes.append({"venue": target, "note": f"停留延长 {extra_minutes} 分钟"})
                break

    retime_chain(slots, walk_default)
    return {
        "slots": slots,
        "changes": changes,
        "end_time": _to_hhmm(trip_end_minute([dict(s) for s in slots], walk_default)),
        "budget": sum(s.get("price", 0) for s in slots),
    }
