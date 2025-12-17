import pdfplumber
import re
import json
import unicodedata
import os

# --- CONFIGURAÇÃO ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"

EI_PAGE_RANGE = range(35, 60)
EF_PAGE_RANGE = range(57, 460)
EM_PAGE_RANGE = range(460, 600)

RE_CODE_EI_FULL = re.compile(r"EI(\d{2})([A-Z]{2})\d{2}")
RE_CODE_EF = re.compile(r"(EF\d{2,3}([A-Z]{2})\d{2,3})") # Captura Grupo 2 como Sigla
RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")

# Mapeamentos EI
CAMPOS_EXPERIENCIA = {
    "EO": "O eu, o outro e o nós",
    "CG": "Corpo, gestos e movimentos",
    "TS": "Traços, sons, cores e formas",
    "EF": "Escuta, fala, pensamento e imaginação",
    "ET": "Espaços, tempos, quantidades, relações e transformações"
}

DIREITOS_APRENDIZAGEM = [
    "Conviver com outras crianças e adultos, em pequenos e grandes grupos, utilizando diferentes linguagens, ampliando o conhecimento de si e do outro, o respeito em relação à cultura e às diferenças entre as pessoas.",
    "Brincar cotidianamente de diversas formas, em diferentes espaços e tempos, com diferentes parceiros (crianças e adultos), ampliando e diversificando seu acesso a produções culturais, seus conhecimentos, sua imaginação, sua criatividade, suas experiências emocionais, corporais, sensoriais, expressivas, cognitivas, sociais e relacionais.",
    "Participar ativamente, com adultos e outras crianças, tanto do planejamento da gestão da escola e das atividades propostas pelo educador quanto da realização das atividades da vida cotidiana, tais como a escolha das brincadeiras, dos materiais e dos ambientes, desenvolvendo diferentes linguagens e elaborando conhecimentos, decidindo e se posicionando.",
    "Explorar movimentos, gestos, sons, formas, texturas, cores, palavras, emoções, transformações, relacionamentos, histórias, objetos, elementos da natureza, na escola e fora dela, ampliando seus saberes sobre a cultura, em suas diversas modalidades: as artes, a escrita, a ciência e a tecnologia.",
    "Expressar, como sujeito dialógico, criativo e sensível, suas necessidades, emoções, sentimentos, dúvidas, hipóteses, descobertas, opiniões, questionamentos, por meio de diferentes linguagens.",
    "Conhecer-se e construir sua identidade pessoal, social e cultural, constituindo uma imagem positiva de si e de seus grupos de pertencimento, nas diversas experiências de cuidados, interações, brincadeiras e linguagens vivenciadas na instituição escolar e em seu contexto familiar e comunitário."
]

# Mapeamento EF (Níveis 1 e 3)
MAPA_EF_ESTRUTURA = {
    "LP": {"componente": "Língua Portuguesa", "area": "Linguagens"},
    "AR": {"componente": "Arte", "area": "Linguagens"},
    "EF": {"componente": "Educação Física", "area": "Linguagens"},
    "LI": {"componente": "Língua Inglesa", "area": "Linguagens"},
    "MA": {"componente": "Matemática", "area": "Matemática"},
    "CI": {"componente": "Ciências", "area": "Ciências da Natureza"},
    "GE": {"componente": "Geografia", "area": "Ciências Humanas"},
    "HI": {"componente": "História", "area": "Ciências Humanas"},
    "ER": {"componente": "Ensino Religioso", "area": "Ensino Religioso"}
}

# --- UTILITÁRIOS GERAIS ---

def clean_text_basic(text):
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_item_sintese(text):
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"^[\s•\-]+", "", text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def processar_descricao_ei(texto_bruto, codigo):
    if codigo: texto = texto_bruto.replace(codigo, "")
    else: texto = texto_bruto
    return re.sub(r"^[\s\(\)\.\-]+", "", texto).strip()

