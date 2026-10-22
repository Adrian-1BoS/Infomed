from pathlib import Path
import json, sys, os

BASE_DIR = Path(__file__).resolve().parent
CAMINHO_IA = BASE_DIR / "core" / "ia"
sys.path.append(str(CAMINHO_IA))

from ai_handler import AIHandler

def testar_respostas_ia():
    # Inicializa o handler de IA (Groq primário, Gemini fallback)
    ai_handler = AIHandler()
    
    # Lista de 3 remédios distintos para o teste
    medicamentos_teste = [
        {
            "nome": "Fenobarbital",
            "substancias": ["Fenobarbital"]
        },
        {
            "nome": "Maleato De Enalapril",
            "substancias": ["Enalapril"]
        },
        {
            "nome": "Ibuprofeno",
            "substancias": ["Ibuprofeno"]
        }
    ]

    
    """
    Voce é um proficional farmacologico que trabalha com o Dicionário de 
    Especialidades Farmacêuticas de cor e salteado usando-o como referencia 
    absoluta em suas pesquisas e consultas e não devolve um retorno sem ter 100% de certeza de sua resposta
    sua função é retornar no foramto json o preenchimeto dessas colunas "efeitos_colaterais": [],
    "incompatibilidades": []
    sendo incompatibilidades, substancia_ativa presentes pela anvisa
    voce trara esse .json do remedio
    """
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

    print("=== INICIANDO TESTE DE RESPOSTAS DA IA (Groq / Gemini) ===")

    for med in medicamentos_teste:
        nome_med = med["nome"]
        substancias = ", ".join(med["substancias"])
        
        print(f"\nBuscando dados farmacológicos para: {nome_med} (Substâncias: {substancias})...")
        
        pergunta_farmaceutica = (
            f"Traga o JSON de efeitos colaterais e incompatibilidades para o "
            f"medicamento '{nome_med}' contendo as substâncias ativas em lista separado por virgula: {substancias}."
        )
        
        try:
            # Chama o método de geração de resposta da sua classe AIHandler
            resposta_ai = ai_handler.gerar_resposta(prompt_farmaceutico, pergunta_farmaceutica)
            
            # Trata o retorno (lidando se vier em stream / gerador ou string direta)
            texto_resposta = ""
            if hasattr(resposta_ai, '__iter__') and not isinstance(resposta_ai, str):
                for chunk in resposta_ai:
                    if hasattr(chunk, 'text') and chunk.text:
                        texto_resposta += chunk.text
            else:
                texto_resposta = str(resposta_ai)
            
            print(f"\n--- Resposta Bruta para [{nome_med}] ---")
            print(texto_resposta.strip())
            print("-" * 50)
            
        except Exception as e:
            print(f"❌ Erro ao consultar a IA para o medicamento {nome_med}: {e}")

if __name__ == "__main__":
    testar_respostas_ia()