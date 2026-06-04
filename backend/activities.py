"""
活动优先级表 —— must_have 提取的唯一数据源。

加新活动类型只需在 ACTIVITIES 里加一行，提取/搜索/排序全自动生效。

字段：
  key       唯一标识
  triggers  触发关键词（命中任一即识别为该活动）
  search    高德搜索词
  strength  强度（3=强/核心目的，2=中，1=弱/顺带）—— 多个命中时按此降序
  icon      展示图标
  label     展示名
"""
from __future__ import annotations

ACTIVITIES = [
    {"key": "cinema",   "triggers": ["看电影", "电影院", "影院", "电影"], "search": "电影院",        "strength": 3, "icon": "🎬", "label": "电影院"},
    {"key": "ktv",      "triggers": ["唱歌", "唱k", "唱K", "ktv", "KTV", "K歌"], "search": "KTV",     "strength": 3, "icon": "🎤", "label": "KTV"},
    {"key": "escape",   "triggers": ["密室", "密室逃脱"],                  "search": "密室逃脱",      "strength": 3, "icon": "🔓", "label": "密室逃脱"},
    {"key": "scriptkill","triggers": ["剧本杀"],                          "search": "剧本杀",        "strength": 3, "icon": "🎭", "label": "剧本杀"},
    {"key": "exhibit",  "triggers": ["看展", "展览", "美术馆", "艺术展"],  "search": "展览 美术馆",   "strength": 2, "icon": "🖼️", "label": "展览"},
    {"key": "bar",      "triggers": ["酒吧", "喝酒", "小酒", "清吧"],      "search": "酒吧",          "strength": 2, "icon": "🍸", "label": "酒吧"},
    {"key": "bowling",  "triggers": ["保龄球", "打保龄"],                  "search": "保龄球",        "strength": 2, "icon": "🎳", "label": "保龄球"},
    {"key": "gym",      "triggers": ["健身", "健身房"],                    "search": "健身房",        "strength": 2, "icon": "💪", "label": "健身房"},
    {"key": "coffee",   "triggers": ["咖啡", "喝咖啡", "咖啡馆"],          "search": "咖啡",          "strength": 1, "icon": "☕", "label": "咖啡"},
    {"key": "tea",      "triggers": ["喝茶", "茶馆", "茶室"],              "search": "茶馆",          "strength": 1, "icon": "🍵", "label": "茶馆"},
]

_BY_LABEL = {a["label"]: a for a in ACTIVITIES}


def detect_activities(text: str, max_n: int = 3) -> list[str]:
    """从文本里检测用户点名的活动，按强度降序返回 label 列表（最多 max_n 个）。"""
    hits = []
    for a in ACTIVITIES:
        if any(t in text for t in a["triggers"]):
            hits.append(a)
    # 按强度降序；同强度保持表中顺序（已大致按强度排）
    hits.sort(key=lambda a: -a["strength"])
    seen, out = set(), []
    for a in hits:
        if a["label"] not in seen:
            seen.add(a["label"])
            out.append(a["label"])
        if len(out) >= max_n:
            break
    return out


def search_word(label: str) -> str:
    """label → 高德搜索词。未知 label 直接当搜索词用。"""
    a = _BY_LABEL.get(label)
    return a["search"] if a else label


def icon_of(label: str) -> str:
    a = _BY_LABEL.get(label)
    return a["icon"] if a else "📍"


def normalize(labels) -> list[str]:
    """把任意输入（字符串/列表/None）规整成 label 列表，按强度降序、去重、最多3个。"""
    if not labels:
        return []
    if isinstance(labels, str):
        labels = [labels]
    # 对已知 label 按强度排，未知的排最后
    def strength(l):
        a = _BY_LABEL.get(l)
        return a["strength"] if a else 0
    uniq = []
    for l in labels:
        if l and l not in uniq:
            uniq.append(l)
    uniq.sort(key=lambda l: -strength(l))
    return uniq[:3]
