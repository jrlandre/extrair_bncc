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
RE_CODE_EF = re.compile(r"(EF\d{2,3}[A-Z]{2,4}\d{2,3})")
RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")

CAMPOS_EXPERIENCIA = {
    "EO": "O eu, o outro e o nós",
    "CG": "Corpo, gestos e movimentos",
    "TS": "Traços, sons, cores e formas",
    "EF": "Escuta, fala, pensamento e imaginação",
    "ET": "Espaços, tempos, quantidades, relações e transformações"
}

# Texto COMPLETO dos direitos (conforme solicitado)
DIREITOS_APRENDIZAGEM = [
    "Conviver com outras crianças e adultos, em pequenos e grandes grupos, utilizando diferentes linguagens, ampliando o conhecimento de si e do outro, o respeito em relação à cultura e às diferenças entre as pessoas.",
    "Brincar cotidianamente de diversas formas, em diferentes espaços e tempos, com diferentes parceiros (crianças e adultos), ampliando e diversificando seu acesso a produções culturais, seus conhecimentos, sua imaginação, sua criatividade, suas experiências emocionais, corporais, sensoriais, expressivas, cognitivas, sociais e relacionais.",
    "Participar ativamente, com adultos e outras crianças, tanto do planejamento da gestão da escola e das atividades propostas pelo educador quanto da realização das atividades da vida cotidiana, tais como a escolha das brincadeiras, dos materiais e dos ambientes, desenvolvendo diferentes linguagens e elaborando conhecimentos, decidindo e se posicionando.",
    "Explorar movimentos, gestos, sons, formas, texturas, cores, palavras, emoções, transformações, relacionamentos, histórias, objetos, elementos da natureza, na escola e fora dela, ampliando seus saberes sobre a cultura, em suas diversas modalidades: as artes, a escrita, a ciência e a tecnologia.",
    "Expressar, como sujeito dialógico, criativo e sensível, suas necessidades, emoções, sentimentos, dúvidas, hipóteses, descobertas, opiniões, questionamentos, por meio de diferentes linguagens.",
    "Conhecer-se e construir sua identidade pessoal, social e cultural, constituindo uma imagem positiva de si e de seus grupos de pertencimento, nas diversas experiências de cuidados, interações, brincadeiras e linguagens vivenciadas na instituição escolar e em seu contexto familiar e comunitário."
]

# --- UTILITÁRIOS ---

def clean_text_basic(text):
    """Limpeza padrão que remove quebras de linha (para objetivos curtos)."""
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_item_sintese(text):
    """Limpeza fina para um item já separado da síntese."""
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    # Remove bullets e hífens do início, mas mantém pontuação interna
    text = re.sub(r"^[\s•\-]+", "", text)
    # Remove espaços extras
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def processar_descricao_ei(texto_bruto, codigo):
    if codigo:
        texto = texto_bruto.replace(codigo, "")
    else:
        texto = texto_bruto
    return re.sub(r"^[\s\(\)\.\-]+", "", texto).strip()

def extract_code_desc_regex(text, pattern):
    """Legado: usado para EF e EM"""
    if not text: return None, None
    match = pattern.search(text)
    if match:
        code = match.group(1)
        desc = text[match.end():].strip()
        desc = re.sub(r"^[\s\.\-]+", "", desc)
        return code, desc
    return None, None

def save_json(data, filename):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"-> Salvo com sucesso: {filename}")
    except Exception as e:
        print(f"ERRO ao salvar {filename}: {e}")

# --- LÓGICA DE SEPARAÇÃO ROBUSTA ---

