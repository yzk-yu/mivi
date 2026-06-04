#!/usr/bin/env python3
"""
local-dining skill · 餐厅/POI 偏好打分实现脚本
------------------------------------------------------------------
OpenClaw 通过 {baseDir}/scripts/recommend.py 调用。
MIVI 后端出方案时，对真实高德 POI 候选调用本脚本打分排序。

输入：8 维偏好向量 + 候选 POI(后端高德搜来的真实字段:name/type/rating/cost)
输出：带匹配分(0-100) + 可解释理由 的排序结果

打分算法与后端 scorer.py 严格一致(基准 50 分制)，保证 skill 调用与后端回退结果相同。

用法：
  python recommend.py --vector '{"budget":0.6,...}' \
      --candidates '[{"name":"晴川日料","type":"餐饮;日本料理","rating":4.7,"cost":130}]' \
      --kind dining --budget 500 --party 2
"""
import argparse, json, sys


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def score_candidate(poi, prefs, kind, budget_total):
    """与后端 scorer.score_candidate 完全一致的打分。返回 (score, reasons, breakdown)。"""
    p = prefs or {}
    pace = _f(p.get("pace"), 0.5)
    budget_sens = _f(p.get("budget"), 0.5)
    energy = _f(p.get("energy"), 0.6)
    aesthetic = _f(p.get("aesthetic"), 0.3)
    adventure = _f(p.get("adventure"), 0.4)
    patience = _f(p.get("patience"), 0.4)
    social = _f(p.get("social"), 0.5)

    rating = _f(poi.get("rating"), 0.0)
    cost = _f(poi.get("cost"), 0.0)
    type_str = (poi.get("type") or "") + (poi.get("name") or "")

    score = 50.0
    reasons, bd = [], {}

    if rating > 0:
        delta = max(-10, min(18, (rating - 4.0) * 12))
        score += delta
        bd["rating"] = round(delta, 1)
        if rating >= 4.6:
            reasons.append(f"高分好店 {rating}\u2605")

    if cost > 0 and budget_total > 0:
        per_stop = budget_total / 3.0
        ratio = cost / per_stop
        if ratio <= 1.0:
            delta = 8 * (1 - budget_sens * 0.3)
            reasons.append("\u4eba\u5747\u5728\u9884\u7b97\u5185")
        elif ratio <= 1.5:
            delta = -4 * budget_sens
        else:
            delta = -12 * budget_sens
            if budget_sens > 0.5:
                reasons.append("\u7565\u8d85\u9884\u7b97\uff08\u5df2\u636e\u4f60\u7684\u9884\u7b97\u504f\u597d\u964d\u6743\uff09")
        score += delta
        bd["budget"] = round(delta, 1)

    if aesthetic > 0.4:
        if kind in ("scenic", "cafe") or any(k in type_str for k in ["\u516c\u56ed", "\u7f8e\u672f", "\u535a\u7269", "\u666f\u533a", "\u5496\u5561", "\u5c55"]):
            delta = 10 * aesthetic
            score += delta; bd["aesthetic"] = round(delta, 1)
            reasons.append("\u73af\u5883\u51fa\u7247\u3001\u9002\u5408\u62cd\u7167")

    if social > 0.45:
        if kind in ("dining", "entertain") or any(k in type_str for k in ["\u9910", "\u9152", "\u8336", "\u5496\u5561"]):
            delta = 8 * social
            score += delta; bd["social"] = round(delta, 1)
            reasons.append("\u6c1b\u56f4\u597d\u3001\u9002\u5408\u7ea6\u4f1a")

    if adventure > 0.5:
        if any(k in type_str for k in ["\u5c0f\u9986", "\u79c1\u623f", "\u521b\u610f", "\u72ec\u7acb", "\u624b\u4f5c", "\u672c\u5730", "\u8001\u5b57\u53f7"]):
            delta = 6 * adventure
            score += delta; bd["adventure"] = round(delta, 1)
            reasons.append("\u6709\u70b9\u7279\u8272\u3001\u503c\u5f97\u4e00\u8bd5")

    if kind == "scenic" and (patience < 0.35 or pace > 0.65):
        score -= 4; bd["pace"] = -4

    if energy < 0.4 and kind in ("scenic", "entertain"):
        score -= 4; bd["energy"] = -4

    score = max(0, min(100, round(score, 1)))
    return score, reasons[:3], bd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--kind", default="dining")
    ap.add_argument("--budget", type=int, default=500)
    ap.add_argument("--party", type=int, default=2)
    a = ap.parse_args()
    try:
        v = json.loads(a.vector); cands = json.loads(a.candidates)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON parse fail: {e}"}, ensure_ascii=False)); sys.exit(1)

    ranked = []
    for poi in cands:
        sc, reasons, bd = score_candidate(poi, v, a.kind, float(a.budget))
        ranked.append({**poi, "match_score": sc, "match_reasons": reasons, "match_breakdown": bd})
    ranked.sort(key=lambda x: x["match_score"], reverse=True)

    print(json.dumps({"ranked": ranked}, ensure_ascii=False))


if __name__ == "__main__":
    main()
