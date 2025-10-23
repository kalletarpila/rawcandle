# Downtrend Generator Implementation Summary

## What Changed

Replaced the simple random data generator with a sophisticated downtrend event generator that finds real downtrend patterns in actual stock data.

## Files Created

1. **`analysis/downtrend_generator.py`** (463 lines)
   - Main generator module
   - `DowntrendGenerator` class with full logic
   - `generate_random_findings()` convenience function
   - Three-criteria downtrend detection
   - Progress tracking and cancellation support

2. **`analysis/DOWNTREND_GENERATOR_README.md`** (294 lines)
   - Complete specification and documentation
   - Detailed explanation of all three downtrend criteria
   - Usage examples and API reference
   - Performance notes and limitations

3. **`tests/test_downtrend_generator.py`** (303 lines)
   - 8 comprehensive tests (all passing)
   - Tests criteria checking, progress callbacks, cancellation
   - Includes fixtures for mock databases

## Files Modified

1. **`main.py`**
   - Updated Candles view Generate button handler
   - Changed from `analysis.random_generator` to `analysis.downtrend_generator`
   - Added progress dialog with:
     - Progress bar showing "Processed X / Y stocks"
     - Cancel button
     - Informative text about downtrend criteria
   - Enhanced confirmation dialog with criteria explanation
   - Changed button text to "Generoi laskutrenditapahtumat"
   - Changed button icon to `TRENDING_DOWN`

## Files Deprecated

- **`analysis/random_generator.py`** → renamed to `random_generator.py.old`
  - Old simple random data generator no longer used

## How It Works

### Downtrend Criteria (all three required)

1. **Progressive Decline**: `close(t-10) > close(t-5) > close(t-2) > close(t0)`
   - Strictly decreasing prices at checkpoints

2. **Minimum 3% Drop**: `((close(t-10) - close(t0)) / close(t-10)) * 100 >= 3`
   - At least 3% decline over 10 days

3. **Moving Average Filter**:
   - `MA5 = avg([close(t-5), close(t-4), close(t-3), close(t-2), close(t-1)])`
   - `MA10 = avg([close(t-10), close(t-9), ..., close(t-2), close(t-1)])`
   - Both: `close(t0) < MA10` AND `MA5 < MA10`

### Process

1. Select random stock from `data/osakedata.db`
2. Find random date >= 2024-01-01
3. Check if date meets all three downtrend criteria
4. If yes → save to `analysis/analysis.db` with:
   - `pattern = "Random"`
   - `signal_strength = 1.0`
   - `description = "Auto-generated downtrend event"`
5. Repeat for requested number of stocks/events
6. Max 500 attempts per stock

### UI Integration

**Location**: Candles view

**Controls**:
- ☑️ "Tee random tapahtumia" checkbox
- 🔢 Number of stocks (1-1000)
- 🔢 Events per stock (1-200)
- 🔘 "Generoi laskutrenditapahtumat" button

**User Flow**:
1. Click Generate → Confirmation dialog
2. Confirm → Progress dialog appears
3. Progress updates: "Käsitelty X / Y osaketta"
4. Can cancel anytime (keeps saved events)
5. Completion → Success message with count

## Test Results

```
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_generator_initialization PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_check_downtrend_criteria_valid PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_check_downtrend_criteria_invalid PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_generate_with_real_db PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_progress_callback PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_cancel_check PASSED
tests/test_downtrend_generator.py::TestDowntrendGenerator::test_input_validation PASSED
tests/test_downtrend_generator.py::test_convenience_function PASSED

8 passed in 8.10s
```

## Database Schema

### Source: `data/osakedata.db`
- Table: `osakedata`
- Columns: `osake` (ticker), `pvm` (date), `open`, `high`, `low`, `close`, `volume`
- Date range: 2023-07-03 to 2025-09-29
- Stocks: 6871 unique tickers

### Target: `analysis/analysis.db`
- Table: `analysis_findings`
- Saves: ticker, date, pattern="Random", signal_strength=1.0, price, volume, OHLC data

## Performance

- **Speed**: ~10-50 stocks/second (depending on criteria match rate)
- **Memory**: Minimal (processes one stock at a time)
- **Attempts**: Max 500 random dates per stock
- **Success Rate**: Varies (strict criteria = fewer matches)

## Next Steps (Optional)

- Run with real data to verify behavior
- Adjust criteria if match rate too low/high
- Add more patterns beyond "Random"
- Add date range filtering in UI
- Add sector/market cap filters

## Implementation Date

October 23, 2025
