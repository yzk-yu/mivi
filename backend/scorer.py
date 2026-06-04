"""
偏好匹配打分器 —— 显式、可解释的匹配算法。

在高德搜到真实候选后、交给 DeepSeek 编排前，
用本模块给每个候选店算一个「匹配分」(0-100) + 命中的匹配理由标签。

8 维用户画像 (preference_vector，取值 0-1)：
  pace          节奏     —— 高=想多去几个地方/紧凑
  budget        预算敏感  —— 高=越在意花钱、偏好便宜
  energy        体力     —— 高=愿意多走/多安排
  aesthetic     审美/拍照 —— 高=在意环境好看、适合拍照
  adventure     探索     —— 高=想试新鲜/小众
  patience      耐心     —— 高=愿意排队/慢慢玩
  social        社交     —— 高=约会/结伴，偏好氛围好
  decision_load 决策负担  —— 高=希望少纠结、给确定推荐

打分是「软约束加权」：每一维对不同类型的店产生加/减分，
最终归一到 0-100。匹配理由用人话标签，方便在 UI / 详情页展示。
"""
from __future__ import annotations


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def score_candidate(poi: dict, prefs: dict, kind: str, budget_total: float) -> dict:
    """给单个候选店打分。返回 {score: 0-100, reasons: [str], breakdown: {...}}。"""
    p = prefs or {}
    pace = _f(p.get("pace"), 0.5)
    budget_sens = _f(p.get("budget"), 0.5)
    energy = _f(p.get("energy"), 0.6)
    aesthetic = _f(p.get("aesthetic"), 0.3)
    adventure = _f(p.get("adventure"), 0.4)
    patience = _f(p.get("patience"), 0.4)
    social = _f(p.get("social"), 0.5)

    rating = _f(poi.get("rating"), 0.0)         # 0-5
    cost = _f(poi.get("cost"), 0.0)             # 人均
    type_str = (poi.get("type") or "") + (poi.get("name") or "")

    score = 50.0          # 基准分
    reasons: list[str] = []
    bd: dict = {}

    # ① 评分基线：好店人人爱，评分越高越加分（最高 +18）
    if rating > 0:
        delta = (rating - 4.0) * 12        # 4.5★→+6, 4.8★→+9.6, 5★→+12
        delta = max(-10, min(18, delta))
        score += delta
        bd["rating"] = round(delta, 1)
        if rating >= 4.6:
            reasons.append(f"高分好店 {rating}★")

    # ② 预算匹配：人均贴近「单店合理预算」加分，超太多则按预算敏感度扣分
    if cost > 0 and budget_total > 0:
        per_stop_budget = budget_total / 3.0     # 粗略：一天约 3 个花钱点
        ratio = cost / per_stop_budget
        if ratio <= 1.0:
            delta = 8 * (1 - budget_sens * 0.3)  # 便宜，预算敏感的人更买账
            reasons.append("人均在预算内")
        elif ratio <= 1.5:
            delta = -4 * budget_sens
        else:
            delta = -12 * budget_sens            # 太贵，越在意预算扣越多
            if budget_sens > 0.5:
                reasons.append("略超预算（已据你的预算偏好降权）")
        score += delta
        bd["budget"] = round(delta, 1)

    # ③ 审美/拍照：aesthetic 高 → 景观、咖啡、有特色的店加分
    if aesthetic > 0.4:
        if kind in ("scenic", "cafe") or any(k in type_str for k in ["公园", "美术", "博物", "景区", "咖啡", "展"]):
            delta = 10 * aesthetic
            score += delta
            bd["aesthetic"] = round(delta, 1)
            reasons.append("环境出片、适合拍照")

    # ④ 社交/约会：social 高 → 餐厅、氛围类加分
    if social > 0.45:
        if kind in ("dining", "entertain") or any(k in type_str for k in ["餐", "酒", "茶", "咖啡"]):
            delta = 8 * social
            score += delta
            bd["social"] = round(delta, 1)
            reasons.append("氛围好、适合约会")

    # ⑤ 探索：adventure 高 → 小众/新鲜（这里用「非连锁」粗略代理：名字含特色词）
    if adventure > 0.5:
        if any(k in type_str for k in ["小馆", "私房", "创意", "独立", "手作", "本地", "老字号"]):
            delta = 6 * adventure
            score += delta
            bd["adventure"] = round(delta, 1)
            reasons.append("有点特色、值得一试")

    # ⑥ 耐心 / 节奏：耐心低 or 节奏快 → 偏好「轻量」店（咖啡/快），重型景点轻微降权
    if kind == "scenic" and (patience < 0.35 or pace > 0.65):
        delta = -4
        score += delta
        bd["pace"] = round(delta, 1)

    # ⑦ 体力：energy 低 → 强度高的（景区/娱乐）轻微降权
    if energy < 0.4 and kind in ("scenic", "entertain"):
        delta = -4
        score += delta
        bd["energy"] = round(delta, 1)

    score = max(0, min(100, round(score, 1)))
    return {"score": score, "reasons": reasons[:3], "breakdown": bd}


def rank_pois(pois_by_kind: dict, prefs: dict, budget_total: float) -> dict:
    """
    给所有候选店打分并按 kind 内降序排。
    优先调用 local-dining skill 打分；失败回退本地 score_candidate。
    返回 {kind: [ {…原字段…, match_score, match_reasons, match_breakdown}, ... ]}
    """
    import skill_bridge
    out: dict = {}
    for kind, items in pois_by_kind.items():
        if not items:
            out[kind] = []
            continue
        # 优先：调用 local-dining skill 打分排序
        ranked = skill_bridge.dining_rank(items, prefs, kind, int(budget_total), 2)
        if ranked is not None:
            out[kind] = ranked
            continue
        # 回退：本地打分
        scored = []
        for poi in items:
            res = score_candidate(poi, prefs, kind, budget_total)
            poi2 = dict(poi)
            poi2["match_score"] = res["score"]
            poi2["match_reasons"] = res["reasons"]
            poi2["match_breakdown"] = res["breakdown"]
            scored.append(poi2)
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        out[kind] = scored
    return out