def expandir_anos_ef(codigo_bncc):
    """
    Nível 5: Expande códigos EF15, EF69, etc. para lista de anos.
    """
    match = re.search(r"EF(\d{2,3})", codigo_bncc)
    if not match: return ["Ano Indefinido"]
    digits = match.group(1)
    
    if digits == "15": return [f"{i}º Ano" for i in range(1, 6)]
    if digits == "69": return [f"{i}º Ano" for i in range(6, 10)]
    if digits == "35": return [f"{i}º Ano" for i in range(3, 6)]
    if digits == "12": return ["1º Ano", "2º Ano"]
    if digits == "67": return ["6º Ano", "7º Ano"]
    if digits == "89": return ["8º Ano", "9º Ano"]
    if len(digits) == 2 and digits.isdigit():
        val = int(digits)
        if 1 <= val <= 9: return [f"{val}º Ano"]
    return [f"Ano {digits}"]

# --- LOGICA DE COMPETÊNCIAS (TEXT MINING) ---

def extrair_competencias_texto(pdf, page_range):
    """
    Varre o texto das páginas procurando listas numeradas de competências.
    Retorna um dict: { "Area/Componente": [Lista de Competências] }
    """
    competencias_map = {}
    current_key = None
    buffer_list = []
    
    # Regex para detectar títulos de competência
    # Ex: "COMPETÊNCIAS ESPECÍFICAS DE LINGUAGENS PARA O ENSINO FUNDAMENTAL"
    re_header = re.compile(r"COMPETÊNCIAS ESPECÍFICAS DE\s+(.+?)\s+PARA O ENSINO FUNDAMENTAL", re.IGNORECASE)
    
    # Regex para detectar itens da lista (1. Texto...)
    re_item_start = re.compile(r"^(\d+)\.\s+(.*)")

    print("--- Mineração de Competências (EF) ---")

    for page_num in page_range:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text()
        if not text: continue
        
        lines = text.split('\n')
        
        for line in lines:
            line_clean = clean_text_basic(line)
            
            # 1. Detecta Cabeçalho
            match_header = re_header.search(line_clean)
            if match_header:
                # Salva o anterior se existir
                if current_key and buffer_list:
                    if current_key not in competencias_map:
                        competencias_map[current_key] = []
                    competencias_map[current_key].extend(buffer_list)
                
                # Inicia novo bloco
                # Normaliza a chave (ex: LINGUAGENS -> Linguagens)
                raw_key = match_header.group(1).strip().upper()
                current_key = raw_key 
                buffer_list = []
                continue
            
            # 2. Detecta Item Numerado (1., 2.)
            if current_key:
                match_item = re_item_start.match(line_clean)
                if match_item:
                    # Se tínhamos um item anterior no buffer sendo construído (multilinha), finaliza ele?
                    # Simplificação: assumimos que o item anterior já foi pro buffer_list como string completa
                    # ou vamos concatenar. Na BNCC, itens costumam ser parágrafos.
                    texto_item = match_item.group(2).strip()
                    buffer_list.append(texto_item)
                
                # 3. Detecta Continuação de Texto (sem número, mas dentro de um bloco)
                elif buffer_list and len(line_clean) > 5 and not line_clean.isupper():
                    # Adiciona ao último item
                    buffer_list[-1] += " " + line_clean

    # Salva o último bloco
    if current_key and buffer_list:
        if current_key not in competencias_map:
            competencias_map[current_key] = []
        competencias_map[current_key].extend(buffer_list)
        
    return competencias_map

def normalizar_chave_competencia(nome_bncc, mapa_chaves):
    """Tenta casar o nome extraído do PDF (ex: 'LINGUAGENS') com o nome no JSON."""
    nome_norm = nome_bncc.upper()
    for chave_json, lista_comps in mapa_chaves.items():
        if chave_json.upper() in nome_norm:
            return chave_json
    return None

# --- EXTRATORES ---

