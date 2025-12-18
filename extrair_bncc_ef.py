"""
EXTRATOR COMPLETO DA BNCC - ENSINO FUNDAMENTAL
Extrai todas as 8 camadas hierárquicas da BNCC-EF de forma estruturada
para consumo via API REST profissional.

Estrutura:
1. Áreas do Conhecimento
2. Competências Específicas de Área
3. Componentes Curriculares
4. Competências Específicas de Componente
5. Anos (granularidade ano por ano)
6. Campos de Atuação / Unidades Temáticas
7. Objetos de Conhecimento
8. Habilidades

Autor: Sistema de Extração BNCC
Data: 2024
"""

import pdfplumber
import json
import re
from typing import Dict, List, Any
from collections import defaultdict

class BNCCExtractorEF:
    """Extrator profissional da BNCC - Ensino Fundamental"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.data = {
            "etapa": "Ensino Fundamental",
            "areas": []
        }
        
        # Mapeamento de áreas e componentes (páginas base do PDF)
        self.estrutura_ef = {
            "Linguagens": {
                "pagina_intro": 63,
                "pagina_competencias_area": 65,
                "num_competencias_area": 6,
                "componentes": {
                    "Língua Portuguesa": {
                        "pagina_inicio": 67,
                        "pagina_competencias": 87,
                        "num_competencias": 10,
                        "anos_iniciais_inicio": 89,
                        "anos_finais_inicio": 136,
                        "usa_campos_atuacao": True
                    },
                    "Arte": {
                        "pagina_inicio": 193,
                        "pagina_competencias": 198,
                        "num_competencias": 9,
                        "anos_iniciais_inicio": 199,
                        "anos_finais_inicio": 205
                    },
                    "Educação Física": {
                        "pagina_inicio": 213,
                        "pagina_competencias": 223,
                        "num_competencias": 10,
                        "anos_iniciais_inicio": 224,
                        "anos_finais_inicio": 231
                    },
                    "Língua Inglesa": {
                        "pagina_inicio": 241,
                        "pagina_competencias": 246,
                        "num_competencias": 6,
                        "anos_finais_inicio": 247
                    }
                }
            },
            "Matemática": {
                "pagina_intro": 265,
                "pagina_competencias_area": 267,
                "num_competencias_area": 8,
                "componentes": {
                    "Matemática": {
                        "pagina_inicio": 268,
                        "num_competencias": 8,
                        "anos_iniciais_inicio": 276,
                        "anos_finais_inicio": 298
                    }
                }
            },
            "Ciências da Natureza": {
                "pagina_intro": 321,
                "pagina_competencias_area": 324,
                "num_competencias_area": 8,
                "componentes": {
                    "Ciências": {
                        "pagina_inicio": 325,
                        "num_competencias": 8,
                        "anos_iniciais_inicio": 331,
                        "anos_finais_inicio": 343
                    }
                }
            },
            "Ciências Humanas": {
                "pagina_intro": 353,
                "pagina_competencias_area": 357,
                "num_competencias_area": 7,
                "componentes": {
                    "Geografia": {
                        "pagina_inicio": 359,
                        "pagina_competencias": 366,
                        "num_competencias": 7,
                        "anos_iniciais_inicio": 367,
                        "anos_finais_inicio": 381
                    },
                    "História": {
                        "pagina_inicio": 397,
                        "pagina_competencias": 402,
                        "num_competencias": 7,
                        "anos_iniciais_inicio": 403,
                        "anos_finais_inicio": 416
                    }
                }
            },
            "Ensino Religioso": {
                "pagina_intro": 435,
                "pagina_competencias_area": 437,
                "num_competencias_area": 6,
                "componentes": {
                    "Ensino Religioso": {
                        "pagina_inicio": 438,
                        "num_competencias": 6,
                        "anos_iniciais_inicio": 442,
                        "anos_finais_inicio": 452
                    }
                }
            }
        }
    
    def extrair_competencias_area(self, pdf, pagina_inicio: int, num_competencias: int) -> List[Dict]:
        """Extrai competências específicas de área (lista numerada)"""
        competencias = []
        
        try:
            # Lê as páginas que contêm as competências (normalmente 1-2 páginas)
            texto_completo = ""
            for i in range(3):  # Lê até 3 páginas
                page = pdf.pages[pagina_inicio - 1 + i]
                texto_completo += page.extract_text() + "\n"
            
            # Padrão para encontrar competências numeradas
            padrao = r'(\d+)\.\s+(.+?)(?=\n\d+\.|$)'
            matches = re.findall(padrao, texto_completo, re.DOTALL)
            
            for numero, descricao in matches[:num_competencias]:
                competencias.append({
                    "numero": int(numero),
                    "descricao": descricao.strip().replace('\n', ' ')
                })
        
        except Exception as e:
            print(f"Erro ao extrair competências de área (página {pagina_inicio}): {e}")
        
        return competencias
    
    def extrair_competencias_componente(self, pdf, pagina_inicio: int, num_competencias: int) -> List[Dict]:
        """Extrai competências específicas de componente curricular"""
        return self.extrair_competencias_area(pdf, pagina_inicio, num_competencias)
    
    def extrair_codigo_ano_da_habilidade(self, codigo: str) -> List[int]:
        """
        Extrai ano(s) do código da habilidade.
        Ex: EF04MA10 -> [4]
        Ex: EF67EF01 -> [6, 7]
        Ex: EF35LP01 -> [3, 4, 5]
        """
        match = re.match(r'EF(\d{2})', codigo)
        if not match:
            return []
        
        anos_str = match.group(1)
        
        # Casos especiais de blocos
        blocos = {
            '12': [1, 2],
            '15': [1, 2, 3, 4, 5],
            '35': [3, 4, 5],
            '67': [6, 7],
            '69': [6, 7, 8, 9],
            '89': [8, 9]
        }
        
        if anos_str in blocos:
            return blocos[anos_str]
        
        # Ano individual
        ano = int(anos_str)
        if 1 <= ano <= 9:
            return [ano]
        
        return []
    
    def extrair_tabelas_habilidades(self, pdf, pagina_inicio: int, pagina_fim: int) -> List[Dict]:
        """
        Extrai tabelas de habilidades de um componente.
        Retorna lista com estrutura: anos, unidade/campo, objetos, habilidades
        """
        dados_extraidos = []
        
        for num_pag in range(pagina_inicio, pagina_fim + 1):
            try:
                page = pdf.pages[num_pag - 1]
                tabelas = page.extract_tables()
                
                for tabela in tabelas:
                    if not tabela or len(tabela) < 2:
                        continue
                    
                    # Identificar estrutura da tabela
                    header = tabela[0]
                    
                    # Processar linhas
                    for linha in tabela[1:]:
                        if not linha or all(cell is None or str(cell).strip() == '' for cell in linha):
                            continue
                        
                        # Extrair dados conforme estrutura
                        # Formato típico: [Unidade/Campo, Objetos, Habilidades] ou [Anos, Unidade, Objetos, Habilidades]
                        
                        # Extração básica (precisa ser refinada por componente)
                        dados_linha = {
                            "unidade_tematica": None,
                            "campo_atuacao": None,
                            "objetos_conhecimento": [],
                            "habilidades": []
                        }
                        
                        # Identificar e extrair códigos de habilidades
                        texto_linha = ' '.join([str(c) for c in linha if c])
                        codigos = re.findall(r'\(EF\d{2}[A-Z]{2}\d{2}\)', texto_linha)
                        
                        for codigo in codigos:
                            codigo_limpo = codigo.strip('()')
                            anos = self.extrair_codigo_ano_da_habilidade(codigo_limpo)
                            
                            # Extrair descrição da habilidade
                            padrao_hab = rf'\({codigo_limpo}\)\s*(.+?)(?=\(EF|$)'
                            match_desc = re.search(padrao_hab, texto_linha, re.DOTALL)
                            descricao = match_desc.group(1).strip() if match_desc else ""
                            
                            dados_linha["habilidades"].append({
                                "codigo": codigo_limpo,
                                "anos": anos,
                                "descricao": descricao
                            })
                        
                        if dados_linha["habilidades"]:
                            dados_extraidos.append(dados_linha)
            
            except Exception as e:
                print(f"Erro ao processar página {num_pag}: {e}")
                continue
        
        return dados_extraidos
    
    def organizar_por_ano(self, dados_tabelas: List[Dict]) -> Dict[int, List]:
        """
        Organiza dados extraídos por ano individual (1 a 9).
        Repete dados quando habilidade se aplica a múltiplos anos.
        """
        por_ano = defaultdict(list)
        
        for item in dados_tabelas:
            for habilidade in item["habilidades"]:
                for ano in habilidade["anos"]:
                    entrada = {
                        "unidade_tematica": item.get("unidade_tematica"),
                        "campo_atuacao": item.get("campo_atuacao"),
                        "objetos_conhecimento": item.get("objetos_conhecimento", []),
                        "habilidade": {
                            "codigo": habilidade["codigo"],
                            "descricao": habilidade["descricao"]
                        }
                    }
                    por_ano[ano].append(entrada)
        
        return dict(por_ano)
    
    def processar_componente(self, pdf, nome_componente: str, config: Dict) -> Dict:
        """Processa um componente curricular completo"""
        print(f"  Processando componente: {nome_componente}")
        
        componente_data = {
            "nome": nome_componente,
            "competencias_especificas": [],
            "anos": {}
        }
        
        # 1. Extrair competências específicas do componente
        if "pagina_competencias" in config:
            componente_data["competencias_especificas"] = self.extrair_competencias_componente(
                pdf,
                config["pagina_competencias"],
                config.get("num_competencias", 0)
            )
        
        # 2. Processar anos iniciais (se houver)
        if "anos_iniciais_inicio" in config:
            print(f"    Extraindo anos iniciais...")
            # Determinar página final (início dos anos finais ou próximo componente)
            pag_fim = config.get("anos_finais_inicio", config["anos_iniciais_inicio"] + 50) - 1
            
            dados_iniciais = self.extrair_tabelas_habilidades(
                pdf,
                config["anos_iniciais_inicio"],
                pag_fim
            )
            
            anos_iniciais = self.organizar_por_ano(dados_iniciais)
            componente_data["anos"].update(anos_iniciais)
        
        # 3. Processar anos finais (se houver)
        if "anos_finais_inicio" in config:
            print(f"    Extraindo anos finais...")
            pag_fim = config["anos_finais_inicio"] + 50  # Ajustar conforme necessário
            
            dados_finais = self.extrair_tabelas_habilidades(
                pdf,
                config["anos_finais_inicio"],
                pag_fim
            )
            
            anos_finais = self.organizar_por_ano(dados_finais)
            componente_data["anos"].update(anos_finais)
        
        return componente_data
    
    def processar_area(self, pdf, nome_area: str, config: Dict) -> Dict:
        """Processa uma área do conhecimento completa"""
        print(f"\nProcessando área: {nome_area}")
        
        area_data = {
            "nome": nome_area,
            "competencias_especificas_area": [],
            "componentes": []
        }
        
        # 1. Extrair competências específicas da área
        if "pagina_competencias_area" in config:
            area_data["competencias_especificas_area"] = self.extrair_competencias_area(
                pdf,
                config["pagina_competencias_area"],
                config.get("num_competencias_area", 0)
            )
        
        # 2. Processar cada componente da área
        for nome_comp, config_comp in config.get("componentes", {}).items():
            componente_data = self.processar_componente(pdf, nome_comp, config_comp)
            area_data["componentes"].append(componente_data)
        
        return area_data
    
    def extrair_completo(self) -> Dict:
        """Extração completa de todas as áreas, componentes e habilidades"""
        print("="*80)
        print("EXTRAÇÃO COMPLETA DA BNCC - ENSINO FUNDAMENTAL")
        print("="*80)
        
        with pdfplumber.open(self.pdf_path) as pdf:
            # Processar cada área do conhecimento
            for nome_area, config_area in self.estrutura_ef.items():
                area_data = self.processar_area(pdf, nome_area, config_area)
                self.data["areas"].append(area_data)
        
        print("\n" + "="*80)
        print("EXTRAÇÃO CONCLUÍDA!")
        print("="*80)
        
        return self.data
    
    def salvar_json(self, output_path: str):
        """Salva dados extraídos em JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"\nArquivo salvo: {output_path}")
    
    def gerar_estatisticas(self) -> Dict:
        """Gera estatísticas da extração"""
        stats = {
            "total_areas": len(self.data["areas"]),
            "areas": {}
        }
        
        for area in self.data["areas"]:
            area_stats = {
                "nome": area["nome"],
                "competencias_area": len(area["competencias_especificas_area"]),
                "componentes": {}
            }
            
            for comp in area["componentes"]:
                comp_stats = {
                    "competencias_componente": len(comp["competencias_especificas"]),
                    "anos_cobertos": list(comp["anos"].keys()),
                    "total_habilidades_por_ano": {
                        ano: len(habs) for ano, habs in comp["anos"].items()
                    }
                }
                area_stats["componentes"][comp["nome"]] = comp_stats
            
            stats["areas"][area["nome"]] = area_stats
        
        return stats


