"""
Aqui ele faz um chekin se o remedio cadastrado do usuario (já filtrado) 
é incompativel com algum outro
"""

import json
import os
import sys
from rapidfuzz import fuzz
from pathlib import Path

# Configura o path para encontrar o ai_handler na pasta core/ia
BASE_DIR = Path(__file__).resolve().parent
if (BASE_DIR / "ia").exists():
    CAMINHO_IA = BASE_DIR / "ia"
elif (BASE_DIR.parent / "core" / "ia").exists():
    CAMINHO_IA = BASE_DIR.parent / "core" / "ia"
else:
    CAMINHO_IA = BASE_DIR / "core" / "ia"

sys.path.append(str(CAMINHO_IA))
from ai_handler import AIHandler

from complementos import carregar_json, salvar_json

def extrair_todos_medicamentos_usuario(usuario_dados):
    """
    Consolida todos os medicamentos do paciente das diferentes listas em uma única lista tratada.
    """
    categorias = ["remedio_solidos", "remedio_liquidos", "remedio_injetavel", "remedio_colirio"]
    lista_medicamentos = []

    for cat in categorias:
        if cat in usuario_dados:
            for item in usuario_dados[cat]:
                nome = item.get("nome_medicamento") or item.get("nome_fornecido")
                med_id = item.get("id")
                
                horario = item.get("horario") or item.get("horario_fixo") or "Não especificado"
                periodo = item.get("periodo") or item.get("periodo_dia") or "Não especificado"

                if nome:
                    lista_medicamentos.append({
                        "id": med_id,
                        "nome": nome,
                        "categoria": cat,
                        "horario": horario,
                        "periodo": periodo
                    })

    return lista_medicamentos


def buscar_dados_base_local(med_id, nome_med, db_dados):
    """
    Localiza o objeto do medicamento na base solidificados.json pelo ID ou pelo Nome.
    """
    categorias_db = ["remedio_solido", "remedio_liquido", "remedio_injetavel", "remedio_colirio"]

    for cat in categorias_db:
        for item in db_dados.get(cat, []):
            if med_id and item.get("id") == med_id:
                return item
            if nome_med and item.get("nome") and fuzz.ratio(nome_med.lower(), item["nome"].lower()) >= 85:
                return item

    return None


