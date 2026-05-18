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
    """Exibe um menu para escolher o arquivo .txt contendo o histórico do chat na pasta do cliente."""
    arquivos = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(".txt") and f != config.ARQUIVO_HISTORICO and not f.startswith("_")
    ]

    if not arquivos:
        print("Nenhum arquivo de chat encontrado na pasta.")
        exit(1)
        
    if auto or len(arquivos) == 1:
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

def limpar_unicode(txt):
    """Remove caracteres invisíveis (RTL, LTR) do texto exportado do WhatsApp."""
    for c in config.UNICODE_LIXO:
        txt = txt.replace(c, "")
    return txt.strip()
