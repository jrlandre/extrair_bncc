import pdfplumber
import re
import json
import unicodedata

# --- CONFIGURATION ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"
EI_PAGE_RANGE = range(35, 57)   # Adjust based on actual PDF content
EF_PAGE_RANGE = range(57, 460)
EM_PAGE_RANGE = range(460, 600)

# --- UTILS ---
def clean_text(text):
    if not text: return ""
    # Normalize unicode characters to standard forms
    text = unicodedata.normalize("NFKC", text)
    # Remove excessive whitespace
    return re.sub(r'\s+', ' ', text).strip()

def extract_code_desc(text):
    """
    Extracts BNCC code and description from a string.
    Supports standard patterns like EF01MA01 and EM13LGG103.
    """
    # Pattern looks for 2 uppercase, digit(s), uppercase(s), digit(s)
    # Covers: EI01TS01, EF15LP10, EM13LGG103
    pattern = r"([A-Z]{2}\d{1,2}[A-Z]{2,3}\d{1,3})"
    
    match = re.search(pattern, text)
    if match:
        code = match.group(1)
        # Description is typically the text immediately following the code
        # We handle cases where code is embedded or at start
        desc = text[match.end():].strip()
        # Clean leading punctuation often found in PDF tables (e.g. "- Desc")
        desc = re.sub(r"^[\s\-\.–]+", "", desc)
        return code, desc
    return None, None

# --- EXTRACTORS ---

def extract_ei(pdf):
    """
    Extracts Educação Infantil.
    Strategy: Text-based parsing since structure is columnar lists, not strict tables.
    """
    data = []
    print("Processing Educação Infantil...")
    
    current_field = "Unknown"
    
    # Mapping codes to fields based on the BNCC specific letter codes
    field_map = {
        "EO": "O eu, o outro e o nós",
        "CG": "Corpo, gestos e movimentos",
        "TS": "Traços, sons, cores e formas",
        "EF": "Escuta, fala, pensamento e imaginação",
        "ET": "Espaços, tempos, quantidades, relações e transformações"
    }

    for page_num in EI_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text()
        
        if not text: continue
        
        lines = text.split('\n')
        for line in lines:
            line = clean_text(line)
            code, desc = extract_code_desc(line)
            
            if code and code.startswith("EI"):
                # Determine field from code structure (e.g. EI01TS01 -> TS)
                # Structure: EI (Stage) + 01 (Age) + TS (Field) + 01 (Num)
                field_code = code[4:6]
                field_name = field_map.get(field_code, "Campo Desconhecido")
                
                # Determine Age Group
                age_code = code[2:4]
                age_group = {
                    "01": "Bebês (zero a 1 ano e 6 meses)",
                    "02": "Crianças bem pequenas (1 ano e 7 meses a 3 anos e 11 meses)",
                    "03": "Crianças pequenas (4 anos a 5 anos e 11 meses)"
                }.get(age_code, "Grupo Desconhecido")

                data.append({
                    "code": code,
                    "description": desc,
                    "field": field_name,
                    "age_group": age_group
                })
    return data

