"""Tests for the persistent settings store.

The store is exercised against a temporary file. No credential is written,
printed or read: the tests only check that the store refuses them.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from settings_store import (  # noqa: E402
    FIELDS,
    SECTIONS,
    SettingsError,
    credential_status,
    effective_settings,
    environment_overrides,
    load,
    save,
    update,
    validate_updates,
)


class SettingsStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.path = Path(self._temporary.name) / "settings.json"


class DefaultsTests(SettingsStoreTestCase):
    def test_a_missing_file_yields_the_defaults(self):
        settings = load(self.path)
        self.assertEqual(settings.problems, [])
        self.assertEqual(settings.get("start_maximized"), False)
        self.assertEqual(settings.get("ups_target"), 60)

    def test_every_field_is_in_exactly_one_section(self):
        listed: list[str] = []
        for names in SECTIONS.values():
            listed.extend(names)
        self.assertEqual(sorted(listed), sorted(field.name for field in FIELDS))
        self.assertEqual(len(listed), len(set(listed)))

    def test_every_field_has_a_description(self):
        for field in FIELDS:
            self.assertTrue(field.description, field.name)

    def test_the_ups_target_is_sixty(self):
        settings = load(self.path)
        self.assertEqual(settings.get("ups_target"), 60)

    def test_the_helper_is_read_only_by_default(self):
        settings = load(self.path)
        self.assertTrue(settings.get("helper_read_only"))


class PersistenceTests(SettingsStoreTestCase):
    def test_a_value_survives_a_save_and_a_load(self):
        update({"start_maximized": True, "ups_target": 59}, self.path)
        settings = load(self.path)
        self.assertTrue(settings.get("start_maximized"))
        self.assertEqual(settings.get("ups_target"), 59)

    def test_the_file_is_valid_json_with_a_schema(self):
        update({"theme": "System"}, self.path)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], 1)
        self.assertEqual(document["settings"]["theme"], "System")

    def test_saving_leaves_no_temporary_file_behind(self):
        update({"theme": "System"}, self.path)
        leftovers = [item.name for item in self.path.parent.iterdir()
                     if item.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_a_rejected_change_leaves_the_file_untouched(self):
        update({"theme": "System"}, self.path)
        before = self.path.read_bytes()
        with self.assertRaises(SettingsError):
            update({"ups_target": 9999}, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(load(self.path).get("theme"), "System")

    def test_save_returns_the_written_path(self):
        settings = load(self.path)
        written = save(settings, self.path)
        self.assertEqual(written, self.path)


class ValidationTests(SettingsStoreTestCase):
    def test_an_unknown_setting_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"not_a_setting": 1})

    def test_a_wrong_type_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"ups_target": "fast"})

    def test_a_boolean_must_be_a_boolean(self):
        with self.assertRaises(SettingsError):
            validate_updates({"start_maximized": 1})

    def test_a_number_below_the_minimum_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"ups_target": 1})

    def test_a_number_above_the_maximum_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"history_retention_samples": 10 ** 9})

    def test_a_value_outside_the_choices_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"theme": "Neon"})

    def test_a_choice_from_the_list_is_accepted(self):
        self.assertEqual(
            validate_updates({"theme": "System"}), {"theme": "System"})

    def test_an_oversized_text_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"llm_endpoint": "x" * 5000})

    def test_the_thresholds_have_to_be_ordered(self):
        # A degraded threshold below the recover threshold would make the
        # UPS guard flap, so the relationship is checked.
        settings = load(self.path)
        self.assertLess(
            settings.get("ups_critical_threshold"),
            settings.get("ups_degrade_threshold"))
        self.assertLess(
            settings.get("ups_degrade_threshold"),
            settings.get("ups_recover_threshold"))
        self.assertLessEqual(
            settings.get("ups_recover_threshold"), settings.get("ups_target"))


class SecretRefusalTests(SettingsStoreTestCase):
    def test_a_password_setting_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"rcon_password": "hunter2"})

    def test_an_api_key_setting_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"api_key": "sk-123"})

    def test_a_token_setting_is_refused(self):
        with self.assertRaises(SettingsError):
            validate_updates({"llm_token": "abc"})

    def test_a_token_limit_is_not_a_credential(self):
        # "tokens" as a limit is not a credential. A substring match
        # would refuse these two legitimate settings.
        self.assertEqual(
            validate_updates({"llm_context_tokens": 4096}),
            {"llm_context_tokens": 4096})
        self.assertEqual(
            validate_updates({"llm_max_output_tokens": 1024}),
            {"llm_max_output_tokens": 1024})

    def test_a_stored_credential_is_ignored_on_load(self):
        self.path.write_text(json.dumps({
            "schema": 1,
            "settings": {"rcon_password": "hunter2", "theme": "System"},
        }), encoding="utf-8")
        settings = load(self.path)
        self.assertEqual(settings.get("theme"), "System")
        self.assertTrue(any("credential" in problem
                            for problem in settings.problems))
        self.assertNotIn("hunter2", json.dumps(settings.as_dict()))

    def test_the_credential_status_reports_only_presence(self):
        import os

        previous = os.environ.get("FACTORIO_RCON_PASSWORD")
        os.environ["FACTORIO_RCON_PASSWORD"] = "secret-value"
        try:
            status = credential_status()
        finally:
            if previous is None:
                os.environ.pop("FACTORIO_RCON_PASSWORD", None)
            else:
                os.environ["FACTORIO_RCON_PASSWORD"] = previous
        self.assertTrue(status["rcon_password_present"])
        self.assertNotIn("secret-value", json.dumps(status))


class BrokenFileTests(SettingsStoreTestCase):
    def test_a_file_that_is_not_json_is_reported_and_defaults_are_used(self):
        self.path.write_text("not json at all", encoding="utf-8")
        settings = load(self.path)
        self.assertTrue(settings.problems)
        self.assertEqual(settings.get("ups_target"), 60)

    def test_a_file_that_is_not_an_object_is_reported(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        settings = load(self.path)
        self.assertTrue(settings.problems)

    def test_an_unknown_field_in_the_file_is_ignored_and_reported(self):
        self.path.write_text(json.dumps({
            "schema": 1, "settings": {"mystery": 1}}), encoding="utf-8")
        settings = load(self.path)
        self.assertTrue(any("mystery" in problem for problem in settings.problems))

    def test_an_invalid_value_in_the_file_falls_back_to_the_default(self):
        self.path.write_text(json.dumps({
            "schema": 1, "settings": {"ups_target": "fast"}}), encoding="utf-8")
        settings = load(self.path)
        self.assertEqual(settings.get("ups_target"), 60)
        self.assertTrue(settings.problems)

    def test_a_wrong_schema_is_reported(self):
        self.path.write_text(json.dumps({
            "schema": 99, "settings": {}}), encoding="utf-8")
        settings = load(self.path)
        self.assertTrue(any("schema" in problem for problem in settings.problems))


class EnvironmentTests(SettingsStoreTestCase):
    def test_the_environment_overrides_the_file(self):
        import os

        update({"llm_model": "from-file"}, self.path)
        os.environ["AUTOENGINEER_LLM_MODEL"] = "from-environment"
        try:
            settings = effective_settings(self.path)
            self.assertEqual(settings.get("llm_model"), "from-environment")
        finally:
            os.environ.pop("AUTOENGINEER_LLM_MODEL", None)

    def test_an_invalid_environment_override_is_reported(self):
        import os

        os.environ["AUTOENGINEER_UPS_TARGET"] = "not-a-number"
        try:
            settings = effective_settings(self.path)
            self.assertEqual(settings.get("ups_target"), 60)
            self.assertTrue(any("AUTOENGINEER_UPS_TARGET" in problem
                                for problem in settings.problems))
        finally:
            os.environ.pop("AUTOENGINEER_UPS_TARGET", None)

    def test_the_override_list_is_empty_without_the_environment(self):
        import os

        for name in list(os.environ):
            if name.startswith("AUTOENGINEER_LLM") or name == "AUTOENGINEER_UPS_TARGET":
                os.environ.pop(name, None)
        self.assertEqual(environment_overrides(), {})


class SectionTests(SettingsStoreTestCase):
    def test_a_section_returns_its_own_settings(self):
        settings = load(self.path)
        section = settings.section("Safety")
        self.assertIn("helper_read_only", section)
        self.assertNotIn("ups_target", section)

    def test_an_unknown_section_is_refused(self):
        settings = load(self.path)
        with self.assertRaises(SettingsError):
            settings.section("Nonexistent")


if __name__ == "__main__":
    unittest.main()
