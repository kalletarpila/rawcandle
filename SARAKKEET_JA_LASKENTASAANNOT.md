# 📊 EXCEL-TIEDOSTON SARAKKEET JA LASKENTASÄÄNNÖT

## 📋 YLEISTÄ
- **Yhteensä sarakeita**: 78
- **Normalisointi**: Kaikki hinta-arvot normalisoidaan t0_alin (käännekynttilän alin kurssi) = 100.00
- **Desimaalit**: Kaikki numerot näytetään 2 desimaalin tarkkuudella
- **Suomalainen muotoilu**: Pilkku desimaalimerkkinä

---

## 🔤 PERUSTIEDOT (Sarakkeet 1-3)

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 1 | `osake` | Osakkeen ticker-symboli | Suoraan tietokannasta |
| 2 | `pvm` | Käännekynttilän päivämäärä | Muoto: YYYY-MM-DD |
| 3 | `kynttila` | Kynttilämallin numero | 1-7 perusmallien mukaan |

### 🕯️ Kynttiläkuvioiden selitykset
| Koodi | Nimi | Kuvaus |
|-------|------|--------|
| 1 | Hammer | Pieni bodi, pitkä alavarjo, lyhyt ylävarjo (bullish) |
| 2 | Inverted Hammer | Pieni bodi, pitkä ylävarjo, lyhyt alavarjo |
| 3 | Hanging Man | Hammer lasketrendissä (bearish) |
| 4 | Shooting Star | Inverted Hammer nousetrendissä (bearish) |
| 5 | Doji | Avaus = päätös, pieni bodi |
| 6 | Dragonfly Doji | Doji pitkällä alavarjolla |
| 7 | Gravestone Doji | Doji pitkällä ylävarjolla |

---

## 🕯️ KYNTTILÄDETALJIT (Sarakkeet 4-15)

### T-1 (Edeltävä päivä)
| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 4 | `t_1_alin` | Edeltävän päivän alin | `(t-1_low / t0_alin) * 100` |
| 5 | `t_1_ylin` | Edeltävän päivän ylin | `(t-1_high / t0_alin) * 100` |
| 6 | `t_1_bodi` | Edeltävän päivän body % | `abs(close-open) / (high-low) * 100` |
| 7 | `t_1_bodi_colour` | Edeltävän päivän väri | `1` jos close > open, `0` jos ≤ |

### T0 (Käännekynttilä)
| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 8 | `t0_alin` | Käännekynttilän alin | **Aina 100.00** (normalisoinnin perusta) |
| 9 | `t0_ylin` | Käännekynttilän ylin | `(t0_high / t0_alin) * 100` |
| 10 | `t0_bodi` | Käännekynttilän body % | `abs(close-open) / (high-low) * 100` |
| 11 | `t0_bodi_colour` | Käännekynttilän väri | `1` jos close > open, `0` jos ≤ |

### T1 (Seuraava päivä)
| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 12 | `t1_alin` | Seuraavan päivän alin | `(t+1_low / t0_alin) * 100` |
| 13 | `t1_ylin` | Seuraavan päivän ylin | `(t+1_high / t0_alin) * 100` |
| 14 | `t1_bodi` | Seuraavan päivän body % | `abs(close-open) / (high-low) * 100` |
| 15 | `t1_bodi_colour` | Seuraavan päivän väri | `1` jos close > open, `0` jos ≤ |

---

## 📉 HISTORIALLISET HINNAT (Sarakkeet 16-20)

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 16 | `t_2` | 2 päivää ennen | `(t-2_close / t0_alin) * 100` |
| 17 | `t_5` | 5 päivää ennen | `(t-5_close / t0_alin) * 100` |
| 18 | `t_10` | 10 päivää ennen | `(t-10_close / t0_alin) * 100` |
| 19 | `t_15` | 15 päivää ennen | `(t-15_close / t0_alin) * 100` |
| 20 | `t_20` | 20 päivää ennen | `(t-20_close / t0_alin) * 100` |

---

## 📈 TULEVAT HINNAT (Sarakkeet 21-24)

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 21 | `t2` | 2 päivää jälkeen | `(t+2_close / t0_alin) * 100` |
| 22 | `t5` | 5 päivää jälkeen | `(t+5_close / t0_alin) * 100` |
| 23 | `t10` | 10 päivää jälkeen | `(t+10_close / t0_alin) * 100` |
| 24 | `t20` | 20 päivää jälkeen | `(t+20_close / t0_alin) * 100` |

---

## 📊 VOLATILITEETTI (Sarakkeet 25-29)

