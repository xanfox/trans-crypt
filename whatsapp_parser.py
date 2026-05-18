import re
from utils import limpar_unicode

def parse_chat_whatsapp(caminho_chat):
    """
    Lê o histórico de chat do WhatsApp e retorna uma lista de dicionários.
    Trata os formatos Android e iOS (chaves com ou sem colchetes e variação de hora).
    """
    mensagens = []
    
    # Padrão A: 12/03/2024 15:30 - Autor: Mensagem
    padrao_a = re.compile(r"^(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}) - (.*?): (.*)")
    
    # Padrão B: [12/03/2024 15:30:15] Autor: Mensagem
    padrao_b = re.compile(r"^\[(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2}:\d{2})\] (.*?): (.*)")

    contador_id = 1
    msg_atual = None

    with open(caminho_chat, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = limpar_unicode(linha.rstrip())
            if not linha:
                continue

            match_b = padrao_b.match(linha)
            match_a = padrao_a.match(linha)
            
            match = match_b or match_a

            if match:
                if msg_atual:
                    mensagens.append(msg_atual)

                data, hora, autor, conteudo = match.groups()
                
                # Se pegou do formato B (hora com segundos), truncamos para HH:MM para padronizar
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
                # Se não é o início de uma nova mensagem, anexa à mensagem atual (quebra de linha)
                if msg_atual:
                    msg_atual["conteudo"] += "\n" + linha.strip()

        # Salva a última mensagem
        if msg_atual:
            mensagens.append(msg_atual)

    return mensagens
