"""记忆库：把「物品 -> 位置」记下来，并支持覆盖更新。

改动来源（允许修改开源项目以满足适配性）：
  1. utkarshjosh/where-is-my-thing
       - spatial_memory_agent/agent.py       : remember_thing / find_thing / move_thing 三个工具的名字与返回结构
       - services/graph_service.py           : action = created / moved / no_change 的判定逻辑
       - services/memory_service.py         : 模糊语义检索（本项目用 difflib 代替向量库，零依赖）
     原本用 Neo4j 图谱 + Gemini 向量，家里只需要「一个物品一个位置」，
     所以这里改用 Python 自带的 SQLite 单表 + UPSERT，语义和返回结构保持一致。
  2. zaidwhy/recall
       - backend/memory.py                  : DECAY_WEIGHT=0.25 的时间衰减打分、日志式 history 追溯
       - backend/tools.py                  : "confident" 置信度门控思路
"""
from __future__ import annotations

import difflib
import json
import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

# 来自 zaidwhy/recall/backend/memory.py：score = distance + DECAY_WEIGHT * log(1 + hours_ago)
DECAY_WEIGHT = 0.25
# 模糊匹配的相似度下限，对应 recall 的 RECALL_MAX_DISTANCE 置信度门控
MIN_SIMILARITY = 0.60


def _time_penalty(timestamp: float) -> float:
    hours_ago = max(0.0, (time.time() - timestamp) / 3600)
    return DECAY_WEIGHT * math.log1p(hours_ago)


