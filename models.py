from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PrescriptionType(Enum):
    SIMPLES = "simples"
    CONTROLE_ESPECIAL = "controle_especial"
    B1_EXCLUDED = "b1_excluded"
    A1_A2_A3_EXCLUDED = "a1_a2_a3_excluded"
    C4_EXCLUDED = "c4_excluded"
    C5_EXCLUDED = "c5_excluded"
    UNKNOWN = "unknown"


class PharmacyProgram(Enum):
    FARMACIA_POPULAR = "farmacia_popular"
    REMUNE = "remune"
    REGULAR = "regular"


class SuspensionStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    POSSIBLY_SUSPENDED = "possibly_suspended"


@dataclass
class ParsedMedication:
    raw_text: str
    medication_name: str
    brand_in_parens: Optional[str] = None
    dose: Optional[str] = None
    posology_code: Optional[str] = None
    frequency: Optional[str] = None
    timing: Optional[str] = None
    quantity_per_dose: Optional[str] = None
    condition: Optional[str] = None
    suspension: SuspensionStatus = SuspensionStatus.ACTIVE
    suspension_reason: Optional[str] = None
    extra_info: Optional[str] = None
    is_tarv: bool = False


@dataclass
class MatchedMedication:
    parsed: ParsedMedication
    db_name: str = ""
    db_id: Optional[int] = None
    prescription_type: PrescriptionType = PrescriptionType.UNKNOWN
    tipo_raw: Optional[str] = None
    apresentacoes: Optional[str] = None
    posologia_adultos: Optional[str] = None
    formas_administracao: Optional[str] = None
    composition: Optional[str] = None
    match_confidence: float = 0.0
    match_method: str = ""
    pharmacy_program: "PharmacyProgram" = None  # type: ignore[assignment]


@dataclass
class PrescriptionItem:
    medication_display: str
    quantity: str
    instructions: str
    prescription_type: PrescriptionType = PrescriptionType.SIMPLES
    is_suspended: bool = False
