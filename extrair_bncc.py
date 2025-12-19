import pdfplumber
import re
import json
import unicodedata
import os

# --- CONFIGURAÇÃO ---
PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"
EI_PAGE_RANGE = range(35, 60)
EF_PAGE_RANGE = range(57, 465)  # Includes all EF content incl. Ensino Religioso 9º Ano (page 461)
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

# Mapeamento EM - Ensino Médio
MAPA_EM_AREAS = {
    "LGG": "Linguagens e suas Tecnologias",
    "LP": "Linguagens e suas Tecnologias",  # Componente LP
    "MAT": "Matemática e suas Tecnologias",
    "CNT": "Ciências da Natureza e suas Tecnologias",
    "CHS": "Ciências Humanas e Sociais Aplicadas"
}

# Páginas por área no EM
EM_AREA_PAGES = {
    "Linguagens e suas Tecnologias": (481, 530),
    "Matemática e suas Tecnologias": (531, 555),
    "Ciências da Natureza e suas Tecnologias": (555, 570),
    "Ciências Humanas e Sociais Aplicadas": (570, 600)
}

# --- FUNÇÕES PARA EXTRAÇÃO DE ITÁLICO ---

def build_formatted_text_from_chars(chars):
    """
    Reconstrói texto a partir de caracteres individuais, 
    adicionando marcadores Markdown *texto* para texto em itálico.
    """
    if not chars:
        return ""
    
    # Ordena caracteres por posição (top, left)
    sorted_chars = sorted(chars, key=lambda c: (c.get('top', 0), c.get('x0', 0)))
    
    result = []
    in_italic = False
    last_x1 = None
    last_top = None
    
    for c in sorted_chars:
        char_text = c.get('text', '')
        if not char_text:
            continue
            
        fontname = c.get('fontname', '')
        is_italic = 'Italic' in fontname or 'Oblique' in fontname
        
        # Detecta nova linha (diferença de top > threshold)
        current_top = c.get('top', 0)
        if last_top is not None and abs(current_top - last_top) > 8:
            if in_italic:
                result.append('*')
                in_italic = False
            result.append(' ')  # Substitui quebra de linha por espaço
        else:
            # Detecta espaço entre palavras
            current_x0 = c.get('x0', 0)
            if last_x1 is not None and current_x0 - last_x1 > 3:
                if in_italic and not is_italic:
                    result.append('*')
                    in_italic = False
                result.append(' ')
                if is_italic and not in_italic:
                    result.append('*')
                    in_italic = True
        
        # Gerencia transição de estilo
        if is_italic and not in_italic:
            result.append('*')
            in_italic = True
        elif not is_italic and in_italic:
            result.append('*')
            in_italic = False
        
        result.append(char_text)
        last_x1 = c.get('x1', 0)
        last_top = current_top
    
    # Fecha itálico pendente
    if in_italic:
        result.append('*')
    
    text = ''.join(result)
    # Limpa asteriscos vazios ou mal formados
    text = re.sub(r'\*\s*\*', '', text)  # Remove ** vazios
    text = re.sub(r'\s+', ' ', text).strip()  # Normaliza espaços
    return text


def get_page_italic_map(page):
    """
    Cria um mapa de regiões com texto em itálico para uma página.
    Retorna um dicionário de (approx_top, approx_left) -> texto_formatado
    """
    chars = page.chars
    if not chars:
        return {}
    
    # Agrupa caracteres por linha aproximada
    lines = {}
    for c in chars:
        top = round(c.get('top', 0) / 5) * 5  # Agrupa em faixas de 5px
        if top not in lines:
            lines[top] = []
        lines[top].append(c)
    
    # Reconstrói texto formatado por linha
    formatted_lines = {}
    for top, line_chars in lines.items():
        formatted_lines[top] = build_formatted_text_from_chars(line_chars)
    
    return formatted_lines


def extract_italic_words(page):
    """
    Extrai todas as palavras/frases em itálico de uma página.
    Retorna um set de strings que estão em itálico.
    """
    chars = page.chars
    if not chars:
        return set()
    
    italic_words = set()
    current_word = []
    in_italic = False
    
    sorted_chars = sorted(chars, key=lambda c: (c.get('top', 0), c.get('x0', 0)))
    last_x1 = None
    
    for c in sorted_chars:
        char_text = c.get('text', '')
        if not char_text:
            continue
            
        fontname = c.get('fontname', '')
        is_italic = 'Italic' in fontname or 'Oblique' in fontname
        current_x0 = c.get('x0', 0)
        
        # Detecta espaço entre palavras
        is_space = last_x1 is not None and current_x0 - last_x1 > 3
        
        if is_italic:
            if is_space and current_word:
                # Salva palavra anterior se também era itálica
                word = ''.join(current_word).strip()
                if len(word) > 2:
                    italic_words.add(word)
                current_word = []
            current_word.append(char_text)
        else:
            if current_word:
                word = ''.join(current_word).strip()
                if len(word) > 2:
                    italic_words.add(word)
                current_word = []
        
        last_x1 = c.get('x1', 0)
    
    # Última palavra
    if current_word:
        word = ''.join(current_word).strip()
        if len(word) > 2:
            italic_words.add(word)
    
    return italic_words


def apply_italic_formatting(text, italic_words):
    """
    Aplica formatação Markdown (*palavra*) para palavras em itálico.
    Usa word boundaries para evitar substituições parciais.
    """
    if not italic_words or not text:
        return text
    
    result = text
    # Ordena por tamanho decrescente para evitar substituições parciais
    for word in sorted(italic_words, key=len, reverse=True):
        if word in result and len(word) > 2:
            # Evita duplicar asteriscos se já formatado
            if f'*{word}*' not in result:
                # Usa word boundary (\b ou espaço/pontuação) para substituição precisa
                # Evita substituir "and" dentro de "explorando"
                result = re.sub(
                    r'(?<![a-zA-ZáéíóúàèìòùâêîôûãõäëïöüçñÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÄËÏÖÜÇÑ\*])' + 
                    re.escape(word) + 
                    r'(?![a-zA-ZáéíóúàèìòùâêîôûãõäëïöüçñÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÄËÏÖÜÇÑ\*])',
                    f'*{word}*',
                    result
                )
    
    return result


def parse_campo_name_description(raw_text):
    """
    Separa nome de Campo/Eixo da sua descrição e aplica formatação inteligente.
    
    Retorna:
        {
            "nome": "Campo das práticas de estudo e pesquisa",  # Title Case inteligente
            "descricao": "Trata-se de ampliar e qualificar..."  # Texto formatado
        }
    
    Regras de capitalização:
    - Palavras principais: capitalize
    - Preposições/artigos (de, da, do, das, dos, e, a, o, as, os, em, na, no, nas, nos): minúsculo
    - Exceção: primeira palavra sempre maiúscula
    - Hífens: preservar capitalização em cada parte
    """
    if not raw_text:
        return {"nome": "", "descricao": ""}
    
    # Só processa se for realmente um Campo/Eixo
    # Textos como "Oralidade *considerar..." não são campos
    upper_text = raw_text.upper()
    is_campo_or_eixo = (
        upper_text.startswith("CAMPO") or 
        upper_text.startswith("EIXO") or
        upper_text.startswith("TODOS") or  # "TODOS OS CAMPOS DE ATUAÇÃO"
        "CAMPO DE ATUAÇÃO" in upper_text or
        "CAMPOS DE ATUAÇÃO" in upper_text or  # plural
        "CAMPO DAS" in upper_text or
        "CAMPO DA" in upper_text
    )
    
    if not is_campo_or_eixo:
        # Retorna texto original sem parsing
        return {"nome": raw_text, "descricao": ""}
    
    # Caso simples: Campo sem descrição (ex: "TODOS OS CAMPOS DE ATUAÇÃO")
    # Verifica se tem separador de descrição
    has_separator = any(sep in raw_text for sep in [" – ", " - ", "Trata-se", "O que está"])
    if not has_separator:
        return {"nome": _smart_title_case(raw_text), "descricao": ""}
    
    # Identificadores de início de descrição
    separadores = [
        " – Trata-se",
        " – O que está",
        " – Este campo",
        " – Neste campo",
        " – Campo de",
        " – Práticas de",
        " – ",  # Fallback genérico
    ]
    
    nome_raw = raw_text
    descricao = ""
    
    # Tenta encontrar o separador
    for sep in separadores:
        if sep in raw_text:
            parts = raw_text.split(sep, 1)
            nome_raw = parts[0].strip()
            if len(parts) > 1:
                # Reconstrói o início da descrição
                if sep != " – ":
                    # Recoloca o início que foi perdido no split
                    inicio = sep.replace(" – ", "").strip()
                    descricao = inicio + parts[1]
                else:
                    descricao = parts[1].strip()
            break
    
    # Aplica Title Case inteligente ao nome
    nome_formatado = _smart_title_case(nome_raw)
    
    # Formata a descrição com quebras de linha inteligentes
    descricao_formatada = _format_campo_description(descricao) if descricao else ""
    
    return {
        "nome": nome_formatado,
        "descricao": descricao_formatada
    }


