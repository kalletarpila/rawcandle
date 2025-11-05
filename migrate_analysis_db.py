#!/usr/bin/env python3
"""
Migraatioskripti: Yksinkertaistaa analysis.db tietokantarakenne
Säilyttää vain tarpeelliset kentät: id, ticker, date, pattern, signal_strength, created_at
"""
import sqlite3
import sys
from pathlib import Path


def migrate_database(db_path: str = "data/analysis.db"):
    """Migroi tietokanta yksinkertaistettuun rakenteeseen"""

    print(f"🔧 Migroidaan tietokanta: {db_path}")

    if not Path(db_path).exists():
        print(f"❌ Tietokantaa ei löydy: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Luo uusi yksinkertaistettu taulu
        print("📝 Luodaan uusi yksinkertaistettu taulu...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_findings_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                pattern TEXT,
                signal_strength REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # 2. Kopioi data vanhasta taulusta (vain tarvittavat kentät)
        print("📋 Kopioidaan data vanhasta taulusta...")

        # Tarkista mitä kenttiä vanhassa taulussa on
        cursor.execute("PRAGMA table_info(analysis_findings)")
        old_columns = {row[1] for row in cursor.fetchall()}

        # Määritä lähdekentät
        source_fields = []
        target_fields = []

        # ticker
        if "ticker" in old_columns:
            source_fields.append("ticker")
            target_fields.append("ticker")
        elif "osake" in old_columns:
            source_fields.append("osake")
            target_fields.append("ticker")
        else:
            print("❌ Ticker-kenttää ei löydy!")
            return False

        # date
        if "date" in old_columns:
            source_fields.append("date")
            target_fields.append("date")
        elif "pvm" in old_columns:
            source_fields.append("pvm")
            target_fields.append("date")
        else:
            print("❌ Date-kenttää ei löydy!")
            return False

        # pattern (ota candle_pattern tai pattern)
        if "pattern" in old_columns:
            source_fields.append("pattern")
            target_fields.append("pattern")
        elif "candle_pattern" in old_columns:
            source_fields.append("candle_pattern")
            target_fields.append("pattern")
        else:
            source_fields.append("NULL")
            target_fields.append("pattern")

        # signal_strength
        if "signal_strength" in old_columns:
            source_fields.append("signal_strength")
            target_fields.append("signal_strength")
        else:
            source_fields.append("NULL")
            target_fields.append("signal_strength")

        # created_at
        if "created_at" in old_columns:
            source_fields.append("created_at")
            target_fields.append("created_at")
        else:
            source_fields.append("CURRENT_TIMESTAMP")
            target_fields.append("created_at")

        # Suorita kopiointi
        source_sql = ", ".join(source_fields)
        target_sql = ", ".join(target_fields)

        copy_query = f"""
            INSERT INTO analysis_findings_new ({target_sql})
            SELECT {source_sql}
            FROM analysis_findings
        """

        cursor.execute(copy_query)
        rows_copied = cursor.rowcount
        print(f"✅ Kopioitu {rows_copied} riviä")

        # 3. Poista vanha taulu
        print("🗑️  Poistetaan vanha taulu...")
        cursor.execute("DROP TABLE analysis_findings")

        # 4. Nimeä uusi taulu
        print("📝 Nimetään uusi taulu...")
        cursor.execute("ALTER TABLE analysis_findings_new RENAME TO analysis_findings")

        # 5. Luo indeksit
        print("📑 Luodaan indeksit...")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticker ON analysis_findings(ticker)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON analysis_findings(date)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pattern ON analysis_findings(pattern)"
        )

        # 6. Päivitä analysis_date jos se on käytössä (vanhentunut kenttä)
        cursor.execute("PRAGMA table_info(analysis_findings)")
        new_columns = {row[1] for row in cursor.fetchall()}

        if "analysis_date" in new_columns:
            cursor.execute("ALTER TABLE analysis_findings DROP COLUMN analysis_date")

        # Commit muutokset
        conn.commit()

        # Näytä uusi rakenne
        print("\n✅ Migraatio valmis! Uusi rakenne:")
        cursor.execute("PRAGMA table_info(analysis_findings)")
        for row in cursor.fetchall():
            print(f"   {row[1]}: {row[2]}")

        cursor.execute("SELECT COUNT(*) FROM analysis_findings")
        count = cursor.fetchone()[0]
        print(f"\n📊 Rivejä tietokannassa: {count}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Virhe migraatiossa: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/analysis.db"
    success = migrate_database(db_path)
    sys.exit(0 if success else 1)
