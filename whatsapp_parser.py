"""
whatsapp_parser.py — Parser e Serializador de Histórico do WhatsApp
====================================================================

Responsabilidade:
    Módulo central de leitura e escrita do formato de texto do WhatsApp.
    É utilizado por step0.py (mesclagem), step2.py (consolidação) e step3.py (HTML).

Formatos de chat suportados:
    - Padrão A (Android): `DD/MM/AAAA HH:MM - Autor: Mensagem`
    - Padrão B (iOS):     `[DD/MM/AAAA HH:MM:SS] Autor: Mensagem`

Formato de saída (salvar_chat_whatsapp):
    Sempre grava no Padrão A para garantir consistência entre todos os arquivos
    gerados internamente pelo TransCrypt, independente da origem do backup.
"""

import re
from datetime import datetime
from utils import limpar_unicode

# Padrão A: 12/03/2024 15:30 - Autor: Mensagem  (Android)
_PADRAO_A = re.compile(r"^(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}) - (.*?): (.*)")

# Padrão B: [12/03/2024 15:30:15] Autor: Mensagem  (iOS)
_PADRAO_B = re.compile(r"^\[(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}:\d{2})\] (.*?): (.*)")


def parse_chat_whatsapp(caminho_chat):
    """
    Lê um arquivo de histórico de chat do WhatsApp e retorna uma lista de mensagens.

    Suporta os formatos Android e iOS automaticamente. Mensagens multi-linha
    (quando o WhatsApp quebra o texto em várias linhas) são corretamente
    concatenadas ao conteúdo da mensagem anterior.

    Args:
        caminho_chat (str): Caminho absoluto ou relativo para o arquivo .txt do chat.

    Returns:
        list[dict]: Lista de dicionários com as chaves:
            - id (int):      Identificador sequencial único da mensagem.
            - data (str):    Data no formato "DD/MM/AAAA".
            - hora (str):    Hora no formato "HH:MM".
            - autor (str):   Nome do remetente.
            - tipo (str):    Sempre "texto" (tipo reservado para extensões futuras).
            - conteudo (str): Texto da mensagem ou nome do arquivo de mídia anexado.
    """
    mensagens = []
    contador_id = 1
    msg_atual = None

    with open(caminho_chat, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = limpar_unicode(linha.rstrip())
            if not linha:
                continue

            # Tenta o Padrão B (iOS) primeiro, depois o Padrão A (Android)
            match = _PADRAO_B.match(linha) or _PADRAO_A.match(linha)

            if match:
                if msg_atual:
                    mensagens.append(msg_atual)

                data, hora, autor, conteudo = match.groups()

                # Normaliza hora do Padrão B (HH:MM:SS) → HH:MM para padronizar
                if len(hora.split(":")) == 3:
                    hora = ":".join(hora.split(":")[:2])

                msg_atual = {
                    "id": contador_id,
                    "data": data,
                    "hora": hora,
                    "autor": autor.strip(),
                    "tipo": "texto",
                    "conteudo": conteudo.strip()
                }
                contador_id += 1
            else:
                # Linha de continuação: anexa à mensagem corrente (mensagem multi-linha)
                if msg_atual:
                    msg_atual["conteudo"] += "\n" + linha.strip()

        # Persiste a última mensagem do arquivo
        if msg_atual:
            mensagens.append(msg_atual)

    return mensagens


def salvar_chat_whatsapp(mensagens, caminho_destino):
    """
    Serializa uma lista de mensagens de volta para o formato de texto do WhatsApp.

    Sempre grava no Padrão A (Android): `DD/MM/AAAA HH:MM - Autor: Mensagem`.
    Este é o formato canônico interno do TransCrypt para todos os `_chat.txt`.

    Args:
        mensagens (list[dict]):  Lista de mensagens no formato retornado por
                                  `parse_chat_whatsapp()`.
        caminho_destino (str):   Caminho onde o arquivo .txt será gravado.
                                  O arquivo é sobrescrito se já existir.
    """
    with open(caminho_destino, "w", encoding="utf-8") as f:
        for msg in mensagens:
            f.write(f"{msg['data']} {msg['hora']} - {msg['autor']}: {msg['conteudo']}\n")
