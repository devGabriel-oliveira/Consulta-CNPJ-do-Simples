import asyncio
import io
import re
import time
import pandas as pd
import streamlit as st
from datetime import datetime
from mcp_fiscal_brasil._core import FiscalNotFoundError
from mcp_fiscal_brasil._core.errors import FiscalHTTPError
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

    :root {
        --vix-navy: #1d2a4d;
        --vix-orange: #f7941d;
        --bg-dark: #0e1117;
    }

    .brand-header {
        background: linear-gradient(135deg, #1d2a4d 0%, #111930 100%);
        border-radius: 16px;
        padding: 2rem;
        margin-bottom: 2rem;
        border-left: 6px solid #f7941d;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }

    .stDataFrame {
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
    }

    div.stButton > button:first-child {
        background: linear-gradient(135deg, #f7941d 0%, #e58512 100%) !important;
        color: white !important;
        border: none !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        padding: 0.75rem 2rem !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 15px rgba(247, 148, 29, 0.4) !important;
        transition: all 0.3s ease !important;
    }

    div.stButton > button:first-child:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(247, 148, 29, 0.6) !important;
    }

    div.stButton > button:first-child:disabled {
        background: rgba(255,255,255,0.1) !important;
        color: rgba(255,255,255,0.3) !important;
        box-shadow: none !important;
        cursor: not-allowed !important;
    }

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

# ==================== CONSTANTES ====================
MAX_TENTATIVAS = 3
BACKOFF_BASE = 1.5   # segundos: 1.5, 3.0, 4.5

STATUS_OK = "OK"
STATUS_NAO_ENCONTRADO = "Não encontrado"
STATUS_ERRO_SIMPLES = "Erro (Simples)"
STATUS_ERRO_CNPJ = "Erro (Receita)"
STATUS_ERRO_TOTAL = "Erro (Falha total)"
STATUS_CNPJ_INVALIDO = "CNPJ inválido"

# HTTP status considerados transitórios (vale tentar de novo)
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}


# ==================== FUNÇÕES AUXILIARES ====================
def limpar_cnpj(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def formatar_cnpj(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def _erro_e_transitorio(exc: Exception) -> bool:
    """Retorna True se o erro merece retry (rede, timeout, 5xx, 429)."""
    if isinstance(exc, FiscalHTTPError):
        return exc.status_code in TRANSIENT_STATUSES
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    # httpx errors
    nome = type(exc).__name__
    return nome in {"ConnectError", "ReadTimeout", "TimeoutException", "NetworkError", "RemoteProtocolError"}


async def _com_retry(coro_factory, tentativas: int = MAX_TENTATIVAS):
    """
    Executa uma corrotina com retries em erros transitórios.
    Retorna: (dado, erro). Se sucesso, erro é None.
    Repropaga FiscalNotFoundError e erros HTTP não-transitórios (403, 401, 404, 400).
    """
    ultimo_erro = None
    for i in range(tentativas):
        try:
            return await coro_factory(), None
        except FiscalNotFoundError:
            raise
        except FiscalHTTPError as e:
            ultimo_erro = e
            if not _erro_e_transitorio(e):
                # 403/401/400 não adianta tentar de novo
                return None, e
            if i < tentativas - 1:
                await asyncio.sleep(BACKOFF_BASE * (i + 1))
        except Exception as e:
            ultimo_erro = e
            if not _erro_e_transitorio(e):
                return None, e
            if i < tentativas - 1:
                await asyncio.sleep(BACKOFF_BASE * (i + 1))
    return None, ultimo_erro


def _formatar_erro(exc: Exception) -> str:
    """Converte exceção em mensagem curta para a coluna Detalhes."""
    if isinstance(exc, FiscalHTTPError):
        return f"HTTP {exc.status_code}: {str(exc)[:120]}"
    return f"{type(exc).__name__}: {str(exc)[:120]}"


async def consultar_um(cnpj_raw: str) -> dict:
    cnpj = limpar_cnpj(cnpj_raw)
    resultado = {
        "CNPJ": formatar_cnpj(cnpj),
        "Razão Social": "---",
        "Situação": "---",
        "Simples Nacional": "---",
        "MEI": "---",
        "Data Opção": "---",
        "Data Opção MEI": "---",
        "Status": STATUS_OK,
        "Detalhes": "",
        "simples_bool": False,
        "mei_bool": False,
        "cnpj_raw": cnpj,
    }

    if len(cnpj) != 14:
        resultado["Razão Social"] = "CNPJ Inválido"
        resultado["Status"] = STATUS_CNPJ_INVALIDO
        resultado["Detalhes"] = "CNPJ precisa ter 14 dígitos"
        return resultado

    cnpj_client = CNPJClient()
    simples_client = SimplesClient()

    # ── Consulta paralela ─────────────────────────────────────
    async def buscar_cnpj():
        try:
            return await _com_retry(lambda: cnpj_client.consultar(cnpj))
        except FiscalNotFoundError:
            return None, "not_found"

    async def buscar_simples():
        try:
            return await _com_retry(lambda: simples_client.get_simples_status(cnpj))
        except FiscalNotFoundError:
            return None, "not_found"

    (dados_cnpj, erro_cnpj), (dados_simples, erro_simples) = await asyncio.gather(
        buscar_cnpj(), buscar_simples()
    )

    # ── Interpreta CNPJ ───────────────────────────────────────
    cnpj_not_found = erro_cnpj == "not_found"
    if dados_cnpj:
        resultado["Razão Social"] = dados_cnpj.razao_social or "Não Informada"
        resultado["Situação"] = dados_cnpj.situacao_cadastral or "Ativa"
    elif cnpj_not_found:
        resultado["Razão Social"] = "Não localizado"
        resultado["Status"] = STATUS_NAO_ENCONTRADO
    elif erro_cnpj is not None:
        resultado["Razão Social"] = "⚠️ Erro na consulta"
        resultado["Status"] = STATUS_ERRO_CNPJ
        resultado["Detalhes"] = f"Receita: {_formatar_erro(erro_cnpj)}"

    # ── Interpreta Simples/SIMEI ──────────────────────────────
    simples_not_found = erro_simples == "not_found"
    if dados_simples:
        resultado["Simples Nacional"] = "Sim" if dados_simples.simples_nacional else "Não"
        resultado["simples_bool"] = bool(dados_simples.simples_nacional)
        resultado["MEI"] = "Sim" if dados_simples.mei else "Não"
        resultado["mei_bool"] = bool(dados_simples.mei)
        if dados_simples.data_opcao:
            resultado["Data Opção"] = dados_simples.data_opcao.strftime("%d/%m/%Y")
        if dados_simples.data_opcao_mei:
            resultado["Data Opção MEI"] = dados_simples.data_opcao_mei.strftime("%d/%m/%Y")
    elif simples_not_found:
        # CNPJ realmente não retornou dados de Simples — é não-optante
        resultado["Simples Nacional"] = "Não"
        resultado["MEI"] = "Não"
    else:
        # Erro real: NÃO afirmar Não
        resultado["Simples Nacional"] = "⚠️ Erro"
        resultado["MEI"] = "⚠️ Erro"
        detalhe_simples = _formatar_erro(erro_simples) if erro_simples else "sem detalhes"
        if resultado["Status"] == STATUS_OK:
            resultado["Status"] = STATUS_ERRO_SIMPLES
            resultado["Detalhes"] = f"Simples: {detalhe_simples}"
        else:
            resultado["Status"] = STATUS_ERRO_TOTAL
            resultado["Detalhes"] += f" | Simples: {detalhe_simples}"

    return resultado


async def consultar_lote(cnpjs: list[str], progress_callback) -> list[dict]:
    resultados = []
    for i, cnpj in enumerate(cnpjs):
        resultado = await consultar_um(cnpj)
        resultados.append(resultado)
        progress_callback(i + 1, len(cnpjs))
    return resultados


def estilizar_linha(row):
    """Aplica cor de fundo por linha conforme o Status."""
    status = row.get("Status", "")
    if status == STATUS_OK:
        if row.get("Simples Nacional") == "Sim" or row.get("MEI") == "Sim":
            return ["background-color: rgba(35, 134, 54, 0.15)"] * len(row)
        return [""] * len(row)
    elif status in (STATUS_ERRO_SIMPLES, STATUS_ERRO_CNPJ, STATUS_ERRO_TOTAL):
        return ["background-color: rgba(247, 148, 29, 0.18)"] * len(row)
    elif status in (STATUS_CNPJ_INVALIDO, STATUS_NAO_ENCONTRADO):
        return ["background-color: rgba(200, 60, 60, 0.12)"] * len(row)
    return [""] * len(row)


# Só monta a UI quando executado via streamlit — evita side effects nos testes
def _renderizar_ui():
    # ==================== CABEÇALHO BRANDING ====================
    with st.container():
        col_logo, col_title = st.columns([1, 4])
        with col_logo:
            try:
                st.image("logo_vixpar.png", use_container_width=True)
            except Exception:
                st.markdown("### VIXPAR")

        with col_title:
            st.markdown("""
            <div class="brand-header">
                <h2 style='margin:0; padding:0; color:white;'>Monitoramento Fiscal Avançado</h2>
                <p style='margin:5px 0 0 0; color:#b0bccc; font-size:0.95rem;'>Consulta em lote automatizada — Simples Nacional & Receita Federal</p>
            </div>
            """, unsafe_allow_html=True)

    # ==================== ABAS ====================
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
            uploaded_file = st.file_uploader(
                "Ou faça upload de um arquivo contendo os CNPJs (.txt, .csv)",
                type=["txt", "csv"]
            )

        with col_side:
            st.markdown("##### :material/tune: Instruções")
            st.caption("1. Adicione os CNPJs ao lado colando ou anexando.")
            st.caption("2. Clique no botão destacado abaixo para disparar as buscas.")
            st.caption("3. Erros de rede são identificados como ⚠️ e podem ser reprocessados.")
            if st.button(":material/refresh: Resetar Painel", use_container_width=True):
                st.session_state.resultados = None
                st.rerun()

        # Tratamento de entradas
        cnpjs_raw = []
        if uploaded_file:
            cnpjs_raw.extend([
                l.strip() for l in uploaded_file.read().decode("utf-8", errors="ignore").splitlines()
                if l.strip()
            ])
        if texto_cnpjs.strip():
            cnpjs_raw.extend([l.strip() for l in texto_cnpjs.splitlines() if l.strip()])

        cnpjs_raw = list(dict.fromkeys(cnpjs_raw))

        st.markdown("---")

        botao_desabilitado = len(cnpjs_raw) == 0
        texto_botao = (
            f":material/bolt: PROCESSAR {len(cnpjs_raw)} CNPJs AGORA"
            if cnpjs_raw
            else ":material/lock: INSIRA CNPJS PARA PROCESSAR"
        )

        if st.button(texto_botao, type="primary", use_container_width=True, disabled=botao_desabilitado):
            inicio = time.time()
            bar_text = st.empty()
            prog_bar = st.progress(0)

            def update_progress(atual, total):
                prog_bar.progress(atual / total)
                bar_text.caption(f"Processando: {atual} de {total} CNPJs analisados...")

            resultados = asyncio.run(consultar_lote(cnpjs_raw, update_progress))
            st.session_state.resultados = resultados
            st.session_state.tempo_execucao = time.time() - inicio

            bar_text.empty()
            prog_bar.empty()

        # ==================== EXIBIÇÃO DOS RESULTADOS ====================
        if st.session_state.resultados:
            df = pd.DataFrame(st.session_state.resultados)

            # ── Métricas ──
            st.markdown("### :material/analytics: Indicadores de Resumo")
            m1, m2, m3, m4, m5 = st.columns(5)

            qtd_erros = int((df["Status"] != STATUS_OK).sum())

            with m1:
                st.metric("Total Processado", len(df))
            with m2:
                st.metric("Optantes Simples", int(df["simples_bool"].sum()))
            with m3:
                st.metric("Microempreendedores (MEI)", int(df["mei_bool"].sum()))
            with m4:
                st.metric(
                    "Erros / Reprocessar",
                    qtd_erros,
                    delta=None if qtd_erros == 0 else "atenção",
                    delta_color="inverse",
                )
            with m5:
                st.metric("Tempo Total", f"{st.session_state.tempo_execucao:.2f}s")

            # ── Reprocessar apenas erros ──
            if qtd_erros > 0:
                st.warning(
                    f"⚠️ {qtd_erros} CNPJ(s) tiveram falha na consulta. "
                    "As colunas mostram ⚠️ Erro em vez de assumir 'Não' incorretamente."
                )
                if st.button(
                    f":material/replay: Reprocessar {qtd_erros} CNPJ(s) com erro",
                    use_container_width=True,
                ):
                    inicio = time.time()
                    indices_erro = df.index[df["Status"] != STATUS_OK].tolist()
                    cnpjs_erro = df.loc[indices_erro, "cnpj_raw"].tolist()

                    bar_text = st.empty()
                    prog_bar = st.progress(0)

                    def update_progress(atual, total):
                        prog_bar.progress(atual / total)
                        bar_text.caption(f"Reprocessando: {atual} de {total}...")

                    novos = asyncio.run(consultar_lote(cnpjs_erro, update_progress))

                    atualizados = list(st.session_state.resultados)
                    for idx, novo in zip(indices_erro, novos):
                        atualizados[idx] = novo
                    st.session_state.resultados = atualizados
                    st.session_state.tempo_execucao += time.time() - inicio

                    bar_text.empty()
                    prog_bar.empty()
                    st.rerun()

            st.markdown("---")
            st.markdown("### :material/table_chart: Dados Consolidados")

            # ── Filtros ──
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                busca = st.text_input(
                    ":material/search: Filtrar resultados na tela:",
                    placeholder="Digite uma Razão Social ou CNPJ...",
                )
            with col_f2:
                mostrar_apenas = st.selectbox(
                    "Exibir:",
                    ["Todos", "Somente OK", "Somente com erro", "Somente optantes"],
                    index=0,
                )

            df_view = df.copy()
            if busca:
                df_view = df_view[
                    df_view["Razão Social"].str.contains(busca, case=False, na=False)
                    | df_view["CNPJ"].str.contains(busca, na=False)
                ]

            if mostrar_apenas == "Somente OK":
                df_view = df_view[df_view["Status"] == STATUS_OK]
            elif mostrar_apenas == "Somente com erro":
                df_view = df_view[df_view["Status"] != STATUS_OK]
            elif mostrar_apenas == "Somente optantes":
                df_view = df_view[(df_view["simples_bool"]) | (df_view["mei_bool"])]

            colunas_visiveis = ["CNPJ", "Razão Social", "Situação", "Simples Nacional",
                                "MEI", "Data Opção", "Data Opção MEI", "Status", "Detalhes"]
            df_display = df_view[colunas_visiveis]

            st.dataframe(
                df_display.style.apply(estilizar_linha, axis=1),
                use_container_width=True,
                hide_index=True,
            )

            # ── Exportação ──
            st.markdown("#### :material/download: Exportar Relatórios")
            c_csv, c_xlsx = st.columns(2)

            df_export = df_view[colunas_visiveis]

            with c_csv:
                csv_data = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    label="Salvar Planilha em CSV",
                    data=csv_data,
                    file_name=f"vixpar_relatorio_fiscal_{datetime.now():%Y%m%d_%H%M}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with c_xlsx:
                output_buffer = io.BytesIO()
                with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
                    df_export.to_excel(writer, index=False, sheet_name="Fiscal")

                    from openpyxl.styles import PatternFill, Font, Alignment
                    from openpyxl.utils import get_column_letter
                    ws = writer.sheets["Fiscal"]

                    header_fill = PatternFill("solid", fgColor="1D2A4D")
                    for cell in ws[1]:
                        cell.fill = header_fill
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.alignment = Alignment(horizontal="center", vertical="center")

                    verde = PatternFill("solid", fgColor="D4EDDA")
                    ambar = PatternFill("solid", fgColor="FFE8CC")
                    vermelho = PatternFill("solid", fgColor="F8D7DA")

                    status_col_idx = colunas_visiveis.index("Status")
                    sn_col_idx = colunas_visiveis.index("Simples Nacional")
                    mei_col_idx = colunas_visiveis.index("MEI")

                    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                        status = row[status_col_idx].value
                        if status == STATUS_OK:
                            if row[sn_col_idx].value == "Sim" or row[mei_col_idx].value == "Sim":
                                for c in row:
                                    c.fill = verde
                        elif status in (STATUS_ERRO_SIMPLES, STATUS_ERRO_CNPJ, STATUS_ERRO_TOTAL):
                            for c in row:
                                c.fill = ambar
                        elif status in (STATUS_CNPJ_INVALIDO, STATUS_NAO_ENCONTRADO):
                            for c in row:
                                c.fill = vermelho

                    for col in ws.columns:
                        max_len = max(len(str(c.value or "")) for c in col)
                        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 3, 60)

                st.download_button(
                    label="Salvar Planilha em Excel (XLSX)",
                    data=output_buffer.getvalue(),
                    file_name=f"vixpar_relatorio_fiscal_{datetime.now():%Y%m%d_%H%M}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

    with tab2:
        st.markdown("### :material/history_toggle_off: Histórico Recente")
        if st.session_state.resultados:
            st.caption("Abaixo constam os dados da última execução armazenados em cache temporário de sessão.")
            df_hist = pd.DataFrame(st.session_state.resultados)
            colunas_hist = ["CNPJ", "Razão Social", "Situação", "Simples Nacional",
                            "MEI", "Data Opção", "Data Opção MEI", "Status", "Detalhes"]
            st.dataframe(
                df_hist[colunas_hist].style.apply(estilizar_linha, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma consulta em lote executada nesta sessão.")

    # ==================== RODAPÉ ====================
    st.markdown("---")
    st.markdown(
        f"<p style='text-align: center; color: #55637a; font-size: 0.85rem;'>© {datetime.now().year} VIXPAR — Setor de Inteligência e Compliance Fiscal</p>",
        unsafe_allow_html=True
    )


# ==================== ENTRY POINT ====================
# Só renderiza a UI quando estamos dentro do runtime do Streamlit
# (evita side effects em testes que importam o módulo)
try:
    from streamlit.runtime import exists as _st_runtime_exists
    if _st_runtime_exists():
        _renderizar_ui()
except Exception:
    pass
