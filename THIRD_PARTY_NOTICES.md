# 第三方项目与许可证说明

本项目的代码是**重新实现**的：只借鉴了下列项目的接口命名、返回结构、配置字段与设计思路，
没有整体复制其源文件。逐条列出出处，方便你开源时履行署名义务。

## 一、借鉴了设计 / 接口（源码均为宽松许可）

| 上游项目 | 许可证 | 具体借鉴了哪个文件、哪一部分 | 用在本项目哪里 |
|---|---|---|---|
| [utkarshjosh/where-is-my-thing](https://github.com/utkarshjosh/where-is-my-thing) | MIT | `spatial_memory_agent/agent.py`：`remember_thing` / `find_thing` / `move_thing` / `list_contents` 四个工具的名字与返回结构；`AGENT_INSTRUCTION` 里「自然语言 → 工具调用」的分派思路 | `findmy/memory.py`、`findmy/nlu.py` |
| 同上 | MIT | `services/graph_service.py`：同名物品再登记时先删旧关系再建新关系，`action = created / moved / no_change` 的判定 | `findmy/memory.py::remember_thing` |
| 同上 | MIT | `services/memory_service.py`：`canonical_similarity_search(..., min_score=0.5)` 的相似度门控与别名归一 | `findmy/memory.py::find_thing`（用标准库 `difflib` 代替向量库，`MIN_SIMILARITY = 0.60`） |
| [zaidwhy/recall](https://github.com/zaidwhy/recall) | MIT | `backend/memory.py`：`DECAY_WEIGHT = 0.25`、`score = distance + 0.25 * log(1 + hours_ago)` 的时间衰减、`RECALL_MAX_DISTANCE` 置信度门控、60 秒内同位置原地更新 | `findmy/memory.py::_time_penalty`、`findmy/vision.py` 的 `conf_threshold` 门控 |
| 同上 | MIT | `backend/tools.py`：`recall_memory` 工具「查到才回答，查不到就明说」的行为 | `findmy/engine.py::_query` |
| [happy-capybara-man/FindForYou](https://github.com/happy-capybara-man/FindForYou) | MIT | `backend/detector.py`：`ObjectDetector._init_model` / `set_classes` / `_update_model_classes` / `_detect_frame` / `_get_surface_region` / `_get_mock_detections` | `findmy/vision.py` |
| 同上 | MIT | `backend/camera_config.json`：`name` / `location` / `enabled` 字段 —— **摄像头直接绑定一个位置**，这是「检测到 = 知道在哪」的关键 | `config/cameras.json`、`findmy/vision.py::find` |
| 同上 | MIT | `backend/custom_classes.json`：`classes[].id` + `classes[].prompts` 多提示词映射 | `config/aliases.json` |
| 同上 | MIT | `backend/main.py`：`trigger_snapshot` / `broadcast_detection` 里把 `location` 附到检测结果上的做法 | `findmy/vision.py::Sighting` |
| [fantasyao/shengwuji（声物记）](https://github.com/fantasyao/shengwuji) | Apache-2.0 | 用「在 / 放在 / 放进」把中文句子拆成「物品—位置」的规则，以及「撤销上一条」的记忆管理思路 | `findmy/nlu.py`（`PLACE_VERBS`、`LOCATION_HINTS`） |

## 二、可选运行时依赖（本项目没有复制它们的任何源码，只在 `pip install` 之后动态 import）

| 项目 | 许可证 | 用途 | 触发条件 |
|---|---|---|---|
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | `WhisperModel(...).transcribe(...)` 本地语音识别 | `pip install faster-whisper` + `--voice` |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | 麦克风录音 / 播放 | 同上 |
| [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) | GPL-3.0 | `PiperVoice.load(...).synthesize_wav(...)` 本地中文语音合成 | 配置了 `tts.piper_model` |
| [pyttsx3](https://github.com/nateshmbhat/pyttsx3) | MPL-2.0 / 部分平台 | 备用朗读引擎 | 自动降级时 |
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | **AGPL-3.0** 或商业许可 | `YOLOWorld(...).set_classes(...)` 开放词汇检测 | `pip install ultralytics` + `vision.mock=false` |
| [opencv-python](https://github.com/opencv/opencv) | Apache-2.0 | 读取摄像头帧 | 同上 |
| [AILab-CVC/YOLO-World](https://github.com/AILab-CVC/YOLO-World) | GPL-3.0 | 上游模型的原始实现（可选替代） | 不走 ultralytics 时 |

> **重要（开源前务必想清楚）**：`ultralytics` 是 AGPL-3.0、`YOLO-World` 原版是 GPL-3.0，
> 二者都有传染性。本项目只是通过公开 API 动态调用，**没有捆绑其源码或权重**，
> 个人自用、学习、以 MIT 开源本项目代码通常没问题；但如果你要**闭源商用或整体分发**，
> 建议三选一：
> 1. 换 Apache-2.0 / MIT 的开放词汇检测模型（如基于 ONNX Runtime 自行加载的 CLIP 类方案）；
> 2. 把检测拆成独立微服务，主程序通过 HTTP/MQTT 拿结果，做进程隔离（合规性请自行咨询律师）；
> 3. 接受 AGPL-3.0，把整个项目一并改为 AGPL-3.0 开源，或购买 Ultralytics 企业许可。
>
> 另外 `piper1-gpl` 是 GPL-3.0，用不到它可以只装 `pyttsx3`（`tts.engine = "pyttsx3"`），
> 或改用 Home Assistant 的 Wyoming Piper 插件作为独立服务。

## 三、本机隐私数据

`data/memory.db` 里是你家里的物品位置，`config/cameras.json` 里可能有摄像头 RTSP 账号密码。
两者都已在 `.gitignore` 中排除。开源前请再次执行 `git status` 确认没有被提交。
