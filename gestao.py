"""Tratamento de divergências: status, responsáveis, justificativas, confirmação de causa com evidência. Valores originais são imutáveis."""
import json
from .db import agora

STATUS = ["Nova", "Em análise", "Causa identificada", "Aguardando validação", "Aguardando ajuste", "Justificada", "Resolvida", "Encerrada"]
PRIORIDADES = ["Baixa", "Média", "Alta", "Crítica"]
CAMPOS_EDITAVEIS = {"responsavel", "prioridade", "prazo", "providencia", "status"}  # não existe campo de valor: valores de origem não são editáveis


def obter(db, div_id):
    r = db.con.execute("SELECT * FROM divergencias WHERE id=?", (div_id,)).fetchone()
    if not r: raise KeyError(div_id)
    return dict(r)


def _evidencias(d):
    det = json.loads(d["detalhe"])
    regs = det.get("registros", [])
    n = sum(len(v) for v in regs.values()) if isinstance(regs, dict) else len(regs)
    return n


def confirmar_causa(db, div_id, usuario, causa, justificativa):
    """Só confirma com causa, justificativa e evidência (registros de origem) — nunca automaticamente."""
    d = obter(db, div_id)
    if not (causa or "").strip() or not (justificativa or "").strip():
        raise ValueError("Informe a causa e a justificativa para confirmar.")
    if _evidencias(d) == 0:
        raise ValueError("Sem evidência (registros de origem) para sustentar a causa confirmada.")
    db.x("UPDATE divergencias SET causa=?, justificativa=?, causa_status='confirmada' WHERE id=?", (causa.strip(), justificativa.strip(), div_id))
    db.hist(usuario, "divergencia", div_id, "causa confirmada", json.dumps(dict(causa=causa, justificativa=justificativa), ensure_ascii=False))


def atualizar(db, div_id, usuario, **campos):
    d = obter(db, div_id)
    for k in campos:
        if k not in CAMPOS_EDITAVEIS: raise ValueError(f"Campo não editável: {k}")
    novo = campos.get("status")
    if novo:
        if novo not in STATUS: raise ValueError("Status inválido.")
        if novo == "Causa identificada" and not d["causa"]: raise ValueError("Registre e confirme a causa antes de marcar 'Causa identificada'.")
        if novo == "Justificada" and not d["justificativa"]: raise ValueError("Registre a justificativa antes de marcar 'Justificada'.")
        if novo == "Resolvida" and d["causa_status"] != "confirmada": raise ValueError("Só é possível resolver com causa confirmada.")
        if novo == "Encerrada":
            if d["status"] != "Resolvida": raise ValueError("Encerre apenas divergências 'Resolvida'.")
            if not usuario: raise ValueError("Informe o responsável pelo encerramento.")
            campos["encerrado_por"] = usuario
        if novo in ("Resolvida", "Encerrada"): campos["data_resolucao"] = agora()
    campos = {k: v for k, v in campos.items() if d.get(k) != v}
    if not campos: return
    db.x(f"UPDATE divergencias SET {','.join(k + '=?' for k in campos)} WHERE id=?", list(campos.values()) + [div_id])
    db.hist(usuario, "divergencia", div_id, "atualizada", json.dumps({k: (d.get(k), v) for k, v in campos.items()}, ensure_ascii=False, default=str))


def comentar(db, div_id, usuario, texto):
    if not texto.strip(): raise ValueError("Comentário vazio.")
    db.x("INSERT INTO comentarios VALUES(?,?,?,?)", (div_id, agora(), usuario, texto.strip()))
    db.hist(usuario, "divergencia", div_id, "comentário", texto[:200])


def transferir(db, div_id, usuario, novo_resp):
    atualizar(db, div_id, usuario, responsavel=novo_resp)
