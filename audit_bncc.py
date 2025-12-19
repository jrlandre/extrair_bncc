#!/usr/bin/env python3
"""
AUDITORIA COMPLETA - Verificação BNCC JSON vs PDF Original
Cobre EI, EF e EM com verificação de estrutura, contagens e conteúdo.
"""

import json
import pdfplumber
import re
import random
from collections import defaultdict

# Regex para códigos
RE_CODE_EF = re.compile(r'\(?(EF\d{2,3}[A-Z]{2}\d{2,3})\)?')
RE_CODE_EI = re.compile(r'(EI\d{2}[A-Z]{2}\d{2})')
RE_CODE_EM = re.compile(r'\(?(EM13[A-Z]{2,4}\d{2,3})\)?')

# Contagens esperadas (verificadas diretamente no PDF)
EXPECTED_COUNTS = {
    'EF': {
        'total_codes': 1304,
        'LP': 391,
        'AR': 61,
        'EF': 69,
        'LI': 88,
        'MA': 247,
        'CI': 111,
        'GE': 123,
        'HI': 151,
        'ER': 63
    },
    'EM': {
        'total': 183,
        'LGG': 28,
        'LP': 54,
        'MAT': 43,
        'CNT': 26,
        'CHS': 32
    },
    'EI': {
        'objetivos': 93,  # 29 (EI01) + 32 (EI02) + 32 (EI03)
        'sintese': 19     # 19 itens distribuídos por campo
    }
}

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_code_in_pdf(pdf, code, page_range):
    """Procura um código no PDF e retorna o contexto ao redor"""
    for page_num in page_range:
        if page_num >= len(pdf.pages):
            continue
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        
        if code in text:
            idx = text.find(code)
            start = max(0, idx - 50)
            end = min(len(text), idx + 200)
            context = text[start:end].replace('\n', ' ')
            return {
                'page': page_num + 1,
                'context': context,
                'found': True
            }
    return {'page': None, 'context': None, 'found': False}

def extract_description_from_context(context, code):
    """Extrai a descrição do contexto do PDF"""
    if not context:
        return ""
    idx = context.find(code)
    if idx >= 0:
        desc_start = idx + len(code)
        desc = context[desc_start:].strip()
        desc = re.sub(r'^[)\s]+', '', desc)
        return desc[:100]
    return ""

# ============================================================================
# SAMPLE FUNCTIONS
# ============================================================================

def sample_ef_skills(data, sample_size=100):
    """Amostra habilidades do EF com hierarquia completa - recursivo para LP"""
    skills = []
    
    def collect_recursive(obj, context):
        """Coleta habilidades recursivamente"""
        if isinstance(obj, dict):
            if 'habilidades' in obj:
                for hab in obj['habilidades']:
                    skills.append({
                        'codigo': hab['codigo'],
                        'descricao': hab['descricao'],
                        'area': context.get('area', ''),
                        'componente': context.get('componente', ''),
                        'ano': context.get('ano', ''),
                        'unidade': context.get('unidade', ''),
                        'objetos': obj.get('objetos', [])
                    })
            for key, value in obj.items():
                if key not in ['habilidades', 'objetos', 'codigo', 'descricao', 'anos_aplicaveis']:
                    # Update context based on key type
                    new_context = context.copy()
                    if 'Ano' in str(key):
                        new_context['ano'] = key
                    elif key not in ['anos', 'componentes']:
                        new_context['unidade'] = key
                    collect_recursive(value, new_context)
        elif isinstance(obj, list):
            for item in obj:
                collect_recursive(item, context)
    
    for area, area_data in data.items():
        if area == "metadata":
            continue
        for comp, comp_data in area_data.get('componentes', {}).items():
            anos = comp_data.get('anos', {})
            collect_recursive(anos, {'area': area, 'componente': comp})
    
    if len(skills) > sample_size:
        skills = random.sample(skills, sample_size)
    return skills


def sample_ei_skills(data, sample_size=50):
    """Amostra objetivos do EI com hierarquia"""
    skills = []
    for faixa, campos in data.get('objetivos_aprendizagem', {}).items():
        for campo, objetivos in campos.items():
            for obj in objetivos:
                skills.append({
                    'codigo': obj['codigo'],
                    'descricao': obj['descricao'],
                    'faixa': faixa,
                    'campo': campo
                })
    
    if len(skills) > sample_size:
        skills = random.sample(skills, sample_size)
    return skills

