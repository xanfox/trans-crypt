"""
step0.py — Extração e Mesclagem de Backups do WhatsApp
=======================================================

Responsabilidade:
    Este é o primeiro passo do pipeline do TransCrypt. Ele gerencia a entrada
    de dados brutos na forma de arquivos .zip exportados diretamente do WhatsApp.

Fluxo de execução:
    1. Escaneia a pasta `clientes/` em busca de qualquer arquivo .zip.
    2. Agrupa os zips que pertencem ao mesmo cliente (incluindo duplicatas como
       "arquivo (1).zip", "arquivo (2).zip") usando o nome como chave.
    3. Para cada cliente, extrai o conteúdo do(s) zip(s) em uma área temporária.
    4. Distribui os arquivos:
       - Arquivos .txt (histórico de chat) → passam pela mesclagem cronológica.
       - Mídias (áudios .opus, imagens, vídeos) → copiadas para a pasta do cliente.
    5. Mescla todos os históricos de chat encontrados (incluindo o _chat.txt já
       existente na pasta, caso haja), removendo mensagens duplicadas e
       ordenando tudo em ordem cronológica.
    6. Salva o resultado unificado como `_chat.txt` na pasta do cliente.
    7. Move os arquivos .zip originais para `clientes/_zips_processados/` para
       evitar reprocessamento futuro.

Tags de nome reconhecidas (removidas automaticamente do nome do cliente):
    - "Conversa do WhatsApp com "  → padrão Android
    - "WhatsApp Chat with "        → padrão iOS (inglês)
    - "WhatsApp Chat - "           → padrão iOS (alternativo)
    - "Lead "                      → contato que ainda não é cliente
    - "Consulente "                → cliente com pelo menos 1 atendimento
    - "FR "                        → lead qualificado via Free Read (leitura gratuita)

Formato de saída de nomes de pasta:
    - Sem data de nascimento: `Marcelo Rubem Paiva`
    - Com data de nascimento:  `Marcelo Rubem Paiva - 15_03_1985`
"""

import os
import re
import shutil
import zipfile
from datetime import datetime
from whatsapp_parser import parse_chat_whatsapp, salvar_chat_whatsapp

# ================= CONFIGURAÇÃO DE PREFIXOS =================
# Lista de prefixos que devem ser removidos do nome do arquivo para obter
# o nome limpo do cliente. A comparação é feita em lowercase para ser
# case-insensitive, mas o nome final preserva o case original do arquivo.
PREFIXES = [
    "conversa do whatsapp com ",
    "whatsapp chat with ",
    "whatsapp chat - ",
    "lead ",
    "consulente ",
    "fr "
]

# ================= FUNÇÕES =================

def clean_client_name(raw_name):
    """
    Deriva o nome limpo do cliente a partir do nome bruto do arquivo .zip.

    O processo ocorre em 3 etapas:
        1. Remove a extensão .zip e sufixos de cópia como " (1)", " (2)".
        2. Remove iterativamente todos os prefixos conhecidos (tags do WhatsApp).
        3. Detecta e reformata a data de nascimento no final do nome, se houver.

    Args:
        raw_name (str): Nome bruto do arquivo .zip (ex: "Conversa do WhatsApp
                        com Lead FR Marcelo Rubem Paiva 15_03_1985 (1).zip").

    Returns:
        str: Nome limpo do cliente (ex: "Marcelo Rubem Paiva - 15_03_1985").
    """
    # Etapa 1: Remove sufixos de cópia do sistema operacional e a extensão .zip
    name = re.sub(r' \(\d+\)\.zip$', '', raw_name)
    name = re.sub(r'\.zip$', '', name)

    # Etapa 2: Remove os prefixos de forma iterativa (um prefixo pode esconder outro)
    # Exemplo: "Conversa do WhatsApp com Lead FR João" → remove "Conversa do WhatsApp com "
    # → remove "Lead " → remove "FR " → "João"
    changed = True
    while changed:
        changed = False
        lower_name = name.lower()
        for prefix in PREFIXES:
            if lower_name.startswith(prefix):
                name = name[len(prefix):].strip()
                changed = True
                break

    # Etapa 3: Detecta data de nascimento no final do nome
    # Aceita os formatos: DD_MM_YYYY, DD-MM-YYYY, DD/MM/YYYY
    match = re.search(r'^(.*?)\s*((?:\d{2}[-_/]\d{2}[-_/]\d{4}\s*)+)$', name)
    if match:
        person_name = match.group(1).strip()
        dates_raw = match.group(2).strip()
        date_match = re.search(r'\d{2}[-_/]\d{2}[-_/]\d{4}', dates_raw)
        if date_match:
            # Normaliza separadores para underscore e formata como "Nome - DD_MM_AAAA"
            date_str = date_match.group(0).replace('-', '_').replace('/', '_')
            return f"{person_name} - {date_str}"

    return name.strip()


