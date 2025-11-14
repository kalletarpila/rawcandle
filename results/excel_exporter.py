"""
Excel-vienti results_data taulusta.

Vie results_data taulun tiedot Excel-tiedostoon samassa muodossa
kuin alkuperäinen generate_results.py ja liittää uudet feature-sarakkeet
85. kolumnista eteenpäin.
"""

import logging
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from analysis.database_manager import DatabaseManager


class ExcelExporter:
    """Vie results_data Excel-tiedostoon."""

    # Pattern mappaus (numero -> nimi)
    PATTERN_NAMES = {
        0: "downtrend",
        1: "Hammer",
        2: "Bullish Engulfing",
        3: "Piercing Pattern",
        4: "Three White Soldiers",
        5: "Morning Star",
        6: "Dragonfly Doji",
        7: "Bullish Divergence",
        8: "Bearish Divergence",
    }

    BASE_HEADERS = [
        "osake",
        "date",
        "kynttila",
        "vahvuus",
        "t_1_alin",
        "t_1_ylin",
        "t_1_bodi",
        "t_1_bodi_colour",
        "t0_alin",
        "t0_ylin",
        "t0_bodi",
        "t0_bodi_colour",
        "t1_alin",
        "t1_ylin",
        "t1_bodi",
        "t1_bodi_colour",
        "t_2",
        "t_5",
        "t_10",
        "t_15",
        "t_20",
        "t_2_hajonta",
        "t_5_hajonta",
        "t_10_hajonta",
        "t_15_hajonta",
        "t_20_hajonta",
        "t2",
        "t5",
        "t10",
        "t20",
        "t_2_volyymi",
        "t_5_volyymi",
        "t_10_volyymi",
        "t_15_volyymi",
        "t_20_volyymi",
        "t0_volyymi",
        "t2_volyymi",
        "t5_volyymi",
        "t10_volyymi",
        "t20_volyymi",
        "t_2_5p_liukuva",
        "t_2_10p_liukuva",
        "t_2_20p_liukuva",
        "t_5_5p_liukuva",
        "t_5_10p_liukuva",
        "t_5_20p_liukuva",
        "t_10_5p_liukuva",
        "t_10_10p_liukuva",
        "t_10_20p_liukuva",
        "t_15_5p_liukuva",
        "t_15_10p_liukuva",
        "t_15_20p_liukuva",
        "t_20_5p_liukuva",
        "t_20_10p_liukuva",
        "t_20_20p_liukuva",
        "t0_50p_liukuva",
        "t0_200p_liukuva",
        "SPX_0",
        "SPX_2",
        "SPX_5",
        "SPX_10",
        "SPX_15",
        "SPX_20",
        "SPX2",
        "SPX5",
        "SPX10",
        "SPX15",
        "SPX20",
        "NDX_0",
        "NDX_2",
        "NDX_5",
        "NDX_10",
        "NDX_15",
        "NDX_20",
        "NDX2",
        "NDX5",
        "NDX10",
        "NDX15",
        "NDX20",
        "RSI14_t0",
        "t0_close_norm",
        "Bearish Divergence",
        "Bullish Divergence",
        "weekday",
    ]

    NEW_FEATURE_HEADERS = [
        "RSI_slope_5",
        "Price_slope_5",
        "Price_slope_10",
        "Price_acceleration_5_10",
        "Volatility_ratio_10_20",
        "Gap_down_strength",
        "Body_ratio",
        "Shadow_ratio",
        "SPX_volatility_10",
        "NDX_volatility_10",
        "Volume_impulse",
        "Reversal_Context_Score",
    ]

    HEADERS = BASE_HEADERS + NEW_FEATURE_HEADERS
    NON_ROUNDED_HEADERS = {
        "t_1_bodi_colour",
        "t0_bodi_colour",
        "t1_bodi_colour",
        "weekday",
    }

    def __init__(self, db_path: str = "analysis.db"):
        """
        Alusta exporter.

        Args:
            db_path: Polku analysis.db tietokantaan
        """
        self.db_path = db_path
        self.db_manager = DatabaseManager(db_path)
        self.logger = logging.getLogger(__name__)

    def export_to_excel(
        self,
        output_path: str,
        selected_patterns: Optional[list] = None,
        ticker_filter: Optional[list] = None,
        id_filter: Optional[list] = None,
        progress_callback=None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        downtrend_only: bool = False,
    ) -> tuple[bool, str]:
        """
        Vie results_data Excel-tiedostoon.

        Args:
            output_path: Polku luotavaan Excel-tiedostoon
            selected_patterns: Lista pattern-numeroita joita viedään (None = kaikki)
            ticker_filter: Lista tickereistä joita viedään (None = kaikki)
            id_filter: Lista result ID:istä joita viedään (None = kaikki)
            progress_callback: Callback(current, total) -> bool (True = keskeytä)
            start_date: ISO-päivä (YYYY-MM-DD) alarajana (None = ei rajaa)
            end_date: ISO-päivä (YYYY-MM-DD) ylärajana (None = ei rajaa)
            downtrend_only: Jos True, vie vain downtrend-mallin rivit

        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Hae data tietokannasta
            all_results = self.db_manager.get_results_data()

            if not all_results:
                return (
                    False,
                    "Ei tuloksia vietäväksi. Generoi ensin tulokset tietokantaan.",
                )

            # Suodata ID:illä ensin (ensisijainen suodatin)
            if id_filter is not None:
                id_set = set(id_filter)
                results = [r for r in all_results if r.get("id") in id_set]
            else:
                results = all_results

                # Suodata patterneilla jos annettu (vain jos ei ID-suodatusta)
                if selected_patterns is not None:
                    results = [
                        r for r in results if r["candle_pattern"] in selected_patterns
                    ]

                # Suodata tickereillä jos annettu (vain jos ei ID-suodatusta)
                if ticker_filter is not None:
                    results = [r for r in results if r["ticker"] in ticker_filter]

            if downtrend_only:
                results = [
                    r for r in results if r.get("candle_pattern") == 0
                ]

            if start_date or end_date:
                def in_date_range(date_value: Optional[str]) -> bool:
                    if not date_value:
                        return False
                    value = str(date_value)
                    if start_date and value < start_date:
                        return False
                    if end_date and value > end_date:
                        return False
                    return True

                results = [r for r in results if in_date_range(r.get("date"))]

            if not results:
                return False, "Valituilla suodattimilla ei löytynyt tuloksia."

            self.logger.info(f"Exporting {len(results)} results to Excel")

            # Luo Excel-tiedosto
            wb = Workbook()
            ws = wb.active
            ws.title = "Kynttilätulokset"

            # Otsikkorivi (84 saraketta - samat kuin generate_results.py)
            headers = self.HEADERS

            # Tyylitys otsikoille
            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill(
                start_color="366092", end_color="366092", fill_type="solid"
            )

            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num)
                cell.value = header
                cell.font = header_font
                cell.fill = header_fill

            # Lisää data
            total_rows = len(results)
            skipped_rows = 0
            written_rows = 0

            for row_num, result in enumerate(results, 2):
                # Tarkista keskeytys joka 100. rivi
                if progress_callback and (row_num - 2) % 100 == 0:
                    cancelled = progress_callback(row_num - 2, total_rows)
                    if cancelled:
                        self.logger.info(
                            f"Excel export cancelled at row {row_num - 2}/{total_rows}"
                        )
                        return False, f"Vienti keskeytetty ({row_num - 2} riviä viety)"

                # Käytä pattern numeroa (SPSS-yhteensopivuus)
                pattern_num = result.get("candle_pattern", 0)

                # Rakenna rivi (84 saraketta)
                row_data = [
                    result.get("ticker"),
                    result.get("date"),
                    pattern_num,  # Numerokoodi nimen sijasta
                    result.get("signal_strength"),
                    result.get("t_1_alin"),
                    result.get("t_1_ylin"),
                    result.get("t_1_bodi"),
                    result.get("t_1_bodi_colour"),
                    result.get("t0_alin"),
                    result.get("t0_ylin"),
                    result.get("t0_bodi"),
                    result.get("t0_bodi_colour"),
                    result.get("t1_alin"),
                    result.get("t1_ylin"),
                    result.get("t1_bodi"),
                    result.get("t1_bodi_colour"),
                    result.get("t_2"),
                    result.get("t_5"),
                    result.get("t_10"),
                    result.get("t_15"),
                    result.get("t_20"),
                    result.get("t_2_hajonta"),
                    result.get("t_5_hajonta"),
                    result.get("t_10_hajonta"),
                    result.get("t_15_hajonta"),
                    result.get("t_20_hajonta"),
                    result.get("t2"),
                    result.get("t5"),
                    result.get("t10"),
                    result.get("t20"),
                    result.get("t_2_volyymi"),
                    result.get("t_5_volyymi"),
                    result.get("t_10_volyymi"),
                    result.get("t_15_volyymi"),
                    result.get("t_20_volyymi"),
                    result.get("t0_volyymi"),
                    result.get("t2_volyymi"),
                    result.get("t5_volyymi"),
                    result.get("t10_volyymi"),
                    result.get("t20_volyymi"),
                    result.get("t_2_5p_liukuva"),
                    result.get("t_2_10p_liukuva"),
                    result.get("t_2_20p_liukuva"),
                    result.get("t_5_5p_liukuva"),
                    result.get("t_5_10p_liukuva"),
                    result.get("t_5_20p_liukuva"),
                    result.get("t_10_5p_liukuva"),
                    result.get("t_10_10p_liukuva"),
                    result.get("t_10_20p_liukuva"),
                    result.get("t_15_5p_liukuva"),
                    result.get("t_15_10p_liukuva"),
                    result.get("t_15_20p_liukuva"),
                    result.get("t_20_5p_liukuva"),
                    result.get("t_20_10p_liukuva"),
                    result.get("t_20_20p_liukuva"),
                    result.get("t0_50p_liukuva"),
                    result.get("t0_200p_liukuva"),
                    result.get("SPX_0"),
                    result.get("SPX_2"),
                    result.get("SPX_5"),
                    result.get("SPX_10"),
                    result.get("SPX_15"),
                    result.get("SPX_20"),
                    result.get("SPX2"),
                    result.get("SPX5"),
                    result.get("SPX10"),
                    result.get("SPX15"),
                    result.get("SPX20"),
                    result.get("NDX_0"),
                    result.get("NDX_2"),
                    result.get("NDX_5"),
                    result.get("NDX_10"),
                    result.get("NDX_15"),
                    result.get("NDX_20"),
                    result.get("NDX2"),
                    result.get("NDX5"),
                    result.get("NDX10"),
                    result.get("NDX15"),
                    result.get("NDX20"),
                    result.get("RSI14_t0"),
                    result.get("t0_close_norm"),
                    result.get("bearish_divergence"),
                    result.get("bullish_divergence"),
                    result.get("weekday"),
                ]
                row_data.extend(
                    [result.get(col) for col in self.NEW_FEATURE_HEADERS]
                )

                # Tarkista että KAIKISSA sarakkeissa on data (ei None-arvoja)
                base_values = row_data[: len(self.BASE_HEADERS)]
                if None in base_values:
                    skipped_rows += 1
                    continue  # Skipppaa tämä rivi

                # Kirjoita rivi (käytä written_rows laskuria rivin numeroinnissa)
                written_rows += 1
                actual_row = written_rows + 1  # +1 koska otsikkorivi on rivi 1

                for col_num, (header, value) in enumerate(
                    zip(headers, row_data), 1
                ):
                    # Pyöristä REAL-luvut 2 desimaaliin
                    if isinstance(value, (int, float)) and value is not None:
                        # Älä pyöristä kokonaislukuja (colour, weekday)
                        if header in self.NON_ROUNDED_HEADERS:
                            ws.cell(row=actual_row, column=col_num, value=value)
                        else:
                            # Pyöristä muut numeeriset arvot 2 desimaaliin
                            ws.cell(
                                row=actual_row, column=col_num, value=round(value, 2)
                            )
                    else:
                        ws.cell(row=actual_row, column=col_num, value=value)

            # Automaattinen sarakeleveys
            for col_num in range(1, len(headers) + 1):
                column_letter = get_column_letter(col_num)
                max_length = 0

                for cell in ws[column_letter]:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass

                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column_letter].width = adjusted_width

            # Tallenna
            wb.save(output_path)

            # Luo viesti
            message = f"Viety {written_rows} riviä Exceliin"
            if skipped_rows > 0:
                message += (
                    f" ({skipped_rows} riviä ohitettu puuttuvien tietojen vuoksi)"
                )

            self.logger.info(f"Excel file saved: {output_path} - {message}")
            return True, message

        except Exception as e:
            self.logger.error(f"Export to Excel failed: {e}")
            return False, f"Excel-vienti epäonnistui: {e}"


if __name__ == "__main__":
    # Testi
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    exporter = ExcelExporter("analysis.db")
    success, msg = exporter.export_to_excel("test_results.xlsx")
    print(f"Success: {success}")
    print(f"Message: {msg}")
