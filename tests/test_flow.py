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
