import pdfplumber
import re
import json
import unicodedata
import os

# --- CONFIGURAÇÃO ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"
EI_PAGE_RANGE = range(35, 57)
EF_PAGE_RANGE = range(57, 460)
EM_PAGE_RANGE = range(460, 600)

# Regex para captura de códigos
RE_CODE_EI = re.compile(r"(EI\d{2}[A-Z]{2}\d{2})")
RE_CODE_EF = re.compile(r"(EF\d{2,3}[A-Z]{2,4}\d{2,3})")
RE_CODE_EM = re.compile(r"(EM\d{2,3}[A-Z]{2,4}\d{2,3})")

# --- UTILITÁRIOS ---
def clean_text(text):
    if not text: return ""
    # Normaliza caracteres (remove acentos quebrados, etc)
    text = unicodedata.normalize("NFKC", text)
    # Remove quebras de linha dentro da célula e espaços extras
    return re.sub(r'\s+', ' ', text).strip()

def extract_code_desc_regex(text, pattern):
    """
    Separa código e descrição usando Regex.
    Retorna (codigo, descricao) ou (None, None).
    """
    if not text: return None, None
    match = pattern.search(text)
    if match:
        code = match.group(1)
        desc = text[match.end():].strip()
        # Remove pontuação inicial comum em listas (hífens, pontos)
        desc = re.sub(r"^[\s\.\-]+", "", desc)
        return code, desc
    return None, None

def save_json(data, filename):
    """
    Salva os dados em JSON, garantindo sobrescrita (override).
    """
    if os.path.exists(filename):
        print(f"Arquivo '{filename}' já existe. Sobrescrevendo...")
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"-> Salvo com sucesso: {filename} ({len(data)} itens)")
    except Exception as e:
        print(f"ERRO ao salvar {filename}: {e}")

# --- EXTRATORES ---

def extract_ei(pdf):
    print("--- Processando Educação Infantil ---")
    data = []
    
    # Mapeamento de colunas da tabela EI para faixas etárias
    # 0: Bebês, 1: Crianças Bem Pequenas, 2: Crianças Pequenas
    age_map = {
        0: "Bebês (zero a 1 ano e 6 meses)",
        1: "Crianças bem pequenas (1 ano e 7 meses a 3 anos e 11 meses)",
        2: "Crianças pequenas (4 anos a 5 anos e 11 meses)"
    }
    
    current_field = "Campo não identificado"

    for page_num in EI_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        # Extrai tabelas preservando layout visual
        tables = page.extract_tables({
            "vertical_strategy": "lines", 
            "horizontal_strategy": "lines"
        })

        for table in tables:
            for row in table:
                # Transforma a linha em string única para checar cabeçalhos
                row_str = "".join([str(c) for c in row if c]).upper()
                
                # Tenta capturar o Campo de Experiências (geralmente em destaque ou mesclado)
                if "CAMPO DE EXPERIÊNCIAS" in row_str:
                    clean_header = clean_text(row_str)
                    # Exemplo: CAMPO DE EXPERIÊNCIAS "O EU, O OUTRO E O NÓS"
                    if '"' in clean_header:
                        current_field = clean_header.split('"')[1]
                    elif "TRAÇOS, SONS" in clean_header: # Fallback para casos sem aspas
                         current_field = "Traços, sons, cores e formas"
                    # Adicione outros elifs se necessário para normalizar nomes
                    continue

                if "OBJETIVOS DE APRENDIZAGEM" in row_str:
                    continue

                # Processa as 3 colunas de faixas etárias
                for col_idx, cell_text in enumerate(row):
                    if not cell_text: continue
                    
                    cleaned = clean_text(cell_text)
                    code, desc = extract_code_desc_regex(cleaned, RE_CODE_EI)
                    
                    if code:
                        data.append({
                            "code": code,
                            "description": desc,
                            "field": current_field,
                            "age_group": age_map.get(col_idx, "Outros")
                        })
    return data

