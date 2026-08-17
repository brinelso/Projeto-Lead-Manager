"""
teste_gemini.py

Script isolado, descartável, só para validar que a API key do Gemini e o
SDK google-genai estão funcionando ANTES de rodar o pipeline completo do
b2b-leads-miner. Não faz parte da aplicação — pode apagar depois de testar.

Como rodar:
    python teste_gemini.py
"""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()  # lê o arquivo .env na raiz do projeto

api_key = os.environ.get("GEMINI_API_KEY", "")

if not api_key:
    print("❌ GEMINI_API_KEY não encontrada.")
    print("   Verifique se existe um arquivo .env na raiz do projeto com a linha:")
    print("   GEMINI_API_KEY=sua_chave_aqui")
    raise SystemExit(1)

print(f"🔑 Chave encontrada (começa com: {api_key[:6]}...). Testando conexão...")

try:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents="Responda apenas com a palavra: funcionando",
    )
    print("✅ Conexão com o Gemini OK!")
    print(f"   Resposta do modelo: {response.text.strip()}")

except Exception as exc:  # noqa: BLE001 - script de teste, queremos ver qualquer erro
    print(f"❌ Falha ao chamar a API do Gemini: {exc}")
    print("   Possíveis causas: chave incorreta, projeto sem a API ativada,")
    print("   ou limite de requisições atingido.")
    raise SystemExit(1)