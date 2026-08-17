from dotenv import load_dotenv; 
load_dotenv()
"""
app.py

Interface web do B2B Leads Miner, construída com Streamlit.

Permite que qualquer pessoa da equipe (comercial, vendas) rode uma
prospecção preenchendo um formulário no navegador — sem abrir terminal,
editar código ou instalar nada além do navegador (quando hospedado).

Como rodar localmente:
    streamlit run app.py

Como disponibilizar para o time sem precisar instalar nada (recomendado):
    1. Suba este repositório no GitHub.
    2. Acesse https://share.streamlit.io, conecte sua conta GitHub.
    3. Aponte para este repositório e o arquivo "app.py".
    4. Você recebe uma URL pública (ex.: seu-app.streamlit.app) — qualquer
       pessoa do time pode acessar direto pelo navegador, sem instalar nada.
"""

import pandas as pd
import streamlit as st

from config.settings import (
    CATEGORY_DATA_BI,
    CATEGORY_NO_SITE,
    CATEGORY_OPTIMIZATION,
    NICHE_PRESET_ICP,
    NICHE_TAGS,
    NICHE_TIER_1,
    NICHE_TIER_2,
    NICHE_TIER_3,
)
from src.data_exporter import COLUMN_ORDER
from src.pipeline import GeocodingError, run_pipeline

st.set_page_config(
    page_title="Marcondes|Leads Finder",
    layout="wide",
)

PRESETS = {
    "Recomendado (ICP)": NICHE_PRESET_ICP,
    "Só comércio de produto": NICHE_TIER_1,
    "Só serviço c/ agendamento": NICHE_TIER_2,
    "Serviço profissional": NICHE_TIER_3,
    "Todos os nichos": list(NICHE_TAGS.keys()),
    "Personalizado": [],
}

CATEGORY_COLORS = {
    CATEGORY_NO_SITE: "🆕",
    CATEGORY_OPTIMIZATION: "🛠️",
    CATEGORY_DATA_BI: "📊",
}

# --------------------------------------------------------------------------
# Tema (roxo claro/escuro) — Streamlit não tem troca de tema nativa em tempo
# real, então isso é CSS injetado por cima. Guardamos a escolha em
# session_state pra sobreviver aos reruns do form.
# --------------------------------------------------------------------------
PALETTES = {
    "Escuro": {
        "bg": "#120E1A",
        "surface": "#1E1830",
        "surface_alt": "#251D3B",
        "border": "#3A2E58",
        "text": "#F1EDFB",
        "text_muted": "#B8ADD4",
        "primary": "#8B5CF6",
        "primary_strong": "#A78BFA",
    },
    "Claro": {
        "bg": "#FAF8FF",
        "surface": "#FFFFFF",
        "surface_alt": "#F1ECFC",
        "border": "#E1D6F7",
        "text": "#1E1533",
        "text_muted": "#6B5F8A",
        "primary": "#5B21B6",
        "primary_strong": "#4C1D95",
    },
}

if "tema" not in st.session_state:
    st.session_state.tema = "Escuro"

_theme_col1, _theme_col2 = st.columns([6, 1])
with _theme_col2:
    st.session_state.tema = st.radio(
        "Tema",
        options=list(PALETTES.keys()),
        index=list(PALETTES.keys()).index(st.session_state.tema),
        horizontal=True,
        label_visibility="collapsed",
    )

