"""Motor Nativo Python BPA: parser determinista de procesos en español e inglés.

Analiza descripciones en texto libre (sin LLM ni APIs externas) y construye un
ProcessGraph tipado con carriles (actores), tareas, decisiones agrupadas,
bucles de retrabajo y cierres semánticos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from alvea.models import (
    ActorKind,
    ActorLane,
    Direction,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
    sanitize_identifier,
    sanitize_label_text,
)


@dataclass(frozen=True, slots=True)
class ActorPattern:
    canonical_id: str
    canonical_name: str
    kind: ActorKind
    pattern: re.Pattern[str]


# Diccionario léxico normalizado ES / EN (ordenado de más específico a más general)
CANONICAL_ACTORS: tuple[ActorPattern, ...] = (
    ActorPattern("RIE", "Analista de Riesgos", ActorKind.DEPARTMENT, re.compile(r"\b(analista\s+de\s+riesgos?|riesgos?|risk\s+analyst|credit\s+analyst|underwriter)\b", re.I)),
    ActorPattern("LEG", "Área Legal", ActorKind.DEPARTMENT, re.compile(r"\b([aá]rea\s+legal|departamento\s+legal|legal|abogados?|jur[ií]dic[oa]|compliance|contract\s+team)\b", re.I)),
    ActorPattern("SRE", "Equipo DevOps / SRE", ActorKind.DEPARTMENT, re.compile(r"\b(devops|sre|ingenier[ií]a\s+de\s+confiabilidad|infraestructura|nivel\s*2|nivel\s*3|site\s+reliability)\b", re.I)),
    ActorPattern("N1", "Mesa de Ayuda / Soporte", ActorKind.DEPARTMENT, re.compile(r"\b(mesa\s+de\s+ayuda|soporte(?:\s+(?:t[eé]cnico|nivel\s*1))?|nivel\s*1|help\s*desk|service\s+desk|support\s+team)\b", re.I)),
    ActorPattern("QA", "Aseguramiento de Calidad (QA)", ActorKind.DEPARTMENT, re.compile(r"\b(aseguramiento\s+de\s+calidad|control\s+de\s+calidad|\bqa\b|quality\s+assurance|testers?)\b", re.I)),
    ActorPattern("AUD", "Auditoría Contable", ActorKind.DEPARTMENT, re.compile(r"\b(auditor[ií]a(?:\s+contable|\s+interna)?|auditor(?:es)?|audit\s+team|internal\s+audit)\b", re.I)),
    ActorPattern("TES", "Tesorería", ActorKind.DEPARTMENT, re.compile(r"\b(tesorer[ií]a|pagos|treasury|payroll)\b", re.I)),
    ActorPattern("CONT", "Contabilidad", ActorKind.DEPARTMENT, re.compile(r"\b(contabilidad|contador(?:es)?|accounting|accounts\s+payable)\b", re.I)),
    ActorPattern("FIN", "Gerencia de Finanzas", ActorKind.DEPARTMENT, re.compile(r"\b(gerente\s+de\s+finanzas|gerencia\s+de\s+finanzas|finanzas|cfo|finance\s+(?:manager|team|department))\b", re.I)),
    ActorPattern("COM", "Departamento de Compras", ActorKind.DEPARTMENT, re.compile(r"\b(departamento\s+de\s+compras|[aá]rea\s+de\s+compras|compras|abastecimiento|procurement|purchasing)\b", re.I)),
    ActorPattern("ALM", "Almacén / Logística", ActorKind.DEPARTMENT, re.compile(r"\b(almac[eé]n|bodega|log[ií]stica|warehouse|fulfillment|logistics)\b", re.I)),
    ActorPattern("RRHH", "Recursos Humanos (RRHH)", ActorKind.DEPARTMENT, re.compile(r"\b(recursos\s+humanos|rrhh|reclutador(?:a|es)?|talento\s+humano|atracci[oó]n\s+de\s+talento|\bhr\b|recruiter|human\s+resources)\b", re.I)),
    ActorPattern("TEC", "Líder Técnico", ActorKind.HUMAN, re.compile(r"\b(l[ií]der\s+(?:t[eé]cnico|de\s+equipo)|tech\s+lead|engineering\s+manager|architect)\b", re.I)),
    ActorPattern("OPS", "Operaciones de TI", ActorKind.DEPARTMENT, re.compile(r"\b(operaciones\s+de\s+ti|equipo\s+de\s+ti|sistemas\s+ti|it\s+ops|it\s+operations|operaciones)\b", re.I)),
    ActorPattern("GER", "Jefatura / Gerencia", ActorKind.HUMAN, re.compile(r"\b(jefe(?:\s+de\s+[aá]rea)?|jefatura|gerente|gerencia|supervisor(?:\s+directo)?|director(?:a)?|direcci[oó]n|comit[eé]|manager|director|vp|approver)\b", re.I)),
    ActorPattern("PROV", "Proveedor Externo", ActorKind.EXTERNAL, re.compile(r"\b(proveedor(?:es)?|vendor|supplier|tercero|partner)\b", re.I)),
    ActorPattern("VENT", "Equipo Comercial / Ventas", ActorKind.DEPARTMENT, re.compile(r"\b(ventas|comercial|ejecutivo\s+comercial|sales(?:\s+rep|\s+team)?|account\s+executive)\b", re.I)),
    ActorPattern("SYS", "Sistema / Plataforma", ActorKind.SYSTEM, re.compile(r"\b(el\s+sistema|la\s+app(?:\s+m[oó]vil)?|app\s+m[oó]vil|app\s+corporativa|sistema|plataforma|erp|crm|portal|bot|api|software|motor|automatizaci[oó]n|system|platform|application|mobile\s+app)\b", re.I)),
    ActorPattern("CLI", "Cliente / Solicitante", ActorKind.HUMAN, re.compile(r"\b(cliente|usuario(?:\s+final)?|postulante|candidato|solicitante|colaborador|empleado|paciente|estudiante|customer|client|user|applicant|employee|requester)\b", re.I)),
)

# Extracción abierta de roles no presentes en el diccionario (ej. "Médico de Triaje", "Aduanas")
OPEN_SUBJECT_PATTERN = re.compile(
    r"^(?:el|la|los|las|un|una|the|a|an)\s+"
    r"((?:[aá]rea|[dD]epartamento|[eE]quipo|[cC]omit[eé]|[gG]erente|[aA]nalista|[mM][eé]dico|[eE]specialista|[oO]ficial|[uU]nidad|[cC]entro)\s+(?:de\s+)?[A-Za-zÁÉÍÓÚÑáéíóúñ0-9/\-]{2,24}(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ0-9/\-]{2,20})?)",
    re.IGNORECASE,
)

TRANSFER_TARGET_PATTERN = re.compile(
    r"\b(?:pasa\s+a(?:l)?|escala\s+a(?:l)?|env[ií]a\s+a(?:l)?|deriva\s+a(?:l)?|devuelve\s+a(?:l)?|notifica\s+a(?:l)?|transfiere\s+a(?:l)?|routes?\s+to|escalates?\s+to|sends?\s+to|returns?\s+to)\s+"
    r"(?:la\s+bandeja\s+del?\s+|el\s+|la\s+|los\s+|the\s+)?"
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9/\-]*(?:\s+(?:de|del|y|&|of)?\s*[A-Za-zÁÉÍÓÚÑáéíóúñ0-9/\-]+){0,3})",
    re.IGNORECASE,
)

PREFIX_ACTOR_PATTERN = re.compile(r"^\s*(?:\[([^\]]{2,40})\]|([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ\s/&\-]{1,32})\s*:)\s*(.+)$")

CONDITIONAL_PREFIX_RE = re.compile(
    r"^(?:si\b|en\s+caso\s+de\s+(?:que\s+)?|cuando\b|if\b|in\s+case\b|when\b)\s+(.+?)(?:,|\bentonces\b|\bthen\b|\s+(?=(?:se\s+requiere|pasa\s+a|escala\s+a|el\s+sistema|la\s+app)\b))\s*(.+)$",
    re.IGNORECASE,
)

ELSE_PREFIX_RE = re.compile(
    r"^(?:de\s+lo\s+contrario|en\s+caso\s+contrario|si\s+no|sino|otherwise|else)\s*,?\s*(.+)$",
    re.IGNORECASE,
)

REWORK_RE = re.compile(
    r"\b(vuelve\s+a|regresa\s+a|devuelve\s+a|retorna\s+a|para\s+corregir|corregir|subsanar|reintenta|rehacer|reproceso|sent\s+back|returns?\s+to|rework|resubmit|fix)\b",
    re.IGNORECASE,
)

REJECT_RE = re.compile(
    r"(?:<=|<|\b(?:rechaz[aeo]|denieg[ae]|descart[ae]|archiv[ae]|cancel[ae]|no\s+cumple|inconsistenc|inv[aá]lid|menor\s+a|reject|den(?:y|ies)|declin|cancel|archive|fails?)\b)",
    re.IGNORECASE,
)

APPROVE_RE = re.compile(
    r"(?:>=|>|\b(?:aprueb[ae]|aprobad|cumple|v[aá]lid|mayor\s+o\s+igual|conforme|acept[ae]|approv|valid|passes?|meets?|accept)\b)",
    re.IGNORECASE,
)

END_SUCCESS_RE = re.compile(
    r"\b(finaliz[ae]|desembols[ae]|cierra\s+(?:el\s+)?ticket|liquid[ae]|programa\s+(?:el\s+)?pago|aprovision[ae]|restituci[oó]n|complet[ae]|concluy[ae]|entrega\s+final|disburs|completes?|closes?|settles?|provisions?)\b",
    re.IGNORECASE,
)

AUTO_RE = re.compile(
    r"\b(autom[aá]tic|api|bur[oó]|ocr|bot|erp|crm|portal|sistema|app|plataforma|software|digitalmente|notifica|correo|email|automat|webhook|script)\b",
    re.IGNORECASE,
)

DURATION_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(min(?:utos?)?|h(?:oras?|rs?)?|d[ií]as?|days?|hours?|minutes?)\b",
    re.IGNORECASE,
)

ENGLISH_HINTS = re.compile(r"\b(the|and|if|then|otherwise|when|customer|system|approves|rejects|sends|reviews)\b", re.I)
SPANISH_HINTS = re.compile(r"\b(el|la|los|las|si|entonces|luego|despu[eé]s|cliente|sistema|aprueba|rechaza|revisa|env[ií]a)\b", re.I)

STOPWORDS_FOR_SIMILARITY = frozenset({
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "a", "al", "y", "o", "por", "para",
    "con", "se", "su", "sus", "que", "es", "son", "si", "no", "the", "a", "an", "of", "to", "in", "for", "and",
})


@dataclass
class ParsedClause:
    raw: str
    is_conditional: bool = False
    is_else: bool = False
    condition_text: str = ""
    action_text: str = ""
    actor_id: str = ""
    actor_name: str = ""
    actor_kind: ActorKind = ActorKind.DEPARTMENT
    explicit_actor: bool = False


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)
    )


def _detect_language(text: str) -> str:
    en_hits = len(ENGLISH_HINTS.findall(text))
    es_hits = len(SPANISH_HINTS.findall(text))
    return "en" if en_hits > es_hits * 1.4 else "es"


def _extract_duration_min(text: str) -> float | None:
    match = DURATION_RE.search(text)
    if not match:
        return None
    val = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit.startswith(("d",)):
        return round(val * 480.0, 1)  # jornada 8h
    if unit.startswith(("h",)):
        return round(val * 60.0, 1)
    return round(val, 1)


def _match_canonical_actor(text: str) -> ActorPattern | None:
    for actor in CANONICAL_ACTORS:
        if actor.pattern.search(text):
            return actor
    return None


def _detect_actor_in_clause(text: str, known_lanes: dict[str, ActorLane]) -> tuple[str, str, ActorKind, bool]:
    # 1. Prefijo explícito tipo "[Finanzas] ..." o "Legal: ..."
    pref = PREFIX_ACTOR_PATTERN.match(text)
    if pref:
        name = (pref.group(1) or pref.group(2) or "").strip()
        canonical = _match_canonical_actor(name)
        if canonical:
            return canonical.canonical_id, canonical.canonical_name, canonical.kind, True
        lid = sanitize_identifier(_strip_accents(name).upper()[:10], prefix="L")
        return lid, sanitize_label_text(name, max_len=48), ActorKind.DEPARTMENT, True

    # 2. Diccionario léxico canónico — prioriza mención más temprana en la cláusula (el sujeto)
    best_pos = 10_000
    best_match: ActorPattern | None = None
    for actor in CANONICAL_ACTORS:
        m = actor.pattern.search(text)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_match = actor

    if best_match is not None:
        return best_match.canonical_id, best_match.canonical_name, best_match.kind, True

    # 3. Patrón sintáctico abierto (sujeto o destinatario de transferencia)
    m_open = OPEN_SUBJECT_PATTERN.match(text.strip())
    if m_open:
        raw_name = m_open.group(1).strip(" ,.;:")
        clean_name = sanitize_label_text(raw_name.title(), max_len=48)
        lid = sanitize_identifier(_strip_accents(raw_name).upper()[:10], prefix="L")
        if lid in known_lanes:
            lane = known_lanes[lid]
            return lane.id, lane.name, lane.kind, True
        return lid, clean_name, ActorKind.DEPARTMENT, True

    m_xfer = TRANSFER_TARGET_PATTERN.search(text)
    if m_xfer:
        raw_target = m_xfer.group(1).strip(" ,.;:")
        canonical = _match_canonical_actor(raw_target)
        if canonical:
            return canonical.canonical_id, canonical.canonical_name, canonical.kind, True
        if len(raw_target.split()) <= 4 and len(raw_target) >= 4:
            clean_name = sanitize_label_text(raw_target.title(), max_len=48)
            lid = sanitize_identifier(_strip_accents(raw_target).upper()[:10], prefix="L")
            return lid, clean_name, ActorKind.DEPARTMENT, True

    return "", "", ActorKind.DEPARTMENT, False


def _segment_text(text: str) -> list[str]:
    """Divide la descripción en cláusulas atómicas preservando cifras decimales/monetarias."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Proteger decimales y montos ($10,000 / 600.5)
    protected = re.sub(r"(\d)\.(\d)", r"\1__DOT__\2", normalized)

    # Dividir por saltos de línea, viñetas, numeración y fin de oración
    raw_parts = re.split(r"(?:\n+|(?<=[.?!;])\s+)", protected)

    clauses: list[str] = []
    for part in raw_parts:
        part = part.replace("__DOT__", ".").strip()
        part = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", part).strip()
        if not part or len(part) < 4:
            continue

        # Sub-dividir por conectores secuenciales fuertes si no es una condición
        subparts = re.split(
            r"(?:,\s*(?=(?:luego|despu[eé]s|posteriormente|a\s+continuaci[oó]n|finalmente|then|next|after\s+that|finally)\b))",
            part,
            flags=re.IGNORECASE,
        )
        for sub in subparts:
            sub = sub.strip(" .;")
            if not sub:
                continue

            # Dividir "X y Y" SOLO cuando el lado derecho introduce un actor distinto o un verbo de cierre
            if not CONDITIONAL_PREFIX_RE.match(sub) and not ELSE_PREFIX_RE.match(sub):
                y_split = re.split(r"\s+\b(?:y|and)\b\s+", sub, maxsplit=1, flags=re.IGNORECASE)
                if len(y_split) == 2:
                    left, right = y_split[0].strip(), y_split[1].strip()
                    left_actor = _match_canonical_actor(left)
                    right_actor = _match_canonical_actor(right)
                    if (
                        len(left.split()) >= 3
                        and len(right.split()) >= 3
                        and (
                            (right_actor and (not left_actor or right_actor.canonical_id != left_actor.canonical_id))
                            or END_SUCCESS_RE.search(right)
                        )
                    ):
                        clauses.append(left)
                        clauses.append(right)
                        continue
            clauses.append(sub)

    return clauses


