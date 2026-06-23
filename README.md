# 🧾 Consulta Fiscal — Simples Nacional em Lote

Aplicação web construída com **Streamlit** para consultar o status de optantes do **Simples Nacional** e **MEI** em lote, diretamente da base da Receita Federal.

---

## ✨ Funcionalidades

- 🔍 **Consulta em lote** — cole múltiplos CNPJs ou importe via arquivo `.txt` / `.csv`
- 🏢 **Dados cadastrais** — Razão Social e Situação Cadastral na Receita Federal
- ✅ **Status Simples Nacional** — verifica se a empresa é optante
- 🧑‍💼 **Status MEI** — identifica Microempreendedores Individuais
- 📅 **Data de opção** — exibe a data de adesão ao Simples Nacional
- 🔎 **Filtros dinâmicos** — filtre por Simples Nacional, MEI ou busque por CNPJ/Razão Social
- 📥 **Exportação** — baixe os resultados em `.csv` ou `.xlsx`
- 📊 **Histórico** — acompanhe a última consulta realizada na sessão
- ⚡ **Assíncrono** — processamento otimizado com `asyncio`

---

## 🚀 Como executar

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/consulta-fiscal.git
cd consulta-fiscal
```

### 2. Crie e ative um ambiente virtual

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Execute a aplicação

```bash
streamlit run app.py
```

A aplicação estará disponível em `http://localhost:8501`.

---

## 📦 Dependências

| Pacote | Descrição |
|---|---|
| `streamlit` | Framework para a interface web |
| `pandas` | Manipulação e exportação de dados |
| `mcp-fiscal-brasil` | Consulta de CNPJ e Simples Nacional |
| `openpyxl` | Exportação em formato `.xlsx` |

Instale todas com:

```bash
pip install streamlit pandas mcp-fiscal-brasil openpyxl
```

Ou via `requirements.txt`:

```
streamlit
pandas
mcp-fiscal-brasil
openpyxl
```

---

## 🗂️ Estrutura do Projeto

```
consulta-fiscal/
├── app.py              # Aplicação principal
├── requirements.txt    # Dependências do projeto
└── README.md           # Este arquivo
```

---

## 📋 Como usar

1. **Cole os CNPJs** na caixa de texto (um por linha, com ou sem formatação) **ou** faça o upload de um arquivo `.txt` ou `.csv`
2. Clique em **🔍 Consultar**
3. Aguarde o processamento — uma barra de progresso mostrará o andamento
4. Visualize os resultados com métricas resumidas (total, optantes, não optantes, MEI)
5. Use os **filtros** para refinar a visualização
6. **Exporte** os dados em CSV ou XLSX

### Formatos aceitos de CNPJ

```
11.222.333/0001-81
33000167000101
60.701.190/0001-04
```

---

## 🔌 APIs utilizadas

| Fonte | Dado |
|---|---|
| Receita Federal (via `mcp-fiscal-brasil`) | Razão Social, Situação Cadastral |
| Base Simples Nacional (via `mcp-fiscal-brasil`) | Status Simples, MEI, Data de Opção |

> Os dados são consultados **em tempo real**. Nenhuma informação é armazenada localmente.

---

## 🔒 Segurança e Privacidade

- ✅ Nenhum dado é persistido em banco de dados
- ✅ Todas as consultas são feitas em tempo real
- ✅ Sem autenticação ou coleta de credenciais

---

## 🛠️ Tecnologias

- [Python 3.10+](https://www.python.org/)
- [Streamlit](https://streamlit.io/)
- [mcp-fiscal-brasil](https://pypi.org/project/mcp-fiscal-brasil/)
- [Pandas](https://pandas.pydata.org/)
- [asyncio](https://docs.python.org/3/library/asyncio.html)

---

## 📄 Licença

Este projeto está sob a licença **MIT**. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