def merge_messages(mensagens_listas):
    """
    Mescla múltiplas listas de mensagens em uma única lista cronológica e sem duplicatas.

    A deduplicação é feita comparando a tupla (data, hora, autor, conteudo).
    Mensagens idênticas nesse quadruplo (que aparecem em múltiplos backups parciais
    do mesmo período) são mantidas apenas uma vez.

    Após a deduplicação, as mensagens são reordenadas do mais antigo para o mais
    recente e seus IDs são recalculados sequencialmente.

    Args:
        mensagens_listas (list[list[dict]]): Lista de listas de mensagens.
            Cada lista interna é o resultado de um `parse_chat_whatsapp()`.

    Returns:
        list[dict]: Lista única de mensagens, ordenada cronologicamente,
                    com IDs atualizados de 1 a N.
    """
    # Achata todas as listas em uma única lista
    todas = []
    for msgs in mensagens_listas:
        todas.extend(msgs)

    # Deduplicação: usa a tupla (data, hora, autor, conteudo) como chave única
    unicas = {}
    for msg in todas:
        key = (msg['data'], msg['hora'], msg['autor'], msg['conteudo'])
        if key not in unicas:
            unicas[key] = msg

    lista_unicas = list(unicas.values())

    # Ordenação cronológica
    def get_datetime(msg):
        try:
            return datetime.strptime(f"{msg['data']} {msg['hora']}", "%d/%m/%Y %H:%M")
        except ValueError:
            # Mensagens com formato de data inválido vão para o início da lista
            return datetime.min

    lista_unicas.sort(key=get_datetime)

    # Recalcula os IDs sequencialmente após a mesclagem
    for i, msg in enumerate(lista_unicas):
        msg['id'] = i + 1

    return lista_unicas


