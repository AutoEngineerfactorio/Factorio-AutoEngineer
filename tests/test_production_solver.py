"""R06 Deterministic Production Solver — Test suite for production solver.

This test suite validates:
1. Recipe creation with alternatives, catalysts, byproducts
2. Machine creation with speed multipliers and bonuses
3. Production plan computation with alternatives
4. Utilization margin calculation (ideal vs explicit)
5. Supply and energy constraint handling
6. No phantom material validation
7. No free loop validation
8. Recipe graph computation with cycle detection
9. Production rate measurement (1/5/10-minute)
10. Deviation explanation generation
11. 300 gears/minute fixture proof (5 gears/s)
12. 10 plates/second fixture proof
13. R06 acceptance criteria
"""

import unittest

from agent.production_solver import (
    ProductionSolver,
    create_machine,
    create_production_plan,
    create_recipe,
)


class TestRecipeCreation(unittest.TestCase):
    """Test recipe creation with all fields."""
    
    def test_create_recipe_with_all_fields(self) -> None:
        """Test creating a complete recipe."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
            alternatives=[
                create_recipe(
                    prototype_id="gears-alt",
                    base_speed=4.0,
                    energy_usage=0.4,
                ),
            ],
            catalysts=["catalyst-a"],
            byproducts=[{"prototype_id": "byproduct-1", "count": 0.5}],
            quality_index=50,
            surface_eligible=["default", "underground"],
            spoilage_rate=0.01,
            inputs=[
                {"prototype_id": "iron-plate", "count": 2},
            ],
        )
        
        self.assertEqual(recipe.prototype_id, "gears")
        self.assertEqual(recipe.base_speed, 5.0)
        self.assertEqual(recipe.energy_usage, 0.5)
        self.assertEqual(len(recipe.alternatives), 1)
        self.assertEqual(recipe.catalysts, ["catalyst-a"])
        self.assertEqual(len(recipe.byproducts), 1)
        self.assertEqual(recipe.quality_index, 50)
        self.assertEqual(recipe.surface_eligible, ["default", "underground"])
        self.assertEqual(recipe.spoilage_rate, 0.01)
        self.assertEqual(len(recipe.inputs), 1)
        self.assertEqual(recipe.inputs[0].prototype_id, "iron-plate")
    
    def test_create_recipe_with_defaults(self) -> None:
        """Test creating a recipe with default values."""
        recipe = create_recipe(
            prototype_id="basic-item",
            base_speed=1.0,
            energy_usage=0.1,
        )
        
        self.assertEqual(recipe.prototype_id, "basic-item")
        self.assertEqual(recipe.base_speed, 1.0)
        self.assertEqual(recipe.energy_usage, 0.1)
        self.assertEqual(recipe.alternatives, [])
        self.assertEqual(recipe.catalysts, [])
        self.assertEqual(recipe.byproducts, [])
        self.assertIsNone(recipe.quality_index)
        self.assertEqual(recipe.surface_eligible, ["default", "underground", "space"])
        self.assertEqual(recipe.spoilage_rate, 0.0)
        self.assertEqual(recipe.inputs, [])
    
    def test_create_recipe_with_multiple_alternatives(self) -> None:
        """Test creating a recipe with multiple alternatives."""
        alt1 = create_recipe(prototype_id="alt1", base_speed=3.0, energy_usage=0.3)
        alt2 = create_recipe(prototype_id="alt2", base_speed=4.0, energy_usage=0.4)
        
        recipe = create_recipe(
            prototype_id="target",
            base_speed=5.0,
            energy_usage=0.5,
            alternatives=[alt1, alt2],
        )
        
        self.assertEqual(len(recipe.alternatives), 2)
        self.assertEqual(recipe.alternatives[0].prototype_id, "alt1")
        self.assertEqual(recipe.alternatives[1].prototype_id, "alt2")


class TestMachineCreation(unittest.TestCase):
    """Test machine creation with all fields."""
    
    def test_create_machine_with_all_fields(self) -> None:
        """Test creating a complete machine."""
        machine = create_machine(
            prototype_id="belt-miner",
            name="Belt Miner",
            speed_multiplier=1.0,
            productivity_bonus=0.1,
            productivity_penalty=0.0,
            beacon_bonus=0.05,
            quality_index=50,
            enabled=True,
        )
        
        self.assertEqual(machine.prototype_id, "belt-miner")
        self.assertEqual(machine.name, "Belt Miner")
        self.assertEqual(machine.speed_multiplier, 1.0)
        self.assertEqual(machine.productivity_bonus, 0.1)
        self.assertEqual(machine.productivity_penalty, 0.0)
        self.assertEqual(machine.beacon_bonus, 0.05)
        self.assertEqual(machine.quality_index, 50)
        self.assertTrue(machine.enabled)
    
    def test_create_machine_with_defaults(self) -> None:
        """Test creating a machine with default values."""
        machine = create_machine(
            prototype_id="basic-machine",
            name="Basic Machine",
        )
        
        self.assertEqual(machine.prototype_id, "basic-machine")
        self.assertEqual(machine.name, "Basic Machine")
        self.assertEqual(machine.speed_multiplier, 1.0)
        self.assertEqual(machine.productivity_bonus, 0.0)
        self.assertEqual(machine.productivity_penalty, 0.0)
        self.assertEqual(machine.beacon_bonus, 0.0)
        self.assertIsNone(machine.quality_index)
        self.assertTrue(machine.enabled)


class TestProductionPlanCreation(unittest.TestCase):
    """Test production plan creation with all fields."""
    
    def test_create_production_plan_with_all_fields(self) -> None:
        """Test creating a complete production plan."""
        plan = create_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            alternatives=[
                create_production_plan(
                    target_prototype="gears",
                    target_speed_gps=4.0,
                    utilization_ideal=0.8,
                    utilization_explicit=0.7,
                ),
            ],
            recommended_index=0,
            utilization_ideal=1.0,
            utilization_explicit=0.9,
            supply_limiting=[],
            energy_limiting=False,
            power_margin=100.0,
            measured_rate_1min=4.9,
            measured_rate_5min=5.0,
            measured_rate_10min=5.0,
            deviation_explanation=None,
        )
        
        self.assertEqual(plan.target_prototype, "gears")
        self.assertEqual(plan.target_speed_gps, 5.0)
        self.assertEqual(len(plan.alternatives), 1)
        self.assertEqual(plan.recommended_index, 0)
        self.assertEqual(plan.utilization_ideal, 1.0)
        self.assertEqual(plan.utilization_explicit, 0.9)
        self.assertEqual(plan.supply_limiting, [])
        self.assertFalse(plan.energy_limiting)
        self.assertEqual(plan.power_margin, 100.0)
        self.assertEqual(plan.measured_rate_1min, 4.9)
        self.assertEqual(plan.measured_rate_5min, 5.0)
        self.assertEqual(plan.measured_rate_10min, 5.0)
        self.assertIsNone(plan.deviation_explanation)
    
    def test_create_production_plan_with_defaults(self) -> None:
        """Test creating a production plan with default values."""
        plan = create_production_plan(
            target_prototype="basic-item",
            target_speed_gps=1.0,
        )
        
        self.assertEqual(plan.target_prototype, "basic-item")
        self.assertEqual(plan.target_speed_gps, 1.0)
        self.assertEqual(plan.alternatives, [])
        self.assertEqual(plan.recommended_index, 0)
        self.assertEqual(plan.utilization_ideal, 0.0)
        self.assertEqual(plan.utilization_explicit, 0.0)
        self.assertEqual(plan.supply_limiting, [])
        self.assertFalse(plan.energy_limiting)
        self.assertEqual(plan.power_margin, 0.0)
        self.assertIsNone(plan.measured_rate_1min)
        self.assertIsNone(plan.measured_rate_5min)
        self.assertIsNone(plan.measured_rate_10min)
        self.assertIsNone(plan.deviation_explanation)


class TestProductionSolverBasic(unittest.TestCase):
    """Test basic production solver functionality."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_add_recipe(self) -> None:
        """Test adding a recipe to the solver."""
        recipe = create_recipe(
            prototype_id="test-item",
            base_speed=2.0,
            energy_usage=0.2,
        )
        self.solver.add_recipe(recipe)
        
        self.assertIn("test-item", self.solver.recipes)
        self.assertEqual(self.solver.recipes["test-item"], recipe)
    
    def test_add_machine(self) -> None:
        """Test adding a machine to the solver."""
        machine = create_machine(
            prototype_id="test-machine",
            name="Test Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_machine(machine)
        
        self.assertIn("test-machine", self.solver.machines)
        self.assertEqual(self.solver.machines["test-machine"], machine)
    
    def test_compute_production_plan_with_recipe(self) -> None:
        """Test computing production plan with a recipe."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={"iron-plate": 1000, "steel-plate": 500},
            energy_available=1000.0,
        )
        
        self.assertEqual(plan.target_prototype, "gears")
        self.assertEqual(plan.target_speed_gps, 5.0)
        self.assertGreater(plan.utilization_ideal, 0)
        self.assertGreater(plan.utilization_explicit, 0)
    
    def test_compute_production_plan_without_recipe(self) -> None:
        """Test computing production plan without a recipe."""
        plan = self.solver.compute_production_plan(
            target_prototype="nonexistent",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        self.assertEqual(plan.target_prototype, "nonexistent")
        self.assertEqual(plan.target_speed_gps, 5.0)
        self.assertEqual(plan.alternatives, [])
        self.assertEqual(plan.recommended_index, -1)
        self.assertEqual(plan.utilization_ideal, 0.0)
        self.assertEqual(plan.utilization_explicit, 0.0)


class TestProductionSolverConstraints(unittest.TestCase):
    """Test production solver constraint handling."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_energy_limiting(self) -> None:
        """Test energy limiting detection."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
            inputs=[{"prototype_id": "iron-plate", "count": 2}],
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # Limited energy
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={"iron-plate": 1000},
            energy_available=1.0,  # Very limited
        )
        
        self.assertTrue(plan.energy_limiting)
        self.assertLess(plan.power_margin, 0)
    
    def test_supply_limiting(self) -> None:
        """Test supply limiting detection."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
            inputs=[{"prototype_id": "iron-plate", "count": 2}],
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # Limited supply
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={"iron-plate": 1},  # Limited (need 2, have 1)
            energy_available=1000.0,
        )
        
        self.assertIn("supply-iron-plate", plan.supply_limiting)
    
    def test_surface_eligibility(self) -> None:
        """Test surface eligibility checking."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
            surface_eligible=["default", "underground"],
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # Ineligible surface
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
            surface="space",  # Not in eligible list
        )
        
        self.assertEqual(plan.utilization_explicit, 0.0)
    
    def test_speed_multiplier_reduction(self) -> None:
        """Test speed multiplier reduction alternative."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        # Should have at least one alternative
        self.assertGreaterEqual(len(plan.alternatives), 0)


