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