def process_zips(base_dir="clientes"):
    """
    Função principal que orquestra todo o pipeline de extração.

    Itera sobre todos os arquivos .zip encontrados na pasta base, os agrupa
    por cliente e executa o fluxo completo de extração, mesclagem e arquivamento.

    Args:
        base_dir (str): Caminho para a pasta base de clientes.
                        Padrão: "clientes" (relativo ao diretório de execução).
    """
    if not os.path.exists(base_dir):
        print(f"Pasta '{base_dir}' não encontrada.")
        return

    arquivos = os.listdir(base_dir)
    zips = [f for f in arquivos if f.lower().endswith('.zip')]

    if not zips:
        print("Nenhum arquivo .zip encontrado na pasta de clientes para extração.")
        return

    print(f"\nEncontrados {len(zips)} arquivos .zip. Iniciando Step 0...\n")

    # Pasta de destino para os zips já processados (evita reprocessamento)
    pasta_processados = os.path.join(base_dir, "_zips_processados")
    os.makedirs(pasta_processados, exist_ok=True)

    # Pasta temporária para extração dos zips antes de distribuir os arquivos
    pasta_temp = os.path.join(base_dir, "_temp_zips")
    os.makedirs(pasta_temp, exist_ok=True)

    # Agrupa os zips pelo nome limpo do cliente
    # Ex: "Conversa...Marcelo.zip" e "Conversa...Marcelo (1).zip" → mesmo cliente
    clientes_map = {}
    for z in zips:
        nome_cliente = clean_client_name(z)
        if nome_cliente not in clientes_map:
            clientes_map[nome_cliente] = []
        clientes_map[nome_cliente].append(z)

    for nome_cliente, zips_cliente in clientes_map.items():
        print(f"📦 Processando cliente: {nome_cliente} ({len(zips_cliente)} zips)")

        pasta_destino = os.path.join(base_dir, nome_cliente)
        os.makedirs(pasta_destino, exist_ok=True)

        listas_mensagens = []

        # Se já existe um _chat.txt na pasta do cliente (de um processamento anterior),
        # ele é carregado primeiro para ser mesclado com os novos backups.
        caminho_chat_existente = os.path.join(pasta_destino, "_chat.txt")
        if os.path.exists(caminho_chat_existente):
            print(f"  ➜ Encontrado _chat.txt existente. Ele será mesclado.")
            listas_mensagens.append(parse_chat_whatsapp(caminho_chat_existente))

        for z_filename in zips_cliente:
            caminho_zip = os.path.join(base_dir, z_filename)
            temp_extracao = os.path.join(pasta_temp, z_filename)
            os.makedirs(temp_extracao, exist_ok=True)

            try:
                with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                    zip_ref.extractall(temp_extracao)

                # Classifica e distribui cada arquivo extraído do zip
                for root, _, files in os.walk(temp_extracao):
                    for file in files:
                        caminho_arq_temp = os.path.join(root, file)
                        if file.endswith('.txt'):
                            # Arquivo de histórico de chat → entra na mesclagem
                            listas_mensagens.append(parse_chat_whatsapp(caminho_arq_temp))
                        else:
                            # Mídias (áudios, imagens, vídeos) → copia para a pasta do cliente
                            # Não sobrescreve arquivos já existentes para evitar corrupção
                            caminho_arq_destino = os.path.join(pasta_destino, file)
                            if not os.path.exists(caminho_arq_destino):
                                shutil.copy2(caminho_arq_temp, caminho_arq_destino)

            except zipfile.BadZipFile:
                print(f"  ❌ Erro: O arquivo {z_filename} está corrompido ou não é um zip válido.")
                continue

        # Mescla e persiste o histórico unificado
        if listas_mensagens:
            print(f"  ➜ Mesclando e removendo duplicidades dos históricos de chat...")
            mensagens_unificadas = merge_messages(listas_mensagens)
            salvar_chat_whatsapp(mensagens_unificadas, caminho_chat_existente)
            print(f"  ➜ {len(mensagens_unificadas)} mensagens únicas salvas no histórico consolidado.")

        # Limpeza: remove a pasta temporária e arquiva os zips originais
        for z_filename in zips_cliente:
            temp_extracao = os.path.join(pasta_temp, z_filename)
            if os.path.exists(temp_extracao):
                shutil.rmtree(temp_extracao)

            caminho_zip = os.path.join(base_dir, z_filename)
            destino_zip_processado = os.path.join(pasta_processados, z_filename)

            # Se um zip com o mesmo nome já existe em _zips_processados, substitui
            if os.path.exists(destino_zip_processado):
                os.remove(destino_zip_processado)
            shutil.move(caminho_zip, destino_zip_processado)

        print(f"  ✅ Concluído: {nome_cliente}")

    # Remove a pasta temporária global ao final de tudo
    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

    print("\n✔ ETAPA 0 FINALIZADA: Todos os zips foram extraídos e mesclados com sucesso!")


# ================= ENTRY POINT =================

def run():
    """Ponto de entrada chamado pelo main.py."""
    print("=== ETAPA 0 | Extração e Mesclagem de Backups (Zips) ===")
    process_zips()


if __name__ == "__main__":
    run()
