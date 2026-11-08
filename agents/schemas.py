"""Pydantic models. These are the trust boundary.

The quarantined intake agent may only return `ExtractedEvidence`. Any free-text
instruction in the source has nowhere to land, because there is no free-text
field here that a downstream agent reads as an instruction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    flood = "flood"
    wind = "wind"
    hazard = "hazard"
    contents = "contents"
    structural = "structural"


class Peril(str, Enum):
    flood = "flood"
    wind_driven_rain = "wind_driven_rain"
    both = "both"
    structural = "structural"
    undetermined = "undetermined"


class Coverage(str, Enum):
    flood_policy = "flood_policy"
    homeowners_policy = "homeowners_policy"
    excluded = "excluded"
    needs_human = "needs_human"


class TrustLabel(str, Enum):
    trusted = "TRUSTED"
    machine = "MACHINE"
    untrusted = "UNTRUSTED"


class Channel(str, Enum):
    manifest_note = "manifest_note"
    homeowner_statement = "homeowner_statement"
    receipt = "receipt"
    contractor_estimate = "contractor_estimate"
    scene_text = "scene_text"
    scene_ocr = "scene_ocr"
    vlm_output = "vlm_output"
    filename_metadata = "filename_metadata"
    adjuster_notes = "adjuster_notes"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float
    y: float
    z: float


class DamageItem(BaseModel):
    """Mirrors Assets/Scripts/DamageItem.cs. Do not add fields Unity lacks."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=200)
    category: Category
    # 0 = present but undamaged. Mac 1 adds severity-0 contents items as the
    # fraud-checker trap: the homeowner claims them destroyed, the scene says no.
    severity: int = Field(ge=0, le=5)
    measuredValue: float = Field(ge=0)
    # May be empty: Mac 1's severity-0 "present but undamaged" items carry no
    # measurement, so they ship with unit "".
    unit: str = Field(default="", max_length=40)
    note: str = Field(max_length=2000)
    heightAboveFloor: float | None = Field(default=None, ge=0)
    room: str | None = None
    position: Position | None = None

    @property
    def height_m(self) -> float:
        """Height used for the wind-vs-water test.

        Mac 1 populates `heightAboveFloor` meaningfully only for contents items
        (a laptop on a shelf at 1.6 m). Everything else carries a literal 0.0 —
        including `kitchen_ceiling_stain`, whose real height is 2.58 m. Treating
        0.0 as authoritative would put the ceiling stain below the waterline and
        destroy the wind-vs-water determination, so 0.0 means "not supplied" and
        we fall back to the transform's y.
        """
        if self.heightAboveFloor:  # non-zero and not None
            return self.heightAboveFloor
        return self.position.y if self.position else 0.0

    @property
    def is_undamaged(self) -> bool:
        return self.severity == 0


class SceneText(BaseModel):
    """Text physically visible inside the house. ALWAYS untrusted."""

    model_config = ConfigDict(extra="ignore")
    id: str
    text: str = Field(max_length=4000)


class DamageManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[DamageItem]
    scene_text: list[SceneText] = Field(default_factory=list)
    waterline_m: float = 0.9


class EvidenceDoc(BaseModel):
    """A piece of untrusted evidence as it arrives. Raw text stays in quarantine."""

    model_config = ConfigDict(extra="forbid")
    doc_id: str
    channel: Channel
    text: str = Field(max_length=20000)
    trust: TrustLabel = TrustLabel.untrusted


class ExtractedEvidence(BaseModel):
    """The ONLY thing allowed to cross from quarantine into the privileged zone.

    Every field is typed and bounded. There is deliberately no free-text field
    that an orchestrator would read as an instruction: `claimant_summary` is
    length-capped and is treated as data for display, never as a prompt.
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    claimed_item_ids: list[str] = Field(default_factory=list, max_length=50)
    claimed_amounts_usd: list[float] = Field(default_factory=list, max_length=50)
    claimed_dates: list[str] = Field(default_factory=list, max_length=20)
    mentions_total_loss: bool = False
    mentions_prior_damage: bool = False
    claimant_summary: str = Field(default="", max_length=400)

    @field_validator("claimed_amounts_usd")
    @classmethod
    def _bound_amounts(cls, v: list[float]) -> list[float]:
        # An extracted amount is a *claim*, never an estimate. Bound it anyway
        # so a hijacked extractor cannot park $250,000 in the record.
        return [max(0.0, min(float(a), 1_000_000.0)) for a in v]


class SecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    channel: Channel
    snippet: str = Field(max_length=400)
    span: tuple[int, int] | None = None
    rule: str
    layer: Literal["rules", "guard_model", "llm_judge", "canary", "bounds",
                   "consistency", "output", "flow_control"]
    severity: Literal["low", "medium", "high", "critical"]
    action_taken: Literal["blocked", "stripped", "quarantined", "flagged_only"] = "blocked"


class Estimate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    low_usd: float = Field(ge=0)
    high_usd: float = Field(ge=0)
    source: Literal["contracts/costs.json"] = "contracts/costs.json"


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    label: str
    peril: Peril
    coverage: Coverage
    exclusion_ref: str | None = None
    estimate: Estimate
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    rationale: str = ""


class Hazard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    hazard_type: Literal["electrical", "gas_co", "mold_airquality", "structural", "contamination"]
    priority: int = Field(ge=1, le=5)
    action: str
    dispatch: Literal[
        "licensed_electrician", "gas_utility", "structural_engineer",
        "remediation_contractor", "none",
    ]


class NeedsHuman(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    reason: str


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    model: str
    ms: float
    tool_calls: list[str] = Field(default_factory=list)
    note: str = ""


class Totals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    low_usd: float = 0
    high_usd: float = 0
    item_count: int = 0
    flood_policy_usd: tuple[float, float] = (0.0, 0.0)
    homeowners_policy_usd: tuple[float, float] = (0.0, 0.0)


class ClaimDraft(BaseModel):
    """Output of /assess. status is a constant: agents never approve payment."""

    model_config = ConfigDict(extra="forbid")

    audit_trail_id: str
    status: Literal["draft_pending_human"] = "draft_pending_human"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_trace: list[TraceStep] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    hazards: list[Hazard] = Field(default_factory=list)
    needs_human_review: list[NeedsHuman] = Field(default_factory=list)
    security_findings: list[SecurityFinding] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)
    # Information-flow result for this run: whether any untrusted input reached
    # a peril, coverage or cost decision. See agents/taint.py.
    flow_control: dict = Field(default_factory=dict)


class AssessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: DamageManifest
    evidence: list[EvidenceDoc] = Field(default_factory=list)
    adjuster_notes: str = Field(default="", max_length=4000)
    guard_enabled: bool = True


class AttackDemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(default="", max_length=20000)
    channel: Channel = Channel.scene_ocr
    image_b64: str | None = Field(default=None, max_length=12_000_000)