class MemoryStore:
    """物品位置记忆。线程不安全但单进程命令行足够用。"""

    def __init__(self, db_path: str | Path, aliases: Optional[dict] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        alias_cfg = aliases or {}
        self.aliases: dict[str, str] = alias_cfg.get("aliases", {})
        self.prompts: dict[str, list[str]] = alias_cfg.get("prompts", {})
        self._init_db()

    # ------------------------------------------------------------------ 基础设施
    @contextmanager
    def _connect(self):
        """每次调用都真正关闭连接。

        注意：`with sqlite3.connect(...)` 只负责提交/回滚事务，并不会 close()，
        在 Windows 上会让 .db 文件一直被占用（上游 zaidwhy/recall 也踩过这个坑）。
        这里包一层 contextmanager，退出时显式 close。
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # 提交 / 回滚
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    name       TEXT PRIMARY KEY,
                    location   TEXT NOT NULL,
                    source     TEXT NOT NULL DEFAULT 'user',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    hit_count  INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT NOT NULL,
                    old_location TEXT,
                    new_location TEXT NOT NULL,
                    action       TEXT NOT NULL,
                    source       TEXT NOT NULL,
                    ts           REAL NOT NULL
                );
                """
            )

    def normalize(self, name: str) -> str:
        """把「车钥匙」归一成「钥匙」；对应 where-is-my-thing 的 canonical resolution。"""
        name = (name or "").strip()
        return self.aliases.get(name, name)

    def prompts_for(self, item_name: str) -> list[str]:
        """给 YOLO-World 用的提示词列表，来自 FindForYou/custom_classes.json 的 classes[].prompts。"""
        key = self.normalize(item_name)
        return self.prompts.get(key, [key])

    # ------------------------------------------------------------------ 查询（流程第 3 步）
    def find_thing(self, query: str) -> dict:
        """按物品名找位置。返回结构与 where-is-my-thing/agent.py 的 find_thing 一致：
        {"query": str, "found": int, "items": [{"name": ..., "path": ...}]}
        """
        key = self.normalize((query or "").strip())
        if not key:
            return {"query": query, "found": 0, "items": []}

        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM items").fetchall()

        names = [r["name"] for r in rows]
        candidates: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            name = row["name"]
            # recall/backend/memory.py 的 find_by_object：精确名匹配优先
            if name == key or key in name or name in key:
                similarity = 1.0
            else:
                ratio = difflib.SequenceMatcher(None, key, name).ratio()
                similarity = ratio if ratio >= MIN_SIMILARITY else 0.0
            if similarity > 0:
                # 分数越小越好：借用 recall 的 distance + 时间衰减
                score = (1.0 - similarity) + _time_penalty(row["updated_at"])
                candidates.append((score, row))

        candidates.sort(key=lambda x: x[0])
        items = [
            {
                "name": r["name"],
                "path": r["location"],
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for _, r in candidates[:5]
        ]
        if items:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE items SET hit_count = hit_count + 1 WHERE name = ?",
                    (items[0]["name"],),
                )
        return {"query": query, "found": len(items), "items": items}

    # ------------------------------------------------------------------ 写入 / 更新（记忆流程第 2、4 步）
    def remember_thing(
        self,
        thing_name: str,
        location: str,
        source: str = "user",
        description: str | None = None,
    ) -> dict:
        """登记或更新物品位置。

        这是本项目最关键的改写：原版 graph_service.remember_thing 发现同名物品时
        会调用 move_thing 删除旧的 LOCATED_IN 关系再建新关系；这里用一条
        INSERT ... ON CONFLICT DO UPDATE 完成同样的事，并返回同样的 action 语义。

        action: created（新登记） / moved（位置变了，已覆盖） / no_change（位置没变）
        """
        name = self.normalize((thing_name or "").strip())
        loc = (location or "").strip()
        if not name or not loc:
            return {"ok": False, "error": "物品名或位置为空", "name": name, "path": loc}

        now = time.time()
        with self._connect() as conn:
            old = conn.execute("SELECT * FROM items WHERE name = ?", (name,)).fetchone()
            if old is None:
                conn.execute(
                    "INSERT INTO items (name, location, source, created_at, updated_at, hit_count)"
                    " VALUES (?, ?, ?, ?, ?, 0)",
                    (name, loc, source, now, now),
                )
                action, old_loc = "created", None
                message = f"已记住：{name}放在{loc}"
            elif old["location"] == loc:
                action, old_loc = "no_change", old["location"]
                conn.execute(
                    "UPDATE items SET updated_at = ?, source = ? WHERE name = ?",
                    (now, source, name),
                )
                message = f"{name}本来就在{loc}，位置没变"
            else:
                action, old_loc = "moved", old["location"]
                conn.execute(
                    "UPDATE items SET location = ?, source = ?, updated_at = ? WHERE name = ?",
                    (loc, source, now, name),
                )
                message = f"已更新：{name}从{old_loc}改到{loc}"

            conn.execute(
                "INSERT INTO history (name, old_location, new_location, action, source, ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (name, old_loc, loc, action, source, now),
            )

        return {
            "ok": True,
            "action": action,
            "name": name,
            "path": loc,
            "old_location": old_loc,
            "source": source,
            "message": message,
        }

    def move_thing(self, thing_name: str, new_location: str, source: str = "user") -> dict:
        """与 where-is-my-thing/agent.py 的 move_thing 同名同义，内部走同一个 upsert。"""
        return self.remember_thing(thing_name, new_location, source=source)

    # ------------------------------------------------------------------ 管理工具
    def list_contents(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, location, source, updated_at FROM items ORDER BY updated_at DESC"
            ).fetchall()
        items = [{"name": r["name"], "path": r["location"], "source": r["source"]} for r in rows]
        return {"count": len(items), "items": items}

    def history(self, name: str | None = None, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            if name:
                rows = conn.execute(
                    "SELECT * FROM history WHERE name = ? ORDER BY ts DESC LIMIT ?",
                    (self.normalize(name), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM history ORDER BY ts DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_thing(self, thing_name: str) -> bool:
        name = self.normalize(thing_name)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM items WHERE name = ?", (name,))
            return cur.rowcount > 0

    def clear_all(self) -> int:
        """记忆刷新重置：清空全部位置记录（history 保留，可追溯）。"""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
            conn.execute("DELETE FROM items")
        return int(count)


def load_aliases(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"aliases": {}, "prompts": {}}
    return json.loads(p.read_text(encoding="utf-8"))
