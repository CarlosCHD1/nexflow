import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# Diretório base para persistência (compatível com desenvolvimento e executável PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "history.json"


def get_resource_path(relative_path: str) -> Path:
    """Retorna o caminho de um recurso (ícones, assets), compatível com PyInstaller --onefile."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


DEFAULT_CONFIG: Dict[str, Any] = {
    # Atalho padrão de 1 única tecla: CapsLock (0x14)
    # Quando a ferramenta está ativa, o CapsLock grava voz sem ativar LETRAS MAIÚSCULAS.
    # Apertando Ctrl + CapsLock você desativa/ativa a ferramenta para usar o CapsLock normal!
    "hotkey_codes": [0x14],  # VK_CAPITAL (CapsLock)
    "hotkey_label": "CapsLock",
    "master_toggle_label": "Ctrl + CapsLock",
    "tool_enabled": True,
    "start_with_windows": True,
    # Modos: "smart" (Toque rápido = Toggle, Segurar = Push-to-Talk), "hold" (Segurar), "toggle" (Apertar)
    "hotkey_mode": "smart",
    # Motor: "hybrid" (Groq Cloud se tiver chave + Fallback Local GPU), "local" (100% Local GPU), "groq" (Groq Cloud)
    "engine_mode": "hybrid",
    # Modelo Whisper local (já em cache na máquina!)
    "local_model": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    # Chave gratuita da Groq (console.groq.com)
    "groq_api_key": "",
    # Modelo de voz na Groq
    "groq_whisper_model": "whisper-large-v3-turbo",
    # Modelo LLM na Groq para limpeza e correção
    "groq_llm_model": "qwen/qwen3.8-27b",
    # Nível de limpeza inteligente: "smart_ai" (Correção completa + limpeza), "clean_fillers" (Limpeza leve), "raw" (Literal)
    "cleanup_level": "smart_ai",
    # Tom do texto: "natural" (Natural e direto), "professional" (Profissional/Formal), "chat" (Mensagem rápida/WhatsApp)
    "writing_tone": "natural",
    # Idioma principal
    "language": "pt",
    # Índice do microfone (-1 = Padrão do Windows)
    "mic_device_id": -1,
    "mic_device_name": "Padrão do Sistema",
    # Comportamento da pílula flutuante: "always" (Sempre visível discreta) ou "active_only" (Apenas ao falar/processar)
    "pill_visibility": "always",
    "pill_x": None,
    "pill_y": None,
    # Efeitos sonoros sutis ao iniciar/parar gravação
    "sound_feedback": True,
    # Restaurar área de transferência anterior após colar (False = mantém o texto ditado no Ctrl+V também)
    "restore_clipboard": False,
    # Adicionar espaço no final se digitar em sequência
    "trailing_space": False,
    # Estatísticas acumuladas
    "stats_total_words": 0,
    "stats_total_dictations": 0,
    "stats_seconds_recorded": 0.0,
}


def load_config() -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    config.update(saved)
        except Exception as e:
            print(f"[Config] Erro ao ler config.json: {e}")
    # Também permite GROQ_API_KEY via variável de ambiente
    if not config.get("groq_api_key") and os.environ.get("GROQ_API_KEY"):
        config["groq_api_key"] = os.environ["GROQ_API_KEY"]
    return config


def save_config(config: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Erro ao salvar config.json: {e}")


def load_history() -> List[Dict[str, Any]]:
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[:50]
        except Exception:
            pass
    return []


def add_history_entry(raw_text: str, final_text: str, duration_s: float, engine_used: str) -> List[Dict[str, Any]]:
    from datetime import datetime

    history = load_history()
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "raw_text": raw_text,
        "final_text": final_text,
        "duration_s": round(duration_s, 2),
        "engine": engine_used,
        "words": len(final_text.split()),
    }
    history.insert(0, entry)
    history = history[:50]
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[History] Erro ao salvar histórico: {e}")
    return history
