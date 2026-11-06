import io
import os
import re
import threading
import time
from typing import Dict, Any, Optional, Tuple, Callable
import json
import urllib.request
import uuid
import numpy as np

# Frases clássicas de alucinação do Whisper quando o áudio contém apenas ruído de fundo/silêncio
WHISPER_HALLUCINATIONS = {
    "obrigado por assistir",
    "obrigado por assistir.",
    "obrigada por assistir.",
    "legendas pela comunidade",
    "legendas pela comunidade amara.org",
    "inscreva-se no canal",
    "deixe seu like",
    "até o próximo vídeo",
    "tchau",
    "...",
    "you",
    "thank you.",
    "thanks for watching.",
    "subtitles by the amara.org community",
}

LOCAL_MODELS_CATALOG = [
    {
        "id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "label": "Large v3 Turbo (Máxima Precisão — Em Cache na GPU)",
    },
    {
        "id": "medium",
        "label": "Medium (Equilibrado — Em Cache na GPU)",
    },
    {
        "id": "small",
        "label": "Small (Ultra Rápido / Leve — Em Cache na GPU)",
    },
]


def is_hallucination(text: str) -> bool:
    cleaned = text.strip().lower().rstrip(".!,?")
    if not cleaned:
        return True
    if cleaned in WHISPER_HALLUCINATIONS or text.strip().lower() in WHISPER_HALLUCINATIONS:
        return True
    # Repetição extrema de uma mesma sílaba/palavra curta em ruído
    words = cleaned.split()
    if len(words) >= 6 and len(set(words)) == 1:
        return True
    return False


