#!/usr/bin/env python3
"""
MLX Prompt Cache 命中规律分析
重点测试 RAG 场景下的缓存行为
"""
import requests
import time
import json
import hashlib

SERVER = "http://127.0.0.1:8080/v1/chat/completions"

def test_request(messages, label="", extra_body=None):
    payload = {
        "model": "default",
        "messages": messages,
        "max_tokens": 30,
        "temperature": 0.6,
    }
    if extra_body:
        payload.update(extra_body)
    
    start = time.time()
    resp = requests.post(SERVER, json=payload, timeout=120)
    elapsed = time.time() - start
    
    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        msg = data["choices"][0]["message"]
        content = (msg.get("content", "") or msg.get("reasoning", "") or "")[:60]
        
        # 计算 prompt 的 hash 用于追踪
        msg_str = json.dumps(messages, ensure_ascii=False)
        msg_hash = hashlib.md5(msg_str.encode()).hexdigest()[:8]
        
        hit_rate = f"{cached/prompt_tokens*100:.0f}%" if prompt_tokens > 0 else "N/A"
        print(f"[{label}] {elapsed:.2f}s | tokens:{prompt_tokens} | cached:{cached}({hit_rate}) | hash:{msg_hash} | {content}")
        return elapsed, prompt_tokens, cached, usage
    else:
        print(f"[{label}] ERROR {resp.status_code}: {resp.text[:200]}")
        return elapsed, 0, 0, {}

# ============================================================
# RAG 场景模拟
# ============================================================
print("=" * 70)
print("RAG 场景缓存分析")
print("=" * 70)

# 模拟 RAG 系统 prompt (每次查询都一样的部分)
RAG_SYSTEM = """你是一个智能文档问答助手。请根据提供的参考资料回答用户的问题。
如果参考资料中没有相关信息，请如实说明。

规则：
1. 回答要准确、简洁
2. 引用参考资料中的具体内容
3. 不要编造不存在的信息"""

# 不同的检索结果 (模拟每次查询检索到不同文档)
doc1 = "参考资料1：腾讯云IM支持多种消息类型，包括文本、图片、音视频等。SDK提供了 sendMessage API 用于发送消息。"
doc2 = "参考资料2：消息回调通过 REST API 实现，配置回调地址后，服务器会在消息到达时主动推送通知。"
doc3 = "参考资料3：用户管理包括注册、登录、资料修改等操作。调用 sigup 接口完成用户注册。"

# ============================================================
# 场景1: 相同 system + 不同检索结果 (RAG 常见场景)
# ============================================================
print("\n--- 场景1: 相同 system + 不同检索结果 ---")

q1 = "如何发送消息？"
msgs_rag1 = [
    {"role": "system", "content": RAG_SYSTEM},
    {"role": "user", "content": f"{doc1}\n\n用户问题：{q1}"}
]
t1, pt1, c1, _ = test_request(msgs_rag1, "RAG查询1")

q2 = "如何接收消息回调？"
msgs_rag2 = [
    {"role": "system", "content": RAG_SYSTEM},
    {"role": "user", "content": f"{doc2}\n\n用户问题：{q2}"}
]
t2, pt2, c2, _ = test_request(msgs_rag2, "RAG查询2")

q3 = "如何注册用户？"
msgs_rag3 = [
    {"role": "system", "content": RAG_SYSTEM},
    {"role": "user", "content": f"{doc3}\n\n用户问题：{q3}"}
]
t3, pt3, c3, _ = test_request(msgs_rag3, "RAG查询3")

# ============================================================
# 场景2: 相同 system + 相同检索结果 (缓存最优)
# ============================================================
print("\n--- 场景2: 完全相同请求 (最佳缓存) ---")

t4, pt4, c4, _ = test_request(msgs_rag1, "完全重复RAG1")

# ============================================================
# 场景3: 不同 system prompt (每次都不一样)
# ============================================================
print("\n--- 场景3: 不同 system prompt (缓存最差) ---")

