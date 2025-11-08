"""
Poista osakkeet joiden keskimääräinen päivävolyymi on alle 100 000 osaketta vuonna 2025
"""

import sqlite3


def remove_low_volume_stocks(min_avg_volume=100000):
    """
    Poista osakkeet joiden keskimääräinen päivävolyymi on alle raja-arvon

    Args:
        min_avg_volume: Minimikeskiarvo päivävolyymeille
    """
    db_path = "data/osakedata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Hae kaikki osakkeet
    cursor.execute("SELECT DISTINCT osake FROM osakedata")
    all_tickers = [row[0] for row in cursor.fetchall()]

    print(f"Tarkistetaan {len(all_tickers)} osaketta...")
    print(
        f"Kriteeri: keskimääräinen päivävolyymi >= {min_avg_volume:,} osaketta vuonna 2025\n"
    )

    to_remove = []
    year_2025 = "2025-%"

    for ticker in all_tickers:
        # Laske keskimääräinen päivävolyymi vuodelle 2025
        cursor.execute(
            """
            SELECT AVG(volume) as avg_volume, COUNT(*) as days
            FROM osakedata
            WHERE osake = ? AND pvm LIKE ?
        """,
            (ticker, year_2025),
        )

        result = cursor.fetchone()
        avg_volume = result[0] if result[0] else 0
        days = result[1]

        if avg_volume < min_avg_volume:
            to_remove.append((ticker, avg_volume, days))
            print(
                f"❌ {ticker:6s} - Keskim. {avg_volume:>12,.0f} osaketta/pv ({days} päivää)"
            )
        else:
            print(
                f"✅ {ticker:6s} - Keskim. {avg_volume:>12,.0f} osaketta/pv ({days} päivää)"
            )

    if not to_remove:
        print("\n✅ Kaikki osakkeet täyttävät kriteerin!")
        conn.close()
        return

    print(f"\n{'='*60}")
    print(f"Poistetaan {len(to_remove)} osaketta:")
    for ticker, avg_vol, days in to_remove:
        print(f"  {ticker:6s} - {avg_vol:>12,.0f} osaketta/pv")

    # Kysy vahvistus
    confirm = input(f"\nHaluatko poistaa nämä {len(to_remove)} osaketta? (y/N): ")

    if confirm.lower() != "y":
        print("Peruutettu.")
        conn.close()
        return

    # Poista osakkeet
    removed_count = 0
    for ticker, _, _ in to_remove:
        cursor.execute("DELETE FROM osakedata WHERE osake = ?", (ticker,))
        removed_count += cursor.rowcount
        print(f"  Poistettu {ticker}: {cursor.rowcount} riviä")

    conn.commit()

    print(f"\n✅ Poistettu {len(to_remove)} osaketta ({removed_count} riviä)")

    # Näytä jäljellä olevat
    cursor.execute("SELECT DISTINCT osake FROM osakedata")
    remaining = cursor.fetchall()
    print(f"✅ Jäljellä {len(remaining)} osaketta")

    conn.close()


if __name__ == "__main__":
    remove_low_volume_stocks(min_avg_volume=100000)
