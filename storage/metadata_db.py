import json
import sqlite3
from pathlib import Path
from typing import Optional


class MetadataDB:
    def __init__(self, db_path: str = "data/sqlite/metadata.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                section TEXT,
                chunk_type TEXT,
                images TEXT,
                tables TEXT,
                code_blocks TEXT,
                breadcrumb TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                last_modified TEXT,
                etag TEXT,
                content_hash TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_page(self, url: str) -> Optional[dict]:
        """获取页面上次爬取的信息"""
        cursor = self.conn.execute(
            "SELECT url, last_modified, etag, content_hash, updated_at FROM pages WHERE url = ?",
            (url,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "url": row[0],
            "last_modified": row[1],
            "etag": row[2],
            "content_hash": row[3],
            "updated_at": row[4],
        }

    def update_page(self, url: str, last_modified: str = "", etag: str = "", content_hash: str = "") -> None:
        """更新页面爬取信息"""
        self.conn.execute(
            """INSERT OR REPLACE INTO pages (url, last_modified, etag, content_hash, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (url, last_modified, etag, content_hash),
        )
        self.conn.commit()

    def add(self, chunks: list) -> None:
        for chunk in chunks:
            self.conn.execute(
                """INSERT OR REPLACE INTO chunks
                   (id, url, title, section, chunk_type, images, tables, code_blocks, breadcrumb)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chunk.id,
                    chunk.metadata.url,
                    chunk.metadata.title,
                    chunk.metadata.section,
                    chunk.metadata.chunk_type.value,
                    json.dumps(chunk.metadata.images, ensure_ascii=False),
                    json.dumps(chunk.metadata.tables, ensure_ascii=False),
                    json.dumps(chunk.metadata.code_blocks, ensure_ascii=False),
                    json.dumps(chunk.metadata.breadcrumb, ensure_ascii=False),
                ),
            )
        self.conn.commit()

    def get(self, chunk_id: str) -> Optional[dict]:
        cursor = self.conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def query_by_url(self, url: str) -> list[dict]:
        cursor = self.conn.execute("SELECT * FROM chunks WHERE url = ?", (url,))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def delete_by_url(self, url: str) -> int:
        """删除指定 URL 的所有 chunks，返回删除数量"""
        cursor = self.conn.execute("DELETE FROM chunks WHERE url = ?", (url,))
        self.conn.commit()
        return cursor.rowcount

    def count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def _row_to_dict(self, row) -> dict:
        return {
            "id": row[0],
            "url": row[1],
            "title": row[2],
            "section": row[3],
            "chunk_type": row[4],
            "images": json.loads(row[5]) if row[5] else [],
            "tables": json.loads(row[6]) if row[6] else [],
            "code_blocks": json.loads(row[7]) if row[7] else [],
            "breadcrumb": json.loads(row[8]) if row[8] else [],
        }

    def close(self) -> None:
        self.conn.close()
