# EXCEL-TIEDOSTON SARAKKEET JA LASKENTASAANNOT

## YLEISTA
- **Yhteensa sarakeita**: 78
- **Normalisointi**: Kaikki hinta-arvot normalisoidaan t0_alin (kaannekynttilan alin kurssi) = 100.00
- **Desimaalit**: Kaikki numerot naytetaan 2 desimaalin tarkkuudella
- **Suomalainen muotoilu**: Pilkku desimaalimerkkinä

---

## PERUSTIEDOT (Sarakkeet 1-3)

| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 1 | `osake` | Osakkeen ticker-symboli | Suoraan tietokannasta |
| 2 | `pvm` | Kaannekynttilan paivamaara | Muoto: YYYY-MM-DD |
| 3 | `kynttila` | Kynttilamallin numero | 1-7 perusmallien mukaan |

### Kynttilamallien selitykset
| Koodi | Nimi | Kuvaus |
|-------|------|--------|
| 1 | Hammer | Pieni bodi, pitka alavarjo, lyhyt ylavarjo (bullish) |
| 2 | Inverted Hammer | Pieni bodi, pitka ylavarjo, lyhyt alavarjo |
| 3 | Hanging Man | Hammer lasketrendissa (bearish) |
| 4 | Shooting Star | Inverted Hammer nousetrendissa (bearish) |
| 5 | Doji | Avaus = paatos, pieni bodi |
| 6 | Dragonfly Doji | Doji pitkalla alavarjolla |
| 7 | Gravestone Doji | Doji pitkalla ylavarjolla |

---

## KYNTTILADETALJIT (Sarakkeet 4-15)

### T-1 (Edellinen paiva, Sarakkeet 4-7)
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 4 | `t_1_alin` | T-1 alin normalisoitu | (t_1_alin / t0_alin) * 100 |
| 5 | `t_1_ylin` | T-1 ylin normalisoitu | (t_1_ylin / t0_alin) * 100 |
| 6 | `t_1_bodi` | T-1 bodin koko prosenttina | abs(paatos - avaus) / avaus * 100 |
| 7 | `t_1_bodi_colour` | T-1 bodin vari | 0=punainen (paatos<avaus), 1=vihrea (paatos>avaus) |

### T0 (Kaannekynttila, Sarakkeet 8-11)
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 8 | `t0_alin` | T0 alin (perusarvo) | Aina 100.00 (normalisointipohja) |
| 9 | `t0_ylin` | T0 ylin normalisoitu | (t0_ylin / t0_alin) * 100 |
| 10 | `t0_bodi` | T0 bodin koko prosenttina | abs(paatos - avaus) / avaus * 100 |
| 11 | `t0_bodi_colour` | T0 bodin vari | 0=punainen, 1=vihrea |

### T1 (Seuraava paiva, Sarakkeet 12-15)
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 12 | `t1_alin` | T1 alin normalisoitu | (t1_alin / t0_alin) * 100 |
| 13 | `t1_ylin` | T1 ylin normalisoitu | (t1_ylin / t0_alin) * 100 |
| 14 | `t1_bodi` | T1 bodin koko prosenttina | abs(paatos - avaus) / avaus * 100 |
| 15 | `t1_bodi_colour` | T1 bodin vari | 0=punainen, 1=vihrea |

---

## HINNAT (Sarakkeet 16-24)

### Historialliset hinnat
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 16 | `t_5` | Hinta 5 paivaa sitten | (hinta_t-5 / t0_alin) * 100 |
| 17 | `t_10` | Hinta 10 paivaa sitten | (hinta_t-10 / t0_alin) * 100 |
| 18 | `t_20` | Hinta 20 paivaa sitten | (hinta_t-20 / t0_alin) * 100 |

### Tulevaisuuden hinnat
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 19 | `t5` | Hinta 5 paivaa eteenpain | (hinta_t+5 / t0_alin) * 100 |
| 20 | `t10` | Hinta 10 paivaa eteenpain | (hinta_t+10 / t0_alin) * 100 |
| 21 | `t20` | Hinta 20 paivaa eteenpain | (hinta_t+20 / t0_alin) * 100 |
| 22 | `t40` | Hinta 40 paivaa eteenpain | (hinta_t+40 / t0_alin) * 100 |
| 23 | `t60` | Hinta 60 paivaa eteenpain | (hinta_t+60 / t0_alin) * 100 |
| 24 | `t252` | Hinta 252 paivaa eteenpain | (hinta_t+252 / t0_alin) * 100 |