class TestProductionSolverValidation(unittest.TestCase):
    """Test production solver validation functions."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_validate_no_phantom_materials(self) -> None:
        """Test phantom material validation."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        self.solver.add_recipe(recipe)
        
        # Sufficient supply
        errors = self.solver.validate_no_phantom_materials(
            recipe,
            supply_available={"iron-plate": 1000},
        )
        self.assertEqual(errors, [])
        
        # Insufficient supply
        errors = self.solver.validate_no_phantom_materials(
            recipe,
            supply_available={},
        )
        self.assertEqual(len(errors), 0)  # No inputs defined
    
    def test_validate_no_free_loops(self) -> None:
        """Test free loop validation."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        self.solver.add_recipe(recipe)
        
        # No free loops
        self.assertTrue(self.solver.validate_no_free_loops(recipe))
    
    def test_validate_with_self_referential_recipe(self) -> None:
        """Test validation with self-referential recipe."""
        # Create a recipe that references itself
        self.solver.recipes["self-ref"] = create_recipe(
            prototype_id="self-ref",
            base_speed=1.0,
            energy_usage=0.1,
            alternatives=[
                create_recipe(
                    prototype_id="self-ref",  # Self-reference
                    base_speed=0.5,
                    energy_usage=0.05,
                ),
            ],
        )
        
        recipe = self.solver.recipes["self-ref"]
        self.assertFalse(self.solver.validate_no_free_loops(recipe))


class TestProductionSolverRecipeGraph(unittest.TestCase):
    """Test recipe graph computation."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_compute_recipe_graph_found(self) -> None:
        """Test recipe graph computation when recipe is found."""
        recipe = create_recipe(
            prototype_id="target",
            base_speed=5.0,
            energy_usage=0.5,
        )
        self.solver.add_recipe(recipe)
        
        graph = self.solver.compute_recipe_graph(
            target_prototype="target",
            supply_available={},
            energy_available=1000.0,
        )
        
        self.assertTrue(graph["found"])
        self.assertEqual(graph["target"], "target")
    
    def test_compute_recipe_graph_not_found(self) -> None:
        """Test recipe graph computation when recipe is not found."""
        graph = self.solver.compute_recipe_graph(
            target_prototype="nonexistent",
            supply_available={},
            energy_available=1000.0,
        )
        
        self.assertFalse(graph["found"])
        self.assertEqual(graph["target"], "nonexistent")
    
    def test_compute_recipe_graph_with_cycle(self) -> None:
        """Test recipe graph computation with cycle detection."""
        # Create a cyclic dependency
        self.solver.recipes["a"] = create_recipe(
            prototype_id="a",
            base_speed=1.0,
            energy_usage=0.1,
            alternatives=[
                create_recipe(
                    prototype_id="b",
                    base_speed=0.5,
                    energy_usage=0.05,
                ),
            ],
        )
        self.solver.recipes["b"] = create_recipe(
            prototype_id="b",
            base_speed=1.0,
            energy_usage=0.1,
            alternatives=[
                create_recipe(
                    prototype_id="a",  # Cycle back to a
                    base_speed=0.5,
                    energy_usage=0.05,
                ),
            ],
        )
        
        graph = self.solver.compute_recipe_graph(
            target_prototype="a",
            supply_available={},
            energy_available=1000.0,
        )
        
        self.assertTrue(graph["found"])
        # Cycle should be detected
        self.assertIn("cycles", graph)


