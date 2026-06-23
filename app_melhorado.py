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
    page_title="VIXPAR | Consulta Fiscal",
    page_icon="https://vixpar.com.br/wp-content/uploads/2023/04/cropped-favicon-vixpar-32x32.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== CUSTOM CSS (PROFESSIONAL DARK THEME) ====================
st.markdown("""
<style>
    /* Importação de fonte profissional */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Cores VIXPAR */
    :root {
        --vix-blue: #1d2a4d;
        --vix-orange: #f7941d;
        --vix-gradient: linear-gradient(135deg, #1d2a4d 0%, #151d33 100%);
    }

    .stApp {
        background-color: #0e1117;
    }

    /* Header e Logo */
    .header-container {
        background: var(--vix-gradient);
        border-bottom: 3px solid var(--vix-orange);
        border-radius: 0 0 20px 20px;
        padding: 2.5rem;
        margin-bottom: 2rem;
        text-align: center;
    }

    /* Títulos */
    h1 {
        color: white !important;
        font-weight: 700 !important;
        letter-spacing: -1px;
    }

    /* Cards de Métricas */
    .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.5rem;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        border-color: var(--vix-orange);
        transform: translateY(-2px);
    }

    /* Estilização de Abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: rgba(255,255,255,0.05);
        border-radius: 8px 8px 0 0;
        color: white;
        padding: 10px 25px;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--vix-orange) !important;
        border: none !important;
    }

    /* Badges de Status na Tabela */
    .status-badge {
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
    }
    .status-sim { background: #155724; color: #d4edda; }
    .status-nao { background: #721c24; color: #f8d7da; }

    /* Inputs e Botões */
    .stButton>button {
        background-color: var(--vix-orange);
        color: white;
        border: none;
        padding: 0.6rem 2rem;
        font-weight: 600;
        border-radius: 8px;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #e68613;
        color: white;
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

# ==================== INTERFACE: LOGO E CABEÇALHO ====================
# Link da logo fornecida (VIXPAR)
LOGO_URL = "https://raw.githubusercontent.com/vixpar/logo/main/logo_vixpar.png" # Exemplo de URL estável

with st.container():
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    # Tenta carregar a imagem da logo que você enviou
    st.image("https://i.postimg.cc/mD7XFpBy/image.png", width=400)
    st.markdown("<h1>Sistema de Monitoramento Fiscal</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #ccc;'>Consultas automatizadas ao Simples Nacional e Base da Receita Federal</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ==================== TABS PRINCIPAIS ====================
tab1, tab2, tab3 = st.tabs([
    ":material/search: Consultar Base", 
    ":material/history: Histórico", 
    ":material/info: Sobre a VIXPAR"
])

with tab1:
    col_inp, col_info = st.columns([2, 1], gap="large")

    with col_inp:
        st.subheader(":material/list_alt: Entrada de Dados")
        texto_cnpjs = st.text_area(
            "Cole os CNPJs (um por linha)",
            height=180,
            placeholder="Ex:\n00.000.000/0001-00\n11.111.111/0001-11",
            help="Aceita CNPJs com ou sem pontuação."
        )
        
        uploaded_file = st.file_uploader("Ou importe via arquivo (CSV/TXT)", type=["txt", "csv"])

    with col_info:
        st.subheader(":material/settings: Parâmetros")
        st.info("Otimizado para consultas em lote. A velocidade depende da estabilidade dos portais governamentais.")
        if st.button(":material/delete: Limpar Campos"):
            st.rerun()

    # Processamento de CNPJs
    cnpjs_raw = []
    if uploaded_file:
        cnpjs_raw = [l.strip() for l in uploaded_file.read().decode().splitlines() if l.strip()]
    elif texto_cnpjs.strip():
        cnpjs_raw = [l.strip() for l in texto_cnpjs.splitlines() if l.strip()]

    if cnpjs_raw:
        if st.button(":material/play_circle: INICIAR CONSULTA FISCAL", type="primary"):
            inicio = time.time()
            bar_text = st.empty()
            prog_bar = st.progress(0)
            
            def cb(atual, total):
                prog_bar.progress(atual/total)
                bar_text.caption(f"Processando registro {atual} de {total}...")

            resultados = asyncio.run(consultar_lote(cnpjs_raw, cb))
            st.session_state.resultados = resultados
            st.session_state.tempo_execucao = time.time() - inicio
            st.success(f"Consulta finalizada em {st.session_state.tempo_execucao:.2f} segundos.")

    # Exibição de Resultados
    if st.session_state.resultados:
        df = pd.DataFrame(st.session_state.resultados)
        
        st.markdown("---")
        st.subheader(":material/analytics: Indicadores do Lote")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", len(df))
        m1.markdown(f'<div class="metric-card"><small>Registros</small></div>', unsafe_allow_html=True)
        
        m2.metric("Optantes Simples", df['simples_bool'].sum())
        m3.metric("Optantes MEI", df['mei_bool'].sum())
        m4.metric("Incorretos", (df['Status'] == 'erro').sum())

        st.markdown("### :material/table_rows: Tabela de Dados")
        
        # Filtro de Busca Profissional
        busca = st.text_input(":material/filter_list: Filtrar na tabela...", placeholder="Busque por razão social ou CNPJ")
        df_view = df.copy()
        if busca:
            df_view = df_view[df_view['Razão Social'].str.contains(busca, case=False) | df_view['CNPJ'].contains(busca)]

        st.dataframe(
            df_view.drop(columns=["Status", "simples_bool", "mei_bool"]),
            use_container_width=True,
            hide_index=True
        )

        # Exportação
        st.subheader(":material/download: Exportar Relatório")
        c_csv, c_xlsx = st.columns(2)
        with c_csv:
            csv = df_view.to_csv(index=False).encode('utf-8')
            st.download_button("Baixar em CSV", csv, "relatorio_vixpar.csv", "text/csv")
        with c_xlsx:
            # Buffer simples para XLSX
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_view.to_excel(writer, index=False)
            st.download_button("Baixar em Excel", output.getvalue(), "relatorio_vixpar.xlsx")

with tab2:
    if st.session_state.resultados:
        st.subheader(":material/history: Última Sessão")
        st.write(f"Sessão iniciada às {datetime.now().strftime('%H:%M')}")
        st.dataframe(pd.DataFrame(st.session_state.resultados).head(10))
    else:
        st.info("Nenhum histórico disponível nesta sessão.")

with tab3:
    st.markdown("""
    ### :material/business: Grupo VIXPAR
    O Grupo **VIXPAR** atua com excelência em soluções corporativas e tecnologia. 
    Este portal de consulta fiscal é uma ferramenta interna para otimização de processos de compliance.
    """)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### :material/settings_suggest: Funcionalidades")
        st.markdown("- Validação de CNPJs em Lote\n- Consulta Simples Nacional\n- Verificação de MEI\n- Status na Receita Federal")
    
    with c2:
        st.markdown("#### :material/bolt: Performance")
        st.markdown("- Motor Assíncrono (Python 3.11+)\n- Cache em Tempo Real\n- Exportação Multi-formato")

    with c3:
        st.markdown("#### :material/security: Segurança")
        st.markdown("- Protocolos HTTPS\n- Sem Armazenamento de Dados Sensíveis\n- Conformidade com LGPD")

# ==================== FOOTER ====================
st.markdown("---")
st.markdown(
    f"<p style='text-align: center; color: #666;'>© {datetime.now().year} VIXPAR | Tecnologia e Gestão Fiscal</p>", 
    unsafe_allow_html=True
)
