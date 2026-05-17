# MLX Prompt Cache 命中规律分析

## 一、缓存机制原理

mlx_lm 使用 **PromptTrie** (前缀树) 数据结构管理缓存:

1. **存储**: 每次请求处理完后，将 token 序列和对应的 KV cache 存入 trie
2. **查找**: 新请求到来时，在 trie 中查找最长前缀匹配
3. **复用**: 找到匹配后，直接复用已计算的 KV 值，只需处理剩余未缓存的 token
4. **淘汰**: 当缓存数量超过 `prompt-cache-size` 或内存超过 `prompt-cache-bytes` 时，按 LRU 淘汰

**关键参数**:
- `--prompt-cache-size 2`: 最多缓存 2 个序列
- `--prompt-cache-bytes 2000000000`: 缓存内存上限 2GB

## 二、8B 模型测试结果

### 基础测试 (Qwen3-8B-MLX-6bit)

| 场景 | 耗时 | prompt tokens | cached | 命中率 |
|------|------|---------------|--------|--------|
| 首次请求 | 1.08s | 102 | 5 | 5% |
| 相同system+不同doc | 0.93s | 99 | 62 | 63% |
| 完全重复请求 | 0.93s | 102 | 62 | 61% |
| 不同system(英文) | 1.13s | 65 | 3 | 5% |
| 多轮追问1 | 1.03s | 136 | 3 | 2% |
| 多轮追问2 | 0.94s | 176 | 136 | 77% |
| 短system | 0.99s | 63 | 17 | 27% |
| 长system | 1.00s | 72 | 18 | 25% |

### 关键发现

1. **前缀匹配是核心**: 相同的 system prompt 开头可以命中缓存，即使后续内容不同
2. **RAG 场景友好**: system prompt 固定时，每次查询的 doc 内容变化不影响 system 部分的缓存
3. **多轮对话**: 前面的轮次可以被缓存复用，但需要对话历史作为前缀
4. **system prompt 变化会破坏缓存**: 即使只差几个字，缓存命中率也会大幅下降

## 三、27B 模型"表现差"的原因分析

### 1. 缓存命中率相同，但绝对延迟更高

27B 模型的缓存命中率和 8B 模型一样，但因为:
- 每个 token 的计算量大 3-4 倍
- 即使缓存命中 60%，剩余 40% 的 token 处理时间仍然很长
- 生成阶段每个 token 都需要完整的前向传播

**举例**:
- 8B: 100 tokens prompt + 50 tokens generation ≈ 1.0s + 0.5s = 1.5s
- 27B: 100 tokens prompt + 50 tokens generation ≈ 3.0s + 2.0s = 5.0s
- 缓存命中 60% 时:
  - 8B: 40 tokens + 50 tokens ≈ 0.4s + 0.5s = 0.9s (省 0.6s)
  - 27B: 40 tokens + 50 tokens ≈ 1.2s + 2.0s = 3.2s (省 1.8s)

### 2. 内存限制导致缓存容量不足

27B 模型的单个 KV cache 更大:
- 8B 6-bit: 每个 cached sequence 约 20-30MB
- 27B 4-bit: 每个 cached sequence 约 80-120MB

在 `prompt-cache-bytes=2GB` 限制下:
- 8B: 可缓存 ~80 个序列
- 27B: 可缓存 ~20 个序列

当并发请求多时，27B 的缓存更容易被淘汰。

### 3. Hermes Agent 的 system prompt 不稳定

Hermes 的 system prompt 包含:
- 工具定义 (每次可能不同)
- 上下文信息 (时间戳、memory 等)
- 项目上下文 (AGENTS.md 内容)

如果这些内容在每次请求间变化，会导致:
- prompt 前缀不匹配
- 缓存无法命中
- 每次都要重新处理整个 prompt

### 4. Thinking 模型的特殊性

Qwen3 是 thinking 模型，生成时会先输出 reasoning 再输出 content。这意味着:
- 生成阶段更长
- 缓存只能加速 prompt 处理阶段
- 对于短 prompt，缓存收益有限

## 四、优化建议

### 对 27B 模型

1. **稳定 system prompt**: 将不变的工具定义和规则放在最前面
2. **增加 prompt-cache-size**: 从 2 增加到 5-10，但要注意内存
3. **使用 pipeline 模式**: 已经开启了，可以让多个请求共享 KV cache
4. **考虑量化**: 当前是 4-bit，已经很低了

### 对 RAG 系统

1. **固定 system prompt**: 确保每次请求的 system prompt 完全相同
2. **将检索结果放在 user message 中**: 这样 system 部分可以被缓存
3. **多轮对话**: 保持对话历史完整，利用前缀匹配

### 监控缓存效果

查看服务器日志:
```
tail -f qwen-mlx-server.log | grep "Prompt Cache"
```

关注:
- `Prompt Cache: N sequences`: 缓存序列数
- `Prompt processing progress: X/Y`: 实际处理的 token 数 (Y-X 是缓存命中的)
- `cached_tokens` in API response: 缓存命中的 token 数

## 五、测试脚本

- `test_cache.py`: 基础缓存测试
- `test_cache_rag.py`: RAG 场景测试
