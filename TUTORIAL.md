# 从零做出 findmy —— 一步步复制粘贴教程

> 这份教程对应你写的两套流程。所有代码**已经写好并在本地跑通**：
> `python -m unittest discover -s tests -v` → 10/10 通过；`python -m findmy.cli --demo` → 完整对话输出正确。
>
> 你只需要按顺序：**在指定位置新建文件 → 把整段代码复制粘贴进去**。
> 每节都会先告诉你「这一步用了上游哪个开源项目的哪个文件、哪一段」，再给代码。

---

## 第 0 步：先把你的流程读成状态机

**查找流程**

```
1 用户询问某项物品位置        「我的钥匙在哪」
2 语音识别物品                → 文字「我的钥匙在哪」→ 抽出物品「钥匙」
3 先从记忆库里查找            → 命中：鞋柜上
4 输出语音「你之前说放在某某位置，是否在那？」
5 ├─ 找到了 → 任务结束
  └─ 用户告知现在不在
     6 接入摄像头并寻找物品
     7 找到物品并告知用户在哪里
```

**记忆流程**

```
1 用户告知某物品放在某位置    「钥匙放在鞋柜上」
2 语音识别并记住              action = created
3 用户告知某物品被放进某新位置 「钥匙被放进抽屉里」
4 更改记忆                    action = moved（旧位置进 history）
```

翻译成程序就是 **3 个状态 + 5 个动作**：

| 状态 | 含义 | 什么时候进入 |
|---|---|---|
| `IDLE` | 空闲，等「查询」或「登记」 | 初始 / 任务结束 |
| `AWAIT_CONFIRM` | 刚说完第 4 步，等「找到了」/「现在不在」 | 记忆库命中后 |
| `AWAIT_VISION_YES` | 记忆库没记录，等用户同意开摄像头 | 查无此物（补全 A） |

| 动作 | 对应流程步 | 代码 |
|---|---|---|
| `speech.listen()` | 查找 1、记忆 1/3 | `findmy/speech.py` |
| `nlu.parse()` | 查找 2、记忆 2 | `findmy/nlu.py` |
| `memory.find_thing()` | 查找 3 | `findmy/memory.py` |
| `speech.say()` | 查找 4、7 | `findmy/speech.py` |
| `vision.find()` | 查找 6 | `findmy/vision.py` |
| `memory.remember_thing()` | **仅**记忆 2/4（用户主动口述） | `findmy/memory.py` |

**原流程有一处空白，我做了补全，可一键关掉：**

- **补全 A**：记忆库里压根没这个物品时，原流程没写走哪条路 → 先问「要我现在开摄像头帮你找找吗？」。
  开关 `config/settings.json → behavior.ask_before_camera_search`。

**一条硬规则：摄像头找到物品后只播报位置，绝不写回记忆库。**

摄像头目击是「它此刻出现在哪」，不是用户认定的固定存放位置；写进去会污染下次查询的答案，
也会让库里堆满一次性目击记录。记忆库**只接受用户主动口述**的登记与更改（记忆流程 1–4）。
所以这里没有任何「自动写回」开关，`_search_by_camera()` 里也不会调用 `remember_thing()`。

状态机全部集中在 **`findmy/engine.py`** 一个文件里，第 3.9 节会逐段讲。

---

## 第 1 步：去上游哪个仓库、哪个文件找什么

**先克隆三个上游项目当参考**（只是看，不用改它们，也不放进你的仓库）：

```bash
mkdir refs && cd refs
git clone --depth 1 https://github.com/utkarshjosh/where-is-my-thing.git
git clone --depth 1 https://github.com/zaidwhy/recall.git
git clone --depth 1 https://github.com/happy-capybara-man/FindForYou.git
cd ..
```

