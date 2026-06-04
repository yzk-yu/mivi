"""
觅 MIVI · 配置层
------------------------------------------------------------------
所有开关和密钥集中在这。密钥从环境变量读，绝不写死在代码里。
本地用法：复制 .env.example 为 .env，填入自己的 key。
"""
import os

# ── 总开关：演示用 Mock（最稳），拿到 key 后改 false 走真接口 ──
# 也可用环境变量 MIVI_USE_MOCK=false 覆盖
USE_MOCK = os.getenv("MIVI_USE_MOCK", "true").lower() == "true"

# ── 高德 Web 服务 key ──
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE = "https://restapi.amap.com"

# ── LLM 可切换层：默认 DeepSeek，可切 Kimi / 通义（都兼容 OpenAI 格式）──
# 用环境变量 MIVI_LLM_PROVIDER 选择：deepseek | kimi | qwen
LLM_PROVIDER = os.getenv("MIVI_LLM_PROVIDER", "deepseek").lower()

LLM_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),  # 旧名 deepseek-chat 2026-07 退役
        "key_env": "DEEPSEEK_API_KEY",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
        "key_env": "KIMI_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": os.getenv("QWEN_MODEL", "qwen-plus"),
        "key_env": "DASHSCOPE_API_KEY",
    },
}


def active_llm() -> dict:
    """返回当前选中的 LLM 配置（含 key）。key 缺失时调用方应回退 Mock/关键词。"""
    cfg = dict(LLM_PROVIDERS.get(LLM_PROVIDER, LLM_PROVIDERS["deepseek"]))
    cfg["api_key"] = os.getenv(cfg["key_env"], "")
    cfg["provider"] = LLM_PROVIDER
    return cfg


def llm_available() -> bool:
    return bool(active_llm()["api_key"]) and not USE_MOCK


def amap_available() -> bool:
    return bool(AMAP_API_KEY) and not USE_MOCK
