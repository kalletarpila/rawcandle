"""
Test Utilities
Apufunktioita testien tukemiseen.
"""

import os
import sqlite3
import tempfile
import shutil
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import Mock, MagicMock
import flet as ft
from contextlib import contextmanager
import time
try:
    import psutil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    from tests import psutil_stub as psutil
import threading
from pathlib import Path


class TestUtils:
    """Yleiset apufunktiot testeille."""

    @staticmethod
    def create_temp_database(schema_sql: str = None) -> str:
        """
        Luo väliaikainen tietokanta.

        Args:
            schema_sql: SQL schema luontiin

        Returns:
            Tietokantatiedoston polku
        """
        fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        if schema_sql:
            conn = sqlite3.connect(temp_path)
            conn.executescript(schema_sql)
            conn.close()

        return temp_path

    @staticmethod
    def cleanup_temp_file(file_path: str) -> None:
        """
        Poista väliaikainen tiedosto.

        Args:
            file_path: Poistettavan tiedoston polku
        """
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except (OSError, PermissionError):
            pass  # Ignore cleanup errors in tests

    @staticmethod
    def count_table_rows(db_path: str, table_name: str) -> int:
        """
        Laske taulun rivien määrä.

        Args:
            db_path: Tietokantapolku
            table_name: Taulun nimi

        Returns:
            Rivien määrä
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    @staticmethod
    def execute_sql(db_path: str, sql: str, params: tuple = ()) -> List[tuple]:
        """
        Suorita SQL kysely.

        Args:
            db_path: Tietokantapolku
            sql: SQL kysely
            params: Kyselyparametrit

        Returns:
            Tulosrivit
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.commit()
        conn.close()
        return results


class MockFactory:
    """Factory mock-objektien luomiseen."""

    @staticmethod
    def create_mock_page() -> Mock:
        """
        Luo mock Flet Page objekti.

        Returns:
            Mock page objekti
        """
        mock_page = Mock(spec=ft.Page)
        mock_page.width = 1200
        mock_page.height = 800
        mock_page.theme = Mock()
        mock_page.theme.color_scheme = Mock()
        mock_page.theme.color_scheme.primary = ft.colors.BLUE
        mock_page.add = Mock()
        mock_page.update = Mock()
        mock_page.clean = Mock()
        mock_page.go = Mock()
        mock_page.route = "/"
        mock_page.session = Mock()
        mock_page.client_storage = Mock()

        # Dialog mock
        mock_page.dialog = None
        mock_page.open_dlg = Mock()
        mock_page.close_dlg = Mock()

        return mock_page

    @staticmethod
    def create_mock_progress_dialog() -> Mock:
        """
        Luo mock progress dialog.

        Returns:
            Mock progress dialog
        """
        mock_dialog = Mock()
        mock_dialog.open = False
        mock_dialog.title = Mock()
        mock_dialog.content = Mock()
        mock_dialog.actions = []

        # Progress-specific methods
        mock_dialog.update_progress = Mock()
        mock_dialog.set_text = Mock()
        mock_dialog.close = Mock()

        return mock_dialog

    @staticmethod
    def create_mock_database_manager() -> Mock:
        """
        Luo mock DatabaseManager.

        Returns:
            Mock DatabaseManager objekti
        """
        mock_db = Mock()

        # Standard methods
        mock_db.get_all_findings.return_value = []
        mock_db.insert_finding.return_value = True
        mock_db.delete_finding.return_value = True
        mock_db.update_finding.return_value = True
        mock_db.search_findings.return_value = []
        mock_db.get_findings_by_pattern.return_value = []
        mock_db.get_findings_by_date_range.return_value = []
        mock_db.get_statistics.return_value = {}
        mock_db.is_connected.return_value = True
        mock_db.close.return_value = None

        return mock_db

    @staticmethod
    def create_mock_analysis_engine() -> Mock:
        """
        Luo mock AnalysisEngine.

        Returns:
            Mock AnalysisEngine objekti
        """
        mock_engine = Mock()

        # Pattern detection methods
        mock_engine.detect_doji.return_value = False
        mock_engine.detect_hammer.return_value = False
        mock_engine.detect_shooting_star.return_value = False
        mock_engine.detect_engulfing.return_value = False
        mock_engine.analyze_batch.return_value = []
        mock_engine.calculate_signal_strength.return_value = 0.5

        return mock_engine