def _synthesize_task_label(action: str, actor_name: str, is_start: bool = False) -> str:
    """Comprime una cláusula en una etiqueta ejecutiva clara (<= 58 caracteres)."""
    cleaned = PREFIX_ACTOR_PATTERN.sub(r"\3", action).strip(" .;,:")
    cleaned = re.sub(
        r"^(?:luego|despu[eé]s|posteriormente|a\s+continuaci[oó]n|entonces|finalmente|asimismo|adem[aá]s|then|next|finally|after\s+that)\s*,?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:el\s+caso\s+|la\s+solicitud\s+)?", "", cleaned, flags=re.IGNORECASE)

    # Capitalizar primera letra
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    if is_start and not cleaned.lower().startswith(("inicio", "start")):
        prefix = "Inicio: "
        cleaned = prefix + cleaned

    return sanitize_label_text(cleaned, max_len=58)


def _synthesize_decision_question(condition_text: str, lang: str) -> tuple[str, str]:
    """Genera la pregunta del rombo y la etiqueta concisa de la rama actual."""
    cond = condition_text.strip(" ,.;:¿?")
    cond_low = cond.lower()

    # Patrones numéricos concretos (score < 600, monto > $10,000)
    m_lt = re.search(r"([a-záéíóúñ\s]{2,22}?)\s+(?:es\s+)?(?:menor\s+(?:a|que)|<\s*|inferior\s+a|below|less\s+than)\s*([\$€]?\d[\d.,]*(?:\s*[a-zA-Z]{2,4})?)", cond, re.I)
    if m_lt:
        metric = m_lt.group(1).strip().split()[-1].capitalize()
        val = m_lt.group(2).strip()
        return f"¿{metric} >= {val}?", f"{metric} < {val}"

    m_gte = re.search(r"([a-záéíóúñ\s]{2,22}?)\s+(?:es\s+)?(?:mayor\s+o\s+igual\s+(?:a|que)|>=\s*|at\s+least)\s*([\$€]?\d[\d.,]*(?:\s*[a-zA-Z]{2,4})?)", cond, re.I)
    if m_gte:
        metric = m_gte.group(1).strip().split()[-1].capitalize()
        val = m_gte.group(2).strip()
        return f"¿{metric} >= {val}?", f"{metric} >= {val}"

    m_gt = re.search(r"([a-záéíóúñ\s]{2,22}?)\s+(?:excede|supera|es\s+mayor\s+(?:a|que)|>\s*|exceeds?|greater\s+than)\s*(?:los\s+|las\s+)?([\$€]?\d[\d.,]*(?:\s*[a-zA-Z]{2,4})?)", cond, re.I)
    if m_gt:
        metric = m_gt.group(1).strip().split()[-1].capitalize()
        val = m_gt.group(2).strip()
        return f"¿{metric} > {val}?", f"{metric} > {val}"

    # Patrones de aprobación / rechazo / cumplimiento
    if APPROVE_RE.search(cond_low) and not REJECT_RE.search(cond_low):
        branch = "Aprobado" if lang == "es" else "Approved"
        q = "¿Aprobado?" if len(cond.split()) <= 3 else f"¿{sanitize_label_text(cond, 42).capitalize()}?"
        return q, branch

    if REJECT_RE.search(cond_low):
        branch = "Rechazado" if lang == "es" else "Rejected"
        q = "¿Cumple validación?" if lang == "es" else "Passes validation?"
        if "inconsistenc" in cond_low or "error" in cond_low:
            branch = "Observado" if lang == "es" else "Issues found"
            q = "¿Comprobantes válidos?" if lang == "es" else "Valid documents?"
        elif "no cumple" in cond_low or "perfil" in cond_low:
            branch = "No cumple" if lang == "es" else "Does not meet"
            q = "¿Cumple requisitos?" if lang == "es" else "Meets criteria?"
        elif "menor" in cond_low or "crític" in cond_low or "critic" in cond_low:
            branch = sanitize_label_text(cond, 26).capitalize()
            q = "¿Severidad crítica?" if lang == "es" else "Critical severity?"
        return q, branch

    short_cond = sanitize_label_text(cond, 40)
    q = f"¿{short_cond[0].upper() + short_cond[1:]}?" if short_cond else ("¿Cumple criterio?" if lang == "es" else "Meets criteria?")
    branch = "Sí" if lang == "es" else "Yes"
    return q, branch


