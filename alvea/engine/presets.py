"""Escenarios corporativos predefinidos de ALVEA (analizados dinámicamente con NetworkX)."""

from __future__ import annotations

from dataclasses import dataclass

from alvea.models import (
    ActorKind,
    ActorLane,
    Direction,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
)


@dataclass(frozen=True, slots=True)
class PresetScenario:
    id: str
    title: str
    domain: str
    text: str
    graph: ProcessGraph


PRESET_SCENARIOS: dict[str, PresetScenario] = {
    "credito": PresetScenario(
        id="credito",
        title="Crédito de Consumo Móvil",
        domain="Banca Digital",
        text=(
            "Un cliente solicita un crédito de consumo en la app móvil. El sistema valida automáticamente "
            "el score crediticio en buró. Si el score es menor a 600, la app rechaza el crédito de forma "
            "automática y notifica al cliente. Si es mayor o igual a 600, el caso pasa a la bandeja del "
            "Analista de Riesgos, quien revisa manualmente los ingresos. Si el analista aprueba, pasa al "
            "área legal para redactar el contrato. El cliente firma digitalmente el contrato y el sistema "
            "finaliza el desembolso."
        ),
        graph=ProcessGraph(
            title="Crédito de Consumo Móvil",
            objective="Evaluar, aprobar y desembolsar créditos de consumo desde canal móvil.",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="CLI", name="Cliente", kind=ActorKind.HUMAN, order=0),
                ActorLane(id="SYS", name="Sistema / App Móvil", kind=ActorKind.SYSTEM, order=1),
                ActorLane(id="RIE", name="Analista de Riesgos", kind=ActorKind.DEPARTMENT, order=2),
                ActorLane(id="LEG", name="Área Legal", kind=ActorKind.DEPARTMENT, order=3),
            ],
            nodes=[
                ProcessNode(id="C1", label="Inicio: Solicita crédito en App Móvil", node_type=NodeType.START, lane_id="CLI", is_automated=True, duration_weight=1.0),
                ProcessNode(id="C2", label="Recibe notificación de rechazo", node_type=NodeType.TASK, lane_id="CLI", is_automated=True, duration_weight=0.8),
                ProcessNode(id="C3", label="Firma digitalmente el contrato", node_type=NodeType.TASK, lane_id="CLI", is_automated=True, duration_weight=1.2),
                ProcessNode(id="C_END_REC", label="Fin: Solicitud rechazada", node_type=NodeType.END_REJECT, lane_id="CLI", is_automated=True, duration_weight=0.5),
                ProcessNode(id="C_END_EXITO", label="Fin: Crédito desembolsado exitosamente", node_type=NodeType.END_SUCCESS, lane_id="CLI", is_automated=True, duration_weight=0.5),
                ProcessNode(id="S1", label="Consulta automática de score en buró", node_type=NodeType.TASK, lane_id="SYS", is_automated=True, duration_weight=1.0),
                ProcessNode(id="D1", label="¿Score >= 600?", node_type=NodeType.DECISION, lane_id="SYS", is_automated=True, duration_weight=1.0),
                ProcessNode(id="S2", label="Rechaza crédito automáticamente", node_type=NodeType.TASK, lane_id="SYS", is_automated=True, duration_weight=0.8),
                ProcessNode(id="S3", label="Ejecuta desembolso final", node_type=NodeType.TASK, lane_id="SYS", is_automated=True, duration_weight=1.0),
                ProcessNode(id="R1", label="Revisión manual de ingresos", node_type=NodeType.TASK, lane_id="RIE", is_automated=False, duration_weight=3.0, risk_level="high"),
                ProcessNode(id="D2", label="¿Ingresos aprobados?", node_type=NodeType.DECISION, lane_id="RIE", is_automated=False, duration_weight=1.5),
                ProcessNode(id="L1", label="Redacción de contrato de crédito", node_type=NodeType.TASK, lane_id="LEG", is_automated=False, duration_weight=2.5),
            ],
            edges=[
                ProcessEdge(source="C1", target="S1"),
                ProcessEdge(source="S1", target="D1"),
                ProcessEdge(source="D1", target="S2", label="Score < 600", is_conditional=True),
                ProcessEdge(source="D1", target="R1", label="Score >= 600", is_conditional=True),
                ProcessEdge(source="S2", target="C2"),
                ProcessEdge(source="C2", target="C_END_REC"),
                ProcessEdge(source="R1", target="D2"),
                ProcessEdge(source="D2", target="S2", label="Rechazado", is_conditional=True),
                ProcessEdge(source="D2", target="L1", label="Aprobado", is_conditional=True),
                ProcessEdge(source="L1", target="C3"),
                ProcessEdge(source="C3", target="S3"),
                ProcessEdge(source="S3", target="C_END_EXITO"),
            ],
        ),
    ),
    "compras": PresetScenario(
        id="compras",
        title="Licitación y Compras Estratégicas",
        domain="Procurement",
        text=(
            "Un empleado del área solicitante genera una orden de compra en el ERP. El jefe de área revisa "
            "el presupuesto. Si el monto excede los $10,000 USD, se requiere la aprobación del Gerente de "
            "Finanzas y tres cotizaciones del Departamento de Compras. Si el Gerente rechaza, se devuelve al "
            "empleado para corregir especificaciones. Si Finanzas aprueba, Compras emite la orden oficial al "
            "Proveedor. El Proveedor entrega los bienes en Almacén, Almacén confirma recepción y Contabilidad "
            "programa el pago."
        ),
        graph=ProcessGraph(
            title="Licitación y Compras Estratégicas",
            objective="Controlar compras corporativas con umbral de autorización y bucle de corrección.",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="SOL", name="Área Solicitante", kind=ActorKind.DEPARTMENT, order=0),
                ActorLane(id="JEF", name="Jefatura & Finanzas", kind=ActorKind.HUMAN, order=1),
                ActorLane(id="COM", name="Departamento de Compras", kind=ActorKind.DEPARTMENT, order=2),
                ActorLane(id="PROV", name="Proveedor", kind=ActorKind.EXTERNAL, order=3),
                ActorLane(id="ALM", name="Almacén & Contabilidad", kind=ActorKind.DEPARTMENT, order=4),
            ],
            nodes=[
                ProcessNode(id="S_INI", label="Inicio: Registro de OC en ERP", node_type=NodeType.START, lane_id="SOL", is_automated=True, duration_weight=1.0),
                ProcessNode(id="S_CORR", label="Corregir especificaciones de OC", node_type=NodeType.TASK, lane_id="SOL", is_automated=False, duration_weight=2.5, risk_level="medium"),
                ProcessNode(id="J1", label="Revisión de presupuesto", node_type=NodeType.TASK, lane_id="JEF", is_automated=False, duration_weight=2.0),
                ProcessNode(id="D_MONTO", label="¿Monto > $10k USD?", node_type=NodeType.DECISION, lane_id="JEF", is_automated=True, duration_weight=1.0),
                ProcessNode(id="J2", label="Aprobación de Gerencia Finanzas", node_type=NodeType.TASK, lane_id="JEF", is_automated=False, duration_weight=3.0, risk_level="high"),
                ProcessNode(id="D_GER", label="¿Aprobado por Finanzas?", node_type=NodeType.DECISION, lane_id="JEF", is_automated=False, duration_weight=1.5),
                ProcessNode(id="C_COT", label="Obtención de 3 cotizaciones", node_type=NodeType.TASK, lane_id="COM", is_automated=False, duration_weight=3.5),
                ProcessNode(id="C_OC", label="Emisión de OC oficial", node_type=NodeType.TASK, lane_id="COM", is_automated=True, duration_weight=1.0),
                ProcessNode(id="P1", label="Despacho y entrega de bienes", node_type=NodeType.TASK, lane_id="PROV", is_automated=False, duration_weight=3.0),
                ProcessNode(id="A1", label="Confirmación de recepción en bodega", node_type=NodeType.TASK, lane_id="ALM", is_automated=False, duration_weight=1.5),
                ProcessNode(id="A2", label="Programación de pago", node_type=NodeType.TASK, lane_id="ALM", is_automated=True, duration_weight=1.0),
                ProcessNode(id="S_FIN", label="Fin: Pago liquidado a proveedor", node_type=NodeType.END_SUCCESS, lane_id="ALM", is_automated=True, duration_weight=0.5),
            ],
            edges=[
                ProcessEdge(source="S_INI", target="J1"),
                ProcessEdge(source="J1", target="D_MONTO"),
                ProcessEdge(source="D_MONTO", target="C_OC", label="No", is_conditional=True),
                ProcessEdge(source="D_MONTO", target="C_COT", label="Sí", is_conditional=True),
                ProcessEdge(source="C_COT", target="J2"),
                ProcessEdge(source="J2", target="D_GER"),
                ProcessEdge(source="D_GER", target="S_CORR", label="Rechazado", is_conditional=True),
                ProcessEdge(source="S_CORR", target="J1", label="Reenvío", is_loop=True),
                ProcessEdge(source="D_GER", target="C_OC", label="Aprobado", is_conditional=True),
                ProcessEdge(source="C_OC", target="P1"),
                ProcessEdge(source="P1", target="A1"),
                ProcessEdge(source="A1", target="A2"),
                ProcessEdge(source="A2", target="S_FIN"),
            ],
        ),
    ),
    "incidentes": PresetScenario(
        id="incidentes",
        title="Gestión de Incidentes Críticos IT",
        domain="DevOps / ITIL",
        text=(
            "Un usuario reporta una caída de servicio en el portal de soporte. La Mesa de Ayuda (Nivel 1) "
            "categoriza el incidente y evalúa el impacto. Si es una falla menor recurrente, Nivel 1 aplica "
            "una solución conocida de la base de conocimiento y cierra el ticket. Si es un incidente crítico "
            "de alta severidad (P1), escala al Equipo DevOps / SRE. DevOps diagnostica el fallo en producción; "
            "si requiere parche urgente, despliega un hotfix, el área de QA valida el servicio y la Mesa de "
            "Ayuda notifica la restitución del servicio al usuario final."
        ),
        graph=ProcessGraph(
            title="Gestión de Incidentes Críticos IT (ITIL / SRE)",
            objective="Aislar incidentes P1 críticos y garantizar restitución validada por QA.",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="USR", name="Usuario Final", kind=ActorKind.HUMAN, order=0),
                ActorLane(id="N1", name="Mesa de Ayuda (Nivel 1)", kind=ActorKind.DEPARTMENT, order=1),
                ActorLane(id="SRE", name="Equipo DevOps / SRE", kind=ActorKind.DEPARTMENT, order=2),
                ActorLane(id="QA", name="Aseguramiento de Calidad (QA)", kind=ActorKind.DEPARTMENT, order=3),
            ],
            nodes=[
                ProcessNode(id="U1", label="Inicio: Reporte de caída de servicio", node_type=NodeType.START, lane_id="USR", is_automated=True, duration_weight=1.0),
                ProcessNode(id="U2", label="Confirmación de servicio restablecido", node_type=NodeType.TASK, lane_id="USR", is_automated=False, duration_weight=1.0),
                ProcessNode(id="U_FIN", label="Fin: Incidente resuelto", node_type=NodeType.END_SUCCESS, lane_id="USR", is_automated=True, duration_weight=0.5),
                ProcessNode(id="H1", label="Categorización y evaluación de impacto", node_type=NodeType.TASK, lane_id="N1", is_automated=False, duration_weight=1.8),
                ProcessNode(id="D_SEV", label="¿Severidad P1 Crítica?", node_type=NodeType.DECISION, lane_id="N1", is_automated=False, duration_weight=1.2),
                ProcessNode(id="H2", label="Aplica solución de KB estándar", node_type=NodeType.TASK, lane_id="N1", is_automated=True, duration_weight=1.0),
                ProcessNode(id="H3", label="Notificación de restitución", node_type=NodeType.TASK, lane_id="N1", is_automated=True, duration_weight=0.8),
                ProcessNode(id="S1", label="Diagnóstico de causa raíz en prod", node_type=NodeType.TASK, lane_id="SRE", is_automated=False, duration_weight=3.0, risk_level="high"),
                ProcessNode(id="D_FIX", label="¿Requiere Hotfix de código?", node_type=NodeType.DECISION, lane_id="SRE", is_automated=False, duration_weight=1.5),
                ProcessNode(id="S2", label="Reinicio de servicios / Failover", node_type=NodeType.TASK, lane_id="SRE", is_automated=True, duration_weight=1.2),
                ProcessNode(id="S3", label="Despliegue de parche urgente", node_type=NodeType.TASK, lane_id="SRE", is_automated=True, duration_weight=2.2),
                ProcessNode(id="Q1", label="Smoke tests en ambiente productivo", node_type=NodeType.TASK, lane_id="QA", is_automated=True, duration_weight=1.5),
            ],
            edges=[
                ProcessEdge(source="U1", target="H1"),
                ProcessEdge(source="H1", target="D_SEV"),
                ProcessEdge(source="D_SEV", target="H2", label="No (Menor)", is_conditional=True),
                ProcessEdge(source="H2", target="H3"),
                ProcessEdge(source="D_SEV", target="S1", label="Sí (Crítico)", is_conditional=True),
                ProcessEdge(source="S1", target="D_FIX"),
                ProcessEdge(source="D_FIX", target="S2", label="No", is_conditional=True),
                ProcessEdge(source="D_FIX", target="S3", label="Sí", is_conditional=True),
                ProcessEdge(source="S2", target="Q1"),
                ProcessEdge(source="S3", target="Q1"),
                ProcessEdge(source="Q1", target="H3"),
                ProcessEdge(source="H3", target="U2"),
                ProcessEdge(source="U2", target="U_FIN"),
            ],
        ),
    ),
    "onboarding": PresetScenario(
        id="onboarding",
        title="Selección y Contratación de Personal",
        domain="Recursos Humanos",
        text=(
            "Un postulante envía su CV a través del portal de empleo. El reclutador de RRHH realiza un "
            "primer filtro curricular y una entrevista telefónica. Si no cumple el perfil mínimo, RRHH envía "
            "correo de agradecimiento y archiva la postulación. Si cumple, pasa a la evaluación técnica con "
            "el Líder de Equipo. Si el líder aprueba la prueba técnica, el postulante se reúne con la Gerencia "
            "para definir la oferta económica. El candidato firma la propuesta laboral y el equipo de "
            "Operaciones de TI aprovisiona su laptop y accesos."
        ),
        graph=ProcessGraph(
            title="Selección y Contratación de Personal (RRHH)",
            objective="Orquestar reclutamiento, evaluación técnica, oferta y aprovisionamiento TI.",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="CAN", name="Candidato", kind=ActorKind.HUMAN, order=0),
                ActorLane(id="RRHH", name="Atracción de Talento (RRHH)", kind=ActorKind.DEPARTMENT, order=1),
                ActorLane(id="TEC", name="Líder Técnico", kind=ActorKind.HUMAN, order=2),
                ActorLane(id="GER", name="Gerencia", kind=ActorKind.HUMAN, order=3),
                ActorLane(id="TI", name="Operaciones de TI", kind=ActorKind.DEPARTMENT, order=4),
            ],
            nodes=[
                ProcessNode(id="C_POST", label="Inicio: Postulación y envío de CV", node_type=NodeType.START, lane_id="CAN", is_automated=True, duration_weight=1.0),
                ProcessNode(id="C_FIRMA", label="Firma de oferta laboral", node_type=NodeType.TASK, lane_id="CAN", is_automated=True, duration_weight=1.2),
                ProcessNode(id="C_DESC", label="Fin: Postulación archivada", node_type=NodeType.END_REJECT, lane_id="CAN", is_automated=True, duration_weight=0.5),
                ProcessNode(id="C_EXI", label="Fin: Onboarding completo", node_type=NodeType.END_SUCCESS, lane_id="CAN", is_automated=True, duration_weight=0.5),
                ProcessNode(id="R_FILTRO", label="Filtro curricular y llamada inicial", node_type=NodeType.TASK, lane_id="RRHH", is_automated=False, duration_weight=2.0),
                ProcessNode(id="D_FIL", label="¿Cumple perfil?", node_type=NodeType.DECISION, lane_id="RRHH", is_automated=False, duration_weight=1.2),
                ProcessNode(id="R_NOTIF", label="Envío de notificación de descarte", node_type=NodeType.TASK, lane_id="RRHH", is_automated=True, duration_weight=0.8),
                ProcessNode(id="T_EVAL", label="Prueba técnica y entrevista", node_type=NodeType.TASK, lane_id="TEC", is_automated=False, duration_weight=3.0, risk_level="high"),
                ProcessNode(id="D_TEC", label="¿Aprobado técnicamente?", node_type=NodeType.DECISION, lane_id="TEC", is_automated=False, duration_weight=1.2),
                ProcessNode(id="G_OFERTA", label="Negociación y oferta económica", node_type=NodeType.TASK, lane_id="GER", is_automated=False, duration_weight=2.5),
                ProcessNode(id="I_PROV", label="Aprovisionamiento de laptop y accesos", node_type=NodeType.TASK, lane_id="TI", is_automated=True, duration_weight=1.5),
            ],
            edges=[
                ProcessEdge(source="C_POST", target="R_FILTRO"),
                ProcessEdge(source="R_FILTRO", target="D_FIL"),
                ProcessEdge(source="D_FIL", target="R_NOTIF", label="No", is_conditional=True),
                ProcessEdge(source="R_NOTIF", target="C_DESC"),
                ProcessEdge(source="D_FIL", target="T_EVAL", label="Sí", is_conditional=True),
                ProcessEdge(source="T_EVAL", target="D_TEC"),
                ProcessEdge(source="D_TEC", target="R_NOTIF", label="No", is_conditional=True),
                ProcessEdge(source="D_TEC", target="G_OFERTA", label="Sí", is_conditional=True),
                ProcessEdge(source="G_OFERTA", target="C_FIRMA"),
                ProcessEdge(source="C_FIRMA", target="I_PROV"),
                ProcessEdge(source="I_PROV", target="C_EXI"),
            ],
        ),
    ),
    "viaticos": PresetScenario(
        id="viaticos",
        title="Rendición de Viáticos y Reembolso",
        domain="Finanzas",
        text=(
            "Un colaborador registra su informe de gastos de viaje y adjunta facturas en la app corporativa. "
            "El Supervisor directo valida la pertinencia de los gastos según la política de viajes. Si hay "
            "inconsistencias, rechaza y el colaborador debe subsanar los comprobantes. Si el supervisor "
            "aprueba, pasa al área de Auditoría Contable para validar validez fiscal de las facturas. "
            "Auditoría aprueba y Tesorería realiza la transferencia bancaria a la cuenta del colaborador, "
            "emitiendo el comprobante de liquidación."
        ),
        graph=ProcessGraph(
            title="Rendición de Viáticos y Reembolso (Finanzas)",
            objective="Validar gastos de viaje bajo doble control operativo y tributario.",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="COL", name="Colaborador", kind=ActorKind.HUMAN, order=0),
                ActorLane(id="SUP", name="Supervisor Directo", kind=ActorKind.HUMAN, order=1),
                ActorLane(id="AUD", name="Auditoría Contable", kind=ActorKind.DEPARTMENT, order=2),
                ActorLane(id="TES", name="Tesorería", kind=ActorKind.DEPARTMENT, order=3),
            ],
            nodes=[
                ProcessNode(id="CO1", label="Inicio: Registro de gastos y facturas", node_type=NodeType.START, lane_id="COL", is_automated=True, duration_weight=1.0),
                ProcessNode(id="CO2", label="Subsanar comprobantes observados", node_type=NodeType.TASK, lane_id="COL", is_automated=False, duration_weight=2.2, risk_level="medium"),
                ProcessNode(id="CO_FIN", label="Fin: Reembolso recibido exitosamente", node_type=NodeType.END_SUCCESS, lane_id="COL", is_automated=True, duration_weight=0.5),
                ProcessNode(id="S_REV", label="Validación según política de viajes", node_type=NodeType.TASK, lane_id="SUP", is_automated=False, duration_weight=2.0),
                ProcessNode(id="D_SUP", label="¿Gastos pertinentes?", node_type=NodeType.DECISION, lane_id="SUP", is_automated=False, duration_weight=1.2),
                ProcessNode(id="A_REV", label="Verificación fiscal ante tributación", node_type=NodeType.TASK, lane_id="AUD", is_automated=False, duration_weight=2.5, risk_level="high"),
                ProcessNode(id="D_AUD", label="¿Comprobantes válidos?", node_type=NodeType.DECISION, lane_id="AUD", is_automated=False, duration_weight=1.2),
                ProcessNode(id="T_TRANSF", label="Transferencia bancaria y liquidación", node_type=NodeType.TASK, lane_id="TES", is_automated=True, duration_weight=1.0),
            ],
            edges=[
                ProcessEdge(source="CO1", target="S_REV"),
                ProcessEdge(source="S_REV", target="D_SUP"),
                ProcessEdge(source="D_SUP", target="CO2", label="Observado", is_conditional=True),
                ProcessEdge(source="CO2", target="S_REV", label="Reenvío", is_loop=True),
                ProcessEdge(source="D_SUP", target="A_REV", label="Aprobado", is_conditional=True),
                ProcessEdge(source="A_REV", target="D_AUD"),
                ProcessEdge(source="D_AUD", target="CO2", label="Rechazado", is_conditional=True),
                ProcessEdge(source="D_AUD", target="T_TRANSF", label="Conforme", is_conditional=True),
                ProcessEdge(source="T_TRANSF", target="CO_FIN"),
            ],
        ),
    ),
}


def match_preset_by_text(text: str) -> PresetScenario | None:
    cleaned = (text or "").strip()
    for preset in PRESET_SCENARIOS.values():
        if cleaned == preset.text.strip():
            return preset
    return None
