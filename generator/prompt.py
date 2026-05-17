SYSTEM_PROMPT = """你是一个腾讯云技术文档助手。根据检索到的文档片段回答用户问题。

规则：
1. 直接回答问题，简洁明了，不要啰嗦
2. 如果文档中有明确答案（API、参数、流程等），直接给出
3. 涉及图片时，用 ![描述](url) 嵌入回答中（最多1-2张关键图）
4. 涉及表格时用 Markdown 表格
5. 涉及代码/请求示例时用代码块
6. 不要在回答中写来源/引用，系统会自动附加
7. 文档中没有相关信息就明确告知
"""


def build_context(chunks: list[dict], metadata_db) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = metadata_db.get(chunk["id"])
        title = chunk["metadata"].get("title", "")
        section = chunk["metadata"].get("section", "")

        part = f"[片段 {i}] 文档: {title}"
        if section:
            part += f" | 章节: {section}"
        part += f"\n来源: {chunk['metadata']['url']}"
        part += f"\n{chunk['text']}"

        if meta:
            if meta["images"]:
                part += "\n\n关联图片:"
                for img in meta["images"]:
                    part += f"\n  - {img.get('alt', '')}: {img['src']}"

            if meta["tables"]:
                part += "\n\n关联表格:"
                for table in meta["tables"]:
                    part += f"\n  标题: {table.get('caption', '无')}"

            if meta["code_blocks"]:
                part += "\n\n关联代码:"
                for code in meta["code_blocks"]:
                    part += f"\n  语言: {code.get('language', '未知')}"

        parts.append(part)

    return "\n\n---\n\n".join(parts)


def build_user_message(query: str, context: str) -> str:
    return f"""请根据以下腾讯云文档片段回答问题。

文档片段：
{context}

问题：{query}

请直接给出答案，不要重复问题。如果文档中有相关内容，请引用具体信息。"""
