"""
Sækir raunveruleg gögn fyrir bandarísku félögin á vaktlistanum og
skrifar þau í data.json, sem síðan HTML-síðan les.

Uppsetning (einu sinni):
    pip install yfinance --break-system-packages

Keyrsla (í hvert sinn sem þú vilt uppfæra gögnin):
    python fetch_data.py

Þetta skrifar data.json í sömu möppu og skriftan er í.
Settu HTML-skrána og data.json í sömu möppu og keyrðu:
    python -m http.server
og opnaðu síðan http://localhost:8000/fjarfestingar-yfirlit.html
(bein opnun á HTML-skránni með tvísmelli virkar EKKI fyrir gagnasækinguna,
því vafrinn leyfir ekki að sækja skrár af diski með fetch() nema í gegnum vefþjón.)
"""

import json
from datetime import datetime, timezone

import yfinance as yf

# ---- Vaktlistinn þinn — bættu við eða fjarlægðu tickera hér ----
# Blanda úr ólíkum atvinnugreinum svo skanninn hafi fjölbreytt úrval til að bera saman
TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN",      # tækni
    "JPM", "V",                          # fjármál
    "JNJ", "UNH",                        # heilbrigði
    "KO", "PG",                          # neysluvörur
    "XOM", "CVX",                        # orka
    "CAT", "BA",                         # iðnaður
]

# Bresk félög — .L viðskeytið segir Yahoo að sækja gögn af London kauphöllinni (LSE).
# ATH: LSE hlutabréf eru langoftast skráð í pensum (GBX), ekki pundum — 100 pensar = 1 pund.
UK_TICKERS = ["HSBA.L", "AZN.L", "SHEL.L", "ULVR.L", "BARC.L"]


def fetch_one(ticker: str) -> dict | None:
    """Sækir verð, 30 daga sögu og grunngreiningartölur fyrir eitt félag."""
    try:
        t = yf.Ticker(ticker)
        info = t.info  # getur verið hægt / stundum takmarkað af Yahoo

        # fast_info er sértaklega ætlað fyrir svona tölur og er oftast áreiðanlegra
        # en .info, sem getur stundum vantað einstaka reiti hjá Yahoo.
        try:
            fast = dict(t.fast_info)
        except Exception:
            fast = {}

        hist = t.history(period="1mo")
        if hist.empty:
            print(f"[viðvörun] engin verðsaga fannst fyrir {ticker}")
            return None

        closes = [round(float(v), 2) for v in hist["Close"].tolist()]
        price = closes[-1]
        prev_close = info.get("previousClose") or (closes[-2] if len(closes) > 1 else price)
        chg_pct = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0

        market_cap = info.get("marketCap") or fast.get("market_cap")
        week_high = info.get("fiftyTwoWeekHigh") or fast.get("year_high")
        week_low = info.get("fiftyTwoWeekLow") or fast.get("year_low")

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "price": price,
            "chg": chg_pct,
            "hist": closes,
            "pe": round(info.get("trailingPE"), 1) if info.get("trailingPE") else None,
            "debtEq": round(info.get("debtToEquity") / 100, 2) if info.get("debtToEquity") else None,
            "sector": info.get("sector", "Óþekkt"),
            "industry": info.get("industry", "Óþekkt"),
            "marketCap": market_cap,
            "weekHigh52": round(week_high, 2) if week_high else None,
            "weekLow52": round(week_low, 2) if week_low else None,
            "dividendYield": info.get("dividendYield"),
            "url": f"https://finance.yahoo.com/quote/{ticker}",
        }
    except Exception as e:
        print(f"[villa] tókst ekki að sækja {ticker}: {e}")
        return None


def add_sector_pe_average(stocks: list[dict]) -> None:
    """Reiknar meðal V/H fyrir hverja atvinnugrein innan vaktlistans sjálfs,
    og notar sem einfaldan samanburðarpunkt (ekki opinbert greinameðaltal)."""
    sector_pes: dict[str, list[float]] = {}
    for s in stocks:
        if s.get("pe"):
            sector_pes.setdefault(s["sector"], []).append(s["pe"])

    sector_avg = {
        sector: round(sum(pes) / len(pes), 1)
        for sector, pes in sector_pes.items()
    }

    for s in stocks:
        s["sectorPe"] = sector_avg.get(s["sector"], s.get("pe", 0))


def main():
    stocks = []
    for ticker in TICKERS:
        result = fetch_one(ticker)
        if result:
            stocks.append(result)
    add_sector_pe_average(stocks)

    uk_stocks = []
    for ticker in UK_TICKERS:
        result = fetch_one(ticker)
        if result:
            uk_stocks.append(result)
    add_sector_pe_average(uk_stocks)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "us": stocks,
        "uk": uk_stocks,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Lokið — {len(stocks)}/{len(TICKERS)} bandarísk og {len(uk_stocks)}/{len(UK_TICKERS)} bresk félög sótt og vistuð í data.json")


if __name__ == "__main__":
    main()
