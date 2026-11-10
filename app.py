"""
    InfoMed Core API - Servidor REST de Escuta Síncrona
    Responsável por receber os payloads da UI do Bubble, persistir os inputs,
    chamar o orquestrador farmacêutico e retornar o prontuário estruturado.
"""

import os, sys, json, logging, httpx, requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 🚀 CONFIGURAÇÃO DE REDE DA AUTOMAÇÃO LOCAL REFEITA CORRETAMENTE
N8N_WEBHOOK_URL = "http://127.0.0.1:5678/webhook-test/logsRegistros"

# 1. MAPEAMENTO DE PASTAS ABSOLUTAS DO SISTEMA
APP_DIR = Path(__file__).resolve().parent
CORE_DIR = APP_DIR / "core"
DATA_DIR = APP_DIR / "data"
DB_LOCAL_PATH = DATA_DIR / "solidificados.json"

# Injeta a pasta core e a raiz no path do sistema para avoid erros de ImportError
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

# Configuração de CORS (Obrigatório para o Bubble conseguir fazer as API Calls sem bloqueio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite requisições de qualquer origem (emuladores e web)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================================
# 3. SCHEMAS DE VALIDAÇÃO DE ENTRADA (Contratos com API Connectors)
# =====================================================================

class ProntuarioRawPayload(BaseModel):
    """
    Contrato unificado e dinâmico mapeado diretamente a partir das tabelas 
    Paciente e User do Bubble, eliminando dados estáticos de contingência.
    """
    patient_id: str
    batch_id: str
    patient_name: str
    patient_phone: str          
    responsible_name: str       
    responsible_phone: str      
    medications: List[Dict[str, Any]]
    existing_medications: List[Dict[str, Any]]


class WebhookPayload(BaseModel):
    """
    Contrato adaptado para o fluxo de automação do n8n.
    Mapeia de forma inteligente tanto 'salvar' quanto 'guardar' e aceita metadados específicos.
    """
    texto: str
    tipo: str
    horario: datetime  # O Pydantic transforma strings como "2026-11-06 08:00:00" em datetime automaticamente
    guardar: Any = Field(True, alias="salvar")  # Intercepta 'salvar' do Bubble e mapeia para 'guardar' do n8n
    dados_especificos: Optional[Dict[str, Any]] = None  # Espaço para enviar IDs de pacientes, remédios, etc.

    class Config:
        populate_by_name = True  # Permite que a API aceite tanto a palavra 'salvar' quanto 'guardar'

    def normalizar_guardar(self) -> bool:
        """Converte strings flexíveis como 'True', 'true' ou '1' vindas do n8n/Bubble em booleanos puros."""
        if isinstance(self.guardar, str):
            return self.guardar.lower() in ('true', '1', 't', 'yes')
        return bool(self.guardar)


# =====================================================================
# 4. ROTAS / ENDPOINTS
# =====================================================================

@app.get("/", status_code=status.HTTP_200_OK)
def ping():
    """Rota simples para o Bubble verificar se o servidor backend está online."""
    return {
        "status": "online",
        "servico": "InfoMed Core API",
        "ambiente": "Desenvolvimento/Faculdade"
    }


def disparar_automacao_n8n(texto: str, tipo: str, dados_clinicos: dict):
    """
    Função auxiliar executada em segundo plano para despachar os dados para o n8n.
    O uso do requests padrão com IP limpa o cache de resolução de DNS do Windows.
    """
    payload_n8n = {
        "texto": texto,
        "tipo": tipo,
        "horario": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "guardar": "True",  # Alinhado exatamente com o nó 'If1' do seu n8n
        "dados_especificos": dados_clinicos
    }
    
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload_n8n, timeout=5.0)
        if response.status_code == 200:
            logger.info(f"[n8n] Sucesso! Automação disparada para o tipo: {tipo}")
        else:
            logger.warning(f"[n8n] Erro de comunicação com o n8n. Código: {response.status_code}")
    except Exception as e:
        logger.error(f"[n8n] Falha ao tentar conectar com o n8n: {str(e)}")

# Handler para interceptar erros 422 e mostrar o culpado nos logs do console
@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc):
    logger.error(f"❌ FALHA DE VALIDAÇÃO DO BUBBLE: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "mensagem": "O contrato enviado pelo Bubble possui campos divergentes."}
    )


