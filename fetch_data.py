"""
Sækir raunveruleg gögn fyrir bandarísku og bresku félögin á vaktlistanum og
skrifar þau í data.json, sem síðan HTML-síðan les.

Uppsetning (einu sinni):
    pip install yfinance vaderSentiment --break-system-packages

Keyrsla (í hvert sinn sem þú vilt uppfæra gögnin):
    python fetch_data.py

Þetta skrifar data.json í sömu möppu og skriftan er í.
Settu HTML-skrána og data.json í sömu möppu og keyrðu:
    python -m http.server
og opnaðu síðan http://localhost:8000/fjarfestingar-yfirlit.html
(bein opnun á HTML-skránni með tvísmelli virkar EKKI fyrir gagnasækinguna,
því vafrinn leyfir ekki að sækja skrár af diski með fetch() nema í gegnum vefþjón.)

Fréttatónn: notar VADER (vaderSentiment), ókeypis og staðbundna sentiment-greiningu
sem er sértaklega hönnuð fyrir stuttan texta eins og fréttafyrirsagnir. Þetta er EKKI
stórt tungumálalíkan (LLM) — bara orðabókarbundin greining — en kostar ekkert og
krefst ekkert API-lykils.
"""

import json
from datetime import datetime, timezone

import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def fetch_news_sentiment(ticker: str) -> dict:
    """Sækir nýjustu fréttafyrirsagnir fyrir félagið og metur tón þeirra með VADER.
    Skilar núll-tón (hlutlaust) ef engar fréttir finnast, frekar en að láta allt hrynja."""
    try:
        t = yf.Ticker(ticker)
        news_items = t.news or []
        if not news_items:
            return {"newsScore": 0, "newsHeadline": None}

        scores = []
        headlines = []
        for item in news_items[:5]:
            # yfinance skilar fréttum ýmist beint eða undir "content" lykli eftir útgáfu
            content = item.get("content", item)
            title = content.get("title") or content.get("summary")
            if not title:
                continue
            headlines.append(title)
            compound = _analyzer.polarity_scores(title)["compound"]  # -1 .. 1
            scores.append(compound)

        if not scores:
            return {"newsScore": 0, "newsHeadline": None}

        avg_compound = sum(scores) / len(scores)
        # Skala -1..1 (VADER) yfir í -2..2 (okkar kvarði) og rúnna að heilli tölu
        news_score = round(avg_compound * 2, 1)

        return {"newsScore": news_score, "newsHeadline": headlines[0]}
    except Exception as e:
        print(f"[viðvörun] tókst ekki að sækja fréttir fyrir {ticker}: {e}")
        return {"newsScore": 0, "newsHeadline": None}

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


def fetch_benchmark_change(index_ticker: str) -> float | None:
    """Sækir 30 daga breytingu (%) fyrir viðmiðunarvísitölu, notað til að reikna afstæðan styrk."""
    try:
        hist = yf.Ticker(index_ticker).history(period="1mo")
        if hist.empty:
            return None
        closes = hist["Close"].tolist()
        return round(((closes[-1] - closes[0]) / closes[0]) * 100, 2)
    except Exception as e:
        print(f"[viðvörun] tókst ekki að sækja viðmiðunarvísitölu {index_ticker}: {e}")
        return None


def fetch_one(ticker: str, benchmark_chg_30d: float | None = None) -> dict | None:
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

        # Afstæður styrkur: hvernig félagið hefur staðið sig síðustu 30 daga
        # samanborið við viðmiðunarvísitöluna á sama tímabili (í prósentustigum).
        rel_strength = None
        if benchmark_chg_30d is not None and len(closes) > 1:
            stock_chg_30d = ((closes[-1] - closes[0]) / closes[0]) * 100
            rel_strength = round(stock_chg_30d - benchmark_chg_30d, 2)

        # Viðskiptamagn: er dagurinn í dag óvenju stór miðað við undanfarið?
        volume_ratio = None
        if "Volume" in hist.columns and len(hist["Volume"]) > 1:
            volumes = hist["Volume"].tolist()
            avg_volume = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
            if avg_volume > 0:
                volume_ratio = round(volumes[-1] / avg_volume, 2)

        market_cap = info.get("marketCap") or fast.get("market_cap")
        week_high = info.get("fiftyTwoWeekHigh") or fast.get("year_high")
        week_low = info.get("fiftyTwoWeekLow") or fast.get("year_low")

        news = fetch_news_sentiment(ticker)

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
            "relStrength": rel_strength,
            "volumeRatio": volume_ratio,
            "newsScore": news["newsScore"],
            "newsHeadline": news["newsHeadline"],
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
    us_benchmark = fetch_benchmark_change("^GSPC")   # S&P 500
    uk_benchmark = fetch_benchmark_change("^FTSE")   # FTSE 100

    stocks = []
    for ticker in TICKERS:
        result = fetch_one(ticker, benchmark_chg_30d=us_benchmark)
        if result:
            stocks.append(result)
    add_sector_pe_average(stocks)

    uk_stocks = []
    for ticker in UK_TICKERS:
        result = fetch_one(ticker, benchmark_chg_30d=uk_benchmark)
        if result:
            uk_stocks.append(result)
    add_sector_pe_average(uk_stocks)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "us": stocks,
        "uk": uk_stocks,
        "benchmarks": {"us": us_benchmark, "uk": uk_benchmark},
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Lokið — {len(stocks)}/{len(TICKERS)} bandarísk og {len(uk_stocks)}/{len(UK_TICKERS)} bresk félög sótt og vistuð í data.json")


if __name__ == "__main__":
    main()
