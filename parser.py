import re
from models import ParsedMedication, SuspensionStatus


# ---------------------------------------------------------------------------
# TARV / ARV detection
# ---------------------------------------------------------------------------
_TARV_RE = re.compile(r"^\s*(?:TARV\s*:|2\s+EM\s+1\s*[-–])", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Suspension detection  (order matters – check explicit first)
# ---------------------------------------------------------------------------
_SUSPENSION_PATTERNS: list[tuple[re.Pattern, SuspensionStatus, str | None]] = [
    (re.compile(r"suspendeu\s+(?:por\s+)?(.+?)$", re.IGNORECASE),
     SuspensionStatus.SUSPENDED, None),
    (re.compile(r"fez\s+suspens[aã]o", re.IGNORECASE),
     SuspensionStatus.SUSPENDED, "fez suspensão"),
    (re.compile(r"cessou\s+uso", re.IGNORECASE),
     SuspensionStatus.SUSPENDED, "cessou uso"),
    (re.compile(r"[-–—]\s*SUSPENSO\s*\?", re.IGNORECASE),
     SuspensionStatus.POSSIBLY_SUSPENDED, "possivelmente suspenso"),
    (re.compile(r"[-–—]\s*SUSPENSO", re.IGNORECASE),
     SuspensionStatus.SUSPENDED, "suspenso"),
    (re.compile(r"SUSPENSO\s*\??", re.IGNORECASE),
     SuspensionStatus.POSSIBLY_SUSPENDED, "possivelmente suspenso"),
]

# ---------------------------------------------------------------------------
# Component extraction patterns
# ---------------------------------------------------------------------------

# Dose/timing combo: 2MG/NOITE, 500MG/DIA (extract dose and timing separately)
_DOSE_TIMING_RE = re.compile(
    r"(\d+(?:[,\.]\d+)?)\s*(mg|mcg|g|ui)\s*/\s*(noite|dia|manh[aã])",
    re.IGNORECASE,
)

# Dose: 30mg, 6,25mg, 500mg, 667mg/ml, 300 mg, 0,25 mg
_DOSE_RE = re.compile(
    r"(\d+(?:[,\.]\d+)?)\s*"
    r"(mg|mcg|g|ui|%|mg/ml|mg/dia)"
    r"(?:/(?:dia|noite|ml))?",
    re.IGNORECASE,
)

# Posology code: 1-0-0, 0-0-1, 1-0-1
_POSOLOGY_RE = re.compile(r"\b(\d)-(\d)-(\d)\b")

# Extended posology in parentheses: (0cp - 1cp - 0cp), (8 UI - 0 UI - 4 UI)
_POSOLOGY_EXT_RE = re.compile(
    r"\(\s*(\d+)\s*(?:cp|comp|UI)?\s*-\s*(\d+)\s*(?:cp|comp|UI)?\s*-\s*(\d+)\s*(?:cp|comp|UI)?\s*\)",
    re.IGNORECASE,
)

# Frequency: 12/12h, 8/8h, de 12 em 12 horas, 3 vezes ao dia, 2x/dia
_FREQ_PATTERNS = [
    re.compile(r"(?:de\s+)?(\d+)\s*/\s*(\d+)\s*h(?:oras)?", re.IGNORECASE),
    re.compile(r"de\s+(\d+)\s+em\s+(\d+)\s+horas?", re.IGNORECASE),
    re.compile(r",?\s*(\d+)\s*(?:vezes|x)\s*(?:ao|por|no)\s*dia", re.IGNORECASE),
    re.compile(r",?\s*(\d+)\s*(?:vezes|x)\s*(?:na|por)\s*semana", re.IGNORECASE),
    re.compile(r",?\s*(\d+)\s*(?:vezes|x)\s*(?:ao|por|no)\s*m[eê]s", re.IGNORECASE),
    re.compile(r"\bpor\s+(?:dia|semana|m[eê]s)\b", re.IGNORECASE),
    re.compile(r"\bao\s+dia\b", re.IGNORECASE),
]

# Combination dose: 100/25mg, 450/50mg, 100mg/25mg
_COMBO_DOSE_RE = re.compile(
    r"(\d+(?:[,\.]\d+)?)\s*/\s*(\d+(?:[,\.]\d+)?)\s*(mg|mcg|g)",
    re.IGNORECASE,
)

# Concentration in parentheses: (200UI/gota), (250mg/5ml), (75mg/ml), (7,5 mg/ml)
_CONC_PAREN_RE = re.compile(
    r"\(\s*(\d+(?:[,\.]\d+)?)\s*(mg|mcg|g|ui|UI)\s*/\s*"
    r"(?:\d+\s*)?(?:ml|gota|dose|comp)\s*\)",
    re.IGNORECASE,
)

# Schedule in parentheses (non-condition): (nos domingos e nas quintas-feiras)
_SCHEDULE_PAREN_RE = re.compile(
    r"\(([^)]*(?:domingo|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|dias?\s+(?:sim|n[aã]o))[^)]*)\)",
    re.IGNORECASE,
)

# Quantity per dose: 1cp, 02 comprimidos, 10 ml, 4 frascos, 1 jato, meio cp
_QTY_RE = re.compile(
    r"(?:(\d+|meio)\s*(cp|comp(?:rimido)?s?|c[aá]ps?(?:ula)?s?|ml|gota(?:s)?|frasco(?:s)?|jato(?:s)?))",
    re.IGNORECASE,
)

# "meio cp" specifically — needs separate handling since "meio" is not \d+
_MEIO_QTY_RE = re.compile(
    r"\bmeio\s+(cp|comp(?:rimido)?|c[aá]p(?:sula)?)\b",
    re.IGNORECASE,
)

# Single timing token (used both standalone and in compound)
_SINGLE_TIMING = (
    r"(?:ced[oo]|(?:pela\s+|de?\s+)?manh[aã]|(?:[àa]\s+)?(?:noite|tarde)"
    r"|(?:ap[oó]s\s+(?:o\s+)?|antes\s+(?:do?\s+)?|no\s+|ao?\s+)?(?:almo[cç]o|jantar))"
)

# Qty/dose token optionally before a timing: "50mg", "2ml", "2cp"
_QTY_DOSE_TOKEN = (
    r"(?:\d+(?:[,\.]\d+)?\s*(?:mg|mcg|g|ui|cp|comp|ml|gotas?|c[aá]ps?|jatos?)\s+)"
)

# Compound timing: "cedo e à tarde", "cedo e 2cp à noite", "cedo e 50mg após o almoço"
_COMPOUND_TIMING_RE = re.compile(
    rf"\b{_SINGLE_TIMING}\s+e\s+{_QTY_DOSE_TOKEN}?{_SINGLE_TIMING}\b",
    re.IGNORECASE,
)

# Simple timing: cedo, manhã, noite, tarde, à noite, pela manhã, após almoço
_TIMING_RE = re.compile(
    rf"\b{_SINGLE_TIMING}\b",
    re.IGNORECASE,
)

# Fasting: "em jejum" — extracted separately as it's a condition, not a time of day
_JEJUM_RE = re.compile(r"\bem\s+jejum\b", re.IGNORECASE)

# Conditional (in parentheses): (se dor em MMII)
_CONDITION_PAREN_RE = re.compile(
    r"\(([^)]*(?:se\s+|quando\s+|sos|prn|necessidade)[^)]*)\)",
    re.IGNORECASE,
)

# Extra-instruction parentheses: (+ 1cp nos momentos de agitação psicomotora)
_EXTRA_INSTR_PAREN_RE = re.compile(
    r"\(\s*\+\s*([^)]+)\)",
    re.IGNORECASE,
)

# Condition outside parentheses: "se crises de ansiedade", "se dor intensa"
_CONDITION_SUFFIX_RE = re.compile(
    r"\bse\s+[\w\sà-úÀ-Ú]+$",
    re.IGNORECASE,
)

# "conforme hábito intestinal", "conforme orientação médica"
_CONFORME_RE = re.compile(
    r",?\s*conforme\s+[\w\sà-úÀ-Ú]+$",
    re.IGNORECASE,
)

# Quantity in parentheses: (10 comprimidos)
_QTY_PAREN_RE = re.compile(
    r"\((\d+\s*(?:comp(?:rimido)?s?|c[aá]ps?(?:ula)?s?|cp|frasco(?:s)?))\)",
    re.IGNORECASE,
)

# Brand in parentheses: (Corus), (Rivotril)
_BRAND_PAREN_RE = re.compile(r"\(([A-Z][A-Za-zÀ-ú]+(?:\s+[A-Z][A-Za-zÀ-ú]+)*)\)")

# Infusion / date info after arrows: --> Di: 21/10/2024
_INFUSION_RE = re.compile(
    r"[-–>]+\s*(?:Di|[Úú]ltima?\s+infus[aã]o|data)\s*:?\s*[\d/.:]+.*$",
    re.IGNORECASE,
)

# Notes from the prescriber: "prescrito pelo psiquiatra", "relata ..."
_NOTES_TRAIL_RE = re.compile(
    r"[-–,]\s*(?:relata|sentiu|prescrito|paciente relata).*$",
    re.IGNORECASE,
)

# "contínuo" / "uso contínuo"
_CONTINUOUS_RE = re.compile(r"\b(?:uso\s+)?cont[ií]nuo\b", re.IGNORECASE)

# "em média Nx por semana" pattern
_MEDIA_RE = re.compile(
    r"[>-]\s*em\s+m[eé]dia.*$",
    re.IGNORECASE,
)

# IM / intramuscular route info: "IM mensal", "IM de 20/20 dias"
_IM_ROUTE_RE = re.compile(
    r"\bIM\s+(?:mensal|de\s+\d+/\d+\s*dias?|semanal|quinzenal)\b",
    re.IGNORECASE,
)


def parse_medication_line(line: str) -> ParsedMedication:
    """Parse a single medication line from a patient record."""
    raw = line.strip()
    # Strip leading bullet characters and BOM
    cleaned = re.sub(r"^\s*[\ufeff]?\s*[-*•]\s*", "", raw)
    cleaned = re.sub(r"^\s*\d+[.)]\s*", "", cleaned)

    result = ParsedMedication(raw_text=raw, medication_name="")

    # 1. TARV / ARV detection
    if _TARV_RE.match(cleaned):
        result.is_tarv = True
        result.medication_name = cleaned
        return result

    # 2. Suspension detection
    for pattern, status, default_reason in _SUSPENSION_PATTERNS:
        m = pattern.search(cleaned)
        if m:
            result.suspension = status
            if default_reason:
                result.suspension_reason = default_reason
            elif m.lastindex and m.lastindex >= 1:
                result.suspension_reason = m.group(1).strip()
            else:
                result.suspension_reason = m.group(0).strip()
            cleaned = pattern.sub("", cleaned).strip()
            break

    # 3. Infusion / date info
    m = _INFUSION_RE.search(cleaned)
    if m:
        result.extra_info = m.group(0).strip()
        cleaned = _INFUSION_RE.sub("", cleaned).strip()

    # 4. Trailing notes ("relata ...", "prescrito pelo ...")
    cleaned = _NOTES_TRAIL_RE.sub("", cleaned).strip()

    # 5. "em média" trailing info
    cleaned = _MEDIA_RE.sub("", cleaned).strip()

    # 5b. "em jejum" (fasting condition — independent of time-of-day timing)
    m = _JEJUM_RE.search(cleaned)
    if m:
        result.extra_info = (result.extra_info or "") + " em jejum"
        result.extra_info = result.extra_info.strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 5c. "conforme hábito intestinal" / "conforme orientação médica"
    m = _CONFORME_RE.search(cleaned)
    if m:
        result.condition = m.group(0).strip().strip(",").strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 5d. IM route info ("IM mensal", "IM de 20/20 dias")
    m = _IM_ROUTE_RE.search(cleaned)
    if m:
        result.extra_info = (result.extra_info or "") + " " + m.group(0).strip()
        result.extra_info = result.extra_info.strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 5e. Extra instruction parentheses: (+ 1cp nos momentos de agitação)
    m = _EXTRA_INSTR_PAREN_RE.search(cleaned)
    if m:
        result.extra_info = (result.extra_info or "") + " (+ " + m.group(1).strip() + ")"
        result.extra_info = result.extra_info.strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 6a. Quantity in parentheses: (10 comprimidos)
    m = _QTY_PAREN_RE.search(cleaned)
    if m:
        result.quantity_per_dose = m.group(1).strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 6a1. Concentration in parentheses: (200UI/gota), (250mg/5ml)
    #      Extract dose from it and remove the whole parenthetical
    m = _CONC_PAREN_RE.search(cleaned)
    if m:
        if not result.dose:
            result.dose = f"{m.group(1)}{m.group(2)}"
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 6a2. Schedule in parentheses: (nos domingos e nas quintas-feiras)
    m = _SCHEDULE_PAREN_RE.search(cleaned)
    if m:
        result.extra_info = (result.extra_info or "") + " " + m.group(1).strip()
        result.extra_info = result.extra_info.strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 6b. Condition in parentheses
    m = _CONDITION_PAREN_RE.search(cleaned)
    if m:
        result.condition = m.group(1).strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 7. Brand in parentheses (only if not a condition keyword)
    m = _BRAND_PAREN_RE.search(cleaned)
    if m:
        candidate = m.group(1)
        condition_words = {"se", "quando", "sos", "prn", "caso", "necessidade"}
        if not any(w in candidate.lower() for w in condition_words):
            result.brand_in_parens = candidate
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 7b. Posology in parentheses: (0-0-1), (0cp - 1cp - 0cp), (8 UI - 0 UI - 4 UI)
    #     Must run BEFORE orphan paren cleanup which would strip digit-only parens.
    m = _POSOLOGY_EXT_RE.search(cleaned)
    if m:
        result.posology_code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 7c. Clean up remaining orphaned parenthetical content
    #     E.g. (/) left from dose extraction of (250mg/5ml) where dose was grabbed
    cleaned = re.sub(r"\(\s*/?\s*\)", "", cleaned).strip()
    # Remove parentheses with only non-alpha content like (+) or (-)
    cleaned = re.sub(r"\(\s*[^a-zA-ZÀ-ú]*\s*\)", "", cleaned).strip()

    # 8. Simple posology code 1-0-0 (without parentheses) — only if not already set
    if not result.posology_code:
        m = _POSOLOGY_RE.search(cleaned)
        if m:
            result.posology_code = m.group(0)
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 9. Frequency (12/12h, de 8 em 8 horas, 3 vezes ao dia)
    for freq_re in _FREQ_PATTERNS:
        m = freq_re.search(cleaned)
        if m:
            result.frequency = m.group(0).strip().strip(",").strip()
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()
            break

    # 9b. Strip orphaned "até" left from "até 3 vezes ao dia" or "até de 8/8h"
    cleaned = re.sub(r"\bat[eé]\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\bat[eé]\s*,", ",", cleaned, flags=re.IGNORECASE).strip()

    # 10. "meio cp" quantity (before regular qty, since it lacks a digit prefix)
    if not result.quantity_per_dose:
        m = _MEIO_QTY_RE.search(cleaned)
        if m:
            result.quantity_per_dose = m.group(0).strip()
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 10b. Quantity per dose (1cp, 02 comprimidos, 1 jato) — extract before timing
    #      so that "cedo e 1cp à tarde" becomes "cedo e à tarde"
    if not result.quantity_per_dose:
        m = _QTY_RE.search(cleaned)
        if m:
            result.quantity_per_dose = m.group(0).strip()
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 11. Timing — try compound first ("cedo e à tarde", "cedo e 2cp à noite"), then simple
    m = _COMPOUND_TIMING_RE.search(cleaned)
    if not m:
        m = _TIMING_RE.search(cleaned)
    if m:
        result.timing = m.group(0).strip()
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 12a. Combination dose: 100/25mg, 450/50mg
    if not result.dose:
        m = _COMBO_DOSE_RE.search(cleaned)
        if m:
            result.dose = f"{m.group(1)}/{m.group(2)}{m.group(3)}"
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 12b. Dose/timing combo (2MG/NOITE, 500MG/DIA)
    if not result.dose:
        m = _DOSE_TIMING_RE.search(cleaned)
        if m:
            result.dose = f"{m.group(1)}{m.group(2)}"
            if not result.timing:
                timing_val = m.group(3).lower()
                if timing_val in ("noite",):
                    result.timing = "à noite"
                elif timing_val in ("dia",):
                    result.timing = "pela manhã"
                else:
                    result.timing = timing_val
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 12c. Dose (30mg, 6,25mg, 500mg) — only if not already set
    if not result.dose:
        m = _DOSE_RE.search(cleaned)
        if m:
            result.dose = m.group(0).strip()
            cleaned = cleaned[: m.start()] + cleaned[m.end() :]
            cleaned = cleaned.strip()

    # 12d. Extract additional doses for combination drugs (e.g. "MedA 1,5g + MedB 1,2g")
    if result.dose:
        extra_dose = _DOSE_RE.search(cleaned)
        if extra_dose:
            result.dose = f"{result.dose} + {extra_dose.group(0).strip()}"
            cleaned = cleaned[: extra_dose.start()] + cleaned[extra_dose.end() :]
            cleaned = cleaned.strip()

    # 13. "contínuo" marker
    m = _CONTINUOUS_RE.search(cleaned)
    if m:
        cleaned = cleaned[: m.start()] + cleaned[m.end() :]
        cleaned = cleaned.strip()

    # 14. Clean up remaining text → medication name
    # Remove trailing dashes, commas, colons, arrows
    cleaned = re.sub(r"[-–—:,>]+\s*$", "", cleaned).strip()
    cleaned = re.sub(r"^\s*[-–—:,>]+", "", cleaned).strip()
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Remove leading/trailing "de" (leftover from "de 12/12h")
    cleaned = re.sub(r"\bde\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^\s*de\b", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove stray "ao dia", "por dia", "na semana" left in the name
    cleaned = re.sub(r"\b(?:ao|por|no)\s+dia\b", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(?:na|por)\s+semana\b", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(?:ao|por|no)\s+m[eê]s\b", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove orphaned "no" or "ao" left from timing extraction (e.g. "no almoço" → "almoço" extracted)
    cleaned = re.sub(r"\bno\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\bao\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove orphaned "e" at end (leftover from compound timing)
    cleaned = re.sub(r"\be\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove "sublingual" as separate timing info
    if "sublingual" in cleaned.lower():
        result.extra_info = (result.extra_info or "") + " sublingual"
        cleaned = re.sub(r"\bsublingual\b", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove "spray" from name if it ended up here (e.g. "Symbicort spray")
    # Actually keep it — it's a valid part of the medication description
    # Remove "xarope" trailing
    # Actually keep it — it's a valid medication form descriptor

    # Condition suffix outside parens: "se crises de ansiedade"
    if not result.condition:
        m = _CONDITION_SUFFIX_RE.search(cleaned)
        if m:
            result.condition = m.group(0).strip()
            cleaned = cleaned[: m.start()].strip()

    # Final cleanup of leftover slashes, parens, and stray punctuation
    cleaned = re.sub(r"[/]\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\(\s*/?\s*\)", "", cleaned).strip()
    # Remove orphan parentheses containing only numbers or punctuation
    cleaned = re.sub(r"\(\s*[^a-zA-ZÀ-ú]*\s*\)", "", cleaned).strip()
    # Strip any remaining leading/trailing commas, dashes, spaces
    cleaned = cleaned.strip(" ,;:-–—/")
    # Collapse repeated spaces that may appear after removals
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    result.medication_name = cleaned
    return result


# ---------------------------------------------------------------------------
# EMR (Electronic Medical Record) multi-line format parser
# ---------------------------------------------------------------------------

_EMR_DETECT_RE = re.compile(r"\|\s*Oral\s*\|", re.IGNORECASE)

_EMR_TYPE_RE = re.compile(
    r"^(?:Uso\s+cont[ií]nuo|Especial)",
    re.IGNORECASE,
)

_EMR_PERIOD_RE = re.compile(r"^Per[ií]odo:", re.IGNORECASE)

_EMR_RECOM_RE = re.compile(r"^Recomenda[çc][õo]es", re.IGNORECASE)

_EMR_NO_RECOM_RE = re.compile(
    r"^N[ãa]o h[áa] recomenda[çc][õo]es",
    re.IGNORECASE,
)

_EMR_DOSING_FREQ_RE = re.compile(
    r"a cada (\d+)\s*(hora|dia|semana|m[eê]s)",
    re.IGNORECASE,
)

_EMR_DOSING_VEZES_RE = re.compile(
    r"(\d+)\s*vez(?:es)?\s*a cada\s*(\d+)\s*(dia|semana|m[eê]s)",
    re.IGNORECASE,
)


def _is_emr_format(text: str) -> bool:
    """Detect if the input is in multi-line EMR format."""
    return bool(_EMR_DETECT_RE.search(text))


def _parse_emr_dosing(dosing_part: str, result: ParsedMedication) -> None:
    """Parse the dosing portion before the first '|'.

    Examples:
        "1 comprimido, a cada 1 dia"
        "20 gotas, pela noite"
        "1 cápsula, 1 vez a cada 7 dias"
        "1 comprimido, a cada 12 horas"
        "1 comprimido, pela manhã"
    """
    # Split on first comma: qty+form , frequency/timing
    parts = [p.strip() for p in dosing_part.split(",", 1)]

    # Quantity + form
    qty_m = re.match(r"(\d+)\s+(.+)", parts[0])
    if qty_m:
        result.quantity_per_dose = f"{qty_m.group(1)} {qty_m.group(2).strip()}"

    if len(parts) < 2:
        return
    freq_part = parts[1].strip()

    # "N vez(es) a cada M dias" → weekly/periodic
    m = _EMR_DOSING_VEZES_RE.search(freq_part)
    if m:
        times, interval, unit = m.group(1), int(m.group(2)), m.group(3).lower()
        if unit.startswith("dia") and interval == 7:
            result.frequency = f"{times} vez por semana"
        elif unit.startswith("dia"):
            result.frequency = f"{times} vez a cada {interval} dias"
        else:
            result.frequency = m.group(0)
        return

    # "a cada N horas" → frequency
    m = _EMR_DOSING_FREQ_RE.search(freq_part)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("hora"):
            result.frequency = f"de {n} em {n} horas"
        elif unit.startswith("dia"):
            if n == 1:
                result.frequency = "1 vez ao dia"
            else:
                result.frequency = f"a cada {n} dias"
        elif unit.startswith("semana"):
            result.frequency = f"a cada {n} semanas"
        else:
            result.frequency = m.group(0)
        return

    # "pela manhã", "pela noite", "pela tarde"
    m = re.search(r"pel[ao]\s+(manh[aã]|noite|tarde)", freq_part, re.IGNORECASE)
    if m:
        val = m.group(1).lower()
        if val in ("manhã", "manha"):
            result.timing = "cedo"
        elif val == "noite":
            result.timing = "noite"
        elif val == "tarde":
            result.timing = "tarde"
        return

    # Fallback: store raw
    result.timing = freq_part


def _parse_emr_block(block_lines: list[str]) -> ParsedMedication:
    """Parse a single EMR medication block into ParsedMedication."""
    raw = "\n".join(block_lines)
    result = ParsedMedication(raw_text=raw, medication_name="")

    # --- Line 0: medication name + dose ---
    name_line = block_lines[0]

    # Extract dose
    dose_m = _DOSE_RE.search(name_line)
    if dose_m:
        result.dose = dose_m.group(0).strip()
        name = name_line[: dose_m.start()].strip()
    else:
        name = name_line.strip()

    # Clean salt-form comma: "Clopidogrel, Bissulfato" → "Clopidogrel Bissulfato"
    name = re.sub(r",\s*", " ", name).strip()
    # Strip parenthetical alternate names but keep them as brand hint
    brand_m = re.search(r"\(([^)]+)\)", name)
    if brand_m:
        result.brand_in_parens = brand_m.group(1).strip()
        name = name[: brand_m.start()] + name[brand_m.end() :]
        name = re.sub(r"\s+", " ", name).strip()

    result.medication_name = name

    # --- Classify remaining lines ---
    dosing_line = ""
    recommendations: list[str] = []
    in_recom = False

    for line in block_lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        if in_recom:
            if not _EMR_NO_RECOM_RE.match(stripped):
                recommendations.append(stripped)
            continue

        if _EMR_RECOM_RE.match(stripped):
            in_recom = True
        elif _EMR_PERIOD_RE.match(stripped):
            continue
        elif "|" in stripped:
            dosing_line = stripped
        # Type line: skip (classification handled by DB match)

    # --- Parse dosing line ---
    if dosing_line:
        pipe_parts = [p.strip() for p in dosing_line.split("|")]
        if pipe_parts:
            _parse_emr_dosing(pipe_parts[0], result)

    # --- Parse recommendations ---
    for rec in recommendations:
        rec_stripped = rec.strip()
        rec_upper = rec_stripped.upper()

        if rec_upper == "EM JEJUM":
            result.extra_info = ((result.extra_info or "") + " em jejum").strip()
        elif rec_upper.startswith("PARA "):
            result.condition = rec_stripped
        elif any(
            rec_upper.startswith(v)
            for v in ("REDUZIR", "AUMENTAR", "TOMAR", "USAR", "APLICAR")
        ):
            result.extra_info = (
                (result.extra_info or "") + " " + rec_stripped
            ).strip()
        elif not result.brand_in_parens:
            # Likely a brand name (ALDACTONE, PURAN T4, ARADOIS / CORUS / ZART)
            brands = [b.strip() for b in rec_stripped.split("/")]
            result.brand_in_parens = brands[0].strip()

    return result


def _parse_emr_list(text: str) -> list[ParsedMedication]:
    """Parse EMR-format multi-line medication list."""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]

    # Find type-line indices ("Uso contínuo", "Especial", etc.)
    # The medication name is always the line before the type line.
    type_indices: list[int] = []
    for i, line in enumerate(lines):
        if _EMR_TYPE_RE.match(line):
            type_indices.append(i)

    if not type_indices:
        return []

    # Build blocks: each starts at (type_index - 1) and ends before the next
    blocks: list[list[str]] = []
    for j, ti in enumerate(type_indices):
        start = max(0, ti - 1)
        end = type_indices[j + 1] - 1 if j + 1 < len(type_indices) else len(lines)
        blocks.append(lines[start:end])

    return [_parse_emr_block(b) for b in blocks]


def parse_medication_list(text: str) -> list[ParsedMedication]:
    """Parse a full text block of medications.

    Auto-detects single-line format vs multi-line EMR format.
    """
    if _is_emr_format(text):
        return _parse_emr_list(text)

    lines = text.strip().split("\n")
    results = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        results.append(parse_medication_line(line))
    return results
