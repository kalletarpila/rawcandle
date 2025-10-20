# 📊 EXCEL SARAKKEET - PIKAOHJEET

## 🔍 SARAKELUOKAT (78 saraketta)

| Luokka | Sarakkeet | Kuvaus |
|--------|-----------|---------|
| 🔤 **Perustiedot** | 1-3 | osake, pvm, kynttila |
| 🕯️ **Kynttilädetaljit** | 4-15 | t-1, t0, t1 (alin, ylin, body, väri) |
| 📉 **Historialliset** | 16-20 | t_2, t_5, t_10, t_15, t_20 |
| 📈 **Tulevat** | 21-24 | t2, t5, t10, t20 |
| 📊 **Volatiliteetti** | 25-29 | hajonta % (suhteellinen std) |
| 📦 **Volyymit** | 30-39 | suhde 100pv keskiarvoon |
| 📈 **Liukuvat MA** | 40-56 | eri aikojen liukuvat keskiarvot |
| 🇺🇸 **S&P 500** | 57-67 | SPX indeksi normalisoitu |
| 💻 **Nasdaq 100** | 68-78 | NDX indeksi normalisoitu |

## ⚡ PIKASÄÄNNÖT

### 🎯 Normalisointi
- **Osake**: `t0_alin = 100.00` (perusta)
- **S&P 500**: `^GSPC t0_low = 100.00` 
- **Nasdaq**: `^NDX t0_low = 100.00`

### 🕯️ Kynttilädata
- **Alin/Ylin**: Normalisoitu t0_alin:iin
- **Body %**: `abs(close-open) / (high-low) * 100`
- **Väri**: `1=vihreä (close>open)`, `0=punainen (close≤open)`

### 📊 Volatiliteetti  
- **Kaava**: `(std / mean) * 100`
- **Aikaikkuna**: 5 päivää keskitettynä

### 📦 Volyymi
- **Kaava**: `current_volume / 100day_avg * 100`
- **100 = normaali**, >100 = korkea, <100 = matala

### 🔽 Laskutrendisuodatin
- **Minimi lasku**: esim. 5% 20 päivässä
- **MA-suodatin**: Kurssi < MA20
- **Volyymi-suodatin**: Volyymi > 100pv avg

## 📋 ESIMERKKIARVO TULKINTA

| Arvo | Merkitys |
|------|----------|
| **100.00** | Normalisoinnin perusta (t0) |
| **105.50** | 5,5% t0_alin yläpuolella |
| **95.20** | 4,8% t0_alin alapuolella |
| **1** | Vihreä kynttilä (nousu) |
| **0** | Punainen kynttilä (lasku) |
| **120** | 20% keskiarvon yläpuolella (volyymi) |
| **3.45** | 3,45% volatiliteetti |

## 🎨 Excel-muotoilu
- **Desimaalit**: 2 desimaalia
- **Suomalainen**: Pilkku desimaalimerkkinä
- **Värikoodit**: Body_colour (0/1)
- **Otsikot**: Sinisellä pohjalla, valkoinen teksti

---
💡 **Vinkki**: Kaikki hinnat ovat suhteellisia t0_alin = 100 perusteeseen!