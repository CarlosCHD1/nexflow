<p align="center">
  <img src="assets/logo.png" width="160" alt="NexFlow Pro Logo"/>
</p>

<h1 align="center">NexFlow Pro</h1>

<p align="center">
  <strong>Ditado por Voz Inteligente com IA & Estúdio de Áudio de Alta Fidelidade.</strong><br>
  A solução definitiva de produtividade por voz para criadores, profissionais e desenvolvedores no Windows, macOS e Linux.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Versão-2.0%20Pro-F97316?style=flat-square" alt="Version"/>
  <img src="https://img.shields.io/badge/Plataforma-Windows%20%7C%20macOS%20%7C%20Linux-1E293B?style=flat-square" alt="Multiplatform"/>
  <img src="https://img.shields.io/badge/Design-Apple%20Obsidian%20Glass-0EA5E9?style=flat-square" alt="Apple Glass"/>
  <img src="https://img.shields.io/badge/Licenciamento-HMAC--SHA256%20Criptografado-10B981?style=flat-square" alt="Licensing"/>
</p>

---

## ✨ O que é o NexFlow Pro?

O **NexFlow Pro** é uma aplicação comercial de alta performance projetada para transformar o modo como você escreve e produz conteúdo. Inspirado na ergonomia de produtos Apple e no Wispr Flow, o NexFlow opera de forma invisível em segundo plano com uma interface flutuante ultramoderna.

Com apenas um toque de tecla, sua fala é capturada, transcrita e refinada por modelos de linguagem de ponta, sendo inserida diretamente onde o seu cursor estiver piscando — em qualquer aplicativo do seu sistema operacional.

---

## 🌟 Principais Recursos

### ⚡ 1. Ditado Inteligente no Cursor (`CapsLock`)
- Pressione `CapsLock`, fale com naturalidade e solte ou faça uma pausa.
- O NexFlow processa o áudio em tempo recorde (~300-500ms via Groq Cloud ou localmente via GPU) e digita o texto final formatado, com pontuação perfeita e sem vícios de linguagem (*"tipo assim"*, *"ééé"*, repetições, gagueiras).
- Compatível com WhatsApp, Word, Notion, Slack, Discord, Google Docs, VS Code, navegadores e qualquer campo de texto.

### 🎧 2. Gravador Studio de Áudio 48 kHz (`Alt + A`)
- Desenvolvido sob medida para criadores de conteúdo, narradores e podcasters.
- Pressione `Alt + A` em qualquer janela para iniciar a gravação de voz em **qualidade broadcast (48.000 Hz, 16-bit PCM WAV)**.
- Ao encerrar, o áudio é salvo automaticamente na pasta:
  `Vídeos/Conteúdos/áudios/` com nomeação cronológica organizada (`REC_YYYYMMDD_HHMMSS.wav`).
- Uma notificação sutil com botão direto para abrir a pasta garante fluxo de trabalho ágil para Premiere, DaVinci Resolve, CapCut e Audacity.

### 🎨 3. UI Premium & Pílula Flutuante Vertical
- Interface inspirada no design minimalista da Apple Store e Dark Obsidian.
- **Pílula Flutuante Vertical**: Posicionada discretamente no canto da tela, sem roubar o foco da janela ativa.
- **Micro-ondas sonoras animadas**: Glow roxo/ciano para Ditado IA e vermelho vibrante para Gravação Studio.
- Sistema de abas segmentadas: *Ditado & IA*, *Gravador Studio*, *Pílula & Sistema* e *Licença Comercial*.

### 🔒 4. Sistema Comercial de Licenciamento Integrado
- Proteção criptográfica forte com assinatura **HMAC-SHA256**.
- Validação por **Machine Fingerprint** (amarração ao hardware do dispositivo do cliente, prevenindo compartilhamento indevido).
- Diálogo elegante de ativação no primeiro uso: sem chave válida, o aplicativo não permite acesso, viabilizando vendas seguras na nuvem (Hotmart, Kiwify, Eduzz, Stripe, Gumroad).

### 🌐 5. Compatibilidade Multiplataforma Total
- Arquitetura limpa com abstração por adaptadores (`platform_adapter.py`):
  - **Windows 10 / 11**: Win32 API nativa, injeção de teclas por virtual codes, sons sintetizados em memória.
  - **macOS (Intel & Apple Silicon)**: Colagem via `pbcopy` e AppleScript `osascript`, sons nativos do sistema (`afplay`), `LaunchAgents`.
  - **Linux (X11 & Wayland)**: Colagem via `wl-copy`/`xclip` + `xdotool`, áudio via `paplay`/`aplay`.

---

## 💼 Guia do Vendedor: Como Monetizar e Gerar Licenças

Como administrador/vendedor do NexFlow, você possui a ferramenta exclusiva de emissão de licenças `keygen.py`:

### Gerando Chaves de Licença para Clientes

```bash
# Gerar 1 licença comercial PRO vitalícia:
python keygen.py -c 1 -t PRO

# Gerar 10 licenças em lote para importação no CRM / plataforma de vendas:
python keygen.py -c 10 -t PRO -o licenças_vendidas.txt

# Gerar licença com validade de 30 dias (formato assinatura):
python keygen.py -c 1 -t PRO --days 30

# Validar se uma chave informada pelo cliente é autêntica:
python keygen.py --verify NEXFLOW-PRO-XXXX-XXXX-XXXX-XXXX-XXXX
```

> **Formato da Chave:** `NEXFLOW-PRO-ABCD-1234-EF56-7890-GH12`
> Cada chave possui assinatura digital que o aplicativo valida instantaneamente off-line ou on-line.

---

## 🚀 Como Distribuir o Executável (.exe)

O NexFlow já vem configurado para empacotamento em arquivo único standalone executável:

1. Dê dois cliques em **`build_exe.bat`**.
2. Escolha a opção **1** (*Arquivo único standalone*).
3. O executável **`NexFlow.exe`** será gerado automaticamente na pasta `dist/`.
4. Suba o `NexFlow.exe` no Google Drive, Dropbox, AWS S3 ou GitHub Releases e compartilhe o link de download na sua página de vendas.
5. Quando o cliente baixar e abrir o programa pela primeira vez, a tela de ativação da licença será exibida solicitando a chave que você forneceu.

---

## 📥 Instalação para Desenvolvedores (Código-Fonte)

Caso queira executar a partir do código-fonte:

```bash
# 1. Clone ou baixe o projeto:
git clone https://github.com/CarlosCHD1/nexflow.git
cd nexflow

# 2. Crie e ative um ambiente virtual:
python -m venv venv
.\venv\Scripts\activate   # No Windows
# source venv/bin/activate # No Mac/Linux

# 3. Instale as dependências:
pip install -r requirements.txt

# 4. Inicie o NexFlow Pro:
python app.py
```

---

## ⌨️ Atalhos Padrão de Produtividade

| Atalho | Função | Descrição |
| :--- | :--- | :--- |
| **`CapsLock`** | **Ditado IA Inteligente** | Pressione para começar a falar; pressione novamente para transcrever e colar no cursor. |
| **`Alt + A`** | **Gravador Studio 48kHz** | Grava áudio com fidelidade acústica máxima e salva direto na pasta de conteúdos. |
| **`Ctrl + CapsLock`** | **Pausar / Retomar Ditado** | Alterna o Caps Lock entre função de ditado ou caixa alta normal do teclado. |

---

## 📂 Arquitetura do Software

```text
NexFlow/
├── assets/                  # Identidade visual, logotipo 3D e ícones do sistema
│   ├── icon.ico             # Ícone do executável Windows
│   ├── logo.png             # Logotipo oficial em alta resolução
│   ├── icon_32.png          # Ícone para pílula e bandeja
│   └── icon_64.png          # Ícone para janelas e diálogos
├── app.py                   # Interface Gráfica Principal (Tkinter Dark Obsidian Apple-style)
├── audio_recorder.py        # Módulo de Captura de Áudio (16kHz ditado / 48kHz Studio)
├── floating_pill.py         # Pílula Flutuante Vertical e indicador de status visual
├── transcriber.py           # Motor de Transcrição Whisper + Reescrita IA (Groq / Local)
├── licensing.py             # Sistema Criptográfico de Licença e Machine Fingerprint
├── keygen.py                # Gerador CLI de Licenças Comerciais para o Vendedor
├── platform_adapter.py      # Camada de Compatibilidade Windows / macOS / Linux
├── config.py                # Gerenciador de Configurações e Persistência JSON
├── win32_utils.py           # Utilitários de Baixo Nível para Windows (Win32 Hooks & Sounds)
├── build_exe.bat            # Script de compilação automatizada com PyInstaller
├── Iniciar_NexFlow.bat      # Inicializador rápido em modo janela
└── Iniciar_Silencioso.vbs   # Inicializador silencioso em segundo plano para o Startup
```

---

## 🛡️ Privacidade e Segurança

- Os áudios ditados são processados em streaming volátil de memória e descartados após a digitação.
- As gravações do modo Studio são armazenadas exclusivamente de forma local no seu disco rígido.
- Nenhuma informação pessoal ou registro de digitação é enviado para servidores de terceiros além do endpoint de IA configurado por você.

---

<p align="center">
  Desenvolvido com excelência técnica para máxima velocidade e retenção de fluxo de trabalho.<br>
  <strong>NexFlow Pro &copy; 2026. Todos os direitos reservados.</strong>
</p>