def extract_ei_final(pdf):
    # (MANTIDO DO SEU CÓDIGO ANTERIOR)
    print("--- Processando Educação Infantil ---")
    
    def separar_itens_sintese(texto_bruto_celula):
        if not texto_bruto_celula: return []
        texto = unicodedata.normalize("NFKC", texto_bruto_celula)
        linhas = texto.split('\n')
        itens = []
        buffer_atual = []
        for linha in linhas:
            linha_limpa = linha.strip()
            if not linha_limpa: continue
            eh_bullet = linha_limpa.startswith(('•', '-', '·'))
            comeca_maiuscula = linha_limpa[0].isupper()
            if not buffer_atual:
                buffer_atual.append(linha_limpa)
            elif eh_bullet:
                itens.append(" ".join(buffer_atual))
                buffer_atual = [linha_limpa]
            elif comeca_maiuscula:
                itens.append(" ".join(buffer_atual))
                buffer_atual = [linha_limpa]
            else:
                buffer_atual.append(linha_limpa)
        if buffer_atual: itens.append(" ".join(buffer_atual))
        itens_finais = []
        for it in itens:
            limpo = clean_item_sintese(it)
            if len(limpo) > 5:
                if not limpo.endswith('.'): limpo += "."
                itens_finais.append(limpo)
        return itens_finais

    output = {
        "metadata": {
            "etapa": "Educação Infantil",
            "direitos_aprendizagem": DIREITOS_APRENDIZAGEM,
            "faixas_etarias": [
                {"id": "EI01", "descricao": "Bebês (zero a 1 ano e 6 meses)"},
                {"id": "EI02", "descricao": "Crianças bem pequenas (1 ano e 7 meses a 3 anos e 11 meses)"},
                {"id": "EI03", "descricao": "Crianças pequenas (4 anos a 5 anos e 11 meses)"}
            ],
            "campos_experiencia": [{"sigla": k, "nome": v} for k, v in CAMPOS_EXPERIENCIA.items()]
        },
        "objetivos_aprendizagem": {
            "EI01": {k: [] for k in CAMPOS_EXPERIENCIA},
            "EI02": {k: [] for k in CAMPOS_EXPERIENCIA},
            "EI03": {k: [] for k in CAMPOS_EXPERIENCIA}
        },
        "sintese_aprendizagens": {k: [] for k in CAMPOS_EXPERIENCIA}
    }
    col_map_obj = {0: "EI01", 1: "EI02", 2: "EI03"}
    ultimo_campo_sintese = None

    for page_num in EI_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        tables = page.extract_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        for table in tables:
            for row in table:
                row_cells_clean = [clean_text_basic(c) for c in row if c]
                row_str = "".join(row_cells_clean).upper()
                tem_codigo = False
                for cell in row_cells_clean:
                    if "EI" in cell and RE_CODE_EI_FULL.search(cell):
                        tem_codigo = True; break
                if tem_codigo:
                    for col_idx, cell_text in enumerate(row):
                        if not cell_text or col_idx not in col_map_obj: continue
                        cleaned = clean_text_basic(cell_text)
                        matches = list(RE_CODE_EI_FULL.finditer(cleaned))
                        for i, match in enumerate(matches):
                            codigo = match.group(0)
                            faixa = "EI" + match.group(1)
                            sigla = match.group(2)
                            start = match.end()
                            end = matches[i+1].start() if (i + 1) < len(matches) else len(cleaned)
                            desc = processar_descricao_ei(cleaned[start:end], "")
                            if faixa in output["objetivos_aprendizagem"] and sigla in CAMPOS_EXPERIENCIA:
                                output["objetivos_aprendizagem"][faixa][sigla].append({"codigo": codigo, "descricao": desc})
                elif "SÍNTESE" in row_str or len(row) == 2:
                    if "SÍNTESE" in row_str and len(row_cells_clean) < 3: continue
                    if len(row) == 2:
                        col_campo_raw = row[0] if row[0] else ""
                        col_texto_raw = row[1] if row[1] else ""
                        col_campo_clean = clean_text_basic(col_campo_raw)
                        for sigla, nome in CAMPOS_EXPERIENCIA.items():
                            if nome.upper() in col_campo_clean.upper():
                                ultimo_campo_sintese = sigla; break
                        if ultimo_campo_sintese and col_texto_raw:
                            novos = separar_itens_sintese(col_texto_raw)
                            output["sintese_aprendizagens"][ultimo_campo_sintese].extend(novos)
    return output