def extract_ef(pdf):
    """
    Extracts Ensino Fundamental.
    Strategy: Stateful Table Parsing.
    Solves the "merged cell" issue by maintaining state of current Unit/Object.
    """
    data = []
    print("Processing Ensino Fundamental...")

    # State variables
    current_unit = None
    current_object = None
    
    # We define a custom table extraction setting for pdfplumber
    # 'lines' strategy is usually best for grid tables in BNCC
    table_settings = {
        "vertical_strategy": "lines", 
        "horizontal_strategy": "lines",
        "intersection_y_tolerance": 5,
    }

    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        
        tables = page.extract_tables(table_settings)
        
        for table in tables:
            for row in table:
                # BNCC EF tables usually have 3 visible columns:
                # 0: Unidade Temática | 1: Objeto de Conhecimento | 2: Habilidade
                # Sometimes column 0 or 1 is None/Empty due to merger.
                
                if not row: continue
                
                # Clean the row cells
                cleaned_row = [clean_text(cell) if cell else "" for cell in row]
                
                # Heuristic: Skip headers
                if "UNIDADES TEMÁTICAS" in str(cleaned_row) or "PRÁTICAS DE LINGUAGEM" in str(cleaned_row):
                    continue

                # --- STATE MANAGEMENT (The Fix) ---
                
                # 1. Update Unit
                # If col 0 has text, it's a new Unit. Update state.
                if len(cleaned_row) > 0 and cleaned_row[0]:
                    current_unit = cleaned_row[0]
                
                # 2. Update Object
                # If col 1 has text, it's a new Object. Update state.
                # Note: Sometimes a new Unit in col 0 implies a reset of Object if col 1 is empty?
                # Actually, usually if col 0 changes, col 1 MUST change or be explicitly merged.
                # If col 0 is filled and col 1 is empty, it might be a header-like row or continuation.
                # We assume if col 1 is filled, update object.
                if len(cleaned_row) > 1 and cleaned_row[1]:
                    current_object = cleaned_row[1]
                
                # 3. Extract Skill
                # The skill is usually in the last column.
                skill_text = cleaned_row[-1]
                
                # Check if this row actually contains a skill code
                if "EF" in skill_text:
                    code, desc = extract_code_desc(skill_text)
                    
                    if code and code.startswith("EF"):
                        # Parse Subject (Componente) from Code
                        # Structure: EF (Stage) + 15 (Year) + LP (Subject) + 01 (Num)
                        subject_code = code[4:6] if code[4:6].isalpha() else code[4:7] # Handle 2 or 3 letter codes? Usually 2 like LP, MA, CI
                        
                        # Fix for edge cases where regex catches wrong slice
                        if not subject_code.isalpha():
                             # Fallback logic if needed
                             pass
                             
                        data.append({
                            "code": code,
                            "description": desc,
                            "component": subject_code, # e.g., MA, LP, CI
                            "thematic_unit": current_unit,
                            "knowledge_object": current_object
                        })
    return data

def extract_em(pdf):
    """
    Extracts Ensino Médio.
    Strategy: Text block search using strict regex pattern for codes.
    Tables are less consistent here, often just lists of skills.
    """
    data = []
    print("Processing Ensino Médio...")
    
    # EM codes are distinctly EM + 2 digits + 3 letters + 3 digits (mostly)
    # e.g., EM13LGG103
    em_pattern = re.compile(r"(EM\d{2}[A-Z]{2,4}\d{1,3})")
    
    for page_num in EM_PAGE_RANGE:
        if page_num >= len(pdf.pages): break
        page = pdf.pages[page_num]
        text = page.extract_text()
        
        if not text: continue
        
        # We split by newlines to process item by item
        lines = text.split('\n')
        
        for line in lines:
            line = clean_text(line)
            match = em_pattern.search(line)
            
            if match:
                code = match.group(1)
                desc = line[match.end():].strip()
                desc = re.sub(r"^[\s\-\.–]+", "", desc)
                
                # If desc is empty, it might be on the next line (not handled in simple loop, 
                # but valid for 95% of BNCC layout where code+desc are on same line start)
                
                # Area can be derived from code: LGG, MAT, CNT, CHS
                area_code = re.search(r"([A-Z]{3})", code).group(1) if re.search(r"([A-Z]{3})", code) else "Unknown"

                data.append({
                    "code": code,
                    "description": desc,
                    "area": area_code
                })
    return data

# --- MAIN EXECUTION ---

def main():
    print(f"Opening PDF: {PDF_PATH}")
    try:
        pdf = pdfplumber.open(PDF_PATH)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return

    # Extract Data
    ei_data = extract_ei(pdf)
    ef_data = extract_ef(pdf)
    em_data = extract_em(pdf)
    
    pdf.close()

    # Deduplication (Essential as PDF extraction often reads headers/footers twice)
    # We use a dict keyed by 'code' to ensure uniqueness
    
    def dedupe(data_list):
        return list({v['code']: v for v in data_list}.values())

    ei_data = dedupe(ei_data)
    ef_data = dedupe(ef_data)
    em_data = dedupe(em_data)

    # Save Files
    print("Saving JSON files...")
    
    with open("bncc_ei.json", "w", encoding="utf-8") as f:
        json.dump(ei_data, f, ensure_ascii=False, indent=2)
        
    with open("bncc_ef.json", "w", encoding="utf-8") as f:
        json.dump(ef_data, f, ensure_ascii=False, indent=2)
        
    with open("bncc_em.json", "w", encoding="utf-8") as f:
        json.dump(em_data, f, ensure_ascii=False, indent=2)

    print("Success.")
    print(f"Stats: EI={len(ei_data)} | EF={len(ef_data)} | EM={len(em_data)}")

if __name__ == "__main__":
    main()