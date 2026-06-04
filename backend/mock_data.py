"""
觅 MIVI · Mock 数据
------------------------------------------------------------------
苏州约会场景的演示数据。字段结构严格对齐 API_SPEC.md，
后端先用这些假数据跑通全链路，之后逐个换成高德 / DeepSeek 真数据。
所有数据均为虚构 / LLM 生成示例，不含任何真实用户信息（合规）。
"""

VENUES: dict[str, dict] = {
    "白岛咖啡": {
        "type": "cafe",
        "name": "白岛咖啡",
        "rating": 4.6,
        "reviewCount": 1280,
        "tags": ["咖啡", "安静", "适合拍照", "人均 ¥45"],
        "address": "苏州市姑苏区平江路历史街区 32 号",
        "hours": "09:00 - 21:00",
        "perCapita": 45,
        "currentQueue": "无需排队",
        "canStayLong": True,
        "hasWifi": True,
        "petFriendly": False,
        "specials": ["📮 明信片寄送 ¥5/张", "📚 二楼有独立阅读区"],
        "hero": {"color": "#FFD9B0", "label": "白岛咖啡"},
        "photos": [],
    },
    "苏州博物馆西馆": {
        "type": "scenic",
        "name": "苏州博物馆西馆",
        "rating": 4.8,
        "reviewCount": 5600,
        "tags": ["博物馆", "贝聿铭", "免费", "适合拍照"],
        "address": "苏州市高新区长江路 399 号",
        "hours": "09:00 - 17:00（周一闭馆）",
        "price": "免费",
        "needBooking": False,
        "crowd": "中等",
        "suggestedDuration": "90-120 分钟",
        "bestTime": "工作日上午人最少",
        "foxTips": {
            "mustSee": ["现代艺术展厅", "建筑本身"],
            "avoid": "周末 14:00 后人流激增",
            "hidden": "西馆后院有片竹林，很少人去，拍照绝佳",
        },
        "hero": {"color": "#C9E3D4", "label": "苏博西馆"},
        "photos": [],
    },
    "晴川日料": {
        "type": "restaurant",
        "name": "晴川日料",
        "rating": 4.7,
        "reviewCount": 2341,
        "tags": ["日料", "必吃榜", "人均 ¥130"],
        "address": "苏州市姑苏区平江路历史街区 88 号",
        "phone": "0512-88888888",
        "hours": "11:00 - 21:30",
        "perCapita": 130,
        "currentQueue": "约 15 分钟",
        "rating_detail": {"taste": 4.8, "env": 4.6, "service": 4.5},
        "recommend": ["寿司拼盘", "鳗鱼饭", "芝士玉子烧"],
        "avoid": [{"name": "炸物拼盘", "reason": "差评率 18%，「油腻」「不值」高频出现"}],
        "reviews": [
            {"name": "用户***234", "date": "2025-11-15", "stars": 5, "text": "鳗鱼饭超好吃，环境也安静"},
        ],
        "hero": {"color": "#FFB74D", "label": "晴川日料"},
        "photos": [],
    },
    "花月日本料理": {
        "type": "restaurant",
        "name": "花月日本料理",
        "rating": 4.5,
        "reviewCount": 1560,
        "tags": ["日料", "安静", "人均 ¥120"],
        "address": "苏州市姑苏区观前街 52 号",
        "phone": "0512-66666666",
        "hours": "11:00 - 22:00",
        "perCapita": 120,
        "currentQueue": "无需排队",
        "rating_detail": {"taste": 4.5, "env": 4.6, "service": 4.4},
        "recommend": ["刺身拼盘", "天妇罗", "茶碗蒸"],
        "avoid": [],
        "reviews": [],
        "hero": {"color": "#F4A8B8", "label": "花月日料"},
        "photos": [],
    },
    "平江路夜景": {
        "type": "scenic",
        "name": "平江路夜景",
        "rating": 4.7,
        "reviewCount": 8900,
        "tags": ["古街", "夜景", "免费", "适合散步"],
        "address": "苏州市姑苏区平江路",
        "hours": "全天开放",
        "price": "免费",
        "needBooking": False,
        "crowd": "晚间较多",
        "suggestedDuration": "30-60 分钟",
        "bestTime": "日落后灯光最美",
        "foxTips": {
            "mustSee": ["小桥流水", "沿河灯光"],
            "avoid": "周末晚 20:00 后人挤人",
            "hidden": "钮家巷拐进去有家安静的评弹馆",
        },
        "hero": {"color": "#A8C4E3", "label": "平江路夜景"},
        "photos": [],
    },
}

