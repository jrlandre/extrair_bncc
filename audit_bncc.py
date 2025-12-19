#!/usr/bin/env python3
"""
AUDITORIA MASSIVA - Verificação BNCC JSON vs PDF Original
Compara dados extraídos em todos os níveis hierárquicos com o PDF fonte.
"""

import json
import pdfplumber
import re
import random
from collections import defaultdict

# Regex para códigos
RE_CODE_EF = re.compile(r'\(?(EF\d{2}[A-Z]{2}\d{2})\)?')
RE_CODE_EI = re.compile(r'(EI\d{2}[A-Z]{2}\d{2})')

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
            # Encontra o contexto ao redor do código
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
    # Remove o código e pega o texto seguinte
    idx = context.find(code)
    if idx >= 0:
        desc_start = idx + len(code)
        desc = context[desc_start:].strip()
        # Limpa caracteres iniciais
        desc = re.sub(r'^[)\s]+', '', desc)
        return desc[:100]  # Primeiros 100 chars
    return ""

def sample_ef_skills(data, sample_size=100):
    """Amostra habilidades do EF com hierarquia completa"""
    skills = []
    for area, area_data in data.items():
        if area == "metadata":
            continue
        for comp, comp_data in area_data.get('componentes', {}).items():
            for ano, ano_data in comp_data.get('anos', {}).items():
                for unidade, grupos in ano_data.items():
                    if isinstance(grupos, list):
                        for grupo in grupos:
                            for obj in grupo.get('objetos', []):
                                for hab in grupo.get('habilidades', []):
                                    skills.append({
                                        'codigo': hab['codigo'],
                                        'descricao': hab['descricao'],
                                        'area': area,
                                        'componente': comp,
                                        'ano': ano,
                                        'unidade': unidade,
                                        'objeto': obj
                                    })
    
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

def verify_skill(pdf, skill, page_range, is_ef=True):
    """Verifica uma habilidade contra o PDF"""
    code = skill['codigo']
    result = find_code_in_pdf(pdf, code, page_range)
    
    if not result['found']:
        return {
            'status': 'NOT_FOUND',
            'code': code,
            'message': f'Código {code} não encontrado no PDF'
        }
    
    # Extrai descrição do PDF para comparação
    pdf_desc = extract_description_from_context(result['context'], code)
    json_desc = skill['descricao'][:100]
    
    # Normaliza para comparação
    pdf_norm = re.sub(r'\s+', ' ', pdf_desc.lower().strip())
    json_norm = re.sub(r'\s+', ' ', json_desc.lower().strip())
    
    # Verifica se as primeiras palavras coincidem
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
        'hierarchy': skill.get('area', skill.get('faixa', '')) + ' > ' + 
                    skill.get('componente', skill.get('campo', '')) + ' > ' +
                    skill.get('ano', '') + ' > ' +
                    skill.get('unidade', '')[:30] + ' > ' +
                    skill.get('objeto', '')[:30]
    }