**Suhteellinen standardipoikkeama** (% keskiarvosta):

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 25 | `t_2_hajonta` | 2 pv volatiliteetti | `(std(t-4:t) / mean(t-4:t)) * 100` |
| 26 | `t_5_hajonta` | 5 pv volatiliteetti | `(std(t-7:t-3) / mean(t-7:t-3)) * 100` |
| 27 | `t_10_hajonta` | 10 pv volatiliteetti | `(std(t-12:t-8) / mean(t-12:t-8)) * 100` |
| 28 | `t_15_hajonta` | 15 pv volatiliteetti | `(std(t-17:t-13) / mean(t-17:t-13)) * 100` |
| 29 | `t_20_hajonta` | 20 pv volatiliteetti | `(std(t-22:t-18) / mean(t-22:t-18)) * 100` |

---

## 📦 VOLYYMIT (Sarakkeet 30-39)

**Suhde 100 päivän keskiarvoon**:

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 30 | `t_2_volyymi` | 2 pv volyymi | `mean(t-4:t) / mean(t-104:t-4) * 100` |
| 31 | `t_5_volyymi` | 5 pv volyymi | `mean(t-7:t-3) / mean(t-107:t-7) * 100` |
| 32 | `t_10_volyymi` | 10 pv volyymi | `mean(t-12:t-8) / mean(t-112:t-12) * 100` |
| 33 | `t_15_volyymi` | 15 pv volyymi | `mean(t-17:t-13) / mean(t-117:t-17) * 100` |
| 34 | `t_20_volyymi` | 20 pv volyymi | `mean(t-22:t-18) / mean(t-122:t-22) * 100` |
| 35 | `t0_volyymi` | Kynttilän volyymi | `t0_volume / mean(t-100:t) * 100` |
| 36 | `t2_volyymi` | 2 pv jälkeen | `mean(t:t+4) / mean(t-100:t) * 100` |
| 37 | `t5_volyymi` | 5 pv jälkeen | `mean(t+3:t+7) / mean(t-100:t) * 100` |
| 38 | `t10_volyymi` | 10 pv jälkeen | `mean(t+8:t+12) / mean(t-100:t) * 100` |
| 39 | `t20_volyymi` | 20 pv jälkeen | `mean(t+18:t+22) / mean(t-100:t) * 100` |

---

## 📈 LIUKUVAT KESKIARVOT (Sarakkeet 40-56)

**Normalisoitu t0_alin = 100**:

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 40 | `t2_5p_liukuva` | 2pv jälkeen 5pv MA | `mean(close, t:t+4) / t0_alin * 100` |
| 41 | `t2_10p_liukuva` | 2pv jälkeen 10pv MA | `mean(close, t-2:t+7) / t0_alin * 100` |
| 42 | `t2_20p_liukuva` | 2pv jälkeen 20pv MA | `mean(close, t-7:t+12) / t0_alin * 100` |
| 43 | `t5_5p_liukuva` | 5pv jälkeen 5pv MA | `mean(close, t+3:t+7) / t0_alin * 100` |
| 44 | `t5_10p_liukuva` | 5pv jälkeen 10pv MA | `mean(close, t:t+9) / t0_alin * 100` |
| 45 | `t5_20p_liukuva` | 5pv jälkeen 20pv MA | `mean(close, t-5:t+14) / t0_alin * 100` |
| 46 | `t10_5p_liukuva` | 10pv jälkeen 5pv MA | `mean(close, t+8:t+12) / t0_alin * 100` |
| 47 | `t10_10p_liukuva` | 10pv jälkeen 10pv MA | `mean(close, t+5:t+14) / t0_alin * 100` |
| 48 | `t10_20p_liukuva` | 10pv jälkeen 20pv MA | `mean(close, t:t+19) / t0_alin * 100` |
| 49 | `t15_5p_liukuva` | 15pv jälkeen 5pv MA | `mean(close, t+13:t+17) / t0_alin * 100` |
| 50 | `t15_10p_liukuva` | 15pv jälkeen 10pv MA | `mean(close, t+10:t+19) / t0_alin * 100` |
| 51 | `t15_20p_liukuva` | 15pv jälkeen 20pv MA | `mean(close, t+5:t+24) / t0_alin * 100` |
| 52 | `t20_5p_liukuva` | 20pv jälkeen 5pv MA | `mean(close, t+18:t+22) / t0_alin * 100` |
| 53 | `t20_10p_liukuva` | 20pv jälkeen 10pv MA | `mean(close, t+15:t+24) / t0_alin * 100` |
| 54 | `t20_20p_liukuva` | 20pv jälkeen 20pv MA | `mean(close, t+10:t+29) / t0_alin * 100` |
| 55 | `t50_50p_liukuva` | 50pv jälkeen 50pv MA | `mean(close, t+25:t+74) / t0_alin * 100` |
| 56 | `t200_200p_liukuva` | 200pv jälkeen 200pv MA | `mean(close, t+100:t+299) / t0_alin * 100` |

