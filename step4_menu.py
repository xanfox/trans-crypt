import os
import json
import csv
import utils
import step4

ARQUIVO_STOPLIST = "ner_stoplist.csv"

def load_categorias_globais():
    caminho = "categorias_personas.json"
    if not os.path.exists(caminho):
        default = {
            "Profissionais/Principais": ["consulente", "consultor"],
            "Relacionamentos": ["conjuge", "pretendente", "amante"],
            "Família": ["familiar", "irmã(o)", "parente"],
            "Sociais": ["amiga(o)", "rival", "conhecida(o)", "colega de trabalho", "vizinho"],
            "Animais": ["animal", "gato", "cão", "ave"],
            "Outros": ["desconhecido"]
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_categorias_globais(categorias):
    with open("categorias_personas.json", "w", encoding="utf-8") as f:
        json.dump(categorias, f, indent=4, ensure_ascii=False)

def load_categorias_traits():
    caminho = "categorias_traits.json"
    if not os.path.exists(caminho):
        default = {
            "condição": ["mental", "físico", "espiritual"],
            "medicação": ["anti depressivo", "anti ansiolítico", "barbitúrico"],
            "psicoativo": ["substância lícita", "substância ilícita"],
            "adicção": ["drogas", "pornografia", "comida", "álcool"]
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_categorias_traits(categorias):
    with open("categorias_traits.json", "w", encoding="utf-8") as f:
        json.dump(categorias, f, indent=4, ensure_ascii=False)


def get_todas_categorias():
    cat_tree = load_categorias_globais()
    flat = []
    for grupo, itens in cat_tree.items():
        flat.extend(itens)
    return flat

def load_stoplist():
    if not os.path.exists(ARQUIVO_STOPLIST):
        return []
    with open(ARQUIVO_STOPLIST, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            next(reader) # skip header
        except StopIteration:
            pass
        return [row[0] for row in reader if row]

def save_stoplist(stoplist):
    with open(ARQUIVO_STOPLIST, "w", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["palavra"])
        for p in stoplist:
            writer.writerow([p])

def load_personas(pasta_cliente):
    arquivo = os.path.join(pasta_cliente, "personas.json")
    if not os.path.exists(arquivo):
        return {}
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_personas(pasta_cliente, personas):
    arquivo = os.path.join(pasta_cliente, "personas.json")
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(personas, f, indent=4, ensure_ascii=False)

def gerenciar_stoplist():
    while True:
        stoplist = load_stoplist()
        print("\n" + "="*40)
        print("   GESTÃO DA STOPLIST (Falsos Positivos NER)")
        print("="*40)
        print(f"Total de palavras na stoplist: {len(stoplist)}")
        print("\n[1] Ver todas as palavras")
        print("[2] Adicionar palavra(s) manualmente")
        print("[0] Voltar")
        
        escolha = input("\nEscolha: ").strip()
        if escolha == '0':
            break
        elif escolha == '1':
            print("\nPalavras na Stoplist:")
            for i, p in enumerate(sorted(stoplist), 1):
                print(f" {i}. {p}")
            input("\nPressione Enter para continuar...")
        elif escolha == '2':
            palavras = input("\nDigite a(s) palavra(s) separadas por vírgula: ").strip()
            if palavras:
                novas = [p.strip().lower() for p in palavras.split(",") if p.strip()]
                atualizadas = set(stoplist)
                atualizadas.update(novas)
                save_stoplist(list(atualizadas))
                print(f"Adicionadas {len(novas)} palavras.")

def formatar_tag_persona(personas, nome, categoria):
    # Calcula o número para aquela categoria
    # Ex: se já existe Lucas -> pretendente, e eu colocar Joao -> pretendente, Joao vira pretendente²
    
    # Se o nome já existe nas personas e já pertence à categoria escolhida, retorna a tag atual.
    if nome in personas:
        current = personas[nome]
        if current.startswith(categoria):
            return current
            
    numerador = 1
    for n, cat in personas.items():
        if cat.startswith(categoria):
            numerador += 1
            
    # Se numerador for 1, pode ser só "amigo" ou "amigo¹", usuário pediu "amigo¹" se tiver mais, mas
    # podemos já padronizar "amigo¹" para o primeiro também, ou só colocar número a partir do 2.
    # Vamos colocar o número convertido para sobrescrito (opcional, ou apenas o número normal).
    superscript_map = {"1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "0": "⁰"}
    num_str = "".join([superscript_map.get(c, c) for c in str(numerador)])
    tag_final = f"{categoria}{num_str}"
    
    # Porém, o que salvamos no dict é a tag exata que será usada, ou apenas a categoria?
    # Melhor salvar a tag pronta.
    personas[nome] = tag_final
    return tag_final

def gerenciar_personas(pasta_cliente):
    personas = load_personas(pasta_cliente)
    
    while True:
        print("\n" + "="*40)
        print("   GESTÃO DE PERSONAS (ROLES)")
        print("="*40)
        print("Personas Cadastradas:")
        if not personas:
            print("  Nenhuma persona cadastrada.")
        else:
            for nome, tag in personas.items():
                print(f"  {nome} -> [{tag}]")
                
        print("\n[1] Classificação Manual (Adicionar nome e papel)")
        print("[2] Classificação Automática (Varredura no chat para encontrar nomes)")
        print("[3] Limpar Personas")
        print("[0] Voltar")
        
        escolha = input("\nEscolha: ").strip()
        if escolha == '0':
            break
        elif escolha == '1':
            nome = input("\nDigite o nome da pessoa: ").strip()
            if nome:
                print("\nEscolha a categoria:")
                categorias_flat = get_todas_categorias()
                for i, cat in enumerate(categorias_flat, 1):
                    print(f"[{i}] {cat}")
                cat_escolha = input("Categoria (número): ").strip()
                if cat_escolha.isdigit() and 1 <= int(cat_escolha) <= len(categorias_flat):
                    categoria = categorias_flat[int(cat_escolha)-1]
                    tag = formatar_tag_persona(personas, nome, categoria)
                    save_personas(pasta_cliente, personas)
                    print(f"Salvo: {nome} -> [{tag}]")
        elif escolha == '2':
            print("\nIniciando varredura para extração de entidades...")
            # Chama step4 para apenas ler as msgs e rodar o NER, retornando nomes prováveis.
            nomes_encontrados = step4.extrair_entidades(pasta_cliente)
            if not nomes_encontrados:
                print("Nenhum nome novo encontrado na varredura.")
                continue
                
            for nome in nomes_encontrados:
                if nome in personas:
                    continue
                print(f"\nNome encontrado: {nome}")
                print("Escolha a categoria (ou 0 para ignorar e usar genérico):")
                categorias_flat = get_todas_categorias()
                for i, cat in enumerate(categorias_flat, 1):
                    print(f"[{i}] {cat}")
                cat_escolha = input("Categoria (número): ").strip()
                if cat_escolha == '0':
                    continue
                if cat_escolha.isdigit() and 1 <= int(cat_escolha) <= len(categorias_flat):
                    categoria = categorias_flat[int(cat_escolha)-1]
                    tag = formatar_tag_persona(personas, nome, categoria)
                    print(f"Salvo: {nome} -> [{tag}]")
                    save_personas(pasta_cliente, personas)
        elif escolha == '3':
            confirm = input("Tem certeza que deseja apagar todas as personas? (s/n): ").strip().lower()
            if confirm == 's':
                personas = {}
                save_personas(pasta_cliente, personas)

def configurar_personalizado():
    flags = {"nomes": True, "datas": True, "locais": True, "clinicas": True}
    while True:
        print("\n" + "="*40)
        print("   NÍVEL 5 - PERSONALIZADO")
        print("="*40)
        print(f"[1] Nomes: {'[X]' if flags['nomes'] else '[ ]'}")
        print(f"[2] Datas: {'[X]' if flags['datas'] else '[ ]'}")
        print(f"[3] Locais: {'[X]' if flags['locais'] else '[ ]'}")
        print(f"[4] Condições Clínicas: {'[X]' if flags['clinicas'] else '[ ]'}")
        print("[0] Concluir")
        
        escolha = input("\nEscolha (1-4 para alternar, 0 para voltar): ").strip()
        if escolha == '0':
            break
        elif escolha == '1': flags['nomes'] = not flags['nomes']
        elif escolha == '2': flags['datas'] = not flags['datas']
        elif escolha == '3': flags['locais'] = not flags['locais']
        elif escolha == '4': flags['clinicas'] = not flags['clinicas']
        
    return flags

def run(pasta_cliente=None):
    if not pasta_cliente:
        pasta_cliente = utils.escolher_pasta_cliente()
        
    nivel_anon = 4
    flags_anon = {"nomes": True, "datas": True, "locais": True, "clinicas": True}
    
    while True:
        print("\n" + "="*40)
        print("   PASSO 4 - ANONIMIZAR HISTÓRICO")
        print("="*40)
        print("Opções de Execução:")
        print("  [ENTER] Rodar Anonimização Agora")
        print("\nSubmenu de Configuração:")
        
        # Display current level
        desc_nivel = ""
        if nivel_anon == 1: desc_nivel = "Nomes Apenas"
        elif nivel_anon == 2: desc_nivel = "Nomes e Datas"
        elif nivel_anon == 3: desc_nivel = "Nomes, Datas e Locais"
        elif nivel_anon == 4: desc_nivel = "Nomes, Datas, Locais e Condições Clínicas"
        elif nivel_anon == 5: desc_nivel = "Personalizado"
        
        print(f"  [1] Nível de Anonimização (Atual: Nível {nivel_anon} - {desc_nivel})")
        print("  [2] Gerenciar Stoplist de Palavras (Global)")
        print("  [3] Gerenciar Personas e Papéis (Local)")
        print("  [0] Voltar ao Menu Principal")
        print("="*40)
        
        escolha = input("Escolha: ")
        
        if escolha == '':
            # Executar processo
            print("\nIniciando processo de anonimização com as configurações escolhidas...")
            personas = load_personas(pasta_cliente)
            stoplist = load_stoplist()
            step4.executar_processo(pasta_cliente, flags_anon, personas, stoplist)
            break
        elif escolha == '0':
            break
        elif escolha == '1':
            print("\nEscolha o nível de anonimização:")
            print("[1] Anonimizar apenas nomes")
            print("[2] Anonimizar nomes e datas")
            print("[3] Anonimizar nomes, datas e locais")
            print("[4] Anonimizar nomes, datas, locais e condições clínicas")
            print("[5] Personalizado")
            n = input("Nível: ").strip()
            if n in ['1', '2', '3', '4']:
                nivel_anon = int(n)
                flags_anon = {
                    "nomes": nivel_anon >= 1,
                    "datas": nivel_anon >= 2,
                    "locais": nivel_anon >= 3,
                    "clinicas": nivel_anon >= 4
                }
            elif n == '5':
                nivel_anon = 5
                flags_anon = configurar_personalizado()
        elif escolha == '2':
            gerenciar_stoplist()
        elif escolha == '3':
            gerenciar_personas(pasta_cliente)
