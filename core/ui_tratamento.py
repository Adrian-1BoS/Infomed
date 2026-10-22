"""
    Aqui sera o principal tratamento UI x dados, processando os dados do usuario
    para um banco de dados mais consiso
"""

from pathlib import Path
import sys

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
    
    mapeamento_categorias = {
        "remedio_solidos": "remedio_solido",
        "remedio_liquidos": "remedio_liquido",
        "remedio_injetavel": "remedio_injetavel",
        "remedio_colirio": "remedio_colirio"
    }

    limiar_fuzzy = 75
    ai_handler = AIHandler()

    print("1º Correção e Mapeamento de Nomes do Usuário (Fuzzy + IA)")
    for chave_usuario, chave_db in mapeamento_categorias.items():
        if chave_usuario not in usuario_dados:
            continue
            
        db_medicamentos = db_dados.get(chave_db, [])
        
        for remedio in usuario_dados[chave_usuario]:
            nome_fornecido = remedio.get("nome_fornecido", "")
            print(f"\nProcessando [{chave_usuario}]: '{nome_fornecido}'")
            
            match, score, med_id, nome_oficial = buscar_medicamento(nome_fornecido, db_medicamentos)
            
            if score >= limiar_fuzzy:
                print(f"Fuzzy - [Local Match] Encontrado (Score: {score}): '{match}' (ID: {med_id})")
                remedio["nome_medicamento"] = nome_oficial
                remedio["id"] = med_id
            else:
                print(f"Fuzzy - [Local Match] Fraco (Score: {score}). Consultando IA...")
                
                prompt_sistema = (
                    "Você é um assistente farmacêutico especialista. "
                    "Verifique se o medicamento informado existe ou a qual medicamento comercial/genérico oficial ele se refere no Brasil. "
                    "Responda apenas com o nome oficial correto do medicamento ou 'Desconhecido'."
                )
                pergunta = f"O paciente informou o medicamento '{nome_fornecido}'. Qual é o nome oficial correto?"
                
                resposta_ai = ai_handler.gerar_resposta(prompt_sistema, pergunta)
                
                texto_resposta = ""
                if hasattr(resposta_ai, '__iter__') and not isinstance(resposta_ai, str):
                    for chunk in resposta_ai:
                        if hasattr(chunk, 'text'):
                            texto_resposta += chunk.text
                else:
                    texto_resposta = str(resposta_ai)
                
                texto_resposta = texto_resposta.strip()
                print(f"  -> Resposta da IA: {texto_resposta}")
                
                if texto_resposta and "desconhecido" not in texto_resposta.lower():
                    remedio["nome_medicamento"] = texto_resposta
                    match_ia, score_ia, med_id_ia, nome_oficial_ia = buscar_medicamento(texto_resposta, db_medicamentos)
                    if score_ia >= limiar_fuzzy:
                        remedio["id"] = med_id_ia
                        remedio["nome_medicamento"] = nome_oficial_ia
                        print(f"IA Match - Mapeado para base local: '{nome_oficial_ia}' (ID: {med_id_ia})")
                else:
                    print("DEBUG: Medicamento não validado pela IA ou inconclusivo.")

    # Salva o resultado final do usuário atualizado
    salvar_json(usuario_dados, output_json_path)
    print(f"\nDados do usuário salvos com sucesso em '{output_json_path}'.")
    
    # Chama a etapa de complementação da base de dados através do módulo importado
    print("\nIniciando verificação e complementação da base de dados...")
    complementar_db_farmaco(db_json_path=db_json_path, usuario_json_path=output_json_path)
    
    verificar_incompatibilidades(output_json_path, db_json_path, "relatorio_incompatibilidades.json")

if __name__ == "__main__":
    usuario_path = DATA_DIR / "usuario.json"
    db_path = DATA_DIR / "solidificados.json"
    output_path = DATA_DIR / "usuario_atualizado.json"
    
    processar_tratamento_completo(usuario_json_path=str(usuario_path), db_json_path=str(db_path), output_json_path=str(output_path))