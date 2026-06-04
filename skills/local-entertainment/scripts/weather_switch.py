#!/usr/bin/env python3
"""
local-entertainment skill · 天气自适应切换实现脚本
------------------------------------------------------------------
OpenClaw 通过 {baseDir}/scripts/weather_switch.py 调用。
输入实时天气 + 计划中的活动，判断是否需要把户外活动换成室内替代。

用法：
  python weather_switch.py --weather "小雨" --temp 18 \
      --activities '[{"name":"平江路夜景散步","outdoor":true,"alt":"诚品书店"},
                     {"name":"白岛咖啡","outdoor":false}]'
"""
import argparse, json, sys


def decide(weather, temp, activities):
    rain = any(k in weather for k in ["雨", "雪", "雷"])
    hot = temp is not None and temp >= 35
    windy = "大风" in weather or "风" in weather and temp is not None and temp <= 5
    decisions = []
    for a in activities:
        rec = {"name": a["name"], "action": "keep", "reason": "天气合适，照常"}
        if a.get("outdoor"):
            if rain:
                rec = {"name": a["name"], "action": "switch",
                       "to": a.get("alt"), "reason": f"{weather}，户外体验打折，建议换室内"}
            elif hot:
                rec = {"name": a["name"], "action": "switch",
                       "to": a.get("alt"), "reason": f"{temp}°C 太晒，建议换有空调的室内场所"}
            elif windy:
                rec = {"name": a["name"], "action": "switch",
                       "to": a.get("alt"), "reason": "大风/低温，避免开放式场地"}
        decisions.append(rec)
    return {
        "weather": weather, "temp": temp,
        "summary": ("有户外活动受天气影响，已给出室内替代" if any(d["action"] == "switch" for d in decisions)
                    else "天气合适，户外活动可照常进行"),
        "decisions": decisions,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--temp", type=int, default=None)
    ap.add_argument("--activities", required=True)
    a = ap.parse_args()
    try:
        acts = json.loads(a.activities)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False)); sys.exit(1)
    print(json.dumps(decide(a.weather, a.temp, acts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
