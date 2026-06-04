#!/usr/bin/env python3
"""
user-profiling skill · 8 维偏好向量实现脚本
------------------------------------------------------------------
OpenClaw 通过 {baseDir}/scripts/profile.py 调用。自包含、无外部依赖。
与后端 core.py 同一套算法（信号提取 / 衰减更新 / 反馈学习），保证前后端一致。

用法：
  # 从一句话提取偏好（衰减更新到已有向量）
  python profile.py extract --text "想轻松一点，别排队" [--vector '{"pace":0.5,...}']
  # 行程结束反馈更新
  python profile.py feedback --key more_photo_spots --vector '{...}'
  # 转雷达图
  python profile.py radar --vector '{...}'
"""
import argparse, json, sys

DIMENSIONS = ["pace", "budget", "energy", "aesthetic", "adventure", "patience", "social", "decision_load"]
LABELS = {"pace":"节奏","budget":"预算","energy":"体力","aesthetic":"颜值",
          "adventure":"探索","patience":"耐心","social":"社交","decision_load":"决策"}
DEFAULT = {"pace":0.5,"budget":0.5,"energy":0.6,"aesthetic":0.3,
           "adventure":0.4,"patience":0.4,"social":0.5,"decision_load":0.5}

SIGNAL_MAP = {
    "想轻松":{"pace":+0.3,"energy":-0.2}, "轻松":{"pace":+0.3,"energy":-0.2},
    "不想太贵":{"budget":+0.3}, "便宜":{"budget":+0.3}, "省钱":{"budget":+0.3},
    "拍照":{"aesthetic":+0.4}, "打卡":{"aesthetic":+0.3},
    "不想排队":{"patience":-0.3}, "不排队":{"patience":-0.3},
    "约会":{"social":+0.2,"aesthetic":+0.2}, "女朋友":{"social":+0.2,"aesthetic":+0.2},
    "随便":{"decision_load":-0.3}, "你帮我":{"decision_load":-0.3},
    "探索":{"adventure":+0.3}, "新地方":{"adventure":+0.3}, "新鲜":{"adventure":+0.2},
    "老地方":{"adventure":-0.3}, "累":{"energy":-0.3,"pace":+0.2}, "充实":{"pace":-0.2,"energy":+0.2},
}
FEEDBACK_MAP = {
    "too_rushed":{"pace":+0.2,"energy":-0.1}, "too_tired":{"energy":-0.2,"pace":+0.1},
    "too_expensive":{"budget":+0.2}, "more_relaxed":{"pace":+0.2},
    "more_packed":{"pace":-0.2,"energy":+0.2}, "more_budget":{"budget":+0.2},
    "more_photo_spots":{"aesthetic":+0.2}, "dislike_queue":{"patience":-0.2},
}

clamp = lambda x: max(0.0, min(1.0, round(x, 3)))


def extract(text, vector):
    v = dict(vector)
    for kw, deltas in SIGNAL_MAP.items():
        if kw in text:
            for dim, d in deltas.items():
                target = clamp(v[dim] + d)
                v[dim] = clamp(v[dim] * 0.3 + target * 0.7)   # 衰减更新
    return v


def feedback(key, vector):
    v = dict(vector); updates = []
    for dim, d in FEEDBACK_MAP.get(key, {}).items():
        old = v[dim]; v[dim] = clamp(old + d)
        updates.append({"dimension": dim, "old": old, "new": v[dim]})
    return v, updates


def radar(vector):
    def lab(x): return "很在意" if x>=0.7 else "比较在意" if x>=0.55 else "适中" if x>=0.4 else "不太在意"
    return [{"name":LABELS[k],"key":k,"value":vector[k],"label":lab(vector[k])} for k in DIMENSIONS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract","feedback","radar"])
    ap.add_argument("--text"); ap.add_argument("--key")
    ap.add_argument("--vector", default=json.dumps(DEFAULT))
    a = ap.parse_args()
    try:
        vec = json.loads(a.vector)
    except json.JSONDecodeError:
        vec = dict(DEFAULT)
    for k in DIMENSIONS:
        vec.setdefault(k, DEFAULT[k])

    if a.cmd == "extract":
        if not a.text: print(json.dumps({"error":"需要 --text"})); sys.exit(1)
        print(json.dumps({"vector": extract(a.text, vec)}, ensure_ascii=False, indent=2))
    elif a.cmd == "feedback":
        v, u = feedback(a.key or "", vec)
        print(json.dumps({"vector": v, "updates": u}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"dimensions": radar(vec)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
