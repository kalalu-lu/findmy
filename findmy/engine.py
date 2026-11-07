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
