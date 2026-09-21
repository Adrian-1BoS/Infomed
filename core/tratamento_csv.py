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
    injetaveis_key =[' INJ', 'SOL INJ', 'SUSP INJ', ' FRASCO AMPOLA ',' FA ',' SER ',' SERINGA ', ' CANETA ', ' CANETAS ']
    liquido_key = ['XPE', 'GOTAS','XAROPE', 'SUSP','EMU', 'SOLUCAO', 'SUSPENSAO', 'SOL OR']
    solidos_key = ['COMP', 'CAP', 'DRG', 'PILULA', 'SACHE', 'TABLETE','PASTILHA','POM', 'CREME','POMADA', 'GEL']
    
    # se palavra chave (kw) na apresentação (coluna J) == kw em alguma das 3, atribui-la a mesma
    if any(kw in apres for kw in injetaveis_key):
        return 'injetavel'
    elif any(kw in apres for kw in liquido_key):
        return 'liquido'
    elif any(kw in apres for kw in solidos_key):
        return 'solido'
    else:
        return 'solido'

# aproveita no csv e extrai a dosagem presente lá.
def dosagem(apresentacao):
    apres = str(apresentacao)
    
    # caso liquido, pega a dosagem (numero antecessor ao mg/ml)
    # re.search == busca ___ r== py não leia os comandos (o regex formata) \d+ busca x numeros até batem em \., (se for decimal depois \d+) ou até bater em algo que não é numero e o re.IGNORECASE == não diferencie maiusculo de minusculo
    match_mg_ml = re.search(r'(\d+(?:[\.,]\d+)?)\s*MG/ML', apres, re.IGNORECASE)
    if match_mg_ml:
        return float(match_mg_ml.group(1).replace(',', '.')), 'mg_ml'
    
    # caso solido, pega a dosagem (numero antecessor ao mg)
    # mesmo tratamento do mg/ml
    match_mg = re.search(r'(\d+(?:[\.,]\d+)?)\s*MG\b', apres, re.IGNORECASE)
    if match_mg:
        return float(match_mg.group(1).replace(',', '.')), 'mg'
    
    # caso não tenha a dosagem (ou não indentificado) retorna none
    return None, None

"""
no .csv as substancias são separadaspor ";" aqui, transformamos em lista
e separamos no .json
"""
def tratar_substancias(substancia_raw):
    subst_str = str(substancia_raw).strip()
    if not subst_str or subst_str.lower() in ['nan', 'none', '']:
        return []
    
    return [s.strip().title() for s in subst_str.split(';') if s.strip()] 

def cod_anvisa(classe_terapeutica):
    cod = str(classe_terapeutica)
    # ^ == inicia pelo primeiro caractere \w+ == busca qualquer valor alfanumerico (numero e letra) e termina em -
    match_cod = re.search(r'^(\w+)\s*-', cod, re.IGNORECASE)
    
    if match_cod:
        return match_cod.group(1)  # Retorna o que foi capturado dentro do parêntese
    return None

# na coluna classe terapeutica, depois do codigo xxxx - (area atuação) tem o ifem - que separa o codigo da descrição
def descricao_area_atuacao(classe_terapeutica):
    texto = str(classe_terapeutica)
    if " - " in texto:
        return texto.split(" - ", 1)[1].strip()
    return texto.strip()
    
    
def processar_csv_anvisa(caminho_csv, caminho_output_json):
    # Mudado para teclas encoding='utf-8' (padrão br para acentuação)
    try:
        df = pd.read_csv(caminho_csv, sep=';', encoding='utf-8', dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(caminho_csv, sep=';', encoding='utf-8-sig', dtype=str)
    
    df.columns = df.columns.str.strip()
    
    #cria as respeqtivas areas para preencher dendro do colchete como visto no solidificados.json
    remedio_solido = []
    remedio_liquido = []
    remedio_injetavel = []
    
    # cria um id para cada remedio do .json 
    id_counter = 1

    for _, row in df.iterrows():
        
        nome_produto = str(row.get('PRODUTO', '')).strip().title()
        substancia = row.get('SUBSTÂNCIA', '')
        apresentacao = str(row.get('APRESENTAÇÃO', '')).strip()
        classe_terapeutica = row.get('CLASSE TERAPÊUTICA', '')
        # Converte a string de substâncias separadas por ';' em lista
        substancias_list = tratar_substancias(substancia)
        tipo = forma_farmaceutica(apresentacao)
        valor_dosagem, unidade = dosagem(apresentacao)
        # Nomes alternativos (se alguma das substâncias não for idêntica ao nome do produto)
        nome_alt = [s for s in substancias_list if s.upper() != nome_produto.upper()]
        
        cod_classe_terapeutica = cod_anvisa(classe_terapeutica)
        area_atuacao = descricao_area_atuacao(classe_terapeutica)
        
        if tipo == 'solido':
            item = {
                "id": id_counter,
                "nome": nome_produto,
                "substancia_ativa": substancias_list,
                "apresentacao": apresentacao,
                "mg": valor_dosagem if unidade == 'mg' else None,
                "codigo_area_atuacao": cod_classe_terapeutica,
                "area_atuacao": area_atuacao,
                "nomes_alternativos": nome_alt,
                "efeitos_colaterais": [],
                "incompatibilidades": []
            }
            remedio_solido.append(item)
            
        elif tipo == 'liquido':
            item = {
                "id": id_counter,
                "nome": nome_produto,
                "substancia_ativa": substancias_list,
                "apresentacao": apresentacao,
                "mg_ml": valor_dosagem if unidade == 'mg_ml' else None,
                "codigo_area_atuacao": cod_classe_terapeutica,
                "area_atuacao": area_atuacao,
                "nomes_alternativos": nome_alt,
                "viscosidade": "",
                "efeitos_colaterais": [],
                "incompatibilidades": []
            }
            remedio_liquido.append(item)
            
        else:  # injetaveis
            item = {
                "id": id_counter,
                "nome": nome_produto,
                "substancia_ativa": substancias_list,
                "apresentacao": apresentacao,
                "mg_ml": valor_dosagem if unidade == 'mg_ml' else None,
                "codigo_area_atuacao": cod_classe_terapeutica,
                "area_atuacao": area_atuacao,
                "nomes_alternativos": nome_alt,
                "efeitos_colaterais": [],
                "incompatibilidades": []
            }
            remedio_injetavel.append(item)
            
        id_counter += 1

    dados_consolidados = {
        "remedio_solido": remedio_solido,
        "remedio_liquido": remedio_liquido,
        "remedio_injetavel": remedio_injetavel
    }

    with open(caminho_output_json, 'w', encoding='utf-8') as f:
        json.dump(dados_consolidados, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    CAMINHO_CSV = BASE_DIR / "data" / "medicamentos.csv"
    CAMINHO_JSON = BASE_DIR / "data" / "solidificados.json"
    
    processar_csv_anvisa(CAMINHO_CSV, CAMINHO_JSON)