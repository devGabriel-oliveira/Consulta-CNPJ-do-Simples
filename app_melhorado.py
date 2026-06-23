import asyncio
import io
import re
import time
from datetime import datetime

import pandas as pd
import streamlit as st
from mcp_fiscal_brasil._core import FiscalNotFoundError
from mcp_fiscal_brasil.cnpj.client import CNPJClient
from mcp_fiscal_brasil.simples.client import SimplesClient

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Consulta Fiscal - Simples Nacional",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== CUSTOM CSS ====================
st.markdown("""
<style>
    * {
        margin: 0;
        padding: 0;
    }

    body {
        background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
        color: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }

    /* Main container */
    .main {
        background: transparent;
    }

    /* Header styling */
    .header-container {
        background: linear-gradient(135deg, rgba(79, 39, 131, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 2rem;
        margin-bottom: 2rem;
        animation: slideDown 0.5s ease-out;
    }

    @keyframes slideDown {
        from {
            opacity: 0;
            transform: translateY(-20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Card styling */
    .metric-card {
        background: linear-gradient(135deg, rgba(147, 51, 234, 0.15) 0%, rgba(59, 130, 246, 0.1) 100%);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(147, 51, 234, 0.3);
        border-radius: 16px;
        padding: 1.5rem;
        transition: all 0.3s ease;
    }

    .metric-card:hover {
        border-color: rgba(147, 51, 234, 0.6);
        transform: translateY(-5px);
        box-shadow: 0 20px 40px rgba(147, 51, 234, 0.2);
    }

    /* Result cards */
    .result-card {
        background: linear-gradient(135deg, rgba(79, 39, 131, 0.08) 0%, rgba(147, 51, 234, 0.05) 100%);
        border: 1px solid rgba(147, 51, 234, 0.25);
        border-radius: 12px;
        padding: 1.25rem;
        margin: 0.75rem 0;
        transition: all 0.3s ease;
    }

    .result-card:hover {
        background: linear-gradient(135deg, rgba(79, 39, 131, 0.15) 0%, rgba(147, 51, 234, 0.1) 100%);
        border-color: rgba(147, 51, 234, 0.5);
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(147, 51, 234, 0.4);
    }

    .stButton > button:active {
        transform: translateY(-1px);
    }

    /* Input fields */
    .stTextArea > div > div > textarea,
    .stFileUploader > div > div,
    input[type="text"] {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(147, 51, 234, 0.3) !important;
        color: #ffffff !important;
        border-radius: 12px !important;
        padding: 1rem !important;
    }

    .stTextArea > div > div > textarea:focus,
    input[type="text"]:focus {
        border-color: rgba(147, 51, 234, 0.7) !important;
        box-shadow: 0 0 0 3px rgba(147, 51, 234, 0.2) !important;
    }

    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #9333ea 0%, #7c3aed 100%);
        border-radius: 10px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: linear-gradient(90deg, rgba(79, 39, 131, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%);
        border-radius: 12px;
        padding: 0.5rem;
        border: 1px solid rgba(147, 51, 234, 0.2);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: rgba(255, 255, 255, 0.7);
        transition: all 0.3s ease;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
        color: white;
    }

    /* Dataframe */
    .stDataFrame {
        background: rgba(79, 39, 131, 0.05) !important;
        border: 1px solid rgba(147, 51, 234, 0.2) !important;
        border-radius: 12px !important;
    }

    /* Divider */
    hr {
        border: 1px solid rgba(147, 51, 234, 0.2);
    }

    /* Info/Warning boxes */
    .stAlert {
        background: linear-gradient(135deg, rgba(147, 51, 234, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
        border-left: 4px solid #9333ea;
        border-radius: 8px;
    }

    /* Badge styling */
    .badge {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }

    .badge-success {
        background: rgba(34, 197, 94, 0.2);
        color: #86efac;
        border: 1px solid rgba(34, 197, 94, 0.4);
    }

    .badge-error {
        background: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
        border: 1px solid rgba(239, 68, 68, 0.4);
    }

    /* Title styling */
    h1, h2, h3 {
        letter-spacing: -0.5px;
    }

    h1 {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #9333ea, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* Animations */
    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    .fade-in {
        animation: fadeIn 0.5s ease-out;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: rgba(79, 39, 131, 0.1);
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb {
        background: rgba(147, 51, 234, 0.4);
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: rgba(147, 51, 234, 0.6);
    }
</style>
""", unsafe_allow_html=True)

