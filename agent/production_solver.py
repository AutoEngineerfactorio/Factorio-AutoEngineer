"""
This bounded estimator calculates a single recipe's output rate from caller-
provided machine factors, sustained input throughputs, power budget and surface.
Those inputs are not independently observed or validated against a live game.
The separate gears fixture is synthetic offline arithmetic, not a factory proof.

It does not solve multi-recipe or multi-product flow balance, optimize real
recipe/machine alternatives, or verify machine/module/beacon/quality mechanics.
Catalyst inventory and returns, cyclic/recycling flows, stochastic yields,
fluid constraints and temperatures are unsupported. Spoilage is only a rough
one-second multiplier. Caller-supplied rate measurements are not collected or
proven live here. R06 and live-game acceptance remain incomplete.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from r06_fixture_chain import base_gears_chain

# Production status values
ProductionStatus = Literal["unavailable", "infeasible", "partial", "estimated", "verified", "measured"]


@dataclass
class MaterialInput:
    """Represents a material input to a recipe."""
    prototype_id: str
    count: float
    is_optional: bool = False
    is_catalyst: bool = False
    surface_required: list[str] = field(default_factory=list)


@dataclass
class MaterialOutput:
    """Represents a material output from a recipe."""
    prototype_id: str
    count: float
    is_byproduct: bool = False
    quality_index: Optional[int] = None


@dataclass
class Recipe:
    """Represents a production recipe with alternatives and constraints."""
    prototype_id: str
    base_speed: float  # items per second at 100% speed
    energy_usage: float  # kW per (output item/second), for deterministic fixture rates
    fluid_ports: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list["Recipe"] = field(default_factory=list)  # Alternative recipes for same output
    catalysts: list[str] = field(default_factory=list)
    byproducts: list[dict[str, Any]] = field(default_factory=list)
    quality_index: Optional[int] = None
    surface_eligible: list[str] = field(default_factory=lambda: ["default", "underground", "space"])
    spoilage_rate: float = 0.0  # probability per second of spoilage
    inputs: list[MaterialInput] = field(default_factory=list)  # Required input materials


@dataclass
class Machine:
    """Represents a production machine with speed and restrictions."""
    prototype_id: str
    name: str
    speed_multiplier: float = 1.0  # nonnegative crafting-speed factor
    productivity_bonus: float = 0.0  # from modules
    productivity_penalty: float = 0.0  # from modules
    beacon_bonus: float = 0.0  # from beacon
    quality_index: Optional[int] = None
    enabled: bool = True


@dataclass
class ProductionPlan:
    """Estimated plan, not live verification. Rates ending in gps are items/s;
    measured_rate_{1,5,10}min fields are normalized items/minute."""
    target_prototype: str
    target_speed_gps: float  # items per second target
    alternatives: list["ProductionPlan"] = field(default_factory=list)
    recommended_index: int = 0
    utilization_ideal: float = 0.0
    utilization_explicit: float = 0.0
    supply_limiting: list[str] = field(default_factory=list)
    energy_limiting: bool = False
    power_margin: float = 0.0
    measured_rate_1min: Optional[float] = None
    measured_rate_5min: Optional[float] = None
    measured_rate_10min: Optional[float] = None
    deviation_explanation: Optional[str] = None
    feasibility_status: ProductionStatus = "unavailable"
    achievable_rate_gps: float = 0.0  # Modeled output bound; not factory throughput proof
    required_power_kw: float = 0.0  # Power needed to meet target speed (kW)


class ProductionSolver:
    """
    Bounded one-recipe throughput estimator; graph output is descriptive only.
    
    The following capabilities are NOT provided or accepted by this estimator:
    - Recipe alternatives and catalysts
    - Cyclic/recycling flows
    - Probability and fluid/temperature handling
    - Spoilage and surface eligibility
    - Speed/productivity/module/beacon/quality restrictions
    - Supply and energy caps
    - No phantom material or free loops
    - Deterministic fallback and incremental invalidation
    """
    
    # Fixture data for 300 gears/minute proof
    # 300 gears/minute = 5 gears/second
    # 10 plates/second for plates recipe
    GEAR_FIXTURE_SPEED = 5.0  # gears per second
    PLATE_FIXTURE_SPEED = 10.0  # plates per second
    
    # Default fixture machine for gears.
    GEAR_MACHINE_PROTOTYPE = "assembling-machine-2"
    # Default fixture machine for plates.
    PLATE_MACHINE_PROTOTYPE = "electric-furnace"
    
    def __init__(self, profile_version: str = "unbound-test-fixture"):
        """
        Initialize the production solver.
        
        Args:
            profile_version: The profile/version string (vanilla, Space Age, etc.)
        """
        self.profile_version = profile_version
        self.recipes: dict[str, Recipe] = {}
        self.machines: dict[str, Machine] = {}
        self._cache: dict[str, Any] = {}
        self._cache_age: float = 0.0
        self._max_cache_age = 5.0  # seconds
        
    def add_recipe(self, recipe: Recipe) -> None:
        """Add a finite, structurally valid recipe estimate."""
        if (not isinstance(recipe, Recipe) or not isinstance(recipe.prototype_id, str)
                or not recipe.prototype_id or type(recipe.base_speed) not in (int, float)
                or not math.isfinite(recipe.base_speed) or recipe.base_speed <= 0
                or type(recipe.energy_usage) not in (int, float)
                or not math.isfinite(recipe.energy_usage) or recipe.energy_usage < 0):
            raise ValueError("Invalid recipe rate or identity")
        if not isinstance(recipe.inputs, list) or not isinstance(recipe.surface_eligible, list):
            raise ValueError("Invalid recipe inputs or surface eligibility")
        for inp in recipe.inputs:
            if (not isinstance(inp, MaterialInput) or not isinstance(inp.prototype_id, str)
                    or not inp.prototype_id or type(inp.count) not in (int, float)
                    or not math.isfinite(inp.count) or inp.count <= 0
                    or type(inp.is_optional) is not bool or type(inp.is_catalyst) is not bool):
                raise ValueError("Invalid recipe input")
            if (not isinstance(inp.surface_required, list)
                    or any(not isinstance(value, str) or not value for value in inp.surface_required)):
                raise ValueError("Invalid input surface restriction")
        if any(not isinstance(surface, str) or not surface for surface in recipe.surface_eligible):
            raise ValueError("Invalid recipe surface")
        self.recipes[recipe.prototype_id] = recipe
        
    def add_machine(self, machine: Machine) -> None:
        """Add a finite machine estimate; crafting speed may exceed one."""
        if not isinstance(machine, Machine):
            raise ValueError("Invalid machine")
        numbers = (
            machine.speed_multiplier, machine.productivity_bonus,
            machine.productivity_penalty, machine.beacon_bonus,
        )
        if (not isinstance(machine.prototype_id, str) or not machine.prototype_id
                or not isinstance(machine.name, str) or type(machine.enabled) is not bool
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in numbers)
                or machine.speed_multiplier < 0
                or machine.productivity_penalty < 0
                or machine.productivity_bonus < 0
                or machine.beacon_bonus < 0
                or (machine.quality_index is not None
                    and (type(machine.quality_index) is not int
                         or not 0 <= machine.quality_index <= 100))):
            raise ValueError("Invalid machine parameters")
        self.machines[machine.prototype_id] = machine
        
    def _compute_effective_speed(
        self,
        recipe: Recipe,
        machine: Machine,
        supply_available: dict[str, float],
        energy_available: float,
    ) -> tuple[float, list[str], bool]:
        """
        Compute the effective production speed with all restrictions.
        
        Args:
            recipe: The recipe being computed
            machine: The machine running the recipe
            supply_available: Input throughput {prototype_id: items/second},
                not an inventory quantity.
            energy_available: Available power in kW
            
        Returns:
            Tuple of (effective_speed, limiting_factors, is_energy_limited)
        """
        if not machine.enabled:
            return 0.0, ["machine-disabled"], False
            
        # Base speed from recipe
        base_speed = recipe.base_speed
        
        # Factorio machine crafting speeds are not limited to 1.0.
        speed = base_speed * machine.speed_multiplier
        
        # Apply productivity bonuses/penalties
        speed *= (1.0 + machine.productivity_bonus - machine.productivity_penalty)
        
        # Apply beacon bonus
        speed *= (1.0 + machine.beacon_bonus)
        
        # This bounded one-machine estimate uses supply_available as input
        # throughput in items/second, NOT a stored inventory snapshot. An
        # inventory snapshot alone cannot establish a sustainable rate.
        if (
            type(energy_available) not in (int, float)
            or not math.isfinite(energy_available)
            or energy_available < 0
            or not math.isfinite(recipe.energy_usage)
            or recipe.energy_usage < 0
        ):
            raise ValueError("Invalid available power or recipe energy rate")
        if not math.isfinite(speed) or speed < 0:
            raise ValueError("Invalid machine production speed")
        if not math.isfinite(recipe.spoilage_rate) or not 0 <= recipe.spoilage_rate <= 1:
            raise ValueError("Invalid spoilage rate")

        speed *= 1.0 - recipe.spoilage_rate  # Estimated one-second loss
        limiting_factors: list[str] = []
        rated_speed = speed
        for inp in recipe.inputs:
            if inp.is_optional:
                continue
            if (
                type(inp.count) not in (int, float)
                or not math.isfinite(inp.count)
                or inp.count <= 0
            ):
                raise ValueError("Input counts must be finite and positive")
            available = supply_available.get(inp.prototype_id, 0)
            if type(available) not in (int, float) or not math.isfinite(available) or available < 0:
                raise ValueError("Input supply must be finite and nonnegative")
            # Input rates are throughput, not inventory. Catalyst starting stock
            # cannot be established by this interface, so do not compare units.
            if inp.is_catalyst:
                continue
            required = rated_speed * inp.count
            if available < required:
                limiting_factors.append(f"supply-{inp.prototype_id}")
            speed = min(speed, available / inp.count)

        is_energy_limited = rated_speed * recipe.energy_usage > energy_available
        if is_energy_limited:
            limiting_factors.append("energy")
            speed = min(speed, energy_available / recipe.energy_usage)
        return max(0.0, speed), limiting_factors, is_energy_limited
    
    def compute_production_plan(
        self,
        target_prototype: str,
        target_speed_gps: float,
        supply_available: dict[str, float],
        energy_available: float,
        surface: str = "default",
    ) -> ProductionPlan:
        """
        Compute a production plan for a target prototype.
        
        Args:
            target_prototype: The prototype ID to produce
            target_speed_gps: Target speed in items per second
            supply_available: Sustainable input throughput {prototype_id: items/second},
                not currently owned item counts.
            energy_available: Available power in kW
            surface: Current surface (default, underground, space)
            
        Returns:
            ProductionPlan with alternatives and utilization margins
        """
        if not isinstance(target_prototype, str) or not target_prototype:
            raise ValueError("Invalid target prototype")
        if (type(target_speed_gps) not in (int, float)
                or not math.isfinite(target_speed_gps) or target_speed_gps < 0):
            raise ValueError("Target throughput must be finite and nonnegative")
        if not isinstance(supply_available, dict):
            raise ValueError("Input throughput must be a mapping")
        for prototype_id, throughput in supply_available.items():
            if (not isinstance(prototype_id, str) or not prototype_id
                    or type(throughput) not in (int, float)
                    or not math.isfinite(throughput) or throughput < 0):
                raise ValueError("Input throughput must be finite and nonnegative")
        if (type(energy_available) not in (int, float)
                or not math.isfinite(energy_available) or energy_available < 0):
            raise ValueError("Available power must be finite and nonnegative")
        if not isinstance(surface, str) or not surface:
            raise ValueError("Invalid planning surface")

        # Find recipe for target prototype
        recipe = self.recipes.get(target_prototype)
        if not recipe:
            return ProductionPlan(
                target_prototype=target_prototype,
                target_speed_gps=target_speed_gps,
                alternatives=[],
                recommended_index=-1,
                utilization_ideal=0.0,
                utilization_explicit=0.0,
                supply_limiting=[],
                energy_limiting=True,
                power_margin=0.0,
            )
        
        # Find machine for this recipe
        machine = self.machines.get(recipe.prototype_id)
        if not machine:
            machine = Machine(
                prototype_id=recipe.prototype_id,
                name=f"{recipe.prototype_id}-machine",
                speed_multiplier=1.0,
            )
        
        # Machine capacity before input, power and surface limits.
        ideal_speed = recipe.base_speed
        ideal_speed *= machine.speed_multiplier
        ideal_speed *= (1.0 + machine.productivity_bonus - machine.productivity_penalty)
        ideal_speed *= (1.0 + machine.beacon_bonus)
        ideal_speed *= (1.0 - recipe.spoilage_rate)
        
        # Compute explicit speed (with all restrictions)
        explicit_speed, limiting_factors, is_energy_limited = self._compute_effective_speed(
            recipe, machine, supply_available, energy_available
        )
        for inp in recipe.inputs:
            if inp.surface_required and surface not in inp.surface_required:
                limiting_factors.append(f"input-surface-{inp.prototype_id}-ineligible")
                explicit_speed = 0.0
        
        # Check surface eligibility
        if surface not in recipe.surface_eligible:
            explicit_speed = 0.0
            limiting_factors.append(f"surface-{surface}-ineligible")
        
        # Compute utilization margins
        utilization_ideal = min(target_speed_gps / ideal_speed, 1.0) if ideal_speed > 0 else 0.0
        utilization_explicit = min(target_speed_gps / explicit_speed, 1.0) if explicit_speed > 0 else 0.0
        
        # Generate alternatives
        alternatives: list[ProductionPlan] = []
        
        # Alternative 1: Reduce speed multiplier
        alt_machine = Machine(
            prototype_id=recipe.prototype_id,
            name=f"{recipe.prototype_id}-machine-slower",
            speed_multiplier=machine.speed_multiplier * 0.7,
            productivity_bonus=machine.productivity_bonus,
            productivity_penalty=machine.productivity_penalty,
            beacon_bonus=machine.beacon_bonus,
        )
        alt_speed, alt_limits, alt_energy_limited = self._compute_effective_speed(
            recipe, alt_machine, supply_available, energy_available
        )
        if alt_speed > 0:
            alternatives.append(ProductionPlan(
                target_prototype=target_prototype,
                target_speed_gps=target_speed_gps,
                alternatives=[],
                recommended_index=0,
                utilization_ideal=utilization_ideal,
                utilization_explicit=min(target_speed_gps / alt_speed, 1.0) if alt_speed > 0 else 0.0,
                supply_limiting=alt_limits,
                energy_limiting=alt_energy_limited,
                power_margin=energy_available - recipe.energy_usage * min(target_speed_gps, recipe.base_speed * 0.7),
                feasibility_status="estimated" if alt_speed >= target_speed_gps else "partial",
                achievable_rate_gps=alt_speed,
                required_power_kw=target_speed_gps * recipe.energy_usage,
            ))
        
        # Alternative 2: Use alternative recipe if available
        if recipe.alternatives:
            alt_recipe = recipe.alternatives[0]
            alt_recipe_machine = self.machines.get(alt_recipe.prototype_id)
            if alt_recipe_machine:
                alt_recipe_speed, alt_limits, alt_energy_limited = self._compute_effective_speed(
                    alt_recipe, alt_recipe_machine, supply_available, energy_available
                )
                if alt_recipe_speed > 0:
                    alternatives.append(ProductionPlan(
                        target_prototype=target_prototype,
                        target_speed_gps=target_speed_gps,
                        alternatives=[],
                        recommended_index=0,
                        utilization_ideal=utilization_ideal,
                        utilization_explicit=min(target_speed_gps / alt_recipe_speed, 1.0) if alt_recipe_speed > 0 else 0.0,
                        supply_limiting=alt_limits,
                        energy_limiting=alt_energy_limited,
                        power_margin=energy_available - alt_recipe.energy_usage * min(target_speed_gps, alt_recipe.base_speed),
                        feasibility_status="estimated" if alt_recipe_speed >= target_speed_gps else "partial",
                        achievable_rate_gps=alt_recipe_speed,
                        required_power_kw=target_speed_gps * alt_recipe.energy_usage,
                    ))
        
        # Determine recommended alternative
        recommended_index = 0
        if len(alternatives) > 0:
            recommended_index = 0  # First alternative is recommended
        
        coverage_limits = []
        if not recipe.inputs:
            coverage_limits.append("unmodeled-source-throughput")
        if recipe.fluid_ports:
            coverage_limits.append("unsupported-fluid-constraints")
        if recipe.byproducts:
            coverage_limits.append("unsupported-byproduct-balance")
        if recipe.catalysts or any(inp.is_catalyst for inp in recipe.inputs):
            coverage_limits.append("unverified-catalyst-inventory-or-return")
        if recipe.quality_index is not None or machine.quality_index is not None:
            coverage_limits.append("unsupported-quality-effects")
        if recipe.spoilage_rate:
            coverage_limits.append("approximate-spoilage-model")
        if len(recipe.alternatives) > 1:
            coverage_limits.append("not-all-alternatives-evaluated")

        # A calculation alone never establishes verified in-game production.
        if explicit_speed <= 0:
            feasibility_status: ProductionStatus = "infeasible"
        elif explicit_speed < target_speed_gps or coverage_limits:
            feasibility_status = "partial"
        else:
            feasibility_status = "estimated"

        return ProductionPlan(
            target_prototype=target_prototype,
            target_speed_gps=target_speed_gps,
            alternatives=alternatives,
            recommended_index=recommended_index,
            utilization_ideal=utilization_ideal,
            utilization_explicit=utilization_explicit,
            supply_limiting=limiting_factors + coverage_limits,
            energy_limiting=is_energy_limited,
            power_margin=energy_available - recipe.energy_usage * min(target_speed_gps, ideal_speed),
            feasibility_status=feasibility_status,
            achievable_rate_gps=max(0.0, explicit_speed),
            required_power_kw=max(0.0, target_speed_gps * recipe.energy_usage),
        )
    
    def compute_recipe_graph(
        self,
        target_prototype: str,
        supply_available: dict[str, float],
        energy_available: float,
    ) -> dict[str, Any]:
        """
        Compute the full recipe graph for a target prototype.
        
        Args:
            target_prototype: The prototype ID to compute graph for
            supply_available: Dict of available materials
            energy_available: Available power in kW
            
        Returns:
            Dict with recipe graph data including alternatives, cycles, etc.
        """
        recipe = self.recipes.get(target_prototype)
        if not recipe:
            return {
                "target": target_prototype,
                "found": False,
                "alternatives": [],
                "cycles": [],
            }
        
        # Deterministic depth-first walk with an active recursion path.
        # Recorded edges are dependencies/alternatives, not proof of a viable
        # recipe. A cycle is not automatically free material.
        graph: dict[str, list[str]] = {}
        cycles: list[list[str]] = []
        complete: set[str] = set()
        active: list[str] = []
        truncated = False
        known: dict[str, Recipe] = dict(self.recipes)
        def register(recipe: Recipe) -> None:
            for alt in recipe.alternatives:
                if alt.prototype_id not in known:
                    known[alt.prototype_id] = alt
                # Cyclic object references are bounded by the known IDs.
        for rec in tuple(known.values()):
            register(rec)

        def build_graph_node(proto_id: str, depth: int = 0) -> None:
            nonlocal truncated
            if proto_id in active:
                cycles.append(active[active.index(proto_id):] + [proto_id])
                return
            if proto_id in complete:
                return
            if depth > 40:
                truncated = True
                return
            active.append(proto_id)
            rec = known.get(proto_id)
            if rec is None:
                graph[proto_id] = []
            else:
                children = list(dict.fromkeys(
                    [inp.prototype_id for inp in rec.inputs]
                    + [alt.prototype_id for alt in rec.alternatives]
                ))
                graph[proto_id] = ["output", *children]
                for dependency in children:
                    build_graph_node(dependency, depth + 1)
            active.pop()
            complete.add(proto_id)

        build_graph_node(target_prototype)
        
        return {
            "target": target_prototype,
            "found": True,
            "graph": graph,
            "cycles": cycles,
            "truncated": truncated,
        }
    
    def measure_production_rate(
        self,
        target_prototype: str,
        duration_seconds: float,
        initial_count: float,
        final_count: float,
    ) -> ProductionPlan:
        """
        Measure production rate from actual counts over time.
        
        Args:
            target_prototype: The prototype ID being measured
            duration_seconds: Duration of measurement in seconds
            initial_count: Initial item count
            final_count: Final item count
            
        Returns:
            ProductionPlan with measured rate and deviation explanation
        """
        if (not isinstance(target_prototype, str) or not target_prototype
                or type(duration_seconds) not in (int, float)
                or not math.isfinite(duration_seconds) or duration_seconds < 0
                or type(initial_count) not in (int, float)
                or not math.isfinite(initial_count) or initial_count < 0
                or type(final_count) not in (int, float)
                or not math.isfinite(final_count) or final_count < initial_count):
            raise ValueError("Invalid production measurement")
        if duration_seconds <= 0:
            return ProductionPlan(
                target_prototype=target_prototype,
                target_speed_gps=0.0,
                alternatives=[],
                recommended_index=-1,
                utilization_ideal=0.0,
                utilization_explicit=0.0,
                supply_limiting=[],
                energy_limiting=False,
                power_margin=0.0,
            )
        
        # Compute measured rate (items per second)
        measured_rate = (final_count - initial_count) / duration_seconds
        
        # Find recipe for target
        recipe = self.recipes.get(target_prototype)
        if not recipe:
            return ProductionPlan(
                target_prototype=target_prototype,
                target_speed_gps=0.0,
                alternatives=[],
                recommended_index=-1,
                utilization_ideal=0.0,
                utilization_explicit=0.0,
                supply_limiting=[],
                energy_limiting=True,
                power_margin=0.0,
            )
        
        # Find machine
        machine = self.machines.get(recipe.prototype_id)
        if not machine:
            machine = Machine(
                prototype_id=recipe.prototype_id,
                name=f"{recipe.prototype_id}-machine",
                speed_multiplier=1.0,
            )
        
        # Compute ideal rate
        ideal_rate = recipe.base_speed * machine.speed_multiplier
        ideal_rate *= (1.0 + machine.productivity_bonus - machine.productivity_penalty)
        ideal_rate *= (1.0 + machine.beacon_bonus)
        ideal_rate *= (1.0 - recipe.spoilage_rate)
        
        # Compute deviation
        deviation = measured_rate - ideal_rate
        deviation_pct = (deviation / ideal_rate * 100) if ideal_rate > 0 else 0.0
        
        # Generate deviation explanation
        deviation_explanation: Optional[str] = None
        if abs(deviation_pct) > 10.0:
            if measured_rate < ideal_rate * 0.5:
                deviation_explanation = "Significant underproduction detected. Check supply constraints, machine status, or recipe alternatives."
            elif measured_rate > ideal_rate * 1.5:
                deviation_explanation = "Overproduction detected. Check for alternative recipes or beacon/productivity effects."
            else:
                deviation_explanation = f"Moderate deviation ({deviation_pct:+.1f}%) from ideal rate. Verify supply and energy constraints."
        
        return ProductionPlan(
            target_prototype=target_prototype,
            target_speed_gps=measured_rate,  # Items/second; rate windows below are items/minute
            alternatives=[],
            recommended_index=0,
            utilization_ideal=min(measured_rate / ideal_rate, 1.0) if ideal_rate > 0 else 0.0,
            utilization_explicit=measured_rate / measured_rate if measured_rate > 0 else 0.0,
            supply_limiting=[],
            energy_limiting=False,
            power_margin=0.0,
            measured_rate_1min=measured_rate * 60.0 if duration_seconds == 60 else None,
            measured_rate_5min=measured_rate * 60.0 if duration_seconds == 300 else None,
            measured_rate_10min=measured_rate * 60.0 if duration_seconds == 600 else None,
            deviation_explanation=deviation_explanation,
        )
    
    def validate_no_phantom_materials(
        self,
        recipe: Recipe,
        supply_available: dict[str, float],
    ) -> list[str]:
        """
        Validate that no phantom materials are used.
        
        Args:
            recipe: The recipe to validate
            supply_available: Available materials
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []
        
        # Check each input material
        for inp in recipe.inputs if hasattr(recipe, 'inputs') else []:
            available = supply_available.get(inp.prototype_id, 0)
            required = inp.count
            if available < required:
                errors.append(f"Missing material: {inp.prototype_id} (need {required}, have {available})")
        
        return errors
    
    def validate_no_free_loops(
        self,
        recipe: Recipe,
    ) -> bool:
        """
        Validate that no free loops exist in the recipe.
        
        Args:
            recipe: The recipe to validate
            
        Returns:
            True if no free loops, False otherwise
        """
        known = dict(self.recipes)
        known[recipe.prototype_id] = recipe
        active: set[str] = set()
        complete: set[str] = set()

        def check(current: Recipe, depth: int) -> bool:
            if depth > 40 or current.prototype_id in active:
                return False  # Unresolved depth/cycle is not proven material-safe.
            if current.prototype_id in complete:
                return True
            active.add(current.prototype_id)
            try:
                for inp in current.inputs:
                    child = known.get(inp.prototype_id)
                    if child is not None and not check(child, depth + 1):
                        return False
                for alternative in current.alternatives:
                    # Alternatives are Recipe objects, NOT MaterialInput.
                    candidate = known.get(alternative.prototype_id, alternative)
                    if not check(candidate, depth + 1):
                        return False
            finally:
                active.remove(current.prototype_id)
            complete.add(current.prototype_id)
            return True

        return check(recipe, 0)
    
    def get_fixture_proof(self, fixture_name: str) -> dict[str, Any]:
        """
        Get proof data for a specific fixture.
        
        Args:
            fixture_name: Name of the fixture ("gears" or "plates")
            
        Returns:
            Dict with fixture proof data
        """
        if fixture_name == "gears":
            return {
                "fixture_name": "gears",
                "target_speed_gps": self.GEAR_FIXTURE_SPEED,
                "target_speed_gpm": self.GEAR_FIXTURE_SPEED * 60.0,
                "machine_prototype": self.GEAR_MACHINE_PROTOTYPE,
                "expected_output": self.GEAR_FIXTURE_SPEED,
                "notes": "Synthetic offline two-stage fixture: 5 gears/s = 300 gears/minute; not gameplay proof",
                "chain": base_gears_chain(),
            }
        elif fixture_name == "plates":
            return {
                "fixture_name": "plates",
                "target_speed_gps": self.PLATE_FIXTURE_SPEED,
                "target_speed_gpm": self.PLATE_FIXTURE_SPEED * 60.0,
                "machine_prototype": self.PLATE_MACHINE_PROTOTYPE,
                "expected_output": self.PLATE_FIXTURE_SPEED,
                "notes": "Synthetic 10 plates/s target only; not gameplay proof",
            }
        else:
            return {
                "fixture_name": fixture_name,
                "target_speed_gps": 0.0,
                "target_speed_gpm": 0.0,
                "machine_prototype": None,
                "expected_output": 0.0,
                "notes": "Unknown fixture",
            }


