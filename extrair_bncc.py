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

# --- MINERAÇÃO DE COMPETÊNCIAS V5 (MATCH EXATO) ---
def extrair_competencias_texto(pdf, page_range):
    print("--- Mineração de Competências (EF) - Modo V5 (Títulos Fixos) ---")
    competencias_map = {}
    
    # Títulos conhecidos na BNCC para busca exata (normalizada)
    TITULOS_ALVO = {
        "LINGUAGENS": "Linguagens",
        "LINGUA PORTUGUESA": "Língua Portuguesa",
        "ARTE": "Arte",
        "EDUCACAO FISICA": "Educação Física",
        "LINGUA INGLESA": "Língua Inglesa",
        "MATEMATICA": "Matemática",
        "CIENCIAS DA NATUREZA": "Ciências da Natureza",
        "CIENCIAS": "Ciências",
        "CIENCIAS HUMANAS": "Ciências Humanas",
        "GEOGRAFIA": "Geografia",
        "HISTORIA": "História",
        "ENSINO RELIGIOSO": "Ensino Religioso"
    }
    
    current_key = None
    buffer_list = []
    
    for page_num in page_range:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text()
        if not text: continue
        
        # 1. Busca Títulos
        text_norm = clean_text_basic(text).upper()
        # Remove acentos para comparação
        text_norm_no_acc = ''.join(c for c in unicodedata.normalize('NFD', text_norm) if unicodedata.category(c) != 'Mn')
        
        found_new_key = False
        if "COMPETENCIAS ESPECIFICAS" in text_norm_no_acc and "ENSINO FUNDAMENTAL" in text_norm_no_acc:
            for titulo_norm, titulo_real in TITULOS_ALVO.items():
                if titulo_norm in text_norm_no_acc:
                    # Achamos um título! Salva o anterior.
                    if current_key and buffer_list:
                        if current_key not in competencias_map: competencias_map[current_key] = []
                        competencias_map[current_key].extend(buffer_list)
                    
                    current_key = titulo_real # Usa o nome bonito
                    buffer_list = []
                    found_new_key = True
                    break
        
        # 2. Extrai Itens
        lines = text.split('\n')
        for line in lines:
            line_clean = clean_text_basic(line)
            if not line_clean: continue
            
            if current_key:
                # Padrão: Número no início da linha (1., 2, 01)
                match_item = re.match(r"^(\d+)[.\)]?\s+(.*)", line_clean)
                if match_item:
                    buffer_list.append(match_item.group(2).strip())
                elif buffer_list and len(line_clean) > 5 and not line_clean.isupper():
                    # Continuação
                    if not re.match(r"^\d+$", line_clean) and "COMPETÊNCIAS" not in line_clean.upper():
                        buffer_list[-1] += " " + line_clean

    # Salva o último
    if current_key and buffer_list:
        if current_key not in competencias_map: competencias_map[current_key] = []
        competencias_map[current_key].extend(buffer_list)
        
    return competencias_map

# --- EXTRATORES ---

def extract_ei_final(pdf):
    # (Mantido - EI está OK)
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