def _condition_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-záéíóúñ0-9]{3,}", _strip_accents(text.lower()))
    return {w for w in words if w not in STOPWORDS_FOR_SIMILARITY}


def _are_complementary_conditions(prev_cond: str, new_cond: str) -> bool:
    """Detecta si dos cláusulas 'Si ...' consecutivas pertenecen a la misma decisión."""
    p_low = prev_cond.lower()
    n_low = new_cond.lower()

    # Mismo número/umbral mencionado (ej. 600 vs 600)
    nums_p = set(re.findall(r"\d+(?:[.,]\d+)?", p_low))
    nums_n = set(re.findall(r"\d+(?:[.,]\d+)?", n_low))
    if nums_p and (nums_p & nums_n):
        return True

    # Polaridad opuesta (ej. "no cumple" vs "cumple", "rechaza" vs "aprueba", "menor" vs "mayor")
    p_neg = bool(REJECT_RE.search(p_low))
    n_neg = bool(REJECT_RE.search(n_low))
    p_pos = bool(APPROVE_RE.search(p_low))
    n_pos = bool(APPROVE_RE.search(n_low))
    if (p_neg and n_pos) or (p_pos and n_neg):
        return True

    # Solapamiento léxico sobre el sujeto de la condición (ej. "incidente menor" vs "incidente crítico")
    tok_p = _condition_tokens(prev_cond)
    tok_n = _condition_tokens(new_cond)
    if tok_p and tok_n and len(tok_p & tok_n) >= 1:
        return True

    # Sujeto elíptico ("si es mayor...", "si cumple", "si no")
    if len(n_low.split()) <= 5 and re.match(r"^(?:es|cumple|no\s+cumple|aprueba|rechaza|hay|tiene|existe)\b", n_low):
        return True

    return False