---

## VOLATILITEETTI (Sarakkeet 25-29)

| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 25 | `vol_5` | 5 paivan volatiliteetti | Standardipoikkeama(paivittaiset_muutokset_5pv) * sqrt(252) |
| 26 | `vol_10` | 10 paivan volatiliteetti | Standardipoikkeama(paivittaiset_muutokset_10pv) * sqrt(252) |
| 27 | `vol_20` | 20 paivan volatiliteetti | Standardipoikkeama(paivittaiset_muutokset_20pv) * sqrt(252) |
| 28 | `vol_60` | 60 paivan volatiliteetti | Standardipoikkeama(paivittaiset_muutokset_60pv) * sqrt(252) |
| 29 | `vol_252` | 252 paivan volatiliteetti | Standardipoikkeama(paivittaiset_muutokset_252pv) * sqrt(252) |

---

## VOLYYMIT (Sarakkeet 30-39)

### Absoluuttiset volyymit
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 30 | `vol_avg_10` | 10 paivan keskivol | Keskiarvo(volyymi_10_paivaa) |
| 31 | `vol_avg_20` | 20 paivan keskivol | Keskiarvo(volyymi_20_paivaa) |
| 32 | `vol_avg_60` | 60 paivan keskivol | Keskiarvo(volyymi_60_paivaa) |

### Volyymisuhteet
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 33 | `vol_t_1_vs_avg10` | T-1 vs 10pv keskim | t_1_volyymi / 10pv_keskiarvo |
| 34 | `vol_t0_vs_avg10` | T0 vs 10pv keskim | t0_volyymi / 10pv_keskiarvo |
| 35 | `vol_t1_vs_avg10` | T1 vs 10pv keskim | t1_volyymi / 10pv_keskiarvo |
| 36 | `vol_t_1_vs_avg20` | T-1 vs 20pv keskim | t_1_volyymi / 20pv_keskiarvo |
| 37 | `vol_t0_vs_avg20` | T0 vs 20pv keskim | t0_volyymi / 20pv_keskiarvo |
| 38 | `vol_t1_vs_avg20` | T1 vs 20pv keskim | t1_volyymi / 20pv_keskiarvo |
| 39 | `vol_spike` | Volyymipiikin tunniste | 1 jos t0_vol > 2 * avg20, muuten 0 |

---

## LIUKUVAT KESKIARVOT (Sarakkeet 40-56)

### Lyhyet MA:t
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 40 | `ma_5` | 5 paivan MA | Keskiarvo(sulkemishinnat_5pv) |
| 41 | `ma_10` | 10 paivan MA | Keskiarvo(sulkemishinnat_10pv) |
| 42 | `ma_20` | 20 paivan MA | Keskiarvo(sulkemishinnat_20pv) |

### Pitkät MA:t
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 43 | `ma_50` | 50 paivan MA | Keskiarvo(sulkemishinnat_50pv) |
| 44 | `ma_100` | 100 paivan MA | Keskiarvo(sulkemishinnat_100pv) |
| 45 | `ma_200` | 200 paivan MA | Keskiarvo(sulkemishinnat_200pv) |

### MA-etäisyydet
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 46 | `dist_ma_5` | Etaisyys MA5:sta | ((t0_hinta - ma_5) / ma_5) * 100 |
| 47 | `dist_ma_10` | Etaisyys MA10:sta | ((t0_hinta - ma_10) / ma_10) * 100 |
| 48 | `dist_ma_20` | Etaisyys MA20:sta | ((t0_hinta - ma_20) / ma_20) * 100 |
| 49 | `dist_ma_50` | Etaisyys MA50:sta | ((t0_hinta - ma_50) / ma_50) * 100 |
| 50 | `dist_ma_100` | Etaisyys MA100:sta | ((t0_hinta - ma_100) / ma_100) * 100 |
| 51 | `dist_ma_200` | Etaisyys MA200:sta | ((t0_hinta - ma_200) / ma_200) * 100 |

### MA-kulmakertoimet
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 52 | `ma_5_slope` | MA5 kulmakerroin | (ma5_tanaan - ma5_5pv_sitten) / 5 |
| 53 | `ma_10_slope` | MA10 kulmakerroin | (ma10_tanaan - ma10_10pv_sitten) / 10 |
| 54 | `ma_20_slope` | MA20 kulmakerroin | (ma20_tanaan - ma20_20pv_sitten) / 20 |
| 55 | `ma_50_slope` | MA50 kulmakerroin | (ma50_tanaan - ma50_50pv_sitten) / 50 |
| 56 | `ma_200_slope` | MA200 kulmakerroin | (ma200_tanaan - ma200_200pv_sitten) / 200 |

