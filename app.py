"""3-Tomadas Table Filler – Streamlit application.

Parses free-text medication lists and fills a medication schedule table
with columns for Morning / Lunch / Night based on posology codes, timing,
and frequency information extracted from the input.
"""

import os
from io import BytesIO
from datetime import date

import streamlit as st

from parser import parse_medication_list
from table_filler import fill_table, get_time_slots, _build_med_display

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tabela 3 Tomadas",
    page_icon="🕐",
    layout="wide",
)

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "Tabela de medicamentos_3 tomadas.docx",
)

# ── Session state ────────────────────────────────────────────────────────
if "parsed_meds" not in st.session_state:
    st.session_state.parsed_meds = None
if "stage" not in st.session_state:
    st.session_state.stage = "input"

# ── Header ───────────────────────────────────────────────────────────────
st.title("Tabela de Medicamentos – 3 Tomadas")
st.caption("Cole a lista de medicamentos e gere a tabela preenchida com horários.")

# ── Stage: Input ─────────────────────────────────────────────────────────
if st.session_state.stage == "input":
    patient_name = st.text_input("Nome do paciente (opcional)")
    st.session_state["patient_name"] = patient_name

    med_text = st.text_area(
        "Lista de medicamentos",
        height=300,
        placeholder=(
            "Cole aqui a lista de medicamentos do prontuário.\n\n"
            "Exemplos:\n"
            "- Losartana 50mg 1-0-1\n"
            "- Omeprazol 20mg cedo\n"
            "- Metformina 850mg 12/12h\n"
            "- Sinvastatina 20mg à noite\n"
            "- Amoxicilina 500mg 8/8h"
        ),
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("Processar", type="primary", use_container_width=True):
            if med_text.strip():
                parsed = parse_medication_list(med_text)
                # Filter out suspended / TARV
                active = [
                    m for m in parsed
                    if m.suspension.value == "active" and not m.is_tarv
                ]
                if active:
                    st.session_state.parsed_meds = active
                    st.session_state.stage = "review"
                    st.rerun()
                else:
                    st.warning("Nenhum medicamento ativo encontrado.")
            else:
                st.warning("Cole a lista de medicamentos primeiro.")

# ── Stage: Review ────────────────────────────────────────────────────────
elif st.session_state.stage == "review":
    meds = st.session_state.parsed_meds

    st.subheader("Revisão dos medicamentos")
    st.info(
        f"**{len(meds)}** medicamentos encontrados. "
        "Revise a distribuição nos horários e ajuste se necessário."
    )

    # Build editable table data
    if "edited_slots" not in st.session_state:
        st.session_state.edited_slots = {}
        for i, med in enumerate(meds):
            morning, lunch, night = get_time_slots(med)
            st.session_state.edited_slots[i] = {
                "name": _build_med_display(med),
                "morning": morning,
                "lunch": lunch,
                "night": night,
            }

    # Display as editable form
    header_cols = st.columns([3, 2, 2, 2])
    header_cols[0].markdown("**Medicamento**")
    header_cols[1].markdown("**☀️ Manhã**")
    header_cols[2].markdown("**🍽️ Almoço**")
    header_cols[3].markdown("**🌙 Noite**")

    for i in range(len(meds)):
        slot = st.session_state.edited_slots[i]
        cols = st.columns([3, 2, 2, 2])

        with cols[0]:
            new_name = st.text_input(
                "med", value=slot["name"], key=f"name_{i}",
                label_visibility="collapsed",
            )
            st.session_state.edited_slots[i]["name"] = new_name

        with cols[1]:
            new_m = st.text_input(
                "manhã", value=slot["morning"], key=f"morning_{i}",
                label_visibility="collapsed",
            )
            st.session_state.edited_slots[i]["morning"] = new_m

        with cols[2]:
            new_l = st.text_input(
                "almoço", value=slot["lunch"], key=f"lunch_{i}",
                label_visibility="collapsed",
            )
            st.session_state.edited_slots[i]["lunch"] = new_l

        with cols[3]:
            new_n = st.text_input(
                "noite", value=slot["night"], key=f"night_{i}",
                label_visibility="collapsed",
            )
            st.session_state.edited_slots[i]["night"] = new_n

    st.divider()

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("Voltar", use_container_width=True):
            st.session_state.stage = "input"
            st.session_state.parsed_meds = None
            if "edited_slots" in st.session_state:
                del st.session_state.edited_slots
            st.rerun()

    with col2:
        if st.button("Gerar Tabela", type="primary", use_container_width=True):
            st.session_state.stage = "generate"
            st.rerun()

# ── Stage: Generate ──────────────────────────────────────────────────────
elif st.session_state.stage == "generate":
    meds = st.session_state.parsed_meds
    slots = st.session_state.edited_slots
    patient_name = st.session_state.get("patient_name", "")

    # Override parsed meds with edited values for the filler
    # We'll pass the edited slots directly to a custom fill function
    from docx import Document
    from table_filler import _set_cell_text, _clone_row
    import copy

    doc = Document(TEMPLATE_PATH)
    table = doc.tables[0]

    # Set patient name in merged header row
    if patient_name:
        _set_cell_text(table.rows[0].cells[0], patient_name, font_size=20)

    first_data_row = 2
    existing_data_rows = len(table.rows) - first_data_row

    for i in range(len(meds)):
        slot = slots[i]
        if i < existing_data_rows:
            row = table.rows[first_data_row + i]
        else:
            _clone_row(table, first_data_row + existing_data_rows - 1)
            row = table.rows[-1]

        _set_cell_text(row.cells[0], slot["name"])
        _set_cell_text(row.cells[1], slot["morning"])
        _set_cell_text(row.cells[2], slot["lunch"])
        _set_cell_text(row.cells[3], slot["night"])

    # Remove unused empty data rows (rows beyond the medications)
    total_needed = len(meds)
    total_data_available = len(table.rows) - first_data_row
    if total_needed < total_data_available:
        tbl_xml = table._tbl
        rows_to_remove = []
        for j in range(first_data_row + total_needed, len(table.rows)):
            rows_to_remove.append(tbl_xml.tr_lst[j])
        for tr in rows_to_remove:
            tbl_xml.remove(tr)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    st.subheader("Tabela gerada!")
    st.success(f"Tabela com {len(meds)} medicamentos gerada com sucesso.")

    filename = "Tabela_3_tomadas"
    if patient_name:
        safe_name = patient_name.replace(" ", "_")[:30]
        filename = f"Tabela_3_tomadas_{safe_name}"
    filename += f"_{date.today().strftime('%d-%m-%Y')}.docx"

    st.download_button(
        label="Baixar tabela (.docx)",
        data=buf,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
    )

    if st.button("Nova tabela"):
        st.session_state.stage = "input"
        st.session_state.parsed_meds = None
        if "edited_slots" in st.session_state:
            del st.session_state.edited_slots
        st.rerun()
