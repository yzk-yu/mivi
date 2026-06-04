#!/usr/bin/env python3
"""
smart-itinerary skill · 增量纠错实现脚本
------------------------------------------------------------------
OpenClaw 的 Skill 通过 {baseDir}/scripts/reschedule.py 调用此脚本。
自包含、无外部依赖，可直接在沙箱/主机跑。

用法：
  python reschedule.py --current "苏州博物馆西馆" --delay 45 \
      --slots '[{"venue":"白岛咖啡","kind":"cafe","duration":60,"walk":0},
                {"venue":"苏州博物馆西馆","kind":"scenic","duration":90,"walk":12},
                {"venue":"晴川日料","kind":"dining","duration":90,"walk":10},
                {"venue":"平江路夜景","kind":"walk","duration":30,"walk":5}]' \
      --buffer 40

输出：一段 JSON，包含 strategy / changes / impact_summary，供 Agent 转成觅狐口吻。
"""
import argparse, json, sys

PRIORITY = {"dining": 100, "scenic": 70, "entertainment": 60, "cafe": 40, "walk": 20, "transit": 10}


def reschedule(slots, current, delay, buffer):
    # 当前点及之前 = 已完成(locked)，之后 = 待重排
    passed, locked, affected = True, [], []
    for s in slots:
        if passed:
            locked.append(s)
        else:
            affected.append(s)
        if s["venue"] == current:
            passed = False

    buffer_left = buffer - delay
    changes = [{"venue": s["venue"], "change": "marked_completed", "note": "已完成，锁定不动"} for s in locked]

    if buffer_left >= 0:
        strategy = "absorb_buffer"
        summary = f"缓冲池还够（剩 {buffer_left} 分钟），后续不用调整，放心继续。"
    elif abs(buffer_left) <= 40:
        strategy = "compress_non_core"
        need = abs(buffer_left)
        for s in sorted(affected, key=lambda x: PRIORITY.get(x["kind"], 50)):
            if need <= 0:
                break
            cut = min(need, max(0, s["duration"] - 15))
            if cut > 0:
                changes.append({"venue": s["venue"], "change": "duration_compressed",
                                "old_duration": s["duration"], "new_duration": s["duration"] - cut,
                                "note": f"停留 {s['duration']}→{s['duration']-cut} 分钟，路线不变"})
                need -= cut
        summary = "压缩了非核心活动的停留时间，用餐和主要景点完全保留。"
    else:
        strategy = "skip_lowest_priority"
        need = abs(buffer_left)
        for s in sorted(affected, key=lambda x: PRIORITY.get(x["kind"], 50)):
            if need <= 0 or PRIORITY.get(s["kind"], 50) >= PRIORITY["dining"]:
                continue
            changes.append({"venue": s["venue"], "change": "cancelled",
                            "note": f"延误较多，建议跳过『{s['venue']}』，保住后面的核心安排"})
            need -= s["duration"] + s.get("walk", 0)
        summary = "延误比较多，跳过了优先级最低的活动，核心体验（用餐）保住了。"

    return {"strategy": strategy, "delay_minutes": delay, "buffer_remaining": buffer_left,
            "changes": changes, "impact_summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True, help="当前所在地点")
    ap.add_argument("--delay", type=int, required=True, help="延误分钟数")
    ap.add_argument("--slots", required=True, help="行程 slots 的 JSON 数组")
    ap.add_argument("--buffer", type=int, default=40, help="总缓冲分钟")
    args = ap.parse_args()
    try:
        slots = json.loads(args.slots)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"slots JSON 解析失败: {e}"}, ensure_ascii=False)); sys.exit(1)
    print(json.dumps(reschedule(slots, args.current, args.delay, args.buffer), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