def _smart_title_case(text):
    """
    Aplica Title Case inteligente, mantendo preposições e artigos em minúsculo.
    """
    if not text:
        return ""
    
    # Palavras que devem permanecer minúsculas (exceto no início)
    lowercase_words = {
        'de', 'da', 'do', 'das', 'dos',
        'a', 'à', 'o', 'as', 'os',
        'e', 'em', 'na', 'no', 'nas', 'nos',
        'por', 'para', 'com', 'sem',
        'que', 'ao', 'aos', 'pela', 'pelo', 'pelas', 'pelos'
    }
    
    # Palavras que devem manter capitalização especial
    special_words = {
        'LP': 'LP', 'EF': 'EF', 'EI': 'EI', 'EM': 'EM',
        'TV': 'TV', 'DVD': 'DVD', 'CD': 'CD'
    }
    
    # Limpa e normaliza
    text = text.strip()
    
    # Trata texto todo em maiúsculas
    if text.isupper():
        text = text.lower()
    
    words = text.split()
    result = []
    
    for i, word in enumerate(words):
        # Trata palavras com hífen
        if '-' in word:
            parts = word.split('-')
            formatted_parts = []
            for j, part in enumerate(parts):
                if part.upper() in special_words:
                    formatted_parts.append(special_words[part.upper()])
                elif part.lower() in lowercase_words and j > 0:
                    formatted_parts.append(part.lower())
                else:
                    formatted_parts.append(part.capitalize())
            result.append('-'.join(formatted_parts))
        elif word.upper() in special_words:
            result.append(special_words[word.upper()])
        elif i == 0:
            # Primeira palavra sempre capitalizada
            result.append(word.capitalize())
        elif word.lower() in lowercase_words:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    
    return ' '.join(result)


def _format_campo_description(text):
    """
    Formata descrição de campo com quebras de linha inteligentes.
    
    - Preserva listas com "-" ou "•"
    - Adiciona quebras antes de marcadores
    - Normaliza espaçamento
    """
    if not text:
        return ""
    
    # Normaliza espaços
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Adiciona quebra antes de marcadores de lista
    text = re.sub(r'\s*[-–•]\s+', '\n- ', text)
    
    # Adiciona quebra antes de frases que começam novo parágrafo
    paragraph_starters = [
        'Trata-se também',
        'Para além',
        'Essas habilidades',
        'Considerando',
        'Além disso',
        'É importante',
        'Nesse sentido',
        'Dessa forma',
    ]
    
    for starter in paragraph_starters:
        text = text.replace(f' {starter}', f'\n\n{starter}')
    
    # Remove quebras duplicadas
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Garante que começa sem quebra
    text = text.strip()
    
    return text

# --- UTILITÁRIOS ---

def clean_text_basic(text):
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    # CRÍTICO: Preserva newlines mas normaliza espaços dentro de cada linha
    lines = text.split('\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    return '\n'.join(line for line in lines if line)

def clean_item_sintese(text):
    if not text: return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"^[\s•\-]+", "", text)
    # CRÍTICO: Preserva newlines mas normaliza espaços dentro de cada linha
    lines = text.split('\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    text = '\n'.join(lines)
    return format_special_chars(text)

def format_special_chars(text):
    """
    Formata caracteres especiais para preservar notação matemática e ordinais.
    Exemplos: "2o grau" → "2º grau", "ax2" → "ax²", "3o ano" → "3º ano"
    """
    if not text: return ""
    
    # Ordinais: 1o, 2o, 3o, etc. → 1º, 2º, 3º
    text = re.sub(r'(\d+)o\b', r'\1º', text)
    text = re.sub(r'(\d+)a\b', r'\1ª', text)
    
    # Superscripts matemáticos comuns
    superscript_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        'n': 'ⁿ', 'x': 'ˣ', 'y': 'ʸ'
    }
    
    # Padrões específicos de notação matemática
    # ax2 → ax², x2 → x², y3 → y³, etc.
    for base in ['x', 'y', 'z', 'a', 'b', 'c', 'n', 'm']:
        for exp in ['2', '3', '4', '5', '6', '7', '8', '9']:
            pattern = f'{base}{exp}'
            replacement = f'{base}{superscript_map[exp]}'
            # Apenas substitui se seguido de espaço, =, +, -, ou fim de string
            text = re.sub(f'{pattern}(?=[\s=+\-)]|$)', replacement, text)
    
    return text

def processar_descricao(texto_bruto, codigo, italic_words=None):
    if codigo: texto = texto_bruto.replace(codigo, "")
    else: texto = texto_bruto
    # Remove newlines e normaliza espaços
    texto = texto.replace('\n', ' ')
    texto = re.sub(r'\s+', ' ', texto)  # Normaliza múltiplos espaços
    texto = re.sub(r"^[\s\(\)\.\-]+", "", texto).strip()
    texto = format_special_chars(texto)
    # Aplica formatação itálico se disponível
    if italic_words:
        texto = apply_italic_formatting(texto, italic_words)
    return texto

def expandir_anos_ef(codigo_bncc):
    """
    Expande códigos de faixa (ex: EF15) para lista de anos individuais.
    Garante 'perfect info' replicando o item para cada ano.
    """
    match = re.search(r"EF(\d{2,3})", codigo_bncc)
    if not match: return ["Ano Indefinido"]
    digits = match.group(1)
    
    anos = []
    
    # Anos individuais de 2 dígitos (01 a 09)
    if len(digits) == 2:
        val = int(digits)
        if 1 <= val <= 9:
            anos = [val]
        # Faixas comuns com 2 dígitos
        elif digits == "12": anos = [1, 2]
        elif digits == "15": anos = [1, 2, 3, 4, 5]
        elif digits == "35": anos = [3, 4, 5]
        elif digits == "67": anos = [6, 7]
        elif digits == "69": anos = [6, 7, 8, 9]
        elif digits == "89": anos = [8, 9]
    
    # Anos individuais de 3 dígitos (ex: EF601, EF602...)
    elif len(digits) == 3:
        # Extract first digit as year
        val = int(digits[0])
        if 1 <= val <= 9:
            anos = [val]
    
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
                        # Remove newlines para comparação com nomes de campos
                        col_campo_normalized = col_campo_clean.replace('\n', ' ').upper()
                        for sigla, nome in CAMPOS_EXPERIENCIA.items():
                            if nome.upper() in col_campo_normalized: ultimo_campo_sintese = sigla; break
                        col_texto_raw = row[1] if row[1] else ""
                        if ultimo_campo_sintese and col_texto_raw:
                            novos = separar_itens_sintese(col_texto_raw)
                            output["sintese_aprendizagens"][ultimo_campo_sintese].extend(novos)
    return output