def sample_em_skills(data, sample_size=50):
    """Amostra habilidades do EM com hierarquia"""
    skills = []
    
    # Habilidades de áreas (LGG, MAT, CNT, CHS)
    for area, area_data in data.items():
        for comp in area_data.get('competencias_especificas', []):
            for hab in comp.get('habilidades', []):
                skills.append({
                    'codigo': hab['codigo'],
                    'descricao': hab['descricao'],
                    'area': area,
                    'competencia': comp['numero'],
                    'tipo': 'area'
                })
        
        # Habilidades LP (campos)
        if 'componentes' in area_data:
            for comp_name, comp_data in area_data['componentes'].items():
                for campo, campo_data in comp_data.get('campos_de_atuacao', {}).items():
                    for hab in campo_data.get('habilidades', []):
                        skills.append({
                            'codigo': hab['codigo'],
                            'descricao': hab['descricao'],
                            'area': area,
                            'componente': comp_name,
                            'campo': campo,
                            'competencias_associadas': hab.get('competencias_associadas', []),
                            'tipo': 'LP'
                        })
    
    if len(skills) > sample_size:
        skills = random.sample(skills, sample_size)
    return skills

# ============================================================================
# VERIFICATION FUNCTIONS
# ============================================================================

def verify_skill(pdf, skill, page_range):
    """Verifica uma habilidade contra o PDF"""
    code = skill['codigo']
    result = find_code_in_pdf(pdf, code, page_range)
    
    if not result['found']:
        return {
            'status': 'NOT_FOUND',
            'code': code,
            'message': f'Código {code} não encontrado no PDF'
        }
    
    pdf_desc = extract_description_from_context(result['context'], code)
    json_desc = skill['descricao'][:100]
    
    pdf_norm = re.sub(r'\s+', ' ', pdf_desc.lower().strip())
    json_norm = re.sub(r'\s+', ' ', json_desc.lower().strip())
    
    pdf_words = pdf_norm.split()[:5]
    json_words = json_norm.split()[:5]
    
    match_score = sum(1 for a, b in zip(pdf_words, json_words) if a == b) / max(len(pdf_words), 1)
    
    return {
        'status': 'MATCH' if match_score > 0.6 else 'MISMATCH',
        'code': code,
        'page': result['page'],
        'match_score': match_score,
        'pdf_excerpt': pdf_desc[:60],
        'json_excerpt': json_desc[:60],
        'skill': skill
    }

# ============================================================================
# COUNT AND STRUCTURE VERIFICATION
# ============================================================================

def count_ef_skills(data):
    """Conta habilidades do EF por componente - recursivo para lidar com LP"""
    counts = defaultdict(lambda: {'total': 0, 'unique': set()})
    
    def count_recursive(obj):
        """Conta habilidades recursivamente em qualquer estrutura"""
        total = 0
        if isinstance(obj, dict):
            if 'habilidades' in obj:
                for h in obj['habilidades']:
                    code = h['codigo']
                    match = RE_CODE_EF.match(code)
                    if match:
                        sigla = code[4:6]  # Ex: EF01LP01 -> LP
                        counts[sigla]['total'] += 1
                        counts[sigla]['unique'].add(code)
                        total += 1
            for key, value in obj.items():
                if key not in ['habilidades', 'objetos', 'codigo', 'descricao', 'anos_aplicaveis']:
                    total += count_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                total += count_recursive(item)
        return total
    
    for area, area_data in data.items():
        if area == "metadata":
            continue
        for comp, comp_data in area_data.get('componentes', {}).items():
            anos = comp_data.get('anos', {})
            count_recursive(anos)
    
    return counts


def count_em_skills(data):
    """Conta habilidades do EM por área/componente"""
    counts = {'LGG': 0, 'LP': 0, 'MAT': 0, 'CNT': 0, 'CHS': 0}
    
    for area, area_data in data.items():
        for comp in area_data.get('competencias_especificas', []):
            for hab in comp.get('habilidades', []):
                code = hab['codigo']
                if 'LGG' in code:
                    counts['LGG'] += 1
                elif 'MAT' in code:
                    counts['MAT'] += 1
                elif 'CNT' in code:
                    counts['CNT'] += 1
                elif 'CHS' in code:
                    counts['CHS'] += 1
        
        if 'componentes' in area_data:
            for comp_name, comp_data in area_data['componentes'].items():
                for campo, campo_data in comp_data.get('campos_de_atuacao', {}).items():
                    counts['LP'] += len(campo_data.get('habilidades', []))
    
    return counts