---

## 🇺🇸 S&P 500 INDEKSI (Sarakkeet 57-67)

**Normalisoitu ^GSPC t0_alin = 100**:

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 57 | `SPX_0` | S&P kynttilän päivä | **Aina 100.00** |
| 58 | `SPX_2` | S&P 2 pv ennen | `(^GSPC_t-2_close / ^GSPC_t0_low) * 100` |
| 59 | `SPX_5` | S&P 5 pv ennen | `(^GSPC_t-5_close / ^GSPC_t0_low) * 100` |
| 60 | `SPX_10` | S&P 10 pv ennen | `(^GSPC_t-10_close / ^GSPC_t0_low) * 100` |
| 61 | `SPX_15` | S&P 15 pv ennen | `(^GSPC_t-15_close / ^GSPC_t0_low) * 100` |
| 62 | `SPX_20` | S&P 20 pv ennen | `(^GSPC_t-20_close / ^GSPC_t0_low) * 100` |
| 63 | `SPX2` | S&P 2 pv jälkeen | `(^GSPC_t+2_close / ^GSPC_t0_low) * 100` |
| 64 | `SPX5` | S&P 5 pv jälkeen | `(^GSPC_t+5_close / ^GSPC_t0_low) * 100` |
| 65 | `SPX10` | S&P 10 pv jälkeen | `(^GSPC_t+10_close / ^GSPC_t0_low) * 100` |
| 66 | `SPX15` | S&P 15 pv jälkeen | `(^GSPC_t+15_close / ^GSPC_t0_low) * 100` |
| 67 | `SPX20` | S&P 20 pv jälkeen | `(^GSPC_t+20_close / ^GSPC_t0_low) * 100` |

---

## 💻 NASDAQ 100 INDEKSI (Sarakkeet 68-78)

**Normalisoitu ^NDX t0_alin = 100**:

| Sarake | Nimi | Kuvaus | Laskentasääntö |
|--------|------|--------|----------------|
| 68 | `NDX_0` | Nasdaq kynttilän päivä | **Aina 100.00** |
| 69 | `NDX_2` | Nasdaq 2 pv ennen | `(^NDX_t-2_close / ^NDX_t0_low) * 100` |
| 70 | `NDX_5` | Nasdaq 5 pv ennen | `(^NDX_t-5_close / ^NDX_t0_low) * 100` |
| 71 | `NDX_10` | Nasdaq 10 pv ennen | `(^NDX_t-10_close / ^NDX_t0_low) * 100` |
| 72 | `NDX_15` | Nasdaq 15 pv ennen | `(^NDX_t-15_close / ^NDX_t0_low) * 100` |
| 73 | `NDX_20` | Nasdaq 20 pv ennen | `(^NDX_t-20_close / ^NDX_t0_low) * 100` |
| 74 | `NDX2` | Nasdaq 2 pv jälkeen | `(^NDX_t+2_close / ^NDX_t0_low) * 100` |
| 75 | `NDX5` | Nasdaq 5 pv jälkeen | `(^NDX_t+5_close / ^NDX_t0_low) * 100` |
| 76 | `NDX10` | Nasdaq 10 pv jälkeen | `(^NDX_t+10_close / ^NDX_t0_low) * 100` |
| 77 | `NDX15` | Nasdaq 15 pv jälkeen | `(^NDX_t+15_close / ^NDX_t0_low) * 100` |
| 78 | `NDX20` | Nasdaq 20 pv jälkeen | `(^NDX_t+20_close / ^NDX_t0_low) * 100` |

---

## 🔽 LASKUTRENDISUODATIN

**Kun käytössä**:
- Minimialasku: Määritettävä % (esim. 5%)
- MA-suodatin: Kurssi liukuvan keskiarvon alapuolella
- Volyymi-suodatin: Volyymi keskiarvon yläpuolella

**Laskentakaava**:
```
decline_percent = ((t0_close - t-20_close) / t-20_close) * 100
käytetään_MA = t0_close < MA_20
käytetään_volume = t0_volume > volume_100d_avg
```

---

## 📊 YHTEENVETO

- **Normalisointi**: Kaikki hinnat suhteessa t0_alin = 100.00
- **Indeksit**: Omat normalisoinnit ^GSPC ja ^NDX t0_low = 100.00  
- **Volatiliteetti**: Suhteellinen standardipoikkeama %
- **Volyymit**: Suhde 100 päivän keskiarvoon
- **Excel-muotoilu**: 2 desimaalia, suomalainen pilkku
- **Rivejä**: Vaihtelee suodattimista (5-51 TSL:lle)

📅 **Luotu**: $(date '+%Y-%m-%d %H:%M')
🔧 **Versio**: RawCandle Excel v1.0