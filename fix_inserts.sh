#!/bin/bash

# Skripti joka korjaa test_database_manager.py INSERT lausekkeet

FILE="tests/test_database_manager.py"

# Korvaa INSERT lausekkeet ja niiden parametrit
sed -i '
/INSERT INTO analysis_findings/,/VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)/ {
    s/(ticker, date, candle_pattern, open_price, high_price, low_price,.*/(ticker, date, pattern, signal_strength, price, volume, description, analysis_date)/
    s/VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)/VALUES (?, ?, ?, ?, ?, ?, ?, ?)/
}
' "$FILE"

# Korvaa parametrilistoja
sed -i '
/item\["ticker"\],/,/item\["sector"\],/ {
    s/item\["candle_pattern"\],/item["candle_pattern"],  # pattern/
    s/item\["open_price"\],//
    s/item\["high_price"\],//
    s/item\["low_price"\],//
    s/item\["close_price"\],/item["close_price"],  # price/
    s/item\["volume"\],/item["volume"],/
    s/item\["pattern_strength"\],/item["pattern_strength"],  # signal_strength/
    s/item\["market_cap"\],/f"Test pattern {item['"'"'candle_pattern'"'"']}", # description/
    s/item\["sector"\],/"2024-01-01T00:00:00",  # analysis_date/
}
' "$FILE"

echo "Korjaukset tehty!"