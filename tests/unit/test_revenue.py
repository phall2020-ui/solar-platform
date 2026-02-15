"""Unit tests for revenue calculations."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.mark.unit
class TestTariffType:
    def test_fixed(self):
        from solar_platform.financial.revenue import TariffType
        assert TariffType.FIXED == "fixed"

    def test_time_of_use(self):
        from solar_platform.financial.revenue import TariffType
        assert TariffType.TIME_OF_USE == "time_of_use"

    def test_fit(self):
        from solar_platform.financial.revenue import TariffType
        assert TariffType.FIT == "fit"

    def test_ppa(self):
        from solar_platform.financial.revenue import TariffType
        assert TariffType.PPA == "ppa"


@pytest.mark.unit
class TestRevenueResult:
    def test_defaults(self):
        from solar_platform.financial.revenue import RevenueResult, TariffType
        r = RevenueResult(plant_uid="p1", year=2025, month=1)
        assert r.generation_mwh == 0.0
        assert r.revenue == 0.0
        assert r.tariff_type == TariffType.FIXED
        assert r.currency == "EUR"
        assert r.metadata == {}

    def test_custom_values(self):
        from solar_platform.financial.revenue import RevenueResult, TariffType
        r = RevenueResult(
            plant_uid="p1", year=2025, month=6,
            generation_mwh=500.0, tariff_per_mwh=50.0,
            revenue=25000.0, tariff_type=TariffType.PPA,
            currency="USD",
        )
        assert r.generation_mwh == 500.0
        assert r.revenue == 25000.0
        assert r.currency == "USD"


@pytest.mark.unit
class TestRevenueService:
    @patch("services.financial.revenue.get_engine")
    def test_calculate_monthly_basic(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        # Simulate 500,000 kWh generation
        mock_engine.execute.return_value = [(500_000.0,)]
        mock_get_engine.return_value = mock_engine
        # Resolve ts column
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("timestamp",)]
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)

        from solar_platform.financial.revenue import RevenueService
        svc = RevenueService(engine=mock_engine)

        # Act
        result = svc.calculate_monthly("p1", 2025, 6, tariff_per_mwh=50.0)

        # Assert
        assert result.plant_uid == "p1"
        assert result.generation_mwh == 500.0  # 500000/1000
        assert result.revenue == 25000.0  # 500 * 50

    @patch("services.financial.revenue.get_engine")
    def test_calculate_monthly_zero_generation(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute.return_value = [(0.0,)]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("timestamp",)]
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.revenue import RevenueService
        svc = RevenueService(engine=mock_engine)

        result = svc.calculate_monthly("p1", 2025, 1, tariff_per_mwh=100.0)
        assert result.revenue == 0.0
        assert result.generation_mwh == 0.0

    @patch("services.financial.revenue.get_engine")
    def test_calculate_monthly_no_readings_table(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = False
        mock_engine.execute.return_value = [(None,)]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.revenue import RevenueService
        svc = RevenueService(engine=mock_engine)

        result = svc.calculate_monthly("p1", 2025, 1, tariff_per_mwh=50.0)
        assert result.generation_mwh == 0.0

    @patch("services.financial.revenue.get_engine")
    def test_portfolio_summary_no_plants(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = False
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.revenue import RevenueService
        svc = RevenueService(engine=mock_engine)

        results = svc.portfolio_summary(2025, 1)
        assert results == []

    @patch("services.financial.revenue.get_engine")
    def test_calculate_monthly_preserves_tariff_type(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute.return_value = [(100_000.0,)]
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [("timestamp",)]
        mock_engine.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_engine.return_value = mock_engine

        from solar_platform.financial.revenue import RevenueService, TariffType
        svc = RevenueService(engine=mock_engine)

        result = svc.calculate_monthly("p1", 2025, 3, 80.0, tariff_type=TariffType.PPA)
        assert result.tariff_type == TariffType.PPA
