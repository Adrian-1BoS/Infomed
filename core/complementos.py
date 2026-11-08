import json
import os
import sys
import re
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

def extrair_dosagem_emergencial(apresentacao):
    """
    Caso o item do DB possua dosagem nula, extrai o valor numérico em tempo 
    de execução para viabilizar o desempate matemático com os dados do usuário.
    """
    if not apresentacao:
        return None
    apres = str(apresentacao).upper()
    padrao_complexo = r'(?:\(([^)]+)\)|(\d+(?:[\.,]\d+)?))\s*(MG/ML|U/ML|MU|MG/G|MG|%)'
    match = re.search(padrao_complexo, apres)
    if not match:
        return None
        
    trecho_numerico = match.group(1) if match.group(1) else match.group(2)
    padrao_numeros = r'(\d+(?:[\.,]\d+)?)'
    valores_encontrados = re.findall(padrao_numeros, trecho_numerico)
    
    if not valores_encontrados:
        return None
    try:
        return sum([float(val.replace(',', '.')) for val in valores_encontrados])
    except (ValueError, TypeError):
        return None

def buscar_medicamento(remedio_usuario, db_medicamentos):
    """
    Busca o melhor match usando fuzzy matching com camadas estritas de prioridade por campo
    (1º Nome Oficial, 2º Nomes Alternativos, 3º Substância Ativa) e desempata por dosagem.
    """
    nome_fornecido = ""
    grandeza_usuario = None
    dosagem_usuario = None

    # 1. CAPTURA E CLASSIFICAÇÃO DA GRANDEZA DA UI
    if isinstance(remedio_usuario, dict):
        nome_fornecido = remedio_usuario.get("nome_fornecido") or remedio_usuario.get("nome_medicamento") or ""
        ordem_chaves_ui = ["dosagem_mg", "mg", "concentracao_mg_ml", "concentracao_ui_ml", "por_cento", "mg_g"]
        for chave in ordem_chaves_ui:
            if remedio_usuario.get(chave) is not None:
                dosagem_usuario = remedio_usuario.get(chave)
                grandeza_usuario = chave
                break
    else:
        nome_fornecido = str(remedio_usuario)

    melhor_match = None
    maior_score = -1
    melhor_id = None
    melhor_nome_oficial = None
    menor_diferenca_dosagem = float('inf')

    nome_fornecido_norm = normalizar_texto(nome_fornecido)

    for item in db_medicamentos:
        # 2. ESTRUTURAÇÃO DE CAMADAS COM PENALIZAÇÃO DE SCORE (Fim do falso positivo)
        # Cada tupla contém: (lista_de_textos, string_da_camada, penalidade_de_score)
        camadas_busca = [
            ([item.get("nome")] if item.get("nome") else [], "nome_oficial", 0),
            (item.get("nomes_alternativos", []), "nome_alternativo", 5),
            (item.get("substancia_ativa", []), "substancia_ativa", 15)
        ]

        # Captura e classificação da grandeza do banco local
        dosagem_db = None
        grandeza_db = None
        if item.get("mg") is not None:
            dosagem_db, grandeza_db = item["mg"], "mg"
        elif item.get("mg_ml") is not None:
            dosagem_db, grandeza_db = item["mg_ml"], "concentracao_mg_ml"
        elif item.get("por_cento") is not None:
            dosagem_db, grandeza_db = item["por_cento"], "por_cento"
        elif item.get("mg_g") is not None:
            dosagem_db, grandeza_db = item["mg_g"], "mg_g"
        
        if dosagem_db is None and item.get("apresentacao"):
            dosagem_db = extrair_dosagem_emergencial(item["apresentacao"])
            grandeza_db = "mg"

        if grandeza_usuario == "dosagem_mg": grandeza_usuario = "mg"

        # Varre as camadas aplicando as penalidades de relevância
        for textos_candidatos, camada, penalidade in camadas_busca:
            for cand in textos_candidatos:
                if not cand:
                    continue
                
                # Calcula o score fuzzy bruto do texto
                score_bruto = fuzz.ratio(nome_fornecido_norm, normalizar_texto(cand))
                
                # Aplica a penalidade baseada na importância do campo (Garante relevância)
                score_final = max(0, score_bruto - penalidade)
                
                # Condição A: Encontrou um score de relevância estritamente maior
                if score_final > maior_score:
                    maior_score = score_final
                    melhor_match = cand
                    melhor_id = item.get("id")
                    melhor_nome_oficial = item.get("nome")
                    
                    if dosagem_usuario is not None and dosagem_db is not None and grandeza_usuario == grandeza_db:
                        try:
                            menor_diferenca_dosagem = abs(float(dosagem_usuario) - float(dosagem_db))
                        except (ValueError, TypeError):
                            menor_diferenca_dosagem = float('inf')
                    else:
                        menor_diferenca_dosagem = float('inf')
                
                # Condição B: EMPATE MATEMÁTICO DE RELEVÂNCIA (O desempate de dosagem entra em ação)
                elif score_final == maior_score and score_final > 0:
                    if dosagem_usuario is not None and dosagem_db is not None:
                        if grandeza_usuario == grandeza_db:
                            try:
                                dif_atual = abs(float(dosagem_usuario) - float(dosagem_db))
                                if dif_atual < menor_diferenca_dosagem:
                                    menor_diferenca_dosagem = dif_atual
                                    melhor_match = cand
                                    melhor_id = item.get("id")
                                    melhor_nome_oficial = item.get("nome")
                            except (ValueError, TypeError):
                                pass

    return melhor_match, maior_score, melhor_id, melhor_nome_oficial