def extract_ef(pdf):
    print("--- Processando Ensino Fundamental ---")
    data = []
    
    # Estado para persistência de células mescladas
    state = {
        "unit": None,      # Unidade Temática
        "object": None     # Objeto de Conhecimento
    }

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
                # Pula linhas vazias
                if not row or not any(row): continue
                
                # Limpa células
                cleaned_row = [clean_text(cell) if cell else "" for cell in row]
                row_str = "".join(cleaned_row).upper()

                # Ignora cabeçalhos
                if "UNIDADES TEMÁTICAS" in row_str or "PRÁTICAS DE LINGUAGEM" in row_str:
                    continue
                if "HABILIDADES" in row_str:
                    continue

                # Lógica de Preenchimento (Forward Fill)
                # Estrutura padrão: Col 0 (Unidade) | Col 1 (Objeto) | Col 2 (Habilidade)
                # Em LP pode ser: Prática | Objeto | Habilidade
                
                # Se temos pelo menos 3 colunas (layout padrão)
                if len(cleaned_row) >= 3:
                    # Se a coluna 0 tem texto, atualiza a Unidade. Senão, mantém a anterior.
                    if cleaned_row[0]: state["unit"] = cleaned_row[0]
                    # Se a coluna 1 tem texto, atualiza o Objeto.
                    if cleaned_row[1]: state["object"] = cleaned_row[1]
                    
                    skill_text = cleaned_row[2] # A habilidade costuma estar na 3ª coluna
                    
                elif len(cleaned_row) == 2:
                    # Layout atípico (às vezes acontece em quebras de página ou LP)
                    # Assume-se que col 0 é objeto (se houver) e col 1 é habilidade
                    if cleaned_row[0]: state["object"] = cleaned_row[0]
                    skill_text = cleaned_row[1]
                else:
                    # Fallback: pega a última coluna não vazia como habilidade
                    skill_text = cleaned_row[-1]

                # Extrai habilidade(s)
                # Pode haver mais de um código na mesma célula? Geralmente não, mas o regex acha o primeiro.
                if "EF" in skill_text:
                    code, desc = extract_code_desc_regex(skill_text, RE_CODE_EF)
                    
                    if code:
                        # Extrai componente do código (ex: EF01MA01 -> MA)
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
    
    # Ensino Médio costuma ser lista corrida ou blocos, menos tabular que EF.
    # Vamos usar extração de texto com regex robusto e buffer para descrições multilinhas.
    
    current_area = "Geral"

    for page_num in EM_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text()
        if not text: continue
        
        # Tenta identificar a área pelo cabeçalho da página
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
                # Se já tínhamos um código sendo processado, salva ele antes de começar o novo
                if buffer_code:
                    data.append({
                        "code": buffer_code,
                        "description": " ".join(buffer_desc).strip(),
                        "area": current_area
                    })
                
                # Inicia novo item
                buffer_code = match.group(1)
                # Pega o resto da linha após o código como início da descrição
                start_desc = clean_line[match.end():].strip()
                start_desc = re.sub(r"^[\s\.\-]+", "", start_desc)
                buffer_desc = [start_desc] if start_desc else []
            
            elif buffer_code:
                # Continuação da descrição da habilidade anterior
                # Evita capturar rodapés (ex: números de página soltos)
                if len(clean_line) > 3 or not clean_line.isdigit():
                    buffer_desc.append(clean_line)

        # Salva o último item da página
        if buffer_code:
            data.append({
                "code": buffer_code,
                "description": " ".join(buffer_desc).strip(),
                "area": current_area
            })
            
    return data

# --- EXECUÇÃO ---

def main():
    print(f"Abrindo PDF: {PDF_PATH}")
    try:
        pdf = pdfplumber.open(PDF_PATH)
    except Exception as e:
        print(f"Erro crítico ao abrir PDF: {e}")
        return

    # Extração
    ei_data = extract_ei(pdf)
    ef_data = extract_ef(pdf)
    em_data = extract_em(pdf)
    
    pdf.close()

    # Deduplicação (simples, baseada no código)
    # Remove duplicatas que ocorrem se o PDF repete cabeçalhos ou quebra páginas mal
    ei_data = list({v['code']: v for v in ei_data}.values())
    ef_data = list({v['code']: v for v in ef_data}.values())
    em_data = list({v['code']: v for v in em_data}.values())

    # Salvamento (Override/Sobrescrita)
    print("\n--- Salvando Arquivos ---")
    save_json(ei_data, "bncc_ei.json")
    save_json(ef_data, "bncc_ef.json")
    save_json(em_data, "bncc_em.json")
    
    print("\nProcesso concluído.")

if __name__ == "__main__":
    main()