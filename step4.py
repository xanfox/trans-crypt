import os
import re
import json
import config
import utils
import step2
import step3
from whatsapp_parser import parse_chat_whatsapp

# ================= DICIONÁRIO DE TERMOS CLÍNICOS =================
# Lista expansível de termos médicos/psicológicos em português.
# Quando encontrados no texto, serão substituídos por [DADO CLÍNICO].
TERMOS_CLINICOS = [
    # Condições psicológicas
    "depressão", "depressao", "ansiedade", "síndrome do pânico", "sindrome do panico",
    "pânico", "panico", "bipolar", "transtorno", "borderline", "esquizofrenia",
    "tdah", "toc", "burnout", "estresse pós-traumático", "ptsd", "fobia",
    "anorexia", "bulimia", "compulsão", "compulsao",
    # Condições médicas gerais
    "diabetes", "hipertensão", "hipertensao", "câncer", "cancer", "tumor",
    "fibromialgia", "endometriose", "tireoide", "hipotireoidismo",
    "hipertireoidismo", "artrite", "artrose", "lúpus", "lupus", "anemia",
    "asma", "bronquite", "pneumonia", "covid", "hiv", "aids", "hepatite",
    "epilepsia", "parkinson", "alzheimer", "esclerose", "mioma", "cisto",
    "hérnia", "hernia", "gastrite", "úlcera", "ulcera", "insônia", "insonia",
    "apneia", "enxaqueca", "labirintite", "sinusite", "rinite", "dermatite",
    "psoríase", "psoriase", "vitiligo", "trombose", "avc", "infarto",
    "arritmia", "taquicardia", "bradicardia",
    # Medicamentos comuns
    "rivotril", "fluoxetina", "sertralina", "escitalopram", "venlafaxina",
    "clonazepam", "diazepam", "alprazolam", "lorazepam", "amitriptilina",
    "paroxetina", "citalopram", "duloxetina", "ritalina", "metilfenidato",
    "lítio", "litio", "quetiapina", "risperidona", "olanzapina", "haloperidol",
    "carbamazepina", "valproato", "lexapro", "prozac", "zoloft", "frontal",
    "omeprazol", "losartana", "metformina", "insulina",
]

# Palavras que o NER frequentemente classifica errado como PER/LOC.
# Alimentar conforme falsos positivos forem encontrados na auditoria.
NER_STOPLIST = {
    # Verbos / palavras comuns mal classificadas
    "aguardo", "estar", "ter", "surgir", "encontrar", "conseguir",
    "demorar", "querer", "quero", "tipo", "comigo", "porque",
    "simplesmente", "obrigado", "obrigada", "querido", "querida",
    "pessoas", "retraída", "descubra", "poxa", "aproveitar",
    "orientações", "energia", "consultor",
    # Vocativos e pronomes
    "me", "pra", "pro", "seu",
    # Conceitos espirituais / filosóficos / tarô
    "deus", "jesus", "cristo", "senhor", "senhora",
    "paus", "espadas", "copas", "ouros", "pagem",
    "rainha", "rei", "cavaleiro", "imperador", "imperatriz",
    "hermetismo", "caibalion", "quaresma", "salvador",
    # Geografia genérica / direções / natureza
    "norte", "sul", "leste", "oeste", "vale", "terra", "mel",
    # Sentimentos / conceitos abstratos
    "amor", "vida", "paz", "luz", "força", "graça",
    "esperança", "fé",
    # Astronomia / astrologia (planetas são confundidos com LOC)
    "mercúrio", "vênus", "marte", "júpiter", "saturno",
    "urano", "netuno", "plutão", "sol", "lua",
    # Marketing / spam
    "vagas limitadas", "vagas",
}

# ================= MOTOR NER (spaCy) =================
_nlp = None  # Cache global para não recarregar o modelo a cada chamada