def extract_ef_pro(pdf):
    print("--- Processando Ensino Fundamental (Profissional 8 Níveis) ---")
    
    # 1. Estrutura Inicial (Áreas e Componentes)
    tree = {}
    
    # 2. Mineração de Competências (Níveis 2 e 4)
    # Extrai tudo para um dicionário temporário
    comps_raw = extrair_competencias_texto(pdf, EF_PAGE_RANGE)
    
    # Popula a Árvore com Áreas, Componentes e Competências
    for sigla, info in MAPA_EF_ESTRUTURA.items():
        area_nome = info["area"]
        comp_nome = info["componente"]
        
        # Nível 1: Área
        if area_nome not in tree:
            # Tenta encontrar competências da área no minerado (Ex: "LINGUAGENS")
            comps_area = []
            key_match = None
            # Busca case-insensitive e parcial (ex: "LINGUAGENS" in "COMPETÊNCIAS... LINGUAGENS...")
            for k in comps_raw:
                if area_nome.upper() in k or k in area_nome.upper():
                    key_match = k
                    break
            if key_match: comps_area = comps_raw[key_match]

            tree[area_nome] = {
                "competencias_especificas_area": comps_area, # Nível 2
                "componentes": {}
            }
        
        # Nível 3: Componente
        if comp_nome not in tree[area_nome]["componentes"]:
            # Tenta encontrar competências do componente (Ex: "LÍNGUA PORTUGUESA")
            comps_comp = []
            key_match = None
            for k in comps_raw:
                # Remove acentos para comparação segura
                k_norm = clean_text_basic(k).upper()
                c_norm = clean_text_basic(comp_nome).upper()
                if c_norm in k_norm:
                    key_match = k
                    break
            if key_match: comps_comp = comps_raw[key_match]

            tree[area_nome]["componentes"][comp_nome] = {
                "competencias_especificas_componente": comps_comp, # Nível 4
                "anos": {} # Nível 5 começa aqui
            }

    # 3. Extração de Habilidades (Níveis 5 a 8)
    current_lp_field = "Campo de atuação geral"
    last_thematic_unit = "Geral"

    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        tables = page.extract_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})

        for table in tables:
            for row in table:
                cleaned_row = [clean_text_basic(c) for c in row if c]
                row_str = "".join(cleaned_row).upper()
                
                if not row_str or "HABILIDADES" in row_str or "PRÁTICAS DE LINGUAGEM" in row_str:
                    continue

                # Contexto LP: Campo de Atuação
                if "CAMPO" in row_str and len(cleaned_row) == 1:
                    current_lp_field = cleaned_row[0]
                    continue
                elif "TODOS OS CAMPOS" in row_str:
                    current_lp_field = "Todos os campos de atuação"
                    continue

                # Busca Habilidade
                skill_code = None
                skill_text = ""
                sigla_comp = None
                
                # Varre de trás pra frente (Habilidade é última col)
                for cell in reversed(cleaned_row):
                    match = RE_CODE_EF.search(cell)
                    if match:
                        skill_code = match.group(1)
                        sigla_comp = match.group(2)
                        skill_text = cell
                        break
                
                if skill_code and sigla_comp in MAPA_EF_ESTRUTURA:
                    # Limpeza da Descrição
                    desc = skill_text[match.end():].strip()
                    desc = re.sub(r"^[\s\)\.\-]+", "", desc)
                    
                    info_comp = MAPA_EF_ESTRUTURA[sigla_comp]
                    nome_area = info_comp["area"]
                    nome_comp = info_comp["componente"]
                    
                    # Nível 5: Expansão (EF15 -> 1, 2, 3, 4, 5)
                    anos_expandidos = expandir_anos_ef(skill_code)
                    
                    # Níveis 6 e 7: Unidade/Campo e Objeto
                    if sigla_comp == "LP":
                        nivel_6 = current_lp_field # Campo de Atuação
                        # Objeto costuma ser a penúltima coluna não vazia, ou a primeira se só tiver 2
                        # Layout LP: [Prática] | [Objeto] | [Habilidade] ou [Objeto] | [Habilidade]
                        if len(cleaned_row) >= 3:
                            nivel_7 = cleaned_row[1] 
                        elif len(cleaned_row) == 2:
                            nivel_7 = cleaned_row[0]
                        else:
                            nivel_7 = "Geral"
                    else:
                        # Layout Padrão: [Unidade] | [Objeto] | [Habilidade]
                        if len(cleaned_row) >= 3:
                            unidade = cleaned_row[0]
                            objeto = cleaned_row[1]
                        elif len(cleaned_row) == 2:
                            unidade = last_thematic_unit
                            objeto = cleaned_row[0]
                        else:
                            unidade = last_thematic_unit
                            objeto = "Geral"
                        
                        if unidade: last_thematic_unit = unidade
                        nivel_6 = last_thematic_unit # Unidade Temática
                        nivel_7 = objeto # Objeto de Conhecimento

                    # Inserção na Árvore
                    branch_comp = tree[nome_area]["componentes"][nome_comp]["anos"]
                    
                    for ano in anos_expandidos:
                        if ano not in branch_comp: branch_comp[ano] = {} # Nível 5
                        
                        # Normaliza chaves para evitar chaves duplicadas com espaços
                        k_n6 = nivel_6.strip()
                        k_n7 = nivel_7.strip()
                        
                        if k_n6 not in branch_comp[ano]: branch_comp[ano][k_n6] = {} # Nível 6
                        
                        if k_n7 not in branch_comp[ano][k_n6]: branch_comp[ano][k_n6][k_n7] = [] # Nível 7
                        
                        # Nível 8: Habilidade
                        # Check simples de duplicidade
                        exists = False
                        for h in branch_comp[ano][k_n6][k_n7]:
                            if h["codigo"] == skill_code:
                                exists = True; break
                        if not exists:
                            branch_comp[ano][k_n6][k_n7].append({"codigo": skill_code, "descricao": desc})
    return tree

