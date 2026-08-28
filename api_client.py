"""Cliente para a API de pesquisa de empresas da Casa dos Dados.

Documentação oficial: https://docs.casadosdados.com.br/
Se a Casa dos Dados alterar nomes de campos do payload, ajuste apenas
a função `build_payload` abaixo — o resto do sistema não precisa mudar.
"""
import os
import unicodedata

import requests

API_URL = os.environ.get(
    "CASADOSDADOS_API_URL",
    "https://api.casadosdados.com.br/v5/public/cnpj/pesquisa",
)
API_KEY = os.environ.get("CASADOSDADOS_API_KEY", "")

# Quantos registros pedir por chamada (máximo permitido pela API). Pedir o
# máximo de cada vez reduz o número de chamadas necessárias para paginar.
LIMITE_POR_CHAMADA = 1000

# Chaves onde a lista de empresas costuma vir dentro da resposta da API.
RESULT_LIST_KEYS = ["resultados", "resultado", "data", "empresas", "cnpjs", "results", "items"]
COUNT_KEYS = ["count", "total", "quantidade", "total_registros"]


class CasaDosDadosError(Exception):
    def __init__(self, message, status_code=None, raw_response=None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


def _sem_acentos(texto):
    nfkd = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalizar_localidade(valor):
    """A API espera uf/município/bairro em minúsculo e sem acento
    (ex: "sao paulo", não "São Paulo") — ver exemplos da documentação."""
    return _sem_acentos(valor).lower().strip()


def build_payload(filtros: dict) -> dict:
    """Converte os filtros do formulário no payload esperado pela API.

    `filtros` vem diretamente do formulário web (strings). Campos vazios
    são omitidos para não enviar chaves inválidas/desnecessárias.
    """
    payload = {}

    texto = (filtros.get("texto") or "").strip()
    if texto:
        busca_textual = {"texto": [texto]}
        campos_busca = filtros.get("campos_busca") or []
        if "razao_social" in campos_busca:
            busca_textual["razao_social"] = True
        if "nome_fantasia" in campos_busca:
            busca_textual["nome_fantasia"] = True
        if "nome_socio" in campos_busca:
            busca_textual["nome_socio"] = True
        payload["busca_textual"] = busca_textual

    def add_list(field, payload_key=None, normalizar=None):
        raw = (filtros.get(field) or "").strip()
        if raw:
            valores = [v.strip() for v in raw.split(",") if v.strip()]
            if normalizar:
                valores = [normalizar(v) for v in valores]
            payload[payload_key or field] = valores

    def add_multi(field, normalizar=None):
        valores = [v for v in (filtros.get(field) or []) if v]
        if normalizar:
            valores = [normalizar(v) for v in valores]
        if valores:
            payload[field] = valores

    add_multi("uf", normalizar=_normalizar_localidade)
    add_multi("municipio", normalizar=_normalizar_localidade)
    add_list("bairro", normalizar=_normalizar_localidade)
    add_list("cep")
    add_list("ddd")
    add_list("codigo_atividade_principal")
    add_list("codigo_atividade_secundaria")
    add_list("codigo_natureza_juridica")

    add_multi("situacao_cadastral")

    if filtros.get("incluir_atividade_secundaria"):
        payload["incluir_atividade_secundaria"] = True

    matriz_filial = (filtros.get("matriz_filial") or "").strip()
    if matriz_filial:
        payload["matriz_filial"] = matriz_filial

    cnpj = (filtros.get("cnpj") or "").strip()
    if cnpj:
        payload["cnpj"] = ["".join(ch for ch in cnpj if ch.isdigit())]

    cnpj_raiz = (filtros.get("cnpj_raiz") or "").strip()
    if cnpj_raiz:
        payload["cnpj_raiz"] = ["".join(ch for ch in cnpj_raiz if ch.isdigit())]

    capital_de = (filtros.get("capital_social_de") or "").strip()
    capital_ate = (filtros.get("capital_social_ate") or "").strip()
    if capital_de or capital_ate:
        capital_social = {}
        if capital_de:
            capital_social["minimo"] = int(float(capital_de))
        if capital_ate:
            capital_social["maximo"] = int(float(capital_ate))
        payload["capital_social"] = capital_social

    data_de = (filtros.get("data_abertura_de") or "").strip()
    data_ate = (filtros.get("data_abertura_ate") or "").strip()
    if data_de or data_ate:
        data_abertura = {}
        if data_de:
            data_abertura["inicio"] = data_de
        if data_ate:
            data_abertura["fim"] = data_ate
        payload["data_abertura"] = data_abertura

    mei = {}
    if filtros.get("somente_mei"):
        mei["optante"] = True
    if filtros.get("excluir_mei"):
        mei["excluir_optante"] = True
    if mei:
        payload["mei"] = mei

    mais_filtros = {}
    if filtros.get("com_email"):
        mais_filtros["com_email"] = True
    if filtros.get("com_telefone"):
        mais_filtros["com_telefone"] = True
    if mais_filtros:
        payload["mais_filtros"] = mais_filtros

    payload["limite"] = LIMITE_POR_CHAMADA

    pagina = filtros.get("pagina")
    if pagina:
        payload["pagina"] = int(pagina)

    return payload


def _extract_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in RESULT_LIST_KEYS:
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _extract_count(data, fallback):
    if isinstance(data, dict):
        for key in COUNT_KEYS:
            if key in data and isinstance(data[key], (int, float)):
                return int(data[key])
    return fallback


def search(filtros: dict, pagina: int = 1, timeout: int = 30):
    """Faz a pesquisa na API. Retorna (lista_de_empresas, total_estimado, resposta_bruta)."""
    if not API_KEY:
        raise CasaDosDadosError(
            "CASADOSDADOS_API_KEY não configurada. Defina a variável de ambiente "
            "no arquivo .env (veja .env.example)."
        )

    filtros = dict(filtros)
    filtros["pagina"] = pagina
    payload = build_payload(filtros)

    try:
        resp = requests.post(
            API_URL,
            params={"tipo_resultado": "completo"},
            json=payload,
            headers={"api-key": API_KEY, "Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise CasaDosDadosError(f"Falha de conexão com a API: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        data = {"raw_text": resp.text}

    if not resp.ok:
        msg = data.get("message") or data.get("error") or resp.text or "Erro desconhecido"
        raise CasaDosDadosError(
            f"API retornou erro {resp.status_code}: {msg}",
            status_code=resp.status_code,
            raw_response=data,
        )

    empresas = _extract_list(data)
    total = _extract_count(data, fallback=len(empresas))
    return empresas, total, data