def verificar_incompatibilidades(usuario_json_path="usuario_atualizado.json", db_json_path="solidificados.json", output_relatorio_path="relatorio_incompatibilidades.json"):
    """
    Varre os medicamentos do paciente, cruza as incompatibilidades da base local
    e complementa com uma auditoria via IA para interações complexas (1x1).
    """
    usuario_dados = carregar_json(usuario_json_path)
    db_dados = carregar_json(db_json_path)

    if not usuario_dados or not db_dados:
        print("DEBUG: Arquivos de entrada não encontrados para validação de incompatibilidades.")
        return {}

    medicamentos_paciente = extrair_todos_medicamentos_usuario(usuario_dados)
    alertas_incompatibilidade = []

    print("\nDEBUG: Iniciando verificação de incompatibilidades farmacológicas (Base Local + IA)...")

    # 1. Validação cruzada via base local (Par a Par)
    total_meds = len(medicamentos_paciente)
    for i in range(total_meds):
        for j in range(i + 1, total_meds):
            med_a = medicamentos_paciente[i]
            med_b = medicamentos_paciente[j]

            dados_a = buscar_dados_base_local(med_a["id"], med_a["nome"], db_dados)
            dados_b = buscar_dados_base_local(med_b["id"], med_b["nome"], db_dados)

            if not dados_a or not dados_b:
                continue

            incompatibilidades_a = dados_a.get("incompatibilidades", [])
            incompatibilidades_b = dados_b.get("incompatibilidades", [])
            substancias_a = dados_a.get("substancia_ativa", [])
            substancias_b = dados_b.get("substancia_ativa", [])

            conflito_encontrado = False
            motivo_conflito = []

            for inc in incompatibilidades_a:
                for subst in substancias_b:
                    if fuzz.partial_ratio(subst.lower(), inc.lower()) >= 80 or subst.lower() in inc.lower():
                        conflito_encontrado = True
                        motivo_conflito.append(f"Incompatibilidade descrita para {med_a['nome']}: '{inc}'")

            for inc in incompatibilidades_b:
                for subst in substancias_a:
                    if fuzz.partial_ratio(subst.lower(), inc.lower()) >= 80 or subst.lower() in inc.lower():
                        conflito_encontrado = True
                        motivo_conflito.append(f"Incompatibilidade descrita para {med_b['nome']}: '{inc}'")

            if conflito_encontrado:
                mesmo_horario = (med_a["horario"] != "Não especificado" and med_a["horario"] == med_b["horario"])
                mesmo_periodo = (med_a["periodo"] != "Não especificado" and med_a["periodo"] == med_b["periodo"])

                nivel_severidade = "ALTA" if (mesmo_horario or mesmo_periodo) else "MEDIA"

                alerta = {
                    "medicamento_1": med_a["nome"],
                    "horario_1": f"{med_a['periodo']} ({med_a['horario']})",
                    "medicamento_2": med_b["nome"],
                    "horario_2": f"{med_b['periodo']} ({med_b['horario']})",
                    "severidade": nivel_severidade,
                    "conflito_horario": mesmo_horario or mesmo_periodo,
                    "detalhes": list(set(motivo_conflito)),
                    "fonte": "base_local"
                }
                
                # Evita duplicatas exatas
                if not any(a["medicamento_1"] == alerta["medicamento_1"] and a["medicamento_2"] == alerta["medicamento_2"] for a in alertas_incompatibilidade):
                    alertas_incompatibilidade.append(alerta)
                    print(f"DEBUG: [ALERTA LOCAL {nivel_severidade}] Conflito entre '{med_a['nome']}' e '{med_b['nome']}'")

    # 2. Auditoria complementar via IA (1x1 ou lote seguro) para garantir robustez clínica
    print("DEBUG: Executando auditoria clínica complementar via IA para interações medicamentosas...")
    try:
        ai_handler = AIHandler()
        lista_nomes_meds = [m["nome"] for m in medicamentos_paciente]
        
        prompt_sistema = (
            "Você é um farmacêutico clínico especialista em interações medicamentosas baseado nos padrões da ANVISA, e usa de referencia o Dicionário de Especialidades Farmacêuticas (DEF). "
            "Analise a lista de medicamentos do paciente e identifique se há interações medicamentosas graves ou moderadas entre suas respectivas classes terapeuticas. "
            "Retorne estritamente um JSON no seguinte formato:\n"
            "{\n"
            '  "interacoes": [\n'
            "    {\n"
            '      "medicamento_1": "Nome A",\n'
            '      "medicamento_2": "Nome B",\n'
            '      "severidade": "ALTA ou MEDIA",\n'
            '      "detalhe": "Descrição curta da interação"\n'
            "    }\n"
            "  ]\n"
            "}"
        )
        pergunta = f"Analise os seguintes medicamentos em uso simultâneo pelo paciente: {', '.join(lista_nomes_meds)}."
        
        resposta_ai = ai_handler.gerar_resposta(prompt_sistema, pergunta)
        
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
            json_limpo = json_limpo.split("```")[1].split("```")[0].strip()
            
        dados_ia = json.loads(json_limpo)
        interacoes_ia = dados_ia.get("interacoes", [])
        
        for inter in interacoes_ia:
            med1 = inter.get("medicamento_1")
            med2 = inter.get("medicamento_2")
            
            # Verifica se esse par já foi capturado pela base local para evitar duplicidade
            ja_existe = any(
                (a["medicamento_1"].lower() == med1.lower() and a["medicamento_2"].lower() == med2.lower()) or
                (a["medicamento_1"].lower() == med2.lower() and a["medicamento_2"].lower() == med1.lower())
                for a in alertas_incompatibilidade
            )
            
            if not ja_existe:
                # Descobre horários na lista do paciente
                h1, h2 = "Não especificado", "Não especificado"
                p1, p2 = "Não especificado", "Não especificado"
                for m in medicamentos_paciente:
                    if fuzz.ratio(m["nome"].lower(), med1.lower()) >= 80:
                        h1, p1 = m["horario"], m["periodo"]
                    if fuzz.ratio(m["nome"].lower(), med2.lower()) >= 80:
                        h2, p2 = m["horario"], m["periodo"]

                mesmo_horario = (h1 != "Não especificado" and h1 == h2)
                mesmo_periodo = (p1 != "Não especificado" and p1 == p2)
                
                alerta_ia = {
                    "medicamento_1": med1,
                    "horario_1": f"{p1} ({h1})",
                    "medicamento_2": med2,
                    "horario_2": f"{p2} ({h2})",
                    "severidade": inter.get("severidade", "MEDIA"),
                    "conflito_horario": mesmo_horario or mesmo_periodo,
                    "detalhes": [inter.get("detalhe", "Interação detectada por IA")],
                    "fonte": "ia_clinica"
                }
                alertas_incompatibilidade.append(alerta_ia)
                print(f"DEBUG: [ALERTA IA] Interação detectada entre '{med1}' e '{med2}'")
                
    except Exception as e:
        print(f"DEBUG: Erro na auditoria complementar de IA para incompatibilidades: {e}")

    # Monta o relatório final
    resultado_final = {
        "paciente_id": usuario_dados.get("paciente_id"),
        "nome_paciente": usuario_dados.get("nome_paciente"),
        "total_medicamentos_analisados": total_meds,
        "possui_incompatibilidades": len(alertas_incompatibilidade) > 0,
        "alertas": alertas_incompatibilidade
    }

    # Salva o relatório de incompatibilidades
    salvar_json(resultado_final, output_relatorio_path)

    # Atualiza o próprio usuario_atualizado.json adicionando o bloco de alertas
    usuario_dados["alertas_incompatibilidade"] = alertas_incompatibilidade
    salvar_json(usuario_dados, usuario_json_path)

    print(f"DEBUG: Análise concluída! Relatório salvo em '{output_relatorio_path}' e 'usuario_atualizado.json' atualizado.")
    return resultado_final


if __name__ == "__main__":
    verificar_incompatibilidades("usuario_atualizado.json", "solidificados.json")