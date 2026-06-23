import asyncio
import io
import re
import time
import pandas as pd
import streamlit as st
from datetime import datetime
from mcp_fiscal_brasil._core import FiscalNotFoundError
from mcp_fiscal_brasil.cnpj.client import CNPJClient
from mcp_fiscal_brasil.simples.client import SimplesClient

# ==================== CONFIGURAÇÃO DA PÁGINA ====================
st.set_page_config(
    page_title="VIXPAR | Portal Fiscal",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== CUSTOM CSS (DESIGN SYSTEM CORPORATIVO) ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Paleta de Cores VIXPAR */
    :root {
        --vix-navy: #1d2a4d;
        --vix-orange: #f7941d;
        --bg-dark: #0e1117;
    }

    /* Container do Cabeçalho Moderno */
    .brand-header {
        background: linear-gradient(135deg, #1d2a4d 0%, #111930 100%);
        border-radius: 16px;
        padding: 2rem;
        margin-bottom: 2rem;
        border-left: 6px solid #f7941d;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }

    /* Estilização das Tabelas e Dataframes */
    .stDataFrame {
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
    }

    /* Customização Discreta dos Botões Principais */
    .stButton>button {
        background: #f7941d !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.2s ease;
    }
    
    .stButton>button:hover {
        background: #e58512 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(247, 148, 29, 0.3);
    }

    /* Ajuste de Abas */
    .stTabs [data-baseweb="tab"] {
        font-weight: 500;
        padding: 12px 24px;
    }
</style>
""", unsafe_allow_html=True)

# ==================== SESSION STATE ====================
if "resultados" not in st.session_state:
    st.session_state.resultados = None
if "tempo_execucao" not in st.session_state:
    st.session_state.tempo_execucao = 0

# ==================== FUNÇÕES AUXILIARES ====================
def limpar_cnpj(texto: str) -> str:
    return re.sub(r"\D", "", texto)

def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj

async def consultar_um(cnpj_raw: str) -> dict:
    cnpj = limpar_cnpj(cnpj_raw)
    resultado = {
        "CNPJ": formatar_cnpj(cnpj),
        "Razão Social": "Carregando...",
        "Situação": "---",
        "Simples Nacional": "---",
        "MEI": "---",
        "Data Opção": "---",
        "Status": "ok",
        "simples_bool": False,
        "mei_bool": False,
    }

    if len(cnpj) != 14:
        resultado["Razão Social"] = "CNPJ Inválido"
        resultado["Status"] = "erro"
        return resultado

    cnpj_client = CNPJClient()
    simples_client = SimplesClient()

    async def buscar_cnpj():
        try: return await cnpj_client.consultar(cnpj)
        except: return None

    async def buscar_simples():
        try: return await simples_client.get_simples_status(cnpj)
        except FiscalNotFoundError: return None
        except: return None

    dados_cnpj, dados_simples = await asyncio.gather(buscar_cnpj(), buscar_simples())

    if dados_cnpj:
        resultado["Razão Social"] = dados_cnpj.razao_social or "Não Informada"
        resultado["Situação"] = dados_cnpj.situacao_cadastral or "Ativa"
    else:
        resultado["Razão Social"] = "Não Localizado"
        resultado["Status"] = "erro"

    if dados_simples:
        resultado["Simples Nacional"] = "Sim" if dados_simples.simples_nacional else "Não"
        resultado["simples_bool"] = dados_simples.simples_nacional or False
        resultado["MEI"] = "Sim" if dados_simples.mei else "Não"
        resultado["mei_bool"] = dados_simples.mei or False
        if dados_simples.data_opcao:
            resultado["Data Opção"] = dados_simples.data_opcao.strftime("%d/%m/%Y")
    else:
        resultado["Simples Nacional"] = "Não"
        resultado["MEI"] = "Não"

    return resultado

async def consultar_lote(cnpjs: list[str], progress_callback) -> list[dict]:
    resultados = []
    for i, cnpj in enumerate(cnpjs):
        resultado = await consultar_um(cnpj)
        resultados.append(resultado)
        progress_callback(i + 1, len(cnpjs))
    return resultados

# ==================== CABEÇALHO BRANDING ====================
with st.container():
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        try:
            # Tenta carregar a imagem local definida por você
            st.image("logo_vixpar.png", use_container_width=True)
        except Exception:
            # Fallback elegante caso a imagem ainda não esteja na pasta ao testar
            st.markdown("### VIXPAR")
            
    with col_title:
        st.markdown("""
        <div class="brand-header">
            <h2 style='margin:0; padding:0; color:white;'>Monitoramento Fiscal Avançado</h2>
            <p style='margin:5px 0 0 0; color:#b0bccc; font-size:0.95rem;'>Consulta em lote automatizada — Simples Nacional & Receita Federal</p>
        </div>
        """, unsafe_allow_html=True)

# ==================== ABAS DO SISTEMA ====================
tab1, tab2 = st.tabs([
    ":material/query_stats: Painel de Consulta", 
    ":material/history: Histórico de Consultas"
])

with tab1:
    col_inp, col_side = st.columns([2, 1], gap="large")

    with col_inp:
        st.markdown("##### :material/input: Dados de Entrada")
        texto_cnpjs = st.text_area(
            "Cole uma lista de CNPJs (um por linha)",
            height=150,
            placeholder="00.000.000/0001-00\n11111111000111",
            label_visibility="collapsed"
        )
        uploaded_file = st.file_uploader("Ou faça upload de um arquivo contendo os CNPJs (.txt, .csv)", type=["txt", "csv"])

    with col_side:
        st.markdown("##### :material/tune: Opções")
        st.caption("A ferramenta processará as requisições de forma assíncrona paralelamente para máxima performance.")
        if st.button(":material/refresh: Limpar Dados", use_container_width=True):
            st.session_state.resultados = None
            st.rerun()

    # Processar inputs
    cnpjs_raw = []
    if uploaded_file:
        cnpjs_raw = [l.strip() for l in uploaded_file.read().decode("utf-8", errors="ignore").splitlines() if l.strip()]
    elif texto_cnpjs.strip():
        cnpjs_raw = [l.strip() for l in texto_cnpjs.splitlines() if l.strip()]

    if cnpjs_raw:
        st.markdown("---")
        if st.button(":material/bolt: PROCESSAR LOTE AGORA", type="primary", use_container_width=True):
            inicio = time.time()
            bar_text = st.empty()
            prog_bar = st.progress(0)
            
            def update_progress(atual, total):
                prog_bar.progress(atual/total)
                bar_text.caption(f"Processando: {atual} de {total} CNPJs analisados...")

            resultados = asyncio.run(consultar_lote(cnpjs_raw, update_progress))
            st.session_state.resultados = resultados
            st.session_state.tempo_execucao = time.time() - inicio
            
            bar_text.empty()
            prog_bar.empty()

    # Resultados da Consulta Ativa
    if st.session_state.resultados:
        df = pd.DataFrame(st.session_state.resultados)
        
        st.markdown("### :material/analytics: Indicadores de Resumo")
        m1, m2, m3, m4 = st.columns(4)
        
        with m1:
            st.metric("Total Processado", len(df))
        with m2:
            st.metric("Optantes Simples", int(df['simples_bool'].sum()))
        with m3:
            st.metric("Microempreendedores (MEI)", int(df['mei_bool'].sum()))
        with m4:
            st.metric("Tempo Total", f"{st.session_state.tempo_execucao:.2f}s")

        st.markdown("---")
        st.markdown("### :material/table_chart: Dados Consolidados")
        
        # Filtro em tempo real dinâmico
        busca = st.text_input(":material/search: Filtrar resultados na tela:", placeholder="Digite uma Razão Social ou CNPJ...")
        df_view = df.copy()
        if busca:
            df_view = df_view[df_view['Razão Social'].str.contains(busca, case=False) | df_view['CNPJ'].str.contains(busca)]

        st.dataframe(
            df_view.drop(columns=["Status", "simples_bool", "mei_bool"]),
            use_container_width=True,
            hide_index=True
        )

        # Seção de Exportação corrigida
        st.markdown("#### :material/download: Exportar Relatórios")
        c_csv, c_xlsx = st.columns(2)
        
        df_export = df_view.drop(columns=["Status", "simples_bool", "mei_bool"])
        
        with c_csv:
            csv_data = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="Salvar Planilha em CSV", 
                data=csv_data, 
                file_name="vixpar_relatorio_fiscal.csv", 
                mime="text/csv",
                use_container_width=True
            )
            
        with c_xlsx:
            # Correção do Erro: Usando openpyxl explicitamente que é nativo e estável
            output_buffer = io.BytesIO()
            with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name="Fiscal")
            
            st.download_button(
                label="Salvar Planilha em Excel (XLSX)", 
                data=output_buffer.getvalue(), 
                file_name="vixpar_relatorio_fiscal.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

with tab2:
    st.markdown("### :material/history_toggle_off: Histórico Recente")
    if st.session_state.resultados:
        st.caption("Abaixo constam os dados da última execução armazenados em cache temporário de sessão.")
        st.dataframe(pd.DataFrame(st.session_state.resultados).drop(columns=["Status", "simples_bool", "mei_bool"]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma consulta em lote executada nesta sessão.")

# ==================== RODAPÉ ====================
st.markdown("---")
st.markdown(
    f"<p style='text-align: center; color: #55637a; font-size: 0.85rem;'>© {datetime.now().year} VIXPAR — Setor de Inteligência e Compliance Fiscal</p>", 
    unsafe_allow_html=True
)
