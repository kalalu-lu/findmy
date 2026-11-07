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
