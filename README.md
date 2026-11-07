# findmy · 在家找东西的语音助手

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-10%20passed-brightgreen)
![Privacy](https://img.shields.io/badge/privacy-100%25%20local-orange)
![Cost](https://img.shields.io/badge/API%20cost-%C2%A50-brightgreen)

> 忘了钥匙放哪，直接说一句就行。先翻你亲口告诉它的记忆，找不到再开摄像头帮你找。
>
> **A local, offline voice assistant that remembers where you put things.** It first recalls locations you told it verbally; if you say "not there", it searches configured cameras and speaks out the location. Zero cloud API calls, zero fees.

```
你：钥匙放在鞋柜上   → 助手：记住了，钥匙放在鞋柜上。下次忘了直接问我。
你：我的钥匙在哪     → 助手：你之前说钥匙放在鞋柜上，是否在那？
你：找到了           → 助手：好的，钥匙找到了就好。（结束）

你：我的钥匙在哪     → 助手：你之前说钥匙放在鞋柜上，是否在那？
你：现在不在         → 助手：好的，我现在看看几个摄像头里有没有钥匙。
                         助手：我在客厅摄像头看到钥匙了，应该在客厅电视柜，
                               大概在画面左侧，你去看一下。

你：钥匙被放进抽屉里 → 助手：已更改记忆：钥匙原来在鞋柜上，现在改到抽屉里了。
```

**摄像头只播报，绝不写回记忆库** —— 目击是「它此刻在哪」，不是固定存放位置；写进去会让下次查询答错。

---

## 目录

- [快速开始](#快速开始)
- [发布到 GitHub（网页拖拽，不用命令行）](#发布到-github网页拖拽不用命令行)
- [它实现的两条流程](#它实现的两条流程)
- [文件与流程对照](#文件与流程对照)
- [每一步用上游哪个文件的哪一段](#每一步用上游哪个文件的哪一段)
- [配置](#配置)
- [接真实语音与摄像头](#接真实语音与摄像头)
- [测试与验证](#测试与验证)
- [隐私与许可证](#隐私与许可证)
- [致谢](#致谢)
- [已知限制](#已知限制)

---

## 快速开始

需要 **Python 3.10+**，**不需要安装任何第三方库**（默认用打字模拟语音、模拟摄像头检测）。

```bash
# 在 GitHub 页面点绿色 Code → Download ZIP，解压后进入项目目录
cd findmy

python -m unittest discover -s tests -v    # 10 个测试，确认代码没问题
python -m findmy.cli --demo                 # 一条命令看完整个流程
python -m findmy.cli                        # 开始自己对话
```

> 代码块开头的 `bash` 只是「这是一段命令行指令」的标签，不是软件、不用安装。
> Windows 上最省事的做法：打开解压出来的 `findmy` 文件夹，在**地址栏**输入 `cmd` 回车，就会直接在这个目录打开命令行窗口，把上面几行粘进去即可。前提是装了 Python 3.10+（安装时勾选 **Add Python to PATH**）。

出现 `[你说] ` 就输入文字。打字模拟的就是「语音识别的输出」，流程和真实语音完全一样。建议按这个顺序走一遍：

```
钥匙放在鞋柜上 → 我的钥匙在哪 → 找到了
钥匙在哪 → 现在不在 → 钥匙被放进抽屉里 → 钥匙在哪 → 退出
```

| 命令 | 作用 |
|---|---|
| `python -m findmy.cli --demo` | 自动演示完整流程 |
| `python -m findmy.cli --text "钥匙在哪" --debug` | 只跑一句，并打印意图解析结果 |
| `python -m findmy.cli --list` | 查看当前记忆库 |
| `python -m findmy.cli --history` | 查看位置变更历史 |
| `python -m findmy.cli --reset` | 记忆刷新重置（保留历史，可追溯） |
| `python -m findmy.cli --voice` | 启用真实麦克风与语音合成 |

想彻底回到白纸状态，删掉 `data/memory.db` 即可（下次运行自动重建）。

`--demo` 实际输出：

```
[助手] 记住了，钥匙放在鞋柜上。下次忘了直接问我。              ← 记忆 1-2
[助手] 你之前说钥匙放在鞋柜上，是否在那？                      ← 查找 1-4
[助手] 好的，我现在看看几个摄像头里有没有钥匙。                ← 查找 5'→6
[助手] 我在客厅摄像头看到钥匙了，应该在客厅电视柜，大概在画面左侧，
       你去看一下。                                            ← 查找 7，只播报不入库
[助手] 已更改记忆：钥匙原来在鞋柜上，现在改到抽屉里了。          ← 记忆 3-4（用户口述才改）
[助手] 我没记过眼镜放在哪。要我现在开摄像头帮你找找吗？        ← 补全
[助手] 好的，我现在看看几个摄像头里有没有眼镜。
[助手] 我在卧室摄像头看到眼镜了，应该在卧室床头柜，大概在画面中间，你去看一下。
```

跑完 `python -m findmy.cli --list` 只会看到 `钥匙 -> 抽屉里 (来源: user)` —— 没有「客厅电视柜」、没有「眼镜」。

---

## 发布到 GitHub（网页拖拽，不用命令行）

**完全不用敲命令**，一行 git 都不需要：

1. GitHub 网页右上角 `+` → **New repository**，填仓库名（比如 `findmy`），选 Public。
   **三个初始化选项都不要勾**：Add a README file、Add .gitignore、Choose a license —— 勾了会和你上传的 README / .gitignore / LICENSE 冲突。
2. 准备文件，**两种方式任选其一**（内容完全一致，别两个都传）：
   - **不解压**：直接用现成的 `findmy` 项目文件夹（已核对与发布包逐字节一致）；
   - **解压**：把 `findmy-github-release.zip` 解压，得到一份干净的 `findmy` 文件夹。
3. **进入这个文件夹里面**，`Ctrl + A` 全选里面的全部内容（`config/`、`.github/`、`findmy/`、`tests/`、`data/` 以及根目录那些文件），一起拖到 GitHub 仓库页面的 **upload files** 区域。
   ⚠️ 别拖外层 `findmy` 文件夹本身（仓库里会多套一层目录、CI 不生效）；也别直接拖 zip 文件（那样仓库里只有一个压缩包，程序跑不起来）。
4. 页面下方填一句提交说明（如 `init: findmy`），点 **Commit changes**，完成。

> **重要：网页拖拽上传不理会 `.gitignore`** —— 拖进去什么就传什么。
> 拖之前打开 `data/` 看一眼：运行过 `--demo` 或 `python -m findmy.cli` 后会生成 `data/memory.db`（你家物品的位置记录），先删掉再拖，或改用刚解压出来的干净副本。

上传完仓库首页应能看到 `config/`、`findmy/`、`.github/`、`README.md` 等，共 **20 个文件**，并会自动跑一次 CI（Python 3.10–3.13 × 10 个测试）。

**仓库里没有任何必须替换的占位符**：README 不含个人用户名；`LICENSE` 第 3 行与 `pyproject.toml` 第 12 行署名 `findmy contributors`，在 MIT 下合法且常见，想改成自己名字属于可选。

---

## 它实现的两条流程

**查找流程**

```
1 用户询问某项物品位置
2 语音识别 → 抽出物品名
3 先查记忆库里用户之前告知过的位置
4 语音输出「你之前说放在某某位置，是否在那？」
5 ├─ 找到了 → 任务结束
  └─ 用户告知「现在不在」
     6 接入摄像头并寻找物品
     7 找到并告知用户在哪里（只播报，不写回记忆）
```

**记忆流程**

```
1 用户告知某物品放在某位置   → action = created
3 用户告知被放进某新位置     → action = moved（旧位置进 history 表）
4 更改记忆                   → 同名物品 UPSERT，永远只有一个当前位置
```

代码里是 3 个状态：`IDLE` → `AWAIT_CONFIRM` → `AWAIT_VISION_YES`，全部集中在 `findmy/engine.py`。

原流程只有一处空白做了补全：**记忆库里压根没这个物品时**，先问「要我现在开摄像头帮你找找吗？」，同意再找。开关在 `config/settings.json → behavior.ask_before_camera_search`。

> **硬规则：摄像头找到后只播报，绝不写回记忆库。** 记忆库只接受用户主动口述的登记与更改，因此没有留任何自动写回开关；`engine.py::_search_by_camera()` 不会调用 `remember_thing()`，测试里也锁死了这条边界。

---

## 文件与流程对照

```
findmy/
├── README.md                    ← 你正在看的文件
├── TUTORIAL.md                  一步步搭建教程（内嵌全部源码，可直接复制）
├── THIRD_PARTY_NOTICES.md       上游出处 + 许可证合规说明
├── LICENSE                      MIT
├── pyproject.toml               可选：pip install -e . 的元数据
├── requirements.txt             可选依赖清单
├── .github/workflows/tests.yml  CI：每次 push 自动跑 10 个测试
├── config/
│   ├── settings.json            总开关（模型、阈值、行为）
│   ├── cameras.json             摄像头 → 位置映射 + 模拟检测结果
│   └── aliases.json             别名归一 + YOLO-World 提示词
├── findmy/
│   ├── engine.py                ★ 状态机，把两条流程串起来
│   ├── memory.py                SQLite 记忆库（upsert / 时间衰减 / history）
│   ├── nlu.py                   中文意图与物品、位置抽取（纯规则，不接 LLM）
│   ├── speech.py                faster-whisper 识别 + Piper 合成（懒加载可降级）
│   ├── vision.py                YOLO-World 多摄像头寻找
│   ├── cli.py                   命令行入口
│   └── __init__.py
├── data/.gitkeep                data/memory.db 运行时生成，已 gitignore
└── tests/test_flow.py           10 个全流程测试
```

| 文件 | 实现哪一步 | 说明 |
|---|---|---|
| `findmy/speech.py` | 查找 **1、4、7**；记忆 **1、3** | `listen()` 语音转文字、`say()` 文字转语音；`TextSpeech` 让无依赖也能跑 |
| `findmy/nlu.py` | 查找 **2、5、5′**；记忆 **1、3** | 拆「意图 + 物品 + 位置」；先判否定再判肯定，避免「不在这儿」被当成「找到了」 |
| `findmy/memory.py` | 查找 **3**；记忆 **2、4** | `find_thing()` 查、`remember_thing()` 增删改、`clear_all()` 重置；**只接受用户口述** |
| `findmy/vision.py` | 查找 **6、7** | 逐摄像头检测，返回 `Sighting(location, camera, region, confidence)`；低于阈值宁可说没看到 |
| `findmy/engine.py` | **全部流程总控** | `_query()` → 第 3–4 步；`_search_by_camera()` → 第 6–7 步；`_remember()` → 记忆 2/4 |
| `findmy/cli.py` | 入口 | 组装配置、提供 `--demo / --voice / --list / --history / --reset` |

完整的一步步搭建教程（含每个文件的全部代码、上游文件对照）：**[TUTORIAL.md](TUTORIAL.md)**。

---

## 每一步用上游哪个文件的哪一段

没有单一现成项目能同时覆盖「口述记忆 + 摄像头」，所以本项目重新实现了四家的核心思路（**均为宽松许可，未复制源码**）。

| 流程步骤 | 复用的开源项目 | 上游**具体文件 / 具体段落** | 本项目落点 | 改了什么 |
|---|---|---|---|---|
| 查找 **1** 用户开口 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | README 的 `WhisperModel(...).transcribe(...)`；[声物记](https://github.com/fantasyao/shengwuji) SenseVoice 离线方案作备选 | `speech.py::VoiceSpeech.listen` | 加 5 秒定时录音 + VAD，缺依赖自动降级为打字 |
| 查找 **2** 抽出物品 | [where-is-my-thing](https://github.com/utkarshjosh/where-is-my-thing) | `spatial_memory_agent/agent.py` 的 `AGENT_INSTRUCTION`；声物记「在 / 放在」拆句规则 | `nlu.py::parse`、`engine.py::handle` | 不接 LLM，改纯规则解析，输出同样的结构化意图 |
| 查找 **3** 查记忆库 | where-is-my-thing | `agent.py::find_thing`、`services/graph_service.py` 层级查询、`services/memory_service.py::canonical_similarity_search(min_score=0.5)` | `memory.py::find_thing` | Neo4j + 向量 → SQLite 单表 + `difflib`，保留 `{"query","found","items":[{"name","path"}]}` |
| 查找 **3** 排序 | [zaidwhy/recall](https://github.com/zaidwhy/recall) | `backend/memory.py`：`DECAY_WEIGHT=0.25`、`score = distance + 0.25*log(1+hours_ago)`、`RECALL_MAX_DISTANCE` | `memory.py::_time_penalty` | 新记录天然排在旧记录前面 |
| 查找 **4** 语音反问 | [Piper](https://github.com/OHF-Voice/piper1-gpl) | `PiperVoice.load(...).synthesize_wav(...)`；[app-piper](https://github.com/home-assistant/app-piper) 可作独立服务 | `speech.py::say` → `engine.py::_query` | 严格用原话术，状态切到 `AWAIT_CONFIRM` |
| 查找 **5 / 5′** | 声物记短反馈词表 | — | `nlu.py::FOUND_WORDS / NEG_WORDS` | **先判否定再判肯定**，否则「不在这儿」会被误判成「找到了」 |
| 查找 **6** 摄像头 | [FindForYou](https://github.com/happy-capybara-man/FindForYou) | `backend/detector.py`：`_init_model` / `set_classes` / `_detect_frame`；`backend/main.py::trigger_snapshot` | `vision.py::CameraFinder.find` | 精简成「只找当前物品的最高分检测框」，逐摄像头轮询 |
| 查找 **6** 开放词汇 | [YOLO-World](https://github.com/AILab-CVC/YOLO-World) / [ultralytics](https://github.com/ultralytics/ultralytics) | `YOLOWorld(model).set_classes(prompts)` | `vision.py::_set_prompts` + `config/aliases.json` | 中文物品名映射成多个英文提示词 |
| 查找 **7** 告知位置 | FindForYou | `backend/camera_config.json` 的 **`location`** 字段；`detector.py::_get_surface_region` bbox 判左右 | `vision.py::Sighting` → `engine.py::_search_by_camera` | 不需 3D 建图：哪个摄像头看到 = 在哪个位置；**结果只播报，不写进记忆库** |
| 记忆 **1 / 3** 口述 | 声物记 | 「在 / 放在 / 放进」拆「物品—位置」 | `nlu.py::PLACE_VERBS` | 扩了「被放进 / 挪到 / 换到」等更新句式 |
| 记忆 **2** 记住 | where-is-my-thing | `agent.py::remember_thing` | `memory.py::remember_thing` | `action=created`，`source='user'`，写 `history` |
| 记忆 **4** 更改 | where-is-my-thing `graph_service.py`（删旧 `LOCATED_IN` 再建新关系）+ recall 60 秒原地更新 | `graph_service.py` 的 `action` 判定 | `memory.py::remember_thing` 的 UPSERT | 一条语句完成覆盖，旧位置进 `history` 可追溯 |
| 记忆刷新重置 | — | — | `memory.py::clear_all` / `cli.py --reset` | 清空位置记录但保留变更历史 |

---

## 配置

三个 JSON 都在 `config/`，**改配置不用改代码**。

| 想做的事 | 改哪里 |
|---|---|
| 加新物品、别名、检测提示词 | `config/aliases.json` 两个表各加一行 |
| 加摄像头、改位置名称 | `config/cameras.json` 的 `cameras`；`location` 填摄像头实际拍到的区域 |
| 改检测置信度 / 模型 / 关闭模拟 | `config/settings.json` 的 `vision` |
| 记忆库没记录时直接开摄像头，不问 | `behavior.ask_before_camera_search = false` |
| 改第 4 步、第 7 步的话术 | `findmy/engine.py` 的 `_query()` / `_search_by_camera()` |

> `location` 是写死的配置，不是模型推理出来的 —— **一台摄像头对应一个区域**。换成你家真实摄像头时记得改，否则会指错地方。

---

## 接真实语音与摄像头

默认零依赖即可跑；下面都是可选增强。

**语音**

```bash
pip install faster-whisper sounddevice pyttsx3
python -m findmy.cli --voice
```

中文想要更准，把 `config/settings.json` 的 `stt.model` 从 `small` 改成 `medium`。想要更好的中文 TTS，装 `piper-tts` 并下载 `zh_CN-huayan-medium.onnx` + `.onnx.json`，把路径填进 `tts.piper_model`。

**摄像头**

```bash
pip install ultralytics opencv-python numpy
# 下载 yolov8s-worldv2.pt 放到项目根目录
```

把 `config/cameras.json` 的 `source` 改成 USB 设备号（`0`/`1`）或 RTSP 地址，`location` 填实际位置；再把 `config/settings.json` 的 `vision.mock` 改成 `false`。误报多就把 `conf_threshold` 提到 `0.35`。

也可以一次性装齐（需先 `pip install -e ".[voice,vision]"`）：

| 附加组 | 装的包 |
|---|---|
| `.[voice]` | faster-whisper、sounddevice、pyttsx3、piper-tts |
| `.[vision]` | ultralytics、opencv-python、numpy |

---

## 测试与验证

```bash
python -m unittest discover -s tests -v
```

| 检查项 | 结果 |
|---|---|
| `python -m compileall -q findmy tests` | 通过 |
| `python -m unittest discover -s tests -v` | **10 / 10 通过** |
| `python -m findmy.cli --demo` | 两条流程所有分支输出正确 |

10 个测试全部不需要麦克风、摄像头或模型，用 `TextSpeech` + 模拟检测跑通两条流程。特别锁死两条边界：

- **摄像头找到后不改写已有记忆**（用户口述的位置保持不变，`history` 不新增）
- **摄像头看到的新物品不被自动登记**（一次性目击不入库）

CI 会在每次 push / PR 时用 Python 3.10–3.13 自动跑这套测试。

---

## 隐私与许可证

- **纯本地**：默认不联网、不上传任何数据。记忆库是本机 `data/memory.db`。
- `data/memory.db`（你家的物品位置）已在 `.gitignore` 中排除，`config/cameras.json` 里只留示例地址。**带真实 RTSP 密码的配置另存为 `config/cameras.local.json`（已忽略），运行时用 `--cameras config/cameras.local.json` 指定**；家用 USB 摄像头直接填设备号 `0`，本来就没有密码。
- ⚠️ **GitHub 网页的 upload files 拖拽上传不会执行 `.gitignore`**：拖进去什么就传什么。只拖干净的发布包，别拖运行过的目录。用命令行 push 时，提交前再跑一次 `git status` 确认。
- 本项目自己的代码：**MIT**，见 [LICENSE](LICENSE)。
- 借鉴的上游均为 MIT / Apache-2.0，逐文件出处与署名见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- ⚠️ 可选依赖 `ultralytics` 是 **AGPL-3.0**、`YOLO-World` 与 `piper1-gpl` 是 **GPL-3.0**，有传染性。本项目只做运行时动态调用、不捆绑源码或权重；若要闭源商用，请先读 `THIRD_PARTY_NOTICES.md` 第二节的三种处理方案。

---

## 致谢

| 上游 | 许可 | 借鉴的部分 |
|---|---|---|
| [utkarshjosh/where-is-my-thing](https://github.com/utkarshjosh/where-is-my-thing) | MIT | `remember_thing / find_thing / move_thing` 工具语义与 `action` 判定 |
| [zaidwhy/recall](https://github.com/zaidwhy/recall) | MIT | 时间衰减打分、置信度门控、「查到才回答」 |
| [happy-capybara-man/FindForYou](https://github.com/happy-capybara-man/FindForYou) | MIT | YOLO-World 开放词汇检测、**摄像头→位置映射**、多提示词表 |
| [fantasyao/shengwuji](https://github.com/fantasyao/shengwuji) | Apache-2.0 | 中文「在 / 放在」拆「物品—位置」的句式规则 |

语音用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（MIT）与 [Piper](https://github.com/OHF-Voice/piper1-gpl) 的公开 API。

---

## 已知限制

- 中文意图是纯规则解析，不接 LLM。想支持「我那个蓝色的小本本」得换语义检索（接口不用改）。
- 摄像头位置是粗粒度的「一台摄像头 = 一个区域」，不是 3D 精确定位。
- 定时录音固定 5 秒，没有唤醒词；常驻唤醒可接 [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)。
- 单人单机命令行程序，没有多用户、没有 Web / 移动端界面。

欢迎提 issue 和 PR。改代码前跑一遍 `python -m unittest discover -s tests -v` 就行。
