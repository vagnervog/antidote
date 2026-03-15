"""SQLite FTS5 memory store."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    id: int
    content: str
    category: str
    created_at: str
    relevance: float


class BaseMemory(ABC):
    @abstractmethod
    async def save(self, content: str, category: str = "fact") -> int:
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        ...

    @abstractmethod
    async def forget(self, memory_id: int) -> bool:
        ...

    @abstractmethod
    async def recent(self, limit: int = 20) -> list[MemoryEntry]:
        ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'fact',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    category,
    content='memories',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category) VALUES ('delete', old.id, old.content, old.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category) VALUES ('delete', old.id, old.content, old.category);
    INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
END;
"""


def _word_overlap(a: str, b: str) -> float:
    """Return word overlap ratio between two strings (0-1)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


class MemoryStore(BaseMemory):
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        """Create DB and tables."""
        import os
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        for statement in SCHEMA.split(";"):
            stmt = statement.strip()
            if stmt:
                await self._db.execute(stmt)
        await self._db.commit()

    async def save(self, content: str, category: str = "fact") -> int:
        # Deduplicate: check for >80% similar existing entry
        async with self._db.execute(
            "SELECT id, content FROM memories WHERE category = ?", (category,)
        ) as cursor:
            async for row in cursor:
                if _word_overlap(content, row[1]) > 0.8:
                    await self._db.execute(
                        "UPDATE memories SET content = ?, updated_at = datetime('now') WHERE id = ?",
                        (content, row[0]),
                    )
                    await self._db.commit()
                    logger.info(f"Updated memory {row[0]} (deduplicated)")
                    return row[0]

        cursor = await self._db.execute(
            "INSERT INTO memories (content, category) VALUES (?, ?)",
            (content, category),
        )
        await self._db.commit()
        logger.info(f"Saved memory {cursor.lastrowid}")
        return cursor.lastrowid

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        # Sanitize query for FTS5
        words = query.split()
        if not words:
            return []
        fts_query = " OR ".join(f'"{w}"' for w in words)

        try:
            async with self._db.execute(
                """SELECT m.id, m.content, m.category, m.created_at, bm25(memories_fts) as rank
                   FROM memories_fts f
                   JOIN memories m ON f.rowid = m.id
                   WHERE memories_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    MemoryEntry(
                        id=r[0],
                        content=r[1],
                        category=r[2],
                        created_at=r[3],
                        relevance=abs(r[4]),
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"Search error: {e}")
            return []

    async def forget(self, memory_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def recent(self, limit: int = 20) -> list[MemoryEntry]:
        async with self._db.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                MemoryEntry(
                    id=r[0], content=r[1], category=r[2], created_at=r[3], relevance=1.0
                )
                for r in rows
            ]

    async def close(self):
        if self._db:
            await self._db.close()
