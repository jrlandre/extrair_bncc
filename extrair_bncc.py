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
RE_CODE_EF = re.compile(r"\(?(EF\d{2,3}([A-Z]{2})\d{2,3})\)?") 
RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")

# --- MAPEAMENTOS ---
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

# --- UTILITÁRIOS ---

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

def processar_descricao(texto_bruto, codigo):
    if codigo: texto = texto_bruto.replace(codigo, "")
    else: texto = texto_bruto
    return re.sub(r"^[\s\(\)\.\-]+", "", texto).strip()

def expandir_anos_ef(codigo_bncc):
    """
    Expande códigos de faixa (ex: EF15) para lista de anos individuais.
    Garante 'perfect info' replicando o item para cada ano.
    """
    match = re.search(r"EF(\d{2,3})", codigo_bncc)
    if not match: return ["Ano Indefinido"]
    digits = match.group(1)
    
    anos = []
    # Faixas comuns na BNCC
    if digits == "15": anos = [1, 2, 3, 4, 5]
    elif digits == "69": anos = [6, 7, 8, 9]
    elif digits == "35": anos = [3, 4, 5]
    elif digits == "12": anos = [1, 2]
    elif digits == "67": anos = [6, 7]
    elif digits == "89": anos = [8, 9]
    # Anos individuais (01 a 09)
    elif len(digits) == 2 and digits.isdigit():
        val = int(digits)
        if 1 <= val <= 9: anos = [val]
    
    if not anos: return [f"Ano {digits}"]
    return [f"{a}º Ano" for a in anos]

# --- EXTRATORES ---

def extract_ei_final(pdf):
    # (Código Original Mantido - Educação Infantil)
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
            if not buffer_atual: buffer_atual.append(linha_limpa)
            elif eh_bullet:
                itens.append(" ".join(buffer_atual)); buffer_atual = [linha_limpa]
            elif comeca_maiuscula:
                itens.append(" ".join(buffer_atual)); buffer_atual = [linha_limpa]
            else: buffer_atual.append(linha_limpa)
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
                    if "EI" in cell and RE_CODE_EI_FULL.search(cell): tem_codigo = True; break
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
                            desc = processar_descricao(cleaned[start:end], "")
                            if faixa in output["objetivos_aprendizagem"] and sigla in CAMPOS_EXPERIENCIA:
                                output["objetivos_aprendizagem"][faixa][sigla].append({"codigo": codigo, "descricao": desc})
                elif "SÍNTESE" in row_str or len(row) == 2:
                    if "SÍNTESE" in row_str and len(row_cells_clean) < 3: continue
                    if len(row) == 2:
                        col_campo_clean = clean_text_basic(row[0] if row[0] else "")
                        for sigla, nome in CAMPOS_EXPERIENCIA.items():
                            if nome.upper() in col_campo_clean.upper(): ultimo_campo_sintese = sigla; break
                        col_texto_raw = row[1] if row[1] else ""
                        if ultimo_campo_sintese and col_texto_raw:
                            novos = separar_itens_sintese(col_texto_raw)
                            output["sintese_aprendizagens"][ultimo_campo_sintese].extend(novos)
    return output

def extract_competencias_ef(pdf, page_range):
    """
    Extrai as competências (Nível 2 e Nível 4) detectando os títulos exatos na página.
    """
    print("--- Extraindo Competências (Área e Componente) ---")
    competencias = {}
    current_key = None
    buffer = []
    re_titulo = re.compile(r"COMPETÊNCIAS ESPECÍFICAS DE (.+?) PARA O ENSINO FUNDAMENTAL", re.IGNORECASE)
    
    for page_num in page_range:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        lines = text.split('\n')
        for line in lines:
            line_clean = clean_text_basic(line)
            if not line_clean: continue
            match = re_titulo.search(line_clean)
            if match:
                if current_key and buffer:
                    competencias[current_key] = [' '.join(buffer).strip() ]
                    buffer = []
                current_key = match.group(1).title()
                buffer = []
            elif current_key:
                if re.match(r"^\d+\.", line_clean):
                    if buffer:
                        competencias[current_key].append(' '.join(buffer).strip() )
                    buffer = [line_clean]
                else:
                    buffer.append(line_clean)
    if current_key and buffer:
        competencias[current_key] = [' '.join(buffer).strip() ]
    
    return competencias