@app.post("/medications/sync", status_code=status.HTTP_200_OK)
def receber_e_tratar_medicamentos(payload: ProntuarioRawPayload, background_tasks: BackgroundTasks):
    """
    Endpoint principal de escuta adaptado para o contrato do Bubble API Connector.
    """
    logger.info(f"Conexão REST estabelecida para o Lote {payload.batch_id} do Paciente ID: {payload.patient_id} - {payload.patient_name}")
    
    input_temp_file = DATA_DIR / f"usuario_raw_input_{payload.patient_id}.json"
    output_temp_file = DATA_DIR / f"usuario_atualizado_{payload.patient_id}.json"
    
    if not DB_LOCAL_PATH.exists():
        logger.error(f"Arquivo de banco local não encontrado em: {DB_LOCAL_PATH}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro de Infraestrutura: Base de dados solidificados.json ausente no servidor."
        )

    try:
        lista_completa_medicamentos = []
        if payload.medications:
            lista_completa_medicamentos.extend(payload.medications)
        if payload.existing_medications:
            lista_completa_medicamentos.extend(payload.existing_medications)
            
        dados_legados_adaptados = {
            "paciente_id": payload.patient_id,
            "nome_paciente": payload.patient_name,
            "tel_paciente": payload.patient_phone,       
            "responsavel": payload.responsible_name,     
            "tel_responsavel": payload.responsible_phone, 
            "medicamentos": lista_completa_medicamentos,
        }

        with open(input_temp_file, 'w', encoding='utf-8') as f:
            json.dump(dados_legados_adaptados, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Dados brutos gravados em cache. Acionando orquestrador em core/ui_tratamento.py...")

        prontuario_final_categorizado = processar_tratamento_completo(
            usuario_json_path=str(input_temp_file),
            db_json_path=str(DB_LOCAL_PATH),
            output_json_path=str(output_temp_file)
        )
        
        chaves_gavetas = ["remedio_solidos", "remedio_liquidos", "remedio_injetavel", "remedio_colirio", "nao_identificados"]
        for chave_gaveta in chaves_gavetas:
            if chave_gaveta in prontuario_final_categorizado and isinstance(prontuario_final_categorizado[chave_gaveta], list):
                for remedio in prontuario_final_categorizado[chave_gaveta]:
                    if "efeitos_colaterais" not in remedio and "detalhes" in remedio:
                        remedio["efeitos_colaterais"] = remedio["detalhes"]
                    elif "efeitos_colaterais" not in remedio:
                        remedio["efeitos_colaterais"] = ""
                    remedio["gaveta_nome"] = chave_gaveta

        if "alertas_incompatibilidade" not in prontuario_final_categorizado or not prontuario_final_categorizado["alertas_incompatibilidade"]:
            prontuario_final_categorizado["alertas_incompatibilidade"] = []

        # =====================================================================
        # 🚀 DISPARO AUTOMÁTICO EM BACKGROUND PARA O n8n LOCAL
        # =====================================================================
        alertas = prontuario_final_categorizado.get("alertas_incompatibilidade", [])
        if alertas:
            texto_alerta = f"Risco Clínico Detectado para o paciente {payload.patient_name}."
            background_tasks.add_task(disparar_automacao_n8n, texto_alerta, "alerta_critico", {"paciente_id": payload.patient_id, "alertas": alertas})
        else:
            texto_sucesso = f"Triagem finalizada sem alertas graves para {payload.patient_name}."
            background_tasks.add_task(disparar_automacao_n8n, texto_sucesso, "log_operacional", {"paciente_id": payload.patient_id})
        # =====================================================================

        logger.info(f"Pipeline concluído com sucesso para o paciente {payload.patient_id}. Enviando resposta...")
        return prontuario_final_categorizado
    
    except json.JSONDecodeError as jde:
        logger.error(f"Erro de decodificação na resposta da IA: {jde}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Erro de JSON na resposta da IA.")
    except Exception as e:
        logger.error(f"Falha crítica interna no pipeline: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno no processamento: {str(e)}")
    finally:
        if input_temp_file.exists():
            try:
                os.remove(input_temp_file)
            except Exception:
                pass


@app.post("/webhook/logsRegistros", status_code=status.HTTP_200_OK)
def receber_webhook(payload: WebhookPayload):
    """
    Endpoint para recepção, mapeamento e persistência síncrona de eventos externos do Bubble/n8n.
    """
    deve_salvar = payload.normalizar_guardar()
    logger.info(f"Webhook interceptado pelo Core. Tipo: {payload.tipo} | Persistir em disco: {deve_salvar}")

    try:
        # Monta a resposta estruturada contendo as informações bases e dados clínicos opcionais
        resposta_evento = {
            "texto": payload.texto,
            "tipo": payload.tipo,
            "horario_evento": payload.horario.strftime("%Y-%m-%d %H:%M:%S"),
            "dados_especificos": payload.dados_especificos,
            "recebido_em_api": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Executa a persistência local ordenada na pasta /data caso 'guardar/salvar' seja True
        if deve_salvar:
            webhook_log_path = DATA_DIR / "webhook_events.json"
            historico = []

            # Se o arquivo já existir, recupera a lista antes do append
            if webhook_log_path.exists():
                try:
                    with open(webhook_log_path, "r", encoding="utf-8") as f:
                        historico = json.load(f)
                        if not isinstance(historico, list):
                            historico = []
                except Exception:
                    historico = []

            historico.append(resposta_evento)

            # Grava no disco de forma limpa (identado e sem caracteres com escape)
            with open(webhook_log_path, "w", encoding="utf-8") as f:
                json.dump(historico, f, ensure_ascii=False, indent=4)
            
            logger.info(f"Metadados específicos do webhook registrados em: {webhook_log_path}")

        return {
            "status": "sucesso",
            "mensagem": "Logs registrados",  # Alinhado com a resposta de sucesso esperada pelo nó n8n
            "dados": resposta_evento
        }

    except Exception as e:
        logger.error(f"Falha crítica ao executar o tratamento do webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha interna no ecossistema da API InfoMed: {str(e)}"
        )


# =====================================================================
# 5. INICIALIZADOR DO SERVIDOR (Execução local via terminal)
# =====================================================================
if __name__ == "__main__":
    import uvicorn
    # Liga o servidor na porta 8080 apontando para o proxy de rede do PowerShell.
    # O parâmetro 'reload=True' atualiza o servidor automaticamente ao alterar o arquivo.
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)