class PerformanceMonitor:
    """Suorituskyvyn seuranta testeissä."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.start_memory = None
        self.end_memory = None
        self.process = psutil.Process()

    def start_monitoring(self) -> None:
        """Aloita seuranta."""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB

    def stop_monitoring(self) -> Dict[str, float]:
        """
        Lopeta seuranta ja palauta tulokset.

        Returns:
            Suorituskykytiedot
        """
        self.end_time = time.time()
        self.end_memory = self.process.memory_info().rss / 1024 / 1024  # MB

        return {
            "execution_time": self.end_time - self.start_time,
            "memory_used": self.end_memory - self.start_memory,
            "peak_memory": self.end_memory,
            "cpu_percent": self.process.cpu_percent(),
        }

    @contextmanager
    def monitor(self):
        """Context manager seurantaan."""
        self.start_monitoring()
        try:
            yield self
        finally:
            results = self.stop_monitoring()
            self.results = results


class ConcurrentTestRunner:
    """Samanaikaisten testien ajaminen."""

    def __init__(self, num_threads: int = 5):
        self.num_threads = num_threads
        self.results = []
        self.errors = []
        self.lock = threading.Lock()

    def run_concurrent_test(
        self, test_func: Callable, args_list: List[tuple]
    ) -> List[Any]:
        """
        Aja testi samanaikaisesti useissa säikeissä.

        Args:
            test_func: Testifunktio
            args_list: Lista argumentteja kullekin säikeelle

        Returns:
            Lista tuloksia
        """
        threads = []

        def worker(args):
            try:
                result = test_func(*args)
                with self.lock:
                    self.results.append(result)
            except Exception as e:
                with self.lock:
                    self.errors.append(e)

        # Käynnistä säikeet
        for args in args_list[: self.num_threads]:
            thread = threading.Thread(target=worker, args=(args,))
            threads.append(thread)
            thread.start()

        # Odota säikeiden valmistumista
        for thread in threads:
            thread.join()

        return self.results


class DatabaseTestHelper:
    """Apuluokka tietokantatesteille."""

    @staticmethod
    def verify_schema(db_path: str, expected_tables: List[str]) -> bool:
        """
        Tarkista tietokannan schema.

        Args:
            db_path: Tietokantapolku
            expected_tables: Odotetut taulut

        Returns:
            True jos schema on oikea
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Hae taulujen nimet
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual_tables = [row[0] for row in cursor.fetchall()]

        conn.close()

        # Tarkista että kaikki odotetut taulut löytyvät
        return all(table in actual_tables for table in expected_tables)

    @staticmethod
    def insert_test_data(db_path: str, table: str, data: List[Dict]) -> int:
        """
        Lisää testidata tauluun.

        Args:
            db_path: Tietokantapolku
            table: Taulun nimi
            data: Lista dataa

        Returns:
            Lisättyjen rivien määrä
        """
        if not data:
            return 0

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Rakenna INSERT SQL
        columns = list(data[0].keys())
        placeholders = ", ".join(["?" for _ in columns])
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"

        # Lisää data
        rows_inserted = 0
        for row in data:
            cursor.execute(sql, [row[col] for col in columns])
            rows_inserted += 1

        conn.commit()
        conn.close()

        return rows_inserted


class AssertionHelpers:
    """Mukautetut assertion-apufunktiot."""

    @staticmethod
    def assert_performance(
        execution_time: float, max_time: float, operation: str = "operation"
    ):
        """
        Tarkista suoritusaika.

        Args:
            execution_time: Toteutunut aika
            max_time: Maksimiaika
            operation: Operaation nimi
        """
        assert (
            execution_time <= max_time
        ), f"{operation} took {execution_time:.3f}s, expected max {max_time:.3f}s"

    @staticmethod
    def assert_memory_usage(
        memory_mb: float, max_memory_mb: float, operation: str = "operation"
    ):
        """
        Tarkista muistin käyttö.

        Args:
            memory_mb: Muistin käyttö MB
            max_memory_mb: Maksimi muisti MB
            operation: Operaation nimi
        """
        assert (
            memory_mb <= max_memory_mb
        ), f"{operation} used {memory_mb:.1f}MB memory, expected max {max_memory_mb:.1f}MB"

    @staticmethod
    def assert_pattern_detected(
        pattern_result: Dict, expected_pattern: str, min_strength: float = 0.0
    ):
        """
        Tarkista kynttiläkuvion tunnistus.

        Args:
            pattern_result: Tunnistustulos
            expected_pattern: Odotettu kuvio
            min_strength: Minimivahvuus
        """
        assert pattern_result is not None, "Pattern detection returned None"
        assert (
            pattern_result.get("pattern") == expected_pattern
        ), f"Expected pattern '{expected_pattern}', got '{pattern_result.get('pattern')}'"
        assert (
            pattern_result.get("signal_strength", 0) >= min_strength
        ), f"Signal strength {pattern_result.get('signal_strength')} below minimum {min_strength}"


# Apufunktioita testitiedostojen kanssa työskentelyyn
def get_test_data_path(filename: str) -> str:
    """Hae testidatatiedoston polku."""
    test_dir = Path(__file__).parent
    return str(test_dir / "data" / filename)


def ensure_test_data_dir() -> str:
    """Varmista että testidatakansio on olemassa."""
    test_dir = Path(__file__).parent
    data_dir = test_dir / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir)


# Decorator apufunktioita
def slow_test(func):
    """Merkitse testi hitaaksi."""
    import pytest

    return pytest.mark.slow(func)


def requires_database(func):
    """Merkitse testi tietokantaa vaativaksi."""
    import pytest

    return pytest.mark.database(func)


def integration_test(func):
    """Merkitse integraatiotestiksi."""
    import pytest

    return pytest.mark.integration(func)


def performance_test(func):
    """Merkitse suorituskykytestiksi."""
    import pytest

    return pytest.mark.slow(pytest.mark.performance(func))


if __name__ == "__main__":
    """Testaa utility-funktiot."""
    print("🧪 Testataan test utilities...")

    # Testaa temp database
    temp_db = TestUtils.create_temp_database()
    print(f"✅ Temp database luotu: {temp_db}")

    # Testaa mock factory
    mock_page = MockFactory.create_mock_page()
    print(f"✅ Mock page luotu: {type(mock_page)}")

    # Testaa performance monitor
    monitor = PerformanceMonitor()
    with monitor.monitor():
        time.sleep(0.1)  # Simuloi työtä
    print(f"✅ Performance monitoring: {monitor.results}")

    # Siivoa
    TestUtils.cleanup_temp_file(temp_db)
    print("✅ Cleanup suoritettu")

    print("\n🎯 Test utilities toimivat!")
