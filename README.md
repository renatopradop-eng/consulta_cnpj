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
`MAX_REGISTROS_CARREGADOS` registros (1000 por padrão, definido no topo de
`app.py`). Ao atingir esse teto, aparece um aviso na tela pedindo para
refinar os filtros ou exportar o que já foi carregado. Ajuste essa
constante se quiser um limite maior ou menor.
4. **Limpar resultados** descarta a busca atual da sessão.

### Sobre a lista de municípios

O endpoint `/api/municipios` do backend consulta a API pública do IBGE
(`servicodados.ibge.gov.br`) sob demanda e mantém um cache em memória por UF
durante a execução do servidor — não precisa de chave nem configuração
extra, mas exige que a máquina que roda o Flask tenha acesso à internet.

## Se a API mudar nomes de campos

O mapeamento entre os filtros do formulário e o payload real enviado à API
está isolado na função `build_payload()` em `api_client.py`. A extração da
lista de empresas da resposta (`_extract_list`) tenta várias chaves comuns
(`resultados`, `data`, `empresas`, etc.) — ajuste essa lista se a Casa dos
Dados usar outro nome no envelope da resposta.

A exportação para XLSX (`utils.py`) é genérica: ela "achata" automaticamente
qualquer estrutura JSON aninhada que a API devolver (ex: `endereco.uf`,
`atividade_principal.descricao`), então novos campos aparecem na planilha
sem precisar mexer no código.

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
