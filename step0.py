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

Prefixos de nome reconhecidos (configuráveis via prefixos.csv na raiz):
     A lista é carregada por utils.py — veja prefixos.csv para personalizar.
     Padrões mínimos garantidos (usados como fallback se o CSV não existir):
      - "Conversa do WhatsApp com "  → padrão Android
      - "WhatsApp Chat with "        → padrão iOS (inglês)
      - "WhatsApp Chat - "           → padrão iOS (alternativo)

Comportamentos adicionais de limpeza:
     - Emojis são removidos automaticamente dos nomes de pasta
     - Caracteres iniciais inválidos ('.', '-', '_', espaço) são descartados
     - Zips sem extensão .zip são detectados automaticamente pelo conteúdo

Formato de saída de nomes de pasta:
    - Sem data de nascimento: `Marcelo Rubem Paiva`
    - Com data de nascimento:  `Marcelo Rubem Paiva - 15_03_1985`
"""

import json
import os
import re
import shutil
import zipfile
from datetime import datetime

import config
import utils
from whatsapp_parser import parse_chat_whatsapp, salvar_chat_whatsapp

# Nomes de pasta reservados pelo próprio Step 0 — nunca devem ser usados como
# pasta de cliente para não corromper a estrutura de diretórios.
NOMES_RESERVADOS = {
    config.PASTA_ZIPS_PROCESSADOS,
    config.PASTA_TEMP_ZIPS,
    "_trash_",
}

# Regex para remover emojis e símbolos Unicode decorativos dos nomes de pasta.
# Cobre os blocos mais comuns de emoji (Emoticons, Símbolos, Transporte, Bandeiras,
# Dingbats, Suplementares) mais o selector de variação e o joiner de largura zero.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FFFF"  # Emoticons, símbolos, pictogramas, transporte
    "\U00002702-\U000027B0"  # Dingbats
    "\u2600-\u2B55"          # Símbolos diversos (sol, lua, etc.)
    "\uFE0F"                # Variation Selector-16 (emoji presentation)
    "\u200D"                # Zero Width Joiner
    "]+",
    flags=re.UNICODE
)

# ================= FUNÇÕES =================

def clean_client_name(raw_name):
    """
    Deriva o nome limpo do cliente a partir do nome bruto do arquivo .zip.

    O processo ocorre em 5 etapas:
        1. Remove a extensão .zip e sufixos de cópia como "(1)", " (2)" (com ou sem espaço).
        2. Remove iterativamente todos os prefixos conhecidos (tags do WhatsApp).
        3. Remove emojis e caracteres decorativos Unicode.
        4. Descarta caracteres iniciais inválidos ('.', '-', '_', espaço) que restam após
           a remoção de prefixos (ex: ". Joice" → "Joice").
        5. Detecta e reformata a data de nascimento no final do nome, se houver.

    Args:
        raw_name (str): Nome bruto do arquivo .zip (ex: "Conversa do WhatsApp
                        com Lead FR Marcelo Rubem Paiva 15_03_1985 (1).zip").

    Returns:
        dict | None: Dicionário com informações do cliente ou None se inválido.
    """
    # Etapa 1: Remove sufixos de cópia do sistema operacional (com ou sem espaço) e a extensão
    name = re.sub(r'\s*\(\d+\)\.zip$', '', raw_name, flags=re.IGNORECASE)
    name = re.sub(r'\.zip$', '', name, flags=re.IGNORECASE)

    # Etapa 1b: Normaliza "fontes Unicode" decorativas (𝒞𝓀𝒾𝓈𝓉𝒾𝓃𝓎 → Ckistiny)
    # para que o matching de prefixos e o nome de pasta sejam sempre legíveis.
    name = utils.limpar_unicode(name)

    # Etapa 2: Remove os prefixos de forma iterativa (lista vem de prefixos.csv via utils)

    tags_found = []
    changed = True
    while changed:
        changed = False
        lower_name = name.lower()
        for prefix in utils.PREFIXES_WHATSAPP:
            if lower_name.startswith(prefix):
                tags_found.append(prefix.strip())
                name = name[len(prefix):].strip()
                changed = True
                break

    # Etapa 3: Remove emojis e símbolos Unicode decorativos
    name = _EMOJI_RE.sub('', name).strip()

    # Etapa 4: Remove caracteres inválidos no início do nome
    # Cobre casos como ". Joice" (ponto sobrando de prefixo) ou "- Nome" etc.
    name = re.sub(r'^[\s.\-_]+', '', name).strip()

    # Etapa 5: Detecta data de nascimento no final do nome
    # Aceita os formatos: DD_MM_YYYY, DD-MM-YYYY, DD/MM/YYYY
    person_name = name
    date_str_formatado = None
    match = re.search(r'^(.*?)\s*((?:\d{2}[-_/]\d{2}[-_/]\d{4}\s*)+)$', name)
    if match:
        person_name = match.group(1).strip()
        # Remove trailing dash from person_name if it exists
        person_name = re.sub(r'\s*-\s*$', '', person_name).strip()
        dates_raw = match.group(2).strip()
        date_match = re.search(r'\d{2}[-_/]\d{2}[-_/]\d{4}', dates_raw)
        if date_match:
            # Normaliza separadores para underscore e formata como "Nome - DD_MM_AAAA"
            date_str = date_match.group(0).replace('-', '_').replace('/', '_')
            name = f"{person_name} - {date_str}"
            date_str_formatado = date_str.replace('_', '/')

    name = name.strip()

    # Etapa 6: Validação — rejeita nomes vazios ou que colidam com pastas reservadas
    if not name or name in NOMES_RESERVADOS:
        return None

    return {
        "nome_pasta": name,
        "nome": person_name,
        "data_nascimento": date_str_formatado,
        "tags_origem": tags_found
    }


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

    # Detecta zips tanto pela extensão '.zip' quanto pelo conteúdo do arquivo.
    # Isso cobre exports do WhatsApp que chegam sem a extensão (bug do app em alguns
    # dispositivos/versões). Os sem-extensão são renomeados com '.zip' antes do processamento.
    zips = []
    for f in arquivos:
        caminho_f = os.path.join(base_dir, f)
        if not os.path.isfile(caminho_f):
            continue
        if f.lower().endswith('.zip'):
            zips.append(f)
        else:
            # Testa se é um zip válido pelo cabeçalho do arquivo
            try:
                if zipfile.is_zipfile(caminho_f):
                    novo_nome = f + '.zip'
                    novo_caminho = os.path.join(base_dir, novo_nome)
                    os.rename(caminho_f, novo_caminho)
                    print(f"  ⚠️  Renomeado (sem extensão): '{f}' → '{novo_nome}'")
                    zips.append(novo_nome)
            except Exception:
                pass

    if not zips:
        print("Nenhum arquivo .zip encontrado na pasta de clientes para extração.")
        return

    print(f"\nEncontrados {len(zips)} arquivos .zip. Iniciando Step 0...\n")

    # Pasta de destino para os zips já processados (evita reprocessamento)
    pasta_processados = os.path.join(base_dir, config.PASTA_ZIPS_PROCESSADOS)
    os.makedirs(pasta_processados, exist_ok=True)

    # Pasta temporária para extração dos zips antes de distribuir os arquivos
    pasta_temp = os.path.join(base_dir, config.PASTA_TEMP_ZIPS)
    os.makedirs(pasta_temp, exist_ok=True)

    # Agrupa os zips pelo nome limpo do cliente
    # Ex: "Conversa...Marcelo.zip" e "Conversa...Marcelo (1).zip" → mesmo cliente
    clientes_map = {}
    cliente_info_map = {}
    for z in zips:
        client_info = clean_client_name(z)
        if client_info is None:
            print(f"  ⚠️  Ignorando '{z}': não foi possível derivar um nome de cliente válido.")
            continue
        
        nome_pasta = client_info["nome_pasta"]
        if nome_pasta not in clientes_map:
            clientes_map[nome_pasta] = []
            cliente_info_map[nome_pasta] = client_info
        else:
            # Merge de tags caso outro zip do mesmo cliente tenha tags diferentes
            for tag in client_info["tags_origem"]:
                if tag not in cliente_info_map[nome_pasta]["tags_origem"]:
                    cliente_info_map[nome_pasta]["tags_origem"].append(tag)
        clientes_map[nome_pasta].append(z)

    for nome_cliente, zips_cliente in clientes_map.items():
        print(f"📦 Processando cliente: {nome_cliente} ({len(zips_cliente)} zips)")

        pasta_destino = os.path.join(base_dir, nome_cliente)
        os.makedirs(pasta_destino, exist_ok=True)

        listas_mensagens = []

        # Caminho canônico do chat unificado na pasta do cliente.
        # Se já existe um _chat.txt (de um processamento anterior), ele é
        # carregado primeiro para ser mesclado com os novos backups.
        caminho_chat_destino = os.path.join(pasta_destino, config.ARQUIVO_CHAT)
        if os.path.exists(caminho_chat_destino):
            print(f"  ➜ Encontrado _chat.txt existente. Ele será mesclado.")
            listas_mensagens.append(parse_chat_whatsapp(caminho_chat_destino))

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
            salvar_chat_whatsapp(mensagens_unificadas, caminho_chat_destino)
            print(f"  ➜ {len(mensagens_unificadas)} mensagens únicas salvas no histórico consolidado.")
            
            # Atualiza métricas de conversa
            autor_mensagens = {}
            autor_audios = {}
            
            for msg in mensagens_unificadas:
                autor = msg['autor']
                autor_mensagens[autor] = autor_mensagens.get(autor, 0) + 1
                
                # Conta mensagens que aparentam ser áudios ou mídia omitida
                conteudo = msg.get('conteudo', '')
                if conteudo.endswith('.opus (arquivo anexado)') or 'Mídia omitida' in conteudo or 'áudio omitido' in conteudo.lower():
                    autor_audios[autor] = autor_audios.get(autor, 0) + 1

            # Cria ou atualiza o cliente_info.json
            caminho_json = os.path.join(pasta_destino, "cliente_info.json")
            info_atual = cliente_info_map[nome_cliente]
            
            dados = {
                "nome": info_atual["nome"],
                "data_nascimento": info_atual["data_nascimento"],
                "tags_origem": info_atual["tags_origem"],
                "metricas": {
                    "num_consultas": 0,
                    "mensagens_por_autor": autor_mensagens,
                    "audios_por_autor": autor_audios,
                    "tempo_audio_minutos": 0
                },
                "esoterico": {
                    "signo": None,
                    "arcano": None
                }
            }
            
            if os.path.exists(caminho_json):
                try:
                    with open(caminho_json, 'r', encoding='utf-8') as f:
                        json_existente = json.load(f)
                    
                    # Merge tags
                    tags_existentes = json_existente.get("tags_origem", [])
                    for tag in info_atual["tags_origem"]:
                        if tag not in tags_existentes:
                            tags_existentes.append(tag)
                    json_existente["tags_origem"] = tags_existentes
                    
                    # Atualiza as métricas computadas sempre que há novos zips
                    if "metricas" not in json_existente:
                        json_existente["metricas"] = {}
                    json_existente["metricas"]["mensagens_por_autor"] = autor_mensagens
                    json_existente["metricas"]["audios_por_autor"] = autor_audios
                    
                    dados = json_existente
                except Exception as e:
                    print(f"  ⚠️  Erro ao ler cliente_info.json: {e}. Sobrescrevendo.")
            
            with open(caminho_json, 'w', encoding='utf-8') as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            print(f"  ➜ cliente_info.json atualizado com métricas de conversa.")

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
