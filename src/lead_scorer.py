"""
src/lead_scorer.py

Camada de scoring determinístico ("score objetivo") do Lead Scoring.

Combina dois grupos de critérios, sem qualquer chamada de rede ou IA:

1. Estado do site (árvore de decisão, mutuamente exclusiva) — evita que
   problemas relacionados ao mesmo fator (ex.: "sem site" e "sem HTTPS")
   se somem de forma redundante e infle o score artificialmente.
2. Fatores independentes (HTTPS inválido, ausência de contato, performance)
   e perfil/ICP do nicho — cada um soma pontos isoladamente, pois
   representam sinais comerciais distintos entre si.

O resultado deste módulo é o "score_objetivo" (0 a 65), que depois é somado
ao "score_ia" (0 a 35, ver src/ai_analyzer.py) em src/pipeline.py para
formar o score_final (0 a 100). Se a IA não estiver disponível, o score
objetivo é reescalado para 0–100 (ver LeadScorer.combine).
"""

from dataclasses import dataclass

from config.settings import (
    NICHE_TIER_1,
    NICHE_TIER_2,
    NICHE_TIER_3,
    SCORE_PRIORITY_ALTA,
    SCORE_PRIORITY_MEDIA,
    SCORE_WEIGHT_PERFIL_ICP,
    SCORE_WEIGHT_PRESENCA_DIGITAL,
)
from src.site_analyzer import SiteAnalysisResult

# --------------------------------------------------------------------------
# Árvore de decisão: estado do site (mutuamente exclusivo)
# --------------------------------------------------------------------------
_PONTOS_SEM_SITE = 28
_PONTOS_SITE_INACESSIVEL = 24
_PONTOS_SITE_COM_ERRO_HTTP = 14
_PONTOS_SITE_SAUDAVEL = 0

# Fatores independentes, somáveis (avaliados só quando fazem sentido)
_PONTOS_HTTPS_INVALIDO = 6
_PONTOS_SITE_LENTO = 4
_PONTOS_SEM_CONTATO = 2

# Perfil/ICP: mutuamente exclusivo por tier de nicho (config.settings)
_PONTOS_ICP_TIER_1 = SCORE_WEIGHT_PERFIL_ICP  # 25 — produto físico
_PONTOS_ICP_TIER_2 = round(SCORE_WEIGHT_PERFIL_ICP * 0.6)  # 15 — serviço c/ agendamento
_PONTOS_ICP_TIER_3 = round(SCORE_WEIGHT_PERFIL_ICP * 0.32)  # 8  — serviço profissional

_MAX_SCORE_OBJETIVO = SCORE_WEIGHT_PRESENCA_DIGITAL + SCORE_WEIGHT_PERFIL_ICP  # 65


@dataclass
class ScoringResult:
    """Resultado final do Lead Scoring para um lead."""

    score_objetivo: int  # 0–65, determinístico (estado do site + ICP)
    score_ia: int  # 0–35, ou 0 se a IA não rodou
    score_final: int  # 0–100 (reescalado se ia_disponivel=False)
    prioridade: str  # "🔥 Alta" | "🟡 Média" | "🟢 Baixa"
    motivos: list[str]
    ia_disponivel: bool