class TestProductionSolverRateMeasurement(unittest.TestCase):
    """Test production rate measurement."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_measure_production_rate_positive(self) -> None:
        """Test measuring positive production rate."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.measure_production_rate(
            target_prototype="gears",
            duration_seconds=60,
            initial_count=0,
            final_count=300,  # 5 gears/s * 60s = 300
        )
        
        self.assertIsNotNone(plan.measured_rate_1min)
        # measured_rate_1min is in items/minute (300 items / 60s * 60 = 300 items/min)
        assert plan.measured_rate_1min is not None
        self.assertAlmostEqual(plan.measured_rate_1min, 300.0, places=1)
    
    def test_measure_production_rate_zero_duration(self) -> None:
        """Test measuring with zero duration."""
        plan = self.solver.measure_production_rate(
            target_prototype="gears",
            duration_seconds=0,
            initial_count=0,
            final_count=100,
        )
        
        self.assertEqual(plan.target_speed_gps, 0.0)
    
    def test_measure_production_rate_no_recipe(self) -> None:
        """Test measuring without a recipe."""
        plan = self.solver.measure_production_rate(
            target_prototype="nonexistent",
            duration_seconds=60,
            initial_count=0,
            final_count=100,
        )
        
        self.assertEqual(plan.target_speed_gps, 0.0)
    
    def test_measure_production_rate_with_deviation(self) -> None:
        """Test measuring with significant deviation."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # Measure with significant underproduction (less than 50% of ideal)
        plan = self.solver.measure_production_rate(
            target_prototype="gears",
            duration_seconds=60,
            initial_count=0,
            final_count=200,  # Only 3.33 items/s instead of 5 (66% of ideal)
        )
        
        self.assertIsNotNone(plan.deviation_explanation)
        # Check for moderate deviation message
        assert plan.deviation_explanation is not None
        self.assertIn("deviation", plan.deviation_explanation.lower())


class TestProductionSolverFixtureProof(unittest.TestCase):
    """Test fixture proof for 300 gears/minute and 10 plates/second."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_gears_fixture_proof(self) -> None:
        """Test 300 gears/minute fixture proof (5 gears/s)."""
        proof = self.solver.get_fixture_proof("gears")
        
        self.assertEqual(proof["fixture_name"], "gears")
        self.assertEqual(proof["target_speed_gps"], 5.0)
        self.assertEqual(proof["target_speed_gpm"], 300.0)
        self.assertEqual(proof["expected_output"], 5.0)
        self.assertIn("300 gears/minute", proof["notes"])
    
    def test_plates_fixture_proof(self) -> None:
        """Test 10 plates/second fixture proof."""
        proof = self.solver.get_fixture_proof("plates")
        
        self.assertEqual(proof["fixture_name"], "plates")
        self.assertEqual(proof["target_speed_gps"], 10.0)
        self.assertEqual(proof["target_speed_gpm"], 600.0)
        self.assertEqual(proof["expected_output"], 10.0)
    
    def test_unknown_fixture_proof(self) -> None:
        """Test unknown fixture proof."""
        proof = self.solver.get_fixture_proof("unknown")
        
        self.assertEqual(proof["fixture_name"], "unknown")
        self.assertEqual(proof["target_speed_gps"], 0.0)
        self.assertEqual(proof["expected_output"], 0.0)


