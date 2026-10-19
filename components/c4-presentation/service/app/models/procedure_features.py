"""Versioned structural measurements for C4's canonical graph.

These measurements describe supplied procedure structure. They do not
claim to measure cognitive difficulty or establish source authenticity.
"""

from typing import Literal

from pydantic import AwareDatetime, Field, computed_field

from app.models.procedure import Completeness, ServiceId
from app.models.procedure_graph import GraphCompleteness, GraphRecord


FEATURE_NAMES = (
    "step_count",
    "information_volume",
    "branch_count",
    "condition_count",
    "dependency_count",
    "dependency_depth",
    "parallel_group_count",
)


class NormalizationScales(GraphRecord):
    """Fixed positive scales, recorded in each measurement.

    These defaults are engineering starting values. They are not learned
    population statistics or validated difficulty thresholds.
    """

    step_count: float = Field(default=10.0, gt=0)
    information_volume: float = Field(default=200.0, gt=0)
    branch_count: float = Field(default=3.0, gt=0)
    condition_count: float = Field(default=5.0, gt=0)
    dependency_count: float = Field(default=10.0, gt=0)
    dependency_depth: float = Field(default=5.0, gt=0)
    parallel_group_count: float = Field(default=3.0, gt=0)


class FeatureMeasurement(GraphRecord):
    """Observed structure, with an explicit completeness qualification."""

    observed: int = Field(ge=0)
    completeness: Completeness
    scale: float = Field(gt=0)

    @computed_field
    @property
    def exact_value(self) -> int | None:
        """Return no exact value when coverage is partial or unknown."""
        if self.completeness == "complete":
            return self.observed
        return None

    @computed_field
    @property
    def normalized_observed(self) -> float:
        return self.observed / (self.observed + self.scale)

    @computed_field
    @property
    def normalized_exact(self) -> float | None:
        if self.completeness == "complete":
            return self.normalized_observed
        return None


class InformationBreakdown(GraphRecord):
    """Disjoint contributions to the chosen input-volume measurement."""

    stage_label_units: int = Field(ge=0)
    required_content_units: int = Field(ge=0)
    supplementary_content_units: int = Field(ge=0)
    condition_units: int = Field(ge=0)
    fact_units: int = Field(ge=0)

    @computed_field
    @property
    def total(self) -> int:
        return (
            self.stage_label_units
            + self.required_content_units
            + self.supplementary_content_units
            + self.condition_units
            + self.fact_units
        )


class FeatureDiagnostics(GraphRecord):
    """Interpretation data outside the seven-feature vector.

    Stage dependency observations use source_completeness.
    service_dependencies from the containing result.

    Branch counts describe groups, not selected execution paths.
    """

    stage_count: int = Field(ge=0)
    observed_stage_dependency_count: int = Field(ge=0)
    observed_stage_dependency_depth: int = Field(ge=0)

    and_group_count: int = Field(ge=0)
    or_group_count: int = Field(ge=0)
    xor_group_count: int = Field(ge=0)
    branch_option_count: int = Field(ge=0)

    referenced_content_count: int = Field(ge=0)
    referenced_fact_count: int = Field(ge=0)
    unreferenced_content_count: int = Field(ge=0)
    unreferenced_condition_count: int = Field(ge=0)

    information: InformationBreakdown


class StructuralFeatures(GraphRecord):
    """Exportable measurement result for a validated canonical snapshot.

    Construct through extract_structural_features(). JSON export includes
    computed interpretation fields; it is not a new graph-import format.
    """

    feature_schema_version: Literal["1.0"] = "1.0"
    measurement_version: Literal["c4-structural-1.0"] = "c4-structural-1.0"
    normalization_method: Literal["x_over_x_plus_scale_v1"] = (
        "x_over_x_plus_scale_v1"
    )
    lexical_rule: Literal["nfc_unicode_lmn_runs_v1"] = (
        "nfc_unicode_lmn_runs_v1"
    )
    unicode_data_version: str

    graph_schema_version: Literal["1.0"]
    plan_id: str
    requested_service_id: ServiceId
    generated_at: AwareDatetime
    synthetic: bool
    disclaimer: str

    measurement_scope: Literal["whole_procedure"] = "whole_procedure"
    step_unit: Literal["action"] = "action"
    dependency_layer: Literal["action"] = "action"
    dependency_depth_unit: Literal["edge"] = "edge"

    source_completeness: GraphCompleteness

    step_count: FeatureMeasurement
    information_volume: FeatureMeasurement
    branch_count: FeatureMeasurement
    condition_count: FeatureMeasurement
    dependency_count: FeatureMeasurement
    dependency_depth: FeatureMeasurement
    parallel_group_count: FeatureMeasurement

    diagnostics: FeatureDiagnostics

    def ordered_measurements(self) -> tuple[FeatureMeasurement, ...]:
        """Return the seven measurements in the documented fixed order."""
        return tuple(getattr(self, name) for name in FEATURE_NAMES)

    def context_encoding(self) -> tuple[tuple[str, float], ...]:
        """Return named numeric inputs with mandatory completeness flags.

        Four entries per feature:
        normalized observation, complete flag, partial flag, unknown flag.

        This prepares structural inputs only. It does not construct the
        eventual full user/procedure/action context or implement LinTS.
        """
        encoded = []
        for name, measurement in zip(
            FEATURE_NAMES, self.ordered_measurements()
        ):
            encoded.append(
                (
                    f"{name}.normalized_observed",
                    measurement.normalized_observed,
                )
            )
            for state in ("complete", "partial", "unknown"):
                encoded.append(
                    (
                        f"{name}.is_{state}",
                        float(measurement.completeness == state),
                    )
                )
        return tuple(encoded)