# Convenience functions for creating production plans

def create_production_plan(
    target_prototype: str,
    target_speed_gps: float,
    alternatives: list[ProductionPlan] = None,
    recommended_index: int = 0,
    utilization_ideal: float = 0.0,
    utilization_explicit: float = 0.0,
    supply_limiting: list[str] = None,
    energy_limiting: bool = False,
    power_margin: float = 0.0,
    measured_rate_1min: Optional[float] = None,
    measured_rate_5min: Optional[float] = None,
    measured_rate_10min: Optional[float] = None,
    deviation_explanation: Optional[str] = None,
) -> ProductionPlan:
    """
    Create a production plan with all fields.
    
    Args:
        target_prototype: The prototype ID to produce
        target_speed_gps: Target speed in gears/items per second
        alternatives: List of alternative plans
        recommended_index: Index of recommended alternative
        utilization_ideal: Ideal utilization margin
        utilization_explicit: Explicit utilization margin
        supply_limiting: List of supply limiting factors
        energy_limiting: Whether energy is limiting
        power_margin: Power margin in kW
        measured_rate_1min: Measured 1-minute rate
        measured_rate_5min: Measured 5-minute rate
        measured_rate_10min: Measured 10-minute rate
        deviation_explanation: Explanation of rate deviation
        
    Returns:
        ProductionPlan instance
    """
    if alternatives is None:
        alternatives = []
    if supply_limiting is None:
        supply_limiting = []
    
    return ProductionPlan(
        target_prototype=target_prototype,
        target_speed_gps=target_speed_gps,
        alternatives=alternatives,
        recommended_index=recommended_index,
        utilization_ideal=utilization_ideal,
        utilization_explicit=utilization_explicit,
        supply_limiting=supply_limiting,
        energy_limiting=energy_limiting,
        power_margin=power_margin,
        measured_rate_1min=measured_rate_1min,
        measured_rate_5min=measured_rate_5min,
        measured_rate_10min=measured_rate_10min,
        deviation_explanation=deviation_explanation,
    )


