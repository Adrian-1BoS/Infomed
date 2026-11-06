"""
Esse .py serve apenas para o tratamento do medicamentos.csv e traser um .json
com as informações que eu achei necessarias.
"""

# leitura de arquivos
import json, re
# Caminho do arquivo
from pathlib import Path
# leitura de texto
import pandas as pd

# Variavel para separar medicamentos em 3 grupos usando key_words.
def forma_farmaceutica(apresentacao):
    apres = f" {str(apresentacao).upper()} "
    
    # Usei gemini para me traser os padroes presentes na coluna J do .csv
    injetaveis_key = [' INJ', 'SOL INJ', 'SUSP INJ', ' FRASCO AMPOLA ', ' FA ', ' SER ', ' SERINGA ', ' CANETA ', ' CANETAS ']
    colirios_key = ['OFT', 'COLIRIO', 'COLÍRIO', 'OFTALMICO', 'OFTÁLMICO']
    liquidos_key = ['XPE', 'GOTAS', 'GOT ', 'XAROPE', 'SUSP', 'EMU', 'SOLUCAO', 'SUSPENSAO', 'SOL OR', 'SOL NAS', 'NASAL']
    solidos_key = ['COMP', 'CAP', 'DRG', 'PILULA', 'SACHE', 'TABLETE', 'PASTILHA', 'POM', 'CREME', 'POMADA', 'GEL']    
    
    # se palavra chave (kw) na apresentação (coluna J) == kw em alguma das 3, atribui-la a mesma
    if any(kw in apres for kw in injetaveis_key):
        return 'injetavel'
    elif any(kw in apres for kw in colirios_key):
        return 'colirio'
    elif any(kw in apres for kw in liquidos_key):
        return 'liquido'
    elif any(kw in apres for kw in solidos_key):
        return 'solido'
    else:
        return 'solido'

# Aproveita no csv e extrai a dosagem presente lá. Tem alguns remedios que apresentam calculos (a verificar)
def dosagem(apresentacao):
    apres = str(apresentacao).upper()
    
    # 1. Regex Unificado: Captura números (incluindo expressões compostas dentro de parênteses como "(10 + 0,4)")
    # ou números isolados colados/próximos das unidades válidas (MG/ML, U/ML, MU, MG/G, MG ou %).
    # O uso de \s* garante suporte total a texto grudado (ex: 2MG/ML) ou com espaços.
    padrao_complexo = r'(?:\(([^)]+)\)|(\d+(?:[\.,]\d+)?))\s*(MG/ML|U/ML|MU|MG/G|MG|%)\b'
    
    match = re.search(padrao_complexo, apres)
    if not match:
        return None, None
        
    # Identifica qual grupo capturou o trecho numérico (com ou sem parênteses)
    trecho_numerico = match.group(1) if match.group(1) else match.group(2)
    unidade_raw = match.group(3)
    
    # Trata o nome da unidade para o padrão do JSON (ex: % -> por cento, MG/ML -> mg_ml)
    unidade_json = "por_cento" if unidade_raw == "%" else unidade_raw.lower().replace('/', '_')
    
    # 2. Extrai todos os números isolados de dentro do trecho numérico identificado
    padrao_numeros = r'(\d+(?:[\.,]\d+)?)'
    valores_encontrados = re.findall(padrao_numeros, trecho_numerico)
    
    if not valores_encontrados:
        return None, None
        
    # 3. Converte e executa a soma matemática dos componentes encontrados
    valores_float = []
    for val in valores_encontrados:
        try:
            valores_float.append(float(val.replace(',', '.')))
        except (ValueError, TypeError):
            continue
            
    if not valores_float:
        return None, None
        
    # Retorna a soma total calculada e a chave correta da unidade
    return sum(valores_float), unidade_json

def tratar_substancias(substancia_raw):
    subst_str = str(substancia_raw).strip()
    if not subst_str or subst_str.lower() in ["nan", "none", ""]:
        return []

    return [s.strip().title() for s in subst_str.split(";") if s.strip()]