_p = PALETTES[st.session_state.tema]

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&display=swap');

    .stApp {{
        background-color: {_p['bg']};
        color: {_p['text']};
    }}
    [data-testid="stHeader"] {{
        background-color: transparent;
    }}
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}
    h1, h2, h3 {{
        font-family: 'Space Grotesk', sans-serif !important;
        color: {_p['text']} !important;
    }}
    p, span, label, .stMarkdown {{
        color: {_p['text']};
    }}
    [data-testid="stCaptionContainer"] {{
        color: {_p['text_muted']} !important;
    }}

    /* Cards de métrica */
    [data-testid="stMetric"] {{
        background-color: {_p['surface']};
        border: 1px solid {_p['border']};
        border-radius: 12px;
        padding: 16px 18px;
    }}
    [data-testid="stMetricValue"] {{
        color: {_p['primary_strong']} !important;
        font-family: 'Space Grotesk', sans-serif;
    }}
    [data-testid="stMetricLabel"] {{
        color: {_p['text_muted']} !important;
    }}

    /* Formulário / inputs */
    [data-testid="stForm"] {{
        background-color: {_p['surface']};
        border: 1px solid {_p['border']};
        border-radius: 14px;
        padding: 20px;
    }}
    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{
        background-color: {_p['surface_alt']} !important;
        color: {_p['text']} !important;
        border-color: {_p['border']} !important;
    }}

    /* Botão primário */
    .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {{
        background-color: {_p['primary']} !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600;
    }}
    .stButton button:hover, .stDownloadButton button:hover,
    [data-testid="stFormSubmitButton"] button:hover {{
        background-color: {_p['primary_strong']} !important;
    }}

    /* Tabela */
    [data-testid="stDataFrame"] {{
        border: 1px solid {_p['border']};
        border-radius: 12px;
        overflow: hidden;
    }}

    /* Painel de detalhe do lead */
    .lead-detail-card {{
        background-color: {_p['surface']};
        border: 1px solid {_p['border']};
        border-left: 4px solid {_p['primary']};
        border-radius: 12px;
        padding: 20px 24px;
        margin-top: 8px;
    }}
    .lead-detail-card h3 {{
        margin-top: 0;
    }}
    .lead-motivo {{
        color: {_p['text_muted']};
        font-size: 0.92rem;
        margin: 2px 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Cabeçalho
# --------------------------------------------------------------------------
st.title("Framework - Prospecção de leads")
st.caption(
    "Prospecção de comércios locais por bairro, encontre quem precisa de "
    "site novo, otimização/segurança ou uma oferta de dados/BI — já "
    "priorizado por Lead Score."
)

# --------------------------------------------------------------------------
# Formulário de busca
# --------------------------------------------------------------------------
with st.form("busca_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        bairro = st.text_input("Bairro", placeholder="Ex.: Aquarius")
    with col2:
        cidade = st.text_input("Cidade", placeholder="Ex.: São José dos Campos")
    with col3:
        uf = st.text_input("UF (opcional)", placeholder="Ex.: SP", max_chars=2)

    preset_label = st.selectbox(
        "Quais nichos buscar?",
        options=list(PRESETS.keys()),
        index=0,
        help=(
            "'Recomendado (ICP)' usa os nichos com maior propensão real de "
            "fechar contrato, com base nos cases da SciTec Jr."
        ),
    )

    nichos_personalizados: list[str] = []
    if preset_label == "Personalizado":
        nichos_personalizados = st.multiselect(
            "Escolha os nichos", options=sorted(NICHE_TAGS.keys())
        )

    col_a, col_b = st.columns(2)
    with col_a:
        excluir_redes = st.checkbox(
            "Excluir grandes redes/franquias (ex.: Carrefour, McDonald's)",
            value=True,
            help="Foca em comércio independente — geralmente o público real do ICP.",
        )
    with col_b:
        ai_enabled = st.checkbox(
            "Usar IA na análise qualitativa (Gemini)",
            value=True,
            help=(
                "Se desmarcado (ou se a IA falhar), o Lead Score usa só os "
                "critérios objetivos, reescalados para 0–100."
            ),
        )

    submitted = st.form_submit_button("🔍 Buscar leads", use_container_width=True)

# --------------------------------------------------------------------------
# Execução da busca
# --------------------------------------------------------------------------
if submitted:
    if not bairro.strip() or not cidade.strip():
        st.error("Preencha ao menos o bairro e a cidade.")
        st.stop()

    niches = (
        nichos_personalizados if preset_label == "Personalizado" else PRESETS[preset_label]
    )
    if not niches:
        st.error("Selecione ao menos um nicho.")
        st.stop()

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def _on_progress(idx: int, total: int, nome: str) -> None:
        progress_bar.progress(idx / total)
        status_text.text(f"Analisando {idx}/{total}: {nome}")

    with st.spinner("Localizando o bairro e minerando estabelecimentos..."):
        try:
            leads = run_pipeline(
                bairro=bairro.strip(),
                cidade=cidade.strip(),
                uf=uf.strip(),
                niches=niches,
                excluir_redes=excluir_redes,
                ai_enabled=ai_enabled,
                on_progress=_on_progress,
            )
        except GeocodingError as exc:
            st.error(
                f"Não foi possível localizar '{bairro}, {cidade}'. "
                f"Verifique a grafia do bairro/cidade. Detalhe técnico: {exc}"
            )
            st.stop()

    progress_bar.empty()
    status_text.empty()

    if not leads:
        st.warning(
            "Nenhum estabelecimento encontrado para esses critérios. "
            "Isso costuma acontecer quando o bairro tem poucos comércios "
            "cadastrados no OpenStreetMap — tente outro bairro ou preset."
        )
        st.stop()

    df = pd.DataFrame(leads)
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + remaining_cols]

    # Guarda no session_state pra sobreviver ao rerun quando o usuário
    # seleciona um lead no painel de detalhe, sem precisar buscar de novo.
    st.session_state.df_resultado = df
    st.session_state.bairro_busca = bairro.strip()

# --------------------------------------------------------------------------
# Exibição dos resultados (roda também em reruns, ex.: ao trocar tema
# ou selecionar um lead — não só logo após o submit)
# --------------------------------------------------------------------------
if "df_resultado" in st.session_state:
    df = st.session_state.df_resultado

    tem_score = "score_final" in df.columns

    # ----------------------------------------------------------------
    # Resumo
    # ----------------------------------------------------------------
    st.subheader("Resumo")

    counts_categoria = df["categoria"].value_counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de leads", len(df))
    m2.metric(f"{CATEGORY_COLORS[CATEGORY_NO_SITE]} {CATEGORY_NO_SITE}", int(counts_categoria.get(CATEGORY_NO_SITE, 0)))
    m3.metric(f"{CATEGORY_COLORS[CATEGORY_OPTIMIZATION]} {CATEGORY_OPTIMIZATION}", int(counts_categoria.get(CATEGORY_OPTIMIZATION, 0)))
    m4.metric(f"{CATEGORY_COLORS[CATEGORY_DATA_BI]} {CATEGORY_DATA_BI}", int(counts_categoria.get(CATEGORY_DATA_BI, 0)))

    if tem_score:
        counts_prioridade = df["prioridade"].value_counts()
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Score médio", f"{df['score_final'].mean():.0f}")
        p2.metric("🔥 Alta prioridade", int(counts_prioridade.get("🔥 Alta", 0)))
        p3.metric("🟡 Média prioridade", int(counts_prioridade.get("🟡 Média", 0)))
        p4.metric("🟢 Baixa prioridade", int(counts_prioridade.get("🟢 Baixa", 0)))

    # ----------------------------------------------------------------
    # Filtro rápido + ranking
    # ----------------------------------------------------------------
    st.subheader("Ranking de leads")
    categoria_filtro = st.multiselect(
        "Filtrar por categoria",
        options=list(counts_categoria.index),
        default=list(counts_categoria.index),
    )
    df_filtrado = df[df["categoria"].isin(categoria_filtro)]
    if tem_score:
        df_filtrado = df_filtrado.sort_values("score_final", ascending=False)

    colunas_ranking = [
        c
        for c in [
            "nome",
            "nicho",
            "score_final",
            "prioridade",
            "categoria",
            "possivel_oportunidade",
            "website",
        ]
        if c in df_filtrado.columns
    ]

    st.dataframe(
        df_filtrado[colunas_ranking] if colunas_ranking else df_filtrado,
        use_container_width=True,
        hide_index=True,
        column_config={
            "score_final": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"
            ),
            "nome": st.column_config.TextColumn("Empresa"),
            "nicho": st.column_config.TextColumn("Nicho"),
            "prioridade": st.column_config.TextColumn("Prioridade"),
            "categoria": st.column_config.TextColumn("Categoria"),
            "possivel_oportunidade": st.column_config.TextColumn("Oportunidade"),
            "website": st.column_config.LinkColumn("Site"),
        },
    )

    # ----------------------------------------------------------------
    # Análise detalhada de um lead
    # ----------------------------------------------------------------
    if tem_score:
        st.subheader("Análise do lead")
        nomes_disponiveis = df_filtrado["nome"].tolist()
        if nomes_disponiveis:
            lead_selecionado = st.selectbox(
                "Selecione um lead para ver o detalhe do score",
                options=nomes_disponiveis,
            )
            lead = df_filtrado[df_filtrado["nome"] == lead_selecionado].iloc[0]

            motivos = str(lead.get("motivos_score", "")).split(" | ") if lead.get("motivos_score") else []
            motivos_html = "".join(f"<p class='lead-motivo'>{m}</p>" for m in motivos if m)

            ia_bloco = ""
            if lead.get("ia_disponivel"):
                ia_bloco = f"""
                <p><b>Oportunidade sugerida (IA):</b> {lead.get('possivel_oportunidade', '—')}</p>
                <p><b>Justificativa da IA:</b> {lead.get('justificativa_ia', '—')}</p>
                """
            else:
                ia_bloco = "<p style='color:#B8ADD4;'><i>Análise de IA não disponível para este lead — score baseado só nos critérios objetivos.</i></p>"

            st.markdown(
                f"""
                <div class="lead-detail-card">
                    <h3>{lead.get('nome', '')}</h3>
                    <p><b>Score:</b> {lead.get('score_final', 0)}/100 &nbsp;&nbsp; <b>Prioridade:</b> {lead.get('prioridade', '')}</p>
                    <p><b>Categoria técnica:</b> {lead.get('categoria', '')}</p>
                    <p><b>Critérios do score:</b></p>
                    {motivos_html}
                    {ia_bloco}
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ----------------------------------------------------------------
    # Download
    # ----------------------------------------------------------------
    csv_bytes = df_filtrado.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV",
        data=csv_bytes,
        file_name=f"leads_{st.session_state.get('bairro_busca', 'busca').lower().replace(' ', '_')}.csv",
        mime="text/csv",
        use_container_width=True,
    )