def extract_em(pdf):
    # (MANTIDO DO SEU CÓDIGO ANTERIOR)
    print("--- Processando Ensino Médio ---")
    data = []
    current_area = "Geral"
    def clean_text_em(text): return re.sub(r'\s+', ' ', unicodedata.normalize("NFKC", text)).strip()
    
    for page_num in EM_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        upper_text = text.upper()
        if "LINGUAGENS" in upper_text: current_area = "Linguagens e suas Tecnologias"
        elif "MATEMÁTICA" in upper_text: current_area = "Matemática e suas Tecnologias"
        elif "NATUREZA" in upper_text: current_area = "Ciências da Natureza e suas Tecnologias"
        elif "HUMANAS" in upper_text: current_area = "Ciências Humanas e Sociais Aplicadas"
        lines = text.split('\n')
        buffer_code = None
        buffer_desc = []
        for line in lines:
            clean_line = clean_text_em(line)
            match = RE_CODE_EM.search(clean_line)
            if match:
                if buffer_code:
                    data.append({"code": buffer_code, "description": " ".join(buffer_desc).strip(), "area": current_area})
                buffer_code = match.group(1)
                start_desc = clean_line[match.end():].strip()
                start_desc = re.sub(r"^[\s\.\-]+", "", start_desc)
                buffer_desc = [start_desc] if start_desc else []
            elif buffer_code:
                if len(clean_line) > 3 or not clean_line.isdigit():
                    buffer_desc.append(clean_line)
        if buffer_code:
            data.append({"code": buffer_code, "description": " ".join(buffer_desc).strip(), "area": current_area})
    return list({v['code']: v for v in data}.values())

# --- EXECUÇÃO ---

def main():
    print(f"Abrindo PDF: {PDF_PATH}")
    if not os.path.exists(PDF_PATH):
        print("Arquivo PDF não encontrado.")
        return

    try:
        pdf = pdfplumber.open(PDF_PATH)
    except Exception as e:
        print(f"Erro ao abrir PDF: {e}")
        return

    # Extrações
    ei_data = extract_ei_final(pdf)
    ef_data = extract_ef_pro(pdf) # Nova versão PRO
    em_data = extract_em(pdf)
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    with open("bncc_ei.json", "w", encoding="utf-8") as f: json.dump(ei_data, f, ensure_ascii=False, indent=2)
    with open("bncc_ef.json", "w", encoding="utf-8") as f: json.dump(ef_data, f, ensure_ascii=False, indent=2)
    with open("bncc_em.json", "w", encoding="utf-8") as f: json.dump(em_data, f, ensure_ascii=False, indent=2)
    
    print("\nProcesso concluído. Arquivos gerados:")
    print("- bncc_ei.json (Estrutura EI Validada)")
    print("- bncc_ef.json (Nova Estrutura Profissional 8 Níveis)")
    print("- bncc_em.json (Estrutura EM Mantida)")

if __name__ == "__main__":
    main()