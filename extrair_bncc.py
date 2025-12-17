import pdfplumber
import re
import json
import unicodedata
import os

# --- CONFIGURAÇÃO E CONSTANTES ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"

# Intervalos de Páginas (Ajustados para cobrir também a Síntese na EI)
EI_PAGE_RANGE = range(35, 60)   # Estendido para garantir leitura da Síntese
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
    Limpa a descrição especificamente para EI.
    MELHORIA: Adicionado '\(' e '\)' na regex para remover parênteses fantasmas.
    """
    if codigo:
        texto = texto_bruto.replace(codigo, "")
    else:
        texto = texto_bruto
    
    # Remove pontuação solta tipo '(', ')', '.', '-' e espaços do início
    texto = re.sub(r"^[\s\(\)\.\-]+", "", texto)
    return texto.strip()

def extract_code_desc_regex(text, pattern):
    """Legado: usado para EF e EM (Mantido conforme solicitado)"""
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

# --- EXTRATORES ---

def extract_ei_final(pdf):
    print("--- Processando Educação Infantil (Versão Final com Síntese) ---")
    
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
        "sintese_aprendizagens": {k: [] for k in CAMPOS_EXPERIENCIA}, # Nova Chave
        "objetivos_aprendizagem": {
            "EI01": {k: [] for k in CAMPOS_EXPERIENCIA},
            "EI02": {k: [] for k in CAMPOS_EXPERIENCIA},
            "EI03": {k: [] for k in CAMPOS_EXPERIENCIA}
        }
    }

    col_map_obj = {0: "EI01", 1: "EI02", 2: "EI03"}
    
    # Controle para saber qual Campo de Experiência estamos lendo na tabela de Síntese
    ultimo_campo_sintese = None

    for page_num in EI_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        # Extração de tabelas
        tables = page.extract_tables({
            "vertical_strategy": "lines", 
            "horizontal_strategy": "lines"
        })

        for table in tables:
            for row in table:
                # Limpeza básica da linha para identificação
                row_cells = [clean_text(c) for c in row if c]
                row_str = "".join(row_cells).upper()
                
                # --- LÓGICA 1: EXTRAÇÃO DE OBJETIVOS (Tabelas padrão) ---
                # Identifica se é uma linha de conteúdo de objetivos (tem códigos EI..)
                tem_codigo = False
                for cell in row_cells:
                    if "EI" in cell and RE_CODE_EI_FULL.search(cell):
                        tem_codigo = True
                        break
                
                if tem_codigo:
                    for col_idx, cell_text in enumerate(row):
                        if not cell_text or col_idx not in col_map_obj: continue
                        
                        cleaned = clean_text(cell_text)
                        
                        # MELHORIA: finditer para capturar múltiplos códigos na mesma célula
                        matches = list(RE_CODE_EI_FULL.finditer(cleaned))
                        
                        for i, match in enumerate(matches):
                            codigo_completo = match.group(0)
                            faixa_id = "EI" + match.group(1)
                            sigla_campo = match.group(2)
                            
                            # Recorte do texto da descrição
                            start_idx = match.end()
                            # Se houver outro match depois, o texto vai até o início dele
                            end_idx = matches[i+1].start() if (i + 1) < len(matches) else len(cleaned)
                            texto_bruto = cleaned[start_idx:end_idx]
                            
                            if faixa_id in output["objetivos_aprendizagem"] and sigla_campo in CAMPOS_EXPERIENCIA:
                                desc = processar_descricao_ei(texto_bruto, "") # Passamos vazio pois já cortamos
                                
                                output["objetivos_aprendizagem"][faixa_id][sigla_campo].append({
                                    "codigo": codigo_completo,
                                    "descricao": desc
                                })

                # --- LÓGICA 2: EXTRAÇÃO DA SÍNTESE DAS APRENDIZAGENS ---
                # A tabela de síntese geralmente tem 2 colunas: [Nome do Campo] | [Texto da Síntese]
                # Ou linhas de continuação onde a primeira coluna é vazia.
                elif "SÍNTESE" in row_str or len(row) == 2:
                    if "SÍNTESE" in row_str and len(row_cells) < 3: 
                        continue # Pula cabeçalho da tabela
                    
                    if len(row) == 2:
                        col_campo = clean_text(row[0])
                        col_texto = clean_text(row[1])
                        
                        # Tenta identificar o campo na primeira coluna
                        campo_detectado = None
                        for sigla, nome in CAMPOS_EXPERIENCIA.items():
                            # Check flexível (in) pois o PDF pode quebrar linhas
                            if nome.upper() in col_campo.upper():
                                campo_detectado = sigla
                                break
                        
                        if campo_detectado:
                            ultimo_campo_sintese = campo_detectado
                        
                        # Se temos um campo ativo e texto na coluna da direita
                        if ultimo_campo_sintese and col_texto and len(col_texto) > 10:
                            # Às vezes o PDF traz vários pontos em uma string só. 
                            # Vamos tentar separar por quebras se houver, ou adicionar como item único.
                            # Na BNCC síntese costuma ser parágrafos ou bullets.
                            output["sintese_aprendizagens"][ultimo_campo_sintese].append(col_texto)

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

    # 1. Extração da EI (Lógica Final com Síntese e Correções)
    ei_data = extract_ei_final(pdf)
    
    # 2. Extração do EF (Lógica Original Mantida)
    ef_data = extract_ef(pdf)
    # Deduplicação EF
    ef_data = list({v['code']: v for v in ef_data}.values())

    # 3. Extração do EM (Lógica Original Mantida)
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