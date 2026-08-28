"""Funções auxiliares: achatar registros JSON aninhados e exportar para XLSX."""
import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

# Colunas que nunca devem aparecer na tabela de resultados nem no XLSX.
COLUNAS_EXCLUIDAS = {
    "CNPJ",
    "situacao_cadastral.situacao_atual",
    "situacao_cadastral.motivo",
    "situacao_cadastral.data",
}

# Colunas que devem aparecer primeiro (nessa ordem), sempre que existirem
# nos dados retornados pela API. Cada item é uma lista de nomes/prefixos
# candidatos — o primeiro que bater com algum segmento do caminho da coluna
# (ex: "endereco.municipio" bate com "municipio") é usado. Ajuste aqui se a
# Casa dos Dados usar nomes de campo diferentes.
COLUNAS_PRIORITARIAS = [
    ["capital_social"],
    ["municipio"],
    ["email"],
    ["telefone"],
    ["cnae_principal", "atividade_principal"],
    ["quadro_societario", "socios"],
]

CHAVES_NOME_SOCIO = ["nome", "nome_socio", "razao_social", "nome_completo"]
CHAVES_SOCIOS_POSSIVEIS = ["quadro_societario", "socios"]


def _nome_socio(socio):
    if isinstance(socio, dict):
        for chave in CHAVES_NOME_SOCIO:
            if socio.get(chave):
                return str(socio[chave])
        valores = [str(v) for v in socio.values() if v]
        return " ".join(valores)
    return str(socio) if socio is not None else ""


def _preparar_socios(records):
    """Reduz a lista de sócios (campo quadro_societario, ou socios em versões
    antigas da API) a uma única string legível por empresa, evitando colunas
    fragmentadas como quadro_societario[0].nome, quadro_societario[1].nome..."""
    preparados = []
    for record in records:
        if not isinstance(record, dict):
            preparados.append(record)
            continue
        record = dict(record)
        for chave in CHAVES_SOCIOS_POSSIVEIS:
            if isinstance(record.get(chave), list):
                record[chave] = " | ".join(filter(None, (_nome_socio(s) for s in record[chave])))
        preparados.append(record)
    return preparados


def _segmentos(coluna):
    return coluna.lower().replace("[", ".").replace("]", "").split(".")


def _bate_com_prioridade(coluna, candidatos):
    segmentos = _segmentos(coluna)
    return any(seg.startswith(candidato) for seg in segmentos for candidato in candidatos)


def _selecionar_e_ordenar_colunas(colunas):
    """Remove as colunas excluídas e traz as prioritárias para o início."""
    restantes = [c for c in colunas if c not in COLUNAS_EXCLUIDAS]

    usadas = set()
    ordenadas = []
    for candidatos in COLUNAS_PRIORITARIAS:
        for col in restantes:
            if col not in usadas and _bate_com_prioridade(col, candidatos):
                ordenadas.append(col)
                usadas.add(col)

    ordenadas.extend(col for col in restantes if col not in usadas)
    return ordenadas


def flatten_record(record, parent_key="", sep="."):
    """Achata um dict aninhado em um único nível, unindo listas simples com ' | '."""
    items = {}
    if isinstance(record, dict):
        for key, value in record.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
            items.update(flatten_record(value, new_key, sep))
    elif isinstance(record, list):
        if all(not isinstance(v, (dict, list)) for v in record):
            items[parent_key] = " | ".join(str(v) for v in record if v is not None)
        else:
            for idx, value in enumerate(record):
                items.update(flatten_record(value, f"{parent_key}[{idx}]", sep))
    else:
        items[parent_key] = record
    return items


def flatten_records(records):
    """Achata uma lista de registros e retorna (colunas_ordenadas, linhas_flat).

    Aplica _preparar_socios (uma coluna legível em vez de várias fragmentadas)
    e _selecionar_e_ordenar_colunas (remove COLUNAS_EXCLUIDAS e prioriza
    COLUNAS_PRIORITARIAS) antes de definir a lista final de colunas.
    """
    records = _preparar_socios(records)
    flat_rows = [flatten_record(r) for r in records]
    colunas = []
    vistas = set()
    for row in flat_rows:
        for key in row.keys():
            if key not in vistas:
                vistas.add(key)
                colunas.append(key)
    colunas = _selecionar_e_ordenar_colunas(colunas)
    return colunas, flat_rows


def build_xlsx(records, sheet_name="Empresas"):
    """Gera um arquivo XLSX em memória a partir de uma lista de registros (dicts)."""
    colunas, flat_rows = flatten_records(records)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "Empresas"

    ws.append(colunas)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in flat_rows:
        ws.append([row.get(col, "") for col in colunas])

    for idx, col in enumerate(colunas, start=1):
        max_len = max([len(col)] + [len(str(row.get(col, ""))) for row in flat_rows]) if flat_rows else len(col)
        ws.column_dimensions[get_column_letter(idx)].width = min(max(max_len + 2, 10), 60)

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