def extract_ef_final(pdf):
    print("--- Processando Ensino Fundamental (Estrutura Completa 8 Níveis) ---")
    
    # 1. Extração Prévia de Competências (Levels 2 & 4)
    competencias_map = extract_competencias_ef(pdf, EF_PAGE_RANGE)
    
    # Inicializa a árvore com a estrutura fixa
    tree = {}
    
    for sigla, info in MAPA_EF_ESTRUTURA.items():
        area = info["area"]
        comp = info["componente"]
        
        if area not in tree:
            tree[area] = {
                "competencias_especificas_area": competencias_map.get(area, []),
                "componentes": {}
            }
        
        if comp not in tree[area]["componentes"]:
            tree[area]["componentes"][comp] = {
                "competencias_especificas_componente": competencias_map.get(comp, []),
                "anos": {}
            }

    # Variáveis de Estado (Memória de Células Mescladas)
    current_area = None
    current_comp = None
    previous_comp = None
    current_campo = None
    last_unidade = "Geral"
    last_objeto = "Geral"

    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        # Tenta identificar contexto da página (Componente no topo)
        text_page = page.extract_text() or ""
        text_upper = text_page.upper()
        
        for sigla, info in MAPA_EF_ESTRUTURA.items():
            if info["componente"].upper() in text_upper: 
                current_comp = info["componente"]
                current_area = info["area"]
                break
        
        # Persist if not found
        if not current_comp and previous_comp:
            current_comp = previous_comp
        
        # Detect current_campo from text
        lines = text_page.split('\n')
        for line in lines:
            line_clean = clean_text_basic(line)
            line_upper = line_clean.upper()
            if re.match(r"^[A-Z /()]+$", line_upper) and len(line_clean) > 10 and not re.search(r"\d", line_upper) and not "COMPETÊNCIAS" in line_upper and not "FUNDAMENTAL" in line_upper:
                current_campo = line_clean
        
        # Reset last_unidade e last_objeto se o componente mudou
        if current_comp != previous_comp:
            last_unidade = "Geral"
            last_objeto = "Geral"
            current_campo = None
            previous_comp = current_comp

        # Extração de Tabela
        tables = page.extract_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        for table in tables:
            if not table or len(table) < 2: continue
            
            # Detecção de Colunas
            header_row = [clean_text_basic(c).upper() for c in table[0] if c]
            header_str = " ".join(header_row)
            
            # Índices Padrão
            idx_unidade = 0
            idx_objeto = 1
            idx_habilidade = 2
            is_lp = False # Língua Portuguesa tem layout diferente
            is_objetos_table = False
            is_habilidades_table = False
            
            if current_comp == "Língua Portuguesa":
                if len(table[0]) >=4 or "CAMPO" in header_str:
                    is_lp = True
                    idx_unidade = 0 # Campo de Atuação (Level 6)
                    # Coluna 1 é "Práticas de Linguagem" (ignorar ou usar como unid se necessário)
                    idx_objeto = 2  # Objeto de Conhecimento (Level 7)
                    idx_habilidade = 3
                else:
                    if "PRÁTICAS DE LINGUAGEM" in header_str or "OBJETOS DE CONHECIMENTO" in header_str:
                        is_objetos_table = True
                        idx_unidade = 0 # Práticas or something
                        idx_objeto = 1 if "OBJETOS" in header_str else 0
                        idx_habilidade = -1
                    elif "HABILIDADES" in header_str or re.search(r"\d+º ANO", header_str):
                        is_habilidades_table = True
                        idx_left = 0
                        idx_right = 1 if len(table[0]) >1 else -1
            else:
                if len(table[0]) ==3 or "UNIDADE" in header_str:
                    idx_unidade, idx_objeto, idx_habilidade = 0, 1, 2
                else:
                    continue 

            # Processa linhas de dados
            for row in table[1:]:
                # For objetos table
                if is_objetos_table:
                    raw_unidade = clean_text_basic(row[idx_unidade])
                    raw_objeto = clean_text_basic(row[idx_objeto]) if len(row) > idx_objeto else ""
                    if raw_unidade: last_unidade = raw_unidade
                    if raw_objeto: last_objeto = raw_objeto
                    continue
                
                # For habilidades table
                if is_habilidades_table:
                    raw_habilidade = clean_text_basic(row[idx_left]) if len(row) > idx_left else ""
                    if raw_habilidade and RE_CODE_EF.search(raw_habilidade):
                        matches = list(RE_CODE_EF.finditer(raw_habilidade))
                        for i, match in enumerate(matches):
                            code = match.group(1)
                            sigla_comp = match.group(2)
                            start = match.end()
                            end = matches[i+1].start() if (i+1) < len(matches) else len(raw_habilidade)
                            desc = processar_descricao(raw_habilidade[start:end], code)
                            if sigla_comp not in MAPA_EF_ESTRUTURA: continue
                            info_now = MAPA_EF_ESTRUTURA[sigla_comp]
                            comp_now = info_now["componente"]
                            area_now = info_now["area"]
                            anos_list = expandir_anos_ef(code)
                            for ano in anos_list:
                                base_node = tree[area_now]["componentes"][comp_now]["anos"]
                                if ano not in base_node: base_node[ano] = {}
                                lvl6_key = current_campo or last_unidade or "Geral"
                                if lvl6_key not in base_node[ano]: base_node[ano][lvl6_key] = {}
                                lvl7_key = last_objeto or "Geral"
                                if lvl7_key not in base_node[ano][lvl6_key]: base_node[ano][lvl6_key][lvl7_key] = []
                                lista_habilidades = base_node[ano][lvl6_key][lvl7_key]
                                if not any(h['codigo'] == code for h in lista_habilidades):
                                    lista_habilidades.append({"codigo": code, "descricao": desc})
                    if idx_right != -1:
                        raw_habilidade = clean_text_basic(row[idx_right]) if len(row) > idx_right else ""
                        if raw_habilidade and RE_CODE_EF.search(raw_habilidade):
                            matches = list(RE_CODE_EF.finditer(raw_habilidade))
                            for i, match in enumerate(matches):
                                code = match.group(1)
                                sigla_comp = match.group(2)
                                start = match.end()
                                end = matches[i+1].start() if (i+1) < len(matches) else len(raw_habilidade)
                                desc = processar_descricao(raw_habilidade[start:end], code)
                                if sigla_comp not in MAPA_EF_ESTRUTURA: continue
                                info_now = MAPA_EF_ESTRUTURA[sigla_comp]
                                comp_now = info_now["componente"]
                                area_now = info_now["area"]
                                anos_list = expandir_anos_ef(code)
                                for ano in anos_list:
                                    base_node = tree[area_now]["componentes"][comp_now]["anos"]
                                    if ano not in base_node: base_node[ano] = {}
                                    lvl6_key = current_campo or last_unidade or "Geral"
                                    if lvl6_key not in base_node[ano]: base_node[ano][lvl6_key] = {}
                                    lvl7_key = last_objeto or "Geral"
                                    if lvl7_key not in base_node[ano][lvl6_key]: base_node[ano][lvl6_key][lvl7_key] = []
                                    lista_habilidades = base_node[ano][lvl6_key][lvl7_key]
                                    if not any(h['codigo'] == code for h in lista_habilidades):
                                        lista_habilidades.append({"codigo": code, "descricao": desc})
                    continue
                
                # Standard processing for other tables
                if len(row) <= idx_habilidade: continue
                
                raw_unidade = clean_text_basic(row[idx_unidade]) if len(row) > idx_unidade else ""
                raw_objeto = clean_text_basic(row[idx_objeto]) if len(row) > idx_objeto else ""
                raw_habilidade = clean_text_basic(row[idx_habilidade]) if len(row) > idx_habilidade else ""
                
                # Forward Fill
                if raw_unidade: last_unidade = raw_unidade
                else: raw_unidade = last_unidade
                
                if raw_objeto: last_objeto = raw_objeto
                else: raw_objeto = last_objeto
                
                # Skip if no habilidade or no code
                if not raw_habilidade or not RE_CODE_EF.search(raw_habilidade):
                    continue
                
                # If code in raw_objeto, perhaps error, skip or adjust
                if RE_CODE_EF.search(raw_objeto):
                    continue
                
                matches = list(RE_CODE_EF.finditer(raw_habilidade))
                if not matches: continue
                
                for i, match in enumerate(matches):
                    code = match.group(1)
                    sigla_comp = match.group(2)
                    start = match.end()
                    end = matches[i+1].start() if (i+1) < len(matches) else len(raw_habilidade)
                    desc = processar_descricao(raw_habilidade[start:end], code)
                    if sigla_comp not in MAPA_EF_ESTRUTURA: continue
                    info_now = MAPA_EF_ESTRUTURA[sigla_comp]
                    comp_now = info_now["componente"]
                    area_now = info_now["area"]
                    anos_list = expandir_anos_ef(code)
                    for ano in anos_list:
                        base_node = tree[area_now]["componentes"][comp_now]["anos"]
                        if ano not in base_node: base_node[ano] = {}
                        lvl6_key = current_campo or raw_unidade or "Geral"
                        if lvl6_key not in base_node[ano]: base_node[ano][lvl6_key] = {}
                        lvl7_key = raw_objeto or "Geral"
                        if lvl7_key not in base_node[ano][lvl6_key]: base_node[ano][lvl6_key][lvl7_key] = []
                        lista_habilidades = base_node[ano][lvl6_key][lvl7_key]
                        if not any(h['codigo'] == code for h in lista_habilidades):
                            lista_habilidades.append({"codigo": code, "descricao": desc})

    return tree

def extract_em(pdf):
    # (Código Original Mantido - Ensino Médio)
    print("--- Processando Ensino Médio ---")
    data = []
    current_area = "Geral"
    def clean_text_em(text): return re.sub(r'\s+', ' ', unicodedata.normalize("NFKC", text)).strip()
    RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")
    
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
    if not os.path.exists(PDF_PATH): print("Arquivo PDF não encontrado."); return
    try: pdf = pdfplumber.open(PDF_PATH)
    except Exception as e: print(f"Erro: {e}"); return

    ei_data = extract_ei_final(pdf)
    ef_data = extract_ef_final(pdf) # Nova versão estruturada
    em_data = extract_em(pdf)
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    with open("bncc_ei.json", "w", encoding="utf-8") as f: json.dump(ei_data, f, ensure_ascii=False, indent=2)
    with open("bncc_ef.json", "w", encoding="utf-8") as f: json.dump(ef_data, f, ensure_ascii=False, indent=2)
    with open("bncc_em.json", "w", encoding="utf-8") as f: json.dump(em_data, f, ensure_ascii=False, indent=2)
    print("Processo concluído.")

if __name__ == "__main__":
    main()