def _normalize_input_dict(inp: dict[str, Any]) -> MaterialInput:
    """
    Normalize a dictionary input to a typed MaterialInput.
    
    Args:
        inp: Dictionary with keys like 'prototype_id', 'count', 'is_optional', 'is_catalyst'
        
    Returns:
        MaterialInput instance
    """
    return MaterialInput(
        prototype_id=inp.get("prototype_id", ""),
        count=inp.get("count", 1),
        is_optional=inp.get("is_optional", False),
        is_catalyst=inp.get("is_catalyst", False),
        surface_required=inp.get("surface_required", []),
    )


def create_recipe(
    prototype_id: str,
    base_speed: float,
    energy_usage: float,
    alternatives: list[Recipe] = None,
    catalysts: list[str] = None,
    byproducts: list[dict[str, Any]] = None,
    quality_index: Optional[int] = None,
    surface_eligible: list[str] = None,
    spoilage_rate: float = 0.0,
    inputs: list[dict[str, Any] | MaterialInput] = None,
) -> Recipe:
    """
    Create a recipe with all fields.
    
    Args:
        prototype_id: The prototype ID
        base_speed: Base production speed (items/second at 100%)
        energy_usage: Energy usage in kW
        alternatives: List of alternative recipes
        catalysts: List of catalyst prototype IDs
        byproducts: List of byproduct definitions
        quality_index: Quality index (0-100)
        surface_eligible: List of eligible surfaces
        spoilage_rate: Spoilage probability per second
        inputs: List of input material definitions (dicts or MaterialInput instances)
        
    Returns:
        Recipe instance
    """
    if alternatives is None:
        alternatives = []
    if catalysts is None:
        catalysts = []
    if byproducts is None:
        byproducts = []
    if surface_eligible is None:
        surface_eligible = ["default", "underground", "space"]
    if inputs is None:
        inputs = []
    
    # Normalize dict inputs to MaterialInput instances
    normalized_inputs: list[MaterialInput] = []
    for inp in inputs:
        if isinstance(inp, dict):
            normalized_inputs.append(_normalize_input_dict(inp))
        else:
            normalized_inputs.append(inp)
    
    return Recipe(
        prototype_id=prototype_id,
        base_speed=base_speed,
        energy_usage=energy_usage,
        alternatives=alternatives,
        catalysts=catalysts,
        byproducts=byproducts,
        quality_index=quality_index,
        surface_eligible=surface_eligible,
        spoilage_rate=spoilage_rate,
        inputs=normalized_inputs,
    )


def create_machine(
    prototype_id: str,
    name: str,
    speed_multiplier: float = 1.0,
    productivity_bonus: float = 0.0,
    productivity_penalty: float = 0.0,
    beacon_bonus: float = 0.0,
    quality_index: Optional[int] = None,
    enabled: bool = True,
) -> Machine:
    """
    Create a machine with all fields.
    
    Args:
        prototype_id: The machine prototype ID
        name: Machine name
        speed_multiplier: Nonnegative machine crafting-speed multiplier
        productivity_bonus: Productivity bonus from modules
        productivity_penalty: Productivity penalty from modules
        beacon_bonus: Beacon bonus
        quality_index: Quality index
        enabled: Whether machine is enabled
        
    Returns:
        Machine instance
    """
    return Machine(
        prototype_id=prototype_id,
        name=name,
        speed_multiplier=speed_multiplier,
        productivity_bonus=productivity_bonus,
        productivity_penalty=productivity_penalty,
        beacon_bonus=beacon_bonus,
        quality_index=quality_index,
        enabled=enabled,
    )
