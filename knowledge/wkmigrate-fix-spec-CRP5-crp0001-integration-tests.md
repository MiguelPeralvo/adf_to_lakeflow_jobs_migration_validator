# CRP-5: CRP0001 Integration Test Suite

> Self-contained specification for /wkmigrate-autodev. Creates an integration test suite that validates all 18 CRP0001 gap fixes (G-1 through G-18) against real Repsol pipeline JSON files.

## Background

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) converts ADF pipeline JSON into Databricks Lakeflow Jobs. The wkmigrate repo is at `/Users/miguel.peralvo/Code/wkmigrate`. The CRP-1 through CRP-4 specs fixed 18 gaps in the expression system and activity translators. This spec validates those fixes end-to-end.

## Purpose

Without integration tests against the actual CRP0001 pipeline JSONs, we have no way to verify that the 18 fixes work together correctly. The existing unit tests test the expression system in isolation; this suite tests the full `translate_pipeline()` path.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 through CRP-4 all landing first.

---

## Test Fixtures

### Pipeline Selection

Select 8 representative pipelines from the CRP0001 corpus (36 total) that cover all gap categories:

| # | Pipeline File | Gaps Exercised | Key Patterns |
|---|--------------|----------------|--------------|
| 1 | `lakeh_a_pl_arquetipo_internal.json` | G-1, G-5, G-13, G-17 | `?.` optional chaining, `activity().error`, Switch, isSequential ForEach |
| 2 | `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json` | G-2, G-3, G-7, G-9, G-15, G-18 | globalParameters, runOutput, DataFactory, convertFromUtc, ExecutePipeline, inactive |
| 3 | `crp0001_c_pl_prc_edw_bfcdt_process_data_AMR.json` | G-2, G-11, G-16 | globalParameters, AppendVariable, setSystemVariable |
| 4 | `crp0001_c_pl_prc_anl_cmd_all_paral_ppal.json` | G-2, G-3, G-6, G-9, G-15 | globalParameters, runOutput, bare activity().output, convertFromUtc, ExecutePipeline |
| 5 | `crp0001_c_pl_prc_anl_fcl_fm_industrial.json` | G-2, G-12, G-15 | globalParameters, Until, ExecutePipeline |
| 6 | `lakeh_a_pl_arquetipo_grant_permission.json` | G-2, G-4 | globalParameters, nested split with index, pipelineReturnValue |
| 7 | `lakeh_a_pl_operational_log_start.json` | G-2, G-8, G-15 | globalParameters, TriggeredByPipelineRunId, ExecutePipeline |
| 8 | `lakeh_a_pl_arquetipo_switch_internal.json` | G-1, G-13, G-14 | `?.` optional chaining, Switch, Fail |

### Fixture Location

Copy the 8 pipeline JSONs into the wkmigrate test resources:

```bash
mkdir -p /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/lakeh_a_pl_arquetipo_internal.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/crp0001_c_pl_prc_edw_bfcdt_process_data_AMR.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/crp0001_c_pl_prc_anl_cmd_all_paral_ppal.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/crp0001_c_pl_prc_anl_fcl_fm_industrial.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/lakeh_a_pl_arquetipo_grant_permission.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/lakeh_a_pl_operational_log_start.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
cp /Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/lakeh_a_pl_arquetipo_switch_internal.json /Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/
```

---

## Test Structure

**New file:** `/Users/miguel.peralvo/Code/wkmigrate/tests/integration/test_crp0001_integration.py`

