"""Leitura, mapeamento de colunas, normalização com log e validações. Arquivos originais nunca são alterados."""
import hashlib, io, json, re, unicodedata
import pandas as pd
from . import normalizacao as nz

CAMPOS = {
    "empresa": ["empresa", "company", "bukrs", "cia"],
    "estabelecimento": ["estabelecimento", "filial", "branch", "werks"],
    "cnpj": ["cnpj"],
    "periodo": ["periodo", "periodo_apuracao", "competencia", "mes_ano", "period"],
    "data_documento": ["data_documento", "data_doc", "dt_documento", "data_emissao", "emissao", "bldat"],
    "data_lancamento": ["data_lancamento", "dt_lancamento", "budat", "data_contabil"],
    "num_doc": ["numero_documento_fiscal", "num_doc", "nf", "nota_fiscal", "numero_nf", "documento_fiscal", "numero_documento"],
    "chave_acesso": ["chave_acesso", "chave_de_acesso", "chave_nfe", "chave", "access_key"],
    "doc_contabil": ["documento_contabil", "doc_contabil", "belnr", "numero_documento_contabil"],
    "item": ["item", "linha", "buzei", "item_documento"],
    "conta": ["conta_contabil", "conta", "hkont", "racct", "conta_sap", "conta_taxone"],
    "centro_custo": ["centro_de_custo", "centro_custo", "kostl", "cc"],
    "tributo": ["tributo", "imposto", "codigo_tributo", "tax"],
    "cfop": ["cfop"], "cst": ["cst", "classificacao_tributaria"], "ncm": ["ncm"],
    "base": ["base_calculo", "base_de_calculo", "base", "bc"],
    "aliquota": ["aliquota", "aliq"],
    "debito": ["debito", "valor_debito", "vl_debito"],
    "credito": ["credito", "valor_credito", "vl_credito"],
    "valor_imposto": ["valor_imposto", "vl_imposto"],
    "valor": ["valor", "saldo", "valor_saldo", "montante", "dmbtr", "valor_total"],
    "moeda": ["moeda", "currency", "waers"],
    "tipo_operacao": ["tipo_operacao"],
    "entrada_saida": ["entrada_saida", "ent_sai", "indicador_entrada_saida"],
    "regra_calculo": ["regra_calculo", "codigo_regra"],
    "origem": ["origem"],
}
IDENT = ["empresa", "estabelecimento", "cnpj", "num_doc", "doc_contabil", "item", "conta", "centro_custo", "tributo",
         "cfop", "cst", "ncm", "moeda", "tipo_operacao", "entrada_saida", "regra_calculo", "origem"]
DATAS = ["data_documento", "data_lancamento"]
DINHEIRO = ["base", "aliquota", "debito", "credito", "valor_imposto", "valor"]
IDENTIFICADORES = ["conta", "num_doc", "chave_acesso", "doc_contabil"]


