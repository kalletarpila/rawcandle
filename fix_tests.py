#!/usr/bin/env python3
"""
Script to fix all database test INSERT statements to use correct schema
"""

import re


def fix_test_file():
    """Fix the test_database_manager.py file"""

    file_path = "tests/test_database_manager.py"

    with open(file_path, "r") as f:
        content = f.read()

    # Pattern to match INSERT statements
    old_pattern = r"""INSERT INTO analysis_findings \s*
                \(ticker, date, candle_pattern, open_price, high_price, low_price,\s*
                 close_price, volume, pattern_strength, market_cap, sector\)\s*
                VALUES \(\?, \?, \?, \?, \?, \?, \?, \?, \?, \?, \?\)"""

    new_pattern = """INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""

    # Replace INSERT pattern
    content = re.sub(old_pattern, new_pattern, content, flags=re.VERBOSE)

    # Fix the parameter tuples
    old_param_pattern = r"""\(\s*
                    item\["ticker"\],\s*
                    item\["date"\],\s*
                    item\["candle_pattern"\],\s*
                    item\["open_price"\],\s*
                    item\["high_price"\],\s*
                    item\["low_price"\],\s*
                    item\["close_price"\],\s*
                    item\["volume"\],\s*
                    item\["pattern_strength"\],\s*
                    item\["market_cap"\],\s*
                    item\["sector"\],\s*
                \)"""

    new_param_pattern = """(
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # candle_pattern mappaa pattern kenttään
                    item["pattern_strength"],  # pattern_strength mappaa signal_strength kenttään
                    item["close_price"],  # close_price mappaa price kenttään
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                )"""

    content = re.sub(old_param_pattern, new_param_pattern, content, flags=re.VERBOSE)

    # Fix field name references in assertions
    content = content.replace('["candle_pattern"]', '["pattern"]')
    content = content.replace('["pattern_strength"]', '["signal_strength"]')

    with open(file_path, "w") as f:
        f.write(content)

    print("Fixed test_database_manager.py")


if __name__ == "__main__":
    fix_test_file()
