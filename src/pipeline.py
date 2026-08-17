"""
src/pipeline.py

Orquestração do pipeline de prospecção, extraída para um módulo compartilhado
para que tanto o CLI (main.py) quanto a interface web (app.py) usem exatamente
a mesma lógica de negócio, evitando duplicação e divergência de comportamento.

Desde a integração do Lead Scoring, o pipeline também calcula automaticamente,
para cada lead: score objetivo (src/lead_scorer.py), análise qualitativa via
IA quando habilitada (src/ai_analyzer.py) e o score final combinado — sem
nenhuma etapa manual adicional para quem usa main.py ou app.py.
"""

from dataclasses import asdict
from typing import Callable, Optional

from src.ai_analyzer import AIAnalyzer
from src.data_exporter import COLUMN_ORDER
from src.lead_classifier import LeadClassifier
from src.lead_scorer import LeadScorer
from src.logger import get_logger
from src.overpass_client import GeocodingError, OverpassClient
from src.site_analyzer import SiteAnalyzer

logger = get_logger(__name__)

ProgressCallback = Callable[[int, int, str], None]


def run_pipeline(
    bairro: str,
    cidade: str,
    uf: str,
    niches: list[str],
    excluir_redes: bool = False,
    ai_enabled: bool = True,
    on_progress: Optional[ProgressCallback] = None,
) -> list[dict]:
    """Executa mineração -> análise técnica -> classificação -> scoring para um bairro.

    Args:
        bairro: nome do bairro alvo.
        cidade: cidade correspondente.
        uf: sigla do estado (opcional).
        niches: lista de chaves de nicho (config.settings.NICHE_TAGS).
        excluir_redes: se True, remove estabelecimentos com tag de marca/rede.
        ai_enabled: se True, tenta rodar a análise qualitativa via Gemini para
            cada lead. Se a chave de API não estiver configurada ou uma
            chamada falhar, o pipeline não é interrompido — o lead
            simplesmente fica com score baseado só nos critérios objetivos,
            reescalado para 0–100 (ver LeadScorer.combine).
        on_progress: callback opcional chamado a cada lead processado, como
            on_progress(indice_atual, total, nome_do_lead) — usado pela UI
            (Streamlit) para atualizar uma barra de progresso em tempo real.

    Returns:
        Lista de dicts com os leads já processados, classificados e com
        Lead Score calculado, ordenados por score_final decrescente —
        prontos para exportação (CSV) ou exibição em tabela/dashboard.

    Raises:
        GeocodingError: se o bairro/cidade não puder ser geocodificado.
    """
    overpass_client = OverpassClient()
    site_analyzer = SiteAnalyzer()
    classifier = LeadClassifier()
    scorer = LeadScorer()
    ai_analyzer = AIAnalyzer() if ai_enabled else None

    raw_leads = overpass_client.search_businesses(bairro, cidade, niches, uf)

    if excluir_redes:
        antes = len(raw_leads)
        raw_leads = [lead for lead in raw_leads if not lead.get("marca_rede")]
        removidos = antes - len(raw_leads)
        if removidos:
            logger.info(
                "%d estabelecimento(s) de rede/franquia removido(s) (excluir_redes).",
                removidos,
            )

    if not raw_leads:
        logger.warning("Nenhum estabelecimento encontrado para os critérios informados.")
        return []

    processed_leads: list[dict] = []
    total = len(raw_leads)

    for idx, lead in enumerate(raw_leads, start=1):
        logger.info("[%d/%d] Analisando: %s", idx, total, lead["nome"])
        if on_progress is not None:
            on_progress(idx, total, lead["nome"])

        try:
            analysis = site_analyzer.analyze(lead.get("website"))
            classification = classifier.classify(analysis)
        except Exception as exc:  # noqa: BLE001 - pipeline não deve parar por 1 lead
            logger.error("Falha ao processar '%s': %s", lead["nome"], exc)
            analysis = None
            classification = None

        record = {**lead}
        if analysis is not None:
            analysis_dict = asdict(analysis)
            record.update(
                {
                    "url_final": analysis_dict.get("url_final"),
                    "status_code": analysis_dict.get("status_code"),
                    "is_https": analysis_dict.get("is_https"),
                    "ssl_valid": analysis_dict.get("ssl_valid"),
                    "response_time_seconds": analysis_dict.get("response_time_seconds"),
                }
            )
        if classification is not None:
            record["categoria"] = classification.categoria
            record["motivos"] = " | ".join(classification.motivos)
        else:
            record["categoria"] = "Erro no processamento"
            record["motivos"] = "Falha inesperada durante análise/classificação."

        # --- Lead Scoring (score objetivo + IA opcional) ---
        if analysis is not None:
            score_objetivo, motivos_objetivo = scorer.score_objetivo(record, analysis)
        else:
            score_objetivo, motivos_objetivo = (
                0,
                ["Score objetivo não calculado (falha na análise do site)."],
            )

        ai_result = None
        if ai_analyzer is not None and analysis is not None:
            ai_input = {
                "nome": record.get("nome"),
                "nicho": record.get("nicho"),
                "categoria": record.get("categoria"),
                "motivos": record.get("motivos"),
                "has_site": analysis.has_site,
                "is_https": analysis.is_https,
                "is_slow": analysis.is_slow,
            }
            ai_result = ai_analyzer.analyze(ai_input)

        scoring = scorer.combine(
            score_objetivo=score_objetivo,
            score_ia=ai_result.score_ia if ai_result else 0,
            motivos_objetivo=motivos_objetivo,
            motivos_ia=ai_result.motivos if ai_result else [],
            ia_disponivel=ai_result is not None,
        )

        record.update(
            {
                "score_objetivo": scoring.score_objetivo,
                "score_ia": scoring.score_ia,
                "score_final": scoring.score_final,
                "prioridade": scoring.prioridade,
                "motivos_score": " | ".join(scoring.motivos),
                "ia_disponivel": scoring.ia_disponivel,
                "possivel_oportunidade": (
                    ai_result.possivel_oportunidade if ai_result else ""
                ),
                "justificativa_ia": ai_result.justificativa if ai_result else "",
            }
        )

        processed_leads.append(record)

    # Já entrega ranqueado — nem app.py nem main.py precisam reordenar.
    processed_leads.sort(key=lambda r: r.get("score_final", 0), reverse=True)

    return processed_leads


__all__ = ["run_pipeline", "GeocodingError", "COLUMN_ORDER"]