def _carregar_spacy():
    """Carrega o modelo spaCy para português (apenas uma vez)."""
    global _nlp
    if _nlp is not None:
        return _nlp

    try:
        import spacy
    except ImportError:
        print("❌ spaCy não instalado. Rode: pip3 install spacy")
        return None

    for modelo in ("pt_core_news_lg", "pt_core_news_md", "pt_core_news_sm"):
        try:
            _nlp = spacy.load(modelo)
            print(f"   ✔ Modelo NER carregado: {modelo}")
            return _nlp
        except OSError:
            continue

    print("❌ Nenhum modelo spaCy pt encontrado. Rode: python3 -m spacy download pt_core_news_lg")
    return None

# ================= EXTRAÇÃO DE IDENTIDADE =================
def _extrair_identidade_cliente(pasta_cliente, mensagens_chat):
    """
    Monta o conjunto de nomes/variações do cliente para substituição direta.
    Fontes: nome da pasta + autores do chat que NÃO são o terapeuta.
    """
    nomes = set()

    # 1. Nome da pasta (já limpo pelo utils)
    nome_display = utils.formatar_nome_display(pasta_cliente)
    # Separa nome e possível data: "Diele Noronha - 07/11/1993"
    partes_display = nome_display.split(" - ")
    nome_limpo = partes_display[0].strip()
    nomes.add(nome_limpo)
    for parte in nome_limpo.split():
        if len(parte) > 2:
            nomes.add(parte)

    # 2. Data de nascimento da pasta
    data_nascimento = None
    if len(partes_display) > 1:
        possivel_data = partes_display[-1].strip()
        if re.match(r'\d{2}/\d{2}/\d{4}', possivel_data):
            data_nascimento = possivel_data

    # 3. Nomes dos autores do chat que NÃO são o terapeuta
    autores_vistos = set()
    for m in mensagens_chat:
        autor = m.get("autor", "")
        if autor in autores_vistos:
            continue
        autores_vistos.add(autor)

        if any(r in autor for r in config.REMETENTES_DIREITA):
            continue  # É o terapeuta, pula

        # Limpa emojis e prefixos
        autor_limpo = re.sub(r'[^\w\s]', '', autor).strip()
        for prefixo in ("Lead", "FR", "lead", "fr", "Consulente", "consulente"):
            if autor_limpo.lower().startswith(prefixo.lower()):
                autor_limpo = autor_limpo[len(prefixo):].strip()

        if autor_limpo:
            nomes.add(autor_limpo)
            for parte in autor_limpo.split():
                if len(parte) > 2:
                    nomes.add(parte)

    nomes.discard("")
    return nomes, data_nascimento

