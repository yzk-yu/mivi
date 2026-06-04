"""
觅 MIVI · 高德 Web 服务客户端
------------------------------------------------------------------
只用与"定位探测"无关的接口（地理编码/POI/路径/天气）。
位置坐标只来自：用户说的地名(geocode) 或 用户授权的 GPS(用完即焚)，绝不静默采集、绝不落盘。

智能选交通：按距离自动选步行/公交/驾车，再用 8 维偏好向量(体力/预算)微调。
"""
from __future__ import annotations
import requests

import config

TIMEOUT = 8


def _get(path: str, params: dict) -> dict | None:
    if not config.amap_available():
        return None
    params = {**params, "key": config.AMAP_API_KEY, "output": "json"}
    import time
    for attempt in range(3):   # 限流(CUQPS)时自动重试，最多 3 次
        try:
            r = requests.get(f"{config.AMAP_BASE}{path}", params=params, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if str(data.get("status")) != "1":
                info = str(data.get("info") or "")
                # 并发超限是瞬时的 → 退避后重试
                if "CUQPS" in info or "LIMIT" in info.upper():
                    if attempt < 2:
                        time.sleep(0.4 * (attempt + 1))   # 0.4s, 0.8s 退避
                        continue
                print(f"[amap] 业务错误 {path}: {info}")
                return None
            return data
        except Exception as e:
            if attempt < 2:
                time.sleep(0.3)
                continue
            print(f"[amap] 请求失败 {path}: {e}")
            return None
    return None


# ── 地理编码：用户说的地名 → 坐标（合规，非定位）──
def geocode(address: str, city: str = "") -> str | None:
    """返回 '经度,纬度' 字符串，失败返回 None"""
    data = _get("/v3/geocode/geo", {"address": address, "city": city})
    if data and data.get("geocodes"):
        return data["geocodes"][0]["location"]
    return None


def reverse_geocode_city(lng: float, lat: float) -> str | None:
    """坐标 → 城市名（逆地理编码）。返回如 '杭州市'，失败返回 None。坐标用完即焚。"""
    data = _get("/v3/geocode/regeo", {"location": f"{lng},{lat}"})
    if not data:
        return None
    comp = data.get("regeocode", {}).get("addressComponent", {})
    city = comp.get("city") or comp.get("province")
    # 直辖市等情况 city 可能是 []，回退到 province
    if isinstance(city, list):
        city = comp.get("province")
    return city or None


# ── POI 搜索 ──
def _flatten(v):
    """高德 extensions=all 里很多字段空值会返回 []，统一成字符串/None。"""
    if isinstance(v, list):
        return None if not v else v
    return v or None

def place_text(keywords: str, city: str = "苏州", page_size: int = 5,
               types: str = "", location: str = "") -> list[dict] | None:
    """
    POI 文本搜索。extensions=all 拿评分/人均/营业时间/照片等富字段。
    types: 高德 POI 分类码（可选，精准搜某类，过滤杂物）。
    location: "经度,纬度"（可选，结果向该点附近偏置）。
    """
    params = {"keywords": keywords, "city": city, "offset": page_size,
              "extensions": "all", "citylimit": "true"}
    if types:
        params["types"] = types
    if location:
        params["location"] = location  # 高德会按距离优先
    data = _get("/v3/place/text", params)
    if not data:
        return None
    out = []
    for p in data.get("pois", []):
        biz = p.get("biz_ext", {}) if isinstance(p.get("biz_ext"), dict) else {}
        photos = p.get("photos", [])
        photo_urls = [ph.get("url") for ph in photos if isinstance(ph, dict) and ph.get("url")] if isinstance(photos, list) else []
        out.append({
            "name": p.get("name"),
            "address": _flatten(p.get("address")) or (p.get("pname", "") + p.get("cityname", "") + p.get("adname", "")),
            "location": p.get("location"),
            "type": _flatten(p.get("type")),
            "typecode": _flatten(p.get("typecode")),
            "tel": _flatten(p.get("tel")),
            "rating": _flatten(biz.get("rating")),       # 评分（常缺，缺则 None）
            "cost": _flatten(biz.get("cost")),           # 人均（常缺）
            "open_time": _flatten(biz.get("open_time")), # 营业时间（常缺）
            "photos": photo_urls,                         # 实景图 URL 列表
        })
    return out


# ── 天气 ──
def weather(city_adcode: str) -> dict | None:
    data = _get("/v3/weather/weatherInfo", {"city": city_adcode})
    if data and data.get("lives"):
        live = data["lives"][0]
        return {
            "city": live.get("city"), "weather": live.get("weather"),
            "temperature": live.get("temperature"), "winddirection": live.get("winddirection"),
        }
    return None


# ── 四种路径规划 ──
def route_walking(origin: str, dest: str) -> dict | None:
    data = _get("/v3/direction/walking", {"origin": origin, "destination": dest})
    if data and data.get("route", {}).get("paths"):
        p = data["route"]["paths"][0]
        return {"mode": "walking", "distance_m": int(p["distance"]), "duration_min": round(int(p["duration"]) / 60)}
    return None


def route_driving(origin: str, dest: str) -> dict | None:
    data = _get("/v3/direction/driving", {"origin": origin, "destination": dest})
    if data and data.get("route", {}).get("paths"):
        p = data["route"]["paths"][0]
        return {
            "mode": "driving", "distance_m": int(p["distance"]),
            "duration_min": round(int(p["duration"]) / 60),
            "taxi_cost": data["route"].get("taxi_cost"),
        }
    return None


def route_transit(origin: str, dest: str, city: str) -> dict | None:
    data = _get("/v3/direction/transit/integrated", {"origin": origin, "destination": dest, "city": city})
    if data and data.get("route", {}).get("transits"):
        t = data["route"]["transits"][0]
        return {
            "mode": "transit", "distance_m": int(t.get("distance", 0)),
            "duration_min": round(int(t["duration"]) / 60),
            "cost": t.get("cost"), "walking_m": int(t.get("walking_distance", 0)),
        }
    return None


def route_bicycling(origin: str, dest: str) -> dict | None:
    # 骑行是 v4 接口，返回结构略不同
    if not config.amap_available():
        return None
    try:
        r = requests.get(f"{config.AMAP_BASE}/v4/direction/bicycling",
                         params={"origin": origin, "destination": dest, "key": config.AMAP_API_KEY}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        paths = data.get("data", {}).get("paths", [])
        if paths:
            p = paths[0]
            return {"mode": "bicycling", "distance_m": int(p["distance"]), "duration_min": round(int(p["duration"]) / 60)}
    except Exception as e:
        print(f"[amap] 骑行请求失败: {e}")
    return None


# ── 智能选交通：距离 + 偏好向量 ──
def pick_transport(origin: str, dest: str, city: str, vector: dict | None = None) -> dict:
    """
    按距离自动选交通方式，再用偏好向量微调：
      < 1.5km → 步行
      1.5–5km → 公交/骑行（体力低则建议打车）
      > 5km   → 驾车/打车（预算敏感则给公交备选）
    返回 {recommended, options[]}。真接口不可用时给 Mock。
    """
    vector = vector or core_default_vector()
    walk = route_walking(origin, dest)

    # Mock 兜底：没有真接口时，返回一个合理的步行估计
    if not walk:
        return {
            "recommended": {"mode": "walking", "distance_m": 800, "duration_min": 10, "label": "🚶 步行 10 分钟"},
            "options": [{"mode": "walking", "distance_m": 800, "duration_min": 10, "label": "🚶 步行 10 分钟"}],
            "source": "mock",
        }

    dist_km = walk["distance_m"] / 1000
    options = [_label(walk)]
    energy = vector.get("energy", 0.6)   # 低=想躺平
    budget = vector.get("budget", 0.5)   # 高=预算敏感

    if dist_km < 1.5:
        recommended = walk
        # 近距离也补一个公交/打车备选，给用户选择
        t = route_transit(origin, dest, city)
        if t: options.append(_label(t))
        if energy < 0.4:
            d = route_driving(origin, dest)
            if d:
                options.append(_label(d))
    elif dist_km <= 5:
        t = route_transit(origin, dest, city)
        b = route_bicycling(origin, dest)
        if t: options.append(_label(t))
        if b: options.append(_label(b))
        # 体力低优先公交，否则可骑行；都没有就步行
        recommended = t or b or walk
        if energy < 0.35:
            d = route_driving(origin, dest)
            if d: recommended = d; options.append(_label(d))
    else:
        d = route_driving(origin, dest)
        t = route_transit(origin, dest, city)   # 长距离也总是给公交/地铁选项
        recommended = d or t or walk
        opts = []
        if d: opts.append(_label(d))
        if t: opts.append(_label(t))            # 公交/地铁
        opts.append(_label(walk))
        options = opts

    return {"recommended": _label(recommended), "options": options, "source": "amap"}


def _label(route: dict) -> dict:
    icons = {"walking": "🚶 步行", "transit": "🚌 公交/地铁", "driving": "🚗 驾车/打车", "bicycling": "🚴 骑行"}
    label = f"{icons.get(route['mode'], route['mode'])} {route['duration_min']} 分钟"
    if route.get("taxi_cost"):
        label += f"（打车约 ¥{round(float(route['taxi_cost']))}）"
    if route.get("cost"):
        label += f"（¥{route['cost']}）"
    return {**route, "label": label}


def core_default_vector() -> dict:
    import core
    return dict(core.DEFAULT_VECTOR)
