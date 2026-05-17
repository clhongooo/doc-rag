#!/usr/bin/env python3
"""测试 prompt cache 命中规律"""
import requests
import time
import json

SERVER = "http://127.0.0.1:8080/v1/chat/completions"

def test_request(messages, label=""):
    """发送请求并记录耗时"""
    start = time.time()
    resp = requests.post(SERVER, json={
        "model": "default",
        "messages": messages,
        "max_tokens": 50,
        "temperature": 0.6,
    }, timeout=120)
    elapsed = time.time() - start
    
    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        # Thinking 模型可能返回 reasoning 而非 content
        msg = data["choices"][0]["message"]
        content = msg.get("content", "") or msg.get("reasoning", "") or ""
        content = content[:80] if content else "(empty)"
        cache_status = usage.get("prompt_tokens_details", {}).get("cached_tokens", None)
        cache_info = f"cached:{cache_status}" if cache_status else "no-cache-info"
        print(f"[{label}] {elapsed:.2f}s | prompt:{prompt_tokens} | completion:{completion_tokens} | {cache_info} | {content}")
        return elapsed, prompt_tokens, usage
    else:
        print(f"[{label}] ERROR {resp.status_code}: {resp.text[:200]}")
        return elapsed, 0, {}

# ============================================================
# 测试1: 首次请求 (无缓存)
# ============================================================
print("=" * 60)
print("测试1: 首次请求 (无缓存)")
print("=" * 60)

system_msg = "你是一个有帮助的助手。请用中文回答。"
user_msg1 = "请解释什么是机器学习？"

messages1 = [
    {"role": "system", "content": system_msg},
    {"role": "user", "content": user_msg1}
]
t1, pt1, usage1 = test_request(messages1, "首次请求")

# ============================================================
# 测试2: 相同 system prompt + 新问题 (应该命中缓存)
# ============================================================
print("\n" + "=" * 60)
print("测试2: 相同 system prompt + 新问题 (期望缓存命中)")
print("=" * 60)

user_msg2 = "请解释什么是深度学习？"
messages2 = [
    {"role": "system", "content": system_msg},
    {"role": "user", "content": user_msg2}
]
t2, pt2, usage2 = test_request(messages2, "相同system+新问题")

# ============================================================
# 测试3: 完全相同的请求 (应该完全缓存命中)
# ============================================================
print("\n" + "=" * 60)
print("测试3: 完全相同的请求 (期望完全缓存)")
print("=" * 60)

t3, pt3, usage3 = test_request(messages1, "完全相同请求")

# ============================================================
# 测试4: 不同 system prompt (缓存不命中)
# ============================================================
print("\n" + "=" * 60)
print("测试4: 不同 system prompt (期望缓存不命中)")
print("=" * 60)

messages4 = [
    {"role": "system", "content": "You are a helpful assistant. Answer in English."},
    {"role": "user", "content": "What is machine learning?"}
]
t4, pt4, usage4 = test_request(messages4, "不同system+英文")

# ============================================================
# 测试5: 多轮对话 (前缀匹配)
# ============================================================
print("\n" + "=" * 60)
print("测试5: 多轮对话 (前缀匹配)")
print("=" * 60)

messages5 = [
    {"role": "system", "content": system_msg},
    {"role": "user", "content": user_msg1},
    {"role": "assistant", "content": "机器学习是人工智能的一个分支..."},
    {"role": "user", "content": "能举个例子吗？"}
]
t5, pt5, usage5 = test_request(messages5, "多轮对话")

# ============================================================
# 测试6: 增加一个 system 标记来测试精确前缀
# ============================================================
print("\n" + "=" * 60)
print("测试6: 在测试5基础上追加一轮")
print("=" * 60)

messages6 = messages5 + [
    {"role": "assistant", "content": "比如图像识别就是典型的机器学习应用..."},
    {"role": "user", "content": "还有其他例子吗？"}
]
t6, pt6, usage6 = test_request(messages6, "多轮+追加")

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 60)
print("总结对比")
print("=" * 60)
print(f"{'请求':<25} {'耗时':>8} {'prompt tokens':>15} {'cache状态':>10}")
print("-" * 60)
results = [
    ("首次请求", t1, pt1),
    ("相同system+新问题", t2, pt2),
    ("完全相同请求", t3, pt3),
    ("不同system", t4, pt4),
    ("多轮对话", t5, pt5),
    ("多轮+追加", t6, pt6),
]
for label, t, pt in results:
    print(f"{label:<25} {t:>7.2f}s {pt:>15}")