def extract_competencias_ef(pdf, page_range):
    """
    Retorna as competências específicas (Área e Componente) do Ensino Fundamental.
    
 NOTA: As páginas de competências no PDF (67, 89-90, etc.) são imagens não-extraíveis programaticamente.
    Por isso, este mapeamento usa o texto oficial da BNCC disponível na documentação pública.
    Fonte: http://basenacionalcomum.mec.gov.br/
    """
    print("--- Extraindo Competências (Área e Componente) ---")
    
    competencias = {
        # Competências Específicas da Área de Linguagens para o Ensino Fundamental
        "Linguagens": [
            "1. Compreender as linguagens como construção humana, histórica, social e cultural, de natureza dinâmica, reconhecendo-as e valorizando-as como formas de significação da realidade e expressão de subjetividades e identidades sociais e culturais.",
            "2. Conhecer e explorar diversas práticas de linguagem (artísticas, corporais e linguísticas) em diferentes campos da atividade humana para continuar aprendendo, ampliar suas possibilidades de participação na vida social e colaborar para a construção de uma sociedade mais justa, democrática e inclusiva.",
            "3. Utilizar diferentes linguagens – verbal (oral ou visual-motora, como Libras, e escrita), corporal, visual, sonora e digital –, para se expressar e partilhar informações, experiências, ideias e sentimentos em diferentes contextos e produzir sentidos que levem ao diálogo, à resolução de conflitos e à cooperação.",
            "4. Utilizar diferentes linguagens para defender pontos de vista que respeitem o outro e promovam os direitos humanos, a consciência socioambiental e o consumo responsável em âmbito local, regional e global, atuando criticamente frente a questões do mundo contemporâneo.",
            "5. Desenvolver o senso estético para reconhecer, fruir e respeitar as diversas manifestações artísticas e culturais, das locais às mundiais, inclusive aquelas pertencentes ao patrimônio cultural da humanidade, bem como participar de práticas diversificadas, individuais e coletivas, da produção artístico-cultural, com respeito à diversidade de saberes, identidades e culturas.",
            "6. Compreender e utilizar tecnologias digitais de informação e comunicação de forma crítica, significativa, reflexiva e ética nas diversas práticas sociais (incluindo as escolares), para se comunicar por meio das diferentes linguagens e mídias, produzir conhecimentos, resolver problemas e desenvolver projetos autorais e coletivos."
        ],
        
        # Competências Específicas de Língua Portuguesa para o Ensino Fundamental
        "Língua Portuguesa": [
            "1. Compreender a língua como fenômeno cultural, histórico, social, variável, heterogêneo e sensível aos contextos de uso, reconhecendo-a como meio de construção de identidades de seus usuários e da comunidade a que pertencem.",
            "2. Apropriar-se da linguagem escrita, reconhecendo-a como forma de interação nos diferentes campos de atuação da vida social e utilizando-a para ampliar suas possibilidades de participar da cultura letrada, de construir conhecimentos (inclusive escolares) e de se envolver com maior autonomia e protagonismo na vida social.",
            "3. Ler, escutar e produzir textos orais, escritos e multissemióticos que circulam em diferentes campos de atuação e mídias, com compreensão, autonomia, fluência e criticidade, de modo a se expressar e partilhar informações, experiências, ideias e sentimentos, e continuar aprendendo.",
            "4. Compreender o fenômeno da variação linguística, demonstrando atitude respeitosa diante de variedades linguísticas e rejeitando preconceitos linguísticos.",
            "5. Empregar, nas interações sociais, a variedade e o estilo de linguagem adequados à situação comunicativa, ao(s) interlocutor(es) e ao gênero do discurso/gênero textual.",
            "6. Analisar informações, argumentos e opiniões manifestados em interações sociais e nos meios de comunicação, posicionando-se ética e criticamente em relação a conteúdos discriminatórios que ferem direitos humanos e ambientais.",
            "7. Reconhecer o texto como lugar de manifestação e negociação de sentidos, valores e ideologias.",
            "8. Selecionar textos e livros para leitura integral, de acordo com objetivos, interesses e projetos pessoais (estudo, formação pessoal, entretenimento, pesquisa, trabalho etc.).",
            "9. Envolver-se em práticas de leitura literária que possibilitem o desenvolvimento do senso estético para fruição, valorizando a literatura e outras manifestações artístico-culturais como formas de acesso às dimensões lúdicas, de imaginário e encantamento, reconhecendo o potencial transformador e humanizador da experiência com a literatura.",
            "10. Mobilizar práticas da cultura digital, diferentes linguagens, mídias e ferramentas digitais para expandir as formas de produzir sentidos (nos processos de compreensão e produção), aprender e refletir sobre o mundo e realizar diferentes projetos autorais."
        ],
        
        # Competências Específicas de Arte para o Ensino Fundamental
        "Arte": [
            "1. Explorar, conhecer, fruir e analisar criticamente práticas e produções artísticas e culturais do seu entorno social, dos povos indígenas, das comunidades tradicionais brasileiras e de diversas sociedades, em distintos tempos e espaços, para reconhecer a arte como um fenômeno cultural, histórico, social e sensível a diferentes contextos e dialogar com as diversidades.",
            "2. Compreender as relações entre as linguagens da Arte e suas práticas integradas, inclusive aquelas possibilitadas pelo uso das novas tecnologias de informação e comunicação, pelo cinema e pelo audiovisual, nas condições particulares de produção, na prática de cada linguagem e nas suas articulações.",
            "3. Pesquisar e conhecer distintas matrizes estéticas e culturais – especialmente aquelas manifestas na arte e nas culturas que constituem a identidade brasileira –, sua tradição e manifestações contemporâneas, reelaborando-as nas criações em Arte.",
            "4. Experienciar a ludicidade, a percepção, a expressividade e a imaginação, ressignificando espaços da escola e de fora dela no âmbito da Arte.",
            "5. Mobilizar recursos tecnológicos como formas de registro, pesquisa e criação artística.",
            "6. Estabelecer relações entre arte, mídia, mercado e consumo, compreendendo, de forma crítica e problematizadora, modos de produção e de circulação da arte na sociedade.",
            "7. Problematizar questões políticas, sociais, econômicas, científicas, tecnológicas e culturais, por meio de exercícios, produções, intervenções e apresentações artísticas.",
            "8. Desenvolver a autonomia, a crítica, a autoria e o trabalho coletivo e colaborativo nas artes.",
            "9. Analisar e valorizar o patrimônio artístico nacional e internacional, material e imaterial, com suas histórias e diferentes visões de mundo."
        ],
        
        # Competências Específicas de Educação Física para o Ensino Fundamental
        "Educação Física": [
            "1. Compreender a origem da cultura corporal de movimento e seus vínculos com a organização da vida coletiva e individual.",
            "2. Planejar e empregar estratégias para resolver desafios e aumentar as possibilidades de aprendizagem das práticas corporais, além de se envolver no processo de ampliação do acervo cultural nesse campo.",
            "3. Refletir, criticamente, sobre as relações entre a realização das práticas corporais e os processos de saúde/doença, inclusive no contexto das atividades laborais.",
            "4. Identificar a multiplicidade de padrões de desempenho, saúde, beleza e estética corporal, analisando, criticamente, os modelos disseminados na mídia e discutir posturas consumistas e preconceituosas.",
            "5. Identificar as formas de produção dos preconceitos, compreender seus efeitos e combater posicionamentos discriminatórios em relação às práticas corporais e aos seus participantes.",
            "6. Interpretar e recriar os valores, os sentidos e os significados atribuídos às diferentes práticas corporais, bem como aos sujeitos que delas participam.",
            "7. Reconhecer as práticas corporais como elementos constitutivos da identidade cultural dos povos e grupos.",
            "8. Usufruir das práticas corporais de forma autônoma para potencializar o envolvimento em contextos de lazer, ampliar as redes de sociabilidade e a promoção da saúde.",
            "9. Reconhecer o acesso às práticas corporais como direito do cidadão, propondo e produzindo alternativas para sua realização no contexto comunitário.",
            "10. Experimentar, desfrutar, apreciar e criar diferentes brincadeiras, jogos, danças, ginásticas, esportes, lutas e práticas corporais de aventura, valorizando o trabalho coletivo e o protagonismo."
        ],
        
        # Competências Específicas de Língua Inglesa para o Ensino Fundamental (página 246 - imagem)
        "Língua Inglesa": [
            "1. Identificar o lugar de si e o do outro em um mundo plurilíngue e multicultural, refletindo, criticamente, sobre como a aprendizagem da língua inglesa contribui para a inserção dos sujeitos no mundo globalizado, inclusive no que concerne ao mundo do trabalho.",
            "2. Comunicar-se na língua inglesa, por meio do uso variado de linguagens em mídias impressas ou digitais, reconhecendo-a como ferramenta de acesso ao conhecimento, de ampliação das perspectivas e de possibilidades para a compreensão dos valores e interesses de outras culturas e para o exercício do protagonismo social.",
            "3. Identificar similaridades e diferenças entre a língua inglesa e a língua materna/outras línguas, articulando-as a aspectos sociais, culturais e identitários, em uma relação intrínseca entre língua, cultura e identidade.",
            "4. Elaborar repertórios linguístico-discursivos da língua inglesa, usados em diferentes países e por grupos sociais distintos dentro de um mesmo país, de modo a reconhecer a diversidade linguística como direito e valorizar os usos heterogêneos, híbridos e multimodais emergentes nas sociedades contemporâneas.",
            "5. Utilizar novas tecnologias, com novas linguagens e modos de interação, para pesquisar, selecionar, compartilhar, posicionar-se e produzir sentidos em práticas de letramento na língua inglesa, de forma ética, crítica e responsável.",
            "6. Conhecer diferentes patrimônios culturais, materiais e imateriais, difundidos na língua inglesa, com vistas ao exercício da fruição e da ampliação de perspectivas no contato com diferentes manifestações artístico-culturais."
        ],
        
        # Competências Específicas da Área de Matemática para o Ensino Fundamental
        "Matemática": [
            "1. Reconhecer que a Matemática é uma ciência humana, fruto das necessidades e preocupações de diferentes culturas, em diferentes momentos históricos, e é uma ciência viva, que contribui para solucionar problemas científicos e tecnológicos e para alicerçar descobertas e construções, inclusive com impactos no mundo do trabalho.",
            "2. Desenvolver o raciocínio lógico, o espírito de investigação e a capacidade de produzir argumentos convincentes, recorrendo aos conhecimentos matemáticos para compreender e atuar no mundo.",
            "3. Compreender as relações entre conceitos e procedimentos dos diferentes campos da Matemática (Aritmética, Álgebra, Geometria, Estatística e Probabilidade) e de outras áreas do conhecimento, sentindo segurança quanto à própria capacidade de construir e aplicar conhecimentos matemáticos.",
            "4. Fazer observações sistemáticas de aspectos quantitativos e qualitativos presentes nas práticas sociais e culturais, de modo a investigar, organizar, representar e comunicar informações relevantes, para interpretá-las e avaliá-las crítica e eticamente, produzindo argumentos convincentes.",
            "5. Utilizar processos e ferramentas matemáticas, inclusive tecnologias digitais disponíveis, para modelar e resolver problemas cotidianos, sociais e de outras áreas de conhecimento, validando estratégias e resultados.",
            "6. Enfrentar situações-problema em múltiplos contextos, incluindo-se situações imaginadas, não diretamente relacionadas com o aspecto prático-utilitário, expressar suas respostas e sintetizar conclusões, utilizando diferentes registros e linguagens (gráficos, tabelas, esquemas, além de texto escrito na língua materna e outras linguagens para descrever algoritmos, como fluxogramas, e dados).",
            "7. Desenvolver e/ou discutir projetos que abordem, sobretudo, questões de urgência social, com base em princípios éticos, democráticos, sustentáveis e solidários, valorizando a diversidade de opiniões de indivíduos e de grupos sociais, sem preconceitos de qualquer natureza.",
            "8. Interagir com seus pares de forma cooperativa, trabalhando coletivamente no planejamento e desenvolvimento de pesquisas para responder a questionamentos e na busca de soluções para problemas, de modo a identificar aspectos consensuais ou não na discussão de uma determinada questão, respeitando o modo de pensar dos colegas e aprendendo com eles."
        ],
        
        # Competências Específicas da Área de Ciências da Natureza para o Ensino Fundamental
        "Ciências da Natureza": [
            "1. Compreender as Ciências da Natureza como empreendimento humano, e o conhecimento científico como provisório, cultural e histórico.",
            "2. Compreender conceitos fundamentais e estruturas explicativas das Ciências da Natureza, bem como dominar processos, práticas e procedimentos da investigação científica, de modo a sentir segurança no debate de questões científicas, tecnológicas, socioambientais e do mundo do trabalho, continuar aprendendo e colaborar para a construção de uma sociedade justa, democrática e inclusiva.",
            "3. Analisar, compreender e explicar características, fenômenos e processos relativos ao mundo natural, social e tecnológico (incluindo o digital), como também as relações que se estabelecem entre eles, exercitando a curiosidade para fazer perguntas, buscar respostas e criar soluções (inclusive tecnológicas) com base nos conhecimentos das Ciências da Natureza.",
            "4. Avaliar aplicações e implicações políticas, socioambientais e culturais da ciência e de suas tecnologias para propor alternativas aos desafios do mundo contemporâneo, incluindo aqueles relativos ao mundo do trabalho.",
            "5. Construir argumentos com base em dados, evidências e informações confiáveis e negociar e defender ideias e pontos de vista que promovam a consciência socioambiental e o respeito a si próprio e ao outro, acolhendo e valorizando a diversidade de indivíduos e de grupos sociais, sem preconceitos de qualquer natureza.",
            "6. Utilizar diferentes linguagens e tecnologias digitais de informação e comunicação para se comunicar, acessar e disseminar informações, produzir conhecimentos e resolver problemas das Ciências da Natureza de forma crítica, significativa, reflexiva e ética.",
            "7. Conhecer, apreciar e cuidar de si, do seu corpo e bem-estar, compreendendo-se na diversidade humana, fazendo-se respeitar e respeitando o outro, recorrendo aos conhecimentos das Ciências da Natureza e às suas tecnologias.",
            "8. Agir pessoal e coletivamente com respeito, autonomia, responsabilidade, flexibilidade, resiliência e determinação, recorrendo aos conhecimentos das Ciências da Natureza para tomar decisões frente a questões científico-tecnológicas e socioambientais e a respeito da saúde individual e coletiva, com base em princípios éticos, democráticos, sustentáveis e solidários."
        ],
        
        # Competências Específicas da Área de Ciências Humanas para o Ensino Fundamental
        "Ciências Humanas": [
            "1. Compreender a si e ao outro como identidades diferentes, de forma a exercitar o respeito à diferença em uma sociedade plural e promover os direitos humanos.",
            "2. Analisar o mundo social, cultural e digital e o meio técnico-científico-informacional com base nos conhecimentos das Ciências Humanas, considerando suas variações de significado no tempo e no espaço, para intervir em situações do cotidiano e se posicionar diante de problemas do mundo contemporâneo.",
            "3. Identificar, comparar e explicar a intervenção do ser humano na natureza e na sociedade, exercitando a curiosidade e propondo ideias e ações que contribuam para a transformação espacial, social e cultural, de modo a participar efetivamente das dinâmicas da vida social.",
            "4. Interpretar e expressar sentimentos, crenças e dúvidas com relação a si mesmo, aos outros e às diferentes culturas, com base nos instrumentos de investigação das Ciências Humanas, promovendo o acolhimento e a valorização da diversidade de indivíduos e de grupos sociais, seus saberes, identidades, culturas e potencialidades, sem preconceitos de qualquer natureza.",
            "5. Comparar eventos ocorridos simultaneamente no mesmo espaço e em espaços variados, e eventos ocorridos em tempos diferentes no mesmo espaço e em espaços variados.",
            "6. Construir argumentos, com base nos conhecimentos das Ciências Humanas, para negociar e defender ideias e opiniões que respeitem e promovam os direitos humanos e a consciência socioambiental, exercitando a responsabilidade e o protagonismo voltados para o bem comum e a construção de uma sociedade justa, democrática e inclusiva.",
            "7. Utilizar as linguagens cartográfica, gráfica e iconográfica e diferentes gêneros textuais e tecnologias digitais de informação e comunicação no desenvolvimento do raciocínio espaço-temporal relacionado a localização, distância, direção, duração, simultaneidade, sucessão, ritmo e conexão."
        ],
        
        # Competências Específicas de Geografia para o Ensino Fundamental
        "Geografia": [
            "1. Utilizar os conhecimentos geográficos para entender a interação sociedade/natureza e exercitar o interesse e o espírito de investigação e de resolução de problemas.",
            "2. Estabelecer conexões entre diferentes temas do conhecimento geográfico, reconhecendo a importância dos objetos técnicos para a compreensão das formas como os seres humanos fazem uso dos recursos da natureza ao longo da história.",
            "3. Desenvolver autonomia e senso crítico para compreensão e aplicação do raciocínio geográfico na análise da ocupação humana e produção do espaço, envolvendo os princípios de analogia, conexão, diferenciação, distribuição, extensão, localização e ordem.",
            "4. Desenvolver o pensamento espacial, fazendo uso das linguagens cartográficas e iconográficas, de diferentes gêneros textuais e das geotecnologias para a resolução de problemas que envolvam informações geográficas.",
            "5. Desenvolver e utilizar processos, práticas e procedimentos de investigação para compreender o mundo natural, social, econômico, político e o meio técnico-científico e informacional, avaliar ações e propor perguntas e soluções (inclusive tecnológicas) para questões que requerem conhecimentos científicos da Geografia.",
            "6. Construir argumentos com base em informações geográficas, debater e defender ideias e pontos de vista que respeitem e promovam a consciência socioambiental e o respeito à biodiversidade e ao outro, sem preconceitos de qualquer natureza.",
            "7. Agir pessoal e coletivamente com respeito, autonomia, responsabilidade, flexibilidade, resiliência e determinação, propondo ações sobre as questões socioambientais, com base em princípios éticos, democráticos, sustentáveis e solidários."
        ],
        
        # Competências Específicas de História para o Ensino Fundamental
        "História": [
            "1. Compreender acontecimentos históricos, relações de poder e processos e mecanismos de transformação e manutenção das estruturas sociais, políticas, econômicas e culturais ao longo do tempo e em diferentes espaços para analisar, posicionar-se e intervir no mundo contemporâneo.",
            "2. Compreender a historicidade no tempo e no espaço, relacionando acontecimentos e processos de transformação e manutenção das estruturas sociais, políticas, econômicas e culturais, bem como problematizar os significados das lógicas de organização cronológica.",
            "3. Elaborar questionamentos, hipóteses, argumentos e proposições em relação a documentos, interpretações e contextos históricos específicos, recorrendo a diferentes linguagens e mídias, exercitando a empatia, o diálogo, a resolução de conflitos, a cooperação e o respeito.",
            "4. Identificar interpretações que expressem visões de diferentes sujeitos, culturas e povos com relação a um mesmo contexto histórico, e posicionar-se criticamente com base em princípios éticos, democráticos, inclusivos, sustentáveis e solidários.",
            "5. Analisar e compreender o movimento de populações e mercadorias no tempo e no espaço e seus significados históricos, levando em conta o respeito e a solidariedade com as diferentes populações.",
            "6. Compreender e problematizar os conceitos e procedimentos norteadores da produção historiográfica.",
            "7. Produzir, avaliar e utilizar tecnologias digitais de informação e comunicação de modo crítico, ético e responsável, compreendendo seus significados para os diferentes grupos ou estratos sociais."
        ],
        
        # Competências Específicas da Área de Ensino Religioso para o Ensino Fundamental
        "Ensino Religioso": [
            "1. Conhecer os aspectos estruturantes das diferentes tradições/movimentos religiosos e filosofias de vida, a partir de pressupostos científicos, filosóficos, estéticos e éticos.",
            "2. Compreender, valorizar e respeitar as manifestações religiosas e filosofias de vida, suas experiências e saberes, em diferentes tempos, espaços e territórios.",
            "3. Reconhecer e cuidar de si, do outro, da coletividade e da natureza, enquanto expressão de valor da vida.",
            "4. Conviver com a diversidade de crenças, pensamentos, convicções, modos de ser e viver.",
            "5. Analisar as relações entre as tradições religiosas e os campos da cultura, da política, da economia, da saúde, da ciência, da tecnologia e do meio ambiente.",
            "6. Debater, problematizar e posicionar-se frente aos discursos e práticas de intolerância, discriminação e violência de cunho religioso, de modo a assegurar os direitos humanos no constante exercício da cidadania e da cultura de paz."
        ]
    }
    
    return competencias