class LeadScorer:
    """Calcula o score objetivo (determinístico) e combina com o score da IA."""

    @staticmethod
    def _pontuar_estado_site(analysis: SiteAnalysisResult) -> tuple[int, list[str]]:
        """Árvore de decisão mutuamente exclusiva sobre o estado do site.

        Cada lead cai em exatamente um destes ramos — nunca soma mais de
        um, para não inflar o score com problemas relacionados ao mesmo
        fator (ex.: um lead sem site não também ganha pontos de "HTTPS
        ausente", já que essa checagem nem se aplica a ele).
        """
        if not analysis.has_site:
            return _PONTOS_SEM_SITE, [f"+{_PONTOS_SEM_SITE} — Sem site cadastrado"]

        site_inacessivel = analysis.error in {"timeout", "connection_error"} or (
            bool(analysis.error) and "unreachable" in analysis.error
        )
        if site_inacessivel:
            return (
                _PONTOS_SITE_INACESSIVEL,
                [f"+{_PONTOS_SITE_INACESSIVEL} — Site fora do ar/inacessível"],
            )

        if analysis.is_http_error:
            return (
                _PONTOS_SITE_COM_ERRO_HTTP,
                [
                    f"+{_PONTOS_SITE_COM_ERRO_HTTP} — Site com erro HTTP "
                    f"(status={analysis.status_code})"
                ],
            )

        return _PONTOS_SITE_SAUDAVEL, []

    @staticmethod
    def _pontuar_fatores_independentes(
        lead: dict, analysis: SiteAnalysisResult
    ) -> tuple[int, list[str]]:
        """Fatores somáveis, avaliados apenas quando aplicáveis ao lead.

        HTTPS e lentidão só fazem sentido se o site respondeu (mesmo que
        via fallback ignorando SSL) — por isso `site_avaliavel` checa
        `status_code is not None`. Ausência de contato é independente do
        site e vale para qualquer lead.
        """
        pontos = 0
        motivos: list[str] = []

        site_avaliavel = analysis.has_site and analysis.status_code is not None
        if site_avaliavel and (not analysis.is_https or not analysis.ssl_valid):
            pontos += _PONTOS_HTTPS_INVALIDO
            motivos.append(f"+{_PONTOS_HTTPS_INVALIDO} — HTTPS ausente ou inválido")

        if site_avaliavel and analysis.is_slow:
            pontos += _PONTOS_SITE_LENTO
            motivos.append(f"+{_PONTOS_SITE_LENTO} — Site com resposta lenta")

        if not lead.get("telefone"):
            pontos += _PONTOS_SEM_CONTATO
            motivos.append(f"+{_PONTOS_SEM_CONTATO} — Sem telefone/contato cadastrado")

        return pontos, motivos

    @staticmethod
    def _pontuar_icp(nicho: str) -> tuple[int, list[str]]:
        """Pontuação de perfil/ICP, mutuamente exclusiva por tier de nicho."""
        if nicho in NICHE_TIER_1:
            return (
                _PONTOS_ICP_TIER_1,
                [f"+{_PONTOS_ICP_TIER_1} — Nicho prioridade 1 do ICP (produto físico)"],
            )
        if nicho in NICHE_TIER_2:
            return (
                _PONTOS_ICP_TIER_2,
                [f"+{_PONTOS_ICP_TIER_2} — Nicho prioridade 2 do ICP (serviço c/ agendamento)"],
            )
        if nicho in NICHE_TIER_3:
            return (
                _PONTOS_ICP_TIER_3,
                [f"+{_PONTOS_ICP_TIER_3} — Nicho prioridade 3 do ICP (serviço profissional)"],
            )
        return 0, []

    @classmethod
    def score_objetivo(
        cls, lead: dict, analysis: SiteAnalysisResult
    ) -> tuple[int, list[str]]:
        """Calcula o score determinístico (0–65) e a lista de motivos legíveis."""
        pontos_site, motivos_site = cls._pontuar_estado_site(analysis)
        pontos_extra, motivos_extra = cls._pontuar_fatores_independentes(lead, analysis)
        pontos_icp, motivos_icp = cls._pontuar_icp(lead.get("nicho", ""))

        total = min(pontos_site + pontos_extra + pontos_icp, _MAX_SCORE_OBJETIVO)
        return total, motivos_site + motivos_extra + motivos_icp

    @staticmethod
    def _prioridade(score_final: int) -> str:
        if score_final >= SCORE_PRIORITY_ALTA:
            return "🔥 Alta"
        if score_final >= SCORE_PRIORITY_MEDIA:
            return "🟡 Média"
        return "🟢 Baixa"

    @classmethod
    def combine(
        cls,
        score_objetivo: int,
        score_ia: int,
        motivos_objetivo: list[str],
        motivos_ia: list[str],
        ia_disponivel: bool,
    ) -> ScoringResult:
        """Combina score objetivo + IA em um score final de 0–100.

        Se a IA não rodou (indisponível, erro, timeout), reescala o score
        objetivo (0–65) para 0–100 em vez de penalizar o lead pela
        ausência da IA — a intenção é que a nota reflita "o quanto o lead
        parece bom" e não "quantos componentes conseguimos rodar".
        """
        if ia_disponivel:
            score_final = min(score_objetivo + score_ia, 100)
        else:
            score_final = (
                round((score_objetivo / _MAX_SCORE_OBJETIVO) * 100)
                if _MAX_SCORE_OBJETIVO
                else 0
            )

        return ScoringResult(
            score_objetivo=score_objetivo,
            score_ia=score_ia if ia_disponivel else 0,
            score_final=score_final,
            prioridade=cls._prioridade(score_final),
            motivos=motivos_objetivo + (motivos_ia if ia_disponivel else []),
            ia_disponivel=ia_disponivel,
        )