---

## S&P 500 TIEDOT (Sarakkeet 57-67)

### Perushinnat
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 57 | `sp500_t_1` | S&P 500 T-1 | Sulkemishinta T-1 |
| 58 | `sp500_t0` | S&P 500 T0 | Sulkemishinta T0 |
| 59 | `sp500_t1` | S&P 500 T1 | Sulkemishinta T1 |

### Liukuvat keskiarvot
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 60 | `sp500_ma_20` | S&P 500 MA20 | 20 paivan liukuva keskiarvo |
| 61 | `sp500_ma_50` | S&P 500 MA50 | 50 paivan liukuva keskiarvo |
| 62 | `sp500_ma_200` | S&P 500 MA200 | 200 paivan liukuva keskiarvo |

### Muutokset ja suhteet
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 63 | `sp500_change_t0` | S&P 500 muutos T0 | ((t0 - t_1) / t_1) * 100 |
| 64 | `sp500_change_t1` | S&P 500 muutos T1 | ((t1 - t0) / t0) * 100 |
| 65 | `sp500_vs_ma20` | S&P 500 vs MA20 | ((t0 - ma20) / ma20) * 100 |
| 66 | `sp500_vs_ma50` | S&P 500 vs MA50 | ((t0 - ma50) / ma50) * 100 |
| 67 | `sp500_vs_ma200` | S&P 500 vs MA200 | ((t0 - ma200) / ma200) * 100 |

---

## NASDAQ 100 TIEDOT (Sarakkeet 68-78)

### Perushinnat
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 68 | `nasdaq_t_1` | Nasdaq 100 T-1 | Sulkemishinta T-1 |
| 69 | `nasdaq_t0` | Nasdaq 100 T0 | Sulkemishinta T0 |
| 70 | `nasdaq_t1` | Nasdaq 100 T1 | Sulkemishinta T1 |

### Liukuvat keskiarvot
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 71 | `nasdaq_ma_20` | Nasdaq 100 MA20 | 20 paivan liukuva keskiarvo |
| 72 | `nasdaq_ma_50` | Nasdaq 100 MA50 | 50 paivan liukuva keskiarvo |
| 73 | `nasdaq_ma_200` | Nasdaq 100 MA200 | 200 paivan liukuva keskiarvo |

### Muutokset ja suhteet
| Sarake | Nimi | Kuvaus | Laskentasaanto |
|--------|------|--------|----------------|
| 74 | `nasdaq_change_t0` | Nasdaq 100 muutos T0 | ((t0 - t_1) / t_1) * 100 |
| 75 | `nasdaq_change_t1` | Nasdaq 100 muutos T1 | ((t1 - t0) / t0) * 100 |
| 76 | `nasdaq_vs_ma20` | Nasdaq 100 vs MA20 | ((t0 - ma20) / ma20) * 100 |
| 77 | `nasdaq_vs_ma50` | Nasdaq 100 vs MA50 | ((t0 - ma50) / ma50) * 100 |
| 78 | `nasdaq_vs_ma200` | Nasdaq 100 vs MA200 | ((t0 - ma200) / ma200) * 100 |

---

## KAYTTOOHJEITA

### Normalisointi
- Kaikki hinta-arvot on normalisoitu suhteessa kaannekynttilan alimpaan hintaan (t0_alin = 100.00)
- Tama mahdollistaa eri osakkeiden vertailun riippumatta niiden absoluuttisesta hintatasosta

### Suomalainen Excel-muotoilu
- Desimaalimerkki: pilkku (,) eika piste (.)
- Numerot esitetaan 2 desimaalin tarkkuudella
- Paivamaaramuoto: VVVV-KK-PP

### Kynttiladetaljit
- Bodin koko lasketaan prosentteina avaushinnasta
- Bodin vari: 0 = punainen (laskeva), 1 = vihrea (nouseva)
- Alin ja ylin hinnat normalisoidaan t0_alin-arvoon

### Tekninen analyysi
- Volatiliteetti annualisoitu (kerrottu sqrt(252))
- Liukuvat keskiarvot lasketaan sulkemishinnoista
- Kulmakertoimet osoittavat trendin suunnan ja voimakkuuden

### Indeksitiedot
- S&P 500: ^GSPC symboli
- Nasdaq 100: ^NDX symboli
- Mahdollistaa markkinakorrelaation analyysin