def cod_anvisa(classe_terapeutica):
    cod = str(classe_terapeutica)
    match_cod = re.search(r"^(\w+)\s*-", cod, re.IGNORECASE)

    if match_cod:
        return match_cod.group(1)
    return None


def descricao_area_atuacao(classe_terapeutica):
    texto = str(classe_terapeutica)
    if " - " in texto:
        return texto.split(" - ", 1)[1].strip()
    return texto.strip()


def processar_csv_anvisa(caminho_csv, caminho_output_json):
    # Tratamento de encoding robusto
    try:
        df = pd.read_csv(caminho_csv, sep=";", encoding="utf-8", dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(caminho_csv, sep=";", encoding="utf-8-sig", dtype=str)

    df.columns = df.columns.str.strip()

    # Mapeamento para direcionar cada tipo à sua respectiva lista consolidada
    categorias = {
        "solido": [],
        "liquido": [],
        "injetavel": [],
        "colirio": [],
        "nao_identificado": [],
    }

    id_counter = 1

    for _, row in df.iterrows():
        nome_produto = str(row.get("PRODUTO", "")).strip().title()
        substancia = row.get("SUBSTÂNCIA", "")
        apresentacao = str(row.get("APRESENTAÇÃO", "")).strip()
        classe_terapeutica = row.get("CLASSE TERAPÊUTICA", "")

        substancias_list = tratar_substancias(substancia)
        tipo = forma_farmaceutica(apresentacao)
        valor_dosagem, unidade = dosagem(apresentacao)

        # Garante que vai para 'nao_identificado' se o tipo retornar algo inesperado
        categoria_destino = (
            tipo if tipo in categorias else "nao_identificado"
        )

        nome_alt = [
            s for s in substancias_list if s.upper() != nome_produto.upper()
        ]
        cod_classe_terapeutica = cod_anvisa(classe_terapeutica)
        area_atuacao = descricao_area_atuacao(classe_terapeutica)

        # 1. Estrutura base comum a absolutamente todos os medicamentos
        item = {
            "id": id_counter,
            "nome": nome_produto,
            "substancia_ativa": substancias_list,
            "apresentacao": apresentacao,
            "codigo_area_atuacao": cod_classe_terapeutica,
            "area_atuacao": area_atuacao,
            "nomes_alternativos": nome_alt,
            "efeitos_colaterais": [],
            "incompatibilidades": [],
        }

        # 2. Injeção DINÂMICA da dosagem baseada na unidade encontrada (mg, mg_ml, u_ml, etc.)
        if unidade:
            item[unidade] = valor_dosagem
        else:
            # Caso não identifique nenhuma unidade, injeta chaves nulas baseado na categoria
            item["mg" if categoria_destino == "solido" else "mg_ml"] = None

        # 3. Adiciona campos extras específicos por categoria se necessário
        if categoria_destino == "liquido":
            item["viscosidade"] = ""

        # Aloca dinamicamente na lista correspondente
        categorias[categoria_destino].append(item)
        id_counter += 1

    # Formata as chaves finais para manter compatibilidade com seu solidificados.json anterior
    dados_consolidados = {
        "remedio_solido": categorias["solido"],
        "remedio_liquido": categorias["liquido"],
        "remedio_injetavel": categorias["injetavel"],
        "remedio_colirio": categorias["colirio"],
        "nao_identificado": categorias["nao_identificado"],
    }

    # Salva o arquivo de saída tratado
    with open(caminho_output_json, "w", encoding="utf-8") as f:
        json.dump(dados_consolidados, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    CAMINHO_CSV = BASE_DIR / "data" / "medicamentos.csv"
    CAMINHO_JSON = BASE_DIR / "data" / "solidificados.json"

    processar_csv_anvisa(CAMINHO_CSV, CAMINHO_JSON)