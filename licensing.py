"""
NexFlow — Sistema de Licenciamento Criptográfico e Ativação Comercial
Garante que apenas clientes autorizados possam utilizar as funcionalidades do software.
"""

import hashlib
import hmac
import json
import os
import platform
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Diretório base
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

LICENSE_FILE = BASE_DIR / "license.dat"

# Chave secreta mestre do NexFlow para assinatura criptográfica (HMAC-SHA256)
_MASTER_SECRET = b"NexFlow_Commercial_Software_Signature_2026_SecAuth_v2"


def get_machine_fingerprint() -> str:
    """Gera um identificador estável, anônimo e único do computador do usuário."""
    try:
        raw_parts = [
            platform.node(),
            platform.machine(),
            platform.processor(),
            str(uuid.getnode()),
        ]
        combined = ":".join(raw_parts).encode("utf-8")
        h = hashlib.sha256(combined).hexdigest()[:16].upper()
        return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"
    except Exception:
        return "NEX-DEFAULT-PC"


def generate_license_key(tier: str = "PRO") -> str:
    """Gera uma chave comercial criptograficamente assinada (ex: NEXFLOW-PRO-XXXX-XXXX-XXXX-XXXX-XXXX)."""
    tier_clean = tier.strip().upper()
    nonce = secrets.token_hex(4).upper()  # 8 caracteres hexadecimais aleatórios
    payload = f"{tier_clean}:{nonce}".encode("utf-8")
    checksum = hmac.new(_MASTER_SECRET, payload, hashlib.sha256).hexdigest()[:12].upper()
    full_code = f"{nonce}{checksum}"  # 20 caracteres
    return (
        f"NEXFLOW-{tier_clean}-"
        f"{full_code[:4]}-{full_code[4:8]}-{full_code[8:12]}-{full_code[12:16]}-{full_code[16:20]}"
    )


def verify_license_key(key_str: str) -> Tuple[bool, str, Optional[str]]:
    """
    Valida a autenticidade criptográfica de uma chave de ativação.
    Retorna: (is_valid, mensagem_amigável, tier)
    """
    if not key_str:
        return False, "Por favor, insira uma chave de licença válida.", None

    clean = key_str.strip().upper().replace(" ", "").replace("\t", "")
    parts = clean.split("-")

    if len(parts) != 7 or parts[0] != "NEXFLOW":
        return (
            False,
            "Formato de chave inválido. Exemplo: NEXFLOW-PRO-XXXX-XXXX-XXXX-XXXX-XXXX",
            None,
        )

    tier = parts[1]
    raw_code = "".join(parts[2:])
    if len(raw_code) != 20:
        return False, "Comprimento da chave incorreto.", None

    nonce = raw_code[:8]
    checksum = raw_code[8:]
    payload = f"{tier}:{nonce}".encode("utf-8")
    expected = hmac.new(_MASTER_SECRET, payload, hashlib.sha256).hexdigest()[:12].upper()

    if hmac.compare_digest(checksum, expected):
        return True, f"Licença {tier} Autêntica e Válida!", tier
    return False, "Chave de ativação inválida ou não reconhecida.", None


def activate_license(key_str: str, user_name: str = "") -> Tuple[bool, str]:
    """Ativa o software no computador atual salvando os dados assinados em license.dat."""
    is_valid, msg, tier = verify_license_key(key_str)
    if not is_valid:
        return False, msg

    machine_id = get_machine_fingerprint()
    now_iso = time.strftime("%Y-%m-%d %H:%M:%S")

    # Cria o payload da licença
    data = {
        "key": key_str.strip().upper(),
        "tier": tier,
        "owner": user_name.strip() or "Licenciado",
        "machine_id": machine_id,
        "activated_at": now_iso,
        "status": "active",
    }

    # Assina os dados locais
    raw_to_sign = f"{data['key']}|{data['tier']}|{data['machine_id']}|{data['activated_at']}".encode("utf-8")
    data["signature"] = hmac.new(_MASTER_SECRET, raw_to_sign, hashlib.sha256).hexdigest()

    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True, f"NexFlow {tier} ativado com sucesso! Aproveite todas as funcionalidades."
    except Exception as e:
        return False, f"Erro ao gravar arquivo de licença: {e}"


def get_license_info() -> Dict[str, Any]:
    """Lê os dados da licença ativa atual."""
    if not LICENSE_FILE.exists():
        return {"activated": False, "tier": "NONE", "owner": "", "status": "unlicensed"}

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        key = data.get("key", "")
        tier = data.get("tier", "PRO")
        machine_id = data.get("machine_id", "")
        activated_at = data.get("activated_at", "")
        sig = data.get("signature", "")

        # Valida a assinatura da chave
        is_key_valid, _, _ = verify_license_key(key)
        if not is_key_valid:
            return {"activated": False, "tier": "NONE", "owner": "", "status": "invalid_key"}

        # Valida a integridade do arquivo
        raw_to_sign = f"{key}|{tier}|{machine_id}|{activated_at}".encode("utf-8")
        expected_sig = hmac.new(_MASTER_SECRET, raw_to_sign, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return {"activated": False, "tier": "NONE", "owner": "", "status": "tampered"}

        return {
            "activated": True,
            "key": key,
            "tier": tier,
            "owner": data.get("owner", "Licenciado"),
            "machine_id": machine_id,
            "activated_at": activated_at,
            "status": "active",
        }
    except Exception:
        return {"activated": False, "tier": "NONE", "owner": "", "status": "corrupt"}


def is_activated() -> bool:
    """Verifica de forma rápida e segura se o aplicativo possui licença comercial ativa."""
    info = get_license_info()
    return bool(info.get("activated", False))


def deactivate_license() -> bool:
    """Remove a licença ativa deste computador."""
    try:
        if LICENSE_FILE.exists():
            os.remove(LICENSE_FILE)
        return True
    except Exception:
        return False
