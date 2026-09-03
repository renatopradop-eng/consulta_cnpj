# Consulta CNPJ — Casa dos Dados

Aplicação web local (Flask) para pesquisar empresas por CNPJ/critérios de
prospecção na API da [Casa dos Dados](https://casadosdados.com.br), visualizar
os resultados em tabela e exportar para uma planilha `.xlsx`.

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite o .env e cole sua chave de API (obtida em
# https://portal.casadosdados.com.br/plataforma/api/chave)

python app.py
```

Acesse http://127.0.0.1:5000 no navegador.

## Como usar

1. Preencha os filtros desejados e clique em **Buscar**.
   - **UF** e **Município**: clique no campo para abrir uma lista com
     checkboxes. O Município só habilita depois de marcar ao menos uma UF, e
     mostra só os municípios das UFs selecionadas (buscados dinamicamente na
     API pública do IBGE). Ambos têm um campo de filtro por texto no topo da
     lista para achar mais rápido.
   - **Limpar Dados** apaga o que foi digitado/marcado no formulário, sem
     descartar resultados já carregados.
   - No painel do **Município**, use **Selecionar todos** / **Limpar seleção**
     para marcar ou desmarcar rapidamente os municípios visíveis (respeita o
     filtro de texto — filtre por um termo e "Selecionar todos" marca só os
     que aparecem).
   - **Capital social de/até** aceitam valores em reais com máscara (ex:
     digite `150000` e o campo mostra `R$ 1.500,00`).
2. Os resultados aparecem em tabela paginada. Use o seletor **Mostrar**
   (10/20/50/100/Exibir tudo) e os botões **Anterior/Próxima** para navegar.
   Ao avançar para uma página que ainda não foi carregada, o sistema busca
   automaticamente mais registros na API — por isso o número de "carregados"
   no cabeçalho cresce conforme você navega, até bater com o total
   encontrado (ou até o teto de segurança abaixo).
3. Clique em **Exportar para XLS** para baixar todos os resultados
   carregados até o momento (não só a página exibida) em uma planilha `.xlsx`.

### Teto de segurança na paginação automática

Cada chamada à API consome créditos da sua conta. Para não gastar créditos
sem controle (por exemplo, ao selecionar "Exibir tudo" numa busca com
milhares de resultados), o app carrega automaticamente no máximo
`MAX_REGISTROS_CARREGADOS` registros (10000 por padrão, definido no topo de
`app.py`). Ao atingir esse teto, aparece um aviso na tela pedindo para
refinar os filtros ou exportar o que já foi carregado. Ajuste essa
constante se quiser um limite maior ou menor.
4. **Limpar resultados** descarta a busca atual da sessão.

### Sobre a lista de municípios

O endpoint `/api/municipios` do backend consulta a API pública do IBGE
(`servicodados.ibge.gov.br`) sob demanda e mantém um cache em memória por UF
durante a execução do servidor — não precisa de chave nem configuração
extra, mas exige que a máquina que roda o Flask tenha acesso à internet.

## Sobre o endpoint e `tipo_resultado=completo`

O endpoint padrão é `https://api.casadosdados.com.br/v5/cnpj/pesquisa`
(pesquisa avançada) — **sem** `/public/` no caminho. O endpoint
`/v5/public/cnpj/pesquisa` parece ser uma versão simplificada que sempre
responde no modo "simples" (só CNPJ, razão social, nome fantasia e
situação cadastral), ignorando o parâmetro `tipo_resultado`.

O app envia `tipo_resultado=completo` tanto na query string quanto no
corpo da requisição (em `api_client.py`, função `search()`) para trazer
também capital social, endereço, quadro societário, e-mail, telefone e
CNAE. **Se você já tem um arquivo `.env` com `CASADOSDADOS_API_URL`
apontando para a URL antiga (com `/public/`), atualize-o** — variável de
ambiente sempre tem prioridade sobre o valor padrão do código.

Se mesmo assim os campos completos não aparecerem, use o link **"Ver
dados brutos"** na tela de resultados (rota `/debug/bruto`) para conferir
a URL e o payload realmente enviados, e a resposta crua da API — nesse
ponto, a causa mais provável passa a ser uma limitação do plano da sua
conta na Casa dos Dados (mode completo costuma ser um recurso pago),
não mais um problema de código.

## Se a API mudar nomes de campos

O mapeamento entre os filtros do formulário e o payload real enviado à API
está isolado na função `build_payload()` em `api_client.py` — já ajustado
conforme o schema oficial (`capital_social` como `{minimo, maximo}`,
`data_abertura` como `{inicio, fim}`, `mei.optante`/`mei.excluir_optante`,
`mais_filtros.com_email`/`mais_filtros.com_telefone`, `uf`/`municipio`/
`bairro` normalizados para minúsculo sem acento). A extração da lista de
empresas da resposta (`_extract_list`) tenta várias chaves comuns
(`cnpjs`, `resultados`, `data`, `empresas`, etc.) — ajuste essa lista se a
Casa dos Dados usar outro nome no envelope da resposta.

A tabela de resultados e o XLSX exibem **apenas** as colunas listadas em
`COLUNAS_PRIORITARIAS` (em `utils.py`), nessa ordem: capital social,
município, e-mail, telefone (e variantes como DDD/celular/WhatsApp) e CNAE
principal — todo o resto que a API devolver (razão social, CNPJ, quadro
societário, endereço completo, etc.) fica fora da tabela e do XLSX, mesmo
estando disponível na busca. Cada item da lista é um conjunto de
nomes/prefixos candidatos — o casamento considera qualquer segmento do
caminho da coluna, então cobre tanto `municipio` quanto
`endereco.municipio`, por exemplo. `COLUNAS_EXCLUIDAS` bloqueia
adicionalmente `CNPJ` e os campos de `situacao_cadastral`, caso algum dia
entrem sem querer nessa lista.

Dois tratamentos especiais em `utils.py`:

- `capital_social` é formatado como moeda brasileira (`R$ 150.000,00`)
  pela função `_formatar_moeda_brl`.
- Campos listados em `CAMPOS_LISTA_PARA_RESUMIR` (sócios/quadro
  societário, telefones, e-mails) que vierem como **lista de objetos** são
  reduzidos a uma única string legível (nomes/números separados por
  " | "), em vez de colunas fragmentadas por índice
  (`telefones[0].numero`, `telefones[1].numero`...). Se o campo já vier
  como valor simples ou objeto único, isso não tem efeito.

Para exibir mais colunas, adicione uma nova lista de candidatos a
`COLUNAS_PRIORITARIAS` em `utils.py`.

Consulte a documentação oficial e atualizada em
https://docs.casadosdados.com.br/ para confirmar nomes de parâmetros antes
de fazer buscas grandes (cada consulta consome créditos da sua conta).

## Estrutura

- `app.py` — rotas Flask (formulário, busca, exportação)
- `api_client.py` — cliente HTTP da API da Casa dos Dados
- `utils.py` — achatamento de JSON e geração do XLSX
- `templates/index.html` — formulário e tabela de resultados
- `static/style.css` — estilos
- `static/app.js` — dropdowns de UF/Município com checkbox e carregamento dinâmico de municípios

## Observações

- Este projeto é para uso local/pessoal (single-user); os resultados de
  cada busca ficam guardados em memória do processo, associados à sessão
  do navegador, e são perdidos ao reiniciar o servidor.
- Nunca faça commit do arquivo `.env` (ele já está no `.gitignore`).