# 备选商家映射
ALTERNATIVES: dict[str, list[dict]] = {
    "晴川日料": [
        {"name": "花月日本料理", "rating": 4.5, "perCapita": 120, "walk_minutes": 8,
         "currentQueue": "无需排队", "reason": "同为日料，评分接近，距离更近，现在不用等"},
        {"name": "苏帮味道", "rating": 4.6, "perCapita": 95, "walk_minutes": 12,
         "currentQueue": "约 10 分钟", "reason": "苏帮菜，性价比更高，环境安静"},
    ],
}

# 到店辅助
IN_STORE_TIPS: dict[str, dict] = {
    "晴川日料": {
        "venue": "晴川日料", "type": "restaurant",
        "order_tips": {
            "recommend": [
                {"name": "寿司拼盘", "price": 88, "reason": "招牌必点，新鲜度好评最多"},
                {"name": "鳗鱼饭", "price": 68, "reason": "好评率 92%，分量足"},
                {"name": "芝士玉子烧", "price": 32, "reason": "颜值高，适合拍照"},
            ],
            "avoid": [{"name": "炸物拼盘", "price": 48, "reason": "差评率 18%，油腻不值"}],
            "combo_suggestion": "这 3 道两个人吃正好，预估 ¥188（人均 ¥94）",
            "budget_status": {"spent_so_far": 62, "this_meal_estimate": 188, "remaining": 250, "verdict": "充裕"},
        },
        "fox_tips": "靠窗位置光线最好，适合拍照；跟服务员说「少冰」，饮品会好喝很多",
    },
    "苏州博物馆西馆": {
        "venue": "苏州博物馆西馆", "type": "scenic",
        "visit_tips": {
            "route": "建议从一楼现代展厅开始 → 二楼古典展 → 负一楼临展",
            "must_see": ["贝聿铭建筑设计", "现代艺术展厅"],
            "skip": "纪念品商店（性价比低）",
            "duration": "建议 90 分钟",
            "photo_spots": ["中庭水池", "几何天窗", "西馆后院竹林"],
        },
        "fox_tips": "后院竹林很少人去，拍照特别好看，从展厅 B 出口左转就到",
    },
}

# 三套方案（comfort 完整，其余给摘要 —— 与 API_SPEC 一致）
PLANS = {
    "comfort": {
        "id": "comfort", "name": "🛋️ 舒适方案", "recommended": True,
        "summary": "轻松约会路线，少走路，氛围好，预算可控",
        "metrics": {"comfort": 88, "fatigue": "低", "budget": 295, "queue_risk": "低"},
        "slots": [
            {"time": "13:30", "venue": "出发", "icon": "🕐", "kind": "transit", "duration": 0, "walk": 8, "price": 0, "status": "pending", "alt_venues": []},
            {"time": "14:00", "venue": "白岛咖啡", "icon": "☕", "kind": "cafe", "duration": 60, "walk": 0, "price": 45, "status": "pending", "alt_venues": ["猫空书店", "半山咖啡"]},
            {"time": "15:20", "venue": "苏州博物馆西馆", "icon": "🏛️", "kind": "scenic", "duration": 90, "walk": 12, "price": 0, "status": "pending", "alt_venues": ["拙政园", "平江路"]},
            {"time": "17:30", "venue": "晴川日料", "icon": "🍣", "kind": "dining", "duration": 90, "walk": 10, "price": 130, "status": "pending", "alt_venues": ["花月日本料理", "苏帮味道"]},
            {"time": "19:10", "venue": "平江路夜景", "icon": "🌙", "kind": "walk", "duration": 30, "walk": 5, "price": 0, "status": "pending", "alt_venues": ["诚品书店"]},
        ],
        "timeline": ["白岛咖啡", "苏州博物馆西馆", "晴川日料", "平江路夜景"],
        "total_budget": 295, "total_walk_minutes": 35, "buffer_minutes": 40,
    },
    "efficient": {
        "id": "efficient", "name": "⚡ 高效方案", "recommended": False,
        "summary": "多去几个点，时间利用率高",
        "metrics": {"comfort": 78, "fatigue": "中", "budget": 350, "queue_risk": "中"},
        "slots": [], "timeline": [], "total_budget": 350, "total_walk_minutes": 55, "buffer_minutes": 25,
    },
    "surprise": {
        "id": "surprise", "name": "🎲 惊喜方案", "recommended": False,
        "summary": "包含小众打卡点，适合探索",
        "metrics": {"comfort": 82, "fatigue": "中", "budget": 320, "queue_risk": "中"},
        "slots": [], "timeline": [], "total_budget": 320, "total_walk_minutes": 45, "buffer_minutes": 30,
    },
}
