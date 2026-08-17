"""
teste_leadscore_offline.py

Testa Lead Scoring (score objetivo + IA) de ponta a ponta SEM depender do
Overpass API — útil enquanto o overpass-api.de estiver instável/congestionado.

Usa leads sintéticos, mas passa pelo SiteAnalyzer de verdade (faz requisição
HTTP real aos sites de exemplo) e pela IA de verdade — só a etapa de
mineração (OverpassClient) é pulada.

Como rodar:
    python teste_leadscore_offline.py
"""

from dotenv import load_dotenv

load_dotenv()

from src.ai_analyzer import AIAnalyzer
from src.data_exporter import DataExporter
from src.lead_classifier import LeadClassifier
from src.lead_scorer import LeadScorer
from src.site_analyzer import SiteAnalyzer

# Leads sintéticos cobrindo os principais cenários da árvore de decisão:
# sem site, site saudável, site sem HTTPS/lento, e sem telefone cadastrado.
RAW_LEADS = [
    {
        "nome": "Loja Exemplo Sem Site",
        "nicho": "loja_roupas",
        "website": None,
        "telefone": "(12) 3456-7890",
        "bairro": "Centro",
        "endereco": "Rua Exemplo, 1",
        "latitude": -23.15,
        "longitude": -45.78,
    },
    {
        "nome": "Salão Exemplo Sem Contato",
        "nicho": "salao_beleza",
        "website": "https://www.example.com",
        "telefone": "",
        "bairro": "Centro",
        "endereco": "Rua Exemplo, 2",
        "latitude": -23.15,
        "longitude": -45.78,
    },
    {
        "nome": "Escritório Exemplo Site OK",
        "nicho": "advocacia",
        "website": "https://www.google.com",
        "telefone": "(12) 3456-7891",
        "bairro": "Centro",
        "endereco": "Rua Exemplo, 3",
        "latitude": -23.15,
        "longitude": -45.78,
    },
]


def main() -> None:
    site_analyzer = SiteAnalyzer()
    classifier = LeadClassifier()
    scorer = LeadScorer()
    ai_analyzer = AIAnalyzer()  # usa GEMINI_API_KEY do .env, se existir

    processed_leads: list[dict] = []

    for lead in RAW_LEADS:
        print(f"\nAnalisando: {lead['nome']}")

        analysis = site_analyzer.analyze(lead.get("website"))
        classification = classifier.classify(analysis)

        record = {**lead}
        record["categoria"] = classification.categoria
        record["motivos"] = " | ".join(classification.motivos)
        record["is_https"] = analysis.is_https
        record["ssl_valid"] = analysis.ssl_valid
        record["status_code"] = analysis.status_code
        record["response_time_seconds"] = analysis.response_time_seconds

        score_objetivo, motivos_objetivo = scorer.score_objetivo(record, analysis)

        ai_result = ai_analyzer.analyze(
            {
                "nome": record["nome"],
                "nicho": record["nicho"],
                "categoria": record["categoria"],
                "motivos": record["motivos"],
                "has_site": analysis.has_site,
                "is_https": analysis.is_https,
                "is_slow": analysis.is_slow,
            }
        )

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

        print(f"  categoria: {record['categoria']}")
        print(f"  score_final: {record['score_final']} | prioridade: {record['prioridade']}")
        print(f"  motivos_score: {record['motivos_score']}")
        print(f"  ia_disponivel: {record['ia_disponivel']}")
        if ai_result:
            print(f"  possivel_oportunidade: {record['possivel_oportunidade']}")

        processed_leads.append(record)

    processed_leads.sort(key=lambda r: r["score_final"], reverse=True)
    DataExporter().export(processed_leads, "teste_offline")


if __name__ == "__main__":
    main()
