#!/usr/bin/env python3
"""
NexFlow — Gerador Oficial de Chaves de Licença Comercial
Use este utilitário para gerar chaves que você enviará para quem comprar o NexFlow.
"""

import argparse
import sys
from licensing import generate_license_key, verify_license_key, get_machine_fingerprint


def main():
    parser = argparse.ArgumentParser(
        description="Gerador de Chaves de Licença Comercial — NexFlow",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=1,
        help="Quantidade de chaves a serem geradas (padrão: 1)",
    )
    parser.add_argument(
        "-t",
        "--tier",
        type=str,
        default="PRO",
        choices=["PRO", "LIFETIME", "ENTERPRISE"],
        help="Plano da licença (padrão: PRO)",
    )
    parser.add_argument(
        "--verify",
        type=str,
        help="Verifica se uma chave fornecida é autêntica e válida",
    )
    args = parser.parse_args()

    if args.verify:
        is_valid, msg, tier = verify_license_key(args.verify)
        print("=" * 60)
        print(f"Verificação da Chave: {args.verify}")
        print(f"Status: {'[VÁLIDA ✓]' if is_valid else '[INVÁLIDA ✕]'}")
        print(f"Mensagem: {msg}")
        if tier:
            print(f"Plano / Tier: {tier}")
        print("=" * 60)
        return

    print("=" * 60)
    print("        NEXFLOW — GERADOR DE CHAVES COMERCIAIS")
    print("=" * 60)
    print(f"Plano selecionado: {args.tier.upper()}")
    print(f"Quantidade: {args.count}")
    print("-" * 60)

    keys = []
    for i in range(args.count):
        k = generate_license_key(tier=args.tier)
        keys.append(k)
        print(f"  [{i+1:02d}] {k}")

    print("-" * 60)
    print("Copie as chaves acima e envie para seus compradores (Kiwify, Hotmart, Stripe, etc.)")
    print("Quando o comprador colar a chave no NexFlow, o aplicativo será ativado permanentemente.")
    print("=" * 60)


if __name__ == "__main__":
    main()