def complementar_db_farmaco(db_json_path, usuario_json_path):
    """
    Varre os medicamentos do usuário e preenche efeitos_colaterais e incompatibilidades.
    Aplica CACHE por substância ativa e herança local para reaproveitar os dados da IA.
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
                    
                    # Cria uma chave única baseada na substância ativa
                    chave_cache = tuple(sorted([s.strip().lower() for s in substancias_list if s]))
                    substancias = ", ".join(substancias_list)

                    # Verificar se já está no CACHE da sessão atual 
                    if chave_cache in cache_substancias:
                        dados_cached = cache_substancias[chave_cache]
                        item["efeitos_colaterais"] = dados_cached["efeitos_colaterais"]
                        item["incompatibilidades"] = dados_cached["incompatibilidades"]
                        atualizou_algum = True
                        print(f"DEBUG: Dados de '{nome_med}' copiados via substância ativa: ({substancias})")
                        continue

                    # Procurar na própria BASE LOCAL se outro medicamento com a mesma substância já possui esses dados
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

                    # Se não achou em nenhum lugar (Cache ou Base), faz a requisição para a IA
                    print(f"DEBUG: Consultando IA para: {nome_med} (Substâncias: {substancias})...")
                    
                    prompt_farmaceutico = (
                        "Você é um profissional farmacêutico clínico especialista na regulamentação da ANVISA e no Dicionário de Especialidades Farmacêuticas (DEF). "
                        "Sua função é retornar estritamente no formato JSON as colunas 'efeitos_colaterais' e 'incompatibilidades'.\n"
                        "REGRAS OBRIGATÓRIAS:\n"
                        "1. Utilize exclusivamente a nomenclatura oficial brasileira (DCB) em 'PORTUGUÊS' para todas as substâncias.\n"
                        "2. Exclua absolutamente substâncias estrangeiras, banidas ou sem registro ativo na ANVISA no Brasil.\n"
                        "3. Seja direto e evite descrições genéricas ou redundantes em formato de texto longo; utilize o nome da classe ou substância de forma concisa.\n"
                        'Formato de saída estrito:\n'
                        '{\n  "efeitos_colaterais": ["..."],\n  "incompatibilidades": ["..."]\n}'
                    )
                
                    pergunta_farmaceutica = (
                        f"Traga o JSON de efeitos colaterais e incompatibilidades para o "
                        f"medicamento '{nome_med}' contendo as substâncias ativas em lista separado por virgula: {substancias}."
                    )
                    
                    try:
                        resposta_ai = ai_handler.gerar_resposta(prompt_farmaceutico, pergunta_farmaceutica)
                        
                        texto_resposta = ""
                        # Tratamento robusto do retorno (Suporta Strings, Chunks e iteradores do AIHandler)
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
                        
                        json_limpo = texto_resposta.strip()
                        if "```json" in json_limpo:
                            json_limpo = json_limpo.split("```json")[1].split("```")[0].strip()
                        elif "```" in json_limpo:
                            json_limpo = json_limpo.split("```")[1].split("```")[0].strip()
                            
                        dados_extras = json.loads(json_limpo)
                        
                        efeitos = dados_extras.get("efeitos_colaterais", [])
                        incompat = dados_extras.get("incompatibilidades", [])

                        if efeitos and incompat:
                            item["efeitos_colaterais"] = efeitos
                            item["incompatibilidades"] = incompat
                            
                            # Guarda no cache de memória para evitar requisições repetidas nesta sessão
                            cache_substancias[chave_cache] = {
                                "efeitos_colaterais": efeitos,
                                "incompatibilidades": incompat
                            }
                            
                            atualizou_algum = True
                            print(f"DEBUG: Sucesso ao atualizar e cachear dados de '{nome_med}'!")
                            
                    except Exception as e:
                        print(f"DEBUG: Erro ao converter resposta da IA para '{nome_med}': {e}")

    # 3. Salvamento e Finalização do Processo de Carga
    if atualizou_algum:
        salvar_json(db_dados, db_json_path)
        print(f"DEBUG: Base de dados '{db_json_path}' atualizada com sucesso (com reutilização por substância)!")
    else:
        print("DEBUG: Todos os medicamentos do paciente já possuem dados cadastrados na base.")