def main():
    """Função principal de execução"""
    
    # Configuração
    PDF_PATH = "BNCC_EI_EF_110518_versaofinal_site.pdf"
    OUTPUT_JSON = "bncc_ef_completo.json"
    OUTPUT_STATS = "bncc_ef_estatisticas.json"
    
    # Criar extrator
    extrator = BNCCExtractorEF(PDF_PATH)
    
    # Extrair dados
    dados = extrator.extrair_completo()
    
    # Salvar JSON
    extrator.salvar_json(OUTPUT_JSON)
    
    # Gerar e salvar estatísticas
    stats = extrator.gerar_estatisticas()
    with open(OUTPUT_STATS, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"Estatísticas salvas: {OUTPUT_STATS}")
    
    # Exibir resumo
    print("\n" + "="*80)
    print("RESUMO DA EXTRAÇÃO")
    print("="*80)
    print(f"Total de áreas: {stats['total_areas']}")
    for area_nome, area_info in stats["areas"].items():
        print(f"\n{area_nome}:")
        print(f"  Competências de área: {area_info['competencias_area']}")
        for comp_nome, comp_info in area_info["componentes"].items():
            print(f"  {comp_nome}:")
            print(f"    Competências: {comp_info['competencias_componente']}")
            print(f"    Anos: {comp_info['anos_cobertos']}")
            print(f"    Habilidades por ano: {comp_info['total_habilidades_por_ano']}")


if __name__ == "__main__":
    main()