def count_ei_items(data):
    """Conta itens do EI"""
    obj_count = 0
    for faixa in data.get('objetivos_aprendizagem', {}).values():
        for campo in faixa.values():
            obj_count += len(campo)
    
    sintese_count = sum(len(v) for v in data.get('sintese_aprendizagens', {}).values())
    
    return {'objetivos': obj_count, 'sintese': sintese_count}

# ============================================================================
# STRUCTURE VERIFICATION
# ============================================================================

def verify_ef_structure(data):
    """Verifica estrutura do EF em detalhes"""
    issues = []
    
    for area, area_data in data.items():
        if area == "metadata":
            continue
        
        # Verifica competências específicas da área
        if 'competencias_especificas_area' not in area_data or not area_data['competencias_especificas_area']:
            issues.append(f"❌ {area}: Falta 'competencias_especificas_area'")
        
        for comp, comp_data in area_data.get('componentes', {}).items():
            # Verifica campos_metadata para LP
            if comp == "Língua Portuguesa":
                if 'campos_metadata' not in comp_data:
                    issues.append(f"❌ {comp}: Falta 'campos_metadata'")
                else:
                    campos = comp_data['campos_metadata']
                    if len(campos) < 4:
                        issues.append(f"⚠️ {comp}: Apenas {len(campos)} campos de atuação")
            
            # Verifica anos
            anos = comp_data.get('anos', {})
            if not anos:
                issues.append(f"⚠️ {comp}: Sem anos definidos")
            
            # Verifica habilidades por ano (contagem recursiva)
            def count_hab_recursive(obj):
                total = 0
                if isinstance(obj, dict):
                    if 'habilidades' in obj:
                        total += len(obj['habilidades'])
                    for k, v in obj.items():
                        if k not in ['habilidades', 'objetos', 'codigo', 'descricao', 'anos_aplicaveis']:
                            total += count_hab_recursive(v)
                elif isinstance(obj, list):
                    for item in obj:
                        total += count_hab_recursive(item)
                return total
            
            for ano, ano_data in anos.items():
                hab_count = count_hab_recursive(ano_data)
                if hab_count == 0:
                    issues.append(f"⚠️ {comp} > {ano}: Sem habilidades")
    
    return issues

def verify_em_structure(data):
    """Verifica estrutura do EM em detalhes"""
    issues = []
    
    expected_areas = [
        "Linguagens e suas Tecnologias",
        "Matemática e suas Tecnologias",
        "Ciências da Natureza e suas Tecnologias",
        "Ciências Humanas e Sociais Aplicadas"
    ]
    
    for area in expected_areas:
        if area not in data:
            issues.append(f"❌ Falta área: {area}")
            continue
        
        area_data = data[area]
        
        # Verifica competências específicas
        comps = area_data.get('competencias_especificas', [])
        if not comps:
            issues.append(f"⚠️ {area}: Sem competências específicas")
        
        # Verifica que cada competência tem habilidades (exceto Linguagens que tem LP separado)
        for comp in comps:
            if 'numero' not in comp:
                issues.append(f"⚠️ {area}: Competência sem número")
            if 'texto' not in comp or not comp['texto']:
                issues.append(f"⚠️ {area} CE{comp.get('numero', '?')}: Sem texto")
    
    # Verifica LP
    if "Linguagens e suas Tecnologias" in data:
        lp_data = data["Linguagens e suas Tecnologias"].get('componentes', {}).get('Língua Portuguesa', {})
        campos = lp_data.get('campos_de_atuacao', {})
        
        if not campos:
            issues.append("❌ LP: Sem campos de atuação")
        else:
            for campo, campo_data in campos.items():
                habs = campo_data.get('habilidades', [])
                if not habs:
                    issues.append(f"⚠️ LP > {campo}: Sem habilidades")
                
                # Verifica competências associadas
                for hab in habs:
                    if 'competencias_associadas' not in hab:
                        issues.append(f"⚠️ {hab.get('codigo', '?')}: Falta competencias_associadas")
    
    return issues

