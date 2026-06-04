"""
Skill Bridge —— MIVI 后端 ↔ OpenClaw Skills 的调用桥。

MIVI 的核心能力由 OpenClaw skills 提供。后端各环节通过本模块调用对应 skill
的实现脚本(scripts/*.py，命令行接口，自包含)。

设计原则:
  1. 真实调用:用 subprocess 跑 skill 脚本，传 JSON 参数、收 JSON 结果——
     这是 MIVI "基于 OpenClaw skills 运行" 的真实链路。
  2. 失败回退:skill 调用异常/超时/返回非法时，返回 None，调用方回退到
     后端内置逻辑，保证线上稳定不崩。
  3. 可观测:每次调用打印日志，演示/答辩时能看到 skill 真的在被调用。

skills 目录布局(与 OpenClaw workspace 一致):
  skills/<skill-name>/scripts/<script>.py
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

# skills 目录:与 backend 同级的 ../skills
_BASE = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(_BASE, "..", "skills"))

# 允许用环境变量覆盖(部署时 skills 可能在 OpenClaw workspace)
SKILLS_DIR = os.environ.get("MIVI_SKILLS_DIR", SKILLS_DIR)

_TIMEOUT = 15   # 单个 skill 调用超时(秒)


def call_skill(skill: str, script: str, args: list[str], stdin_data: str | None = None) -> dict | None:
    """
    调用一个 skill 脚本。
      skill:  skill 目录名，如 "user-profiling"
      script: 脚本文件名，如 "profile.py"
      args:   命令行参数列表
      stdin_data: 可选，通过 stdin 传入(大 JSON 用，避免命令行过长)
    成功返回解析后的 dict；任何异常返回 None(调用方回退)。
    """
    path = os.path.join(SKILLS_DIR, skill, "scripts", script)
    if not os.path.exists(path):
        print(f"[skill] 脚本不存在，回退: {path}")
        return None
    try:
        cmd = [sys.executable, path, *args]
        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode != 0:
            print(f"[skill] {skill}/{script} 退出码 {result.returncode}，回退。stderr: {result.stderr[:200]}")
            return None
        out = json.loads(result.stdout)
        print(f"[skill] ✓ 调用 {skill}/{script} {' '.join(args[:2])} 成功")
        return out
    except subprocess.TimeoutExpired:
        print(f"[skill] {skill}/{script} 超时({_TIMEOUT}s)，回退")
        return None
    except (json.JSONDecodeError, Exception) as e:
        print(f"[skill] {skill}/{script} 异常({e})，回退")
        return None


# ─────────────────────────────────────────────
# 各 skill 的便捷封装(后端各环节调用这些)
# ─────────────────────────────────────────────

def profiling_extract(text: str, vector: dict) -> dict | None:
    """user-profiling skill:从一句话提取/更新 8 维偏好向量。"""
    out = call_skill("user-profiling", "profile.py",
                     ["extract", "--text", text, "--vector", json.dumps(vector, ensure_ascii=False)])
    return out.get("vector") if out else None


def dining_rank(candidates: list[dict], vector: dict, kind: str, budget: int, party: int) -> list[dict] | None:
    """local-dining skill:给某一类(kind)候选 POI 打分排序。"""
    out = call_skill("local-dining", "recommend.py",
                     ["--vector", json.dumps(vector, ensure_ascii=False),
                      "--candidates", json.dumps(candidates, ensure_ascii=False),
                      "--kind", kind, "--budget", str(budget), "--party", str(party)])
    return out.get("ranked") if out else None


def entertainment_weather_switch(weather: str, temp, activities: list[dict]) -> dict | None:
    """local-entertainment skill:天气自适应,判断户外活动是否换室内。
      weather: 天气描述字符串(如"小雨")；temp: 温度数字或 None；
      activities: [{name, outdoor:bool, alt:替代场所}]"""
    args = ["--weather", str(weather), "--activities", json.dumps(activities, ensure_ascii=False)]
    if temp is not None:
        args += ["--temp", str(int(temp))]
    out = call_skill("local-entertainment", "weather_switch.py", args)
    return out if out else None


def itinerary_reschedule_overtime(slots: list[dict], current_venue: str, delay: int, buffer: int) -> dict | None:
    """smart-itinerary skill:事中超时增量纠错(吸收缓冲/压缩/跳过)。"""
    out = call_skill("smart-itinerary", "reschedule.py",
                     ["--current", current_venue, "--delay", str(delay),
                      "--slots", json.dumps(slots, ensure_ascii=False),
                      "--buffer", str(buffer)])
    return out if out else None
