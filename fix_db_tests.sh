#!/bin/bash

# Fix test_database_manager.py systematically

cd /home/kalle/projects/rawcandle

# Backup the current file
cp tests/test_database_manager.py tests/test_database_manager.py.backup2

# Replace VALUES patterns  
sed -i 's/VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)/VALUES (?, ?, ?, ?, ?, ?, ?, ?)/g' tests/test_database_manager.py

# Create a temporary file with the correct parameter structure
cat > /tmp/fix_params.py << 'EOF'
import re

with open('tests/test_database_manager.py', 'r') as f:
    content = f.read()

# Pattern to match the old parameter structure
old_params = r'''\(\s*
\s*item\["ticker"\],\s*
\s*item\["date"\],\s*
\s*item\["candle_pattern"\],\s*
\s*item\["open_price"\],\s*
\s*item\["high_price"\],\s*
\s*item\["low_price"\],\s*
\s*item\["close_price"\],\s*
\s*item\["volume"\],\s*
\s*item\["pattern_strength"\],\s*
\s*item\["market_cap"\],\s*
\s*item\["sector"\],\s*
\s*\)'''

new_params = '''(
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                )'''

content = re.sub(old_params, new_params, content, flags=re.VERBOSE)

# Fix field name references in assertions
content = content.replace('["candle_pattern"]', '["pattern"]')

with open('tests/test_database_manager.py', 'w') as f:
    f.write(content)
EOF

python /tmp/fix_params.py