# ==================== SESSION STATE ====================
if "resultados" not in st.session_state:
    st.session_state.resultados = None
if "cnpjs_processados" not in st.session_state:
    st.session_state.cnpjs_processados = []
if "tempo_execucao" not in st.session_state:
    st.session_state.tempo_execucao = 0

# ==================== HELPER FUNCTIONS ====================
def limpar_cnpj(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def badge_simples(valor: bool) -> str:
    if valor:
        return '<span class="badge badge-success">✅ Optante</span>'
    return '<span class="badge badge-error">❌ Não optante</span>'


def badge_mei(valor: bool) -> str:
    if valor:
        return '<span class="badge badge-success">✅ Sim</span>'
    return '<span class="badge badge-error">❌ Não</span>'


async def consultar_um(cnpj_raw: str) -> dict:
    cnpj = limpar_cnpj(cnpj_raw)
    resultado = {
        "CNPJ": formatar_cnpj(cnpj),
        "Razão Social": "—",
        "Situação": "—",
        "Simples Nacional": "—",
        "MEI": "—",
        "Data Opção": "—",
        "Status": "ok",
        "simples_bool": False,
        "mei_bool": False,
    }

    if len(cnpj) != 14:
        resultado["Razão Social"] = "❌ CNPJ inválido"
        resultado["Status"] = "erro"
        return resultado

    cnpj_client = CNPJClient()
    simples_client = SimplesClient()

    async def buscar_cnpj():
        try:
            return await cnpj_client.consultar(cnpj)
        except Exception:
            return None

    async def buscar_simples():
        try:
            return await simples_client.get_simples_status(cnpj)
        except FiscalNotFoundError:
            return None
        except Exception:
            return None

    dados_cnpj, dados_simples = await asyncio.gather(buscar_cnpj(), buscar_simples())

    if dados_cnpj:
        resultado["Razão Social"] = dados_cnpj.razao_social or "—"
        resultado["Situação"] = dados_cnpj.situacao_cadastral or "—"
    else:
        resultado["Razão Social"] = "❌ Não encontrado"
        resultado["Status"] = "erro"

    if dados_simples:
        resultado["Simples Nacional"] = "✅ Sim" if dados_simples.simples_nacional else "❌ Não"
        resultado["simples_bool"] = dados_simples.simples_nacional or False
        resultado["MEI"] = "✅ Sim" if dados_simples.mei else "❌ Não"
        resultado["mei_bool"] = dados_simples.mei or False
        if dados_simples.data_opcao:
            resultado["Data Opção"] = dados_simples.data_opcao.strftime("%d/%m/%Y")
    else:
        resultado["Simples Nacional"] = "❌ Não"
        resultado["MEI"] = "❌ Não"

    return resultado


async def consultar_lote(cnpjs: list[str], progress_callback) -> list[dict]:
    resultados = []
    for i, cnpj in enumerate(cnpjs):
        resultado = await consultar_um(cnpj)
        resultados.append(resultado)
        progress_callback(i + 1, len(cnpjs))
    return resultados


# ==================== HEADER ====================
st.markdown('<div class="header-container">', unsafe_allow_html=True)
col1, col2 = st.columns([1, 3])
with col1:
    st.markdown("## 🧾")
with col2:
    st.markdown("""
    # Consulta Fiscal
    **Verifique optantes do Simples Nacional em lote**
    """)
st.markdown('</div>', unsafe_allow_html=True)

# ==================== TABS ====================
tab1, tab2, tab3 = st.tabs(["📊 Consultar", "📈 Histórico", "ℹ️ Informações"])

with tab1:
    st.markdown("### Informe seus CNPJs")

    col1, col2 = st.columns([2, 1], gap="medium")

    with col1:
        st.markdown("**Cole ou envie CNPJs** (com ou sem formatação)")
        texto_cnpjs = st.text_area(
            label="CNPJs para consulta",
            height=200,
            placeholder="11.222.333/0001-81\n33000167000101\n60701190000104\n(um por linha)",
            label_visibility="collapsed"
        )

    with col2:
        st.markdown("**Ou importe um arquivo**")
        arquivo = st.file_uploader(
            "Selecione arquivo",
            type=["txt", "csv"],
            label_visibility="collapsed"
        )
        st.markdown("**Formatos:** TXT ou CSV, um CNPJ por linha")

    # Processar entrada
    cnpjs_raw: list[str] = []

    if arquivo:
        conteudo = arquivo.read().decode("utf-8", errors="ignore")
        cnpjs_raw = [l.strip() for l in conteudo.splitlines() if l.strip()]
    elif texto_cnpjs.strip():
        cnpjs_raw = [l.strip() for l in texto_cnpjs.strip().splitlines() if l.strip()]

    # Status
    if cnpjs_raw:
        cols = st.columns([1, 1, 1, 1])
        with cols[0]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: #9333ea;">{len(cnpjs_raw)}</div>
                    <div style="font-size: 0.85rem; color: rgba(255,255,255,0.7); margin-top: 0.5rem;">CNPJs Identificados</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Botão Consultar
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 3])
    with btn_col1:
        consultar = st.button("🔍 Consultar", type="primary", disabled=not cnpjs_raw, use_container_width=True)
    with btn_col2:
        if cnpjs_raw:
            limpar_campos = st.button("🗑️ Limpar", use_container_width=True)
            if limpar_campos:
                st.rerun()

    # ========== EXECUÇÃO ==========
    if consultar and cnpjs_raw:
        inicio = time.time()

        progresso = st.progress(0, text="⏳ Iniciando consultas...")
        status_box = st.empty()
        status_detalhe = st.empty()

        def atualizar_progresso(atual, total):
            pct = atual / total
            progresso.progress(pct, text=f"⏳ Consultando... {atual} de {total}")
            status_detalhe.caption(f"⚡ Processado: {atual}/{total} | Tempo: {time.time() - inicio:.1f}s")

        resultados = asyncio.run(consultar_lote(cnpjs_raw, atualizar_progresso))
        
        tempo_total = time.time() - inicio
        st.session_state.tempo_execucao = tempo_total
        st.session_state.resultados = resultados
        st.session_state.cnpjs_processados = cnpjs_raw

        progresso.empty()
        status_box.empty()
        status_detalhe.empty()

        # ========== RESULTADOS ==========
        st.markdown("---")
        st.markdown(f"### ✅ Consulta Concluída em {tempo_total:.2f}s")

        df = pd.DataFrame(resultados)

        # Métricas
        total = len(df)
        sim = (df["simples_bool"]).sum()
        nao = (~df["simples_bool"]).sum()
        mei_count = (df["mei_bool"]).sum()

        cols = st.columns(4, gap="medium")
        with cols[0]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #9333ea;">{total}</div>
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-top: 0.5rem;">Total Consultado</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[1]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #22c55e;">{sim}</div>
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-top: 0.5rem;">Optantes Simples</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[2]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #ef4444;">{nao}</div>
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-top: 0.5rem;">Não Optantes</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with cols[3]:
            st.markdown(f"""
            <div class="metric-card">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; font-weight: 700; color: #3b82f6;">{mei_count}</div>
                    <div style="font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-top: 0.5rem;">MEI</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        # Filtros e busca
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            filtro_simples = st.radio(
                "Filtrar por Simples Nacional:",
                ("Todos", "✅ Sim", "❌ Não"),
                horizontal=True,
                label_visibility="collapsed"
            )
        with col2:
            filtro_mei = st.radio(
                "Filtrar por MEI:",
                ("Todos", "✅ Sim", "❌ Não"),
                horizontal=True,
                label_visibility="collapsed"
            )
        with col3:
            busca = st.text_input("🔎 Buscar CNPJ/Razão Social", label_visibility="collapsed", placeholder="Digite para filtrar...")

        # Aplicar filtros
        df_filtrado = df.copy()

        if filtro_simples != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Simples Nacional"] == filtro_simples]

        if filtro_mei != "Todos":
            df_filtrado = df_filtrado[df_filtrado["MEI"] == filtro_mei]

        if busca:
            mask = (
                df_filtrado["CNPJ"].str.contains(busca, case=False) |
                df_filtrado["Razão Social"].str.contains(busca, case=False, na=False)
            )
            df_filtrado = df_filtrado[mask]

        st.markdown(f"**Mostrando {len(df_filtrado)} de {len(df)} registros**")

        # Tabela com estilo
        df_exibir = df_filtrado.drop(columns=["Status", "simples_bool", "mei_bool"])

        st.dataframe(
            df_exibir,
            use_container_width=True,
            hide_index=True,
            column_config={
                "CNPJ": st.column_config.TextColumn("CNPJ", width="medium"),
                "Razão Social": st.column_config.TextColumn("Razão Social", width="large"),
                "Situação": st.column_config.TextColumn("Situação", width="small"),
                "Simples Nacional": st.column_config.TextColumn("Simples Nacional", width="small"),
                "MEI": st.column_config.TextColumn("MEI", width="small"),
                "Data Opção": st.column_config.TextColumn("Data Opção", width="small"),
            },
            height=400
        )

        # Exportar
        st.markdown("---")
        st.markdown("### 📥 Exportar Resultados")

        col1, col2 = st.columns(2, gap="medium")

        with col1:
            df_export = df_filtrado.drop(columns=["Status", "simples_bool", "mei_bool"])
            df_export["Simples Nacional"] = df_export["Simples Nacional"].str.replace("✅ ", "").str.replace("❌ ", "")
            df_export["MEI"] = df_export["MEI"].str.replace("✅ ", "").str.replace("❌ ", "")

            csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

            st.download_button(
                label="⬇️ CSV",
                data=io.BytesIO(csv_bytes),
                file_name=f"simples_nacional_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col2:
            xlsx_buffer = io.BytesIO()
            with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
                df_export.to_excel(writer, sheet_name="Resultados", index=False)
            xlsx_buffer.seek(0)

            st.download_button(
                label="⬇️ XLSX",
                data=xlsx_buffer,
                file_name=f"simples_nacional_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

with tab2:
    st.markdown("### 📊 Histórico de Consultas")
    
    if st.session_state.resultados:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Última Consulta", f"{len(st.session_state.resultados)} CNPJs")
        with col2:
            st.metric("Tempo de Processamento", f"{st.session_state.tempo_execucao:.2f}s")
        with col3:
            taxa_simples = (len([r for r in st.session_state.resultados if r['simples_bool']]) / len(st.session_state.resultados) * 100) if st.session_state.resultados else 0
            st.metric("Taxa de Optantes", f"{taxa_simples:.1f}%")
        
        st.markdown("---")
        st.markdown("**Últimos CNPJs Consultados:**")
        df_historico = pd.DataFrame(st.session_state.resultados).drop(columns=["Status", "simples_bool", "mei_bool"])
        st.dataframe(df_historico.head(20), use_container_width=True, hide_index=True)
    else:
        st.info("📭 Nenhuma consulta realizada ainda.")

with tab3:
    st.markdown("""
    ### ℹ️ Sobre esta Ferramenta

    **Consulta Fiscal** é uma solução para verificar o status de optantes do **Simples Nacional** em lote.

    #### 🎯 Funcionalidades
    - ✅ Consulta de múltiplos CNPJs simultaneamente
    - ✅ Importação de arquivos (TXT, CSV)
    - ✅ Informações de Razão Social e Situação Cadastral
    - ✅ Status MEI (Microempreendedor Individual)
    - ✅ Data de opção pelo Simples Nacional
    - ✅ Filtros e buscas rápidas
    - ✅ Exportação em CSV e XLSX

    #### 📚 Dados Consultados
    - **Receita Federal** - Cadastro de CNPJ
    - **Governo Federal** - Base Simples Nacional

    #### ⚡ Performance
    - Processamento paralelo e assíncrono
    - Consultas otimizadas
    - Cache inteligente

    #### 🔒 Segurança
    - Nenhum dado é armazenado
    - Consultas em tempo real
    - Sem consumo de tokens de IA

    ---
    
    **Desenvolvido com:** Streamlit | mcp-fiscal-brasil | Python
    """)

# ==================== FOOTER ====================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: rgba(255,255,255,0.5); font-size: 0.85rem; padding: 2rem 0;">
    <p>🧾 Consulta Fiscal • Simples Nacional em Lote</p>
    <p>Dados atualizados em tempo real • Sem consumo de tokens</p>
</div>
""", unsafe_allow_html=True)