def separar_itens_sintese(texto_bruto_celula):
    """
    Separa itens da síntese baseando-se em Quebras de Linha + Capitalização.
    Não depende de ponto e vírgula.
    """
    if not texto_bruto_celula: return []
    
    # 1. Normaliza unicode, mas MANTÉM os \n originais
    texto = unicodedata.normalize("NFKC", texto_bruto_celula)
    
    # 2. Divide em linhas físicas
    linhas = texto.split('\n')
    
    itens = []
    buffer_atual = []

    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa: continue # Ignora linhas vazias

        # Identifica se é início de novo item
        eh_bullet = linha_limpa.startswith(('•', '-', '·'))
        comeca_maiuscula = linha_limpa[0].isupper()
        
        # Heurística: É novo item se tem bullet OU (começa com Maiúscula E não é continuação óbvia)
        # Se o buffer está vazio, com certeza é o primeiro item
        if not buffer_atual:
            buffer_atual.append(linha_limpa)
        
        elif eh_bullet:
            # Salvamos o anterior e começamos um novo
            itens.append(" ".join(buffer_atual))
            buffer_atual = [linha_limpa]
            
        elif comeca_maiuscula:
            # Ponto delicado: às vezes uma frase quebra e a próxima linha começa com Nome Próprio.
            # Mas na Síntese da BNCC, geralmente Maiúscula = Novo Objetivo.
            # Vamos assumir novo item, exceto se a linha anterior terminou sem pontuação 'finalizadora'?
            # Para ficar ROBUSTO contra ; interno, vamos confiar na quebra de parágrafo visual.
            itens.append(" ".join(buffer_atual))
            buffer_atual = [linha_limpa]
            
        else:
            # Começa com minúscula (ex: "e seus familiares..."), é continuação
            buffer_atual.append(linha_limpa)
    
    # Adiciona o que sobrou no buffer
    if buffer_atual:
        itens.append(" ".join(buffer_atual))

    # Limpeza final de cada item
    itens_finais = []
    for it in itens:
        limpo = clean_item_sintese(it)
        if len(limpo) > 5: # Ignora sujeira muito curta
            # Garante ponto final estético
            if not limpo.endswith('.'): limpo += "."
            itens_finais.append(limpo)
            
    return itens_finais

# --- EXTRATORES ---

