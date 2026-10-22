"""
Aqui ele faz um chekin se o remedio cadastrado do usuario (já filtrado) 
é incompativel com algum outro
"""

import json, os
from rapidfuzz import fuzz
from complementos import carregar_json, salvar_json

def extrair_todos_medicamentos_usuario(usuario_dados):
    
    # Consolida todos os medicamentos do paciente das diferentes listas em uma única lista tratada.
    
    categorias = ["remedio_solidos", "remedio_liquidos", "remedio_injetavel", "remedio_colirio"]
    lista_medicamentos = []

    for cat in categorias:
        if cat in usuario_dados:
            for item in usuario_dados[cat]:
                # Usa o nome oficial mapeado; se estiver vazio, usa o fornecido
                nome = item.get("nome_medicamento") or item.get("nome_fornecido")
                med_id = item.get("id")
                
                # Trata horário e período de acordo com as chaves do objeto
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
    
    # Localiza o objeto do medicamento na base solidificados.json pelo ID ou pelo Nome.
    
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
    e identifica conflitos diretos.
    """
    usuario_dados = carregar_json(usuario_json_path)
    db_dados = carregar_json(db_json_path)

    if not usuario_dados or not db_dados:
        print("DEBUG: Arquivos de entrada não encontrados para validação de incompatibilidades.")
        return {}

    medicamentos_paciente = extrair_todos_medicamentos_usuario(usuario_dados)
    alertas_incompatibilidade = []

    print("\nDEBUG: Iniciando verificação de incompatibilidades farmacológicas do paciente...")

    # Comparação Par a Par (N x N)
    total_meds = len(medicamentos_paciente)
    for i in range(total_meds):
        for j in range(i + 1, total_meds):
            med_a = medicamentos_paciente[i]
            med_b = medicamentos_paciente[j]

            # Busca dados completos da base solidificados.json
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

            # 1. Verifica se substâncias de B estão nas incompatibilidades de A
            for inc in incompatibilidades_a:
                for subst in substancias_b:
                    if fuzz.partial_ratio(subst.lower(), inc.lower()) >= 80 or subst.lower() in inc.lower():
                        conflito_encontrado = True
                        motivo_conflito.append(f"Incompatibilidade descrita para {med_a['nome']}: '{inc}'")

            # 2. Verifica se substâncias de A estão nas incompatibilidades de B
            for inc in incompatibilidades_b:
                for subst in substancias_a:
                    if fuzz.partial_ratio(subst.lower(), inc.lower()) >= 80 or subst.lower() in inc.lower():
                        conflito_encontrado = True
                        motivo_conflito.append(f"Incompatibilidade descrita para {med_b['nome']}: '{inc}'")

            # Se houver conflito, verifica se há coincidência de horário
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
                    "detalhes": list(set(motivo_conflito))
                }
                alertas_incompatibilidade.append(alerta)
                print(f"DEBUG:  [ALERTA {nivel_severidade}] Conflito entre '{med_a['nome']}' e '{med_b['nome']}'")

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