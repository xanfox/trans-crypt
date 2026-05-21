import os
import config

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
    """Remove caracteres invisíveis (RTL, LTR) do texto exportado do WhatsApp."""
    for c in config.UNICODE_LIXO:
        txt = txt.replace(c, "")
    return txt.strip()


def formatar_nome_display(pasta_cliente):
    """Retorna o nome limpo e formatado do cliente para exibição na interface HTML.
    
    Aplica as mesmas regras de limpeza do Step 0 diretamente sobre o nome da
    pasta, eliminando prefixos do WhatsApp, tags de qualificação, datas
    duplicadas e formatando a data de nascimento com barras (DD/MM/AAAA).
    
    Args:
        pasta_cliente (str): Caminho para a pasta do cliente.
        
    Returns:
        str: Nome limpo para exibição (ex: 'Stefan Frederick Toledo - 21/10/1995').
    """
    import re

    PREFIXOS = [
        "conversa do whatsapp com ",
        "whatsapp chat with ",
        "whatsapp chat - ",
        "lead ",
        "consulente ",
        "fr ",
    ]

    nome = os.path.basename(pasta_cliente.rstrip('/\\'))

    # Remove prefixos iterativamente (case-insensitive)
    alterou = True
    while alterou:
        alterou = False
        lower = nome.lower()
        for prefixo in PREFIXOS:
            if lower.startswith(prefixo):
                nome = nome[len(prefixo):].strip()
                alterou = True
                break

    # Detecta e formata data no final, eliminando duplicatas
    # Aceita DD_MM_AAAA, DD-MM-AAAA ou DD/MM/AAAA (pode aparecer mais de uma vez)
    match = re.search(r'^(.*?)\s*((?:\d{2}[-_/]\d{2}[-_/]\d{4}\s*)+)$', nome)
    if match:
        nome_pessoa = match.group(1).strip()
        # Pega apenas a PRIMEIRA data encontrada (elimina duplicatas)
        primeira_data = re.search(r'\d{2}[-_/]\d{2}[-_/]\d{4}', match.group(2))
        if primeira_data:
            # Normaliza para DD/MM/AAAA (formato de leitura humana)
            data_fmt = re.sub(r'[-_]', '/', primeira_data.group(0))
            nome = f"{nome_pessoa} - {data_fmt}"

    return nome.strip() or os.path.basename(pasta_cliente.rstrip('/\\'))