class LocalBPAEngine:
    """Motor determinista Python de análisis BPA (texto libre -> ProcessGraph)."""

    def parse(
        self,
        text: str,
        *,
        direction: Direction = Direction.LR,
        title: str | None = None,
    ) -> ProcessGraph:
        raw_text = (text or "").strip()
        if not raw_text:
            raise ValueError("La descripción del proceso no puede estar vacía.")

        lang = _detect_language(raw_text)
        raw_clauses = _segment_text(raw_text)
        if not raw_clauses:
            raw_clauses = [raw_text]

        lanes: dict[str, ActorLane] = {}
        parsed_clauses: list[ParsedClause] = []

        # 1. Clasificación de cláusulas y resolución anafórica de actores
        last_actor: tuple[str, str, ActorKind] = (
            "SOL",
            "Solicitante" if lang == "es" else "Requester",
            ActorKind.HUMAN,
        )

        for raw in raw_clauses:
            pc = ParsedClause(raw=raw, action_text=raw)

            m_else = ELSE_PREFIX_RE.match(raw)
            m_cond = CONDITIONAL_PREFIX_RE.match(raw) if not m_else else None

            if m_else:
                pc.is_conditional = True
                pc.is_else = True
                pc.condition_text = "De lo contrario" if lang == "es" else "Otherwise"
                pc.action_text = m_else.group(1).strip()
            elif m_cond:
                pc.is_conditional = True
                pc.condition_text = m_cond.group(1).strip()
                pc.action_text = m_cond.group(2).strip()
            else:
                pc.action_text = raw

            # Detectar actor en la acción (y si no hay, en toda la cláusula)
            aid, aname, akind, explicit = _detect_actor_in_clause(pc.action_text, lanes)
            if not explicit and pc.condition_text:
                aid, aname, akind, explicit = _detect_actor_in_clause(pc.condition_text, lanes)

            if explicit:
                pc.actor_id, pc.actor_name, pc.actor_kind, pc.explicit_actor = aid, aname, akind, True
                last_actor = (aid, aname, akind)
            else:
                pc.actor_id, pc.actor_name, pc.actor_kind, pc.explicit_actor = (*last_actor, False)

            if pc.actor_id not in lanes:
                lanes[pc.actor_id] = ActorLane(
                    id=pc.actor_id,
                    name=pc.actor_name,
                    kind=pc.actor_kind,
                    order=len(lanes),
                )

            parsed_clauses.append(pc)

        # 2. Construcción secuencial + decisiones agrupadas + bucles de retrabajo
        nodes: list[ProcessNode] = []
        edges: list[ProcessEdge] = []
        node_counter: dict[str, int] = {}

        def next_node_id(lane_id: str, suffix: str = "") -> str:
            node_counter[lane_id] = node_counter.get(lane_id, 0) + 1
            base = f"{lane_id}_{suffix}{node_counter[lane_id]}"
            return sanitize_identifier(base, prefix="N")

        active_tails: list[str] = []  # Nodos abiertos desde los que continúa el flujo principal
        last_decision_id: str | None = None
        last_decision_cond: str = ""
        last_decision_branches: list[str] = []
        last_review_node_id: str | None = None
        reject_end_id: str | None = None
        first_lane_id = parsed_clauses[0].actor_id

        for idx, clause in enumerate(parsed_clauses):
            lane = lanes[clause.actor_id]
            is_auto = lane.kind == ActorKind.SYSTEM or bool(AUTO_RE.search(clause.action_text))
            est_min = _extract_duration_min(clause.raw)
            dur_weight = 1.0 if is_auto else 2.5

            if idx == 0 and not clause.is_conditional:
                start_id = next_node_id(lane.id, "INI")
                nodes.append(
                    ProcessNode(
                        id=start_id,
                        label=_synthesize_task_label(clause.action_text, lane.name, is_start=True),
                        node_type=NodeType.START,
                        lane_id=lane.id,
                        is_automated=is_auto,
                        duration_weight=1.0,
                        estimated_duration_min=est_min,
                        source_clause=clause.raw[:220],
                    )
                )
                active_tails = [start_id]
                continue

            # Si la primera cláusula fuera condicional, crear un nodo START sintético
            if not nodes:
                start_id = next_node_id(first_lane_id, "INI")
                nodes.append(
                    ProcessNode(
                        id=start_id,
                        label="Inicio del proceso" if lang == "es" else "Process Start",
                        node_type=NodeType.START,
                        lane_id=first_lane_id,
                        is_automated=False,
                        duration_weight=1.0,
                    )
                )
                active_tails = [start_id]

            if clause.is_conditional:
                cond_actor_match = _match_canonical_actor(clause.condition_text)
                last_dec_node = next((n for n in nodes if n.id == last_decision_id), None) if last_decision_id else None
                tail_lane = next((n.lane_id for n in nodes if active_tails and n.id == active_tails[-1]), None)
                belongs_to_new_tail_actor = bool(
                    cond_actor_match
                    and last_dec_node is not None
                    and tail_lane is not None
                    and cond_actor_match.canonical_id == tail_lane
                    and tail_lane != last_dec_node.lane_id
                )
                reuse_decision = (
                    last_decision_id is not None
                    and not belongs_to_new_tail_actor
                    and (
                        clause.is_else
                        or _are_complementary_conditions(last_decision_cond, clause.condition_text)
                    )
                )

                question, branch_label = _synthesize_decision_question(clause.condition_text, lang)

                if reuse_decision and last_decision_id is not None:
                    dec_id = last_decision_id
                    if clause.is_else:
                        branch_label = "No" if any(b in ("Sí", "Yes", "Aprobado", "Approved") for b in last_decision_branches) else ("De lo contrario" if lang == "es" else "Otherwise")
                    elif branch_label in last_decision_branches:
                        branch_label = "Alternativa" if lang == "es" else "Alternative"
                else:
                    # Ubicar el rombo en el carril del evaluador (el actor anterior o el de la condición)
                    eval_lane_id = nodes[-1].lane_id if nodes else lane.id
                    cond_actor = _match_canonical_actor(clause.condition_text)
                    if cond_actor and cond_actor.canonical_id in lanes:
                        eval_lane_id = cond_actor.canonical_id
                    dec_id = next_node_id(eval_lane_id, "D")
                    nodes.append(
                        ProcessNode(
                            id=dec_id,
                            label=question,
                            node_type=NodeType.DECISION,
                            lane_id=eval_lane_id,
                            is_automated=lanes[eval_lane_id].kind == ActorKind.SYSTEM,
                            duration_weight=1.5,
                            risk_level="medium",
                            source_clause=clause.condition_text[:220],
                        )
                    )
                    for tail in active_tails:
                        edges.append(ProcessEdge(source=tail, target=dec_id))
                    last_decision_id = dec_id
                    last_decision_cond = clause.condition_text
                    last_decision_branches = []
                    # El nodo justo antes de la decisión es el mejor punto de retorno para bucles de retrabajo
                    if active_tails:
                        last_review_node_id = active_tails[0]
                    active_tails = []

                last_decision_branches.append(branch_label)

                # Crear nodo de acción para esta rama
                is_rework = bool(REWORK_RE.search(clause.action_text))
                is_reject_branch = bool(REJECT_RE.search(clause.action_text)) and not is_rework

                action_id = next_node_id(lane.id, "T")
                nodes.append(
                    ProcessNode(
                        id=action_id,
                        label=_synthesize_task_label(clause.action_text, lane.name),
                        node_type=NodeType.TASK,
                        lane_id=lane.id,
                        is_automated=is_auto,
                        duration_weight=dur_weight,
                        estimated_duration_min=est_min,
                        risk_level="high" if is_rework else "low",
                        source_clause=clause.raw[:220],
                    )
                )
                edges.append(
                    ProcessEdge(
                        source=dec_id,
                        target=action_id,
                        label=branch_label,
                        is_conditional=True,
                    )
                )

                if is_rework:
                    # Conectar bucle de retorno al nodo de evaluación previo
                    target_loop = last_review_node_id or nodes[0].id
                    if target_loop == action_id and len(nodes) >= 2:
                        target_loop = nodes[0].id
                    edges.append(
                        ProcessEdge(
                            source=action_id,
                            target=target_loop,
                            label="Reenvío corregido" if lang == "es" else "Resubmitted",
                            is_loop=True,
                        )
                    )
                elif is_reject_branch:
                    # Rama terminal de rechazo: cierra limpiamente en END_REJECT
                    if reject_end_id is None:
                        reject_end_id = next_node_id(first_lane_id, "FIN_REC")
                        nodes.append(
                            ProcessNode(
                                id=reject_end_id,
                                label="Fin: Solicitud rechazada" if lang == "es" else "End: Request Rejected",
                                node_type=NodeType.END_REJECT,
                                lane_id=first_lane_id,
                                is_automated=True,
                                duration_weight=0.5,
                            )
                        )
                    edges.append(ProcessEdge(source=action_id, target=reject_end_id))
                else:
                    # Rama de avance normal: queda abierta para continuar el flujo
                    active_tails.append(action_id)
                    if re.search(r"\b(revis|valid|evalu|verific|audit|analiz|review|check|assess)\b", clause.action_text, re.I):
                        last_review_node_id = action_id
            else:
                # Cláusula secuencial normal
                is_rework = bool(REWORK_RE.search(clause.action_text))
                task_id = next_node_id(lane.id, "T")
                nodes.append(
                    ProcessNode(
                        id=task_id,
                        label=_synthesize_task_label(clause.action_text, lane.name),
                        node_type=NodeType.TASK,
                        lane_id=lane.id,
                        is_automated=is_auto,
                        duration_weight=dur_weight,
                        estimated_duration_min=est_min,
                        source_clause=clause.raw[:220],
                    )
                )

                if active_tails:
                    for tail in active_tails:
                        edges.append(ProcessEdge(source=tail, target=task_id))
                elif last_decision_id is not None:
                    # Si la decisión anterior solo había tenido ramas cerradas/rework, conectar la rama positiva aquí
                    lbl = "Aprobado" if lang == "es" else "Approved"
                    edges.append(
                        ProcessEdge(
                            source=last_decision_id,
                            target=task_id,
                            label=lbl,
                            is_conditional=True,
                        )
                    )
                    last_decision_branches.append(lbl)
                else:
                    edges.append(ProcessEdge(source=nodes[-2].id, target=task_id))

                if is_rework and last_review_node_id and last_review_node_id != task_id:
                    edges.append(
                        ProcessEdge(
                            source=task_id,
                            target=last_review_node_id,
                            label="Revisión" if lang == "es" else "Re-check",
                            is_loop=True,
                        )
                    )
                    active_tails = []
                else:
                    active_tails = [task_id]
                    if re.search(r"\b(revis|valid|evalu|verific|audit|analiz|review|check|assess)\b", clause.action_text, re.I):
                        last_review_node_id = task_id
                # Una tarea secuencial nueva cierra la agrupación de la decisión anterior
                last_decision_id = None
                last_decision_cond = ""
                last_decision_branches = []

        # 3. Garantizar que toda decisión tenga >= 2 salidas (validez BPMN)
        out_counts: dict[str, int] = {n.id: 0 for n in nodes}
        for e in edges:
            out_counts[e.source] = out_counts.get(e.source, 0) + 1

        for node in list(nodes):
            if node.node_type == NodeType.DECISION and out_counts.get(node.id, 0) < 2:
                if reject_end_id is None:
                    reject_end_id = next_node_id(first_lane_id, "FIN_REC")
                    nodes.append(
                        ProcessNode(
                            id=reject_end_id,
                            label="Fin: Proceso rechazado / cancelado" if lang == "es" else "End: Rejected / Cancelled",
                            node_type=NodeType.END_REJECT,
                            lane_id=first_lane_id,
                            is_automated=True,
                            duration_weight=0.5,
                        )
                    )
                existing_labels = {e.label for e in edges if e.source == node.id}
                fallback_lbl = "Rechazado" if lang == "es" else "Rejected"
                if fallback_lbl in existing_labels:
                    fallback_lbl = "No" if lang == "es" else "No"
                edges.append(
                    ProcessEdge(
                        source=node.id,
                        target=reject_end_id,
                        label=fallback_lbl,
                        is_conditional=True,
                    )
                )

        # 4. Cerrar todas las colas abiertas no-terminales con un nodo END_SUCCESS limpio
        out_map: dict[str, int] = {}
        for e in edges:
            out_map[e.source] = out_map.get(e.source, 0) + 1

        open_non_terminal = [
            n for n in nodes
            if n.node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT)
            and out_map.get(n.id, 0) == 0
        ]

        if open_non_terminal or reject_end_id is None:
            final_lane_id = first_lane_id
            end_success_id = next_node_id(final_lane_id, "FIN")
            end_label = (
                "Fin: Proceso completado exitosamente"
                if lang == "es"
                else "End: Process Completed Successfully"
            )
            nodes.append(
                ProcessNode(
                    id=end_success_id,
                    label=end_label,
                    node_type=NodeType.END_SUCCESS,
                    lane_id=final_lane_id,
                    is_automated=True,
                    duration_weight=0.5,
                )
            )
            if open_non_terminal:
                for node in open_non_terminal:
                    edges.append(ProcessEdge(source=node.id, target=end_success_id))
            else:
                # Fallback seguro: conectar desde la última tarea/decisión (nunca desde END_REJECT)
                last_operational = next(
                    (n for n in reversed(nodes[:-1]) if n.node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT)),
                    None,
                )
                if last_operational is not None:
                    edges.append(ProcessEdge(source=last_operational.id, target=end_success_id))

        inferred_title = title or self._infer_title(raw_text, lang)

        return ProcessGraph(
            title=inferred_title,
            objective=sanitize_label_text(raw_clauses[0], max_len=180),
            language="en" if lang == "en" else "es",
            direction=direction,
            lanes=list(lanes.values()),
            nodes=nodes,
            edges=edges,
        )

    @staticmethod
    def _infer_title(text: str, lang: str) -> str:
        first = re.split(r"[.\n;]", text.strip())[0]
        words = first.split()[:7]
        candidate = " ".join(words)
        if len(candidate) < 6:
            return "Arquitectura de Proceso" if lang == "es" else "Process Architecture"
        return sanitize_label_text(candidate[0].upper() + candidate[1:], max_len=64)