def extract_ei_final(pdf):
    print("--- Processando Educação Infantil (Lógica Robusta v4) ---")
    
    output = {
        "metadata": {
            "etapa": "Educação Infantil",
            "direitos_aprendizagem": DIREITOS_APRENDIZAGEM,
            "faixas_etarias": [
                {"id": "EI01", "descricao": "Bebês (zero a 1 ano e 6 meses)"},
                {"id": "EI02", "descricao": "Crianças bem pequenas (1 ano e 7 meses a 3 anos e 11 meses)"},
                {"id": "EI03", "descricao": "Crianças pequenas (4 anos a 5 anos e 11 meses)"}
            ],
            "campos_experiencia": [
                {"sigla": k, "nome": v} for k, v in CAMPOS_EXPERIENCIA.items()
            ]
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
        
        tables = page.extract_tables({
            "vertical_strategy": "lines", 
            "horizontal_strategy": "lines"
        })

        for table in tables:
            for row in table:
                # Texto para identificação (flat)
                row_cells_clean = [clean_text_basic(c) for c in row if c]
                row_str = "".join(row_cells_clean).upper()
                
                # --- 1. OBJETIVOS ---
                tem_codigo = False
                for cell in row_cells_clean:
                    if "EI" in cell and RE_CODE_EI_FULL.search(cell):
                        tem_codigo = True
                        break
                
                if tem_codigo:
                    for col_idx, cell_text in enumerate(row):
                        if not cell_text or col_idx not in col_map_obj: continue
                        cleaned = clean_text_basic(cell_text)
                        
                        matches = list(RE_CODE_EI_FULL.finditer(cleaned))
                        for i, match in enumerate(matches):
                            codigo_completo = match.group(0)
                            faixa_id = "EI" + match.group(1)
                            sigla_campo = match.group(2)
                            
                            start_idx = match.end()
                            end_idx = matches[i+1].start() if (i + 1) < len(matches) else len(cleaned)
                            texto_bruto = cleaned[start_idx:end_idx]
                            
                            if faixa_id in output["objetivos_aprendizagem"] and sigla_campo in CAMPOS_EXPERIENCIA:
                                desc = processar_descricao_ei(texto_bruto, "")
                                output["objetivos_aprendizagem"][faixa_id][sigla_campo].append({
                                    "codigo": codigo_completo,
                                    "descricao": desc
                                })

                # --- 2. SÍNTESE (NOVA LÓGICA) ---
                elif "SÍNTESE" in row_str or len(row) == 2:
                    if "SÍNTESE" in row_str and len(row_cells_clean) < 3: 
                        continue 
                    
                    if len(row) == 2:
                        # Pega o texto bruto DA CÉLULA (sem clean_basic) para manter \n
                        col_campo_raw = row[0] if row[0] else ""
                        col_texto_raw = row[1] if row[1] else ""
                        
                        # Identifica campo
                        col_campo_clean = clean_text_basic(col_campo_raw)
                        for sigla, nome in CAMPOS_EXPERIENCIA.items():
                            if nome.upper() in col_campo_clean.upper():
                                ultimo_campo_sintese = sigla
                                break
                        
                        if ultimo_campo_sintese and col_texto_raw:
                            # Chama a função robusta
                            novos_itens = separar_itens_sintese(col_texto_raw)
                            output["sintese_aprendizagens"][ultimo_campo_sintese].extend(novos_itens)

    return output

def extract_ef(pdf):
    print("--- Processando Ensino Fundamental ---")
    data = []
    state = {"unit": None, "object": None}

    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        tables = page.extract_tables({
            "vertical_strategy": "lines", 
            "horizontal_strategy": "lines",
            "intersection_y_tolerance": 5
        })

        for table in tables:
            for row in table:
                if not row or not any(row): continue
                cleaned_row = [clean_text_basic(cell) if cell else "" for cell in row]
                row_str = "".join(cleaned_row).upper()

                if "UNIDADES TEMÁTICAS" in row_str or "PRÁTICAS DE LINGUAGEM" in row_str or "HABILIDADES" in row_str:
                    continue

                if len(cleaned_row) >= 3:
                    if cleaned_row[0]: state["unit"] = cleaned_row[0]
                    if cleaned_row[1]: state["object"] = cleaned_row[1]
                    skill_text = cleaned_row[2]
                elif len(cleaned_row) == 2:
                    if cleaned_row[0]: state["object"] = cleaned_row[0]
                    skill_text = cleaned_row[1]
                else:
                    skill_text = cleaned_row[-1]

                if "EF" in skill_text:
                    code, desc = extract_code_desc_regex(skill_text, RE_CODE_EF)
                    if code:
                        comp_match = re.search(r"EF\d{2,3}([A-Z]{2,4})\d{2,3}", code)
                        comp = comp_match.group(1) if comp_match else "Geral"
                        data.append({
                            "code": code,
                            "description": desc,
                            "component": comp,
                            "thematic_unit": state["unit"],
                            "knowledge_object": state["object"]
                        })
    return data

def extract_em(pdf):
    print("--- Processando Ensino Médio ---")
    data = []
    current_area = "Geral"

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
            clean_line = clean_text_basic(line)
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
            
    return data

# --- EXECUÇÃO ---

def main():
    print(f"Abrindo PDF: {PDF_PATH}")
    if not os.path.exists(PDF_PATH):
        print("Arquivo PDF não encontrado na pasta.")
        return

    try:
        pdf = pdfplumber.open(PDF_PATH)
    except Exception as e:
        print(f"Erro crítico ao abrir PDF: {e}")
        return

    ei_data = extract_ei_final(pdf)
    ef_data = extract_ef(pdf)
    ef_data = list({v['code']: v for v in ef_data}.values()) 
    em_data = extract_em(pdf)
    em_data = list({v['code']: v for v in em_data}.values()) 
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    save_json(ei_data, "bncc_ei.json")
    save_json(ef_data, "bncc_ef.json")
    save_json(em_data, "bncc_em.json")
    
    print("\nProcesso concluído.")

if __name__ == "__main__":
    main()