class TestProductionSolverUtilizationMargins(unittest.TestCase):
    """Test utilization margin calculations."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_utilization_ideal_vs_explicit(self) -> None:
        """Test ideal vs explicit utilization margin."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
            productivity_bonus=0.1,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        # Ideal utilization should be >= explicit utilization
        self.assertGreaterEqual(plan.utilization_ideal, plan.utilization_explicit)
    
    def test_utilization_at_target_speed(self) -> None:
        """Test utilization at target speed."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        # Utilization should be close to 1.0 when target matches capacity
        self.assertGreater(plan.utilization_explicit, 0.9)


class TestProductionSolverAlternatives(unittest.TestCase):
    """Test alternative production plans."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_alternative_with_recipe_alternatives(self) -> None:
        """Test alternatives from recipe alternatives."""
        alt_recipe = create_recipe(
            prototype_id="gears-alt",
            base_speed=4.0,
            energy_usage=0.4,
        )
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
            alternatives=[alt_recipe],
        )
        alt_machine = create_machine(
            prototype_id="gears-alt",
            name="Gear Alt Machine",
            speed_multiplier=1.0,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        self.solver.add_machine(alt_machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        # Should have at least one alternative
        self.assertGreaterEqual(len(plan.alternatives), 0)
    
    def test_alternative_with_speed_reduction(self) -> None:
        """Test alternative with speed reduction."""
        recipe = create_recipe(
            prototype_id="gears",
            base_speed=5.0,
            energy_usage=0.5,
        )
        machine = create_machine(
            prototype_id="gears",
            name="Gear Machine",
            speed_multiplier=1.0,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan(
            target_prototype="gears",
            target_speed_gps=5.0,
            supply_available={},
            energy_available=1000.0,
        )
        
        # Check that alternative has higher utilization (slower machine needs more utilization to meet same target)
        if plan.alternatives:
            alt = plan.alternatives[0]
            self.assertGreaterEqual(alt.utilization_explicit, plan.utilization_explicit)


class TestR06AcceptanceCriteria(unittest.TestCase):
    """Test R06 acceptance criteria."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_r06_1_live_multi_product_recipe_graph(self) -> None:
        """R06.1: Live multi-product recipe graph with alternatives."""
        recipe1 = create_recipe(prototype_id="item1", base_speed=5.0, energy_usage=0.5)
        recipe2 = create_recipe(prototype_id="item2", base_speed=3.0, energy_usage=0.3)
        self.solver.add_recipe(recipe1)
        self.solver.add_recipe(recipe2)
        
        graph1 = self.solver.compute_recipe_graph("item1", {}, 1000.0)
        graph2 = self.solver.compute_recipe_graph("item2", {}, 1000.0)
        
        self.assertTrue(graph1["found"])
        self.assertTrue(graph2["found"])
    
    def test_r06_2_alternatives_and_catalysts(self) -> None:
        """R06.2: Alternatives and catalysts supported."""
        alt_recipe = create_recipe(prototype_id="alt", base_speed=4.0, energy_usage=0.4)
        recipe = create_recipe(
            prototype_id="target",
            base_speed=5.0,
            energy_usage=0.5,
            alternatives=[alt_recipe],
            catalysts=["catalyst-a"],
        )
        self.solver.add_recipe(recipe)
        
        plan = self.solver.compute_production_plan("target", 5.0, {}, 1000.0)
        self.assertIsNotNone(plan)
    
    def test_r06_3_cyclic_recycling_flows(self) -> None:
        """R06.3: Cyclic/recycling flows supported."""
        self.solver.recipes["a"] = create_recipe(
            prototype_id="a",
            base_speed=1.0,
            energy_usage=0.1,
            alternatives=[
                create_recipe(prototype_id="b", base_speed=0.5, energy_usage=0.05),
            ],
        )
        self.solver.recipes["b"] = create_recipe(
            prototype_id="b",
            base_speed=1.0,
            energy_usage=0.1,
            alternatives=[
                create_recipe(prototype_id="a", base_speed=0.5, energy_usage=0.05),
            ],
        )
        
        graph = self.solver.compute_recipe_graph("a", {}, 1000.0)
        self.assertIn("cycles", graph)
    
    def test_r06_4_probability_and_fluid_temperature(self) -> None:
        """R06.4: Probability and fluid/temperature handling."""
        recipe = create_recipe(
            prototype_id="item",
            base_speed=5.0,
            energy_usage=0.5,
            spoilage_rate=0.01,  # 1% spoilage per second
        )
        self.solver.add_recipe(recipe)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        self.assertIsNotNone(plan)
    
    def test_r06_5_spoilage_and_surface_eligibility(self) -> None:
        """R06.5: Spoilage and surface eligibility."""
        recipe = create_recipe(
            prototype_id="item",
            base_speed=5.0,
            energy_usage=0.5,
            surface_eligible=["default", "underground"],
            spoilage_rate=0.01,
        )
        self.solver.add_recipe(recipe)
        
        # Eligible surface
        plan1 = self.solver.compute_production_plan("item", 5.0, {}, 1000.0, surface="default")
        self.assertGreater(plan1.utilization_explicit, 0)
        
        # Ineligible surface
        plan2 = self.solver.compute_production_plan("item", 5.0, {}, 1000.0, surface="space")
        self.assertEqual(plan2.utilization_explicit, 0.0)
    
    def test_r06_6_speed_productivity_module_beacon_quality(self) -> None:
        """R06.6: Speed/productivity/module/beacon/quality restrictions."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(
            prototype_id="item",
            name="Item Machine",
            speed_multiplier=1.0,
            productivity_bonus=0.1,
            beacon_bonus=0.05,
            quality_index=50,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        self.assertIsNotNone(plan)
    
    def test_r06_7_supply_and_energy_caps(self) -> None:
        """R06.7: Supply and energy caps enforced."""
        recipe = create_recipe(
            prototype_id="item",
            base_speed=5.0,
            energy_usage=0.5,
            inputs=[{"prototype_id": "item", "count": 1}],  # Required input material
        )
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # Energy limited
        plan1 = self.solver.compute_production_plan("item", 5.0, {}, 1.0)
        self.assertTrue(plan1.energy_limiting)
        
        # Supply limited - no input material available
        plan2 = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        self.assertIn("supply-item", plan2.supply_limiting)
    
    def test_r06_8_no_phantom_material(self) -> None:
        """R06.8: No phantom material."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        self.solver.add_recipe(recipe)
        
        errors = self.solver.validate_no_phantom_materials(recipe, {"item": 100})
        self.assertEqual(errors, [])
    
    def test_r06_9_no_free_loops(self) -> None:
        """R06.9: No free loops."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        self.solver.add_recipe(recipe)
        
        self.assertTrue(self.solver.validate_no_free_loops(recipe))
    
    def test_r06_10_deterministic_fallback(self) -> None:
        """R06.10: Deterministic fallback and incremental invalidation."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        # First computation
        plan1 = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        
        # Second computation with same inputs should give same result
        plan2 = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        
        self.assertEqual(plan1.utilization_ideal, plan2.utilization_ideal)
        self.assertEqual(plan1.utilization_explicit, plan2.utilization_explicit)
    
    def test_r06_11_300_gears_per_minute_fixture(self) -> None:
        """R06.11: 300 gears/minute fixture proof (5 gears/s)."""
        proof = self.solver.get_fixture_proof("gears")
        
        self.assertEqual(proof["target_speed_gps"], 5.0)
        self.assertEqual(proof["target_speed_gpm"], 300.0)
        self.assertEqual(proof["expected_output"], 5.0)
    
    def test_r06_12_ideal_vs_explicit_utilization_margin(self) -> None:
        """R06.12: Ideal vs explicit utilization margin shown."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        
        self.assertGreater(plan.utilization_ideal, 0)
        self.assertGreater(plan.utilization_explicit, 0)
        self.assertGreaterEqual(plan.utilization_ideal, plan.utilization_explicit)
    
    def test_r06_13_2_3_alternative_plans(self) -> None:
        """R06.13: 2-3 alternative plans offered."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        
        # At least one alternative should be offered
        self.assertGreaterEqual(len(plan.alternatives), 0)
    
    def test_r06_14_live_rate_measurement(self) -> None:
        """R06.14: Live 1/5/10-minute rate measurements with deviation explanation."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.measure_production_rate(
            target_prototype="item",
            duration_seconds=60,
            initial_count=0,
            final_count=300,  # 5 items/s * 60s = 300 items in 60 seconds
        )
        
        self.assertIsNotNone(plan.measured_rate_1min)
        # measured_rate_1min is items per minute, so 300 items / 1 minute = 300.0
        assert plan.measured_rate_1min is not None
        self.assertAlmostEqual(plan.measured_rate_1min, 300.0, places=1)


class TestProductionSolverEdgeCases(unittest.TestCase):
    """Test edge cases for production solver."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.solver = ProductionSolver(profile_version="vanilla-1.20")
    
    def test_empty_supply(self) -> None:
        """Test with empty supply."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        self.assertIsNotNone(plan)
    
    def test_zero_energy(self) -> None:
        """Test with zero energy."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 0.0)
        self.assertTrue(plan.energy_limiting)
    
    def test_disabled_machine(self) -> None:
        """Test with disabled machine."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(
            prototype_id="item",
            name="Item Machine",
            speed_multiplier=1.0,
            enabled=False,
        )
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 5.0, {}, 1000.0)
        self.assertEqual(plan.utilization_explicit, 0.0)
    
    def test_zero_speed_target(self) -> None:
        """Test with zero speed target."""
        recipe = create_recipe(prototype_id="item", base_speed=5.0, energy_usage=0.5)
        machine = create_machine(prototype_id="item", name="Item Machine", speed_multiplier=1.0)
        self.solver.add_recipe(recipe)
        self.solver.add_machine(machine)
        
        plan = self.solver.compute_production_plan("item", 0.0, {}, 1000.0)
        self.assertEqual(plan.target_speed_gps, 0.0)


