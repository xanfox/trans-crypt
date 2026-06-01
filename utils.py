import csv
import os
import unicodedata
from pathlib import Path
import config


# ================= PREFIXOS DE NOME (fonte única) =================

# Prefixos mínimos garantidos mesmo sem o CSV (só os que o próprio WhatsApp gera).
_PREFIXES_FALLBACK = [
    "conversa do whatsapp com ",
    "whatsapp chat with ",
    "whatsapp chat - ",
]

# Caminho do CSV na raiz do projeto (mesmo diretório onde utils.py está).
_CSV_PREFIXOS = Path(__file__).parent / "prefixos.csv"


def _carregar_prefixos() -> list[str]:
    """Lê prefixos.csv e retorna a lista de prefixos em lowercase.

    O CSV deve ter (pelo menos) uma coluna chamada 'prefixo'.
    Linhas em branco e comentários (#) são ignorados.
    Se o arquivo não existir, retorna os prefixos padrão do WhatsApp.

    Formato esperado::

        prefixo,descricao
        lead ,Contato pre-cliente
        consulente ,Cliente com atendimento

    Returns:
        list[str]: Lista de strings em lowercase prontas para comparação.
    """
    if not _CSV_PREFIXOS.exists():
        print(
            f"⚠️  prefixos.csv não encontrado em {_CSV_PREFIXOS}. "
            "Usando apenas os prefixos padrão do WhatsApp."
        )
        return _PREFIXES_FALLBACK[:]

    prefixos = []
    with open(_CSV_PREFIXOS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("prefixo", "").lstrip()  # preserva espaço final intencional
            if raw and not raw.startswith("#"):
                prefixos.append(raw.lower())

    if not prefixos:
        return _PREFIXES_FALLBACK[:]

    return prefixos


# Lista carregada uma única vez no import — consumida por step0.py e utils.py.
PREFIXES_WHATSAPP: list[str] = _carregar_prefixos()

def escolher_pasta_cliente():
    """Exibe um menu para escolher o diretório do cliente e retorna o caminho absoluto/relativo."""
    if not os.path.exists(config.PASTA_BASE):
        os.makedirs(config.PASTA_BASE)
        print(f"\n⚠️  A pasta base '{config.PASTA_BASE}' foi criada agora!")
        print("👉 Por favor, coloque as pastas exportadas do WhatsApp dentro dela e rode o programa novamente.")
        exit(0)

    pastas = [
        d for d in os.listdir(config.PASTA_BASE)
        if os.path.isdir(os.path.join(config.PASTA_BASE, d))
        and d not in (config.PASTA_ZIPS_PROCESSADOS, config.PASTA_TEMP_ZIPS)
    ]

    if not pastas:
        print(f"Nenhuma pasta encontrada em {config.PASTA_BASE}")
        exit(1)

    print("\nSelecione a pasta do cliente:\n")
    for i, pasta in enumerate(pastas, 1):
        print(f"[{i}] {pasta}")

    while True:
        escolha = input("\nDigite o número: ").strip()
        if escolha.isdigit():
            idx = int(escolha) - 1
            if 0 <= idx < len(pastas):
                return os.path.join(config.PASTA_BASE, pastas[idx])
        print("Opção inválida.")

def escolher_chat_txt(pasta_cliente, auto=False):
    """Exibe um menu para escolher o arquivo .txt contendo o histórico do chat na pasta do cliente.

    Inclui explicitamente `_chat.txt` (gerado pelo Step 0), mas exclui o
    `historico_consolidado.txt` (gerado pelo Step 2) para evitar que o pipeline
    consuma o próprio resultado como entrada.
    """
    arquivos = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(".txt")
        and f != config.ARQUIVO_HISTORICO   # exclui historico_consolidado.txt
        and f != "historico_anonimizado.txt" # exclui saída do Step 4
    ]

    if not arquivos:
        print("Nenhum arquivo de chat encontrado na pasta.")
        exit(1)

    if auto or len(arquivos) == 1:
        # Prefere _chat.txt (gerado pelo Step 0) quando há múltiplos .txt em modo auto
        if config.ARQUIVO_CHAT in arquivos:
            return os.path.join(pasta_cliente, config.ARQUIVO_CHAT)
        return os.path.join(pasta_cliente, arquivos[0])

    print("\nSelecione o arquivo de chat:\n")
    for i, arq in enumerate(arquivos, 1):
        print(f"[{i}] {arq}")

    while True:
        escolha = input("\nNúmero: ").strip()
        if escolha.isdigit():
            idx = int(escolha) - 1
            if 0 <= idx < len(arquivos):
                return os.path.join(pasta_cliente, arquivos[idx])
        print("Opção inválida.")