msgs_diff1 = [
    {"role": "system", "content": "You are a helpful assistant. Answer in English."},
    {"role": "user", "content": f"Based on: {doc1}\n\nQuestion: How to send messages?"}
]
t5, pt5, c5, _ = test_request(msgs_diff1, "英文system+doc1")

msgs_diff2 = [
    {"role": "system", "content": "Du bist ein hilfreicher Assistent. Antworte auf Deutsch."},
    {"role": "user", "content": f"Basierend auf: {doc2}\n\nFrage: Wie empfängt man Nachrichten?"}
]
t6, pt6, c6, _ = test_request(msgs_diff2, "德文system+doc2")

# ============================================================
# 场景4: 多轮对话 (RAG 追问场景)
# ============================================================
print("\n--- 场景4: 多轮追问 (RAG 追问) ---")

msgs_multi1 = [
    {"role": "system", "content": RAG_SYSTEM},
    {"role": "user", "content": f"{doc1}\n\n用户问题：{q1}"},
    {"role": "assistant", "content": "根据参考资料，您可以通过调用 sendMessage API 来发送消息..."},
    {"role": "user", "content": "能详细说说这个 API 的参数吗？"}
]
t7, pt7, c7, _ = test_request(msgs_multi1, "RAG追问1")

msgs_multi2 = msgs_multi1 + [
    {"role": "assistant", "content": "sendMessage API 主要参数包括：to（接收方ID）、msgType（消息类型）、content（消息内容）..."},
    {"role": "user", "content": "图片消息怎么发？"}
]
t8, pt8, c8, _ = test_request(msgs_multi2, "RAG追问2")

# ============================================================
# 场景5: system prompt 微小差异 (可能破坏缓存)
# ============================================================
print("\n--- 场景5: system prompt 微小差异 ---")

sys_v1 = "你是一个智能文档问答助手。请根据提供的参考资料回答用户的问题。"
sys_v2 = "你是一个智能文档问答助手。请根据提供的参考资料回答用户的问题。如果参考资料中没有相关信息，请如实说明。"

msgs_sysv1 = [
    {"role": "system", "content": sys_v1},
    {"role": "user", "content": f"{doc1}\n\n问题：{q1}"}
]
t9, pt9, c9, _ = test_request(msgs_sysv1, "短system+doc1")

msgs_sysv2 = [
    {"role": "system", "content": sys_v2},
    {"role": "user", "content": f"{doc1}\n\n问题：{q1}"}
]
t10, pt10, c10, _ = test_request(msgs_sysv2, "长system+doc1")

# ============================================================
# 总结
# ============================================================
print("\n" + "=" * 70)
print("总结分析")
print("=" * 70)
print(f"{'场景':<25} {'耗时':>8} {'tokens':>8} {'cached':>8} {'命中率':>8}")
print("-" * 70)

results = [
    ("RAG查询1 (首次)", t1, pt1, c1),
    ("RAG查询2 (同sys不同doc)", t2, pt2, c2),
    ("RAG查询3 (同sys不同doc)", t3, pt3, c3),
    ("完全重复RAG1", t4, pt4, c4),
    ("英文system", t5, pt5, c5),
    ("德文system", t6, pt6, c6),
    ("RAG追问1", t7, pt7, c7),
    ("RAG追问2", t8, pt8, c8),
    ("短system", t9, pt9, c9),
    ("长system", t10, pt10, c10),
]
for label, t, pt, c in results:
    hit = f"{c/pt*100:.0f}%" if pt > 0 else "N/A"
    print(f"{label:<25} {t:>7.2f}s {pt:>8} {c:>8} {hit:>8}")

print("\n" + "=" * 70)
print("关键发现:")
print("1. mlx_lm 使用前缀匹配 (prefix matching) 策略")
print("2. 相同 system prompt 开头的请求可以命中缓存")
print("3. prompt-cache-size 控制缓存的序列数量")
print("4. RAG 场景: system prompt 固定时，doc 内容变化不影响前缀缓存")
print("5. 多轮对话: 前面的轮次可以被缓存复用")
print("=" * 70)