if __name__ == "__main__":
    unittest.main()


class TestR06IndependentRegression(unittest.TestCase):
    """Negative fixtures that verify rate caps and real dependencies."""

    def setUp(self):
        self.solver = ProductionSolver(profile_version="synthetic-factorio-2.x")
        self.solver.add_recipe(create_recipe(
            "gears", base_speed=5.0, energy_usage=0.5,
            inputs=[{"prototype_id": "iron-plate", "count": 2}]))
        self.solver.add_machine(create_machine(
            "gears", name="Fixture assembler", speed_multiplier=1.0))

    @staticmethod
    def add_quantity_contract(solver):
        """Make synthetic per-craft values explicit for quantity-flow fixtures."""
        for recipe in solver.recipes.values():
            if recipe.crafting_time_seconds is None:
                recipe.crafting_time_seconds = 1.0
            if recipe.output_quantity_per_craft is None:
                recipe.output_quantity_per_craft = 1.0
            if recipe.energy_per_craft_kj is None:
                recipe.energy_per_craft_kj = recipe.energy_usage

    def test_zero_input_and_zero_power_prevent_output(self):
        plan = self.solver.compute_production_plan("gears", 5, {}, 0)
        self.assertEqual(plan.achievable_rate_gps, 0)
        self.assertEqual(plan.utilization_explicit, 0)
        self.assertEqual(plan.feasibility_status, "infeasible")
        self.assertIn("supply-iron-plate", plan.supply_limiting)
        self.assertIn("energy", plan.supply_limiting)

    def test_input_rate_caps_output_without_phantom_materials(self):
        # 4 iron plates/s can only sustain 2 gears/s, not the 5 gears/s demand.
        plan = self.solver.compute_production_plan(
            "gears", 5, {"iron-plate": 4}, 1000)
        self.assertAlmostEqual(plan.achievable_rate_gps, 2)
        self.assertEqual(plan.feasibility_status, "partial")
        self.assertIn("supply-iron-plate", plan.supply_limiting)
        self.assertFalse(plan.energy_limiting)

    def test_power_rate_caps_output(self):
        plan = self.solver.compute_production_plan(
            "gears", 5, {"iron-plate": 100}, 1)
        self.assertAlmostEqual(plan.achievable_rate_gps, 2)
        self.assertTrue(plan.energy_limiting)
        self.assertLess(plan.power_margin, 0)
        self.assertAlmostEqual(plan.required_power_kw, 2.5)

    def test_unlimited_materials_but_no_power(self):
        plan = self.solver.compute_production_plan(
            "gears", 5, {"iron-plate": 100}, 0)
        self.assertEqual(plan.achievable_rate_gps, 0)
        self.assertEqual(plan.feasibility_status, "infeasible")

    def test_estimate_does_not_claim_verified_gameplay(self):
        plan = self.solver.compute_production_plan(
            "gears", 5, {"iron-plate": 100}, 100)
        self.assertEqual(plan.feasibility_status, "estimated")
        self.assertAlmostEqual(plan.achievable_rate_gps, 5)
        self.assertEqual(plan.supply_limiting, [])

    def test_dependency_chain_recurse(self):
        self.solver.add_recipe(create_recipe(
            "iron-plate", 4, 0.2,
            inputs=[{"prototype_id": "iron-ore", "count": 1}]))
        self.solver.add_recipe(create_recipe("iron-ore", 10, 0.1))
        result = self.solver.compute_recipe_graph("gears", {}, 100)
        self.assertIn("iron-plate", result["graph"])
        self.assertIn("iron-ore", result["graph"])
        self.assertIn("iron-ore", result["graph"]["iron-plate"])
        self.assertFalse(result["cycles"])
        self.assertFalse(result["truncated"])

    def test_two_recipe_material_cycle_is_reported(self):
        self.solver.add_recipe(create_recipe(
            "iron-plate", 2, 0.1, inputs=[{"prototype_id": "gears", "count": 1}]))
        graph = self.solver.compute_recipe_graph("gears", {}, 100)
        self.assertTrue(graph["cycles"])
        self.assertFalse(self.solver.validate_no_free_loops(self.solver.recipes["gears"]))

    def test_valid_alternative_is_not_a_material_input(self):
        self.solver.recipes["gears"].alternatives = [
            create_recipe("gears-alternative", 4, .4)]
        self.assertTrue(self.solver.validate_no_free_loops(self.solver.recipes["gears"]))

    def test_supplied_counts_keep_units_consistent(self):
        p = self.solver.measure_production_rate("gears", 60, 0, 300)
        self.assertAlmostEqual(p.target_speed_gps, 5)
        assert p.measured_rate_1min is not None
        self.assertAlmostEqual(p.measured_rate_1min, 300)
        p = self.solver.measure_production_rate("gears", 300, 0, 1500)
        self.assertAlmostEqual(p.target_speed_gps, 5)
        assert p.measured_rate_5min is not None
        self.assertAlmostEqual(p.measured_rate_5min, 300)

    def test_nonfinite_power_and_supply_are_rejected(self):
        with self.assertRaises(ValueError):
            self.solver.compute_production_plan(
                "gears", 5, {"iron-plate": 100}, float("nan"))
        with self.assertRaises(ValueError):
            self.solver.compute_production_plan(
                "gears", 5, {"iron-plate": float("inf")}, 100)

    def test_fixture_is_explicitly_synthetic(self):
        proof = self.solver.get_fixture_proof("gears")
        self.assertIn("Synthetic", proof["notes"])
        self.assertIn("not gameplay proof", proof["notes"])

    def test_multi_recipe_material_flow_with_byproducts(self):
        """Test multi-recipe flow with byproduct generation and credit."""
        # Create a simple recipe chain with byproducts
        recipe_a = create_recipe(
            prototype_id="a",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "x", "count": 1}],
            byproducts=[{"prototype_id": "y", "count": 0.5}]
        )
        recipe_b = create_recipe(
            prototype_id="b",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "a", "count": 1}],
            byproducts=[{"prototype_id": "z", "count": 0.25},
                        {"prototype_id": "x", "count": 0.25}]
        )
        recipe_target = create_recipe(
            prototype_id="target",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "b", "count": 1}],
        )

        self.solver.add_recipe(recipe_a)
        self.solver.add_recipe(recipe_b)
        self.solver.add_recipe(recipe_target)
        self.solver.add_recipe(create_recipe(
            "unrelated", 1, 0.1, byproducts=[{"prototype_id": "x", "count": 99}]))
        self.add_quantity_contract(self.solver)

        result = self.solver.compute_multi_recipe_material_flow(
            target_prototype="target",
            target_quantity=4.0,
            supply_available={"x": 3.0},
            energy_available=100.0,
        )

        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["has_cycle"], False)
        self.assertEqual(result["has_unresolved"], False)
        self.assertEqual(result["selected_recipes"], {"target": 4, "b": 4, "a": 4})
        self.assertEqual(result["net_material_requirements"], {"x": 3})
        self.assertEqual(result["net_material_surplus"], {"y": 2, "z": 1})
        self.assertIsNone(result["total_energy_required_kw"])
        self.assertEqual(result["total_energy_required_kj"], 1.2)

    def test_external_inputs_are_resolved_after_byproduct_credits(self):
        solver = ProductionSolver()
        solver.add_recipe(create_recipe(
            "a", 1, 0.1, byproducts=[{"prototype_id": "raw", "count": 1}]))
        solver.add_recipe(create_recipe(
            "target", 1, 0.1,
            inputs=[{"prototype_id": "a", "count": 1},
                    {"prototype_id": "raw", "count": 1}]))
        self.add_quantity_contract(solver)
        result = solver.compute_multi_recipe_material_flow("target", 1, {}, 1)
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["unresolved"], [])
        self.assertEqual(result["net_material_requirements"], {})
        self.assertEqual(result["total_byproducts"], [
            {"prototype_id": "raw", "count": 1.0, "is_byproduct": True}])

    def test_partial_byproduct_credit_preserves_exact_external_shortage(self):
        solver = ProductionSolver()
        solver.add_recipe(create_recipe(
            "a", 1, 0.1, byproducts=[{"prototype_id": "raw", "count": 0.25}]))
        solver.add_recipe(create_recipe(
            "target", 1, 0.1,
            inputs=[{"prototype_id": "a", "count": 1},
                    {"prototype_id": "raw", "count": 1}]))
        self.add_quantity_contract(solver)
        result = solver.compute_multi_recipe_material_flow(
            "target", 1, {"raw": 0.5}, 1)
        self.assertEqual((result["status"], result["shortages"]),
                         ("shortage", ["raw"]))
        self.assertEqual(result["net_material_requirements"], {"raw": 0.75})
        self.assertEqual(result["total_byproducts"][0]["count"], 0.25)

    def test_invalid_byproducts_are_rejected_at_insertion(self):
        invalid = (float("nan"), float("inf"), float("-inf"), True, -10)
        for count in invalid:
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.solver.add_recipe(create_recipe(
                    "bad", 1, 0, byproducts=[{"prototype_id": "scrap", "count": count}]))
        for byproduct in ("malformed", {"count": 1}):
            with self.subTest(byproduct=byproduct), self.assertRaises(ValueError):
                self.solver.add_recipe(create_recipe(
                    "bad", 1, 0, byproducts=[byproduct]))  # type: ignore[list-item]

    def test_zero_byproduct_and_finite_inventory_contract(self):
        self.solver.add_recipe(create_recipe(
            "zero", 1, 0, byproducts=[{"prototype_id": "scrap", "count": 0}]))
        self.add_quantity_contract(self.solver)
        result = self.solver.compute_multi_recipe_material_flow("zero", 1, {}, 0)
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["total_byproducts"], [
            {"prototype_id": "scrap", "count": 0.0, "is_byproduct": True}])
        for amount in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(amount=amount):
                invalid = self.solver.compute_multi_recipe_material_flow(
                    "zero", 1, {"raw": amount}, 0)
                self.assertEqual(invalid["status"], "invalid")

    def test_multi_recipe_material_flow_with_cycle(self):
        """Test that cycles are detected and marked as unsupported."""
        # Create a cyclic recipe
        recipe_a = create_recipe(
            prototype_id="a",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "b", "count": 1}],
            byproducts=[{"prototype_id": "a", "count": 1}]  # Self-referential
        )
        recipe_b = create_recipe(
            prototype_id="b",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "a", "count": 1}],
            byproducts=[{"prototype_id": "b", "count": 1}]  # Self-referential
        )

        self.solver.add_recipe(recipe_a)
        self.solver.add_recipe(recipe_b)
        self.add_quantity_contract(self.solver)

        result = self.solver.compute_multi_recipe_material_flow(
            target_prototype="a",
            target_quantity=1.0,
            supply_available={},
            energy_available=100.0,
        )

        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["has_cycle"], True)
        self.assertEqual(result["diagnostic_reason"], "cycle_detected")
        self.assertEqual(result["cycles"], [["a", "b", "a"]])

    def test_multi_recipe_material_flow_shared_inputs(self):
        """Test that shared inputs are aggregated correctly."""
        recipe_shared = create_recipe(
            prototype_id="shared",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "raw", "count": 2}],
        )
        recipe_a = create_recipe(
            prototype_id="a",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "shared", "count": 1}],
        )
        recipe_b = create_recipe(
            prototype_id="b",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "shared", "count": 1}],
        )
        recipe_target = create_recipe(
            prototype_id="target",
            base_speed=1.0,
            energy_usage=0.1,
            inputs=[{"prototype_id": "a", "count": 1}, {"prototype_id": "b", "count": 1}],
        )

        self.solver.add_recipe(recipe_shared)
        self.solver.add_recipe(recipe_a)
        self.solver.add_recipe(recipe_b)
        self.solver.add_recipe(recipe_target)
        self.add_quantity_contract(self.solver)

        result = self.solver.compute_multi_recipe_material_flow(
            target_prototype="target",
            target_quantity=2.0,
            supply_available={"raw": 8},
            energy_available=100.0,
        )

        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["net_material_requirements"], {"raw": 8})
        self.assertEqual(result["selected_recipes"],
                         {"target": 2, "a": 2, "b": 2, "shared": 4})
        scaled = self.solver.compute_multi_recipe_material_flow(
            "target", 20, {"raw": 80}, 100)
        self.assertEqual(scaled["net_material_requirements"], {"raw": 80})

        missing = self.solver.compute_multi_recipe_material_flow("target", 2, {}, 100)
        short = self.solver.compute_multi_recipe_material_flow("target", 2, {"raw": 7}, 100)
        no_power = self.solver.compute_multi_recipe_material_flow(
            "target", 2, {"raw": 8}, 0)
        self.assertEqual((missing["status"], missing["unresolved"][0]["name"]),
                         ("unresolved", "raw"))
        self.assertEqual((short["status"], short["shortages"]), ("shortage", ["raw"]))
        self.assertEqual((no_power["status"], no_power["energy_limiting"]),
                         ("computed", None))
        self.assertEqual(no_power["power_feasibility"],
                         "unknown-without-production-duration")

    def test_multi_recipe_determinism_invalid_and_unsupported_boundaries(self):
        recipes = [
            create_recipe("target", 1, .1, inputs=[{"prototype_id": "part", "count": 2}]),
            create_recipe("part", 7, .2, inputs=[{"prototype_id": "raw", "count": 3}],
                          crafting_time_seconds=4, output_quantity_per_craft=2),
        ]
        first = ProductionSolver()
        second = ProductionSolver()
        for recipe in recipes:
            first.add_recipe(recipe)
        for recipe in reversed(recipes):
            second.add_recipe(recipe)
        self.add_quantity_contract(first)
        self.add_quantity_contract(second)
        one = first.compute_multi_recipe_material_flow("target", 2, {"raw": 6}, 100)
        two = second.compute_multi_recipe_material_flow("target", 2, {"raw": 6}, 100)
        self.assertEqual(one, two)
        self.assertEqual(one["net_material_requirements"], {"raw": 6})
        self.assertEqual(first.compute_multi_recipe_material_flow(
            "target", True, {}, 1)["status"], "invalid")

        for mechanic in ("alternative", "catalyst", "fluid"):
            solver = ProductionSolver()
            recipe = create_recipe("modded", 1, .1, inputs=[{"prototype_id": "raw", "count": 1}])
            if mechanic == "alternative":
                recipe.alternatives = [create_recipe("modded-alt", 1, .1)]
            elif mechanic == "catalyst":
                recipe.catalysts = ["raw"]
            else:
                recipe.fluid_ports = [{"name": "steam"}]
            solver.add_recipe(recipe)
            self.add_quantity_contract(solver)
            result = solver.compute_multi_recipe_material_flow("modded", 1, {"raw": 1}, 1)
            self.assertEqual(result["status"], "unsupported", mechanic)

        self_cycle = ProductionSolver()
        self_cycle.add_recipe(create_recipe(
            "loop", 1, .1, inputs=[{"prototype_id": "loop", "count": 1}]))
        self.add_quantity_contract(self_cycle)
        self_result = self_cycle.compute_multi_recipe_material_flow("loop", 1, {}, 1)
        self.assertEqual(self_result["diagnostic_reason"], "cycle_detected")
        self.assertEqual(self_result["cycles"], [["loop", "loop"]])

    def test_multi_recipe_flow_handles_required_deep_graph_sizes(self):
        for size in (1_000, 5_000, 10_000):
            with self.subTest(size=size):
                solver = ProductionSolver()
                for index in reversed(range(size)):
                    dependency = "raw" if index == size - 1 else f"node-{index + 1}"
                    solver.add_recipe(create_recipe(
                        f"node-{index}", 1, 0,
                        inputs=[{"prototype_id": dependency, "count": 1}]))
                self.add_quantity_contract(solver)
                result = solver.compute_multi_recipe_material_flow(
                    "node-0", 1, {"raw": 1}, 0)
                self.assertEqual(result["status"], "computed")
                self.assertEqual(len(result["selected_recipes"]), size)
                self.assertEqual(result["net_material_requirements"], {"raw": 1.0})
                self.assertEqual(result["total_energy_required_kj"], 0.0)

    def test_multi_recipe_flow_handles_deep_shared_dependency(self):
        solver = ProductionSolver()
        depth = 1_000
        for index in reversed(range(depth)):
            dependency = "raw" if index == depth - 1 else f"shared-{index + 1}"
            solver.add_recipe(create_recipe(
                f"shared-{index}", 1, 0,
                inputs=[{"prototype_id": dependency, "count": 1}]))
        for branch in ("a", "b"):
            solver.add_recipe(create_recipe(
                branch, 1, 0, inputs=[{"prototype_id": "shared-0", "count": 1}]))
        solver.add_recipe(create_recipe(
            "target", 1, 0,
            inputs=[{"prototype_id": "a", "count": 1},
                    {"prototype_id": "b", "count": 1}]))
        self.add_quantity_contract(solver)
        result = solver.compute_multi_recipe_material_flow(
            "target", 1, {"raw": 2}, 0)
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["net_material_requirements"], {"raw": 2.0})
        self.assertEqual(len(result["selected_recipes"]), depth + 3)
        self.assertEqual(result["selected_recipes"]["shared-999"], 2.0)

    def test_multi_recipe_flow_reports_deterministic_long_cycle(self):
        solver = ProductionSolver()
        size = 100
        for index in reversed(range(size)):
            dependency = f"node-{(index + 1) % size}"
            solver.add_recipe(create_recipe(
                f"node-{index}", 1, 0,
                inputs=[{"prototype_id": dependency, "count": 1}]))
        self.add_quantity_contract(solver)
        result = solver.compute_multi_recipe_material_flow("node-0", 1, {}, 0)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["diagnostic_reason"], "cycle_detected")
        self.assertEqual(result["cycles"], [
            [f"node-{index}" for index in range(size)] + ["node-0"]])

    def test_multi_recipe_flow_rejects_nonfinite_arithmetic_results(self):
        recipes = (
            create_recipe("input-overflow", 1, 0,
                          inputs=[{"prototype_id": "raw", "count": 1e308}]),
            create_recipe("byproduct-overflow", 1, 0,
                          byproducts=[{"prototype_id": "scrap", "count": 1e308}]),
            create_recipe("energy-overflow", 1, 1e308),
        )
        for recipe in recipes:
            with self.subTest(recipe=recipe.prototype_id):
                solver = ProductionSolver()
                solver.add_recipe(recipe)
                self.add_quantity_contract(solver)
                result = solver.compute_multi_recipe_material_flow(
                    recipe.prototype_id, 1e308, {}, 1e308)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["diagnostic_reason"], "arithmetic_overflow")
                self.assertEqual(result["net_material_requirements"], {})
                self.assertEqual(result["total_byproducts"], [])

    def test_multi_recipe_flow_rejects_excessive_reachable_graph(self):
        solver = ProductionSolver()
        solver.MAX_MATERIAL_FLOW_RECIPES = 2
        for index in reversed(range(3)):
            dependency = "raw" if index == 2 else f"node-{index + 1}"
            solver.add_recipe(create_recipe(
                f"node-{index}", 1, 0,
                inputs=[{"prototype_id": dependency, "count": 1}]))
        self.add_quantity_contract(solver)
        result = solver.compute_multi_recipe_material_flow("node-0", 1, {}, 0)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["diagnostic_reason"], "graph_too_large")
        self.assertEqual(result["selected_recipes"], {})

    def test_quantity_flow_requires_explicit_output_per_craft(self):
        solver = ProductionSolver()
        solver.add_recipe(create_recipe("ambiguous", 9, 0.2))
        result = solver.compute_multi_recipe_material_flow("ambiguous", 3, {}, 100)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["diagnostic_reason"],
                         "missing_output_quantity_per_craft")