def buscar_transcricao(pasta_transcricoes, arquivo_midia):
    """Busca o arquivo de transcrição (.txt) correspondente a um arquivo de mídia.

    Função centralizada usada pelo Step 2 e Step 3 para evitar duplicação de código.

    Args:
        pasta_transcricoes (str): Caminho para a pasta `_transcricoes/` do cliente.
        arquivo_midia (str): Nome do arquivo de mídia (ex: "PTT-20240312.opus").

    Returns:
        str | None: Conteúdo da transcrição ou None se não encontrada.
    """
    base = os.path.splitext(arquivo_midia)[0]
    caminho = os.path.join(pasta_transcricoes, base + ".txt")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    return None

def limpar_unicode(txt):
    """Remove caracteres invisíveis (RTL, LTR) e normaliza fontes Unicode decorativas.

    Além dos caracteres de controle do WhatsApp (RTL, BOM, etc.), converte as
    chamadas "fontes Unicode" — blocos de caracteres matemáticos/cursivos como
    𝒞𝓀𝒾𝓈𝓉𝒾𝓃𝓎 — de volta para suas letras latinas normais usando NFKD.
    Isso evita que nomes estilizados quebrem o matching de nomes e o NER.
    """
    # Etapa 1: Remove caracteres de controle do WhatsApp (RTL, BOM, etc.)
    for c in config.UNICODE_LIXO:
        txt = txt.replace(c, "")

    # Etapa 2: NFKC converte "fontes Unicode" decorativas para letras normais
    # (𝒞𝓀𝒾𝓈𝓉𝒾𝓃𝓎 → Ckistiny, 𝔽𝕠𝕟𝕥𝕖 → Fonte) preservando acentos do português
    # (ã, é, ç, etc.) — NFKC recompõe os combining marks latinos automaticamente.
    txt = unicodedata.normalize("NFKC", txt)

    return txt.strip()


def formatar_nome_display(pasta_cliente):
    """Retorna o nome limpo e formatado do cliente para exibição na interface HTML.
    
    Remove prefixos do WhatsApp, tags de qualificação, datas duplicadas e
    formata a data de nascimento com barras (DD/MM/AAAA).
    
    Args:
        pasta_cliente (str): Caminho para a pasta do cliente.
        
    Returns:
        str: Nome limpo (ex: 'Stefan Frederick Toledo - 21/10/1995').
    """
    import re

    nome = os.path.basename(pasta_cliente.rstrip('/\\'))

    # Remove prefixos iterativamente (case-insensitive) — lista vem de prefixos.csv
    alterou = True
    while alterou:
        alterou = False
        lower = nome.lower()
        for prefixo in PREFIXES_WHATSAPP:
            if lower.startswith(prefixo):
                nome = nome[len(prefixo):].strip()
                alterou = True
                break

    # Encontra TODAS as datas no formato DD_MM_AAAA / DD-MM-AAAA / DD/MM/AAAA
    PADRAO_DATA = re.compile(r'\d{2}[-_/]\d{2}[-_/]\d{4}')
    datas = PADRAO_DATA.findall(nome)

    if datas:
        # Remove todas as ocorrências de data do nome (elimina duplicatas)
        nome_sem_data = PADRAO_DATA.sub('', nome)
        # Remove emojis e caracteres especiais (mantém letras, acentos, números, espaços, hífens)
        nome_sem_data = re.sub(r'[^\w\s\-\/]', '', nome_sem_data)
        # Limpa espaços extras resultantes da remoção
        nome_sem_data = re.sub(r'\s+', ' ', nome_sem_data).strip().rstrip('-').strip()
        # Formata apenas a primeira data com barras: 21_10_1995 → 21/10/1995
        data_fmt = re.sub(r'[-_]', '/', datas[0])
        nome = f"{nome_sem_data} - {data_fmt}"
    else:
        # Remove emojis e caracteres especiais caso não haja data
        nome = re.sub(r'[^\w\s\-\/]', '', nome)
        nome = re.sub(r'\s+', ' ', nome).strip().rstrip('-').strip()

    return nome or os.path.basename(pasta_cliente.rstrip('/\\'))
