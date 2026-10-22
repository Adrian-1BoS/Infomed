import json
import os
import sys
from rapidfuzz import fuzz
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
CAMINHO_IA = BASE_DIR / "ia"
sys.path.append(str(CAMINHO_IA))

from ai_handler import AIHandler

def carregar_json(caminho):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvar_json(dados, caminho):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def normalizar_texto(texto):
    return str(texto).strip().lower()

def buscar_medicamento(nome_fornecido, db_medicamentos):
    """
    Busca o melhor match usando fuzzy matching contra:
    - nome
    - nomes_alternativos
    - substancia_ativa
    """
    melhor_match = None
    maior_score = 0
    melhor_id = None
    melhor_nome_oficial = None

    for item in db_medicamentos:
        candidatos = []
        if item.get("nome"):
            candidatos.append(item["nome"])
        for alt in item.get("nomes_alternativos", []):
            if alt:
                candidatos.append(alt)
        for subst in item.get("substancia_ativa", []):
            if subst:
                candidatos.append(subst)

        for cand in candidatos:
            score = fuzz.ratio(normalizar_texto(nome_fornecido), normalizar_texto(cand))
            if score > maior_score:
                maior_score = score
                melhor_match = cand
                melhor_id = item.get("id")
                melhor_nome_oficial = item.get("nome")

    return melhor_match, maior_score, melhor_id, melhor_nome_oficial


