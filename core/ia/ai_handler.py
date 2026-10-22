"""
Esse arquivo serve como chamada para as IAs gemini ou groq
o intuido é que essa chamada seja reutilizavel 
"""
import os, logging, json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq
from typing import Generator, Union
from pathlib import Path

# Mapeia o diretorio em busca do .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
logger = logging.getLogger(__name__)

"""
Classe auxiliar para padronizar as respostas da Groq
permitindo que usem a sintaxe 'chunk.text' idêntica à do Gemini.
"""
class TextChunk:
    def __init__(self, text: str):
        self.text = text

# Função principal
class AIHandler:
    def __init__(self):
        self.api_key_gemini = os.getenv("GEMINI_API_KEY")
        self.api_key_groq = os.getenv("GROQ_API_KEY")
        
        
        self.client_gemini = genai.Client(api_key=self.api_key_gemini) if self.api_key_gemini else None
        self.client_groq = Groq(api_key=self.api_key_groq) if self.api_key_groq else None
        
        
        # lista do melhor para o pior de modelos que melhor respondeu
        """
        gemini-2.5-Flash
        gemini-flash-latest
        gemini-3.8-flash
        gemini-3.6-flash
        gemini-3.1-flash-lite
        gemini-2.5-flash-lite
        """
        self.gemini_disponivel = True
        self.gemini_models = [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite"
        ]
        self.modelo_gemini = self.gemini_models[0]
        # Caso gemini não responda
        self.modelo_groq = "openai/gpt-oss-120b"
        
        self._verificar_apis()

    def _verificar_apis(self):
        # Verifica se a API do Gemini está respondendo
        if not self.client_gemini:
            self.gemini_disponivel = False
            logger.warning("Att! Chave do Gemini não encontrada. Groq em standby.")
            return

        try:
            # Teste rápido de conectividade no Gemini
            self.client_gemini.models.generate_content(
                model=self.modelo_gemini,
                contents="ping"
            )
            logger.info("Sys: Gemini OK.")
        except Exception as e:
            self.gemini_disponivel = False
            logger.warning(f"Sys: Gemini nada ({e}). Alternando para Groq.")

    def gerar_resposta(self, prompt_sistema: str, pergunta: str) -> Union[Generator, str]:
        # Roteamento resiliente: Gemini (Principal) -> Groq (Suporte).
        
        # 1. TENTA GEMINI PRIMEIRO
        if self.gemini_disponivel:
            try:
                stream = self._chamar_gemini_stream(prompt_sistema, pergunta)

                def gerador_seguro():
                    try:
                        for chunk in stream:
                            yield chunk
                    except Exception as e:
                        logger.error(f"Erro ao ler stream do Gemini ({e}). Alternando para a Groq...")
                        self.gemini_disponivel = False
                        
                        # Consome o fallback da Groq usando TextChunk
                        backup = self._chamar_groq(prompt_sistema, pergunta)
                        if isinstance(backup, Generator):
                            yield from backup
                        else:
                            yield TextChunk(backup)

                return gerador_seguro()

            except Exception as e:
                self.gemini_disponivel = False
                logger.error(f"Falha na inicialização do stream Gemini: {e}. Tentando Groq...")

        # 2. SE GEMINI ESTIVER DESATIVADO OU FALHAR DE INÍCIO, USA GROQ
        return self._chamar_groq(prompt_sistema, pergunta)
    
    def _chamar_gemini_stream(self, prompt_sistema: str, pergunta: str) -> Generator:
        """Tenta iterar pelos modelos do Gemini em ordem de preferência antes de desistir."""
        config = types.GenerateContentConfig(
            system_instruction=prompt_sistema
        )
        
        ultimo_erro = None
        for modelo in self.gemini_models:
            try:
                logger.info(f"Tentando Gemini Cloud com o modelo: {modelo}...")
                stream = self.client_gemini.models.generate_content_stream(
                    model=modelo,
                    contents=pergunta,
                    config=config
                )
                # Se deu certo, consome o stream e sai do loop
                for chunk in stream:
                    yield chunk
                return  # Sucesso total, encerra a função
                
            except Exception as e:
                ultimo_erro = e
                logger.warning(f"⚠️ O modelo {modelo} falhou/indisponível ({e}). Tentando o próximo da lista...")
        
        # Se esgotar todos os modelos do Gemini, propaga o erro para o fallback da Groq assumir
        raise Exception(f"Todos os modelos do Gemini falharam. Último erro: {ultimo_erro}")

    def _chamar_groq(self, prompt_sistema: str, pergunta: str) -> Union[Generator, str]:
        """Fallback utilizando a Groq (Cloud)."""
        if not self.client_groq:
            logger.error("Ambas as APIs falharam ou chaves não estão configuradas no .env.")
            return "Desculpe, estou enfrentando instabilidades no momento e nenhum serviço de IA pôde responder."

        logger.info(f"Usando Groq Cloud ({self.modelo_groq}) como fallback...")
        try:
            stream = self.client_groq.chat.completions.create(
                model=self.modelo_groq,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": pergunta}
                ],
                stream=True,
            )

            def groq_wrapper():
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta:
                        texto = chunk.choices[0].delta.content
                        if texto:
                            yield TextChunk(texto)

            return groq_wrapper()

        except Exception as e:
            logger.error(f"Groq Fallback também falhou: {e}")
            return "Serviços de inteligência artificial estão indisponíveis no momento."