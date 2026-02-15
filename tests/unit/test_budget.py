"""Unit tests for budget comparison service."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestBudgetComparison:
    def test_defaults(self):
        from solar_platform.financial.budget import BudgetComparison
        bc = BudgetComparison(plant_uid="p1", year=2025, month=1)
        assert bc.budget_kwh == 0.0
        assert bc.actual_kwh == 0.0
        assert bc.variance_kwh == 0.0
        assert bc.variance_pct == 0.0
        assert bc.scenario == "base"

    def test_on_track_within_5pct(self):
        from solar_platform.financial.budget import BudgetComparison
        bc = BudgetComparison(
            plant_uid="p1", year=2025, month=1,
            budget_kwh=1000.0, actual_kwh=1040.0,
            variance_kwh=40.0, variance_pct=4.0,
        )
        assert bc.on_track is True

    def test_off_track_over_5pct(self):
        from solar_platform.financial.budget import BudgetComparison
        bc = BudgetComparison(
            plant_uid="p1", year=2025, month=1,
            budget_kwh=1000.0, actual_kwh=800.0,
            variance_kwh=-200.0, variance_pct=-20.0,
        )
        assert bc.on_track is False

    def test_on_track_boundary_5pct(self):
        from solar_platform.financial.budget import BudgetComparison
        bc = BudgetComparison(
            plant_uid="p1", year=2025, month=1,
            variance_pct=5.0,
        )
        assert bc.on_track is True

    def test_on_track_boundary_negative_5pct(self):
        from solar_platform.financial.budget import BudgetComparison
        bc = BudgetComparison(
            plant_uid="p1", year=2025, month=1,
            variance_pct=-5.0,
        )
        assert bc.on_track is True


@pytest.mark.unit
class TestBudgetService:
    @patch("solar_platform.financial.budget.get_engine")
    def test_compare_with_budget(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_engine.table_exists.side_effect = lambda table: {
            "plant_budgets": True,
            "readings": True,
        }.get(table, False)
        # Budget query returns 1000 kWh, actual returns 900 kWh
        mock_engine.execute.side_effect = [
            [(1000.0,)],  # _get_budget
            [(900.0,)],   # _get_actual
        ]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("timestamp",)]
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.budget import BudgetService
        svc = BudgetService(engine=mock_engine)

        # Act
        result = svc.compare("p1", 2025, 1)

        # Assert
        assert result.budget_kwh == 1000.0
        assert result.actual_kwh == 900.0
        assert result.variance_kwh == -100.0
        assert result.variance_pct == pytest.approx(-10.0)

    @patch("solar_platform.financial.budget.get_engine")
    def test_compare_zero_budget(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute.side_effect = [
            [(0.0,)],   # budget = 0
            [(500.0,)], # actual
        ]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("timestamp",)]
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.budget import BudgetService
        svc = BudgetService(engine=mock_engine)

        result = svc.compare("p1", 2025, 1)
        # variance_pct should be 0 when budget is 0 (division guard)
        assert result.variance_pct == 0.0

    @patch("solar_platform.financial.budget.get_engine")
    def test_compare_no_readings_table(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.side_effect = lambda table: table == "plant_budgets"
        mock_engine.execute.return_value = [(500.0,)]
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.budget import BudgetService
        svc = BudgetService(engine=mock_engine)

        result = svc.compare("p1", 2025, 1)
        assert result.actual_kwh == 0.0

    @patch("solar_platform.financial.budget.get_engine")
    def test_set_budget(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.budget import BudgetService
        svc = BudgetService(engine=mock_engine)

        svc.set_budget("p1", 2025, 6, 2000.0)
        mock_engine.execute_upsert.assert_called_once()
        call_args = mock_engine.execute_upsert.call_args
        assert call_args[0][1]["budget_kwh"] == 2000.0
