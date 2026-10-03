import os
import time
from datetime import date
import requests

FALLBACK = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-5", "gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"]
_CACHE = {"ts": 0.0, "data": None}
TTL = 600
_OPENAI_SKIP = ("embedding", "whisper", "tts", "dall-e", "audio", "realtime", "transcribe",
                "image", "moderation", "search", "codex", "instruct")


def _openai(key):
    r = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
    r.raise_for_status()
    ids = [m["id"] for m in r.json()["data"]]
    return sorted(i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))
                  and not any(s in i for s in _OPENAI_SKIP))


def _anthropic(key):
    r = requests.get("https://api.anthropic.com/v1/models?limit=1000",
                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=15)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json()["data"])


def _gemini(key):
    out, token = [], None
    while True:
        params = {"key": key, "pageSize": 100, **({"pageToken": token} if token else {})}
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        out += [f"gemini/{m['name'].split('/', 1)[1]}" for m in j.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]
        token = j.get("nextPageToken")
        if not token:
            return sorted(out)


PROVIDERS = {
    "openai": ("OPENAI_API_KEY", _openai),
    "anthropic": ("ANTHROPIC_API_KEY", _anthropic),
    "gemini": (("GEMINI_API_KEY", "GOOGLE_API_KEY"), _gemini),
}


def list_models(refresh: bool = False) -> dict:
    if not refresh and _CACHE["data"] and time.time() - _CACHE["ts"] < TTL:
        return _CACHE["data"]
    models, errors = [], {}
    for name, (env, fn) in PROVIDERS.items():
        envs = (env,) if isinstance(env, str) else env
        key = next((os.getenv(e) for e in envs if os.getenv(e)), None)
        if not key:
            errors[name] = f"{envs[0]} não configurada"
            continue
        try:
            models += fn(key)
        except Exception as e:
            errors[name] = str(e)[:200]
    data = {"models": models or FALLBACK, "live": bool(models), "errors": errors}
    _CACHE.update(ts=time.time(), data=data)
    return data


_SKIP_AUTO = _OPENAI_SKIP + ("preview", "-exp", "thinking", "deep-research", "computer-use", "robotics")


def _price(model: str):
    """(input, output) USD por token segundo a tabela de preços do LiteLLM, ou None se desconhecido/inadequado."""
    from litellm import model_cost
    info = model_cost.get(model)
    if not info or info.get("mode") != "chat":
        return None
    i, o = info.get("input_cost_per_token"), info.get("output_cost_per_token")
    if not i or not o:
        return None
    dep = info.get("deprecation_date")
    if dep and str(dep) < date.today().isoformat():
        return None
    return i, o


def cheapest_models(n: int = 5, refresh: bool = False) -> list:
    """Modelos de chat mais baratos entre os DISPONÍVEIS (lista ao vivo das suas chaves) que têm preço no LiteLLM.
    Custo ponderado 3:1 entrada/saída, pois consolidar memória é uma tarefa dominada por entrada."""
    data = list_models(refresh)
    if not data.get("live"):
        return []  # sem lista ao vivo não sabemos o que está disponível
    ranked = []
    for m in data["models"]:
        if any(x in m for x in _SKIP_AUTO):
            continue
        p = _price(m)
        if p:
            ranked.append((3 * p[0] + p[1], m, p))
    ranked.sort()
    return [{"model": m, "input_per_1m": round(p[0] * 1e6, 4), "output_per_1m": round(p[1] * 1e6, 4)}
            for _, m, p in ranked[:n]]


def cheapest_model():
    try:
        r = cheapest_models(1)
        return r[0]["model"] if r else None
    except Exception:
        return None
