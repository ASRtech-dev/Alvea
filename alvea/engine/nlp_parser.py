"""ALVEA v3.0 Native Python Workflow Engine (Deterministic EN/ES Parser).

Converts free prose, numbered/bulleted lists, `Actor: Action` scripts, and
`Source -> Target: Action` handoff notation into a typed ProcessGraph with:
- Industry-agnostic open-domain actor discovery & alias merging
- Multi-branch `if / else if / else` decision gateways
- True parallel `fork / join` blocks (`in parallel`, `simultaneously`, `meanwhile`)
- Rework / feedback loop detection
- Fine-grained node classification (`start`, `task`, `system`, `subprocess`, `wait`, `decision`, `parallel`, `end_success`, `end_reject`)
- Explicit SLA/duration extraction feeding weighted NetworkX critical path
- Anti-ReDoS flat regexes and strict graph bounds (MAX_LANES/NODES/EDGES)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

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

MAX_LANES = 16
MAX_NODES = 75
MAX_EDGES = 190
MAX_PARALLEL_BRANCHES = 6


@dataclass(frozen=True, slots=True)
class ActorPattern:
    canonical_id: str
    canonical_name_en: str
    canonical_name_es: str
    kind: ActorKind
    pattern: re.Pattern[str]


# Industry-agnostic bilingual actor dictionary (most specific first)
CANONICAL_ACTORS: tuple[ActorPattern, ...] = (
    ActorPattern("RISK", "Risk Analyst", "Analista de Riesgos", ActorKind.DEPARTMENT, re.compile(r"\b(risk\s+analyst|credit\s+analyst|underwriter|risk\s+team|analista\s+de\s+riesgos?|riesgos?)\b", re.I)),
    ActorPattern("LEG", "Legal & Compliance", "Área Legal", ActorKind.DEPARTMENT, re.compile(r"\b(legal\s+team|legal\s+department|compliance|counsel|attorney|legal|[aá]rea\s+legal|abogados?|jur[ií]dic[oa])\b", re.I)),
    ActorPattern("SRE", "DevOps / SRE", "Equipo DevOps / SRE", ActorKind.DEPARTMENT, re.compile(r"\b(devops|sre|site\s+reliability|platform\s+engineering|infrastructure|tier\s*[23]|nivel\s*[23])\b", re.I)),
    ActorPattern("SUP", "Support Desk", "Mesa de Ayuda / Soporte", ActorKind.DEPARTMENT, re.compile(r"\b(help\s*desk|service\s+desk|support\s+team|tier\s*1|support|mesa\s+de\s+ayuda|soporte(?:\s+t[eé]cnico)?|nivel\s*1)\b", re.I)),
    ActorPattern("QA", "Quality Assurance (QA)", "Aseguramiento de Calidad (QA)", ActorKind.DEPARTMENT, re.compile(r"\b(quality\s+assurance|\bqa\b|testers?|qa\s+team|control\s+de\s+calidad|aseguramiento\s+de\s+calidad)\b", re.I)),
    ActorPattern("SEC", "Security / InfoSec", "Seguridad / InfoSec", ActorKind.DEPARTMENT, re.compile(r"\b(infosec|security\s+team|soc\s+analyst|cybersecurity|seguridad\s+inform[aá]tica)\b", re.I)),
    ActorPattern("AUD", "Internal Audit", "Auditoría Contable", ActorKind.DEPARTMENT, re.compile(r"\b(internal\s+audit|audit\s+team|auditors?|auditor[ií]a(?:\s+contable|\s+interna)?)\b", re.I)),
    ActorPattern("TRE", "Treasury / Payroll", "Tesorería", ActorKind.DEPARTMENT, re.compile(r"\b(treasury|payroll|disbursements?|tesorer[ií]a)\b", re.I)),
    ActorPattern("ACC", "Accounting", "Contabilidad", ActorKind.DEPARTMENT, re.compile(r"\b(accounting|accounts\s+payable|billing|bookkeeping|contabilidad|facturaci[oó]n)\b", re.I)),
    ActorPattern("FIN", "Finance", "Gerencia de Finanzas", ActorKind.DEPARTMENT, re.compile(r"\b(finance\s+(?:manager|team|department)|cfo|finance|geren(?:te|cia)\s+de\s+finanzas|finanzas)\b", re.I)),
    ActorPattern("PROC", "Procurement", "Departamento de Compras", ActorKind.DEPARTMENT, re.compile(r"\b(procurement|purchasing|sourcing|departamento\s+de\s+compras|compras|abastecimiento)\b", re.I)),
    ActorPattern("LOG", "Warehouse & Logistics", "Almacén / Logística", ActorKind.DEPARTMENT, re.compile(r"\b(warehouse|fulfillment|logistics|shipping|carrier|customs|almac[eé]n|bodega|log[ií]stica|aduanas)\b", re.I)),
    ActorPattern("HR", "Human Resources (HR)", "Recursos Humanos (RRHH)", ActorKind.DEPARTMENT, re.compile(r"\b(human\s+resources|\bhr\b|recruiter|talent\s+acquisition|people\s+ops|recursos\s+humanos|rrhh|reclutador(?:a|es)?)\b", re.I)),
    ActorPattern("ENG", "Engineering / Tech Lead", "Líder Técnico / Ingeniería", ActorKind.DEPARTMENT, re.compile(r"\b(tech\s+lead|engineering\s+manager|software\s+engineer|developer|architect|engineering|l[ií]der\s+t[eé]cnico|desarrollador(?:es)?)\b", re.I)),
    ActorPattern("IT", "IT Operations", "Operaciones de TI", ActorKind.DEPARTMENT, re.compile(r"\b(it\s+ops|it\s+operations|it\s+admin|\bit\b|operaciones\s+de\s+ti|equipo\s+de\s+ti)\b", re.I)),
    ActorPattern("CLIN", "Clinical / Medical Team", "Equipo Médico / Triaje", ActorKind.DEPARTMENT, re.compile(r"\b(triage\s+nurse|physician|doctor|clinician|pharmacy|laboratory|lab\s+tech|m[eé]dico(?:\s+de\s+triaje)?|enfermer[oa]|farmacia|laboratorio)\b", re.I)),
    ActorPattern("MGT", "Management / Approver", "Jefatura / Gerencia", ActorKind.HUMAN, re.compile(r"\b(manager|supervisor|director|vp|executive|approver|committee|jefe(?:\s+de\s+[aá]rea)?|jefatura|gerente|gerencia|comit[eé])\b", re.I)),
    ActorPattern("VEN", "External Vendor", "Proveedor Externo", ActorKind.EXTERNAL, re.compile(r"\b(vendor|supplier|partner|third[\s-]party|insurer|insurance|proveedor(?:es)?|tercero)\b", re.I)),
    ActorPattern("SLS", "Sales / Account Team", "Equipo Comercial / Ventas", ActorKind.DEPARTMENT, re.compile(r"\b(sales\s+(?:rep|team)|account\s+executive|sales|ventas|comercial)\b", re.I)),
    ActorPattern("OPS", "Operations", "Operaciones", ActorKind.DEPARTMENT, re.compile(r"\b(operations\s+team|operations|ops\s+team|operaciones)\b", re.I)),
    ActorPattern("SYS", "System / Platform", "Sistema / Plataforma", ActorKind.SYSTEM, re.compile(r"\b(api\s+gateway|payment\s+gateway|database|\bdb\b|webhook|erp|crm|portal|mobile\s+app|web\s+app|system|platform|engine|bot|automation|software|service|el\s+sistema|la\s+app|app\s+m[oó]vil|sistema|plataforma)\b", re.I)),
    ActorPattern("CUST", "Customer / Requester", "Cliente / Solicitante", ActorKind.HUMAN, re.compile(r"\b(customer|client|end\s+user|user|applicant|candidate|employee|requester|patient|student|cliente|usuario|postulante|candidato|solicitante|colaborador|empleado|paciente)\b", re.I)),
)

# Control keywords excluded from `Actor: Action` prefixes
CONTROL_PREFIXES = frozenset({
    "if", "else", "elif", "else if", "otherwise", "when", "unless", "then",
    "parallel", "in parallel", "simultaneously", "meanwhile", "fork", "join",
    "step", "note", "start", "end", "options", "two options", "si", "sino",
    "en paralelo", "mientras tanto", "de lo contrario", "cuando", "paso",
    "nota", "inicio", "fin", "opciones", "dos opciones", "tienen dos opciones",
})

# Anti-ReDoS flat patterns
ARROW_LINE_RE = re.compile(r"^\s*([A-Za-z0-9ÁÉÍÓÚÑáéíóúñ &/()._-]{2,42}?)\s*(?:->|→|=>)\s*([A-Za-z0-9ÁÉÍÓÚÑáéíóúñ &/()._-]{2,42}?)\s*:\s*(.+)$")
CHAIN_ARROW_RE = re.compile(r"^\s*([A-Za-z0-9ÁÉÍÓÚÑáéíóúñ &/()._-]{2,42}?)\s*(?:->|→|=>)\s*([A-Za-z0-9ÁÉÍÓÚÑáéíóúñ &/()._-]{2,42})(?:\s*(?:->|→|=>)\s*.+)?$")
PREFIX_ACTOR_RE = re.compile(r"^\s*(?:\[([^\]]{2,42})\]|([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-z0-9ÁÉÍÓÚÑáéíóúñ &/()._-]{1,36})\s*:)\s*(.+)$")

PARALLEL_HEADER_RE = re.compile(
    r"^(?:in\s+parallel|simultaneously|at\s+the\s+same\s+time|concurrently|parallel\s+tasks?|fork|en\s+paralelo|simult[aá]neamente|al\s+mismo\s+tiempo)\s*[:,]?\s*(.*)$",
    re.IGNORECASE,
)
MEANWHILE_PREFIX_RE = re.compile(r"^(?:meanwhile|at\s+the\s+same\s+time|simultaneously|in\s+parallel|mientras\s+tanto|en\s+paralelo)\s*,?\s+(.+)$", re.IGNORECASE)
JOIN_PREFIX_RE = re.compile(r"^(?:once\s+(?:both|all)\s+(?:complete|finish|are\s+done)|after\s+(?:both|all)|when\s+(?:both|all)\s+(?:complete|finish)|then\s+merge|join|cuando\s+(?:ambos|todos)\s+terminen|una\s+vez\s+completados)\s*,?\s*(.*)$", re.IGNORECASE)

ELIF_PREFIX_RE = re.compile(
    r"^(?:else\s+if|elif|elseif|or\s+if|si\s+en\s+cambio|si\s+por\s+el\s+contrario)\s+(.+?)(?:,|\bthen\b|\bentonces\b)\s*(.+)$",
    re.IGNORECASE,
)
ELSE_PREFIX_RE = re.compile(
    r"^(?:else|otherwise|if\s+not|de\s+lo\s+contrario|en\s+caso\s+contrario|si\s+no|sino)\s*,?\s*(.+)$",
    re.IGNORECASE,
)
IF_PREFIX_RE = re.compile(
    r"^(?:if|when|in\s+case(?:\s+of)?|si|cuando|en\s+caso\s+de(?:\s+que)?)\s+(.+?)(?:,|\bthen\b|\bentonces\b|\s+(?=(?:the\s+system|the\s+app|manager|it\s+|routes?\s+to|escalates?\s+to|se\s+requiere|pasa\s+a|escala\s+a|el\s+sistema|la\s+app)\b))\s*(.+)$",
    re.IGNORECASE,
)

OPEN_SUBJECT_RE = re.compile(
    r"^(?:the|a|an|el|la|los|las|un|una)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-z0-9ÁÉÍÓÚÑáéíóúñ/\-]*(?:\s+[A-Za-z0-9ÁÉÍÓÚÑáéíóúñ/\-]+){0,2})\s+(?:reviews?|checks?|validates?|approves?|rejects?|sends?|submits?|creates?|processes?|updates?|verifies?|revisa|valida|aprueba|rechaza|env[ií]a|crea|procesa|verifica|eval[uú]a)\b",
    re.IGNORECASE,
)

TRANSFER_TARGET_RE = re.compile(
    r"\b(?:routes?\s+to|assigns?\s+to|escalates?\s+to|sends?\s+to|hands?\s+off\s+to|returns?\s+to|pasa\s+al?|deriva\s+al?|escala\s+al?|env[ií]a\s+al?|devuelve\s+al?)\s+(?:the\s+|el\s+|la\s+)?([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-z0-9ÁÉÍÓÚÑáéíóúñ/\-]*(?:\s+[A-Za-z0-9ÁÉÍÓÚÑáéíóúñ/\-]+){0,2})",
    re.IGNORECASE,
)

REWORK_RE = re.compile(
    r"\b(returns?\s+to|sent\s+back|loops?\s+back|rework|resubmit|fix\s+and\s+resubmit|retry|vuelve\s+a|regresa\s+a|devuelve\s+a|retorna\s+a|corregir|subsanar|reintenta|reproceso)\b",
    re.IGNORECASE,
)
REJECT_RE = re.compile(
    r"(?:<=|!=|<|\b(?:reject\w*|den(?:y|ies|ied)|declin\w*|cancel\w*|archiv\w*|fail\w*|invalid|below|less\s+than|rechaz\w*|denieg\w*|descart\w*|no\s+cumple|inconsistenc\w*|inv[aá]lid\w*|menor\s+a)\b)",
    re.IGNORECASE,
)
APPROVE_RE = re.compile(
    r"(?:>=|>|\b(?:approv\w*|valid\w*|pass(?:es|ed)?|meets?|accept\w*|above|exceeds?|greater\s+than|aprueb\w*|aprobad\w*|cumple|v[aá]lid\w*|mayor\s+o\s+igual|conforme|acept\w*)\b)",
    re.IGNORECASE,
)
END_SUCCESS_RE = re.compile(
    r"\b(completes?|closes?|disburs\w*|settles?|provisions?|fulfills?|finishes?|concludes?|finaliz\w*|desembols\w*|liquid\w*|cierra\s+(?:el\s+)?(?:ticket|caso)|concluy\w*)\b",
    re.IGNORECASE,
)

WAIT_NODE_RE = re.compile(
    r"\b(waits?\b|waiting\b|delay\b|sla\s+(?:timer|window)|timer\b|holds?\s+for|batch\s+cutoff|pending\s+for|espera\b|aguarda\b|plazo\s+de)\b",
    re.IGNORECASE,
)
SUBPROCESS_NODE_RE = re.compile(
    r"\b(sub[\s-]?process|sub[\s-]?workflow|procedure|background\s+check|\bkyc\b|onboarding\s+process|subproceso|procedimiento)\b",
    re.IGNORECASE,
)
SYSTEM_NODE_RE = re.compile(
    r"\b(api\b|database|\bdb\b|erp\b|crm\b|webhook|cron|syncs?|automati(?:c|cally)|scoring|bureau|charge\s+card|persists?|encrypts?|notifies?\s+automatically|email\s+notification|autom[aá]tic\w*|bur[oó]|digitalmente)\b",
    re.IGNORECASE,
)

DURATION_RE = re.compile(
    r"(?:\[|\()?\b(\d+(?:[.,]\d+)?)\s*(s(?:ec(?:onds?)?)?|m(?:in(?:utes?|utos?)?)?|h(?:rs?|ours?|oras?)?|d(?:ays?|i[aá]s?|[ií]as?)?|w(?:eeks?|semanas?)?)\b(?:\]|\))?",
    re.IGNORECASE,
)

SPANISH_HINTS_RE = re.compile(r"\b(el|la|los|las|si|entonces|luego|despu[eé]s|cliente|sistema|aprueba|rechaza|revisa|env[ií]a|devuelve|para)\b", re.I)
ENGLISH_HINTS_RE = re.compile(r"\b(the|and|if|then|otherwise|when|customer|system|approves?|rejects?|sends?|reviews?|submits?|returns?)\b", re.I)

STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "are", "if", "not",
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "a", "al", "y", "o", "por", "para", "si", "no",
})


@dataclass
class StructuredItem:
    raw: str
    kind: str = "step"  # "step" | "parallel_group" | "join_marker"
    action_text: str = ""
    condition_text: str = ""
    cond_kind: str = ""  # "" | "if" | "elif" | "else"
    source_actor_hint: str = ""
    target_actor_hint: str = ""
    is_meanwhile: bool = False
    parallel_branches: list["StructuredItem"] = field(default_factory=list)


def _strip_accents(val: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", val) if not unicodedata.combining(ch))


def _detect_language(text: str) -> str:
    es_hits = len(SPANISH_HINTS_RE.findall(text))
    en_hits = len(ENGLISH_HINTS_RE.findall(text))
    # Default to English unless Spanish clearly dominates
    return "es" if es_hits > max(2, en_hits * 1.4) else "en"


def _extract_duration_min(text: str) -> float | None:
    match = DURATION_RE.search(text)
    if not match:
        return None
    val = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit.startswith("w"):
        return round(val * 2400.0, 1)
    if unit.startswith("d"):
        return round(val * 480.0, 1)
    if unit.startswith("h"):
        return round(val * 60.0, 1)
    if unit.startswith("s"):
        return round(max(0.1, val / 60.0), 2)
    return round(val, 1)


def _strip_duration_tokens(text: str) -> str:
    cleaned = re.sub(r"\s*[\[(]\s*\d+(?:[.,]\d+)?\s*(?:s|sec\w*|m|min\w*|h|hr\w*|hours?|d|days?|d[ií]as?|w|weeks?)\s*[\])]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip(" ,.;:")


class ActorRegistry:
    """Industry-agnostic actor discovery with canonical dictionary & alias merging."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.lanes: dict[str, ActorLane] = {}
        self.alias_to_id: dict[str, str] = {}

    def _canonical_match(self, text: str) -> ActorPattern | None:
        best_pos = 10_000
        best: ActorPattern | None = None
        for ap in CANONICAL_ACTORS:
            m = ap.pattern.search(text)
            if m and m.start() < best_pos:
                best_pos = m.start()
                best = ap
        return best

    def register_explicit(self, raw_name: str) -> ActorLane:
        clean_name = sanitize_label_text(raw_name.strip(" []():"), max_len=48)
        norm_key = _strip_accents(clean_name).lower()
        if norm_key in self.alias_to_id:
            return self.lanes[self.alias_to_id[norm_key]]

        canonical = self._canonical_match(clean_name)
        if canonical and canonical.canonical_id in self.lanes:
            self.alias_to_id[norm_key] = canonical.canonical_id
            return self.lanes[canonical.canonical_id]

        # Alias merge against existing lane names (e.g., "analyst" -> "Risk Analyst")
        for lid, existing in self.lanes.items():
            ex_norm = _strip_accents(existing.name).lower()
            if norm_key in ex_norm or ex_norm in norm_key:
                self.alias_to_id[norm_key] = lid
                return existing

        if len(self.lanes) >= MAX_LANES:
            return next(iter(self.lanes.values()))

        kind = canonical.kind if canonical else (
            ActorKind.SYSTEM if SYSTEM_NODE_RE.search(clean_name) else ActorKind.DEPARTMENT
        )
        lid = canonical.canonical_id if (canonical and canonical.canonical_id not in self.lanes) else sanitize_identifier(
            _strip_accents(clean_name).upper()[:10], prefix="L"
        )
        if lid in self.lanes:
            self.alias_to_id[norm_key] = lid
            return self.lanes[lid]

        lane = ActorLane(id=lid, name=clean_name, kind=kind, order=len(self.lanes))
        self.lanes[lid] = lane
        self.alias_to_id[norm_key] = lid
        return lane

    def detect_in_text(self, text: str) -> ActorLane | None:
        # 1. Canonical match
        canonical = self._canonical_match(text)
        if canonical is not None:
            if canonical.canonical_id in self.lanes:
                return self.lanes[canonical.canonical_id]
            name = canonical.canonical_name_es if self.lang == "es" else canonical.canonical_name_en
            if len(self.lanes) >= MAX_LANES:
                return next(iter(self.lanes.values()))
            lane = ActorLane(id=canonical.canonical_id, name=name, kind=canonical.kind, order=len(self.lanes))
            self.lanes[lane.id] = lane
            self.alias_to_id[_strip_accents(name).lower()] = lane.id
            return lane

        # 2. Match existing registered open-domain lanes
        low_text = _strip_accents(text).lower()
        for alias, lid in self.alias_to_id.items():
            if len(alias) >= 4 and re.search(rf"\b{re.escape(alias)}\b", low_text):
                return self.lanes[lid]

        # 3. Open syntactic subject
        m_subj = OPEN_SUBJECT_RE.match(text.strip())
        if m_subj:
            raw_subj = m_subj.group(1).strip(" ,.;:")
            if raw_subj.lower() not in CONTROL_PREFIXES and len(raw_subj) >= 3:
                return self.register_explicit(raw_subj.title())

        # 4. Transfer target ("routes to Customs", "escalates to Billing")
        m_xfer = TRANSFER_TARGET_RE.search(text)
        if m_xfer:
            raw_tgt = m_xfer.group(1).strip(" ,.;:")
            if raw_tgt.lower() not in CONTROL_PREFIXES and len(raw_tgt) >= 3:
                return self.register_explicit(raw_tgt.title())

        return None