def _h(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def automap(colunas):
    mapa, usadas = {}, set()
    por_h = {_h(c): c for c in colunas}
    for campo, aliases in CAMPOS.items():
        for a in aliases:
            if a in por_h and por_h[a] not in usadas:
                mapa[campo] = por_h[a]; usadas.add(por_h[a]); break
    return mapa


def ler_arquivo(conteudo: bytes, nome: str) -> pd.DataFrame:
    """Lê XLSX/XLS/CSV sem inferir tipos (preserva zeros à esquerda em texto)."""
    n = nome.lower()
    if n.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(conteudo), dtype=object)
    elif n.endswith((".csv", ".txt")):
        txt = conteudo.decode("utf-8-sig", errors="replace")
        sep = ";" if txt.count(";") > txt.count(",") else ","
        df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str, keep_default_na=False)
    else:
        raise ValueError("Formato não suportado. Use XLSX, XLS ou CSV.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def hash_arquivo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def normalizar(df, mapa, fonte, arquivo, fator_sinal=1, decimal="auto", excluir_invalidas=False):
    """Retorna (registros, log_transformacoes, problemas). 'valor' = valor de comparação já com a convenção de sinal da fonte."""
    problemas, log, regs = [], [], []
    for c in mapa.values():
        if c not in df.columns:
            problemas.append(dict(nivel="erro", tipo="Coluna ausente", mensagem=f"Coluna '{c}' não existe no arquivo.", linhas=[]))
    if not any(k in mapa for k in ("valor", "valor_imposto", "debito", "credito")):
        problemas.append(dict(nivel="erro", tipo="Colunas obrigatórias", mensagem="Mapeie ao menos uma coluna de valor (valor, valor do imposto, débito ou crédito).", linhas=[]))
    if not any(k in mapa for k in IDENTIFICADORES):
        problemas.append(dict(nivel="erro", tipo="Colunas obrigatórias", mensagem="Mapeie ao menos um identificador (conta, nº do documento, chave de acesso ou doc. contábil).", linhas=[]))
    if any(p["nivel"] == "erro" for p in problemas):
        return pd.DataFrame(), pd.DataFrame(), problemas
    vazios, invalidas = 0, {}
    for idx, row in df.iterrows():
        linha = int(idx) + 2  # linha da planilha (cabeçalho = 1)
        if all(nz._vazio(v) or str(v).strip() == "" for v in row.values):
            vazios += 1; continue
        r = dict(fonte=fonte, linha_origem=linha, arquivo=arquivo, registro_id=f"{fonte}:{linha}")
        r["dados_originais"] = json.dumps({str(k): (None if nz._vazio(v) else str(v)) for k, v in row.items()}, ensure_ascii=False)
        erro_linha = False
        for campo, col in mapa.items():
            orig = row[col]
            try:
                if campo in IDENT: novo, regra = nz.ident(orig), "texto: espaços aparados, maiúsculas, zeros preservados"
                elif campo == "chave_acesso": novo, regra = nz.chave_acesso(orig), "chave: espaços removidos"
                elif campo in DATAS: novo, regra = nz.parse_data(orig), "data -> AAAA-MM-DD"
                elif campo == "periodo": novo, regra = nz.parse_periodo(orig), "período -> AAAA-MM"
                else: novo, regra = nz.parse_valor(orig, decimal), f"valor monetário (decimal={decimal})"
            except ValueError as e:
                problemas.append(dict(nivel="erro", tipo="Valor/data inválido", mensagem=f"Linha {linha}, coluna '{col}': {e}", linhas=[linha]))
                novo, regra, erro_linha = None, "inválido", True
            r[campo] = novo
            so, sn = ("" if nz._vazio(orig) else str(orig)), ("" if novo is None else str(novo))
            if so != sn:
                log.append(dict(registro_id=r["registro_id"], linha_origem=linha, campo=campo, valor_original=so, valor_normalizado=sn, regra=regra))
        # valor de comparação (ausência permanece None, nunca vira zero)
        if r.get("valor") is not None: vc, rg = r["valor"], "valor"
        elif r.get("valor_imposto") is not None: vc, rg = r["valor_imposto"], "valor_imposto"
        elif r.get("debito") is not None or r.get("credito") is not None: vc, rg = (r.get("debito") or 0) - (r.get("credito") or 0), "débito − crédito"
        else: vc, rg = None, "sem valor"
        r["valor_original"] = vc
        r["valor"] = None if vc is None else round(vc * fator_sinal, 2)
        r["regra_valor"] = f"{rg} × fator de sinal da fonte ({fator_sinal:+d})"
        if not r.get("periodo"):
            d = r.get("data_lancamento") or r.get("data_documento")
            if d is not None:
                r["periodo"] = f"{d.year:04d}-{d.month:02d}"
                log.append(dict(registro_id=r["registro_id"], linha_origem=linha, campo="periodo", valor_original="", valor_normalizado=r["periodo"], regra="período derivado da data de lançamento/documento"))
        if r["valor"] is None:
            problemas.append(dict(nivel="alerta", tipo="Sem valor", mensagem=f"Linha {linha}: sem valor monetário (tratado como ausente, não como zero).", linhas=[linha]))
        if erro_linha: invalidas[linha] = True
        regs.append(r)
    reg = pd.DataFrame(regs)
    if vazios:
        problemas.append(dict(nivel="alerta", tipo="Registros vazios", mensagem=f"{vazios} linha(s) vazia(s) ignorada(s).", linhas=[]))
    if reg.empty:
        problemas.append(dict(nivel="erro", tipo="Arquivo vazio", mensagem="Nenhum registro encontrado.", linhas=[]))
        return reg, pd.DataFrame(log), problemas
    if excluir_invalidas and invalidas:
        reg = reg[~reg.linha_origem.isin(invalidas)]
        for p in problemas:
            if p["tipo"] == "Valor/data inválido":
                p["nivel"] = "alerta"; p["mensagem"] += " (linha excluída do processamento)"
    if "periodo" in reg and reg["periodo"].nunique() > 1:
        problemas.append(dict(nivel="alerta", tipo="Períodos inconsistentes", mensagem=f"O arquivo contém mais de um período: {sorted(reg['periodo'].dropna().unique())}.", linhas=[]))
    for k in ("chave_acesso", "num_doc"):
        if k in reg and reg[k].notna().any():
            sub = [k, "valor"] + (["conta"] if "conta" in reg else [])
            d = reg[reg[k].notna() & reg.duplicated(subset=sub, keep=False)]
            if len(d):
                problemas.append(dict(nivel="alerta", tipo="Documentos duplicados", mensagem=f"{len(d)} registro(s) com {k} repetido e mesmo valor/conta.", linhas=sorted(d.linha_origem.tolist())))
            break
    if "chave_acesso" in reg:
        ruim = reg[reg.chave_acesso.notna() & ~reg.chave_acesso.astype(str).str.fullmatch(r"\d{44}")]
        if len(ruim):
            problemas.append(dict(nivel="alerta", tipo="Formato inesperado", mensagem=f"{len(ruim)} chave(s) de acesso fora do padrão de 44 dígitos.", linhas=ruim.linha_origem.tolist()))
    return reg.reset_index(drop=True), pd.DataFrame(log), problemas
