<p align="center">
  <img src="assets/logo.png" width="150" alt="WisperFlow Free Logo"/>
</p>

<h1 align="center">WisperFlow Free</h1>

<p align="center">
  <strong>A alternativa livre, gratuita e ultrarrápida ao Wispr Flow para Windows.</strong><br>
  Ditado por voz inteligente com IA diretamente no cursor de qualquer aplicativo, navegador ou campo de texto.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Plataforma-Windows%2010%20%7C%2011-0078D6?logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/Motor-Groq%20Cloud%20%2B%20Whisper-F55036" alt="Groq"/>
  <img src="https://img.shields.io/badge/Licença-MIT-10B981" alt="MIT License"/>
</p>

---

## ✨ O que é o WisperFlow Free?

O **WisperFlow Free** foi desenvolvido para quem quer economizar tempo e raciocínio ao digitar. Com apenas um toque no teclado, você fala naturalmente o que está pensando e a sua fala é transcrita, corrigida e formatada instantaneamente no campo onde você está trabalhando — seja no WhatsApp Web, Word, Notion, IDEs de programação, navegadores ou campos de busca do sistema.

### 🌟 Principais Recursos

- ⌨️ **Ditado Inteligente por 1 Tecla (`CapsLock`)**: Pressione `CapsLock`, fale e pressione novamente (ou faça uma pausa). O texto é transcrito e digitado diretamente onde seu cursor estiver piscando.
- 🎧 **Gravador de Áudio Studio (`Alt + A`)**: Pressione `Alt + A` para gravar áudios de altíssima fidelidade (48.000 Hz, 16-bit PCM WAV broadcast) que são salvos automaticamente na sua pasta `Vídeos/Conteúdos/áudios/` com data e hora. Ideal para criadores de conteúdo, podcasts e edição de vídeo (Premiere, DaVinci Resolve, CapCut).
- 🔄 **Pausar / Retomar Ditado com `Ctrl + CapsLock`**: Quando precisar usar o Caps Lock tradicional para letras maiúsculas, basta apertar `Ctrl + CapsLock` para alternar o modo.
- 🧠 **Motor Híbrido com IA de Ponta**:
  - **Groq Cloud (Whisper Turbo + LLM Inteligente)**: Transcrição em ~400ms com reescrita que remove vícios de fala (*"ééé"*, *"tipo"*, repetições, gagueiras) e pontua automaticamente.
  - **Fallback Local (Faster-Whisper CUDA)**: Funciona 100% offline se estiver sem internet ou preferir processamento local na sua placa de vídeo.
- 📱 **Pílula Flutuante Vertical & Discreta**: Interface moderna, compacta e translúcida que exibe ondas de áudio dinâmicas sem roubar o foco da sua janela ativa (roxo para ditado, vermelho para gravação de áudio studio).
- ⚡ **Nenhum Rastreamento ou Assinatura**: 100% gratuito e de código aberto sob a licença MIT.

---

## 🚀 Como Começar

### Opção 1: Usando o Executável (.exe)
1. Baixe o executável mais recente na aba [Releases](../../releases).
2. Execute o `WisperFlow.exe`.
3. Na primeira inicialização, insira sua chave gratuita da Groq (veja abaixo como gerar em 1 minuto) ou selecione o modo local offline.
4. Pronto! O app fica rodando em segundo plano.

### Opção 2: Executando a partir do Código Fonte (Python)

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/SEU-USUARIO/wisperflow-free.git
   cd wisperflow-free
   ```

2. **Crie e ative um ambiente virtual (recomendado):**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Inicie a aplicação:**
   ```bash
   python app.py
   ```

---

## 🔑 Como Obter sua Chave Gratuita da Groq Cloud

A Groq oferece cotas gratuitas generosas e extremamente velozes para transcrição de áudio e modelos de linguagem:

1. Acesse o console da Groq: **[console.groq.com/keys](https://console.groq.com/keys)**
2. Crie uma conta gratuita (pode usar o login com Google ou GitHub).
3. Clique em **"Create API Key"**, copie a chave gerada (começa com `gsk_...`).
4. Abra a tela de configurações do **WisperFlow Free**, cole a chave no campo indicado e clique em **"Salvar Chave"**.

---

## 🛠️ Como Gerar seu Próprio Executável (.exe)

O repositório já inclui um script automatizado com PyInstaller:

1. Dê dois cliques no arquivo `build_exe.bat`.
2. Escolha a opção **1** (Arquivo único standalone) ou **2** (Pasta portátil).
3. O executável com o ícone oficial será gerado automaticamente na pasta `dist/`.

---

## 📂 Estrutura do Projeto

```text
wisperflow-free/
├── assets/                  # Logotipo e ícones do aplicativo (.ico, .png)
│   ├── icon.ico
│   ├── logo.png
│   └── icon_64.png
├── app.py                   # Interface gráfica principal e orquestrador
├── audio_recorder.py        # Gravação de áudio nativa via WinMM (ctypes)
├── floating_pill.py         # Pílula flutuante vertical com renderização Pillow
├── transcriber.py           # Cliente Groq Cloud + Faster-Whisper local
├── win32_utils.py           # Hooks de teclado de baixo nível e injeção de texto
├── config.py                # Gerenciador de configurações e persistência
├── config.example.json      # Modelo de configuração para novos usuários
├── build_exe.bat            # Script para compilar o executável com PyInstaller
├── Iniciar_Silencioso.vbs   # Inicializador em segundo plano para o Windows
├── requirements.txt         # Lista de dependências Python
└── LICENSE                  # Licença MIT
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.
