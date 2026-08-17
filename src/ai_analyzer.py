"""
src/ai_analyzer.py

Camada de análise qualitativa via IA (Google Gemini). Complementa o score
determinístico de src/lead_scorer.py com uma leitura qualitativa baseada
SOMENTE nos dados que já existem no pipeline — a IA não deve inventar fatos
externos sobre a empresa (ex.: não presume expansão, contratações, faturamento).

Se a chamada falhar por qualquer motivo (API indisponível, timeout, quota
excedida, resposta fora do formato/limites esperados), analyze() retorna None
e src/pipeline.py usa apenas o score objetivo, reescalado para 0–100
(ver LeadScorer.combine) — a IA nunca derruba o pipeline.
"""

import json
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from config.settings import AI_MODEL, AI_TIMEOUT_SECONDS, GEMINI_API_KEY, SCORE_WEIGHT_IA
from src.logger import get_logger
from src.prompts import SYSTEM_INSTRUCTION, build_prompt

logger = get_logger(__name__)

# Conversão da nota da IA (0-10) para pontos de score_ia (soma = SCORE_WEIGHT_IA)
_PESO_POTENCIAL_COMERCIAL = 15
_PESO_ADERENCIA_SCITEC = 12
_PONTOS_FIXOS_IA_RODOU = SCORE_WEIGHT_IA - _PESO_POTENCIAL_COMERCIAL - _PESO_ADERENCIA_SCITEC  # 8

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "potencial_comercial": {"type": "integer"},
        "aderencia_scitec": {"type": "integer"},
        "possivel_oportunidade": {"type": "string"},
        "justificativa": {"type": "string"},
        "confianca": {"type": "number"},
    },
    "required": [
        "potencial_comercial",
        "aderencia_scitec",
        "possivel_oportunidade",
        "justificativa",
        "confianca",
    ],
}


@dataclass
class AIAnalysisResult:
    """Resultado estruturado e validado da análise qualitativa da IA."""

    potencial_comercial: int
    aderencia_scitec: int
    possivel_oportunidade: str
    justificativa: str
    confianca: float
    score_ia: int
    motivos: list[str]


class AIAnalyzer:
    """Executa a análise qualitativa de um lead via Gemini, com fallback seguro."""

    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = AI_MODEL) -> None:
        self._enabled = bool(api_key)
        self._model = model
        if self._enabled:
            self._client = genai.Client(
                api_key=api_key,
                # timeout em milissegundos, conforme types.HttpOptions do SDK
                http_options=types.HttpOptions(timeout=AI_TIMEOUT_SECONDS * 1000),
            )

    def analyze(self, lead_data: dict) -> Optional[AIAnalysisResult]:
        """Analisa um lead e devolve AIAnalysisResult, ou None em caso de falha.

        Args:
            lead_data: dict só com campos que já existem no pipeline (nome,
                nicho, categoria, motivos, has_site, is_https, is_slow).
        """
        if not self._enabled:
            logger.info("IA desabilitada (sem GEMINI_API_KEY) — usando só score objetivo.")
            return None

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=build_prompt(lead_data),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                ),
            )
            return self._parse(response.text)

        except Exception as exc:  # noqa: BLE001 - IA não deve derrubar o pipeline
            logger.warning(
                "Falha na análise de IA para '%s': %s", lead_data.get("nome"), exc
            )
            return None

    @staticmethod
    def _parse(raw_json: str) -> Optional[AIAnalysisResult]:
        """Valida o formato e os limites dos campos antes de aceitar a resposta."""
        try:
            data = json.loads(raw_json)

            potencial = int(data["potencial_comercial"])
            aderencia = int(data["aderencia_scitec"])
            confianca = float(data["confianca"])

            limites_ok = (
                0 <= potencial <= 10 and 0 <= aderencia <= 10 and 0 <= confianca <= 1
            )
            if not limites_ok:
                logger.warning("Resposta da IA fora dos limites esperados: %s", data)
                return None

            score_variavel = (potencial / 10) * _PESO_POTENCIAL_COMERCIAL + (
                aderencia / 10
            ) * _PESO_ADERENCIA_SCITEC
            score_ia = min(
                round(score_variavel * confianca) + _PONTOS_FIXOS_IA_RODOU,
                SCORE_WEIGHT_IA,
            )

            motivos = [
                f"+{score_ia} — Análise IA (potencial={potencial}/10, "
                f"aderência={aderencia}/10, confiança={confianca:.2f})"
            ]

            return AIAnalysisResult(
                potencial_comercial=potencial,
                aderencia_scitec=aderencia,
                possivel_oportunidade=str(data["possivel_oportunidade"]),
                justificativa=str(data["justificativa"]),
                confianca=confianca,
                score_ia=score_ia,
                motivos=motivos,
            )

        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("JSON da IA inválido/incompleto: %s (%s)", raw_json, exc)
            return None
