import ctypes
from ctypes import wintypes
import io
import threading
import time
import wave
from typing import List, Dict, Optional, Tuple, Callable
import numpy as np

winmm = ctypes.windll.winmm

WAVE_MAPPER = 0xFFFFFFFF
WAVE_FORMAT_PCM = 1
WHDR_DONE = 0x00000001
WHDR_PREPARED = 0x00000002


class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_char_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


def list_microphones() -> List[Dict[str, any]]:
    """Lista todos os microfones disponíveis no Windows."""
    devices = [{"id": -1, "name": "Automático Inteligente (Detecta o microfone ativo)"}]
    try:
        num = winmm.waveInGetNumDevs()
        for i in range(num):
            caps = WAVEINCAPSW()
            res = winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
            if res == 0:
                devices.append({"id": i, "name": caps.szPname.strip()})
    except Exception as e:
        print(f"[Audio] Erro ao listar microfones: {e}")
    return devices


class _SingleDeviceStream:
    """Captura áudio de 1 dispositivo WinMM específico em 16kHz 16-bit Mono."""

    def __init__(self, dev_id: int, sample_rate: int, chunk_bytes: int, num_buffers: int):
        self.dev_id = dev_id
        self.hwi = ctypes.c_void_p()
        self.buffers = []
        self.headers = []
        self.chunks: List[bytes] = []
        self.idx = 0
        self.opened = False
        self.max_rms = 0.0

        wfx = WAVEFORMATEX(
            WAVE_FORMAT_PCM,
            1,
            sample_rate,
            sample_rate * 2,
            2,
            16,
            0,
        )
        res = winmm.waveInOpen(ctypes.byref(self.hwi), dev_id, ctypes.byref(wfx), 0, 0, 0)
        if res != 0:
            return

        self.opened = True
        for _ in range(num_buffers):
            buf = ctypes.create_string_buffer(chunk_bytes)
            hdr = WAVEHDR(
                ctypes.cast(buf, ctypes.c_char_p),
                chunk_bytes,
                0,
                0,
                0,
                0,
                None,
                0,
            )
            winmm.waveInPrepareHeader(self.hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInAddBuffer(self.hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
            self.buffers.append(buf)
            self.headers.append(hdr)

        winmm.waveInStart(self.hwi)

    def poll(self) -> Optional[bytes]:
        if not self.opened:
            return None
        latest_slice = None
        while True:
            hdr = self.headers[self.idx]
            if hdr.dwFlags & WHDR_DONE:
                recorded = hdr.dwBytesRecorded
                if recorded > 0:
                    raw_slice = self.buffers[self.idx].raw[:recorded]
                    self.chunks.append(raw_slice)
                    latest_slice = raw_slice
                    arr = np.frombuffer(raw_slice, dtype=np.int16).astype(np.float32) / 32768.0
                    if arr.size > 0:
                        rms = float(np.sqrt(np.mean(arr * arr)))
                        if rms > self.max_rms:
                            self.max_rms = rms
                hdr.dwFlags &= ~WHDR_DONE
                hdr.dwBytesRecorded = 0
                winmm.waveInAddBuffer(self.hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
                self.idx = (self.idx + 1) % len(self.headers)
            else:
                break
        return latest_slice

    def close(self) -> None:
        if not self.opened:
            return
        self.opened = False
        try:
            winmm.waveInStop(self.hwi)
            winmm.waveInReset(self.hwi)
            # Coleta qualquer áudio restante no buffer final após o Reset
            for i in range(len(self.headers)):
                idx = (self.idx + i) % len(self.headers)
                hdr = self.headers[idx]
                if hdr.dwBytesRecorded > 0:
                    raw_slice = self.buffers[idx].raw[: hdr.dwBytesRecorded]
                    self.chunks.append(raw_slice)
                    hdr.dwBytesRecorded = 0
            for hdr in self.headers:
                winmm.waveInUnprepareHeader(self.hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInClose(self.hwi)
        except Exception:
            pass


class AudioRecorder:
    """
    Gravador de áudio multi-microfone de baixíssima latência via Windows WinMM (16kHz, 16-bit, Mono).
    - No modo Automático (-1), escuta simultaneamente todos os microfones do PC e usa automaticamente
      aquele que captou a sua voz com maior clareza (evitando microfones mudos como fifine SC3!).
    - Possui detecção automática de fim de fala (VAD): se o usuário der 1 toque no CapsLock, falar
      e fizer silêncio por ~1.5s, finaliza e cola o texto automaticamente!
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BITS_PER_SAMPLE = 16
    CHUNK_DURATION_MS = 50
    NUM_BUFFERS = 16

    def __init__(self, on_auto_silence_stop: Optional[Callable[[], None]] = None):
        self.on_auto_silence_stop = on_auto_silence_stop
        self.is_recording = False
        self.auto_stop_on_silence = True
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._best_pcm_bytes: bytes = b""
        self._start_time: float = 0.0
        self.current_level: float = 0.0
        self.waveform_bars: List[float] = [0.08] * 9
        self.active_mic_name: str = ""

    def start(self, device_id: int = -1, allow_auto_silence_stop: bool = True) -> bool:
        with self._lock:
            if self.is_recording:
                return True
            self._best_pcm_bytes = b""
            self.current_level = 0.0
            self.waveform_bars = [0.08] * 9
            self.is_recording = True
            self.auto_stop_on_silence = allow_auto_silence_stop
            self._start_time = time.perf_counter()

        self._thread = threading.Thread(
            target=self._record_loop, args=(device_id,), daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> Tuple[np.ndarray, bytes, float]:
        with self._lock:
            if not self.is_recording:
                return np.array([], dtype=np.float32), b"", 0.0
            self.is_recording = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        raw_pcm = self._best_pcm_bytes
        self.current_level = 0.0
        self.waveform_bars = [0.08] * 9

        if not raw_pcm:
            return np.array([], dtype=np.float32), b"", 0.0

        samples_int16 = np.frombuffer(raw_pcm, dtype=np.int16)
        audio_float32 = samples_int16.astype(np.float32) / 32768.0

        # Remove eventual DC offset do microfone
        if audio_float32.size > 0:
            audio_float32 = audio_float32 - float(np.mean(audio_float32))

        # Normalização inteligente de ganho (amplifica mesmo microfones bem baixos!)
        peak = float(np.max(np.abs(audio_float32))) if audio_float32.size > 0 else 0.0
        if 0.002 < peak < 0.65:
            gain = min(12.0, 0.80 / peak)
            audio_float32 = np.clip(audio_float32 * gain, -1.0, 1.0)
            samples_int16 = (audio_float32 * 32767.0).astype(np.int16)
            raw_pcm = samples_int16.tobytes()

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(raw_pcm)

        actual_duration = len(samples_int16) / float(self.SAMPLE_RATE)
        return audio_float32, wav_io.getvalue(), actual_duration

    def cancel(self) -> None:
        with self._lock:
            self.is_recording = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._best_pcm_bytes = b""
        self.current_level = 0.0
        self.waveform_bars = [0.08] * 9

    def get_duration(self) -> float:
        if not self.is_recording:
            return 0.0
        return max(0.0, time.perf_counter() - self._start_time)

    def _record_loop(self, device_id: int) -> None:
        chunk_bytes = int((self.SAMPLE_RATE * self.CHUNK_DURATION_MS // 1000) * 2)

        streams: List[_SingleDeviceStream] = []
        num_devs = winmm.waveInGetNumDevs()

        if device_id >= 0 and device_id < num_devs:
            st = _SingleDeviceStream(device_id, self.SAMPLE_RATE, chunk_bytes, self.NUM_BUFFERS)
            if st.opened:
                streams.append(st)

        # Se for Automático (-1) ou se o dispositivo específico falhou, abre TODOS os microfones disponíveis!
        if not streams:
            for d_id in range(num_devs):
                st = _SingleDeviceStream(d_id, self.SAMPLE_RATE, chunk_bytes, self.NUM_BUFFERS)
                if st.opened:
                    streams.append(st)
            if not streams:
                st = _SingleDeviceStream(WAVE_MAPPER, self.SAMPLE_RATE, chunk_bytes, self.NUM_BUFFERS)
                if st.opened:
                    streams.append(st)

        if not streams:
            self.is_recording = False
            return

        # Variáveis para detecção automática de voz e silêncio (VAD)
        noise_floor = 0.003
        has_spoken = False
        speech_frames = 0
        last_voice_time = time.perf_counter()
        triggered_auto_stop = False

        try:
            while self.is_recording:
                best_slice = None
                best_slice_rms = -1.0

                for st in streams:
                    sl = st.poll()
                    if sl is not None:
                        arr = np.frombuffer(sl, dtype=np.int16).astype(np.float32) / 32768.0
                        rms = float(np.sqrt(np.mean(arr * arr))) if arr.size > 0 else 0.0
                        if rms > best_slice_rms:
                            best_slice_rms = rms
                            best_slice = sl

                if best_slice is not None:
                    self._update_levels(best_slice)
                    now = time.perf_counter()
                    elapsed_total = now - self._start_time

                    # Calibra ruído ambiente nos primeiros 0.25s
                    if elapsed_total < 0.25 and not has_spoken:
                        noise_floor = max(0.002, min(0.018, 0.7 * noise_floor + 0.3 * best_slice_rms))

                    voice_threshold = max(0.0055, noise_floor * 2.4)
                    if best_slice_rms >= voice_threshold:
                        speech_frames += 1
                        last_voice_time = now
                        if speech_frames >= 3:  # ~150ms de voz real
                            has_spoken = True
                    else:
                        # Se o usuário já falou e fez uma pausa de 1.5s em modo mãos-livres, finaliza sozinho!
                        if (
                            self.auto_stop_on_silence
                            and has_spoken
                            and not triggered_auto_stop
                            and (now - last_voice_time) >= 1.55
                            and elapsed_total >= 1.8
                        ):
                            triggered_auto_stop = True
                            if self.on_auto_silence_stop:
                                threading.Thread(target=self.on_auto_silence_stop, daemon=True).start()
                                break
                else:
                    time.sleep(0.012)
        finally:
            # Escolhe o buffer do microfone que teve o maior sinal de voz na sessão!
            best_stream = max(streams, key=lambda s: s.max_rms) if streams else None
            if best_stream and best_stream.chunks:
                self._best_pcm_bytes = b"".join(best_stream.chunks)
            for st in streams:
                st.close()

    def _update_levels(self, raw_slice: bytes) -> None:
        try:
            arr = np.frombuffer(raw_slice, dtype=np.int16).astype(np.float32) / 32768.0
            if arr.size == 0:
                return
            rms = float(np.sqrt(np.mean(arr * arr)))
            norm_level = min(1.0, pow(rms * 8.5, 0.68))
            self.current_level = 0.6 * norm_level + 0.4 * self.current_level

            if arr.size >= 64:
                fft_mag = np.abs(np.fft.rfft(arr * np.hanning(arr.size)))
                bands = np.array_split(fft_mag[2:92], 9)
                new_bars = []
                weights = [0.65, 0.85, 1.0, 1.15, 1.3, 1.15, 1.0, 0.85, 0.65]
                for b, w in zip(bands, weights):
                    val = float(np.mean(b)) if b.size > 0 else 0.0
                    bar_h = min(1.0, max(0.08, pow(val * 0.55 * w, 0.62)))
                    new_bars.append(bar_h)
                self.waveform_bars = [
                    0.65 * nb + 0.35 * ob
                    for nb, ob in zip(new_bars, self.waveform_bars)
                ]
        except Exception:
            pass