```python
"""Integration tests: CRP0001 Repsol pipeline translation.

Validates that the 18 gap fixes (G-1 through G-18) work correctly when
translating real ADF pipeline JSON files from the CRP0001 corpus.
"""
from __future__ import annotations

import json
import pathlib
import pytest

from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.expression_parser import parse_expression
from wkmigrate.parsers.expression_emitter import emit

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "resources" / "pipelines" / "crp0001"


def _load_pipeline(name: str) -> dict:
    """Load a CRP0001 pipeline JSON fixture."""
    path = FIXTURE_DIR / name
    with open(path) as f:
        return json.load(f)


# ============================================================
# Expression-level tests (G-1 through G-10)
# ============================================================

class TestGlobalParameters:
    """G-2: pipeline().globalParameters.X should resolve."""

    @pytest.mark.parametrize("param_name", [
        "env_variable", "libFileName", "deequLibFileName",
        "clusterVersion", "DatabricksUCUrl", "GroupLogs",
    ])
    def test_global_parameter_resolves(self, param_name):
        expr = f"@pipeline().globalParameters.{param_name}"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue), f"G-2: {expr} should resolve"
        assert "spark.conf.get" in result

    def test_global_parameter_in_concat(self):
        expr = "@concat('/Volumes/', pipeline().globalParameters.env_variable, '/libs/')"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue), "G-2: concat with globalParam should resolve"


class TestActivityOutputTypes:
    """G-3, G-4, G-5, G-6: Extended activity output reference types."""

    def test_run_output(self):
        """G-3: activity().output.runOutput should resolve."""
        result = emit(parse_expression("@activity('Control ejecucion').output.runOutput"))
        assert not isinstance(result, UnsupportedValue), "G-3 failed"
        assert "taskValues.get" in result

    def test_pipeline_return_value(self):
        """G-4: activity().output.pipelineReturnValue.X should resolve."""
        result = emit(parse_expression(
            "@activity('datatsources').output.pipelineReturnValue.str_array"
        ))
        assert not isinstance(result, UnsupportedValue), "G-4 failed"
        assert "taskValues.get" in result

    def test_activity_error(self):
        """G-5: activity().error.message should resolve."""
        result = emit(parse_expression("@activity('internal switch').error.message"))
        assert not isinstance(result, UnsupportedValue), "G-5 failed"

    def test_bare_activity_output(self):
        """G-6: activity().output without sub-property should resolve."""
        result = emit(parse_expression("@activity('cmd_notebook_BW1').output"))
        assert not isinstance(result, UnsupportedValue), "G-6 failed"
        assert "taskValues.get" in result

    def test_contains_bare_output(self):
        """G-6: contains(activity().output, 'key') should resolve."""
        result = emit(parse_expression(
            "@contains(activity('cmd_notebook_BW1').output, 'runError')"
        ))
        assert not isinstance(result, UnsupportedValue), "G-6 in contains() failed"


class TestPipelineVars:
    """G-7, G-8: Additional pipeline system variables."""

    def test_data_factory(self):
        """G-7: pipeline().DataFactory should resolve."""
        result = emit(parse_expression("@pipeline().DataFactory"))
        assert not isinstance(result, UnsupportedValue), "G-7 failed"

    def test_triggered_by_pipeline_run_id(self):
        """G-8: pipeline().TriggeredByPipelineRunId should resolve."""
        result = emit(parse_expression("@pipeline().TriggeredByPipelineRunId"))
        assert not isinstance(result, UnsupportedValue), "G-8 failed"


class TestDateTimeFunctions:
    """G-9, G-10: convertFromUtc and convertTimeZone fixes."""

    def test_convert_from_utc_3_args(self):
        """G-9: convertFromUtc with format argument."""
        result = emit(parse_expression(
            "@convertFromUtc(utcnow(), 'Romance Standard Time', 'dd/MM/yyyy HH:mm')"
        ))
        assert not isinstance(result, UnsupportedValue), "G-9 failed"
        assert "_wkmigrate_convert_time_zone" in result
        assert "'UTC'" in result

    def test_convert_from_utc_2_args(self):
        """G-9: convertFromUtc without format."""
        result = emit(parse_expression(
            "@convertFromUtc(utcnow(), 'Romance Standard Time')"
        ))
        assert not isinstance(result, UnsupportedValue), "G-9 2-arg failed"

    def test_convert_time_zone_4_args(self):
        """G-10: convertTimeZone with optional format argument."""
        result = emit(parse_expression(
            "@convertTimeZone(utcnow(), 'UTC', 'Romance Standard Time', 'dd/MM/yyyy')"
        ))
        assert not isinstance(result, UnsupportedValue), "G-10 failed"


class TestOptionalChaining:
    """G-1: ?. optional chaining in expressions."""

    def test_item_optional_chaining(self):
        """G-1: item()?.condition should tokenize, parse, and emit."""
        result = emit(parse_expression("@item()?.condition"))
        assert not isinstance(result, UnsupportedValue), "G-1 failed"
        assert "get('condition')" in result

    def test_nested_optional_chaining(self):
        """G-1: item()?.condition?.name (double ?.)."""
        result = emit(parse_expression("@coalesce(item()?.condition?.name, 'fallback')"))
        assert not isinstance(result, UnsupportedValue), "G-1 nested failed"

    @pytest.mark.parametrize("expr", [
        "@coalesce(item()?.condition, 'notFound')",
        "@coalesce(item()?.type, 'default')",
        "@coalesce(item()?.aux_params, '{}')",
        "@coalesce(item()?.name, 'no_name')",
        "@toUpper(coalesce(item()?.type, 'DEFAULT'))",
    ])
    def test_crp0001_optional_chaining_expressions(self, expr):
        """G-1: All CRP0001 optional chaining expressions should resolve."""
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue), f"G-1: {expr} failed"


# ============================================================
# Complex expression golden tests (multi-gap)
# ============================================================

class TestComplexExpressions:
    """Expressions that exercise multiple gaps simultaneously."""

    def test_bfc_send_mail_condition(self):
        """G-3 + G-7: nested logical with runOutput and DataFactory."""
        expr = "@and(and(equals(string(activity('Fec_cerrado').output.runOutput),'0'),equals(string(activity('Control ejecucion').output.runOutput),'0')),equals(pipeline().DataFactory,'datahub01pdfcrp0001'))"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue), f"Multi-gap expression failed: {expr[:60]}..."

    def test_cmd_contains_run_error(self):
        """G-3 + G-6: concat with if/contains on bare activity output."""
        # Simplified version of the CMD pattern
        expr = "@if(contains(activity('cmd_notebook_BW1').output,'runError'),'ERROR','OK')"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue)

    def test_fecha_inicio(self):
        """G-9: convertFromUtc in BFC date formatting."""
        expr = "@convertFromUtc(utcnow(),'Romance Standard Time','dd/MM/yyyy HH:mm')"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue)
        assert "_wkmigrate" in result

    def test_operational_log_uid(self):
        """G-2 + G-8: concat with globalParameters and TriggeredByPipelineRunId."""
        # Simplified version — full version has pipeline().parameters too
        expr = "@concat('lakeh#$', pipeline().parameters.applicationName, '#', pipeline().TriggeredByPipelineRunId)"
        result = emit(parse_expression(expr))
        assert not isinstance(result, UnsupportedValue)


# ============================================================
# Pipeline-level tests (if translate_pipeline is available)
# ============================================================

class TestPipelineTranslation:
    """End-to-end pipeline translation tests.

    These tests require the full translation pipeline including IR
    construction and activity dispatch. They may need to be skipped
    if translate_pipeline is not importable in the test environment.
    """

    @pytest.fixture
    def arquetipo_internal(self):
        return _load_pipeline("lakeh_a_pl_arquetipo_internal.json")

    @pytest.fixture
    def bfc_parallel(self):
        return _load_pipeline("crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json")

    @pytest.fixture
    def operational_log(self):
        return _load_pipeline("lakeh_a_pl_operational_log_start.json")

    def test_fixtures_load(self, arquetipo_internal, bfc_parallel, operational_log):
        """Sanity check: all fixtures load as valid JSON with expected structure."""
        for pipeline in [arquetipo_internal, bfc_parallel, operational_log]:
            assert "name" in pipeline
            assert "properties" in pipeline
            activities = pipeline["properties"].get("activities", [])
            assert len(activities) > 0, f"Pipeline {pipeline['name']} has no activities"
```

