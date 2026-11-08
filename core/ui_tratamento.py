"""
    Aqui sera o principal tratamento UI x dados, processando os dados do usuario
    para um banco de dados mais consiso
"""

from pathlib import Path
import sys, os
import json

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"

CAMINHO_IA = BASE_DIR / "ia"
sys.path.append(str(CAMINHO_IA))

from ai_handler import AIHandler
from complementos import carregar_json, salvar_json, buscar_medicamento, complementar_db_farmaco
from incompativeis import verificar_incompatibilidades

def processar_tratamento_completo(usuario_json_path, db_json_path, output_json_path="usuario_atualizado.json"):
    usuario_dados = carregar_json(usuario_json_path)
    db_dados = carregar_json(db_json_path)
    
    # Dicionário reverso para salvar o remédio na chave correta que a UI espera ler no output
    mapeamento_saida = {
        "remedio_solido": "remedio_solidos",
        "remedio_liquido": "remedio_liquidos",
        "remedio_injetavel": "remedio_injetavel",
        "remedio_colirio": "remedio_colirio",
        "nao_identificado": "nao_identificados"
    }

    # Inicializa a estrutura limpa de categorias no dicionário final do paciente
    dados_finais_paciente = {
        "paciente_id": usuario_dados.get("paciente_id"),
        "nome_paciente": usuario_dados.get("nome_paciente"),
        "tel_paciente": usuario_dados.get("tel_paciente"),
        "responsavel": usuario_dados.get("responsavel"),
        "tel_responsavel": usuario_dados.get("tel_responsavel"),
        "remedio_solidos": [],
        "remedio_liquidos": [],
        "remedio_injetavel": [],
        "remedio_colirio": [],
        "nao_identificados": []
    }

    # Captura a lista plana de medicamentos enviada pela UI (seja dentro de uma chave ou varrendo a raiz)
    medicamentos_brutos = usuario_dados.get("medicamentos", [])
    if not medicamentos_brutos:
        # Fallback caso a UI envie os remédios soltos na raiz do JSON
        medicamentos_brutos = [v for k, v in usuario_dados.items() if isinstance(v, dict) and "nome_fornecido" in v]
        if not medicamentos_brutos and isinstance(usuario_dados, dict):
            # Se vier uma lista de dicionários misturada com os dados cadastrais
            medicamentos_brutos = [item for item in usuario_dados.values() if isinstance(item, list)]
            # Se os remédios vierem numa lista sem chave, achamos limpando metadados
            medicamentos_brutos = []
            for chave, valor in usuario_dados.items():
                if isinstance(valor, list) and len(valor) > 0 and "nome_fornecido" in valor[0]:
                    medicamentos_brutos.extend(valor)

    limiar_fuzzy = 75
    ai_handler = AIHandler()

    print("1º Triagem, Correção e Categorização Dinâmica dos Medicamentos (Fuzzy + IA)")
    
    for remedio in medicamentos_brutos:
        nome_fornecido = remedio.get("nome_fornecido", "")
        print(f"\nProcessando Medicamento da UI: '{nome_fornecido}'")
        
        melhor_match_global = None
        maior_score_global = -1
        id_global = None
        nome_oficial_global = None
        categoria_vencedora = "nao_identificado"

        # 1. VARREDURA GLOBAL: Procura o remédio em todas as categorias do banco de dados para descobrir o grupo
        for cat_db, lista_db in db_dados.items():
            if not isinstance(lista_db, list):
                continue
                
            match, score, med_id, nome_oficial = buscar_medicamento(remedio, lista_db)
            
            if score > maior_score_global:
                maior_score_global = score
                melhor_match_global = match
                id_global = med_id
                nome_oficial_global = nome_oficial
                categoria_vencedora = cat_db

        # 2. DECISÃO DE MATCH LOCAL (Fuzzy Forte)
        if maior_score_global >= limiar_fuzzy:
            print(f"  -> [Match Local] Encontrado em '{categoria_vencedora}' (Score: {maior_score_global}): '{melhor_match_global}' (ID: {id_global})")
            remedio["nome_medicamento"] = nome_oficial_global
            remedio["id"] = id_global
            
            # Aloca dinamicamente na categoria correta de saída do prontuário
            chave_saida = mapeamento_saida.get(categoria_vencedora, "nao_identificados")
            dados_finais_paciente[chave_saida].append(remedio)
            
        else:
            # 3. FALLBACK DA IA SE O FUZZY GLOBAL FOR FRACO
            print(f"  -> [Fuzzy Fraco] Score: {maior_score_global}. Consultando inteligência artificial...")
            
            prompt_sistema = (
                "Você é um assistente farmacêutico especialista. "
                "Verifique se o medicamento informado existe ou a qual medicamento comercial/genérico oficial ele se refere no Brasil. "
                "Responda estritamente apenas com o nome oficial correto do medicamento ou a palavra 'Desconhecido'. Não adicione pontuação ou explicações."
            )
            pergunta = f"O paciente informou o medicamento '{nome_fornecido}'. Qual é o nome oficial correto?"
            
            resposta_ai = ai_handler.gerar_resposta(prompt_sistema, pergunta)
            
            texto_resposta = ""
            if isinstance(resposta_ai, str):
                texto_resposta = resposta_ai
            elif hasattr(resposta_ai, 'text'):
                texto_resposta = resposta_ai.text
            elif hasattr(resposta_ai, '__iter__'):
                for chunk in resposta_ai:
                    if isinstance(chunk, str):
                        texto_resposta += chunk
                    elif hasattr(chunk, 'text'):
                        texto_resposta += chunk.text
            
            texto_resposta = texto_resposta.strip()
            print(f"    -> Resposta da IA: {texto_resposta}")
            
            if texto_resposta and "desconhecido" not in texto_resposta.lower():
                # Nova varredura utilizando o termo corrigido pela IA
                maior_score_ia = -1
                categoria_vencedora_ia = "nao_identificado"
                
                for cat_db, lista_db in db_dados.items():
                    if not isinstance(lista_db, list):
                        continue
                    match_ia, score_ia, med_id_ia, nome_oficial_ia = buscar_medicamento(texto_resposta, lista_db)
                    
                    if score_ia > maior_score_ia:
                        maior_score_ia = score_ia
                        melhor_match_global = match_ia
                        id_global = med_id_ia
                        nome_oficial_global = nome_oficial_ia
                        categoria_vencedora_ia = cat_db

                if maior_score_ia >= limiar_fuzzy:
                    remedio["id"] = id_global
                    remedio["nome_medicamento"] = nome_oficial_global
                    print(f"    -> [IA Match] Mapeado para a base local na categoria '{categoria_vencedora_ia}' (ID: {id_global})")
                    chave_saida = mapeamento_saida.get(categoria_vencedora_ia, "nao_identificados")
                    dados_finais_paciente[chave_saida].append(remedio)
                else:
                    remedio["nome_medicamento"] = texto_resposta
                    remedio["id"] = None
                    dados_finais_paciente["nao_identificados"].append(remedio)
                    print(f"    -> DEBUG: Nome traduzido pela IA ('{texto_resposta}'), mas categoria não mapeada no DB local.")
            else:
                remedio["id"] = None
                dados_finais_paciente["nao_identificados"].append(remedio)
                print("    -> DEBUG: Medicamento não validado pela IA ou inconclusivo.")

    # SALVAMENTO DO NOVO JSON SEPARADO POR CATEGORIAS
    try:
        salvar_json(dados_finais_paciente, output_json_path)
        print(f"\n[Sucesso] Prontuário categorizado dinamicamente salvo em '{output_json_path}'.")
    except Exception as e:
        print(f"\n[Erro] Falha ao gravar arquivo de saída do usuário: {e}")

    # COMPLEMENTAÇÃO DA BASE DE DADOS E ANÁLISE DE INTERAÇÕES
    print("\nIniciando verificação e complementação da base de dados...")
    try:
        complementar_db_farmaco(db_json_path=db_json_path, usuario_json_path=output_json_path)
    except Exception as e:
        print(f"[Erro] Falha ao executar a complementação do banco: {e}")
    
    print("\nIniciando análise cruzada de incompatibilidades do paciente...")
    try:
        relatorio_path = str(DATA_DIR / "relatorio_incompatibilidades.json")
        verificar_incompatibilidades(output_json_path, db_json_path, relatorio_path)
        print("[Sucesso] Relatório de incompatibilidades gerado.")
        
        # ⚡ LEITURA ROBUSTA: Abre o arquivo gerado fisicamente em disco pela IA
        if os.path.exists(relatorio_path):
            with open(relatorio_path, 'r', encoding='utf-8') as rf:
                relatorio_dados = json.load(rf)
                
                # Desembrulha o JSON dinamicamente, não importa o formato de escrita do motor
                if isinstance(relatorio_dados, dict) and "alertas_incompatibilidade" in relatorio_dados:
                    dados_finais_paciente["alertas_incompatibilidade"] = relatorio_dados["alertas_incompatibilidade"]
                elif isinstance(relatorio_dados, dict) and "alertas" in relatorio_dados:
                    dados_finais_paciente["alertas_incompatibilidade"] = relatorio_dados["alertas"]
                elif isinstance(relatorio_dados, list):
                    dados_finais_paciente["alertas_incompatibilidade"] = relatorio_dados
                else:
                    dados_finais_paciente["alertas_incompatibilidade"] = []
        else:
            dados_finais_paciente["alertas_incompatibilidade"] = []
                    
    except Exception as e:
        print(f"[Erro] Falha ao rodar a análise de incompatibilidades do paciente: {e}")
        dados_finais_paciente["alertas_incompatibilidade"] = []

    # Devolve o dicionário contendo as gavetas populadas e as interações extraídas do disco
    return dados_finais_paciente

if __name__ == "__main__":
    usuario_path = DATA_DIR / "usuario.json"
    db_path = DATA_DIR / "solidificados.json"
    output_path = DATA_DIR / "usuario_atualizado.json"
    
    processar_tratamento_completo(usuario_json_path=str(usuario_path), db_json_path=str(db_path), output_json_path=str(output_path))