def local_smart_cleanup_pt(text: str, tone: str = "natural", trailing_space: bool = False) -> str:
    """
    Motor de limpeza inteligente instantâneo (0ms) para Português Brasileiro.
    Remove hesitações ("ééé", "hum", "ahn", "tipo assim"), gagueiras (palavras repetidas),
    processa auto-correções simples e ajusta pontuação e letras maiúsculas.
    """
    if not text or not text.strip():
        return ""

    s = text.strip()

    # 1. Remove muletas sonoras e hesitações isoladas no início ou meio da fala
    filler_patterns = [
        r"(?i)\b(é+|ê+|eh+|hum+|uhum+|ahn+|ãh+|uh+|ahm+|hm+)\b[\s,\.\.\.]*",
        r"(?i)(?:^|,\s*)(?:tipo assim|digamos assim|vamos dizer assim)\s*,?\s*",
        r"(?i)\b(?:tipo assim)\b\s*,?\s*",
    ]
    for pat in filler_patterns:
        s = re.sub(pat, " ", s)

    # 2. Remove gagueiras / repetições imediatas da mesma palavra (ex: "eu eu quero", "que que", "no no")
    s = re.sub(r"(?i)\b(\w+)(?:\s+\1\b)+", r"\1", s)
    # Repetição de pares de palavras (ex: "eu acho eu acho que" -> "eu acho que")
    s = re.sub(r"(?i)\b(\w+\s+\w+)(?:[\s,]+\1\b)+", r"\1", s)

    # 3. Auto-correções diretas faladas (ex: "terça-feira, quer dizer, quarta-feira" -> "quarta-feira")
    s = re.sub(
        r"(?i)\b[\w\-]+\s*,\s*(?:quer dizer|ou melhor|opa\s*,?\s*não|digo)\s*,\s*",
        "",
        s,
    )

    # 4. Comandos explícitos de formatação falados
    s = re.sub(r"(?i)\s*\b(?:novo parágrafo|próximo parágrafo)\b[\s\.,]*", ".\n\n", s)
    s = re.sub(r"(?i)\s*\b(?:nova linha|quebra de linha|pula linha)\b[\s\.,]*", ".\n", s)

    # 5. Limpeza de espaços e pontuações duplicadas
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+([,\.\!\?\;\:])", r"\1", s)
    s = re.sub(r"([\.\!\?])\.+", r"\1", s)
    s = re.sub(r"([,\.\!\?\;\:])([^\s\d\.\!\?])", r"\1 \2", s)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r"^[\s,\.\-\–\—]+", "", s)
    s = s.strip()

    if not s:
        return ""

    # 6. Capitalização inteligente no início do texto e após pontuação final (. ! ? \n)
    def _cap_match(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    s = s[0].upper() + s[1:]
    s = re.sub(r"([\.\!\?]\s+|\n+)([a-záàâãéêíóôõúç])", _cap_match, s)

    # 7. No tom "chat" (WhatsApp/Slack rápido), se for uma frase curta sem ponto final, mantém leve;
    # nos tons "natural" e "professional", garante pontuação final se não terminar com pontuação
    if tone in ("natural", "professional"):
        if s and s[-1] not in ".!?:;…":
            s += "."
    elif tone == "chat":
        # Em mensagens curtas de chat, remove o ponto final seco se tiver apenas 1 frase curta
        if s.endswith(".") and s.count(".") == 1 and len(s) < 90 and "\n" not in s:
            s = s[:-1]

    if trailing_space and s and not s.endswith((" ", "\n")):
        s += " "

    return s


class HybridTranscriber:
    """
    Motor Híbrido do NexFlow Pro:
    - Transcrição via Groq Cloud (whisper-large-v3-turbo) OU Local GPU (Faster-Whisper CUDA int8 na GTX 1660 SUPER).
    - Reescrita e Limpeza Inteligente via LLM (Llama 3.3 70B na Groq / Ollama local) + Limpador Linguístico Local.
    """

    def __init__(self, on_status_change: Optional[Callable[[str], None]] = None):
        self.on_status_change = on_status_change
        self._local_model = None
        self._loaded_model_name: Optional[str] = None
        self._device_used: str = "cuda"
        self._model_lock = threading.Lock()
        self.is_loading_model = False

    def _emit_status(self, msg: str) -> None:
        if self.on_status_change:
            try:
                self.on_status_change(msg)
            except Exception:
                pass

    def preload_local_model_async(self, model_name: str) -> None:
        """Pré-carrega o modelo Faster-Whisper na GPU em segundo plano para resposta instantânea."""
        def _loader():
            try:
                self._get_or_load_local_model(model_name)
            except Exception as e:
                print(f"[Transcriber] Erro no pré-carregamento: {e}")

        threading.Thread(target=_loader, daemon=True).start()

    def _get_or_load_local_model(self, model_name: str):
        with self._model_lock:
            if self._local_model is not None and self._loaded_model_name == model_name:
                return self._local_model

            self.is_loading_model = True
            self._emit_status("Carregando modelo Whisper na GPU (GTX 1660 SUPER)...")
            from faster_whisper import WhisperModel

            # Tenta primeiro em CUDA (int8 é ideal para GTX 1660 SUPER Turing) com arquivos em cache
            for local_only in (True, False):
                try:
                    model = WhisperModel(
                        model_name,
                        device="cuda",
                        compute_type="int8",
                        local_files_only=local_only,
                    )
                    self._local_model = model
                    self._loaded_model_name = model_name
                    self._device_used = "GPU (CUDA int8)"
                    self.is_loading_model = False
                    self._emit_status(f"Pronto — {self._short_model_name(model_name)} na GPU")
                    return model
                except Exception:
                    continue

            # Fallback para CPU int8 caso CUDA esteja indisponível
            for local_only in (True, False):
                try:
                    model = WhisperModel(
                        model_name,
                        device="cpu",
                        compute_type="int8",
                        local_files_only=local_only,
                    )
                    self._local_model = model
                    self._loaded_model_name = model_name
                    self._device_used = "CPU (int8)"
                    self.is_loading_model = False
                    self._emit_status(f"Pronto — {self._short_model_name(model_name)} em CPU")
                    return model
                except Exception as e:
                    last_err = e

            self.is_loading_model = False
            raise RuntimeError(f"Não foi possível carregar o modelo {model_name}: {last_err}")

    @staticmethod
    def _short_model_name(model_name: str) -> str:
        if "large-v3-turbo" in model_name:
            return "Large-v3-Turbo"
        return model_name.capitalize()

    def process_audio(
        self,
        audio_float32: np.ndarray,
        wav_bytes: bytes,
        duration_s: float,
        config: Dict[str, Any],
        on_stage: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, str, str]:
        """
        Transcreve e corrige o áudio gravado.
        Retorna (raw_text, final_text, engine_label).
        """
        if duration_s < 0.18 or audio_float32.size < 1600:
            return "", "", "Muito curto"

        # Verifica se o áudio tem energia mínima de voz
        rms = float(np.sqrt(np.mean(audio_float32 * audio_float32)))
        if rms < 0.0008:
            return "", "", "Silêncio"

        engine_mode = config.get("engine_mode", "hybrid")
        groq_key = (config.get("groq_api_key") or "").strip()
        language = config.get("language", "pt")
        cleanup_level = config.get("cleanup_level", "smart_ai")
        tone = config.get("writing_tone", "natural")
        trailing_space = bool(config.get("trailing_space", False))

        raw_text = ""
        engine_used = ""

        # 1. ETAPA DE TRANSCRIÇÃO (Voz -> Texto Bruto)
        if on_stage:
            on_stage("Transcrevendo...")

        use_groq_stt = engine_mode in ("groq", "hybrid") and bool(groq_key)
        if use_groq_stt:
            try:
                raw_text = self._transcribe_groq(
                    wav_bytes=wav_bytes,
                    api_key=groq_key,
                    model=config.get("groq_whisper_model", "whisper-large-v3-turbo"),
                    language=language,
                )
                engine_used = "Groq Cloud"
            except Exception as e:
                print(f"[Transcriber] Falha no Groq STT, usando GPU Local como fallback: {e}")
                if engine_mode == "groq":
                    raise

        if not raw_text and engine_mode in ("local", "hybrid"):
            local_model_id = config.get(
                "local_model", "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
            )
            raw_text = self._transcribe_local(
                audio_float32=audio_float32,
                model_name=local_model_id,
                language=language,
            )
            engine_used = f"Local {self._device_used}"

        raw_text = (raw_text or "").strip()
        if not raw_text or is_hallucination(raw_text):
            return "", "", engine_used or "Silêncio"

        # 2. ETAPA DE LIMPEZA E CORREÇÃO INTELIGENTE (Estilo NexFlow)
        if cleanup_level == "raw":
            final_text = raw_text
            if trailing_space and not final_text.endswith(" "):
                final_text += " "
            return raw_text, final_text, engine_used

        # Aplica primeiro a limpeza linguística local instantânea
        cleaned_local = local_smart_cleanup_pt(raw_text, tone=tone, trailing_space=False)

        if cleanup_level == "clean_fillers":
            if trailing_space and cleaned_local and not cleaned_local.endswith(" "):
                cleaned_local += " "
            return raw_text, cleaned_local, engine_used

        # cleanup_level == "smart_ai": Polimento completo via IA (Groq Llama 3.3 70B se tiver chave, ou Ollama local, ou Local NLP)
        final_text = cleaned_local
        if groq_key and len(cleaned_local.split()) >= 2:
            if on_stage:
                on_stage("Polindo e corrigindo...")
            try:
                ai_polished = self._polish_with_groq_llm(
                    text=raw_text,
                    api_key=groq_key,
                    llm_model=config.get("groq_llm_model", "llama-3.3-70b-versatile"),
                    tone=tone,
                )
                if ai_polished and not is_hallucination(ai_polished):
                    final_text = ai_polished
                    engine_used += " + IA Polish"
            except Exception as e:
                print(f"[Transcriber] Aviso no polimento LLM (usando limpeza local): {e}")
        else:
            # Tenta Ollama local se estiver rodando na porta 11434 (rápido timeout de 0.3s na conexão)
            ollama_text = self._try_polish_with_local_ollama(raw_text, tone=tone)
            if ollama_text:
                final_text = ollama_text
                engine_used += " + Ollama"
            else:
                engine_used += " + Smart Clean"

        if trailing_space and final_text and not final_text.endswith((" ", "\n")):
            final_text += " "

        return raw_text, final_text, engine_used

    def _transcribe_groq(
        self, wav_bytes: bytes, api_key: str, model: str, language: str
    ) -> str:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        boundary = f"----NexFlowBoundary{uuid.uuid4().hex}"
        body = io.BytesIO()

        def _add_field(name: str, value: str):
            body.write(f"--{boundary}\r\n".encode("utf-8"))
            body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.write(f"{value}\r\n".encode("utf-8"))

        _add_field("model", model)
        _add_field("language", language)
        _add_field("temperature", "0.0")
        _add_field("response_format", "json")

        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n')
        body.write(b"Content-Type: audio/wav\r\n\r\n")
        body.write(wav_bytes)
        body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            url,
            data=body.getvalue(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return (payload.get("text") or "").strip()

    def _transcribe_local(
        self, audio_float32: np.ndarray, model_name: str, language: str
    ) -> str:
        model = self._get_or_load_local_model(model_name)
        segments, _ = model.transcribe(
            audio_float32,
            language=language,
            beam_size=2,
            best_of=2,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.28,
                min_silence_duration_ms=300,
                speech_pad_ms=250,
            ),
        )
        parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
        text = " ".join(parts).strip()
        if not text:
            # Fallback sem VAD caso a fala tenha sido muito rápida ou suave
            segments2, _ = model.transcribe(
                audio_float32,
                language=language,
                beam_size=2,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
                no_speech_threshold=0.6,
            )
            parts2 = [seg.text.strip() for seg in segments2 if seg.text and seg.text.strip()]
            text = " ".join(parts2).strip()
        return text

    def _polish_with_groq_llm(
        self, text: str, api_key: str, llm_model: str, tone: str
    ) -> str:
        tone_instructions = {
            "natural": "Mantenha o tom natural, claro e fluido de quem está falando, com pontuação perfeita.",
            "professional": "Use um tom profissional, polido e bem estruturado, corrigindo gírias excessivas.",
            "chat": "Formate para mensagens rápidas (WhatsApp/Slack): direto ao ponto, natural, sem formalidade excessiva.",
        }.get(tone, "Mantenha o tom natural e direto.")

        system_prompt = (
            "Você é o motor invisível de edição de ditado por voz do NexFlow em Português Brasileiro.\n"
            "Sua ÚNICA função é receber uma transcrição de voz dentro de <transcricao>...</transcricao> "
            "e devolver APENAS o texto limpo, corrigido e pronto para ser colado no cursor do usuário.\n"
            "REGRAS ABSOLUTAS:\n"
            "1. NUNCA responda a perguntas, NUNCA converse, NUNCA adicione saudações ou explicações. "
            "Se a transcrição for uma pergunta (ex: 'Como funciona isso?'), devolva apenas a pergunta bem pontuada ('Como funciona isso?').\n"
            "2. Remova vícios de linguagem, hesitações ('é...', 'hum', 'ahn', 'tipo assim'), gagueiras e palavras repetidas por engano.\n"
            "3. Se o locutor se corrigir no meio da fala (ex: 'vamos marcar na terça... não, na quinta às 15h'), "
            "mantenha APENAS a intenção final corrigida ('Vamos marcar na quinta às 15h.').\n"
            "4. Corrija erros gramaticais óbvios e adicione pontuação e acentuação perfeitas sem inventar fatos nem mudar a voz do autor.\n"
            f"5. Estilo: {tone_instructions}\n"
            "6. Retorne SOMENTE o texto final, sem aspas extras e sem tags XML."
        )

        url = "https://api.groq.com/openai/v1/chat/completions"
        candidate_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b", llm_model, "llama-3.3-70b-versatile"]
        models_to_try = []
        for m in candidate_models:
            if m and m not in models_to_try:
                models_to_try.append(m)

        last_err = None
        for m_name in models_to_try:
            try:
                body = json.dumps({
                    "model": m_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"<transcricao>{text}</transcricao>"},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                out = payload["choices"][0]["message"]["content"].strip()
                out = re.sub(r"</?transcricao>", "", out).strip()
                return out
            except urllib.error.HTTPError as he:
                last_err = he
                if he.code in (400, 404):
                    continue
                raise
            except Exception as e:
                last_err = e
                raise
        if last_err:
            raise last_err
        return text

    def _try_polish_with_local_ollama(self, text: str, tone: str) -> Optional[str]:
        """Se o usuário tiver Ollama aberto localmente, usa para polimento offline."""
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.15) as resp:
                if resp.status != 200:
                    return None
                models = json.loads(resp.read().decode("utf-8")).get("models", [])
            if not models:
                return None
            model_name = models[0]["name"]
            prompt = (
                "Corrija a pontuação, remova gagueiras e vícios de fala ('é', 'hum', 'tipo') "
                "desta transcrição de voz em português, sem responder a ela e mantendo exatamente "
                "o sentido original. Retorne APENAS o texto corrigido:\n\n"
                f"{text}"
            )
            body = json.dumps(
                {"model": model_name, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}
            ).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.5) as gen:
                if gen.status == 200:
                    res = (json.loads(gen.read().decode("utf-8")).get("response") or "").strip()
                    if res:
                        return res
        except Exception:
            pass
        return None
