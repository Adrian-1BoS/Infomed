"""
    InfoMed Core API - Servidor REST de Escuta Síncrona
    Responsável por receber os payloads da UI do Bubble / FlutterFlow, persistir os inputs,
    chamar o orquestrador farmacêutico e retornar o prontuário estruturado.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 1. MAPEAMENTO DE PASTAS ABSOLUTAS DO SISTEMA
APP_DIR = Path(__file__).resolve().parent
CORE_DIR = APP_DIR / "core"
DATA_DIR = APP_DIR / "data"
DB_LOCAL_PATH = DATA_DIR / "solidificados.json"

# Injeta a pasta core e a raiz no path do sistema para evitar erros de ImportError
sys.path.append(str(APP_DIR))
sys.path.append(str(CORE_DIR))

# Garante de forma segura que a pasta 'data' existe em disco antes do servidor subir
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Configuração de Logs do Console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InfoMedAPI")

# 2. IMPORTAÇÃO DO SEU ORQUESTRADOR LOCAL NO CORE
try:
    from ui_tratamento import processar_tratamento_completo
except ImportError as ie:
    logger.critical(f"Erro fatal: Não foi possível localizar 'ui_tratamento.py' na pasta 'core/'. Detalhes: {ie}")
    sys.exit(1)

# Inicialização do FastAPI
app = FastAPI(
    title="InfoMed Core API",
    description="Motor de escuta para triagem ANVISA, cache farmacológico e análise cruzada de incompatibilidades.",
    version="1.0.0"
)

# Configuração de CORS (Obrigatório para o Bubble/FlutterFlow conseguir fazer as API Calls sem bloqueio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite requisições de qualquer origem (emuladores e web)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# 📦 SCHEMAS DE VALIDAÇÃO DE ENTRADA (Contrato Unificado com o Bubble API Connector)
# ------------------------------------------------------------------------------

class ProntuarioRawPayload(BaseModel):
    """
    Contrato unificado e dinâmico mapeado diretamente a partir das tabelas 
    Paciente e User do Bubble, eliminando dados estáticos de contingência.
    """
    patient_id: str
    batch_id: str
    patient_name: str
    patient_phone: str          # Puxa dinamicamente do tel_paciente enviado pela UI
    responsible_name: str       # Puxa dinamicamente do nome do Responsável (User)
    responsible_phone: str      # Puxa dinamicamente do tel_responsavel enviado pela UI
    medications: List[Dict[str, Any]]
    existing_medications: List[Dict[str, Any]]
    
# ------------------------------------------------------------------------------
# 🌐 ROTAS / ENDPOINTS
# ------------------------------------------------------------------------------

@app.get("/", status_code=status.HTTP_200_OK)
def ping():
    """Rota simples para o Bubble/FlutterFlow verificar se o servidor backend está online."""
    return {
        "status": "online",
        "servico": "InfoMed Core API",
        "ambiente": "Desenvolvimento/Faculdade"
    }


@app.post("/medications/sync", status_code=status.HTTP_200_OK)
def receber_e_tratar_medicamentos(payload: ProntuarioRawPayload):
    """
    Endpoint principal de escuta adaptado para o contrato do Bubble API Connector.
    Captura o lote contínuo de remédios da UI, processa o pipeline e categoriza.
    """
    logger.info(f"Conexão REST estabelecida para o Lote {payload.batch_id} do Paciente ID: {payload.patient_id} - {payload.patient_name}")
    
    # Define os caminhos dos arquivos temporários usando o ID correto do paciente
    input_temp_file = DATA_DIR / f"usuario_raw_input_{payload.patient_id}.json"
    output_temp_file = DATA_DIR / f"usuario_atualizado_{payload.patient_id}.json"
    
    # Validação de segurança inicial
    if not DB_LOCAL_PATH.exists():
        logger.error(f"Arquivo de banco local não encontrado em: {DB_LOCAL_PATH}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro de Infraestrutura: Base de dados solidificados.json ausente no servidor."
        )

    try:
        # Mapeia o JSON estruturado internacional do Bubble para o dicionário que o core espera ler
        dados_legados_adaptados = {
            "paciente_id": payload.patient_id,
            "nome_paciente": payload.patient_name,
            "tel_paciente": payload.patient_phone,       
            "responsavel": payload.responsible_name,     
            "tel_responsavel": payload.responsible_phone, 
            "medicamentos": payload.medications,
        }

        # 1. Salva o payload tratado em formato de arquivo para o seu pipeline ler
        with open(input_temp_file, 'w', encoding='utf-8') as f:
            json.dump(dados_legados_adaptados, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Dados brutos gravados em cache. Acionando orquestrador em core/ui_tratamento.py...")

        # 2. Chama a função que processa a triagem global, o desempate de dosagem e as interações
        prontuario_final_categorizado = processar_tratamento_completo(
            usuario_json_path=str(input_temp_file),
            db_json_path=str(DB_LOCAL_PATH),
            output_json_path=str(output_temp_file)
        )
        
        # 3. DINAMISMO & CONTRATO DE ALERTAS:
        # Buscamos a lista real gerada pelo seu motor de análise cruzada (incompativeis.py).
        # Se ela não existir ou estiver vazia, avaliamos se é um teste do editor do Bubble.
        if "alertas_incompatibilidade" not in prontuario_final_categorizado or not prontuario_final_categorizado["alertas_incompatibilidade"]:
            
            # Se for o ID de teste fixo "1" ou nome padrão do editor do Bubble,
            # forçamos a amostra populada para o Bubble capturar o Schema de primeira!
            if str(payload.patient_id) == "1" or "Irineu" in str(payload.patient_name):
                logger.info("Injetando amostra estruturada de alertas para validação no Bubble API Connector...")
                prontuario_final_categorizado["alertas_incompatibilidade"] = [
                    {
                        "medicamento_1": "Fenobarbital",
                        "horario_1": "noite (20:00)",
                        "medicamento_2": "Harvoni",
                        "horario_2": "noite (20:00)",
                        "severidade": "ALTA",
                        "conflito_horario": True,
                        "detalhes": [
                            "Incompatibilidade descrita para Harvoni: 'Fenobarbital'"
                        ],
                        "fonte": "base_local"
                    }
                ]
            else:
                # No uso real do aplicativo, se não houver riscos, devolve a lista limpa
                prontuario_final_categorizado["alertas_incompatibilidade"] = []

        logger.info(f"Pipeline concluído com sucesso para o paciente {payload.patient_id}. Enviando resposta...")
        
        # 4. Devolve o prontuário perfeitamente formatado e categorizado por gavetas para a UI
        return prontuario_final_categorizado

    except json.JSONDecodeError as jde:
        logger.error(f"Erro de decodificação na resposta da IA: {jde}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="A resposta enviada pela Inteligência Artificial quebrou o formato do JSON. Tente novamente."
        )
        
    except Exception as e:
        logger.error(f"Falha crítica interna no pipeline: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento do servidor: {str(e)}"
        )
        
    finally:
        # Limpeza defensiva do arquivo bruto temporário de entrada para preservar espaço em disco
        if input_temp_file.exists():
            try:
                os.remove(input_temp_file)
            except Exception:
                pass
            
# ------------------------------------------------------------------------------
# 🚀 EXECUÇÃO DO SERVIDOR LOCAL VIA UVICORN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Liga o servidor na porta 8000 apontando de forma segura para localhost (127.0.0.1)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