def _parse_single_clause(raw: str) -> StructuredItem:
    text = raw.strip(" ;")
    item = StructuredItem(raw=text)

    # Join marker ("Once both complete, ...")
    m_join = JOIN_PREFIX_RE.match(text)
    if m_join:
        rest = m_join.group(1).strip()
        if not rest:
            item.kind = "join_marker"
            return item
        text = rest

    # Meanwhile / inline parallel trigger
    m_mean = MEANWHILE_PREFIX_RE.match(text)
    if m_mean:
        item.is_meanwhile = True
        text = m_mean.group(1).strip()

    # Arrow notation: `Source -> Target: Action`
    m_arrow = ARROW_LINE_RE.match(text)
    if m_arrow:
        item.source_actor_hint = m_arrow.group(1).strip()
        item.target_actor_hint = m_arrow.group(2).strip()
        item.action_text = m_arrow.group(3).strip()
        return item

    # Multi-branch conditionals: else if / else / if
    m_elif = ELIF_PREFIX_RE.match(text)
    if m_elif:
        item.cond_kind = "elif"
        item.condition_text = m_elif.group(1).strip()
        item.action_text = m_elif.group(2).strip()
        return item

    m_else = ELSE_PREFIX_RE.match(text)
    if m_else:
        item.cond_kind = "else"
        item.condition_text = "Otherwise"
        item.action_text = m_else.group(1).strip()
        return item

    m_if = IF_PREFIX_RE.match(text)
    if m_if:
        item.cond_kind = "if"
        item.condition_text = m_if.group(1).strip()
        item.action_text = m_if.group(2).strip()
        return item

    # Explicit `Actor: Action` or `[Actor] Action`
    m_pref = PREFIX_ACTOR_RE.match(text)
    if m_pref:
        actor_cand = (m_pref.group(1) or m_pref.group(2) or "").strip()
        if actor_cand.lower() not in CONTROL_PREFIXES:
            item.target_actor_hint = actor_cand
            item.action_text = m_pref.group(3).strip()
            return item

    item.action_text = text
    return item


