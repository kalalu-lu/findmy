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
