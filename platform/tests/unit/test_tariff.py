"""Unit tests for tariff management."""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from pathlib import Path

import pandas as pd


@pytest.mark.unit
class TestTariffManager:
    @patch("services.financial.tariff.get_engine")
    def test_get_tariff_found(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute.return_value = [
            ("p1", "fixed", 50.0, date(2025, 1, 1), None, 2.0, "EUR")
        ]
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)
        result = mgr.get_tariff("p1", target_date=date(2025, 6, 1))

        assert result is not None
        assert result["plant_uid"] == "p1"
        assert result["rate"] == 50.0
        assert result["tariff_type"] == "fixed"
        assert result["currency"] == "EUR"
        assert result["escalation_pct"] == 2.0

    @patch("services.financial.tariff.get_engine")
    def test_get_tariff_not_found(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_engine.execute.return_value = []
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)
        result = mgr.get_tariff("nonexistent", target_date=date(2025, 1, 1))

        assert result is None

    @patch("services.financial.tariff.get_engine")
    def test_set_tariff(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)
        mgr.set_tariff("p1", "ppa", 75.0, date(2025, 1, 1), escalation_pct=3.0)

        mock_engine.execute_upsert.assert_called_once()
        call_data = mock_engine.execute_upsert.call_args[0][1]
        assert call_data["rate"] == 75.0
        assert call_data["tariff_type"] == "ppa"
        assert call_data["escalation_pct"] == 3.0

    @patch("services.financial.tariff.get_engine")
    def test_set_tariff_with_end_date(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)
        mgr.set_tariff("p1", "fixed", 40.0, date(2025, 1, 1), end_date=date(2025, 12, 31))

        call_data = mock_engine.execute_upsert.call_args[0][1]
        assert call_data["end_date"] == date(2025, 12, 31)

    @patch("services.financial.tariff.get_engine")
    def test_import_from_csv_file_not_found(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)

        with pytest.raises(FileNotFoundError):
            mgr.import_from_csv("/nonexistent/file.csv")

    @patch("services.financial.tariff.get_engine")
    def test_import_from_csv_missing_columns(self, mock_get_engine, tmp_path):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        # Create CSV with missing required columns
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("col_a,col_b\n1,2\n")

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)

        with pytest.raises(ValueError, match="missing required columns"):
            mgr.import_from_csv(csv_path)

    @patch("services.financial.tariff.get_engine")
    def test_import_from_csv_success(self, mock_get_engine, tmp_path):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = True
        mock_get_engine.return_value = mock_engine

        csv_path = tmp_path / "tariffs.csv"
        csv_path.write_text(
            "plant_uid,tariff_type,rate,start_date\n"
            "p1,fixed,50.0,2025-01-01\n"
            "p2,ppa,75.0,2025-06-01\n"
        )

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)
        count = mgr.import_from_csv(csv_path)

        assert count == 2
        assert mock_engine.execute_upsert.call_count == 2

    @patch("services.financial.tariff.get_engine")
    def test_ensure_table_created(self, mock_get_engine):
        mock_engine = MagicMock()
        mock_engine.table_exists.return_value = False
        mock_get_engine.return_value = mock_engine

        from services.financial.tariff import TariffManager
        mgr = TariffManager(engine=mock_engine)

        mock_engine.execute.assert_called()  # CREATE TABLE was called