def verify_ei_structure(data):
    """Verifica estrutura do EI em detalhes"""
    issues = []
    
    # Verifica faixas (usando códigos EI01/EI02/EI03)
    faixas_esperadas = ["EI01", "EI02", "EI03"]  # Bebês, Crianças bem pequenas, Crianças pequenas
    faixas = list(data.get('objetivos_aprendizagem', {}).keys())
    
    for f in faixas_esperadas:
        if f not in faixas:
            issues.append(f"⚠️ Falta faixa: {f}")
    
    # Verifica campos de experiência (5 campos: EO, CG, TS, EF, ET)
    campos_esperados = 5
    for faixa, campos in data.get('objetivos_aprendizagem', {}).items():
        if len(campos) < campos_esperados:
            issues.append(f"⚠️ {faixa}: Apenas {len(campos)} campos (esperado: {campos_esperados})")
    
    # Verifica síntese
    sintese = data.get('sintese_aprendizagens', {})
    if not sintese:
        issues.append("❌ Falta síntese de aprendizagens")
    elif len(sintese) < 5:
        issues.append(f"⚠️ Síntese com apenas {len(sintese)} campos")
    
    # Direitos de aprendizagem são opcionais (estão em metadata ou extrair_bncc.py)
    # Não reportar como erro se ausentes
    
    return issues

# ============================================================================
# MAIN AUDIT FUNCTION
# ============================================================================

