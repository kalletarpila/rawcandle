import flet as ft

def render_single_ticker_results(df, selected_patterns, patterns_module):
    """
    Luo Flet-komponentit yksittäisen osakkeen analyysituloksille.
    Näyttää: Kuvion nimi ja päivämäärä, jolloin se löytyi.
    """
    results = []
    try:
        for pattern_name in selected_patterns:
            func_name = {
                "Hammer": "is_hammer",
                "Bullish Engulfing": "is_bullish_engulfing",
                "Piercing Pattern": "is_piercing_pattern",
                "Three White Soldiers": "is_three_white_soldiers",
                "Morning Star": "is_morning_star",
                "Dragonfly Doji": "is_dragonfly_doji",
            }[pattern_name]
            func = getattr(patterns_module, func_name, None)
            if func is None:
                continue
            found = func(df)
            for idx, is_found in found.items():
                if is_found:
                    date = df.iloc[idx]["pvm"] if "pvm" in df.columns else str(idx)
                    results.append(f"{pattern_name}: {date}")
    except Exception as ex:
        return [ft.Text(f"Virhe tulosten luonnissa: {ex}", color=ft.Colors.RED_700)]
    if not results:
        return [ft.Text("Ei löytynyt valittuja kuvioita tältä aikaväliltä.", color=ft.Colors.GREY_700)]
    return [ft.Text(r, color=ft.Colors.GREEN_800) for r in results]