def extract_ef_v5_platinum(pdf):
    print("--- Processando Ensino Fundamental (V5 Platinum: Memória Agressiva) ---")
    
    tree = {}
    
    # 1. Competências com Match Seguro
    # O mapeamento retorna chaves como "Língua Portuguesa"
    # Precisamos normalizar para bater com MAPA_EF_ESTRUTURA
    comps_raw = extrair_competencias_texto(pdf, EF_PAGE_RANGE)
    
    for sigla, info in MAPA_EF_ESTRUTURA.items():
        area_nome = info["area"]
        comp_nome = info["componente"]
        
        if area_nome not in tree:
            # Tenta encontrar a chave exata ou parcial
            comps_area = comps_raw.get(area_nome, [])
            if not comps_area: # Tenta match parcial
                 for k, v in comps_raw.items():
                     if area_nome in k or k in area_nome: comps_area = v; break
            tree[area_nome] = {"competencias_especificas_area": comps_area, "componentes": {}}
        
        if comp_nome not in tree[area_nome]["componentes"]:
            comps_comp = comps_raw.get(comp_nome, [])
            if not comps_comp:
                 for k, v in comps_raw.items():
                     if comp_nome in k or k in comp_nome: comps_comp = v; break
            tree[area_nome]["componentes"][comp_nome] = {"competencias_especificas_componente": comps_comp, "anos": {}}

    current_lp_field = "Campo de atuação geral"
    
    # MEMÓRIA GLOBAL DE COLUNAS (Persistente entre linhas)
    mem_col0 = None
    mem_col1 = None

    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        tables = page.extract_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})

        for table in tables:
            for row in table:
                row_cells_raw = [clean_text_basic(c) for c in row] 
                row_str = "".join(row_cells_raw).upper()
                
                # Ignora cabeçalhos
                if not row_str or "HABILIDADES" in row_str or "PRÁTICAS DE LINGUAGEM" in row_str:
                    continue

                tem_skill = False
                for c in row_cells_raw:
                    if "EF" in c and RE_CODE_EF.search(c): tem_skill = True; break

                # --- ATUALIZAÇÃO DE MEMÓRIA (Antes de processar skill) ---
                if not tem_skill:
                    if "CAMPO" in row_str:
                        possivel_campo = next((c for c in row_cells_raw if c), "")
                        if len(possivel_campo) > 5:
                            current_lp_field = possivel_campo
                        continue
                else:
                    # É linha de skill. Atualiza memórias se houver texto à esquerda.
                    skill_idx = -1
                    for idx in range(len(row_cells_raw)-1, -1, -1):
                        if RE_CODE_EF.search(row_cells_raw[idx]):
                            skill_idx = idx; break
                    
                    if skill_idx == -1: continue

                    # Atualiza Col 0 (Prática / Unidade)
                    if skill_idx >= 1:
                         val = row_cells_raw[0]
                         # Só atualiza se for texto válido e não um número de página
                         if val and len(val) > 3 and not re.match(r"^\d+$", val):
                             mem_col0 = val
                    
                    # Atualiza Col 1 (Objeto)
                    if skill_idx >= 2:
                        val = row_cells_raw[1]
                        if val and len(val) > 3:
                            mem_col1 = val
                    elif skill_idx == 1:
                        # Em layouts de 2 colunas, às vezes col0 é o objeto
                        val = row_cells_raw[0]
                        if val and len(val) > 3:
                            mem_col1 = val

                # --- PROCESSAMENTO DA SKILL ---
                if tem_skill:
                    cell_text = row_cells_raw[skill_idx]
                    matches = list(RE_CODE_EF.finditer(cell_text))
                    
                    for i, match in enumerate(matches):
                        skill_code = match.group(1)
                        sigla_comp = match.group(2)
                        
                        start = match.end()
                        end = matches[i+1].start() if (i+1) < len(matches) else len(cell_text)
                        
                        raw_desc = cell_text[start:end]
                        if raw_desc.strip().endswith('('): raw_desc = raw_desc.strip()[:-1]
                        desc = processar_descricao(raw_desc, "")
                        
                        if sigla_comp in MAPA_EF_ESTRUTURA:
                            info = MAPA_EF_ESTRUTURA[sigla_comp]
                            area = info["area"]
                            comp = info["componente"]
                            anos = expandir_anos_ef(skill_code)
                            
                            # Definição de Níveis usando Memória
                            if sigla_comp == "LP":
                                nivel_6 = current_lp_field
                                # Em LP: Col 0=Prática, Col 1=Objeto
                                # Se a linha atual tiver texto, usa ele. Se não, usa memória.
                                # Se memória for None, usa "Geral"
                                
                                if skill_idx >= 2:
                                    val_obj = row_cells_raw[1] if row_cells_raw[1] else mem_col1
                                elif skill_idx == 1:
                                    val_obj = row_cells_raw[0] if row_cells_raw[0] else mem_col1
                                else:
                                    val_obj = mem_col1
                                
                                nivel_7 = val_obj if val_obj else "Geral"
                                
                            else:
                                # Outros: Unidade | Objeto | Skill
                                if skill_idx >= 2:
                                    val_uni = row_cells_raw[0] if row_cells_raw[0] else mem_col0
                                    val_obj = row_cells_raw[1] if row_cells_raw[1] else mem_col1
                                elif skill_idx == 1:
                                    val_uni = mem_col0 # Assume mesclada
                                    val_obj = row_cells_raw[0] if row_cells_raw[0] else mem_col1
                                else:
                                    val_uni = mem_col0
                                    val_obj = mem_col1

                                nivel_6 = val_uni if val_uni else "Geral"
                                nivel_7 = val_obj if val_obj else "Geral"

                            branch = tree[area]["componentes"][comp]["anos"]
                            for ano in anos:
                                if ano not in branch: branch[ano] = {}
                                n6, n7 = nivel_6.strip(), nivel_7.strip()
                                if n6 not in branch[ano]: branch[ano][n6] = {}
                                if n7 not in branch[ano][n6]: branch[ano][n6][n7] = []
                                
                                exists = any(h['codigo'] == skill_code for h in branch[ano][n6][n7])
                                if not exists:
                                    branch[ano][n6][n7].append({"codigo": skill_code, "descricao": desc})
    return tree

def extract_em(pdf):
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
    ef_data = extract_ef_v5_platinum(pdf) # Versão Platinum
    em_data = extract_em(pdf)
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    with open("bncc_ei.json", "w", encoding="utf-8") as f: json.dump(ei_data, f, ensure_ascii=False, indent=2)
    with open("bncc_ef_FINAL.json", "w", encoding="utf-8") as f: json.dump(ef_data, f, ensure_ascii=False, indent=2)
    with open("bncc_em.json", "w", encoding="utf-8") as f: json.dump(em_data, f, ensure_ascii=False, indent=2)
    print("Processo concluído. Verifique bncc_ef_FINAL.json")

if __name__ == "__main__":
    main()