def complementar_db_farmaco(db_json_path, usuario_json_path):
    """
    Varre APENAS os medicamentos do usuário e preenche efeitos_colaterais e incompatibilidades.
    Aplica CACHE por substância ativa e herança local para evitar requisições redundantes na IA.
    """
    db_dados = carregar_json(db_json_path)
    usuario_dados = carregar_json(usuario_json_path)
    
    if not db_dados or not usuario_dados:
        print(f"DEBUG: Erro ao carregar '{db_json_path}' ou '{usuario_json_path}'.")
        return

    # 1. Coleta apenas os medicamentos do paciente
    meds_paciente = []
    categorias_user = ["remedio_solidos", "remedio_liquidos", "remedio_injetavel", "remedio_colirio"]
    for cat in categorias_user:
        for item in usuario_dados.get(cat, []):
            med_id = item.get("id")
            nome = item.get("nome_medicamento") or item.get("nome_fornecido")
            if med_id or nome:
                meds_paciente.append({"id": med_id, "nome": nome})

    if not meds_paciente:
        print("DEBUG: Nenhum medicamento encontrado na lista do usuário.")
        return

    ai_handler = AIHandler()
    categorias_db = ["remedio_solido", "remedio_liquido", "remedio_injetavel", "remedio_colirio"]
    atualizou_algum = False

    # CACHE EM MEMÓRIA (Chave: tuple de substâncias ordenadas)
    cache_substancias = {}

    print("\nDEBUG: 2º: Preenchimento Sob Demanda com Cache por Substância Ativa")
    
    for chave_db in categorias_db:
        if chave_db not in db_dados:
            continue
            
        for item in db_dados[chave_db]:
            # Verifica se o item pertence ao paciente
            pertence_ao_paciente = any(
                (p["id"] and p["id"] == item.get("id")) or 
                (p["nome"] and p["nome"].lower() == item.get("nome", "").lower())
                for p in meds_paciente
            )

            if pertence_ao_paciente:
                # Checa se falta preencher
                if not item.get("efeitos_colaterais") or not item.get("incompatibilidades"):
                    nome_med = item.get("nome")
                    substancias_list = item.get("substancia_ativa", [])
                    
                    # Cria uma chave única baseada na substância ativa (ex: "fenobarbital" ou "ledipasvir, sofosbuvir")
                    chave_cache = tuple(sorted([s.strip().lower() for s in substancias_list if s]))
                    substancias = ", ".join(substancias_list)

                    # -------------------------------------------------------------
                    # TÁTICA 1: Verificar se já está no CACHE da sessão atual
                    # -------------------------------------------------------------
                    if chave_cache in cache_substancias:
                        dados_cached = cache_substancias[chave_cache]
                        item["efeitos_colaterais"] = dados_cached["efeitos_colaterais"]
                        item["incompatibilidades"] = dados_cached["incompatibilidades"]
                        atualizou_algum = True
                        print(f"DEBUG: Dados de '{nome_med}' copiados via substância ativa: ({substancias})")
                        continue

                    # -------------------------------------------------------------
                    # TÁTICA 2: Procurar na própria BASE LOCAL se outro medicamento 
                    # com a mesma substância já possui esses dados
                    # -------------------------------------------------------------
                    encontrado_na_base = False
                    for cat_busca in categorias_db:
                        for item_busca in db_dados.get(cat_busca, []):
                            subst_busca = tuple(sorted([s.strip().lower() for s in item_busca.get("substancia_ativa", []) if s]))
                            if subst_busca == chave_cache and item_busca.get("efeitos_colaterais") and item_busca.get("incompatibilidades"):
                                item["efeitos_colaterais"] = item_busca["efeitos_colaterais"]
                                item["incompatibilidades"] = item_busca["incompatibilidades"]
                                
                                # Salva no cache também
                                cache_substancias[chave_cache] = {
                                    "efeitos_colaterais": item_busca["efeitos_colaterais"],
                                    "incompatibilidades": item_busca["incompatibilidades"]
                                }
                                atualizou_algum = True
                                encontrado_na_base = True
                                print(f"DEBUG: Dados de '{nome_med}' herdados de registro existente na base ({substancias})")
                                break
                        if encontrado_na_base:
                            break

                    if encontrado_na_base:
                        continue

                    # -------------------------------------------------------------
                    # TÁTICA 3: Se não achou em nenhum lugar, faz a requisição na IA
                    # -------------------------------------------------------------
                    print(f"DEBUG: Consultando IA para: {nome_med} (Substâncias: {substancias})...")
                    
                    prompt_farmaceutico = (
                        "Você é um profissional farmacêutico que trabalha com o Dicionário de Especialidades Farmacêuticas "
                        "de cor e salteado, usando-o como referência absoluta em suas pesquisas e consultas. "
                        "Sua função é retornar estritamente no formato JSON o preenchimento dessas duas colunas:\n"
                        '{\n  "efeitos_colaterais": [...],\n  "incompatibilidades": [...]\n}\n'
                        "Sendo incompatibilidades focadas nas substâncias ativas presentes de acordo com a ANVISA."
                    )
                
                    pergunta_farmaceutica = f"Traga o JSON em forma de lista de efeitos colaterais e incompatibilidades para o medicamento '{nome_med}' contendo as substâncias ativas: {substancias}."
                
                    try:
                        resposta_ai = ai_handler.gerar_resposta(prompt_farmaceutico, pergunta_farmaceutica)
                        
                        texto_resposta = ""
                        if hasattr(resposta_ai, '__iter__') and not isinstance(resposta_ai, str):
                            for chunk in resposta_ai:
                                if hasattr(chunk, 'text'):
                                    texto_resposta += chunk.text
                        else:
                            texto_resposta = str(resposta_ai)
                        
                        json_limpo = texto_resposta.strip()
                        if "```json" in json_limpo:
                            json_limpo = json_limpo.split("```json")[1].split("```")[0].strip()
                        elif "```" in json_limpo:
                            json_limpo = json_limpo.split("```json")[0].split("```")[0].strip()
                            
                        dados_extras = json.loads(json_limpo)
                        
                        efeitos = dados_extras.get("efeitos_colaterais", [])
                        incompat = dados_extras.get("incompatibilidades", [])

                        if efeitos and incompat:
                            item["efeitos_colaterais"] = efeitos
                            item["incompatibilidades"] = incompat
                            
                            # Guarda no cache para as próximas iterações
                            cache_substancias[chave_cache] = {
                                "efeitos_colaterais": efeitos,
                                "incompatibilidades": incompat
                            }
                            
                            atualizou_algum = True
                            print(f"DEBUG: Sucesso ao atualizar e cachear dados de '{nome_med}'!")
                    except Exception as e:
                        print(f"DEBUG: Erro ao converter resposta da IA para '{nome_med}': {e}")

    if atualizou_algum:
        salvar_json(db_dados, db_json_path)
        print(f"DEBUG: Base de dados '{db_json_path}' atualizada com sucesso (com reutilização por substância)!")
    else:
        print("DEBUG: Todos os medicamentos do paciente já possuem dados cadastrados na base.")