def run_audit():
    print("=" * 80)
    print("AUDITORIA COMPLETA - BNCC JSON vs PDF Original")
    print("=" * 80)
    
    pdf_path = 'BNCC_EI_EF_110518_versaofinal_site.pdf'
    pdf = pdfplumber.open(pdf_path)
    
    # ========================================================================
    # 1. CONTAGENS
    # ========================================================================
    print("\n" + "=" * 60)
    print("1. VERIFICAÇÃO DE CONTAGENS")
    print("=" * 60)
    
    # EF
    ef_data = load_json('bncc_ef.json')
    ef_counts = count_ef_skills(ef_data)
    
    print("\n--- ENSINO FUNDAMENTAL ---")
    print(f"{'Componente':<15} {'Extraído':<10} {'Esperado':<10} {'Status'}")
    print("-" * 50)
    
    total_ef = 0
    for sigla, expected in EXPECTED_COUNTS['EF'].items():
        if sigla == 'total_codes':
            continue
        extracted = len(ef_counts[sigla]['unique'])
        total_ef += extracted
        status = "✅" if extracted == expected else f"❌ (diff: {extracted - expected})"
        print(f"{sigla:<15} {extracted:<10} {expected:<10} {status}")
    
    print("-" * 50)
    expected_total = EXPECTED_COUNTS['EF']['total_codes']
    status = "✅" if total_ef == expected_total else f"❌ (diff: {total_ef - expected_total})"
    print(f"{'TOTAL':<15} {total_ef:<10} {expected_total:<10} {status}")
    
    # EM
    em_data = load_json('bncc_em.json')
    em_counts = count_em_skills(em_data)
    
    print("\n--- ENSINO MÉDIO ---")
    print(f"{'Área/Comp':<15} {'Extraído':<10} {'Esperado':<10} {'Status'}")
    print("-" * 50)
    
    total_em = 0
    for sigla in ['LGG', 'LP', 'MAT', 'CNT', 'CHS']:
        extracted = em_counts[sigla]
        expected = EXPECTED_COUNTS['EM'][sigla]
        total_em += extracted
        status = "✅" if extracted == expected else f"❌ (diff: {extracted - expected})"
        print(f"{sigla:<15} {extracted:<10} {expected:<10} {status}")
    
    print("-" * 50)
    expected_total = EXPECTED_COUNTS['EM']['total']
    status = "✅" if total_em == expected_total else f"❌ (diff: {total_em - expected_total})"
    print(f"{'TOTAL':<15} {total_em:<10} {expected_total:<10} {status}")
    
    # EI
    ei_data = load_json('bncc_ei.json')
    ei_counts = count_ei_items(ei_data)
    
    print("\n--- EDUCAÇÃO INFANTIL ---")
    print(f"{'Item':<20} {'Extraído':<10} {'Esperado':<10} {'Status'}")
    print("-" * 50)
    
    for item in ['objetivos', 'sintese']:
        extracted = ei_counts[item]
        expected = EXPECTED_COUNTS['EI'][item]
        status = "✅" if extracted == expected else f"❌ (diff: {extracted - expected})"
        print(f"{item:<20} {extracted:<10} {expected:<10} {status}")
    
    # ========================================================================
    # 2. VERIFICAÇÃO DE ESTRUTURA
    # ========================================================================
    print("\n" + "=" * 60)
    print("2. VERIFICAÇÃO DE ESTRUTURA")
    print("=" * 60)
    
    print("\n--- ENSINO FUNDAMENTAL ---")
    ef_issues = verify_ef_structure(ef_data)
    if ef_issues:
        for issue in ef_issues[:10]:
            print(f"  {issue}")
        if len(ef_issues) > 10:
            print(f"  ... e mais {len(ef_issues) - 10} problemas")
    else:
        print("  ✅ Estrutura OK")
    
    print("\n--- ENSINO MÉDIO ---")
    em_issues = verify_em_structure(em_data)
    if em_issues:
        for issue in em_issues[:10]:
            print(f"  {issue}")
    else:
        print("  ✅ Estrutura OK")
    
    print("\n--- EDUCAÇÃO INFANTIL ---")
    ei_issues = verify_ei_structure(ei_data)
    if ei_issues:
        for issue in ei_issues:
            print(f"  {issue}")
    else:
        print("  ✅ Estrutura OK")
    
    # ========================================================================
    # 3. AMOSTRAGEM DE CONTEÚDO
    # ========================================================================
    print("\n" + "=" * 60)
    print("3. VERIFICAÇÃO DE CONTEÚDO (Amostragem)")
    print("=" * 60)
    
    # EF
    print("\n--- ENSINO FUNDAMENTAL ---")
    ef_skills = sample_ef_skills(ef_data, sample_size=100)
    print(f"  Amostra: {len(ef_skills)} habilidades")
    
    ef_results = defaultdict(list)
    for skill in ef_skills:
        result = verify_skill(pdf, skill, range(60, 500))
        ef_results[result['status']].append(result)
    
    print(f"  ✅ MATCH:     {len(ef_results['MATCH'])} ({100*len(ef_results['MATCH'])/len(ef_skills):.1f}%)")
    print(f"  ⚠️  MISMATCH:  {len(ef_results['MISMATCH'])} ({100*len(ef_results['MISMATCH'])/len(ef_skills):.1f}%)")
    print(f"  ❌ NOT_FOUND: {len(ef_results['NOT_FOUND'])} ({100*len(ef_results['NOT_FOUND'])/len(ef_skills):.1f}%)")
    
    # EM
    print("\n--- ENSINO MÉDIO ---")
    em_skills = sample_em_skills(em_data, sample_size=50)
    print(f"  Amostra: {len(em_skills)} habilidades")
    
    em_results = defaultdict(list)
    for skill in em_skills:
        result = verify_skill(pdf, skill, range(480, 600))
        em_results[result['status']].append(result)
    
    print(f"  ✅ MATCH:     {len(em_results['MATCH'])} ({100*len(em_results['MATCH'])/len(em_skills):.1f}%)")
    print(f"  ⚠️  MISMATCH:  {len(em_results['MISMATCH'])} ({100*len(em_results['MISMATCH'])/len(em_skills):.1f}%)")
    print(f"  ❌ NOT_FOUND: {len(em_results['NOT_FOUND'])} ({100*len(em_results['NOT_FOUND'])/len(em_skills):.1f}%)")
    
    # EI
    print("\n--- EDUCAÇÃO INFANTIL ---")
    ei_skills = sample_ei_skills(ei_data, sample_size=30)
    print(f"  Amostra: {len(ei_skills)} objetivos")
    
    ei_results = defaultdict(list)
    for skill in ei_skills:
        result = verify_skill(pdf, skill, range(35, 60))
        ei_results[result['status']].append(result)
    
    print(f"  ✅ MATCH:     {len(ei_results['MATCH'])} ({100*len(ei_results['MATCH'])/len(ei_skills):.1f}%)")
    print(f"  ⚠️  MISMATCH:  {len(ei_results['MISMATCH'])} ({100*len(ei_results['MISMATCH'])/len(ei_skills):.1f}%)")
    print(f"  ❌ NOT_FOUND: {len(ei_results['NOT_FOUND'])} ({100*len(ei_results['NOT_FOUND'])/len(ei_skills):.1f}%)")
    
    # ========================================================================
    # 4. EXEMPLOS DETALHADOS
    # ========================================================================
    print("\n" + "=" * 60)
    print("4. EXEMPLOS DETALHADOS")
    print("=" * 60)
    
    print("\n--- EXEMPLOS EF (3 amostras) ---")
    for r in random.sample(ef_results['MATCH'], min(3, len(ef_results['MATCH']))):
        skill = r['skill']
        print(f"\n  {r['code']} (pág {r['page']}, score: {r['match_score']:.2f})")
        print(f"    Área: {skill.get('area', '')}")
        print(f"    Componente: {skill.get('componente', '')}")
        print(f"    Ano: {skill.get('ano', '')}")
        print(f"    Unidade: {skill.get('unidade', '')[:50]}")
        print(f"    PDF: \"{r['pdf_excerpt']}...\"")
        print(f"    JSON: \"{r['json_excerpt']}...\"")
    
    print("\n--- EXEMPLOS EM (3 amostras) ---")
    for r in random.sample(em_results['MATCH'], min(3, len(em_results['MATCH']))):
        skill = r['skill']
        print(f"\n  {r['code']} (pág {r['page']}, score: {r['match_score']:.2f})")
        if skill.get('tipo') == 'LP':
            print(f"    Componente: LP")
            print(f"    Campo: {skill.get('campo', '')[:40]}")
            print(f"    Competências: {skill.get('competencias_associadas', [])}")
        else:
            print(f"    Área: {skill.get('area', '')[:40]}")
            print(f"    Competência: CE{skill.get('competencia', '')}")
        print(f"    PDF: \"{r['pdf_excerpt']}...\"")
        print(f"    JSON: \"{r['json_excerpt']}...\"")
    
    # ========================================================================
    # 5. PROBLEMAS ENCONTRADOS
    # ========================================================================
    all_issues = []
    
    # Mismatches
    for r in ef_results['MISMATCH'][:3]:
        all_issues.append(f"EF MISMATCH: {r['code']} - PDF: \"{r['pdf_excerpt'][:30]}\" vs JSON: \"{r['json_excerpt'][:30]}\"")
    for r in em_results['MISMATCH'][:3]:
        all_issues.append(f"EM MISMATCH: {r['code']} - PDF: \"{r['pdf_excerpt'][:30]}\" vs JSON: \"{r['json_excerpt'][:30]}\"")
    
    # Not found
    for r in ef_results['NOT_FOUND'][:3]:
        all_issues.append(f"EF NOT_FOUND: {r['code']}")
    for r in em_results['NOT_FOUND'][:3]:
        all_issues.append(f"EM NOT_FOUND: {r['code']}")
    
    if all_issues:
        print("\n" + "=" * 60)
        print("5. PROBLEMAS ENCONTRADOS")
        print("=" * 60)
        for issue in all_issues:
            print(f"  ⚠️  {issue}")
    
    # ========================================================================
    # RESUMO FINAL
    # ========================================================================
    print("\n" + "=" * 80)
    print("RESUMO FINAL")
    print("=" * 80)
    
    # Scores
    ef_score = len(ef_results['MATCH']) / len(ef_skills) * 100 if ef_skills else 0
    em_score = len(em_results['MATCH']) / len(em_skills) * 100 if em_skills else 0
    ei_score = len(ei_results['MATCH']) / len(ei_skills) * 100 if ei_skills else 0
    
    # Count checks
    ef_count_ok = total_ef == EXPECTED_COUNTS['EF']['total_codes']
    em_count_ok = total_em == EXPECTED_COUNTS['EM']['total']
    ei_count_ok = ei_counts['objetivos'] == EXPECTED_COUNTS['EI']['objetivos']
    
    print(f"""
  ┌─────────────────────────────────────────────────────────────┐
  │ BNCC JSON Audit Results                                     │
  ├─────────────────────────────────────────────────────────────┤
  │ Ensino Fundamental (EF)                                     │
  │   Contagem: {total_ef} códigos {'✅' if ef_count_ok else '❌'}                                   │
  │   Conteúdo: {ef_score:.1f}% match                                       │
  │   Estrutura: {len(ef_issues)} problemas                                     │
  ├─────────────────────────────────────────────────────────────┤
  │ Ensino Médio (EM)                                           │
  │   Contagem: {total_em} códigos {'✅' if em_count_ok else '❌'}                                    │
  │   Conteúdo: {em_score:.1f}% match                                       │
  │   Estrutura: {len(em_issues)} problemas                                      │
  ├─────────────────────────────────────────────────────────────┤
  │ Educação Infantil (EI)                                      │
  │   Contagem: {ei_counts['objetivos']} objetivos {'✅' if ei_count_ok else '❌'}                                  │
  │   Conteúdo: {ei_score:.1f}% match                                       │
  │   Estrutura: {len(ei_issues)} problemas                                      │
  └─────────────────────────────────────────────────────────────┘
    """)
    
    pdf.close()
    
    print("=" * 80)
    print("AUDITORIA CONCLUÍDA")
    print("=" * 80)

if __name__ == "__main__":
    run_audit()