def extract_ef_final(pdf):
    """
    Extrai Ensino Fundamental com contexto correto de Unidade Temática e Objetos de Conhecimento.
    
    Estratégia: O PDF alterna entre tabelas de "contexto" (Unidades/Objetos) e tabelas de "habilidades".
    Precisamos armazenar o contexto da tabela anterior para aplicar às habilidades.
    """
    print("--- Processando Ensino Fundamental (Estrutura Completa) ---")
    
    # 1. Extração Prévia de Competências
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
            # Obtém competências do componente
            comp_competencias = competencias_map.get(comp, [])
            area_competencias = tree[area]["competencias_especificas_area"]
            
            # Verifica se são as mesmas (redundância) ou se componente está vazio
            if comp_competencias == area_competencias and len(comp_competencias) > 0:
                # Redundância: mesmas competências → usar referência
                tree[area]["componentes"][comp] = {
                    "competencias_especificas_componente": comp_competencias,
                    "competencias_especificas_ref": "area",  # Indica que são as mesmas da área
                    "anos": {}
                }
            elif len(comp_competencias) == 0 and len(area_competencias) > 0:
                # Componente sem competências próprias → herda da área
                tree[area]["componentes"][comp] = {
                    "competencias_especificas_componente": area_competencias,
                    "competencias_especificas_ref": "area",
                    "anos": {}
                }
            else:
                # Competências diferentes (normal)
                tree[area]["componentes"][comp] = {
                    "competencias_especificas_componente": comp_competencias,
                    "anos": {}
                }


    # ========================================================================
    # CONTEXTO GLOBAL - Variáveis de estado entre páginas/tabelas
    # ========================================================================
    current_comp = None
    current_area = None
    
    # Contexto de Campo/Unidade/Objeto (persistem entre tabelas da mesma página)
    context_unidades = []  # Lista de (campo, unidade, objeto)
    last_campo = ""  # Campo de Atuação (LP)
    last_unidade = ""
    last_objeto = ""
    
    # Dicionário para acumular continuações de descrições de campos
    # (aplicado ao campos_metadata no final do processamento)
    campo_desc_extra = {}  # {campo_nome_parseado: [lista de continuações]}
    
    # ========================================================================
    # FUNÇÕES AUXILIARES
    # ========================================================================
    def is_valid_label(text):
        """Valida se o texto é um label válido de Unidade/Objeto."""
        if not text or len(text) < 3: return False
        if len(text) > 300: return False
        if RE_CODE_EF.search(text): return False
        upper = text.upper().strip()
        headers = ['HABILIDADES', 'UNIDADE TEMÁTICA', 'UNIDADES TEMÁTICAS', 
                   'OBJETOS DE CONHECIMENTO', 'OBJETO DE CONHECIMENTO',
                   'PRÁTICAS DE LINGUAGEM', 'CAMPO DE ATUAÇÃO']
        if upper in headers: return False
        if text.isupper() and ' ' not in text and len(text) < 15: return False
        return True
    
    def is_context_table(header_str):
        """Detecta se é uma tabela de contexto (Unidades/Objetos, sem habilidades)."""
        has_unidade = "UNIDADE" in header_str or "CAMPO" in header_str or "PRÁTICA" in header_str
        has_objeto = "OBJETO" in header_str or "CONHECIMENTO" in header_str
        no_habilidade = "HABILIDADES" not in header_str
        return (has_unidade or has_objeto) and no_habilidade
    
    def is_skills_table(header_str, table):
        """Detecta se é uma tabela de habilidades."""
        if "HABILIDADES" in header_str:
            return True
        # Também verifica se a tabela contém códigos de habilidade
        for row in table[:5]:
            for cell in row:
                if cell and RE_CODE_EF.search(str(cell)):
                    return True
        return False
    
    def extract_context_from_table(table, num_cols):
        """
        Extrai contexto (Unidade, Objeto) de uma tabela, um par por linha.
        Para LP: detecta estrutura hierárquica Campo → Prática → Objeto.
        Retorna lista de tuplas (unidade, objeto) para correspondência com linhas de habilidade.
        """
        result = []
        last_campo = ""  # Campo de Atuação (LP)
        last_pratica = ""  # Prática de Linguagem (LP)
        last_unidade = ""  # Unidade Temática (outros componentes)
        
        for row in table[1:]:  # Skip header
            if not row or not any(c for c in row if c):
                continue
            
            # Primeira coluna: pode ser Campo, Prática, ou Unidade Temática
            col0 = clean_text_basic(row[0]) if len(row) > 0 and row[0] else ""
            # Segunda coluna: Objetos de Conhecimento
            col1 = clean_text_basic(row[1]) if len(row) > 1 and row[1] else ""
            # Terceira coluna (às vezes vazia)
            col2 = clean_text_basic(row[2]) if len(row) > 2 and row[2] else ""
            
            # Detecta se col0 é um Campo de Atuação (LP) ou Eixo (Inglês)
            # LP: "CAMPO DA VIDA COTIDIANA – ...", "TODOS OS CAMPOS DE ATUAÇÃO"
            # Inglês: "EIXO ORALIDADE – Práticas de...", "EIXO ESCRITA – ..."
            # EXCLUI: notas com asterisco (ex: "Oralidade *Considerar...")
            is_nota = "*" in col0 and col0.index("*") < 50  # Asterisco no início = nota
            is_campo = (
                not is_nota and
                ("CAMPO" in col0.upper() or "EIXO" in col0.upper()) and 
                ("–" in col0 or ":" in col0 or "TODOS" in col0.upper() or len(col0) > 40)
            )
            
            # Detecta se col0 é uma Prática de Linguagem (LP)
            is_pratica = not is_campo and not is_nota and is_valid_label(col0) and any(p in col0 for p in [
                "Leitura", "Escrita", "Oralidade", "Análise", "Produção"
            ])
            
            # Função para limpar newlines das unidades
            def clean_label(s):
                return re.sub(r'\s+', ' ', s.replace('\n', ' ')).strip()
            
            # Atualiza contexto hierárquico
            if is_campo:
                last_campo = clean_label(col0)
                last_pratica = ""  # Reset prática quando muda campo
            elif is_pratica:
                # Separa nome da prática de observações (ex: "Oralidade *Considerar...")
                pratica_text = clean_label(col0)
                if "*" in pratica_text:
                    parts = pratica_text.split("*", 1)
                    pratica_nome = parts[0].strip()
                    pratica_nota = "*" + parts[1].strip() if len(parts) > 1 else ""
                    # Armazena nota de prática em metadata (se disponível)
                    # Nota: praticas_metadata seria criado no add_skill_to_tree
                else:
                    pratica_nome = pratica_text
                last_pratica = pratica_nome
            elif is_valid_label(col0):
                # Outros componentes: col0 é Unidade Temática
                last_unidade = clean_label(col0)
            
            # Determina Objeto (pode estar em col1 ou col2)
            obj_raw = col1 if is_valid_label(col1) else (col2 if is_valid_label(col2) else "")
            
            # Para LP/Inglês: usa Prática ou Unidade como segundo nível
            # Para outros: usa Unidade Temática diretamente
            # Prioridade: last_pratica > last_unidade > last_campo (fallback)
            if last_pratica:
                unidade_final = last_pratica
            elif last_unidade:
                unidade_final = last_unidade
            else:
                unidade_final = last_campo if last_campo else "Conteúdos"
            # Processa objetos da célula - podem ser múltiplos objetos separados por newline
            # Usa "||" como separador para indicar objetos distintos na mesma linha
            if obj_raw:
                linhas = [l.strip() for l in obj_raw.split('\n') if l.strip()]
                
                if len(linhas) == 1:
                    # Único objeto
                    obj = linhas[0]
                    if is_valid_label(obj) and len(obj) > 5:
                        result.append((last_campo, unidade_final, obj))
                else:
                    # Múltiplas linhas - detectar se são objetos separados ou continuação
                    # Heurísticas mais robustas para identificar continuação vs novo objeto
                    objetos_finais = []
                    buffer = linhas[0]
                    
                    # Palavras que indicam continuação na próxima linha
                    palavras_finais_continuacao = {
                        'do', 'da', 'dos', 'das', 'de', 'no', 'na', 'nos', 'nas',
                        'e', 'ou', 'como', 'entre', 'sobre', 'para', 'por', 'com',
                        'ao', 'aos', 'à', 'às', 'em', 'que', 'o', 'a', 'os', 'as',
                        'seu', 'sua', 'seus', 'suas', 'um', 'uma', 'uns', 'umas'
                    }
                    
                    for i in range(1, len(linhas)):
                        linha = linhas[i]
                        
                        # Analisa buffer anterior
                        buffer_palavras = buffer.rstrip().split()
                        ultima_palavra = buffer_palavras[-1].lower().rstrip('.,;:/') if buffer_palavras else ''
                        buffer_termina_incompleto = buffer.rstrip().endswith((',', '-', '–', ':', '/'))
                        buffer_termina_com_prep = ultima_palavra in palavras_finais_continuacao
                        
                        # Analisa linha atual
                        primeiro_char = linha[0] if linha else ''
                        primeira_palavra = linha.split()[0].lower() if linha.split() else ''
                        palavras_linha = linha.split()
                        
                        # Preposições que indicam continuação se a linha é muito curta
                        preps = {'no', 'na', 'nos', 'nas', 'do', 'da', 'dos', 'das', 'de', 'e'}
                        
                        # Heurística baseada em proporção de tamanho:
                        # - Linha muito curta (<20 chars) após buffer longo (>30 chars) 
                        # - E contém preposição → provavelmente continua o anterior
                        # Ex: "Solar no Universo" (17 chars) após "..do Sistema" (45+ chars)
                        linha_parece_continuacao = False
                        if len(linha) < 20 and len(buffer) > 30:
                            # Verifica se contém preposição
                            palavras_lower = {w.lower() for w in palavras_linha}
                            if palavras_lower & preps:
                                linha_parece_continuacao = True
                        
                        # Detecta se é CONTINUAÇÃO:
                        # 1. Buffer termina com preposição/artigo (frase incompleta)
                        # 2. Buffer termina com pontuação incompleta
                        # 3. Linha começa com minúscula
                        # 4. Linha muito curta com preposição (completa frase anterior)
                        eh_continuacao = (
                            buffer_termina_com_prep or
                            buffer_termina_incompleto or
                            not primeiro_char.isupper() or
                            primeiro_char in '•–-(' or
                            linha_parece_continuacao
                        )
                        if eh_continuacao:
                            buffer += ' ' + linha
                        else:
                            # Novo objeto
                            objetos_finais.append(buffer)
                            buffer = linha
                    
                    if buffer:
                        objetos_finais.append(buffer)
                    
                    # Junta objetos válidos com separador || (preserva 1:1 com linha)
                    # Limpa "/" que foi usado como marcador de continuação
                    objs_validos = []
                    for o in objetos_finais:
                        # Remove "/" do final ou entre palavras (ex: "grafias/ Acentuação" -> "grafias/Acentuação")
                        o_limpo = o.replace('/ ', '/').rstrip('/').strip()
                        if is_valid_label(o_limpo) and len(o_limpo) > 5:
                            objs_validos.append(o_limpo)
                    if objs_validos:
                        # Retorna tupla de 3: (campo, pratica/unidade, objeto)
                        # Para LP: campo é o Campo de Atuação, pratica é a Prática de Linguagem
                        # Para outros: campo fica vazio, unidade é usada
                        result.append((last_campo, unidade_final, "||".join(objs_validos)))
        
        return result
    
    def add_skill_to_tree(code, desc, sigla_comp, campo_key, unidade_key, objeto_key):
        """
        Adiciona uma habilidade à árvore com a estrutura correta.
        Para LP: ano → campo de atuação → prática → objetos + habilidades
        Para outros: ano → unidade temática → objetos + habilidades
        """
        if sigla_comp not in MAPA_EF_ESTRUTURA:
            return
        
        info = MAPA_EF_ESTRUTURA[sigla_comp]
        comp_name = info["componente"]
        area_name = info["area"]
        
        # LP e Inglês têm 4 níveis: ano → campo/eixo → prática/unidade → objetos
        is_4_levels = comp_name in ["Língua Portuguesa", "Língua Inglesa"]
        
        anos_list = expandir_anos_ef(code)
        
        # Defaults para campo (LP/Inglês) ou unidade (outros)
        if is_4_levels:
            if comp_name == "Língua Portuguesa":
                if not campo_key:
                    campo_key = "Todos os campos de atuação"
                if not unidade_key:
                    unidade_key = "Práticas de linguagem"
            elif comp_name == "Língua Inglesa":
                if not campo_key:
                    campo_key = "Eixo oralidade"
                if not unidade_key:
                    unidade_key = "Interação discursiva"
        else:
            if not unidade_key:
                defaults = {
                    "Arte": "Artes integradas", "Educação Física": "Brincadeiras e jogos",
                    "Matemática": "Números",
                    "Ciências": "Vida e evolução", "Geografia": "O sujeito e seu lugar no mundo",
                    "História": "Mundo pessoal: meu lugar no mundo",
                    "Ensino Religioso": "Identidades e alteridades"
                }
                unidade_key = defaults.get(comp_name, "Conteúdos")
        
        # Divide objetos que foram separados por || (múltiplos objetos na mesma célula)
        if not objeto_key or len(objeto_key.strip()) < 5:
            objetos = ["Habilidades gerais"]
        else:
            obj_limpo = objeto_key.strip()
            if obj_limpo.upper() in ['HABILIDADES', 'OBJETOS DE CONHECIMENTO', 'OBJETO DE CONHECIMENTO']:
                objetos = ["Habilidades gerais"]
            elif "||" in obj_limpo:
                # Múltiplos objetos separados por ||
                objetos = [o.strip() for o in obj_limpo.split("||") if o.strip()]
            else:
                objetos = [obj_limpo]
        
        for ano in anos_list:
            base = tree[area_name]["componentes"][comp_name]["anos"]
            if ano not in base:
                base[ano] = {}
            
            if is_4_levels:
                # LP/Inglês: 4 níveis - ano → campo/eixo → prática/unidade → grupos
                # Parseia campo_key para separar nome de descrição
                parsed_campo = parse_campo_name_description(campo_key)
                campo_nome = parsed_campo["nome"] or "Campo não especificado"
                campo_descricao = parsed_campo["descricao"]
                
                # Inicializa campos_metadata se necessário
                comp_base = tree[area_name]["componentes"][comp_name]
                if "campos_metadata" not in comp_base:
                    comp_base["campos_metadata"] = {}
                
                # Armazena descrição do campo (evita duplicatas)
                if campo_nome not in comp_base["campos_metadata"] and campo_descricao:
                    comp_base["campos_metadata"][campo_nome] = campo_descricao
                
                # Usa nome limpo como chave
                if campo_nome not in base[ano]:
                    base[ano][campo_nome] = {}
                
                if unidade_key not in base[ano][campo_nome]:
                    base[ano][campo_nome][unidade_key] = []
                
                target_list = base[ano][campo_nome][unidade_key]
            else:
                # Outros: 3 níveis - ano → unidade → grupos
                if unidade_key not in base[ano]:
                    base[ano][unidade_key] = []
                
                target_list = base[ano][unidade_key]
            
            # Procura grupo existente com exatamente os mesmos objetos
            objetos_set = tuple(sorted(objetos))  # Para comparação
            grupo_existente = None
            
            for grupo in target_list:
                if tuple(sorted(grupo.get("objetos", []))) == objetos_set:
                    grupo_existente = grupo
                    break
            
            if grupo_existente is None:
                # Cria novo grupo
                grupo_existente = {"objetos": objetos, "habilidades": []}
                target_list.append(grupo_existente)
            
            # Adiciona habilidade ao grupo (sem duplicar)
            if not any(s['codigo'] == code for s in grupo_existente["habilidades"]):
                grupo_existente["habilidades"].append({
                    "codigo": code, 
                    "descricao": desc,
                    "anos_aplicaveis": anos_list  # Lista de todos os anos onde essa habilidade se aplica
                })
    
    # ========================================================================
    # LOOP PRINCIPAL DE EXTRAÇÃO
    # ========================================================================
    
    for page_num in EF_PAGE_RANGE:
        if page_num >= len(pdf.pages):
            break
        
        page = pdf.pages[page_num]
        text_page = page.extract_text() or ""
        text_upper = text_page.upper()
        
        # Extrai palavras em itálico da página para formatação Markdown
        page_italic_words = extract_italic_words(page)
        
        # Detecta componente atual pela página
        # PRIORIDADE 1: Padrões de área com componente específico
        detected_comp = None
        
        # Check área patterns primeiro (mais específicos)
        if "CIÊNCIAS HUMANAS – HISTÓRIA" in text_upper or "HISTÓRIA –" in text_upper:
            detected_comp = "História"
        elif "CIÊNCIAS HUMANAS – GEOGRAFIA" in text_upper or "GEOGRAFIA –" in text_upper:
            detected_comp = "Geografia"
        elif "CIÊNCIAS DA NATUREZA – CIÊNCIAS" in text_upper or "CIÊNCIAS –" in text_upper:
            detected_comp = "Ciências"
        elif "LINGUAGENS – ARTE" in text_upper or "\nARTE –" in text_upper or "\nARTE\n" in text_upper:
            detected_comp = "Arte"
        elif "LINGUAGENS – EDUCAÇÃO FÍSICA" in text_upper or "EDUCAÇÃO FÍSICA –" in text_upper:
            detected_comp = "Educação Física"
        elif "LINGUAGENS – LÍNGUA INGLESA" in text_upper or "LÍNGUA INGLESA –" in text_upper:
            detected_comp = "Língua Inglesa"
        elif "LINGUAGENS – LÍNGUA PORTUGUESA" in text_upper or "LÍNGUA PORTUGUESA –" in text_upper:
            detected_comp = "Língua Portuguesa"
        elif "ENSINO RELIGIOSO –" in text_upper or "\nENSINO RELIGIOSO\n" in text_upper:
            detected_comp = "Ensino Religioso"
        elif "MATEMÁTICA –" in text_upper or "\nMATEMÁTICA\n" in text_upper:
            detected_comp = "Matemática"
        
        if detected_comp:
            # Encontra área correspondente
            for sigla, info in MAPA_EF_ESTRUTURA.items():
                if info["componente"] == detected_comp:
                    if current_comp != detected_comp:
                        # Mudou de componente, reseta contexto
                        context_unidades = []
                        last_unidade = ""
                        last_objeto = ""
                    current_comp = detected_comp
                    current_area = info["area"]
                    break
        
        # Extrai tabelas
        tables = page.extract_tables({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        
        for table in tables:
            if not table or len(table) < 2:
                continue
            
            # Analisa header
            header_row = [clean_text_basic(c).upper() if c else "" for c in table[0]]
            header_str = " ".join(header_row)
            num_cols = len(table[0])
            
            # Skip competências
            if "COMPETÊNCIAS" in header_str or "COMPETÊNCIA" in header_str:
                continue
            
            # ============================================
            # TABELA DE CONTEXTO (Unidades/Objetos)
            # ============================================
            if is_context_table(header_str):
                new_context = extract_context_from_table(table, num_cols)
                if new_context:
                    context_unidades = new_context  # Lista de tuplas (campo, unidade, objeto)
                    # Atualiza last_campo/last_unidade/last_objeto para ÚLTIMA entrada
                    # (o contexto mais recente será usado para habilidades seguintes)
                    for c, u, o in context_unidades:
                        if c:
                            last_campo = c
                        if u:
                            last_unidade = u
                        if o:
                            last_objeto = o
                continue
            
            # ============================================
            # TABELA DE HABILIDADES
            # ============================================
            if is_skills_table(header_str, table):
                # Processa cada linha de dados (pula header)
                data_rows = [r for r in table[1:] if r and any(c for c in r if c)]
                
                # Filtra sub-headers que contêm apenas labels de anos (1º ANO, 2º ANO, etc.)
                # Essas linhas não contêm habilidades e causam deslocamento no mapeamento
                def is_year_subheader(row):
                    text = ' '.join(str(c) if c else '' for c in row).strip().upper()
                    # Se a linha contém apenas combinações de "Nº ANO" sem códigos EF
                    return (bool(re.search(r'^\d+º?\s*ANO', text)) and 
                            not RE_CODE_EF.search(text) and
                            len(text) < 50)
                
                data_rows = [r for r in data_rows if not is_year_subheader(r)]
                
                # MAPEAMENTO POSICIONAL: Row N da tabela de habilidades corresponde
                # a Row N da tabela de contexto (podem estar em páginas diferentes)
                # context_unidades persiste da última tabela de contexto processada
                
                for row_idx, row in enumerate(data_rows):
                    if not row:
                        continue
                    
                    # Determina contexto para esta linha usando mapeamento 1:1
                    if context_unidades and row_idx < len(context_unidades):
                        row_campo, row_unidade, row_objeto = context_unidades[row_idx]
                    else:
                        # Fallback: usa último contexto conhecido
                        row_campo = last_campo
                        row_unidade = last_unidade
                        row_objeto = last_objeto
                    
                    # Processa cada célula que pode conter habilidades
                    for col_idx, cell in enumerate(row):
                        if not cell:
                            continue
                        
                        cell_text = clean_text_basic(cell)
                        
                        # Verifica se a célula contém códigos de habilidade
                        if not RE_CODE_EF.search(cell_text):
                            # Detecta continuação de descrição de Campo (qualquer coluna)
                            # (texto longo sem código EF que parece descrição)
                            if (len(cell_text) > 80 and 
                                  (cell_text.startswith("Trata-se") or 
                                   cell_text.startswith("Considerando") or
                                   cell_text.startswith("Essas habilidades") or
                                   cell_text.startswith("Para além") or
                                   cell_text.startswith("É importante") or
                                   cell_text.startswith("Vários são") or  # Campo Jornalístico
                                   cell_text.startswith("Diversos também") or  # Continuação
                                   cell_text.startswith("Ainda com relação") or  # Continuação
                                   cell_text.startswith("Nesse campo") or  # Continuação
                                   cell_text.startswith("A formação") or  # Campo Artístico-Literário
                                   "vivências significativas" in cell_text or
                                   "articulação com todas as áreas" in cell_text) and
                                  last_campo):
                                # Acumula continuação para aplicar no final
                                parsed = parse_campo_name_description(last_campo)
                                campo_nome = parsed["nome"]
                                continuation = _format_campo_description(cell_text)
                                if campo_nome not in campo_desc_extra:
                                    campo_desc_extra[campo_nome] = []
                                campo_desc_extra[campo_nome].append(continuation)
                            # Pode ser label de Unidade/Objeto na primeira coluna
                            elif col_idx == 0 and is_valid_label(cell_text):
                                # Atualiza contexto para próximas linhas sem contexto
                                if len(cell_text) < 50:
                                    last_unidade = cell_text
                                else:
                                    last_objeto = cell_text
                            continue
                        
                        # Extrai todos os códigos da célula
                        matches = list(RE_CODE_EF.finditer(cell_text))
                        
                        for i, match in enumerate(matches):
                            code = match.group(1)
                            sigla_comp = match.group(2)
                            
                            # Extrai descrição
                            start_pos = match.end()
                            end_pos = matches[i+1].start() if i+1 < len(matches) else len(cell_text)
                            desc = processar_descricao(cell_text[start_pos:end_pos], code, page_italic_words)
                            
                            # Usa contexto da linha ou fallback
                            add_skill_to_tree(code, desc, sigla_comp,
                                            row_campo if row_campo else last_campo,
                                            row_unidade if row_unidade else last_unidade, 
                                            row_objeto if row_objeto else last_objeto)
                
                
                continue
            
            # ============================================
            # TABELA MISTA (3+ colunas com Unidade/Objeto/Habilidade)
            # ============================================
            if num_cols >= 3:
                for row in table[1:]:
                    if not row or len(row) < 3:
                        continue
                    
                    col0 = clean_text_basic(row[0]) if row[0] else ""
                    col1 = clean_text_basic(row[1]) if row[1] else ""
                    col2 = clean_text_basic(row[2]) if len(row) > 2 and row[2] else ""
                    
                    # Atualiza contexto
                    if is_valid_label(col0):
                        last_unidade = col0
                    if is_valid_label(col1):
                        last_objeto = col1
                    
                    # Procura habilidades na última coluna (ou em col2)
                    skill_text = col2 if RE_CODE_EF.search(col2) else ""
                    if not skill_text:
                        # Tenta col1 se col2 não tem código
                        if RE_CODE_EF.search(col1):
                            skill_text = col1
                            last_objeto = ""  # col1 era habilidade, não objeto
                    
                    if not skill_text:
                        continue
                    
                    matches = list(RE_CODE_EF.finditer(skill_text))
                    for i, match in enumerate(matches):
                        code = match.group(1)
                        sigla_comp = match.group(2)
                        start_pos = match.end()
                        end_pos = matches[i+1].start() if i+1 < len(matches) else len(skill_text)
                        desc = processar_descricao(skill_text[start_pos:end_pos], code, page_italic_words)
                        
                        add_skill_to_tree(code, desc, sigla_comp, last_campo, last_unidade, last_objeto)
            
            # ============================================
            # TABELA 2 COLUNAS
            # ============================================
            elif num_cols == 2:
                for row in table[1:]:
                    if not row or len(row) < 2:
                        continue
                    
                    col0 = clean_text_basic(row[0]) if row[0] else ""
                    col1 = clean_text_basic(row[1]) if row[1] else ""
                    
                    # Col0 pode ser Unidade/Objeto label
                    if is_valid_label(col0) and not RE_CODE_EF.search(col0):
                        last_unidade = col0
                    
                    # Col1 geralmente tem as habilidades
                    if not RE_CODE_EF.search(col1):
                        continue
                    
                    matches = list(RE_CODE_EF.finditer(col1))
                    for i, match in enumerate(matches):
                        code = match.group(1)
                        sigla_comp = match.group(2)
                        start_pos = match.end()
                        end_pos = matches[i+1].start() if i+1 < len(matches) else len(col1)
                        desc = processar_descricao(col1[start_pos:end_pos], code, page_italic_words)
                        
                        add_skill_to_tree(code, desc, sigla_comp, last_campo, last_unidade, last_objeto)

    # ========================================================================
    # RELATÓRIO FINAL
    # ========================================================================
    print("\n--- Resumo da Extração EF ---")
    total_all = 0
    for area, area_data in tree.items():
        for comp, comp_data in area_data["componentes"].items():
            total_skills = 0
            unique_codes = set()
            def count_skills(obj):
                nonlocal total_skills
                if isinstance(obj, dict):
                    if 'codigo' in obj: 
                        total_skills += 1
                        unique_codes.add(obj['codigo'])
                    for v in obj.values(): count_skills(v)
                elif isinstance(obj, list):
                    for item in obj: count_skills(item)
            count_skills(comp_data["anos"])
            print(f"  {comp}: {total_skills} habilidades ({len(unique_codes)} códigos únicos)")
            total_all += len(unique_codes)
    
    print(f"\n  TOTAL: {total_all} códigos únicos extraídos")
    
    # Aplica continuações de descrições de campos acumuladas
    if campo_desc_extra:
        for area_name, area_data in tree.items():
            if "componentes" not in area_data:
                continue
            for comp_name, comp_data in area_data.get("componentes", {}).items():
                if "campos_metadata" not in comp_data:
                    continue
                for campo_nome, continuations in campo_desc_extra.items():
                    if campo_nome in comp_data["campos_metadata"]:
                        existing = comp_data["campos_metadata"][campo_nome]
                        for cont in continuations:
                            existing = existing + "\n\n" + cont
                        comp_data["campos_metadata"][campo_nome] = existing
    
    return tree


# ========================================================================
# EXTRAÇÃO ENSINO MÉDIO - ESTRUTURA HIERÁRQUICA
# ========================================================================

def extract_em_final(pdf):
    """
    Extrai Ensino Médio em estrutura hierárquica:
    - Áreas com Competências Específicas
    - Habilidades agrupadas por Competência
    - LP com Campos de Atuação e Competências Associadas
    """
    print("--- Processando Ensino Médio ---")
    
    # Regex patterns
    RE_CODE_EM = re.compile(r"\(?(EM13([A-Z]{2,4})(\d{2,3}))\)?")
    RE_COMP_ESP = re.compile(r"COMPETÊNCIA\s+ESPECÍFICA\s+(\d+)", re.IGNORECASE)
    RE_CAMPO = re.compile(r"^(TODOS OS CAMPOS|CAMPO\s+D[AEO]\s+[A-ZÁÉÍÓÚÃÕÊ\s]+)", re.IGNORECASE)
    
    def clean_text(text):
        if not text:
            return ""
        return re.sub(r'\s+', ' ', unicodedata.normalize("NFKC", text)).strip()
    
    # Estrutura de saída
    tree = {
        "Linguagens e suas Tecnologias": {
            "competencias_especificas": [],
            "componentes": {
                "Língua Portuguesa": {
                    "campos_de_atuacao": {}
                }
            }
        },
        "Matemática e suas Tecnologias": {
            "competencias_especificas": []
        },
        "Ciências da Natureza e suas Tecnologias": {
            "competencias_especificas": []
        },
        "Ciências Humanas e Sociais Aplicadas": {
            "competencias_especificas": []
        }
    }
    
    # Estado de processamento
    current_area = ""
    current_comp_esp = None
    current_campo = ""
    current_praticas = ""
    
    # Dicionário temporário para competências
    comp_esp_temp = {}  # {(area, numero): {"texto": str, "habilidades": []}}
    lp_habilidades = []  # Lista de habilidades LP com competências associadas
    
    # ========================================================================
    # FASE 1: Extrair Competências Específicas e suas descrições
    # ========================================================================
    
    for page_num in range(480, 600):
        if page_num >= len(pdf.pages):
            break
        
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        upper_text = text.upper()
        
        # Detecta área atual
        if "LINGUAGENS E SUAS TECNOLOGIAS" in upper_text and page_num < 530:
            current_area = "Linguagens e suas Tecnologias"
        elif "MATEMÁTICA E SUAS TECNOLOGIAS" in upper_text:
            current_area = "Matemática e suas Tecnologias"
        elif "CIÊNCIAS DA NATUREZA E SUAS TECNOLOGIAS" in upper_text:
            current_area = "Ciências da Natureza e suas Tecnologias"
        elif "CIÊNCIAS HUMANAS E SOCIAIS APLICADAS" in upper_text:
            current_area = "Ciências Humanas e Sociais Aplicadas"
        
        # Detecta Competência Específica
        comp_match = RE_COMP_ESP.search(text)
        if comp_match and current_area:
            comp_num = int(comp_match.group(1))
            
            # Extrai texto da competência (próximas linhas após o título)
            lines = text.split('\n')
            comp_text = ""
            capture = False
            for line in lines:
                if RE_COMP_ESP.search(line):
                    capture = True
                    continue
                if capture:
                    clean_line = clean_text(line)
                    # Para quando encontra habilidade ou próxima competência
                    if RE_CODE_EM.search(clean_line) or RE_COMP_ESP.search(clean_line):
                        break
                    if len(clean_line) > 10:
                        comp_text += " " + clean_line
            
            comp_text = clean_text(comp_text)
            if comp_text:
                key = (current_area, comp_num)
                if key not in comp_esp_temp:
                    comp_esp_temp[key] = {"texto": comp_text, "habilidades": []}
            
            current_comp_esp = comp_num
    
    # ========================================================================
    # FASE 2: Extrair Habilidades e associá-las às Competências
    # ========================================================================
    
    current_area = ""
    current_comp_esp = None
    
    for page_num in range(480, 600):
        if page_num >= len(pdf.pages):
            break
        
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        upper_text = text.upper()
        
        # Detecta área
        if "LINGUAGENS E SUAS TECNOLOGIAS" in upper_text and page_num < 530:
            current_area = "Linguagens e suas Tecnologias"
        elif "MATEMÁTICA E SUAS TECNOLOGIAS" in upper_text:
            current_area = "Matemática e suas Tecnologias"
        elif "CIÊNCIAS DA NATUREZA E SUAS TECNOLOGIAS" in upper_text:
            current_area = "Ciências da Natureza e suas Tecnologias"
        elif "CIÊNCIAS HUMANAS E SOCIAIS APLICADAS" in upper_text:
            current_area = "Ciências Humanas e Sociais Aplicadas"
        
        # Detecta Competência Específica
        comp_match = RE_COMP_ESP.search(text)
        if comp_match:
            current_comp_esp = int(comp_match.group(1))
        
        # Extrai habilidades
        lines = text.split('\n')
        buffer_code = None
        buffer_desc = []
        buffer_sigla = ""
        
        for line in lines:
            clean_line = clean_text(line)
            match = RE_CODE_EM.search(clean_line)
            
            if match:
                # Salva habilidade anterior
                if buffer_code and buffer_desc:
                    desc = clean_text(" ".join(buffer_desc))
                    _add_em_habilidade(comp_esp_temp, current_area, current_comp_esp, 
                                       buffer_code, buffer_sigla, desc)
                
                # Nova habilidade
                buffer_code = match.group(1)
                buffer_sigla = match.group(2)
                start_desc = clean_line[match.end():].strip()
                start_desc = re.sub(r"^[\s\.\-\)]+", "", start_desc)
                buffer_desc = [start_desc] if start_desc else []
                
            elif buffer_code:
                # Continua descrição
                if len(clean_line) > 3 and not clean_line.isdigit():
                    buffer_desc.append(clean_line)
        
        # Última habilidade da página
        if buffer_code and buffer_desc:
            desc = clean_text(" ".join(buffer_desc))
            _add_em_habilidade(comp_esp_temp, current_area, current_comp_esp,
                               buffer_code, buffer_sigla, desc)
    
    # ========================================================================
    # FASE 3: Processar LP com tabelas (Campos de Atuação + Competências Associadas)
    # ========================================================================
    
    current_campo = "Todos os Campos de Atuação Social"
    current_praticas = ""
    
    for page_num in range(506, 530):
        if page_num >= len(pdf.pages):
            break
        
        page = pdf.pages[page_num]
        tables = page.extract_tables()
        
        for table in tables:
            if not table or len(table) < 2:
                continue
            
            for row in table:
                if not row or len(row) < 1:
                    continue
                
                col0 = clean_text(row[0]) if row[0] else ""
                col1 = clean_text(row[1]) if len(row) > 1 and row[1] else ""
                
                # Detecta Campo de Atuação
                if "TODOS OS CAMPOS" in col0.upper():
                    current_campo = "Todos os Campos de Atuação Social"
                elif "CAMPO DA VIDA PESSOAL" in col0.upper():
                    current_campo = "Campo da Vida Pessoal"
                elif "CAMPO DE ATUAÇÃO NA VIDA PÚBLICA" in col0.upper():
                    current_campo = "Campo de Atuação na Vida Pública"
                elif "CAMPO DAS PRÁTICAS DE ESTUDO" in col0.upper():
                    current_campo = "Campo das Práticas de Estudo e Pesquisa"
                elif "CAMPO JORNALÍSTICO" in col0.upper():
                    current_campo = "Campo Jornalístico-Midiático"
                elif "CAMPO ARTÍSTICO" in col0.upper():
                    current_campo = "Campo Artístico-Literário"
                
                # Detecta Práticas
                if "PRÁTICAS" in col0.upper() and len(col0) < 200:
                    current_praticas = col0
                
                # Extrai habilidade LP
                lp_match = RE_CODE_EM.search(col0)
                if lp_match and lp_match.group(2) == "LP":
                    code = lp_match.group(1)
                    # Descrição é o resto da célula após o código
                    desc_start = col0[lp_match.end():].strip()
                    desc_start = re.sub(r"^[\s\.\-\)]+", "", desc_start)
                    
                    # Competências associadas (números na col1)
                    comp_assoc = []
                    if col1:
                        nums = re.findall(r"\d+", col1)
                        comp_assoc = [int(n) for n in nums if 1 <= int(n) <= 7]
                    
                    lp_habilidades.append({
                        "codigo": code,
                        "descricao": desc_start,
                        "campo": current_campo,
                        "praticas": current_praticas,
                        "competencias_associadas": comp_assoc
                    })
    
    # ========================================================================
    # FASE 4: Montar estrutura final
    # ========================================================================
    
    # Adiciona competências específicas às áreas
    for (area, num), data in sorted(comp_esp_temp.items(), key=lambda x: (x[0][0], x[0][1])):
        if area in tree:
            # Filtra habilidades LGG/MAT/CNT/CHS (não LP)
            habilidades_filtradas = [h for h in data["habilidades"] if "LP" not in h["codigo"]]
            
            tree[area]["competencias_especificas"].append({
                "numero": num,
                "texto": data["texto"][:500] if data["texto"] else "",  # Limita tamanho
                "habilidades": habilidades_filtradas
            })
    
    # Adiciona habilidades LP aos campos de atuação
    lp_data = tree["Linguagens e suas Tecnologias"]["componentes"]["Língua Portuguesa"]
    for hab in lp_habilidades:
        campo = hab["campo"]
        if campo not in lp_data["campos_de_atuacao"]:
            lp_data["campos_de_atuacao"][campo] = {
                "habilidades": []
            }
        
        lp_data["campos_de_atuacao"][campo]["habilidades"].append({
            "codigo": hab["codigo"],
            "descricao": hab["descricao"],
            "competencias_associadas": hab["competencias_associadas"]
        })
    
    # ========================================================================
    # ESTATÍSTICAS
    # ========================================================================
    
    total_hab = 0
    for area, area_data in tree.items():
        area_count = 0
        for comp in area_data.get("competencias_especificas", []):
            area_count += len(comp.get("habilidades", []))
        
        # Conta LP separadamente
        if "componentes" in area_data:
            for comp_name, comp_data in area_data["componentes"].items():
                for campo, campo_data in comp_data.get("campos_de_atuacao", {}).items():
                    area_count += len(campo_data.get("habilidades", []))
        
        if area_count > 0:
            print(f"  {area}: {area_count} habilidades")
        total_hab += area_count
    
    print(f"\n  TOTAL EM: {total_hab} habilidades extraídas")
    
    return tree


def _add_em_habilidade(comp_esp_temp, area, comp_num, code, sigla, desc):
    """Adiciona habilidade à competência específica correspondente."""
    if not area or not comp_num:
        return
    
    # Deriva competência do código (ex: EM13LGG101 -> comp 1, EM13LGG201 -> comp 2)
    if sigla in ["LGG", "MAT", "CNT", "CHS"]:
        # O primeiro dígito após a sigla indica a competência
        match = re.search(r"\d+$", code)
        if match:
            num_str = match.group()
            if len(num_str) >= 2:
                derived_comp = int(num_str[0])
            else:
                derived_comp = comp_num
        else:
            derived_comp = comp_num
    else:
        derived_comp = comp_num
    
    key = (area, derived_comp)
    if key not in comp_esp_temp:
        comp_esp_temp[key] = {"texto": "", "habilidades": []}
    
    # Evita duplicatas
    existing_codes = [h["codigo"] for h in comp_esp_temp[key]["habilidades"]]
    if code not in existing_codes:
        comp_esp_temp[key]["habilidades"].append({
            "codigo": code,
            "descricao": desc
        })


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
    em_data = extract_em_final(pdf)  # Nova versão estruturada
    
    pdf.close()

    print("\n--- Salvando Arquivos ---")
    with open("bncc_ei.json", "w", encoding="utf-8") as f: json.dump(ei_data, f, ensure_ascii=False, indent=2)
    with open("bncc_ef.json", "w", encoding="utf-8") as f: json.dump(ef_data, f, ensure_ascii=False, indent=2)
    with open("bncc_em.json", "w", encoding="utf-8") as f: json.dump(em_data, f, ensure_ascii=False, indent=2)
    print("Processo concluído.")

if __name__ == "__main__":
    main()