> `zaidwhy/recall` 的默认分支是 `master`，另外两个是 `main`。
> 不想克隆也行，直接看在线文件：
> [agent.py](https://github.com/utkarshjosh/where-is-my-thing/blob/main/spatial_memory_agent/agent.py) ·
> [graph_service.py](https://github.com/utkarshjosh/where-is-my-thing/blob/main/services/graph_service.py) ·
> [memory_service.py](https://github.com/utkarshjosh/where-is-my-thing/blob/main/services/memory_service.py) ·
> [recall/backend/memory.py](https://github.com/zaidwhy/recall/blob/master/backend/memory.py) ·
> [recall/backend/tools.py](https://github.com/zaidwhy/recall/blob/master/backend/tools.py) ·
> [FindForYou/backend/detector.py](https://github.com/happy-capybara-man/FindForYou/blob/main/backend/detector.py) ·
> [camera_config.json](https://github.com/happy-capybara-man/FindForYou/blob/main/backend/camera_config.json) ·
> [custom_classes.json](https://github.com/happy-capybara-man/FindForYou/blob/main/backend/custom_classes.json) ·
> [FindForYou/backend/main.py](https://github.com/happy-capybara-man/FindForYou/blob/main/backend/main.py)

### 逐个文件对照表（照着搜关键字，就能看懂我们要改的是哪一段）

| 想看的东西 | 打开哪个文件 | 在里面搜 | 用在我们哪个文件 |
|---|---|---|---|
| 记忆工具的接口长什么样 | `refs/where-is-my-thing/spatial_memory_agent/agent.py` | `def remember_thing`、`def find_thing`、`def move_thing`、`list_contents`、`AGENT_INSTRUCTION` | `findmy/memory.py`、`findmy/nlu.py` |
| 同名物品换位置怎么覆盖 | `refs/where-is-my-thing/services/graph_service.py` | `"moved"`、`action`、`LOCATED_IN` | `findmy/memory.py::remember_thing` |
| 别名 / 模糊语义检索 | `refs/where-is-my-thing/services/memory_service.py` | `canonical_similarity_search`、`min_score` | `findmy/memory.py::find_thing` |
| 新记忆盖过旧记忆 | `refs/recall/backend/memory.py` | `DECAY_WEIGHT`、`log1p`、`RECALL_MAX_DISTANCE`、60 秒去重 | `findmy/memory.py::_time_penalty` |
| 「查到才回答」的工具行为 | `refs/recall/backend/tools.py` | `def recall_memory` | `findmy/engine.py::_query` |
| YOLO-World 开放词汇检测 | `refs/FindForYou/backend/detector.py` | `_init_model`、`set_classes`、`_update_model_classes`、`_detect_frame`、`_get_surface_region`、`_get_mock_detections` | `findmy/vision.py` |
| **摄像头 = 位置** 的巧思 | `refs/FindForYou/backend/camera_config.json` | `location` | `config/cameras.json` |
| 一个物品多个英文提示词 | `refs/FindForYou/backend/custom_classes.json` | `classes[].id`、`classes[].prompts` | `config/aliases.json` |
| 检测结果附上位置 | `refs/FindForYou/backend/main.py` | `trigger_snapshot`、`broadcast_detection` | `findmy/vision.py::Sighting` |
| 中文「在 / 放在」拆句 | [fantasyao/shengwuji](https://github.com/fantasyao/shengwuji) 的 README | 「钥匙在鞋柜上」 | `findmy/nlu.py` |

### 流程每一步 → 上游段落 → 本项目函数（速查）

| 流程步 | 上游 | 上游具体段落 | 本项目 |
|---|---|---|---|
| 查找 1 语音输入 | faster-whisper | `WhisperModel(...).transcribe(...)` | `speech.py::VoiceSpeech.listen` |
| 查找 2 抽出物品 | where-is-my-thing / 声物记 | `AGENT_INSTRUCTION` 工具分派 / 中文拆句 | `nlu.py::parse` |
| 查找 3 查记忆 | where-is-my-thing + recall | `find_thing` / `canonical_similarity_search` / `find_by_object` + 时间衰减 | `memory.py::find_thing` |
| 查找 4 语音反问 | piper1-gpl | `synthesize_wav` | `speech.py::say` + `engine.py::_query` |
| 查找 5 找到了 | 声物记 | 短反馈词表 | `nlu.py::FOUND_WORDS` + `engine.py::handle` |
| 查找 5' 现在不在 | 声物记 | 「撤销/不对」否定词 | `nlu.py::NEG_WORDS`（**先判否定**） |
| 查找 6 摄像头 | FindForYou | `detector.py` 全套 + `main.py::trigger_snapshot` | `vision.py::CameraFinder.find` |
| 查找 7 告知位置 | FindForYou | `camera_config.json::location` + `_get_surface_region` | `vision.py::Sighting` + `engine.py::_search_by_camera` |
| 记忆 1/3 口述 | 声物记 | 「放在 / 在」 | `nlu.py::PLACE_VERBS` |
| 记忆 2 记住 | where-is-my-thing | `remember_thing` | `memory.py::remember_thing` → `created` |
| 记忆 4 更改 | where-is-my-thing + recall | `graph_service` 删旧关系 / 60 秒原地更新 | `memory.py::remember_thing` → `moved` + `history` |

### 为什么是这三家拼，而不是直接用某一个

| 项目 | 记忆增删改 | 摄像头 | 口述登记 | 结论 |
|---|---|---|---|---|
| `where-is-my-thing` | ✅ 最完整 | ❌ | ✅ | **当记忆骨架** |
| `happy-capybara-man/FindForYou` | ❌ | ✅ 且摄像头绑定位置 | ❌ | **当眼睛** |
| `zaidwhy/recall` | ✅ 但只来自摄像头 | ✅ | ❌ | **借时间衰减与置信度门控** |
| `fantasyao/shengwuji` | ✅ 但同名追加而非覆盖 | ❌ | ✅ 中文离线 | **借中文句式** |

四家全都是 MIT / Apache-2.0，允许修改后自行开源。语音用 faster-whisper + Piper，全本地零费用。

---

## 第 2 步：建目录

在你想放项目的位置执行（Windows 用 PowerShell / Git Bash 都行）：

```bash
mkdir -p findmy/findmy findmy/config findmy/tests findmy/data
cd findmy
```

最终目录长这样：

```
findmy/
├── config/          settings.json / cameras.json / aliases.json
├── findmy/          __init__.py / memory.py / nlu.py / speech.py / vision.py / engine.py / cli.py
├── tests/           test_flow.py
├── data/            memory.db（运行时自动生成）
├── requirements.txt
├── LICENSE
├── .gitignore
├── README.md
└── THIRD_PARTY_NOTICES.md
```

Python 版本要求 **3.10+**（用了 `str | Path` 类型写法）。看一下版本：

```bash
python --version
```

---

## 第 3 步：逐个文件建好，整段粘贴代码

> 下面 12 个小节，每一节 = 一个文件 = 一次「新建 + 全选复制粘贴」。
> 顺序无所谓，但建议按 3.1 → 3.12 来，能边建边理解。

---

### 3.1 `config/settings.json` — 总开关

**上游来源**：无（本项目新增）。把三个上游项目散落在环境变量里的配置项收拢到一起。

**关键字段**：`vision.mock=true` 表示不装任何依赖也能跑模拟摄像头；`behavior` 里的开关对应第 0 步的补全 A。
注意 `behavior` 里**没有**「摄像头找到后自动写回记忆」的开关 —— 那条是硬规则，不做成可选项。

**新建 `config/settings.json`，粘贴：**

```json
{
  "stt": {
    "engine": "faster-whisper",
    "model": "small",
    "language": "zh",
    "device": "cpu",
    "compute_type": "int8",
    "record_seconds": 5,
    "sample_rate": 16000
  },
  "tts": {
    "engine": "auto",
    "piper_model": "",
    "fallback": "pyttsx3"
  },
  "vision": {
    "model": "yolov8s-worldv2.pt",
    "conf_threshold": 0.25,
    "frames_per_camera": 3,
    "mock": true
  },
  "memory": {
    "db_path": "data/memory.db"
  },
  "behavior": {
    "_note": "摄像头找到物品后只播报位置，不写回记忆库；记忆只由用户主动口述写入",
    "ask_before_camera_search": true
  }
}
```

---

### 3.2 `config/cameras.json` — 摄像头 ↔ 位置

**上游来源**：`refs/FindForYou/backend/camera_config.json`。
照搬它的 `name` / `location` / `enabled` 三字段，新增了 `source`（OpenCV 设备号或 RTSP 地址）和 `mock_detections`（无摄像头时的模拟结果）。

**这是回答流程第 7 步「告知用户在哪里」的关键**：不需要 3D 建图，哪个摄像头看到 = 在哪个位置。
`location` 请一定填成那个摄像头实际拍到的家具/区域。

**新建 `config/cameras.json`，粘贴：**

```json
{
  "_source": "照搬 happy-capybara-man/FindForYou/backend/camera_config.json 的结构：name / location / enabled；新增 source（OpenCV 设备号或 RTSP 地址）",
  "cameras": {
    "0": {
      "name": "客厅摄像头",
      "location": "客厅电视柜",
      "enabled": true,
      "source": 0
    },
    "1": {
      "name": "卧室摄像头",
      "location": "卧室床头柜",
      "enabled": true,
      "source": 1
    },
    "2": {
      "name": "玄关摄像头",
      "location": "玄关鞋柜",
      "enabled": true,
      "source": "rtsp://admin:password@192.168.1.50/stream1"
    }
  },
  "default_camera": 0,
  "_mock_note": "vision.mock=true 时不会真的开摄像头，而是从这里读取模拟检测结果，方便先跑通流程",
  "mock_detections": {
    "钥匙": {"camera_id": "0", "confidence": 0.87, "region": "left"},
    "眼镜": {"camera_id": "1", "confidence": 0.79, "region": "center"},
    "遥控器": {"camera_id": "0", "confidence": 0.91, "region": "right"},
    "手机": {"camera_id": "2", "confidence": 0.83, "region": "left"}
  }
}
```

---

### 3.3 `config/aliases.json` — 别名归一 + 检测提示词

**上游来源**：
- `refs/FindForYou/backend/custom_classes.json` 的 `classes[].id` + `classes[].prompts`（一个物品给多个英文提示词）→ 这里的 `prompts`；
- `refs/where-is-my-thing/services/memory_service.py::canonical_similarity_search` 的别名归一思路 → 这里的 `aliases`。

效果：说「车钥匙」「门钥匙」「钥匙串」都会归一成同一条记录 `钥匙`；找钥匙时 YOLO-World 会用 `keys / a bunch of keys / key / 钥匙` 四个提示词。**新物品往这两个表里各加一行即可，不用改代码。**

**新建 `config/aliases.json`，粘贴：**

```json
{
  "_source": "prompts 结构照搬 happy-capybara-man/FindForYou/backend/custom_classes.json 的 classes[].id + classes[].prompts 多提示词映射，中文物品名 -> YOLO-World 英文提示词",
  "aliases": {
    "钥匙串": "钥匙",
    "车钥匙": "钥匙",
    "门钥匙": "钥匙",
    "锁匙": "钥匙",
    "手机": "手机",
    "电话": "手机",
    "移动电话": "手机",
    "遥控": "遥控器",
    "电视遥控器": "遥控器",
    "皮夹": "钱包",
    "钱夹": "钱包",
    "老花镜": "眼镜"
  },
  "prompts": {
    "钥匙": ["keys", "a bunch of keys", "key", "钥匙"],
    "手机": ["cell phone", "mobile phone", "phone", "手机"],
    "钱包": ["wallet", "purse", "钱包"],
    "遥控器": ["remote control", "TV remote", "遥控器"],
    "眼镜": ["glasses", "eyeglasses", "spectacles", "眼镜"],
    "杯子": ["cup", "mug", "杯子"],
    "耳机": ["headphones", "earbuds", "耳机"],
    "书": ["book", "书"],
    "雨伞": ["umbrella", "雨伞"],
    "充电器": ["phone charger", "charging cable", "充电器"]
  }
}
```

---

### 3.4 `findmy/__init__.py` — 包说明

**新建 `findmy/__init__.py`，粘贴：**

```python
"""findmy - 家用「找东西」语音助手。

拼接自以下免费开源项目（详见 README.md）：
  - utkarshjosh/where-is-my-thing  -> 记忆语义（remember_thing / find_thing / move_thing / action）
  - zaidwhy/recall                 -> 时间衰减、置信度门控、去重刷新
  - happy-capybara-man/FindForYou  -> YOLO-World 开放词汇检测、摄像头位置映射
  - SYSTRAN/faster-whisper         -> 本地语音识别
  - OHF-Voice/piper1-gpl           -> 本地语音合成
"""

__version__ = "0.1.0"
```

---

### 3.5 `findmy/memory.py` — 记忆库（查找 3 / 记忆 2、4）

**上游来源与改动**（本项目最核心的改写）：

| 上游 | 具体段落 | 我们改成 |
|---|---|---|
| `where-is-my-thing/spatial_memory_agent/agent.py` | `remember_thing` / `find_thing` / `move_thing` / `list_contents` 的函数名与返回结构 `{"query","found","items":[{"name","path"}]}` | **名字和返回结构保持不变**，方便你以后换回原版 |
| `where-is-my-thing/services/graph_service.py` | 同名物品再登记 → 删旧 `LOCATED_IN` 关系、建新关系，`action = created/moved/no_change` | 一条 SQLite UPSERT 完成同样语义，旧位置写进 `history` 表 |
| `where-is-my-thing/services/memory_service.py` | `canonical_similarity_search(min_score=0.5)` 向量模糊检索 | `difflib.SequenceMatcher` + `MIN_SIMILARITY=0.60`，零依赖 |
| `recall/backend/memory.py` | `DECAY_WEIGHT=0.25`、`score = distance + 0.25*log(1+hours_ago)` | `_time_penalty()`，让新位置自动盖过旧位置 |
| `recall/backend/memory.py` | `RECALL_MAX_DISTANCE` 置信度门控 | `MIN_SIMILARITY` |
| `recall/backend/tools.py` | `recall_memory` 查不到就明说 | `find_thing` 返回 `found=0` |

**这里也有一个真实踩过的坑**：`with sqlite3.connect(...)` 只提交事务、**不会关闭连接**，Windows 上会让 `.db` 文件一直被占用（recall 的注释里也提到过）。所以 `_connect()` 用 `@contextmanager` 包了一层，退出时显式 `conn.close()`。

**新建 `findmy/memory.py`，粘贴：**

```python
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
```

---

### 3.6 `findmy/nlu.py` — 中文意图与物品/位置抽取（查找 2、5、5' / 记忆 1、3）

**上游来源**：
- `refs/where-is-my-thing/spatial_memory_agent/agent.py` 的 `AGENT_INSTRUCTION`：把一句话映射成 `remember_thing / find_thing / move_thing` 三个工具调用。本项目**不接 LLM**（省钱、离线、延迟低），改成规则解析，但输出同样是结构化意图；
- `fantasyao/shengwuji` 的中文句式：「钥匙在鞋柜上」「钥匙放在鞋柜上」→ 拆成「物品—位置」，`PLACE_VERBS` / `LOCATION_HINTS` 就是这么来的，另扩了「被放进 / 挪到 / 换到」等**更新位置**的句式；
- 声物记的「撤销 / 这条不对」→ `NEG_WORDS` 短否定反馈。

**一个必须注意的顺序**：`nlu.py::parse` 里在 `AWAIT_CONFIRM` 状态**先判否定再判肯定**，否则「不在这儿」含有「在这儿」，会被误判成「找到了」，流程就走错了。

**新建 `findmy/nlu.py`，粘贴：**

```python
"""中文意图识别：把用户说的话拆成「意图 + 物品 + 位置」。

来源：
  - fantasyao/shengwuji（声物记）用「在 / 放在」关键字拆出「物品—位置」，本项目把这套
    中文句式规则抽出来做成纯 Python 实现，不依赖 Android。
  - utkarshjosh/where-is-my-thing/spatial_memory_agent/agent.py 的 AGENT_INSTRUCTION：
    把自然语言映射成 remember_thing / find_thing / move_thing 三个工具调用。
    本项目不接 LLM（省钱、离线、延迟低），改用规则解析器，输出同样的结构化意图。

支持的用户话术（对应你写的流程）：
  查询：我的钥匙在哪 / 钥匙放哪儿了 / 找不到眼镜 / 遥控器呢
  登记：钥匙放在鞋柜上 / 我把钥匙放在鞋柜上
  更新：钥匙被放进抽屉里 / 把钥匙挪到书桌上
  否定：现在不在 / 没找到 / 不在这儿
  确认：找到了 / 在的 / 就在这儿
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    QUERY = "query"            # 流程1：询问物品位置
    REMEMBER = "remember"      # 记忆流程1/3：告知（新）位置
    NOT_FOUND = "not_found"    # 流程5：第4步之后没找到
    FOUND = "found"            # 流程5：找到了，任务结束
    YES = "yes"                # 同意开摄像头
    NO = "no"                  # 不同意开摄像头
    EXIT = "exit"
    UNKNOWN = "unknown"


@dataclass
class Parsed:
    intent: Intent
    item: str = ""
    location: str = ""
    raw: str = ""

    def __repr__(self) -> str:
        return f"Parsed({self.intent.value}, item={self.item!r}, location={self.location!r})"


# ---------------------------------------------------------------- 词表
QUERY_TAILS = [
    "在哪儿", "在哪里", "在哪", "放哪儿", "放哪里", "放哪了", "放哪",
    "搁哪儿", "搁哪", "去哪儿了", "去哪了", "哪去了", "丢哪了", "在哪边",
    "找不到了", "不见了", "找不着了",
]
PLACE_VERBS = sorted(
    [
        "放在", "放到了", "放进", "放到", "搁在", "搁到", "收在", "收进", "收到",
        "塞进", "塞在", "存在", "存到", "摆在", "挂到", "挂在", "装进", "装到",
        "被放在", "被放进", "被放到", "挪到", "挪进", "移到", "移进", "换到",
        "放回了", "放回", "放到", "记到",
    ],
    key=len,
    reverse=True,
)
FOUND_WORDS = ["找到了", "找着了", "就在这", "在这儿", "在的", "找到了谢谢", "嗯找到了", "对找到了"]
NEG_WORDS = ["不在", "没找到", "没找着", "没看见", "没有啊", "还是没有", "没在那", "没找见", "没有找到", "不在这儿", "不在那儿"]
YES_WORDS = ["要", "好", "好的", "开吧", "找吧", "可以", "行", "嗯", "开摄像头", "找一下", "帮我找"]
NO_WORDS = ["不要", "不用", "算了", "不用了", "不用找", "别找", "取消"]
EXIT_WORDS = ["退出", "拜拜", "结束", "不说了", "quit", "exit"]

# 位置词，用来兜底识别「牙刷在厨房小推车」这种只有「在」的句式
LOCATION_HINTS = (
    "上", "下", "里", "中", "旁", "边", "柜", "桌", "箱", "抽屉", "包", "袋",
    "架", "角", "处", "房", "间", "台", "盒", "篮", "筐", "门", "墙", "床",
    "沙发", "书架", "鞋柜", "冰箱", "厨房", "卧室", "客厅", "阳台", "卫生间",
    "玄关", "储藏", "柜子", "盒子", "篮子", "口袋", "抽屉", "茶几", "书桌",
)

ITEM_PREFIXES = ["我把", "把", "我", "我的", "我那", "那个", "这", "请问", "帮我找找", "帮我找一下", "帮我找", "请记住", "记住", "麻烦你"]
TAIL_JUNK = "了|吧|啊|呀|呢|吗|哦|嘛|哈|。|？|？|\\?|，|,|\\s+"

_PUNCT = str.maketrans({
    "，": "", "。": "", "？": "", "！": "", "、": "", "：": "", "；": "",
    ",": "", ".": "", "?": "", "!": "", " ": "", "\t": "",
})


def _clean(text: str) -> str:
    return (text or "").strip().translate(_PUNCT)


def _strip_item_prefix(item: str) -> str:
    changed = True
    while changed and item:
        changed = False
        for p in sorted(ITEM_PREFIXES, key=len, reverse=True):
            if item.startswith(p) and len(item) > len(p):
                item = item[len(p):]
                changed = True
                break
    return item.strip()


def _strip_tail(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(f"(?:{TAIL_JUNK})+$", "", s).strip()
    return s


def _strip_location(s: str) -> str:
    s = _strip_tail(s)
    s = re.sub(r"^(?:现在|目前|已经|就|一直|刚才)", "", s).strip()
    s = re.sub(r"^(?:放到|放在|搁在|在)", "", s).strip()
    return _strip_tail(s)


def parse(utterance: str, state: str = "IDLE") -> Parsed:
    """把一句话解析成结构化意图。

    state 用于消歧：在 AWAIT_CONFIRM（刚问完「是否在那」）时，
    短否定/肯定句优先当成流程第 5 步的反馈，而不是新的查询或登记。
    """
    raw = utterance or ""
    t = _clean(raw)
    if not t:
        return Parsed(Intent.UNKNOWN, raw=raw)

    if any(w in t for w in EXIT_WORDS) and len(t) <= 6:
        return Parsed(Intent.EXIT, raw=raw)

    # ---- 流程5：等待「是否在那」的回答时，先判短反馈 ----
    # 顺序很重要：「不在这儿」里含「在这儿」，必须先判否定，否则会被误判成「找到了」
    if state == "AWAIT_CONFIRM":
        if any(w in t for w in NEG_WORDS) and len(t) <= 12:
            return Parsed(Intent.NOT_FOUND, raw=raw)
        if any(w in t for w in FOUND_WORDS) and len(t) <= 10 and not any(n in t for n in NEG_WORDS):
            return Parsed(Intent.FOUND, raw=raw)
        if t in ("对", "是的", "嗯", "在"):
            return Parsed(Intent.FOUND, raw=raw)

    if state == "AWAIT_VISION_YES":
        if any(t == w or t.startswith(w) for w in NO_WORDS):
            return Parsed(Intent.NO, raw=raw)
        if any(t == w or t.startswith(w) for w in YES_WORDS):
            return Parsed(Intent.YES, raw=raw)

    # ---- 通用短反馈 ----
    if t in NO_WORDS:
        return Parsed(Intent.NO, raw=raw)
    if t in YES_WORDS:
        return Parsed(Intent.YES, raw=raw)
    if len(t) <= 10 and any(w in t for w in NEG_WORDS) and not any(v in t for v in ("在哪", "哪", "找不到")):
        return Parsed(Intent.NOT_FOUND, raw=raw)

    # ---- 流程1：查询句式 ----
    for pat in (r"^(?:请问)?(?:帮我)?找不到(.+)$", r"^(?:请问)?(?:帮我)?找不着(.+)$"):
        m = re.match(pat, t)
        if m:
            return Parsed(Intent.QUERY, item=_strip_item_prefix(_strip_tail(m.group(1))), raw=raw)

    tails = "|".join(re.escape(x) for x in sorted(QUERY_TAILS, key=len, reverse=True))
    m = re.match(rf"^(.+?)(?:{tails})(?:了|呢|啊|呀|吗)*$", t)
    if m:
        item = _strip_item_prefix(_strip_tail(m.group(1)))
        if item:
            return Parsed(Intent.QUERY, item=item, raw=raw)

    # 「钥匙呢」/「遥控器不见了」
    m = re.match(r"^(.+?)呢$", t)
    if m and len(m.group(1)) <= 12:
        return Parsed(Intent.QUERY, item=_strip_item_prefix(_strip_tail(m.group(1))), raw=raw)

    # ---- 记忆流程1/3：告知位置 ----
    verbs = "|".join(re.escape(v) for v in PLACE_VERBS)
    m = re.search(rf"(?:被)?(?:{verbs})(.+)$", t)
    if m:
        item = _strip_item_prefix(_strip_tail(t[: m.start()]))
        location = _strip_location(m.group(1))
        if item and location:
            return Parsed(Intent.REMEMBER, item=item, location=location, raw=raw)

    # 兜底：「牙刷在厨房小推车」（声物记的「在」句式）
    m = re.match(r"^(.+?)在(.+)$", t)
    if m:
        item = _strip_item_prefix(_strip_tail(m.group(1)))
        location = _strip_location(m.group(2))
        if item and location and any(h in location for h in LOCATION_HINTS):
            return Parsed(Intent.REMEMBER, item=item, location=location, raw=raw)

    return Parsed(Intent.UNKNOWN, raw=raw)
```

---

### 3.7 `findmy/speech.py` — 语音识别 + 语音合成（查找 1、4、7）

**上游来源**：
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)（MIT）：`WhisperModel(model, device=..., compute_type=...)` 与 `model.transcribe(wav, language="zh", vad_filter=True)`；
- [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)（GPL-3.0）：`PiperVoice.load(...).synthesize_wav(text, wav_file)`；原 `rhasspy/piper`（MIT）已归档；
- [home-assistant/app-whisper](https://github.com/home-assistant/app-whisper) / [app-piper](https://github.com/home-assistant/app-piper) 可当独立 Wyoming 服务替代；
- 中文识别想更准可换 [fantasyao/shengwuji](https://github.com/fantasyao/shengwuji) 的 sherpa-onnx + SenseVoice 方案。

**设计要点**：所有第三方库**懒加载**。没装、没麦克风、没中文模型时逐级降级（Piper → pyttsx3 → 只打印文字），程序永远能跑，不会一上来就报错。

**新建 `findmy/speech.py`，粘贴：**

```python
"""语音输入输出：本地语音识别(STT) + 本地语音合成(TTS)，全部可离线、免费。

来源：
  - SYSTRAN/faster-whisper        : WhisperModel(...).transcribe(...) 做语音转文字
  - OHF-Voice/piper1-gpl          : PiperVoice.load(...).synthesize_wav(...) 做文字转语音
    （原 rhasspy/piper 已归档，MIT；新仓库为 GPL-3.0，详见 README 许可证一节）
  - home-assistant/app-whisper / app-piper : 官方 Wyoming 语音插件，可选替代方案
  - fantasyao/shengwuji           : 中文离线方案 sherpa-onnx + SenseVoice，想换更准的中文识别可看它

设计要点：所有第三方库都懒加载。没装、没麦克风、没中文语音模型时自动降级，
保证程序永远能跑（打字模拟 -> 只打印文字），不会一上来就报错劝退。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional


class BaseSpeech:
    def listen(self) -> str:
        raise NotImplementedError

    def say(self, text: str) -> None:
        raise NotImplementedError


class TextSpeech(BaseSpeech):
    """打字模拟语音。用于 --text / --demo 和自动化测试，零依赖。"""

    def __init__(self, script: Optional[list[str]] = None, echo: bool = True):
        self.script = list(script or [])
        self.spoken: list[str] = []
        self.echo = echo

    def listen(self) -> str:
        if self.script:
            return self.script.pop(0)
        return input("[你说] ").strip()

    def say(self, text: str) -> None:
        self.spoken.append(text)
        if self.echo:
            print(f"[助手] {text}")


class VoiceSpeech(BaseSpeech):
    """真实麦克风 + 扬声器。缺少依赖时逐级降级。"""

    def __init__(self, settings: dict, echo: bool = True):
        stt = settings.get("stt", {})
        tts = settings.get("tts", {})
        self.model_name = stt.get("model", "small")
        self.language = stt.get("language", "zh")
        self.device = stt.get("device", "cpu")
        self.compute_type = stt.get("compute_type", "int8")
        self.record_seconds = float(stt.get("record_seconds", 5))
        self.sample_rate = int(stt.get("sample_rate", 16000))
        self.piper_model = tts.get("piper_model", "")
        self.engine = tts.get("engine", "auto")
        self.echo = echo
        self._stt = None
        self._piper = None
        self._pyttsx3 = None
        self.warnings: list[str] = []

    # ------------------------------------------------------------ STT（流程第 2 步）
    def _ensure_stt(self):
        if self._stt is not None:
            return self._stt
        try:
            from faster_whisper import WhisperModel
            self._stt = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        except Exception as exc:
            self.warnings.append(
                f"语音识别不可用（{exc}）。请执行 pip install faster-whisper，"
                f"或改用 --text 打字模式。"
            )
            self._stt = False
        return self._stt

    def _record_wav(self) -> str:
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError(f"缺少录音依赖 sounddevice：{exc}；请 pip install sounddevice") from exc

        frames = int(self.record_seconds * self.sample_rate)
        print(f"[录音] 请说话（{self.record_seconds} 秒）...")
        audio = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="int16")
        sd.wait()
        tmp = os.path.join(tempfile.gettempdir(), f"findmy_{os.getpid()}.wav")
        with wave.open(tmp, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(self.sample_rate)
            f.writeframes(np.asarray(audio, dtype=np.int16).tobytes())
        return tmp

    def listen(self) -> str:
        model = self._ensure_stt()
        if not model:
            return input("[你说，语音识别未启用，请打字] ").strip()
        wav_path = self._record_wav()
        try:
            segments, _info = model.transcribe(
                wav_path,
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )
            text = "".join(seg.text for seg in segments).strip()
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        if self.echo:
            print(f"[识别] {text}")
        return text

    # ------------------------------------------------------------ TTS（流程第 4、7 步）
    def _ensure_piper(self):
        if self._piper is not None:
            return self._piper
        if not self.piper_model or not Path(self.piper_model).exists():
            self._piper = False
            return False
        try:
            from piper import PiperVoice
            self._piper = PiperVoice.load(self.piper_model)
        except Exception as exc:
            self.warnings.append(f"Piper 语音模型加载失败（{exc}），将改用备用朗读引擎。")
            self._piper = False
        return self._piper

    @staticmethod
    def _play_wav(path: str) -> bool:
        # Windows 用标准库 winsound，同步播放，保证说完才继续对话
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                return True
            except Exception:
                pass
        for cmd in (["afplay", path], ["aplay", "-q", path], ["paplay", path]):
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
        try:
            import numpy as np
            import sounddevice as sd
            with wave.open(path, "rb") as f:
                data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
                sd.play(data, samplerate=f.getframerate())
                sd.wait()
            return True
        except Exception:
            return False

    def _say_piper(self, text: str) -> bool:
        voice = self._ensure_piper()
        if not voice:
            return False
        tmp = os.path.join(tempfile.gettempdir(), f"findmy_say_{os.getpid()}.wav")
        try:
            with wave.open(tmp, "wb") as f:
                if hasattr(voice, "synthesize_wav"):
                    voice.synthesize_wav(text, f)
                else:
                    voice.synthesize(text, f)
            return self._play_wav(tmp)
        except Exception as exc:
            self.warnings.append(f"Piper 合成失败（{exc}），将改用备用朗读引擎。")
            return False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _say_pyttsx3(self, text: str) -> bool:
        try:
            import pyttsx3
            if self._pyttsx3 is None:
                self._pyttsx3 = pyttsx3.init()
            self._pyttsx3.say(text)
            self._pyttsx3.runAndWait()
            return True
        except Exception:
            return False

    def say(self, text: str) -> None:
        if self.echo:
            print(f"[助手] {text}")
        # engine=print 时只打印；auto 时依次尝试 Piper -> pyttsx3 -> 只打印
        if self.engine == "print":
            return
        if self.engine in ("auto", "piper") and self._say_piper(text):
            return
        if self.engine in ("auto", "pyttsx3") and self._say_pyttsx3(text):
            return
        # 静默降级：文字已经打印出来了，程序继续跑


def build_speech(settings: dict, voice: bool = False, script: Optional[list[str]] = None,
                 echo: bool = True) -> BaseSpeech:
    if not voice:
        return TextSpeech(script=script, echo=echo)
    return VoiceSpeech(settings, echo=echo)
```

---

### 3.8 `findmy/vision.py` — 摄像头寻找（查找 6、7）

**上游来源**（逐函数对应 `refs/FindForYou/backend/detector.py`）：

| 上游函数 | 本项目 | 说明 |
|---|---|---|
| `ObjectDetector._init_model` | `_ensure_model` | 加载 `YOLOWorld` 开放词汇模型，缺依赖自动转模拟模式 |
| `set_classes` / `_update_model_classes` | `_set_prompts` | 每次只把「当前要找的物品」的提示词设给模型 |
| `_detect_frame` 遍历 `r.boxes.xyxy / conf / cls` | `_detect_frame` | 精简成只取最高置信度的那个框 |
| `_get_surface_region` 用 bbox 中心判左右 | `_describe_region` | 生成「画面左侧 / 偏下」这种人听得懂的方向 |
| `_get_mock_detections` | `_mock_find` | 模拟数据改从 `config/cameras.json` 读 |
| `backend/main.py::trigger_snapshot/broadcast_detection` 把 `location` 附到结果上 | `Sighting.location` | **哪个摄像头看到 = 在哪个位置** |
| `recall/backend/memory.py::RECALL_MAX_DISTANCE` | `conf_threshold` 门控 | 低于阈值宁可说「没看到」，也不乱指位置 |

**新建 `findmy/vision.py`，粘贴：**

```python
"""摄像头寻找：用开放词汇检测在多个摄像头里找指定物品，并回答「在哪里」。

来源（直接改写自 happy-capybara-man/FindForYou 的两个文件）：
  - backend/detector.py
      ObjectDetector.__init__ / _init_model / _update_model_classes / set_classes
      -> 这里精简成 CameraFinder._ensure_model + _set_prompts
      _detect_frame 里遍历 r.boxes.xyxy / conf / cls 并映射 prompt -> canonical id
      -> 这里精简成 _detect_frame 只找目标物品的最高置信度框
      _get_surface_region 用 bbox 中心判断左右区域
      -> 这里保留，用来把「在画面左边」说给用户听
      _get_mock_detections 的模拟数据思路
      -> 这里保留，用 config/cameras.json 的 mock_detections 配置
  - backend/camera_config.json 与 backend/main.py 的 trigger_snapshot / broadcast_detection
      "摄像头 -> location" 的映射，让「检测到」直接等价于「知道在哪个位置」
      -> 这是回答流程第 7 步「告知用户在哪里」的关键，不需要 3D 建图

另外借鉴 zaidwhy/recall/backend/memory.py 的 RECALL_MAX_DISTANCE 置信度门控：
低于 conf_threshold 的检测一律不报，宁可说没看到，也不乱指一个位置。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Sighting:
    item: str
    location: str
    camera: str
    camera_id: str
    confidence: float
    region: str = ""
    source: str = "camera"
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class CameraFinder:
    def __init__(
        self,
        cameras_path: str | Path,
        aliases: Optional[dict] = None,
        model_path: str = "yolov8s-worldv2.pt",
        conf_threshold: float = 0.25,
        frames_per_camera: int = 3,
        mock: bool = False,
    ):
        cfg = json.loads(Path(cameras_path).read_text(encoding="utf-8"))
        self.cameras: dict = cfg.get("cameras", {})
        self.mock_detections: dict = cfg.get("mock_detections", {})
        self.default_camera = cfg.get("default_camera", 0)
        self.aliases = (aliases or {}).get("aliases", {})
        self.prompts: dict = (aliases or {}).get("prompts", {})
        self.model_path = model_path
        self.conf_threshold = float(conf_threshold)
        self.frames_per_camera = int(frames_per_camera)
        self.mock = bool(mock)
        self._model = None
        self._cv2 = None
        self.warnings: list[str] = []

    # ---------------------------------------------------------------- 模型
    def _ensure_model(self):
        """对应 FindForYou/backend/detector.py 的 _init_model。"""
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLOWorld
        except ImportError:
            try:
                from ultralytics import YOLO as YOLOWorld
            except ImportError:
                self.warnings.append(
                    "未安装 ultralytics，摄像头检测将自动使用模拟模式。"
                    "真实检测请执行 pip install ultralytics 并下载 yolov8s-worldv2.pt。"
                )
                self._model = False
                return False
        try:
            self._model = YOLOWorld(self.model_path)
        except Exception as exc:
            self.warnings.append(f"YOLO-World 模型加载失败（{exc}），自动使用模拟模式。")
            self._model = False
        return self._model

    def _set_prompts(self, item_name: str) -> list[str]:
        """对应 detector.py 的 set_classes / _update_model_classes。"""
        key = self.aliases.get(item_name, item_name)
        prompts = self.prompts.get(key, [key])
        model = self._ensure_model()
        if model and hasattr(model, "set_classes"):
            model.set_classes(prompts)
        return prompts

    # ---------------------------------------------------------------- 取帧
    def _grab(self, source):
        """打开一个摄像头（设备号或 RTSP 地址）抓一帧。"""
        if self._cv2 is None:
            try:
                import cv2
                self._cv2 = cv2
            except ImportError:
                self.warnings.append("未安装 opencv-python，摄像头检测将自动使用模拟模式。")
                self._cv2 = False
        if not self._cv2:
            return None
        cap = self._cv2.VideoCapture(source)
        if not cap.isOpened():
            return None
        frame = None
        try:
            for _ in range(self.frames_per_camera):
                ok, f = cap.read()
                if ok:
                    frame = f
        finally:
            cap.release()
        return frame

    # ---------------------------------------------------------------- 检测
    def _detect_frame(self, frame, prompts: list[str]) -> tuple[float, list[float]]:
        """对应 detector.py 的 _detect_frame，只保留目标物品的最高分检测框。"""
        model = self._ensure_model()
        if not model or frame is None:
            return 0.0, []
        try:
            results = model(frame, conf=self.conf_threshold, verbose=False)
        except Exception as exc:
            self.warnings.append(f"检测调用失败（{exc}）。")
            return 0.0, []
        best_conf, best_box = 0.0, []
        for r in results:
            if r.boxes is None:
                continue
            for box, conf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                if float(conf) > best_conf:
                    best_conf = float(conf)
                    best_box = [float(x) for x in box]
        return best_conf, best_box

    @staticmethod
    def _describe_region(bbox: list[float], frame_width: int, frame_height: int) -> str:
        """对应 detector.py 的 _get_surface_region：把 bbox 中心翻成人类听得懂的方向。"""
        if not bbox or not frame_width or not frame_height:
            return ""
        cx = (bbox[0] + bbox[2]) / 2 / frame_width
        cy = (bbox[1] + bbox[3]) / 2 / frame_height
        horizontal = "画面左侧" if cx < 0.33 else ("画面右侧" if cx > 0.66 else "画面中间")
        vertical = "偏上" if cy < 0.33 else ("偏下" if cy > 0.66 else "")
        return horizontal + vertical

    # ---------------------------------------------------------------- 对外主接口（流程第 6、7 步）
    def find(self, item_name: str) -> Optional[Sighting]:
        """在所有启用的摄像头里找 item_name，返回最可信的一次目击。"""
        key = self.aliases.get(item_name, item_name)
        if self.mock or not self._ensure_model():
            return self._mock_find(key)

        prompts = self._set_prompts(item_name)
        best: Optional[Sighting] = None
        for cam_id, cam in self.cameras.items():
            if not cam.get("enabled", True):
                continue
            frame = self._grab(cam.get("source", int(cam_id) if str(cam_id).isdigit() else cam_id))
            if frame is None:
                continue
            conf, bbox = self._detect_frame(frame, prompts)
            # 置信度门控：对应 recall 的 "宁可说没看到，也不编造位置"
            if conf < self.conf_threshold or not bbox:
                continue
            h, w = frame.shape[:2]
            sighting = Sighting(
                item=key,
                location=cam.get("location", cam.get("name", "未知位置")),
                camera=cam.get("name", f"摄像头{cam_id}"),
                camera_id=str(cam_id),
                confidence=round(conf, 3),
                region=self._describe_region(bbox, w, h),
                timestamp=time.time(),
            )
            if best is None or sighting.confidence > best.confidence:
                best = sighting
        return best

    def _mock_find(self, key: str) -> Optional[Sighting]:
        hit = self.mock_detections.get(key)
        if not hit:
            return None
        conf = float(hit.get("confidence", 0.0))
        if conf < self.conf_threshold:
            return None
        cam_id = str(hit.get("camera_id", self.default_camera))
        cam = self.cameras.get(cam_id, {})
        region_map = {"left": "画面左侧", "center": "画面中间", "right": "画面右侧"}
        return Sighting(
            item=key,
            location=cam.get("location", "未知位置"),
            camera=cam.get("name", f"摄像头{cam_id}"),
            camera_id=cam_id,
            confidence=conf,
            region=region_map.get(hit.get("region", ""), ""),
            timestamp=time.time(),
        )
```

---

### 3.9 `findmy/engine.py` — ★ 状态机，把你的两条流程串起来

**这是唯一一个完全由我们新写的文件**，也是把前面所有零件按你的流程接起来的地方。逐段对应：

| 代码位置 | 对应流程 |
|---|---|
| `handle()` 第 73–86 行，`state == "AWAIT_CONFIRM"` | 查找 5 / 5' 的岔路口：`FOUND` → 结束；`NOT_FOUND` → `_search_by_camera` |
| `handle()` 第 89–100 行，`state == "AWAIT_VISION_YES"` | 补全 A：没记忆时先征求同意 |
| `handle()` 第 103–104 行 → `_remember()` | 记忆 1–4 全部入口 |
| `handle()` 第 107–108 行 → `_query()` | 查找 1–4 入口 |
| `_query()`：`memory.find_thing()` | 查找 3 先查记忆库 |
| `_query()`：第 138 行 `f"你之前说{canonical}放在{location}，是否在那？"` | **查找 4，严格用你写的话术** |
| `_search_by_camera()`：`vision.find(item)` | 查找 6 |
| `_search_by_camera()`：拼 `Sighting.location` + `region` | 查找 7 告知在哪里 |
| `_search_by_camera()`：末尾**不调用** `remember_thing()` | 摄像头只播报，绝不写回记忆（硬规则） |
| `_remember()`：`action == "moved"` 时回「已更改记忆：原来在X，现在改到Y」 | 记忆 4 |

`transcript` 列表记录整段对话，测试和调试都靠它。

**新建 `findmy/engine.py`，粘贴：**

```python
"""流程编排状态机：把你写的两套流程逐条映射成代码。

=========================== 查找流程 ===========================
  1 用户询问某项物品位置          -> QUERY 分支入口
  2 语音识别物品                  -> speech.listen() 已把语音转成文字；nlu.parse() 抽出物品名
  3 先从记忆库里查用户告知过的位置 -> memory.find_thing()
  4 输出语音「你之前说放在XX，是否在那？」 -> _on_query_hit()，state 切到 AWAIT_CONFIRM
  5 用户找到，任务结束            -> FOUND 分支，state 回到 IDLE
  5' 用户说「现在不在」           -> NOT_FOUND 分支（state=AWAIT_CONFIRM 时优先识别）
  6 接入摄像头并寻找物品          -> vision.find()
  7 找到物品并告知用户在哪里       -> _search_by_camera()，只播报，不写回记忆

=========================== 记忆流程 ===========================
  1 用户告知某物品放在某位置      -> REMEMBER 分支
  2 语音识别并记住                -> memory.remember_thing()，action=created
  3 用户告知被放进新位置          -> REMEMBER 分支（句式「被放进/挪到/放到」）
  4 更改记忆                      -> 同一个 upsert，action=moved，旧位置写进 history

状态：
  IDLE             空闲，接受「查询」或「登记」
  AWAIT_CONFIRM    刚回答完第 4 步，等「找到了」/「现在不在」
  AWAIT_VISION_YES 记忆库没记录，等用户同意开摄像头（对原流程的合理补全）

重要边界：摄像头看到的位置是「此刻它在哪」，不是用户认定的固定存放位置。
记忆库只接受用户主动口述的登记/更改，摄像头结果一律只播报、不写入。
这样既不会污染记忆（下次问会答错），也不会让库里堆满一次性目击记录。
"""
from __future__ import annotations

from typing import Optional

from . import nlu
from .memory import MemoryStore
from .speech import BaseSpeech
from .vision import CameraFinder, Sighting


class Assistant:
    def __init__(
        self,
        memory: MemoryStore,
        speech: BaseSpeech,
        vision: CameraFinder,
        ask_before_camera_search: bool = True,
    ):
        self.memory = memory
        self.speech = speech
        self.vision = vision
        self.ask_before_camera_search = ask_before_camera_search
        self.state = "IDLE"
        self.pending_item: str = ""
        self.transcript: list[tuple[str, str]] = []  # (角色, 内容)，方便测试与调试

    # ---------------------------------------------------------------- 工具
    def speak(self, text: str) -> str:
        self.transcript.append(("助手", text))
        self.speech.say(text)
        return text

    def hear(self, utterance: str) -> str:
        self.transcript.append(("用户", utterance))
        return utterance

    def _idle(self) -> None:
        self.state = "IDLE"
        self.pending_item = ""

    # ---------------------------------------------------------------- 主入口
    def handle(self, utterance: str) -> str:
        """处理一句话，返回助手要说的话（同时已经通过 speech 说出来）。"""
        self.hear(utterance)
        parsed = nlu.parse(utterance, state=self.state)

        # ---- 等待「是否在那」的回答（流程第 5 步的岔路口）----
        if self.state == "AWAIT_CONFIRM":
            if parsed.intent == nlu.Intent.FOUND:
                item = self.pending_item
                self._idle()
                return self.speak(f"好的，{item}找到了就好，有事再叫我。")
            if parsed.intent == nlu.Intent.NOT_FOUND:
                item = self.pending_item
                self._idle()
                return self._search_by_camera(item, announce=True)
            if parsed.intent == nlu.Intent.EXIT:
                self._idle()
                return self.speak("好的，先不找了。")
            # 用户没直接回答，而是问了别的东西 / 报了新位置 -> 正常往下走
            self._idle()

        # ---- 等待「要不要开摄像头」的回答 ----
        if self.state == "AWAIT_VISION_YES":
            if parsed.intent == nlu.Intent.NO or parsed.intent == nlu.Intent.EXIT:
                self._idle()
                return self.speak("好的，那先不开摄像头。你想起它放在哪了随时告诉我。")
            if parsed.intent == nlu.Intent.YES:
                item = self.pending_item
                self._idle()
                return self._search_by_camera(item, announce=True)
            if parsed.intent in (nlu.Intent.QUERY, nlu.Intent.REMEMBER):
                self._idle()
            else:
                return self.speak("要我现在开摄像头找找吗？说「要」或者「不用」就行。")

        # ---- 记忆流程第 1~4 步：登记 / 更改位置 ----
        if parsed.intent == nlu.Intent.REMEMBER:
            return self._remember(parsed.item, parsed.location)

        # ---- 查找流程第 1~4 步：查询 ----
        if parsed.intent == nlu.Intent.QUERY:
            return self._query(parsed.item)

        if parsed.intent == nlu.Intent.EXIT:
            return self.speak("好的，回头见。")

        if parsed.intent == nlu.Intent.NOT_FOUND:
            return self.speak("你说没找到，但我这边没有正在进行的查找。先告诉我你要找什么吧。")

        if parsed.intent == nlu.Intent.FOUND:
            return self.speak("好的。还有什么要找的吗？")

        return self.speak(
            "我没太听清。你可以说「钥匙在哪」，或者说「钥匙放在鞋柜上」让我记住。"
        )

    # ---------------------------------------------------------------- 查找流程
    def _query(self, item: str) -> str:
        """第 3 步：先查记忆库；第 4 步：命中就先反问。"""
        item = (item or "").strip()
        if not item:
            return self.speak("你要找什么东西？直接说物品名就行。")

        result = self.memory.find_thing(item)
        if result["found"]:
            hit = result["items"][0]
            canonical = hit["name"]
            location = hit["path"]
            self.pending_item = canonical
            self.state = "AWAIT_CONFIRM"
            # 第 4 步：严格按你写的话术输出
            return self.speak(f"你之前说{canonical}放在{location}，是否在那？")

        # 记忆库没记录：对原流程的补全，先征求同意再动摄像头（省电、保护隐私）
        self.pending_item = item
        if self.ask_before_camera_search:
            self.state = "AWAIT_VISION_YES"
            return self.speak(f"我没记过{item}放在哪。要我现在开摄像头帮你找找吗？")
        return self._search_by_camera(item, announce=True)

    def _search_by_camera(self, item: str, announce: bool = False) -> str:
        """第 6 步：接入摄像头寻找；第 7 步：找到并告知位置。"""
        if announce:
            self.speak(f"好的，我现在看看几个摄像头里有没有{item}。")

        sighting: Optional[Sighting] = self.vision.find(item)

        if sighting is None:
            return self.speak(
                f"几个摄像头都没看到{item}。你可以直接告诉我它现在放在哪，我记下来。"
            )

        region_hint = f"，大概在{sighting.region}" if sighting.region else ""
        reply = (
            f"我在{sighting.camera}看到{item}了，应该在{sighting.location}{region_hint}，"
            f"你去看一下。"
        )
        # 只播报，绝不写回记忆库。
        # 摄像头目击是「此刻出现在哪」，不是用户认定的固定存放位置；
        # 写进去既污染下次查询的答案，又会让库里堆满一次性记录。
        # 记忆库只由用户主动口述（_remember）写入。
        self._idle()
        return self.speak(reply)

    # ---------------------------------------------------------------- 记忆流程
    def _remember(self, item: str, location: str) -> str:
        """第 2 步记住 / 第 4 步更改，都由同一个 upsert 完成。"""
        result = self.memory.remember_thing(item, location, source="user")
        if not result.get("ok"):
            return self.speak("我没听清物品名或者位置，再说一遍好吗？")

        action = result["action"]
        if action == "created":
            text = f"记住了，{result['name']}放在{result['path']}。下次忘了直接问我。"
        elif action == "moved":
            text = (
                f"已更改记忆：{result['name']}原来在{result['old_location']}，"
                f"现在改到{result['path']}了。"
            )
        else:
            text = f"{result['name']}本来就在{result['path']}，我记着呢。"
        self._idle()
        return self.speak(text)
```

---

### 3.10 `findmy/cli.py` — 命令行入口

`DEMO_SCRIPT` 就是按你写的两条流程排的一句话脚本，注释里标了每一步。
`--demo` 自动跑，`--voice` 用真麦克风，`--text` 跑单句，`--list / --history / --reset` 管理记忆（重置对应「记忆刷新重置」）。

**新建 `findmy/cli.py`，粘贴：**

```python
"""命令行入口。

    python -m findmy.cli --demo      自动跑一遍完整流程（不需要麦克风/摄像头/模型）
    python -m findmy.cli             打字交互模式（把打字当成「语音识别的结果」）
    python -m findmy.cli --voice     真实麦克风 + 本地语音合成
    python -m findmy.cli --text "钥匙放在鞋柜上"   只跑一句话
    python -m findmy.cli --list      查看记忆库
    python -m findmy.cli --history   查看位置变更历史
    python -m findmy.cli --reset     清空记忆（记忆刷新重置）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import nlu
from .engine import Assistant
from .memory import MemoryStore, load_aliases
from .speech import build_speech
from .vision import CameraFinder

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


# 这一步演示覆盖了你写的两条流程的所有分支
DEMO_SCRIPT = [
    "钥匙放在鞋柜上",          # 记忆流程 1-2：登记
    "我的钥匙在哪",            # 查找流程 1-4：命中记忆并反问
    "现在不在",                # 查找流程 5-6：说没找到，触发摄像头
    "钥匙被放进抽屉里",        # 记忆流程 3-4：更改记忆
    "眼镜在哪",                # 记忆库没记录，询问是否开摄像头
    "要",                      # 同意开摄像头
    "找到了",                  # 任务结束
    "退出",
]


def load_settings(path: Path | None = None) -> dict:
    p = path or (CONFIG_DIR / "settings.json")
    return json.loads(p.read_text(encoding="utf-8"))


def build(paths: dict | None = None, voice: bool = False, script=None,
          echo: bool = True, settings_path: Path | None = None) -> Assistant:
    paths = paths or {}
    settings = load_settings(settings_path)
    root = settings_path.parent.parent if settings_path else ROOT

    db = Path(paths.get("db") or settings["memory"]["db_path"])
    if not db.is_absolute():
        db = root / db

    aliases = load_aliases(paths.get("aliases") or (CONFIG_DIR / "aliases.json"))
    cameras = paths.get("cameras") or (CONFIG_DIR / "cameras.json")

    memory = MemoryStore(db, aliases=aliases)
    speech = build_speech(settings, voice=voice, script=script, echo=echo)
    vcfg = settings.get("vision", {})
    finder = CameraFinder(
        cameras_path=cameras,
        aliases=aliases,
        model_path=vcfg.get("model", "yolov8s-worldv2.pt"),
        conf_threshold=vcfg.get("conf_threshold", 0.25),
        frames_per_camera=vcfg.get("frames_per_camera", 3),
        mock=vcfg.get("mock", True),
    )
    behavior = settings.get("behavior", {})
    assistant = Assistant(
        memory=memory,
        speech=speech,
        vision=finder,
        ask_before_camera_search=behavior.get("ask_before_camera_search", True),
    )
    for w in getattr(speech, "warnings", []) + getattr(finder, "warnings", []):
        print(f"[提示] {w}")
    return assistant


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="findmy - 家用找东西语音助手")
    parser.add_argument("--demo", action="store_true", help="自动演示完整流程")
    parser.add_argument("--voice", action="store_true", help="启用真实麦克风与语音合成")
    parser.add_argument("--text", type=str, help="只处理这一句话")
    parser.add_argument("--list", action="store_true", help="打印记忆库内容")
    parser.add_argument("--history", action="store_true", help="打印位置变更历史")
    parser.add_argument("--reset", action="store_true", help="清空记忆库")
    parser.add_argument("--debug", action="store_true", help="打印每句话的意图解析结果")
    parser.add_argument("--db", type=str, help="自定义 SQLite 数据库路径")
    parser.add_argument("--cameras", type=str, help="自定义摄像头配置路径")
    parser.add_argument("--aliases", type=str, help="自定义别名/提示词配置路径")
    parser.add_argument("--config", type=str, help="自定义 settings.json 路径")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    settings_path = Path(args.config) if args.config else None
    paths = {"db": args.db, "cameras": args.cameras, "aliases": args.aliases}
    paths = {k: v for k, v in paths.items() if v}

    if args.reset:
        a = build(paths, settings_path=settings_path)
        n = a.memory.clear_all()
        print(f"已清空 {n} 条位置记忆。")
        return 0
    if args.list:
        a = build(paths, settings_path=settings_path)
        data = a.memory.list_contents()
        if not data["items"]:
            print("记忆库是空的。")
        else:
            for it in data["items"]:
                print(f"  {it['name']}  ->  {it['path']}   (来源: {it['source']})")
        return 0
    if args.history:
        a = build(paths, settings_path=settings_path)
        for row in a.memory.history(limit=50):
            print(f"  {row['name']}: {row['old_location']} -> {row['new_location']}  [{row['action']}]")
        return 0

    script = DEMO_SCRIPT if args.demo else None
    assistant = build(paths, voice=args.voice, script=script,
                      settings_path=settings_path)

    print("findmy 已启动。说『钥匙在哪』查位置，说『钥匙放在鞋柜上』记位置，说『退出』结束。")

    if args.text:
        if args.debug:
            print("  ", nlu.parse(args.text, state=assistant.state))
        assistant.handle(args.text)
        return 0

    while True:
        if args.demo and not getattr(assistant.speech, "script", None):
            break
        utterance = assistant.speech.listen()
        if not utterance:
            if args.demo:
                continue
            break
        if args.debug:
            print("  ", nlu.parse(utterance, state=assistant.state))
        assistant.handle(utterance)
        if assistant.state == "IDLE" and utterance in ("退出", "quit", "exit"):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

### 3.11 `requirements.txt` — 依赖清单

**最小可跑依赖 = 0**：不装任何东西就能跑打字 + 模拟摄像头全流程。下面全是「要接真实硬件」才需要的，按需逐条装。

**新建 `requirements.txt`，粘贴：**

```text
# 最小可跑依赖：什么都不装也能用打字模式 + 模拟摄像头跑通全流程（只用 Python 标准库）
# 下面这些是「开真实语音 / 开真实摄像头」时才需要，按需逐条装：

# --- 语音识别（流程第 2 步）--- 来自 SYSTRAN/faster-whisper，MIT
# faster-whisper>=1.1.0
# sounddevice>=0.4.6          # 麦克风录音

# --- 语音合成（流程第 4、7 步）--- 来自 OHF-Voice/piper1-gpl，GPL-3.0
# piper-tts>=1.3.0
# pyttsx3>=2.90              # 备用朗读引擎，Windows 零配置（MIT）

# --- 摄像头识别（流程第 6 步）--- 来自 ultralytics，AGPL-3.0 / 企业许可
# ultralytics>=8.3.0
# opencv-python>=4.9.0
# numpy>=1.26

# 一键全装（会下载模型，首次较慢）：
# pip install faster-whisper sounddevice piper-tts pyttsx3 ultralytics opencv-python numpy
```

---

### 3.12 `tests/test_flow.py` — 全流程测试

不需要麦克风、摄像头、模型，用 `TextSpeech` + `mock=True` 跑通你的两条流程：
命中记忆直接结束、没找到触发摄像头、**摄像头找到但不写回记忆（含：已有记录的物品位置不被改写、摄像头看到的新物品不被自动登记、history 不新增）**、摄像头没找到、无记忆先征询、登记/更改/重复登记、别名归一。

**新建 `tests/test_flow.py`，粘贴：**

```python
"""全流程测试：不需要麦克风、摄像头、模型，用打字模拟 + 模拟检测跑通你的两条流程。

特别验证：摄像头只播报位置，绝不写回记忆库（一次性目击不是固定存放位置）。

运行： python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from findmy import nlu                      # noqa: E402
from findmy.engine import Assistant         # noqa: E402
from findmy.memory import MemoryStore       # noqa: E402
from findmy.speech import TextSpeech        # noqa: E402
from findmy.vision import CameraFinder      # noqa: E402

CONFIG_DIR = ROOT / "config"


def make_assistant(tmp: Path, mock_detections: dict | None = None,
                   ask: bool = True) -> Assistant:
    aliases = json.loads((CONFIG_DIR / "aliases.json").read_text(encoding="utf-8"))
    cameras = json.loads((CONFIG_DIR / "cameras.json").read_text(encoding="utf-8"))
    if mock_detections is not None:
        cameras["mock_detections"] = mock_detections
    cam_path = tmp / "cameras.json"
    cam_path.write_text(json.dumps(cameras, ensure_ascii=False), encoding="utf-8")

    memory = MemoryStore(tmp / "memory.db", aliases=aliases)
    speech = TextSpeech(echo=False)
    finder = CameraFinder(cam_path, aliases=aliases, conf_threshold=0.25, mock=True)
    return Assistant(memory, speech, finder, ask_before_camera_search=ask)


class TestNLU(unittest.TestCase):
    def test_query_patterns(self):
        for text, expect_item in [
            ("我的钥匙在哪", "钥匙"),
            ("钥匙放哪儿了", "钥匙"),
            ("找不到眼镜", "眼镜"),
            ("遥控器呢", "遥控器"),
            ("请问手机在哪里", "手机"),
        ]:
            with self.subTest(text=text):
                p = nlu.parse(text)
                self.assertEqual(p.intent, nlu.Intent.QUERY, f"{text} -> {p}")
                self.assertEqual(p.item, expect_item, f"{text} -> {p}")

    def test_remember_patterns(self):
        for text, item, loc in [
            ("钥匙放在鞋柜上", "钥匙", "鞋柜上"),
            ("我把钥匙放在鞋柜上", "钥匙", "鞋柜上"),
            ("钥匙被放进抽屉里", "钥匙", "抽屉里"),
            ("把遥控器挪到书桌上", "遥控器", "书桌上"),
            ("牙刷在厨房小推车", "牙刷", "厨房小推车"),
        ]:
            with self.subTest(text=text):
                p = nlu.parse(text)
                self.assertEqual(p.intent, nlu.Intent.REMEMBER, f"{text} -> {p}")
                self.assertEqual(p.item, item, f"{text} -> {p}")
                self.assertEqual(p.location, loc, f"{text} -> {p}")

    def test_feedback_patterns(self):
        for text in ("现在不在", "没找到", "不在这儿", "还是没有"):
            with self.subTest(text=text):
                self.assertEqual(
                    nlu.parse(text, state="AWAIT_CONFIRM").intent, nlu.Intent.NOT_FOUND
                )
        for text in ("找到了", "在的", "就在这儿"):
            with self.subTest(text=text):
                self.assertEqual(
                    nlu.parse(text, state="AWAIT_CONFIRM").intent, nlu.Intent.FOUND
                )
        self.assertEqual(nlu.parse("要", state="AWAIT_VISION_YES").intent, nlu.Intent.YES)
        self.assertEqual(nlu.parse("不用了", state="AWAIT_VISION_YES").intent, nlu.Intent.NO)


class TestMemory(unittest.TestCase):
    def test_created_then_moved(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d))
            first = a.memory.remember_thing("车钥匙", "鞋柜上")
            self.assertEqual(first["action"], "created")
            self.assertEqual(first["name"], "钥匙")          # 别名归一

            second = a.memory.remember_thing("钥匙", "抽屉里")
            self.assertEqual(second["action"], "moved")
            self.assertEqual(second["old_location"], "鞋柜上")

            found = a.memory.find_thing("钥匙")
            self.assertEqual(found["found"], 1)
            self.assertEqual(found["items"][0]["path"], "抽屉里")

            third = a.memory.remember_thing("钥匙", "抽屉里")
            self.assertEqual(third["action"], "no_change")
            self.assertEqual(len(a.memory.history("钥匙")), 3)


class TestFindFlow(unittest.TestCase):
    def test_step1_to_5_found(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d))
            a.handle("钥匙放在鞋柜上")
            reply = a.handle("我的钥匙在哪")
            self.assertIn("你之前说钥匙放在鞋柜上，是否在那", reply)  # 流程第 4 步
            self.assertEqual(a.state, "AWAIT_CONFIRM")
            reply = a.handle("找到了")
            self.assertIn("找到了就好", reply)
            self.assertEqual(a.state, "IDLE")                          # 流程第 5 步结束

    def test_step5_not_found_triggers_camera_without_touching_memory(self):
        """摄像头找到后只播报，绝不改写用户口述的存放位置。"""
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d))
            a.handle("钥匙放在鞋柜上")
            a.handle("我的钥匙在哪")
            before = len(a.memory.history("钥匙"))
            reply = a.handle("现在不在")                               # 流程第 5 步否定
            self.assertIn("客厅摄像头", reply)                         # 流程第 6、7 步
            self.assertIn("客厅电视柜", reply)
            self.assertNotIn("更新成", reply)                          # 不宣称改了记忆
            self.assertNotIn("记下来了", reply)
            self.assertEqual(a.memory.find_thing("钥匙")["items"][0]["path"], "鞋柜上")
            self.assertEqual(len(a.memory.history("钥匙")), before)     # 也没新增变更历史
            self.assertEqual(a.state, "IDLE")

    def test_no_memory_asks_then_camera(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d))
            reply = a.handle("眼镜在哪")
            self.assertIn("要我现在开摄像头", reply)
            self.assertEqual(a.state, "AWAIT_VISION_YES")
            reply = a.handle("要")
            self.assertIn("卧室摄像头", reply)
            self.assertIn("卧室床头柜", reply)
            self.assertEqual(a.memory.list_contents()["count"], 0)      # 依然没有偷偷登记
            self.assertEqual(a.state, "IDLE")

    def test_camera_found_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d), mock_detections={})
            reply = a.handle("雨伞在哪")
            self.assertEqual(a.state, "AWAIT_VISION_YES")
            reply = a.handle("要")
            self.assertIn("都没看到", reply)

    def test_camera_sighting_never_registers_new_item(self):
        """记忆库里没有的物品，摄像头看到也不该被自动登记（一次性目击不入库）。"""
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d), ask=False)
            reply = a.handle("眼镜在哪")
            self.assertIn("卧室床头柜", reply)
            self.assertEqual(a.memory.list_contents()["count"], 0)
            self.assertEqual(a.memory.history(), [])


class TestRememberFlow(unittest.TestCase):
    def test_step1_to_4(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_assistant(Path(d))
            r1 = a.handle("钥匙放在鞋柜上")
            self.assertIn("记住了", r1)
            r2 = a.handle("钥匙被放进抽屉里")
            self.assertIn("已更改记忆", r2)
            self.assertIn("鞋柜上", r2)
            self.assertIn("抽屉里", r2)
            self.assertEqual(a.memory.find_thing("钥匙")["items"][0]["path"], "抽屉里")
            r3 = a.handle("钥匙在哪")
            self.assertIn("抽屉里", r3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

---

## 第 4 步：不装任何依赖，先跑通

在 `findmy/` 目录下（**注意是含 `findmy/` 子目录的那一层**）：

```bash
python -m compileall -q findmy tests
python -m unittest discover -s tests -v
python -m findmy.cli --demo
```

期望输出（10 个测试全过）：

```
test_camera_found_nothing ... ok
test_feedback_patterns ... ok
test_step5_not_found_triggers_camera_without_touching_memory ... ok
test_camera_sighting_never_registers_new_item ... ok
...
Ran 10 tests in 0.130s
OK
```

`--demo` 期望输出：

```
[助手] 记住了，钥匙放在鞋柜上。下次忘了直接问我。            ← 记忆 1-2
[助手] 你之前说钥匙放在鞋柜上，是否在那？                    ← 查找 1-4
[助手] 好的，我现在看看几个摄像头里有没有钥匙。              ← 查找 5'→6
[助手] 我在客厅摄像头看到钥匙了，应该在客厅电视柜，大概在画面左侧，
       你去看一下。                                          ← 查找 7，只播报、不记
[助手] 已更改记忆：钥匙原来在鞋柜上，现在改到抽屉里了。        ← 记忆 3-4（用户口述才改）
[助手] 我没记过眼镜放在哪。要我现在开摄像头帮你找找吗？      ← 补全 A
[助手] 好的，我现在看看几个摄像头里有没有眼镜。
[助手] 我在卧室摄像头看到眼镜了，应该在卧室床头柜，大概在画面中间，你去看一下。
```

跑完执行 `python -m findmy.cli --list`，记忆库里**只有** `钥匙 -> 抽屉里`，
没有「客厅电视柜」，也没有「眼镜」：摄像头结果一次都没入库。

```
  钥匙  ->  抽屉里   (来源: user)
```

自己手动过一遍流程：

```bash
python -m findmy.cli
```
然后依次输入：`钥匙放在鞋柜上` → `我的钥匙在哪` → `现在不在` → `钥匙被放进抽屉里` → `钥匙在哪` → `找到了` → `退出`。

查状态：

```bash
python -m findmy.cli --list        # 当前记忆
python -m findmy.cli --history     # 位置变更历史（证明「更改记忆」真的发生了）
python -m findmy.cli --reset       # 记忆刷新重置
python -m findmy.cli --text "钥匙在哪" --debug   # 看意图解析结果
```

---

## 第 5 步（可选）：接真实语音

```bash
pip install faster-whisper sounddevice pyttsx3
python -m findmy.cli --voice
```

- 首次运行会自动下载 `small` 模型（约 500 MB），中文想要更准把 `config/settings.json` 的 `stt.model` 改 `medium`。
- `sounddevice` 需要系统有可用麦克风；Windows 若报 PortAudio 错误，先 `pip install pipwin && pipwin install pyaudio` 或换 `pip install sounddevice --upgrade`。
- `pyttsx3` 在 Windows 上零配置就能朗读（系统中文语音包需已安装）。

**要更好的中文 TTS**（Piper，GPL-3.0）：

```bash
pip install piper-tts
# 下载中文语音模型两个文件，放到 models/ 下：
#   zh_CN-huayan-medium.onnx
#   zh_CN-huayan-medium.onnx.json
# 来源：https://huggingface.co/rhasspy/piper-voices/tree/main/zh/zh_CN/huayan/medium
```

然后改 `config/settings.json`：

```json
"tts": { "engine": "piper", "piper_model": "models/zh_CN-huayan-medium.onnx", "fallback": "pyttsx3" }
```

`VoiceSpeech.say()` 会自动 `PiperVoice.load(...).synthesize_wav(...)` → `winsound` / `afplay` 播放；失败则降级到 pyttsx3。

> 想做「小爱同学」式的常驻唤醒词，接 [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)（Apache-2.0）或 openWakeWord，把唤醒后的音频喂给 `VoiceSpeech.listen()` 即可；本项目的 5 秒定时录音只是最简实现。

---

## 第 6 步（可选）：接真实摄像头

```bash
pip install ultralytics opencv-python numpy
```

下载开放词汇模型权重 `yolov8s-worldv2.pt` 放到项目根目录。

改 `config/cameras.json`，把 `source` 换成你的真实设备，`location` 填摄像头实际对着的位置：

```json
"0": { "name": "客厅摄像头", "location": "客厅电视柜", "enabled": true, "source": 0 },
"2": { "name": "玄关摄像头", "location": "玄关鞋柜", "enabled": true,
       "source": "rtsp://admin:password@192.168.1.50/stream1" }
```

再把 `config/settings.json` 里 `vision.mock` 从 `true` 改成 `false`：

```json
"vision": { "model": "yolov8s-worldv2.pt", "conf_threshold": 0.25, "frames_per_camera": 3, "mock": false }
```

`vision.find()` 会依次打开每个启用的摄像头、抓帧、用 `config/aliases.json` 里的提示词调用 `set_classes`、取置信度最高的框，超过 `conf_threshold` 才报。误报多就把阈值提到 `0.35`。

**注意**：`location` 是粗粒度的「一台摄像头 = 一个区域」。要精确到「茶几第二层」，得加 3D 建图（可参考 `Trolleroof/sandhacks`），但那样硬件门槛会高很多。

---

## 第 7 步：开源到 GitHub

先把 `LICENSE`、`.gitignore`、`README.md`、`THIRD_PARTY_NOTICES.md` 放进项目根目录（内容见本仓库对应文件；`LICENSE` 用 MIT 模板，署名保持 `findmy contributors` 或改成你的名字，都合法）。本仓库已全部备齐，**没有任何必须替换的占位符**。

### 方式 A：网页拖拽上传（推荐，一行命令都不用敲）

1. GitHub 网页右上角 `+` → **New repository**，填仓库名、选 Public，**不要勾选** Add a README file / Add .gitignore / Choose a license（勾了会和你要上传的 README、.gitignore、LICENSE 冲突）。
2. **不用解压**：直接用现成的 `findmy` 项目文件夹（已核对与发布包 20 个文件逐字节一致）；也可以解压 `findmy-github-release.zip` 拿一份干净副本，二选一，别两个都传。**进入文件夹里面**，`Ctrl + A` 全选里面全部内容，一起拖到仓库页面的 **upload files** 区域。
   别拖外层 `findmy` 文件夹本身（仓库里会多套一层目录、CI 不生效），也别直接拖 zip 文件（仓库里只会有一个压缩包，程序跑不起来）。
3. 填一句提交说明 → 点 **Commit changes**。仓库首页应出现 20 个文件，并自动跑一次 CI。

> ⚠️ **网页拖拽上传不会执行 `.gitignore`**：拖进去什么就传什么。拖之前打开 `data/` 看一眼：运行过 `--demo` 或 `python -m findmy.cli` 后会有 `data/memory.db`（你家物品的位置记录），先删掉再拖，或改用刚解压的干净副本。

### 方式 B：命令行（可选）

```bash
git init
git add .
git status                 # ★ 确认 data/memory.db 和 models/*.onnx、*.pt 都没被 add
git commit -m "feat: findmy - 家用找东西语音助手"

# 在 GitHub 网页新建空仓库后，页面会显示仓库地址，直接复制过来替换下一行的中文
git remote add origin 粘贴GitHub给你的仓库地址
git branch -M main
git push -u origin main
```

**开源前必查三件事：**

1. 提交清单里**不能有** `data/memory.db`（你家的物品位置）、真实 RTSP 密码、模型权重。带真实密码的配置另存为 `config/cameras.local.json`（已在 `.gitignore`），**运行时加 `--cameras config/cameras.local.json` 指定它**；仓库里的 `cameras.json` 只留示例地址。家用 USB 摄像头填设备号 `0` 即可，不涉及密码。
2. `THIRD_PARTY_NOTICES.md` 必须保留 —— 这是 MIT / Apache 要求的署名义务。
3. 如果你的仓库捆绑或依赖 `ultralytics`（AGPL-3.0）/ `YOLO-World`（GPL-3.0）/ `piper1-gpl`（GPL-3.0），读一遍该文件第二节的三种处理方案，别稀里糊涂踩传染性许可。

---

## 附录 A：许可证速查

| 组件 | 许可证 | 我们有没有复制源码 |
|---|---|---|
| `where-is-my-thing` | MIT | 否，只借接口命名与 `action` 语义，重新实现 |
| `zaidwhy/recall` | MIT | 否，只借打分公式与门控思路 |
| `FindForYou` | MIT | 否，只借配置字段与函数结构，重新实现 |
| `shengwuji` | Apache-2.0 | 否，只借中文句式规则 |
| `faster-whisper` | MIT | 否，运行时动态 import |
| `piper1-gpl` | GPL-3.0 | 否，运行时动态 import（可选） |
| `ultralytics` | **AGPL-3.0** / 商业 | 否，运行时动态 import（可选） |
| `AILab-CVC/YOLO-World` | GPL-3.0 | 否，模型来源 |
| **本项目自己的代码** | **MIT** | — |

完整说明见 `THIRD_PARTY_NOTICES.md`。

---

## 附录 B：想改功能，改哪个文件

| 想做的事 | 改哪里 |
|---|---|
| 加新物品 / 改别名 / 加检测提示词 | `config/aliases.json`，两个表各加一行，**不用动代码** |
| 加摄像头 / 改位置名称 | `config/cameras.json` 的 `cameras` |
| 改第 4 步的话术 | `findmy/engine.py::_query` 里那句 `f"你之前说...是否在那？"` |
| 改第 7 步的话术 | `findmy/engine.py::_search_by_camera` 的 `reply = ...` |
| 让摄像头结果也进记忆（**不推荐**，会污染下次查询） | 需自行在 `findmy/engine.py::_search_by_camera` 里加一行 `memory.remember_thing(...)`；默认刻意不提供此开关 |
| 记忆库没记录时直接开摄像头，不问 | `config/settings.json → behavior.ask_before_camera_search = false` |
| 支持更多中文说法 | `findmy/nlu.py` 的 `QUERY_TAILS` / `PLACE_VERBS` / `FOUND_WORDS` / `NEG_WORDS` |
| 换更好的语音识别 | 替换 `findmy/speech.py::VoiceSpeech._ensure_stt` 与 `listen`，接口不变 |
| 换检测模型 | 替换 `findmy/vision.py::_ensure_model` / `_set_prompts` / `_detect_frame` 三个方法 |
| 换成向量语义检索（支持「那个蓝色小本本」） | 改 `findmy/memory.py::find_thing`，返回结构别变 |
| 清空记忆 / 查历史 | `python -m findmy.cli --reset` / `--history` |

---

## 附录 C：踩过的坑

1. **SQLite 连接没关**：`with sqlite3.connect(...)` 只提交事务不 `close()`，Windows 上 `.db` 会被锁住。已在 `memory.py::_connect` 用 `@contextmanager` 修掉。
2. **「不在这儿」被当成「找到了」**：因为 `FOUND_WORDS` 里有「在这儿」。已在 `nlu.parse` 里改成 `AWAIT_CONFIRM` 状态**先判否定、再判肯定**。
3. **同名物品追加而非覆盖**：声物记是日志式追加，查出来会有多个位置。本项目用主键 UPSERT，一个物品永远只有一个当前位置，旧位置进 `history`。
4. **YOLO-World 把「手机」识别成「遥控器」**：靠 `conf_threshold` 门控 + 多提示词 + 「宁可说没看到」策略兜底，别让程序乱指位置。
5. **摄像头画面里没找到 ≠ 东西不在那个房间**：`vision.find()` 返回 `None` 时只说「几个摄像头都没看到」，不擅自否定用户口述的位置。
6. **别把摄像头目击写进记忆库**（这一条是按需求特意改掉的）：目击是「此刻在哪」，不是固定存放位置。早期版本会自动 `remember_thing(..., source="camera")`，结果用户随口一句「钥匙在哪」会被答成「上次摄像头看到它在客厅电视柜」—— 既答错，又白堆一次性记录。现在 `_search_by_camera()` 只播报，`memory` 只由用户口述写入，且没有留开关防止误开。
7. **AGPL 传染性**：详见 `THIRD_PARTY_NOTICES.md`，商用前务必处理。

---

到这里，一个能跑、能改、能开源、完整覆盖你两条流程的程序就做完了。
