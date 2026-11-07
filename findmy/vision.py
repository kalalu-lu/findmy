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