def _extract_structured_items(text: str) -> list[StructuredItem]:
    """Multi-format extractor: arrow chains, Actor:Action, parallel blocks, lists, and prose."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [ln.rstrip() for ln in normalized.split("\n")]

    items: list[StructuredItem] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or len(line) < 3:
            continue

        # 1. Parallel block header ("In parallel:" followed by bulleted/numbered items OR inline "and")
        m_par = PARALLEL_HEADER_RE.match(line)
        if m_par:
            remainder = m_par.group(1).strip()
            branches: list[StructuredItem] = []
            if remainder:
                # Inline split on " and " / " y " / ";"
                parts = re.split(r"\s*(?:;|\band\b|\by\b)\s*", remainder, flags=re.I)
                for p in parts[:MAX_PARALLEL_BRANCHES]:
                    p = p.strip(" .;")
                    if len(p) >= 3:
                        branches.append(_parse_single_clause(p))
            else:
                # Collect subsequent bulleted/numbered lines belonging to this parallel block
                while i < len(lines):
                    nxt = lines[i].strip()
                    if not nxt:
                        i += 1
                        break
                    if re.match(r"^(?:[-*•+]|\d+[.)])\s+", nxt):
                        clean_b = re.sub(r"^(?:[-*•+]|\d+[.)])\s+", "", nxt).strip()
                        if clean_b and len(branches) < MAX_PARALLEL_BRANCHES:
                            branches.append(_parse_single_clause(clean_b))
                        i += 1
                    else:
                        break
            if len(branches) >= 2:
                items.append(StructuredItem(raw=line, kind="parallel_group", parallel_branches=branches))
                continue
            if len(branches) == 1:
                items.append(branches[0])
                continue

        # 2. Pure arrow chain without colon (`Customer -> System -> Risk -> Legal`)
        if not ARROW_LINE_RE.match(line) and "->" in line and ":" not in line:
            parts = [p.strip(" .;:") for p in re.split(r"\s*(?:->|→|=>)\s*", line) if p.strip()]
            if len(parts) >= 2 and all(len(p) <= 48 for p in parts):
                for idx_p, part in enumerate(parts):
                    if idx_p == 0:
                        items.append(StructuredItem(raw=part, action_text=part))
                    else:
                        items.append(StructuredItem(raw=f"{parts[idx_p - 1]} -> {part}", source_actor_hint=parts[idx_p - 1], action_text=part))
                continue

        # 3. Single structured line (`Actor: Action` or `A -> B: Action`) ONLY if it is a single clause (no sentence breaks)
        clean_line = re.sub(r"^(?:[-*•+]|\d+[.)])\s+", "", line).strip()
        has_multi_sentence = bool(re.search(r"[.?!;]\s+\S", clean_line))
        if not has_multi_sentence and (
            ARROW_LINE_RE.match(clean_line)
            or (
                PREFIX_ACTOR_RE.match(clean_line)
                and (PREFIX_ACTOR_RE.match(clean_line).group(1) or PREFIX_ACTOR_RE.match(clean_line).group(2) or "").strip().lower() not in CONTROL_PREFIXES
            )
        ):
            items.append(_parse_single_clause(clean_line))
            continue

        # 4. Prose sentence segmentation (preserving decimals & common abbreviations)
        protected = re.sub(r"(\d)\.(\d)", r"\1__DOT__\2", clean_line)
        protected = re.sub(r"\b(e\.g|i\.e|vs|Dr|Mr|Ms|Inc)\.", r"\1__DOT__", protected, flags=re.I)
        sentences = re.split(r"(?<=[.?!;])\s+", protected)

        for sent in sentences:
            sent = sent.replace("__DOT__", ".").strip(" .;")
            if not sent or len(sent) < 3:
                continue

            # Split sequential connectors inside a long sentence
            subparts = re.split(
                r",\s*(?=(?:then|next|after\s+that|subsequently|finally|meanwhile|simultaneously|luego|despu[eé]s|posteriormente|finalmente|mientras\s+tanto)\b)",
                sent,
                flags=re.I,
            )
            for sub in subparts:
                sub = sub.strip(" .;")
                if not sub:
                    continue
                # Inline parallel phrase inside prose
                m_par_in = PARALLEL_HEADER_RE.match(sub)
                if m_par_in and m_par_in.group(1):
                    p_parts = re.split(r"\s*(?:;|\band\b|\by\b)\s*", m_par_in.group(1), flags=re.I)
                    p_branches = [_parse_single_clause(p.strip(" .;")) for p in p_parts[:MAX_PARALLEL_BRANCHES] if len(p.strip()) >= 3]
                    if len(p_branches) >= 2:
                        items.append(StructuredItem(raw=sub, kind="parallel_group", parallel_branches=p_branches))
                        continue
                # Split "X and Y" when right side introduces a different actor or end verb
                if not IF_PREFIX_RE.match(sub) and not ELIF_PREFIX_RE.match(sub) and not ELSE_PREFIX_RE.match(sub):
                    y_split = re.split(r"\s+\b(?:and|y)\b\s+", sub, maxsplit=1, flags=re.I)
                    if len(y_split) == 2:
                        left, right = y_split[0].strip(), y_split[1].strip()
                        if len(left.split()) >= 3 and len(right.split()) >= 3:
                            left_ap = next((a for a in CANONICAL_ACTORS if a.pattern.search(left)), None)
                            right_ap = next((a for a in CANONICAL_ACTORS if a.pattern.search(right)), None)
                            if (right_ap and (not left_ap or right_ap.canonical_id != left_ap.canonical_id)) or END_SUCCESS_RE.search(right):
                                items.append(_parse_single_clause(left))
                                items.append(_parse_single_clause(right))
                                continue
                items.append(_parse_single_clause(sub))

    return items


def _classify_node_type(action_text: str, lane: ActorLane) -> tuple[NodeType, bool]:
    if WAIT_NODE_RE.search(action_text):
        return NodeType.WAIT, False
    if SUBPROCESS_NODE_RE.search(action_text):
        return NodeType.SUBPROCESS, False
    if lane.kind == ActorKind.SYSTEM or SYSTEM_NODE_RE.search(action_text):
        return NodeType.SYSTEM, True
    return NodeType.TASK, False


def _synthesize_label(action: str, is_start: bool = False, lang: str = "en") -> str:
    cleaned = _strip_duration_tokens(action)
    cleaned = re.sub(
        r"^(?:then|next|finally|after\s+that|subsequently|meanwhile|simultaneously|luego|despu[eé]s|posteriormente|finalmente|mientras\s+tanto)\s*,?\s*",
        "",
        cleaned,
        flags=re.I,
    ).strip(" .;,:")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    if is_start and not cleaned.lower().startswith(("start", "inicio")):
        cleaned = ("Inicio: " if lang == "es" else "Start: ") + cleaned
    return sanitize_label_text(cleaned, max_len=64)


def _synthesize_decision(cond_text: str, lang: str) -> tuple[str, str]:
    cond = _strip_duration_tokens(cond_text).strip(" ,.;:¿?")
    low = cond.lower()

    m_num = re.search(r"([a-zA-ZÁÉÍÓÚÑáéíóúñ ]{2,22}?)\s+(?:is\s+|es\s+)?(<=|>=|<|>|below|less\s+than|above|exceeds?|greater\s+than|at\s+least|menor\s+(?:a|que)|mayor\s+o\s+igual\s+(?:a|que)|supera|excede)\s*(?:los\s+|las\s+)?([\$€£]?\d[\d.,]*(?:\s*[a-zA-Z]{2,4})?)", cond, re.I)
    if m_num:
        metric = m_num.group(1).strip().split()[-1].capitalize()
        op_raw = m_num.group(2).lower()
        val = m_num.group(3).strip()
        if any(k in op_raw for k in ("<=",)):
            return f"{metric} <= {val}?", f"{metric} <= {val}"
        if any(k in op_raw for k in ("<", "below", "less", "menor")):
            return f"{metric} >= {val}?", f"{metric} < {val}"
        if any(k in op_raw for k in (">=", "at least", "mayor o igual")):
            return f"{metric} >= {val}?", f"{metric} >= {val}"
        return f"{metric} > {val}?", f"{metric} > {val}"

    if APPROVE_RE.search(low) and not REJECT_RE.search(low):
        branch = "Aprobado" if lang == "es" else "Approved"
        q = "¿Aprobado?" if lang == "es" else "Approved?"
        if len(cond.split()) > 3:
            short = sanitize_label_text(cond, 42)
            q = f"{short[0].upper() + short[1:]}?"
        return q, branch

    if REJECT_RE.search(low):
        branch = "Rechazado" if lang == "es" else "Rejected"
        q = "¿Cumple validación?" if lang == "es" else "Passes validation?"
        if "invalid" in low or "inconsist" in low or "error" in low:
            branch = "Observado" if lang == "es" else "Invalid"
            q = "¿Datos válidos?" if lang == "es" else "Valid inputs?"
        return q, branch

    short = sanitize_label_text(cond, 42)
    q = f"{short[0].upper() + short[1:]}?" if short else ("¿Cumple criterio?" if lang == "es" else "Meets criteria?")
    branch = "Sí" if lang == "es" else "Yes"
    return q, branch


def _word_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", _strip_accents(text.lower())) if w not in STOPWORDS}


def _are_complementary(prev_cond: str, new_cond: str) -> bool:
    p_low, n_low = prev_cond.lower(), new_cond.lower()
    nums_p = set(re.findall(r"\d+(?:[.,]\d+)?", p_low))
    nums_n = set(re.findall(r"\d+(?:[.,]\d+)?", n_low))
    if nums_p and (nums_p & nums_n):
        return True
    if (bool(REJECT_RE.search(p_low)) and bool(APPROVE_RE.search(n_low))) or (bool(APPROVE_RE.search(p_low)) and bool(REJECT_RE.search(n_low))):
        return True
    if _word_tokens(prev_cond) & _word_tokens(new_cond):
        return True
    return False


class LocalBPAEngine:
    """ALVEA v3.0 Deterministic Workflow Parser (multi-format, parallel fork/join, multi-branch, SLAs)."""

    def parse(
        self,
        text: str,
        *,
        direction: Direction = Direction.LR,
        title: str | None = None,
    ) -> ProcessGraph:
        raw_text = (text or "").strip()
        if not raw_text:
            raise ValueError("Workflow description cannot be empty.")

        lang = _detect_language(raw_text)
        items = _extract_structured_items(raw_text)
        if not items:
            items = [StructuredItem(raw=raw_text, action_text=raw_text)]

        registry = ActorRegistry(lang)
        default_actor = registry.register_explicit("Solicitante" if lang == "es" else "Requester")

        nodes: list[ProcessNode] = []
        edges: list[ProcessEdge] = []
        node_counter: dict[str, int] = {}

        def next_id(lane_id: str, suffix: str = "") -> str:
            node_counter[lane_id] = node_counter.get(lane_id, 0) + 1
            return sanitize_identifier(f"{lane_id}_{suffix}{node_counter[lane_id]}", prefix="N")

        def add_node(node: ProcessNode) -> bool:
            if len(nodes) >= MAX_NODES:
                return False
            nodes.append(node)
            return True

        def add_edge(edge: ProcessEdge) -> None:
            if len(edges) < MAX_EDGES and edge.source != edge.target:
                edges.append(edge)

        last_lane: ActorLane = default_actor
        active_tails: list[str] = []
        parallel_tails: list[str] = []
        last_decision_id: str | None = None
        last_decision_cond: str = ""
        last_decision_branches: list[str] = []
        last_review_node_id: str | None = None
        reject_end_id: str | None = None
        first_lane_id: str | None = None
        last_node_by_lane: dict[str, str] = {}

        def resolve_lane(item: StructuredItem, fallback: ActorLane) -> ActorLane:
            if item.target_actor_hint:
                return registry.register_explicit(item.target_actor_hint)
            found = registry.detect_in_text(item.action_text)
            if found is not None:
                return found
            if item.condition_text:
                found_c = registry.detect_in_text(item.condition_text)
                if found_c is not None:
                    return found_c
            return fallback

        def close_parallel_if_open(join_lane: ActorLane) -> None:
            nonlocal parallel_tails, active_tails
            if len(parallel_tails) >= 2:
                join_id = next_id(join_lane.id, "JOIN")
                if add_node(
                    ProcessNode(
                        id=join_id,
                        label="Sync / Join" if lang == "en" else "Sincronizar / Unir",
                        node_type=NodeType.PARALLEL,
                        lane_id=join_lane.id,
                        is_automated=True,
                        duration_weight=0.5,
                    )
                ):
                    for pt in parallel_tails:
                        add_edge(ProcessEdge(source=pt, target=join_id, is_parallel=True))
                    active_tails = [join_id]
                parallel_tails = []
            elif len(parallel_tails) == 1:
                active_tails = list(parallel_tails)
                parallel_tails = []

        def ensure_start(lane: ActorLane) -> None:
            nonlocal first_lane_id, active_tails
            if nodes:
                return
            first_lane_id = lane.id
            sid = next_id(lane.id, "INI")
            add_node(
                ProcessNode(
                    id=sid,
                    label="Process Start" if lang == "en" else "Inicio del Proceso",
                    node_type=NodeType.START,
                    lane_id=lane.id,
                    is_automated=lane.kind == ActorKind.SYSTEM,
                    duration_weight=1.0,
                )
            )
            active_tails = [sid]
            last_node_by_lane[lane.id] = sid

        for idx, item in enumerate(items):
            if len(nodes) >= MAX_NODES - 2:
                break

            if item.kind == "join_marker":
                close_parallel_if_open(last_lane)
                continue

            # 1. Parallel Fork-Join Block
            if item.kind == "parallel_group":
                ensure_start(last_lane)
                close_parallel_if_open(last_lane)
                fork_id = next_id(last_lane.id, "FORK")
                if not add_node(
                    ProcessNode(
                        id=fork_id,
                        label="Parallel Split" if lang == "en" else "Inicio en Paralelo",
                        node_type=NodeType.PARALLEL,
                        lane_id=last_lane.id,
                        is_automated=True,
                        duration_weight=0.5,
                    )
                ):
                    continue
                for tail in active_tails:
                    add_edge(ProcessEdge(source=tail, target=fork_id))
                active_tails = []
                parallel_tails = []
                for br in item.parallel_branches[:MAX_PARALLEL_BRANCHES]:
                    br_lane = resolve_lane(br, last_lane)
                    ntype, is_auto = _classify_node_type(br.action_text, br_lane)
                    est_min = _extract_duration_min(br.raw)
                    bid = next_id(br_lane.id, "P")
                    if add_node(
                        ProcessNode(
                            id=bid,
                            label=_synthesize_label(br.action_text, lang=lang),
                            node_type=ntype,
                            lane_id=br_lane.id,
                            is_automated=is_auto,
                            estimated_duration_min=est_min,
                            source_clause=br.raw[:220],
                        )
                    ):
                        add_edge(ProcessEdge(source=fork_id, target=bid, label="Parallel" if lang == "en" else "Paralelo", is_parallel=True))
                        parallel_tails.append(bid)
                        last_node_by_lane[br_lane.id] = bid
                last_decision_id = None
                continue

            # 2. Inline `Meanwhile` parallel attachment to previous step
            if item.is_meanwhile and nodes:
                br_lane = resolve_lane(item, last_lane)
                last_lane = br_lane
                ntype, is_auto = _classify_node_type(item.action_text, br_lane)
                est_min = _extract_duration_min(item.raw)
                bid = next_id(br_lane.id, "P")
                # Fork from predecessor of current active tail if available
                parent_id = active_tails[0] if active_tails else nodes[-1].id
                prev_edges = [e.source for e in edges if e.target == parent_id]
                fork_anchor = prev_edges[-1] if prev_edges else parent_id
                if add_node(
                    ProcessNode(
                        id=bid,
                        label=_synthesize_label(item.action_text, lang=lang),
                        node_type=ntype,
                        lane_id=br_lane.id,
                        is_automated=is_auto,
                        estimated_duration_min=est_min,
                        source_clause=item.raw[:220],
                    )
                ):
                    add_edge(ProcessEdge(source=fork_anchor, target=bid, label="Parallel" if lang == "en" else "Paralelo", is_parallel=True))
                    if not parallel_tails:
                        parallel_tails = list(active_tails)
                    parallel_tails.append(bid)
                    active_tails = []
                    last_node_by_lane[br_lane.id] = bid
                continue

            # 3. Resolve Source -> Target arrow handoffs & standard actors
            src_lane: ActorLane | None = None
            if item.source_actor_hint:
                src_lane = registry.register_explicit(item.source_actor_hint)
            lane = resolve_lane(item, src_lane or last_lane)
            last_lane = lane

            if parallel_tails:
                close_parallel_if_open(lane)

            # First non-conditional node becomes START
            if idx == 0 and not item.cond_kind:
                first_lane_id = (src_lane or lane).id
                start_lane = lane
                if src_lane and src_lane.id != lane.id and not nodes:
                    # Create origin trigger in Source lane and hand off to Target lane
                    s0 = next_id(src_lane.id, "INI")
                    add_node(
                        ProcessNode(
                            id=s0,
                            label=_synthesize_label(f"Initiate handoff to {lane.name}" if lang == "en" else f"Inicia envío a {lane.name}", is_start=True, lang=lang),
                            node_type=NodeType.START,
                            lane_id=src_lane.id,
                            is_automated=src_lane.kind == ActorKind.SYSTEM,
                            duration_weight=1.0,
                        )
                    )
                    last_node_by_lane[src_lane.id] = s0
                    active_tails = [s0]
                else:
                    sid = next_id(start_lane.id, "INI")
                    add_node(
                        ProcessNode(
                            id=sid,
                            label=_synthesize_label(item.action_text, is_start=True, lang=lang),
                            node_type=NodeType.START,
                            lane_id=start_lane.id,
                            is_automated=start_lane.kind == ActorKind.SYSTEM or bool(SYSTEM_NODE_RE.search(item.action_text)),
                            estimated_duration_min=_extract_duration_min(item.raw),
                            source_clause=item.raw[:220],
                        )
                    )
                    active_tails = [sid]
                    last_node_by_lane[start_lane.id] = sid
                    continue

            ensure_start(src_lane or lane)

            # 4. Conditional Branching (`if / else if / else`)
            if item.cond_kind:
                last_dec_node = next((n for n in nodes if n.id == last_decision_id), None) if last_decision_id else None
                tail_lane = next((n.lane_id for n in nodes if active_tails and n.id == active_tails[-1]), None)
                cond_actor_lane = registry.detect_in_text(item.condition_text) if item.condition_text else None
                belongs_to_new_tail = bool(
                    cond_actor_lane
                    and last_dec_node is not None
                    and tail_lane is not None
                    and cond_actor_lane.id == tail_lane
                    and tail_lane != last_dec_node.lane_id
                )

                reuse = (
                    last_decision_id is not None
                    and not belongs_to_new_tail
                    and (
                        item.cond_kind in ("elif", "else")
                        or _are_complementary(last_decision_cond, item.condition_text)
                    )
                )

                question, branch_lbl = _synthesize_decision(item.condition_text, lang)

                if reuse and last_decision_id is not None:
                    dec_id = last_decision_id
                    if item.cond_kind == "else":
                        branch_lbl = "No" if any(b in ("Yes", "Sí", "Approved", "Aprobado") for b in last_decision_branches) else ("Otherwise" if lang == "en" else "De lo contrario")
                    elif item.cond_kind == "elif":
                        branch_lbl = sanitize_label_text(item.condition_text, 32) or branch_lbl
                    elif branch_lbl in last_decision_branches:
                        branch_lbl = "Alternative" if lang == "en" else "Alternativa"
                else:
                    eval_lane_id = (cond_actor_lane.id if cond_actor_lane else (nodes[-1].lane_id if nodes else lane.id))
                    dec_id = next_id(eval_lane_id, "D")
                    add_node(
                        ProcessNode(
                            id=dec_id,
                            label=question,
                            node_type=NodeType.DECISION,
                            lane_id=eval_lane_id,
                            is_automated=registry.lanes[eval_lane_id].kind == ActorKind.SYSTEM,
                            risk_level="medium",
                            source_clause=item.condition_text[:220],
                        )
                    )
                    for tail in active_tails:
                        add_edge(ProcessEdge(source=tail, target=dec_id))
                    last_decision_id = dec_id
                    last_decision_cond = item.condition_text
                    last_decision_branches = []
                    if active_tails:
                        last_review_node_id = active_tails[0]
                    active_tails = []

                last_decision_branches.append(branch_lbl)

                is_rework = bool(REWORK_RE.search(item.action_text))
                is_reject = bool(REJECT_RE.search(item.action_text)) and not is_rework
                ntype, is_auto = _classify_node_type(item.action_text, lane)
                act_id = next_id(lane.id, "T")
                add_node(
                    ProcessNode(
                        id=act_id,
                        label=_synthesize_label(item.action_text, lang=lang),
                        node_type=ntype,
                        lane_id=lane.id,
                        is_automated=is_auto,
                        estimated_duration_min=_extract_duration_min(item.raw),
                        risk_level="high" if is_rework else "low",
                        source_clause=item.raw[:220],
                    )
                )
                add_edge(ProcessEdge(source=dec_id, target=act_id, label=branch_lbl, is_conditional=True))
                last_node_by_lane[lane.id] = act_id

                if is_rework:
                    target_loop = self._select_rework_target(nodes, item.action_text, last_review_node_id, act_id)
                    add_edge(
                        ProcessEdge(
                            source=act_id,
                            target=target_loop,
                            label="Rework / Resubmit" if lang == "en" else "Reenvío corregido",
                            is_loop=True,
                        )
                    )
                elif is_reject:
                    if reject_end_id is None:
                        rej_lane = first_lane_id or lane.id
                        reject_end_id = next_id(rej_lane, "END_REJ")
                        add_node(
                            ProcessNode(
                                id=reject_end_id,
                                label="End: Request Rejected" if lang == "en" else "Fin: Solicitud Rechazada",
                                node_type=NodeType.END_REJECT,
                                lane_id=rej_lane,
                                is_automated=True,
                            )
                        )
                    add_edge(ProcessEdge(source=act_id, target=reject_end_id))
                else:
                    active_tails.append(act_id)
                    if re.search(r"\b(review|check|validat|audit|assess|evaluat|revis|verific|analiz)\b", item.action_text, re.I):
                        last_review_node_id = act_id
                continue

            # 5. Standard Sequential Step
            is_rework = bool(REWORK_RE.search(item.action_text))
            ntype, is_auto = _classify_node_type(item.action_text, lane)
            tid = next_id(lane.id, "T")
            add_node(
                ProcessNode(
                    id=tid,
                    label=_synthesize_label(item.action_text, lang=lang),
                    node_type=ntype,
                    lane_id=lane.id,
                    is_automated=is_auto,
                    estimated_duration_min=_extract_duration_min(item.raw),
                    source_clause=item.raw[:220],
                )
            )

            # Connect from explicit arrow source if available, else active_tails
            if src_lane and src_lane.id in last_node_by_lane and not active_tails:
                add_edge(ProcessEdge(source=last_node_by_lane[src_lane.id], target=tid))
            elif active_tails:
                for tail in active_tails:
                    add_edge(ProcessEdge(source=tail, target=tid))
            elif last_decision_id is not None:
                lbl = "Approved" if lang == "en" else "Aprobado"
                add_edge(ProcessEdge(source=last_decision_id, target=tid, label=lbl, is_conditional=True))
                last_decision_branches.append(lbl)
            elif len(nodes) >= 2:
                add_edge(ProcessEdge(source=nodes[-2].id, target=tid))

            last_node_by_lane[lane.id] = tid

            if is_rework and last_review_node_id and last_review_node_id != tid:
                add_edge(ProcessEdge(source=tid, target=last_review_node_id, label="Retry" if lang == "en" else "Revisión", is_loop=True))
                active_tails = []
            else:
                active_tails = [tid]
                if re.search(r"\b(review|check|validat|audit|assess|evaluat|revis|verific|analiz)\b", item.action_text, re.I):
                    last_review_node_id = tid
            last_decision_id = None
            last_decision_cond = ""
            last_decision_branches = []

        # Close any open parallel block at end of workflow
        if parallel_tails:
            close_parallel_if_open(last_lane)

        # Ensure every decision has >= 2 outgoing branches
        out_counts: dict[str, int] = {}
        for e in edges:
            out_counts[e.source] = out_counts.get(e.source, 0) + 1

        for node in list(nodes):
            if node.node_type == NodeType.DECISION and out_counts.get(node.id, 0) < 2:
                if reject_end_id is None:
                    rej_lane = first_lane_id or node.lane_id
                    reject_end_id = next_id(rej_lane, "END_REJ")
                    add_node(
                        ProcessNode(
                            id=reject_end_id,
                            label="End: Rejected / Cancelled" if lang == "en" else "Fin: Rechazado / Cancelado",
                            node_type=NodeType.END_REJECT,
                            lane_id=rej_lane,
                            is_automated=True,
                        )
                    )
                existing_lbls = {e.label for e in edges if e.source == node.id}
                fb_lbl = ("Rejected" if lang == "en" else "Rechazado")
                if fb_lbl in existing_lbls:
                    fb_lbl = "No"
                add_edge(ProcessEdge(source=node.id, target=reject_end_id, label=fb_lbl, is_conditional=True))

        # Close open non-terminal nodes with END_SUCCESS (never connect END_REJECT -> END_SUCCESS)
        out_map: dict[str, int] = {}
        for e in edges:
            out_map[e.source] = out_map.get(e.source, 0) + 1

        open_non_terminal = [
            n for n in nodes
            if n.node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT)
            and out_map.get(n.id, 0) == 0
        ]

        if open_non_terminal or reject_end_id is None:
            end_lane = first_lane_id or last_lane.id
            end_id = next_id(end_lane, "END")
            if add_node(
                ProcessNode(
                    id=end_id,
                    label="End: Workflow Completed" if lang == "en" else "Fin: Proceso Completado",
                    node_type=NodeType.END_SUCCESS,
                    lane_id=end_lane,
                    is_automated=True,
                )
            ):
                if open_non_terminal:
                    for n in open_non_terminal:
                        add_edge(ProcessEdge(source=n.id, target=end_id))
                else:
                    last_op = next(
                        (n for n in reversed(nodes[:-1]) if n.node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT)),
                        None,
                    )
                    if last_op is not None:
                        add_edge(ProcessEdge(source=last_op.id, target=end_id))

        # Remove unused synthetic default lane if never referenced
        used_lanes = {n.lane_id for n in nodes}
        active_lanes = [ln for ln in registry.lanes.values() if ln.id in used_lanes] or list(registry.lanes.values())

        # Apply hybrid duration weights (minutes if any explicit SLA exists, else relative points)
        self._assign_duration_weights(nodes)

        inferred_title = title or self._infer_title(raw_text, lang)
        objective = sanitize_label_text(items[0].raw, max_len=180)

        return ProcessGraph(
            title=inferred_title,
            objective=objective,
            language="es" if lang == "es" else "en",
            direction=direction,
            lanes=active_lanes,
            nodes=nodes,
            edges=edges,
        )

    @staticmethod
    def _select_rework_target(
        nodes: list[ProcessNode],
        action_text: str,
        last_review_id: str | None,
        current_id: str,
    ) -> str:
        # 1. Lexicon overlap with earlier operational nodes
        act_tokens = _word_tokens(action_text)
        best_id: str | None = None
        best_score = 0
        for n in nodes:
            if n.id == current_id or n.node_type in (NodeType.END_SUCCESS, NodeType.END_REJECT, NodeType.DECISION):
                continue
            overlap = len(act_tokens & _word_tokens(n.label))
            if overlap > best_score:
                best_score = overlap
                best_id = n.id
        if best_id and best_score >= 1:
            return best_id
        if last_review_id and last_review_id != current_id:
            return last_review_id
        return nodes[0].id

    @staticmethod
    def _assign_duration_weights(nodes: list[ProcessNode]) -> None:
        has_explicit = any(n.estimated_duration_min is not None for n in nodes)
        if has_explicit:
            defaults_min = {
                NodeType.START: 1.0,
                NodeType.SYSTEM: 2.0,
                NodeType.DECISION: 5.0,
                NodeType.TASK: 30.0,
                NodeType.SUBPROCESS: 60.0,
                NodeType.WAIT: 120.0,
                NodeType.PARALLEL: 0.5,
                NodeType.END_SUCCESS: 0.5,
                NodeType.END_REJECT: 0.5,
            }
            for n in nodes:
                n.duration_weight = max(0.1, n.estimated_duration_min if n.estimated_duration_min is not None else defaults_min[n.node_type])
        else:
            defaults_pts = {
                NodeType.START: 1.0,
                NodeType.SYSTEM: 1.0,
                NodeType.DECISION: 1.5,
                NodeType.TASK: 2.5,
                NodeType.SUBPROCESS: 4.0,
                NodeType.WAIT: 3.5,
                NodeType.PARALLEL: 0.5,
                NodeType.END_SUCCESS: 0.5,
                NodeType.END_REJECT: 0.5,
            }
            for n in nodes:
                n.duration_weight = defaults_pts[n.node_type]

    @staticmethod
    def _infer_title(text: str, lang: str) -> str:
        first = re.split(r"[.\n;]", text.strip())[0]
        first = _strip_duration_tokens(first)
        words = first.split()[:7]
        candidate = " ".join(words)
        if len(candidate) < 6:
            return "Business Process Workflow" if lang == "en" else "Arquitectura de Proceso"
        return sanitize_label_text(candidate[0].upper() + candidate[1:], max_len=64)