def run_audit():
    print("=" * 80)
    print("AUDITORIA MASSIVA - BNCC JSON vs PDF Original")
    print("=" * 80)
    
    pdf_path = 'BNCC_EI_EF_110518_versaofinal_site.pdf'
    pdf = pdfplumber.open(pdf_path)
    
    # ========================
    # AUDITORIA ENSINO FUNDAMENTAL
    # ========================
    print("\n" + "=" * 40)
    print("ENSINO FUNDAMENTAL (bncc_ef.json)")
    print("=" * 40)
    
    ef_data = load_json('bncc_ef.json')
    ef_skills = sample_ef_skills(ef_data, sample_size=150)
    
    print(f"\nAmostra: {len(ef_skills)} habilidades")
    
    ef_results = defaultdict(list)
    for i, skill in enumerate(ef_skills):
        result = verify_skill(pdf, skill, range(60, 500), is_ef=True)
        ef_results[result['status']].append(result)
        
        if (i + 1) % 25 == 0:
            print(f"  Processado: {i+1}/{len(ef_skills)}")
    
    print(f"\n--- RESULTADOS EF ---")
    print(f"  ✅ MATCH:     {len(ef_results['MATCH'])} ({100*len(ef_results['MATCH'])/len(ef_skills):.1f}%)")
    print(f"  ⚠️ MISMATCH:  {len(ef_results['MISMATCH'])} ({100*len(ef_results['MISMATCH'])/len(ef_skills):.1f}%)")
    print(f"  ❌ NOT_FOUND: {len(ef_results['NOT_FOUND'])} ({100*len(ef_results['NOT_FOUND'])/len(ef_skills):.1f}%)")
    
    # Mostra exemplos detalhados
    print("\n--- EXEMPLOS DE MATCH (5 amostras) ---")
    for r in random.sample(ef_results['MATCH'], min(5, len(ef_results['MATCH']))):
        print(f"\n  {r['code']} (pág {r['page']}, score: {r['match_score']:.2f})")
        print(f"    Hierarquia: {r['hierarchy']}")
        print(f"    PDF: \"{r['pdf_excerpt']}...\"")
        print(f"    JSON: \"{r['json_excerpt']}...\"")
    
    if ef_results['MISMATCH']:
        print("\n--- EXEMPLOS DE MISMATCH (até 5) ---")
        for r in ef_results['MISMATCH'][:5]:
            print(f"\n  ⚠️ {r['code']} (pág {r['page']}, score: {r['match_score']:.2f})")
            print(f"    Hierarquia: {r['hierarchy']}")
            print(f"    PDF: \"{r['pdf_excerpt']}...\"")
            print(f"    JSON: \"{r['json_excerpt']}...\"")
    
    if ef_results['NOT_FOUND']:
        print("\n--- CÓDIGOS NÃO ENCONTRADOS (até 10) ---")
        for r in ef_results['NOT_FOUND'][:10]:
            print(f"  ❌ {r['code']}")
    
    # ========================
    # AUDITORIA EDUCAÇÃO INFANTIL
    # ========================
    print("\n" + "=" * 40)
    print("EDUCAÇÃO INFANTIL (bncc_ei.json)")
    print("=" * 40)
    
    ei_data = load_json('bncc_ei.json')
    ei_skills = sample_ei_skills(ei_data, sample_size=50)
    
    print(f"\nAmostra: {len(ei_skills)} objetivos")
    
    ei_results = defaultdict(list)
    for i, skill in enumerate(ei_skills):
        result = verify_skill(pdf, skill, range(35, 60), is_ef=False)
        ei_results[result['status']].append(result)
    
    print(f"\n--- RESULTADOS EI ---")
    print(f"  ✅ MATCH:     {len(ei_results['MATCH'])} ({100*len(ei_results['MATCH'])/len(ei_skills):.1f}%)")
    print(f"  ⚠️ MISMATCH:  {len(ei_results['MISMATCH'])} ({100*len(ei_results['MISMATCH'])/len(ei_skills):.1f}%)")
    print(f"  ❌ NOT_FOUND: {len(ei_results['NOT_FOUND'])} ({100*len(ei_results['NOT_FOUND'])/len(ei_skills):.1f}%)")
    
    print("\n--- EXEMPLOS DE MATCH EI (5 amostras) ---")
    for r in random.sample(ei_results['MATCH'], min(5, len(ei_results['MATCH']))):
        print(f"\n  {r['code']} (pág {r['page']}, score: {r['match_score']:.2f})")
        print(f"    Hierarquia: {r['hierarchy']}")
        print(f"    PDF: \"{r['pdf_excerpt']}...\"")
        print(f"    JSON: \"{r['json_excerpt']}...\"")
    
    # ========================
    # VERIFICAÇÃO DE HIERARQUIA
    # ========================
    print("\n" + "=" * 40)
    print("VERIFICAÇÃO DE HIERARQUIA")
    print("=" * 40)
    
    # Verifica estrutura de áreas e componentes
    print("\n--- Estrutura EF ---")
    for area in ef_data:
        if area == "metadata":
            continue
        comps = list(ef_data[area].get('componentes', {}).keys())
        print(f"  {area}: {comps}")
    
    print("\n--- Estrutura EI ---")
    print(f"  Faixas: {list(ei_data.get('objetivos_aprendizagem', {}).keys())}")
    print(f"  Campos: {list(ei_data.get('metadata', {}).get('campos_experiencia', []))}")
    
    # ========================
    # CONTAGENS FINAIS
    # ========================
    print("\n" + "=" * 40)
    print("CONTAGENS FINAIS")
    print("=" * 40)
    
    # EF
    total_ef_skills = 0
    unique_codes_ef = set()
    for area in ef_data.values():
        if isinstance(area, dict) and 'componentes' in area:
            for comp in area['componentes'].values():
                for ano in comp.get('anos', {}).values():
                    for grupos in ano.values():
                        if isinstance(grupos, list):
                            for g in grupos:
                                for h in g.get('habilidades', []):
                                    total_ef_skills += 1
                                    unique_codes_ef.add(h['codigo'])
    
    print(f"\n  EF:")
    print(f"    Total habilidades: {total_ef_skills}")
    print(f"    Códigos únicos: {len(unique_codes_ef)}")
    
    # EI
    total_ei = 0
    for faixa in ei_data.get('objetivos_aprendizagem', {}).values():
        for campo in faixa.values():
            total_ei += len(campo)
    
    print(f"\n  EI:")
    print(f"    Total objetivos: {total_ei}")
    
    # Síntese
    total_sintese = sum(len(v) for v in ei_data.get('sintese_aprendizagens', {}).values())
    print(f"    Síntese itens: {total_sintese}")
    
    pdf.close()
    
    print("\n" + "=" * 80)
    print("AUDITORIA CONCLUÍDA")
    print("=" * 80)

if __name__ == "__main__":
    run_audit()
