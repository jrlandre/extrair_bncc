import pdfplumber
import re
import json
import unicodedata
import os

# --- CONFIGURAÇÃO E CONSTANTES ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"

# Intervalos de Páginas
EI_PAGE_RANGE = range(35, 57)   # Cobre introdução e tabelas da EI
EF_PAGE_RANGE = range(57, 460)  # Ensino Fundamental
EM_PAGE_RANGE = range(460, 600) # Ensino Médio

# Regex para captura de códigos
# EI: Captura grupos para montar a hierarquia (Faixa, Campo, Sequencial)
RE_CODE_EI_FULL = re.compile(r"EI(\d{2})([A-Z]{2})\d{2}")
# EF e EM: Mantidos do original para compatibilidade
RE_CODE_EF = re.compile(r"(EF\d{2,3}[A-Z]{2,4}\d{2,3})")
RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")

# Mapeamentos Estáticos (EI)
CAMPOS_EXPERIENCIA = {
    "EO": "O eu, o outro e o nós",
    "CG": "Corpo, gestos e movimentos",
    "TS": "Traços, sons, cores e formas",
    "EF": "Escuta, fala, pensamento e imaginação",
    "ET": "Espaços, tempos, quantidades, relações e transformações"
}

DIREITOS_APRENDIZAGEM = [
    "Conviver", "Brincar", "Participar", "Explorar", "Expressar", "Conhecer-se"
]

# --- UTILITÁRIOS ---
def clean_text(text):
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r'\s+', ' ', text).strip()

def processar_descricao_ei(texto_bruto, codigo):
    """
    Limpa a descrição especificamente para EI, removendo o código e
    pontuações de início de lista (parênteses, hífens).
    """
    texto = texto_bruto.replace(codigo, "")
    # Remove pontuação solta tipo ')', '.', '-' que sobrava no PDF
    texto = re.sub(r"^[\s\(\)\.\-]+", "", texto)
    return texto.strip()

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
        # Verifica se é lista ou dict para contar itens
        count = len(data) if isinstance(data, list) else len(str(data))
        print(f"-> Salvo com sucesso: {filename}")
    except Exception as e:
        print(f"ERRO ao salvar {filename}: {e}")

# --- EXTRATORES ---

def extract_ei_v2(pdf):
    """
    Nova lógica para Educação Infantil:
    - Gera estrutura hierárquica (JSON aninhado).
    - Resolve o problema de 'Campo não identificado' usando o próprio código BNCC.
    - Limpa caracteres sujos da descrição.
    """
    print("--- Processando Educação Infantil (Estrutura Otimizada) ---")
    
    # Estrutura base da API
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
        }
    }

    # Mapa de colunas do PDF (índice -> id da faixa)
    col_map = {0: "EI01", 1: "EI02", 2: "EI03"}

    for page_num in EI_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        tables = page.extract_tables({
            "vertical_strategy": "lines", 
            "horizontal_strategy": "lines"
        })

        for table in tables:
            for row in table:
                # Pula cabeçalhos e linhas vazias
                row_str = "".join([str(c) for c in row if c]).upper()
                if not row_str or "CAMPO DE EXPERIÊNCIAS" in row_str or "OBJETIVOS DE APRENDIZAGEM" in row_str:
                    continue
                
                for col_idx, cell_text in enumerate(row):
                    if not cell_text or col_idx not in col_map: continue
                    
                    cleaned = clean_text(cell_text)
                    
                    # Regex captura a estrutura EI + Faixa + Campo
                    match = RE_CODE_EI_FULL.search(cleaned)
                    if match:
                        codigo_completo = match.group(0) # Ex: EI02TS01
                        faixa_id = "EI" + match.group(1) # Ex: EI02
                        sigla_campo = match.group(2)     # Ex: TS
                        
                        # Segurança: verifica se o código capturado é válido na nossa estrutura
                        if faixa_id in output["objetivos_aprendizagem"] and sigla_campo in CAMPOS_EXPERIENCIA:
                            desc = processar_descricao_ei(cleaned, codigo_completo)
                            
                            obj_data = {
                                "codigo": codigo_completo,
                                "descricao": desc
                            }
                            
                            # Adiciona na lista correta
                            output["objetivos_aprendizagem"][faixa_id][sigla_campo].append(obj_data)
    
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
                cleaned_row = [clean_text(cell) if cell else "" for cell in row]
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
            clean_line = clean_text(line)
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

    # 1. Extração da EI (Nova Lógica)
    ei_data = extract_ei_v2(pdf)
    
    # 2. Extração do EF (Lógica Original)
    ef_data = extract_ef(pdf)
    # Deduplicação EF
    ef_data = list({v['code']: v for v in ef_data}.values())

    # 3. Extração do EM (Lógica Original)
    em_data = extract_em(pdf)
    # Deduplicação EM
    em_data = list({v['code']: v for v in em_data}.values())
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    save_json(ei_data, "bncc_ei.json")
    save_json(ef_data, "bncc_ef.json")
    save_json(em_data, "bncc_em.json")
    
    print("\nProcesso concluído.")

if __name__ == "__main__":
    main()