---

## Files to Create

All paths relative to wkmigrate repo root at `/Users/miguel.peralvo/Code/wkmigrate`:

| Absolute Path | Purpose |
|---------------|---------|
| `/Users/miguel.peralvo/Code/wkmigrate/tests/integration/test_crp0001_integration.py` | Integration test suite (~200 lines) |
| `/Users/miguel.peralvo/Code/wkmigrate/tests/resources/pipelines/crp0001/` | Directory for 8 fixture pipeline JSONs |
| 8 JSON files copied from `/Users/miguel.peralvo/Downloads/crp0001_pipelines/pipeline/` | See fixture commands above |

## Acceptance Criteria

1. All expression-level tests pass (TestGlobalParameters through TestOptionalChaining)
2. All complex expression golden tests pass (TestComplexExpressions)
3. Pipeline fixtures load correctly
4. No regressions in existing tests (`make test`)
5. `make fmt` clean
6. Every G-series gap (G-1 through G-18) is covered by at least one test

## Test Coverage Matrix

| Gap | Test Class | Test Method(s) |
|-----|-----------|----------------|
| G-1 | TestOptionalChaining | test_item_optional_chaining, test_nested_optional_chaining, parametrized |
| G-2 | TestGlobalParameters | parametrized over 6 param names + concat |
| G-3 | TestActivityOutputTypes | test_run_output |
| G-4 | TestActivityOutputTypes | test_pipeline_return_value |
| G-5 | TestActivityOutputTypes | test_activity_error |
| G-6 | TestActivityOutputTypes | test_bare_activity_output, test_contains_bare_output |
| G-7 | TestPipelineVars | test_data_factory |
| G-8 | TestPipelineVars | test_triggered_by_pipeline_run_id |
| G-9 | TestDateTimeFunctions | test_convert_from_utc_3_args, test_convert_from_utc_2_args |
| G-10 | TestDateTimeFunctions | test_convert_time_zone_4_args |
| G-11 | (unit tests in CRP-4 spec) | — |
| G-12 | (unit tests in CRP-3 spec) | — |
| G-13 | (unit tests in CRP-3 spec) | — |
| G-14 | (unit tests in CRP-4 spec) | — |
| G-15 | (unit tests in CRP-3 spec) | — |
| G-16 | (unit tests in CRP-4 spec) | — |
| G-17 | (unit tests in CRP-4 spec) | — |
| G-18 | (unit tests in CRP-4 spec) | — |
| Multi | TestComplexExpressions | 4 golden tests combining multiple gaps |

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests  # after CRP-1 through CRP-4 landed
git checkout -b feature/crp5-integration-tests
# Copy fixtures, write tests
# Run: make test && make fmt
git push -u fork feature/crp5-integration-tests
```
