import os
import json
import config
import utils
from whatsapp_parser import parse_chat_whatsapp

# ================= SAÍDA =================
def gerar_historico(pasta_cliente, mensagens_chat, arquivo_saida=config.ARQUIVO_HISTORICO, 
                    arquivo_edits="conferencia_edits.json", pasta_transcricoes=config.PASTA_TRANSCRICOES):
    caminho_saida = os.path.join(pasta_cliente, arquivo_saida)
    caminho_edits = os.path.join(pasta_cliente, arquivo_edits)
    pasta_trans = os.path.join(pasta_cliente, pasta_transcricoes)

    arquivos_midia = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)
    ]

    edits = {"deleted_ids": [], "edited_texts": {}}
    if os.path.exists(caminho_edits):
        try:
            with open(caminho_edits, "r", encoding="utf-8") as f:
                edits = json.load(f)
        except Exception as e:
            print(f"\\n⚠️ AVISO: {caminho_edits} corrompido ({e}).")
            print("Consolidando sem as edições anteriores para evitar falha crítica do sistema.")

    # Normaliza deleted_ids para sempre trabalhar com int, independente de como foram salvos.
    deleted_ids = {int(x) for x in edits.get("deleted_ids", [])}

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("===== HISTÓRICO CONSOLIDADO =====\n\n")

        for m in mensagens_chat:
            msg_id = m["id"]
            msg_id_str = str(msg_id)

            # 1. Mensagens deletadas
            if msg_id in deleted_ids:
                f.write(f"{m['data']} {m['hora']} — {m['autor']} — #id:{msg_id}\n[Mensagem Apagada pelo Revisor]\n\n")
                continue

            # 2. Aplica edição de texto
            conteudo = m["conteudo"]
            if msg_id_str in edits.get("edited_texts", {}):
                conteudo = edits["edited_texts"][msg_id_str]

            # 3. Verifica se tem mídia anexada para puxar a transcrição
            arquivo_encontrado = None
            for arq in arquivos_midia:
                if arq in conteudo:
                    arquivo_encontrado = arq
                    break

            f.write(f"{m['data']} {m['hora']} — {m['autor']} — #id:{msg_id}\n")

            if arquivo_encontrado:
                trans = utils.buscar_transcricao(pasta_trans, arquivo_encontrado)
                if trans:
                    f.write(f"[MÍDIA: {arquivo_encontrado}]\n")
                    f.write(f"--- TRANSCRIÇÃO ---\n{trans}\n-------------------\n\n")
                else:
                    f.write(f"{conteudo}\n\n")
            else:
                f.write(f"{conteudo}\n\n")

    print(f"\n✔ Histórico consolidado criado em:\n{caminho_saida}")

# ================= MAIN =================
def run(pasta_cliente=None, auto=False, **kwargs):
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()

    chat = utils.escolher_chat_txt(pasta_cliente, auto=auto)

    print("\n📖 Processando chat...")
    mensagens_chat = parse_chat_whatsapp(chat)

    gerar_historico(pasta_cliente, mensagens_chat, **kwargs)

if __name__ == "__main__":
    run()