# ================= MOTOR DE ANONIMIZAÇÃO =================
def _anonimizar_texto(texto, nomes_cliente, nlp, data_nascimento=None):
    """
    Anonimiza um texto usando:
      1. Substituição direta dos nomes conhecidos do cliente
      2. NER (spaCy) para nomes e locais desconhecidos
      3. Regex para padrões de data
      4. Dicionário para termos clínicos

    Retorna (texto_anonimizado, lista_de_substituicoes).
    Cada substituição é um dict: {"start": int, "end": int, "original": str, "tag": str, "type": str}
    """
    if not texto.strip():
        return texto, []

    # Coletar substituições como (inicio, fim, tag, tipo)
    substituicoes = []

    # 1. Nomes conhecidos do cliente (mais longos primeiro para evitar match parcial)
    for nome in sorted(nomes_cliente, key=len, reverse=True):
        padrao = re.compile(re.escape(nome), re.IGNORECASE)
        for match in padrao.finditer(texto):
            substituicoes.append((match.start(), match.end(), "[NOME]", "dict"))

    # 2. NER com spaCy (detecta nomes e locais que não conhecemos)
    if nlp:
        doc = nlp(texto)
        for ent in doc.ents:
            # Filtra falsos positivos pela stoplist (checa texto completo e cada palavra)
            ent_lower = ent.text.strip().lower()
            if ent_lower in NER_STOPLIST:
                continue
            if any(w in NER_STOPLIST for w in ent_lower.split()):
                continue
            if ent.label_ == "PER":
                substituicoes.append((ent.start_char, ent.end_char, "[NOME]", "ner"))
            elif ent.label_ in ("LOC", "GPE"):
                substituicoes.append((ent.start_char, ent.end_char, "[LOCAL]", "ner"))

    # 3. Data de nascimento específica do cliente
    if data_nascimento:
        for sep in ("/", "-", "."):
            variacao = data_nascimento.replace("/", sep)
            for match in re.finditer(re.escape(variacao), texto):
                substituicoes.append((match.start(), match.end(), "[DATA NASCIMENTO]", "regex"))

    # 4. Padrão genérico de datas (DD/MM/AAAA, DD-MM-AAAA)
    for match in re.finditer(r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b', texto):
        substituicoes.append((match.start(), match.end(), "[DATA]", "regex"))

    # 5. Termos clínicos (dicionário)
    for termo in TERMOS_CLINICOS:
        padrao = re.compile(r'\b' + re.escape(termo) + r'\b', re.IGNORECASE)
        for match in padrao.finditer(texto):
            substituicoes.append((match.start(), match.end(), "[DADO CLÍNICO]", "dict"))

    # ── Resolver sobreposições e aplicar ──
    substituicoes.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    filtradas = []
    ultimo_fim = -1
    for inicio, fim, tag, tipo in substituicoes:
        if inicio >= ultimo_fim:
            filtradas.append((inicio, fim, tag, tipo))
            ultimo_fim = fim

    # Gera mapa de substituições para revisão inline
    anon_map = []
    for inicio, fim, tag, tipo in filtradas:
        anon_map.append({
            "original": texto[inicio:fim],
            "tag": tag,
            "type": tipo
        })

    # Aplica de trás para frente para não deslocar índices
    resultado = texto
    for inicio, fim, tag, tipo in reversed(filtradas):
        resultado = resultado[:inicio] + tag + resultado[fim:]

    return resultado, anon_map

# ================= EXECUÇÃO =================
def run(pasta_cliente=None, auto=False):
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()

    client_name = utils.formatar_nome_display(pasta_cliente)
    chat = utils.escolher_chat_txt(pasta_cliente, auto=auto)

    print(f"\n📖 Carregando mensagens de {client_name}...")
    mensagens_chat = parse_chat_whatsapp(chat)

    print("🔍 Carregando motor de reconhecimento de entidades (spaCy)...")
    nlp = _carregar_spacy()
    if not nlp:
        return

    # Extrai nomes e data de nascimento do cliente
    nomes_cliente, data_nascimento = _extrair_identidade_cliente(pasta_cliente, mensagens_chat)
    print(f"   📋 Nomes/variações detectados para anonimizar: {sorted(nomes_cliente, key=len, reverse=True)}")
    if data_nascimento:
        print(f"   📅 Data de nascimento detectada: {data_nascimento}")

    # Carrega edições existentes (conferencia_edits.json)
    caminho_edits = os.path.join(pasta_cliente, "conferencia_edits.json")
    edits = {"deleted_ids": [], "edited_texts": {}}
    if os.path.exists(caminho_edits):
        try:
            with open(caminho_edits, "r", encoding="utf-8") as f:
                edits = json.load(f)
        except Exception as e:
            print(f"\n⚠️ AVISO: conferencia_edits.json corrompido ({e}). Continuando sem edições anteriores.")

    # Prepara o estado anonimizado
    caminho_edits_anon = os.path.join(pasta_cliente, "conferencia_edits_anonimizada.json")
    edits_anon = {
        "deleted_ids": edits.get("deleted_ids", []),
        "edited_texts": {},
        "status": edits.get("status", {})
    }

    # Pasta de transcrições anonimizadas
    pasta_trans_orig = os.path.join(pasta_cliente, config.PASTA_TRANSCRICOES)
    pasta_trans_anon = os.path.join(pasta_cliente, "_transcricoes_anonimizadas")
    os.makedirs(pasta_trans_anon, exist_ok=True)

    arquivos_midia = [
        f for f in os.listdir(pasta_cliente)
        if f.lower().endswith(config.EXTENSOES_MIDIA_HTML)
    ]

    deleted_ids = {int(x) for x in edits_anon.get("deleted_ids", [])}
    mensagens_validas = [m for m in mensagens_chat if m["id"] not in deleted_ids]
    total = len(mensagens_validas)

    print(f"\n🤖 Anonimizando {total} mensagens...\n")

    contadores = {"nomes": 0, "locais": 0, "datas": 0, "clinicos": 0, "inalteradas": 0}

    for idx, m in enumerate(mensagens_validas, 1):
        msg_id_str = str(m["id"])
        conteudo_base = edits.get("edited_texts", {}).get(msg_id_str, m["conteudo"])
        arquivo_encontrado = next((arq for arq in arquivos_midia if arq in conteudo_base), None)

        # ── Texto da mensagem ──
        texto_msg = conteudo_base
        if arquivo_encontrado:
            texto_msg = ""  # A mensagem é só referência à mídia

        texto_anon = ""
        msg_anon_map = []
        if texto_msg.strip():
            texto_anon, msg_anon_map = _anonimizar_texto(texto_msg, nomes_cliente, nlp, data_nascimento)

        # ── Transcrição do áudio (se houver) ──
        trans_anon_texto = None
        if arquivo_encontrado:
            trans_orig = utils.buscar_transcricao(pasta_trans_orig, arquivo_encontrado)
            if trans_orig:
                trans_anon_texto, trans_map = _anonimizar_texto(trans_orig, nomes_cliente, nlp, data_nascimento)
                msg_anon_map.extend(trans_map)
                # Salva transcrição anonimizada
                base_nome = os.path.splitext(arquivo_encontrado)[0]
                with open(os.path.join(pasta_trans_anon, base_nome + ".txt"), "w", encoding="utf-8") as f:
                    f.write(trans_anon_texto)

        # ── Salva resultado ──
        if arquivo_encontrado:
            edits_anon["edited_texts"][msg_id_str] = conteudo_base
        else:
            edits_anon["edited_texts"][msg_id_str] = texto_anon if texto_anon else conteudo_base

        # Salva mapa de substituições para revisão inline
        if msg_anon_map:
            edits_anon.setdefault("anon_map", {})[msg_id_str] = msg_anon_map

        # ── Contadores e progresso ──
        texto_comparar = (texto_anon or "") + (trans_anon_texto or "")
        if "[NOME]" in texto_comparar:
            contadores["nomes"] += 1
        if "[LOCAL]" in texto_comparar:
            contadores["locais"] += 1
        if "[DATA" in texto_comparar:
            contadores["datas"] += 1
        if "[DADO CLÍNICO]" in texto_comparar:
            contadores["clinicos"] += 1
        if texto_comparar == (texto_msg or "") + ((utils.buscar_transcricao(pasta_trans_orig, arquivo_encontrado) or "") if arquivo_encontrado else ""):
            contadores["inalteradas"] += 1

        # Barra de progresso simples
        if idx % 50 == 0 or idx == total:
            pct = int(idx / total * 100)
            print(f"   [{idx}/{total}] {pct}% concluído — "
                  f"Nomes:{contadores['nomes']} | Locais:{contadores['locais']} | "
                  f"Datas:{contadores['datas']} | Clínicos:{contadores['clinicos']}")

    # Salva estado anonimizado de forma atômica (evita corrupção em caso de CTRL+C)
    tmp_anon = caminho_edits_anon + f".{__import__('uuid').uuid4().hex}.tmp"
    with open(tmp_anon, "w", encoding="utf-8") as f:
        json.dump(edits_anon, f, indent=4, ensure_ascii=False)
    os.replace(tmp_anon, caminho_edits_anon)

    print(f"\n✅ Anonimização concluída!")
    print(f"   📊 Resumo: {contadores['nomes']} msgs com nomes, "
          f"{contadores['locais']} com locais, {contadores['datas']} com datas, "
          f"{contadores['clinicos']} com dados clínicos")

    print("\n📄 Gerando exportações...")

    step2.gerar_historico(
        pasta_cliente, mensagens_chat,
        arquivo_saida="historico_anonimizado.txt",
        arquivo_edits="conferencia_edits_anonimizada.json",
        pasta_transcricoes="_transcricoes_anonimizadas"
    )

    step3.gerar_html(
        mensagens_chat, pasta_cliente,
        nome_saida="conferencia_anonimizada.html",
        arquivo_edits="conferencia_edits_anonimizada.json",
        pasta_transcricoes="_transcricoes_anonimizadas"
    )


if __name__ == '__main__':
    run()

