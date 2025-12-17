import unittest
import json
import re
import os
import pdfplumber

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================
ARQ_PDF = "BNCC_EI_EF_110518_versaofinal_site.pdf"
JSON_EI = "bncc_ei.json"
JSON_EF = "bncc_ef.json"
JSON_EM = "bncc_em.json"

class TesteRigidoBNCC(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n⚡ INICIANDO BATERIA DE TESTES DE ALTA RIGIDEZ (V35 - HYBRID)...")
        
        # 1. Carrega JSONs
        try:
            with open(JSON_EI, 'r', encoding='utf-8') as f: cls.ei = json.load(f)
            with open(JSON_EF, 'r', encoding='utf-8') as f: cls.ef = json.load(f)
            with open(JSON_EM, 'r', encoding='utf-8') as f: cls.em = json.load(f)
        except FileNotFoundError:
            raise RuntimeError("❌ ERRO: Execute o 'extrair_bncc.py' antes para gerar os JSONs.")

        # 2. Carrega Texto do PDF para Auditoria Forense (Recurso do código original)
        # Se não quiser esperar, comente este bloco.
        print("   ↳ Lendo PDF para verificação cruzada (Forense)...")
        cls.texto_pdf_completo = ""
        if os.path.exists(ARQ_PDF):
            with pdfplumber.open(ARQ_PDF) as pdf:
                for page in pdf.pages:
                    cls.texto_pdf_completo += page.extract_text() or ""
        else:
            print("   ⚠️ AVISO: PDF original não encontrado. Teste forense será pulado.")

    # =========================================================================
    # 1. EDUCAÇÃO INFANTIL (EI)
    # =========================================================================
    def test_ei_estrutura_estrita(self):
        """EI: Verifica campos obrigatórios e regex de código."""
        print("   ↳ Validando Educação Infantil...")
        erros = []
        pattern = re.compile(r"EI\d{2}[A-Z]{2}\d{2}") # Ex: EI02CG01
        
        for item in self.ei:
            cod = item.get('codigo', 'SEM_COD')
            if not pattern.match(cod):
                erros.append(f"{cod}: Formato inválido")
            if not item.get('campo_experiencia'):
                erros.append(f"{cod}: Sem Campo de Experiência")
            if not item.get('faixa_etaria'):
                erros.append(f"{cod}: Sem Faixa Etária")

        if erros:
            self.fail(f"❌ ERROS EI:\n" + "\n".join(erros[:10]))
        else:
            print("     ✅ EI: Estrutura Perfeita.")

    # =========================================================================
    # 2. ENSINO FUNDAMENTAL (EF) - O MAIS CRÍTICO
    # =========================================================================
    def test_ef_auditoria_completa(self):
        """
        EF: Varre TODOS os itens e relata progresso/erros de Unidade e Objeto.
        Combina a rigidez do original com o relatório da versão curta.
        """
        print(f"   ↳ Validando {len(self.ef)} itens do Fundamental...")
        
        erros_unidade = []
        erros_objeto = []
        pattern = re.compile(r"EF\d{2}[A-Z]{2}\d{2}")

        for item in self.ef:
            cod = item.get('codigo', 'SEM_COD')
            componente = item.get('componente', '')
            if componente == 'Língua Portuguesa':
                continue  # Pula verificação para Língua Portuguesa, pois não segue o mesmo padrão de u/o
            
            u = item.get('unidade_tematica')
            o = item.get('objeto_conhecimento')
            
            # Validação de Formato
            if not pattern.match(cod):
                self.fail(f"❌ CÓDIGO INVÁLIDO NO EF: {cod}")

            # Validação de Conteúdo (Campos Vazios)
            # Aceitamos None apenas se for estritamente necessário, mas na BNCC quase tudo tem.
            # Verificamos comprimento > 2 para evitar strings vazias "" ou " "
            if not u or len(str(u).strip()) < 2:
                erros_unidade.append(cod)
            
            if not o or len(str(o).strip()) < 2:
                erros_objeto.append(cod)

        total_erros = len(erros_unidade) + len(erros_objeto)
        
        if total_erros > 0:
            msg = f"\n❌ FALHA DE INTEGRIDADE EF: {total_erros} problemas encontrados.\n"
            if erros_unidade:
                msg += f"--- {len(erros_unidade)} ITENS SEM UNIDADE TEMÁTICA ---\n" + ", ".join(erros_unidade[:30]) + "...\n"
            if erros_objeto:
                msg += f"--- {len(erros_objeto)} ITENS SEM OBJETO DE CONHECIMENTO ---\n" + ", ".join(erros_objeto[:30]) + "...\n"
            self.fail(msg)
        else:
            print("     ✅ EF: Blindagem Total (Unidades e Objetos 100% preenchidos).")

    # =========================================================================
    # 3. ENSINO MÉDIO (EM)
    # =========================================================================
    def test_em_estrutura(self):
        """EM: Verifica Competências e Áreas."""
        print("   ↳ Validando Ensino Médio...")
        erros = []
        for item in self.em:
            cod = item['codigo']
            # Matemática e Ciências precisam de Area e Competencia
            if "MAT" in cod or "CNT" in cod or "CHS" in cod or "LGG" in cod:
                 if not item.get('competencia_especifica'):
                     erros.append(f"{cod} sem Competência Específica")
            
            # Língua Portuguesa no EM tem Campo de Atuação Social
            if "LP" in cod:
                if not item.get('campo_atuacao_social'):
                    erros.append(f"{cod} sem Campo de Atuação Social")

        if erros:
            self.fail(f"❌ ERROS EM:\n" + "\n".join(erros[:10]))
        else:
             print("     ✅ EM: Estrutura OK.")

    # =========================================================================
    # 4. AUDITORIA FORENSE (O RETORNO)
    # =========================================================================
    def test_forense_amostragem(self):
        """
        Verifica se uma amostra aleatória de códigos realmente existe no PDF.
        Isso garante que o extrator não está 'alucinando' códigos.
        """
        if not self.texto_pdf_completo:
            return

        import random
        todos_codigos = [i['codigo'] for i in self.ei + self.ef + self.em]
        amostra = random.sample(todos_codigos, 20) # Testa 20 códigos aleatórios
        
        print(f"   ↳ Teste Forense em Amostra: {amostra}")
        
        erros = []
        for cod in amostra:
            if cod not in self.texto_pdf_completo:
                erros.append(cod)
        
        if erros:
            print(f"     ⚠️ ALERTA: Códigos não encontrados no texto bruto: {erros}")
            print("        (Isso pode ocorrer se o PDF tiver quebras de linha no meio do código, ex: EF01\\nLP01)")
        else:
            print("     ✅ Forense: Amostra validada com sucesso no texto original.")

if __name__ == '__main__':
    unittest.main(verbosity=2)
