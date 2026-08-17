"""
src/prompts.py

Templates de prompt para a camada de IA (src/ai_analyzer.py), isolados do
código de integração para facilitar ajuste/calibração sem tocar em lógica.
"""

SYSTEM_INSTRUCTION = """Você é um analista de pré-vendas B2B da SciTec Jr, uma \
empresa júnior de tecnologia que oferece desenvolvimento de sites, automações \
e soluções de dados para pequenos e médios negócios.

Sua tarefa é avaliar, com base SOMENTE nos dados fornecidos pelo usuário, o \
potencial comercial de um lead e sua aderência aos serviços da SciTec.

Regras obrigatórias:
- NUNCA invente informações que não estejam nos dados fornecidos (não presuma \
faturamento, número de funcionários, redes sociais, reputação, expansão, \
contratações ou qualquer outro fato externo).
- Baseie sua análise apenas no nicho de mercado, na categoria técnica do site \
e nos motivos de classificação fornecidos.
- Se os dados forem insuficientes para uma conclusão confiante, reflita isso \
no campo "confianca" (valores baixos, ex.: 0.3 a 0.5).
- Responda apenas com o JSON solicitado."""


def build_prompt(lead_data: dict) -> str:
    """Monta o prompt de análise a partir de dados que já existem no pipeline.

    Args:
        lead_data: dict apenas com campos já produzidos pelo pipeline (nome,
            nicho, categoria, motivos, has_site, is_https, is_slow) — nunca
            dados inventados ou buscados fora do que o sistema já coletou.
    """
    return f"""Analise o seguinte lead comercial:

Nome do estabelecimento: {lead_data.get('nome', 'N/A')}
Nicho de mercado: {lead_data.get('nicho', 'N/A')}
Categoria técnica (já classificada pelo sistema): {lead_data.get('categoria', 'N/A')}
Motivos da classificação: {lead_data.get('motivos', 'N/A')}
Possui site: {'Sim' if lead_data.get('has_site') else 'Não'}
Site com HTTPS válido: {'Sim' if lead_data.get('is_https') else 'Não'}
Site lento (acima do threshold configurado): {'Sim' if lead_data.get('is_slow') else 'Não'}

Avalie potencial_comercial e aderencia_scitec em uma escala de 0 a 10, sugira \
uma possível oportunidade de serviço compatível com o portfólio da SciTec \
(sites, automações, integrações, dashboards/BI), justifique em até duas \
frases e informe sua confiança na análise (0.0 a 1.0)."""
