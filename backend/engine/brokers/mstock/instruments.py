"""
backend/engine/brokers/mstock/instruments.py
---------------------------------------------
NiftyInstruments: Downloads the Nifty 500 constituent list from NSE and maps
each symbol to an m.Stock instrument token.  Falls back to a static symbol /
sector mapping when the NSE endpoint is unreachable.
"""

from __future__ import annotations

import asyncio
import io
import os
from typing import Dict, List, Optional

import requests

from backend.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Static fallback: well-known NSE symbols → sector
# ---------------------------------------------------------------------------

NIFTY500_SECTOR_MAP: Dict[str, str] = {
    "RELIANCE": "Oil & Gas",
    "TCS": "IT",
    "INFY": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "HINDUNILVR": "FMCG",
    "SBIN": "Banking",
    "BHARTIARTL": "Telecom",
    "KOTAKBANK": "Banking",
    "LT": "Infrastructure",
    "AXISBANK": "Banking",
    "ASIANPAINT": "Chemicals",
    "MARUTI": "Auto",
    "SUNPHARMA": "Pharma",
    "TITAN": "FMCG",
    "WIPRO": "IT",
    "TECHM": "IT",
    "HCLTECH": "IT",
    "BAJFINANCE": "Finance",
    "BAJAJFINSV": "Finance",
    "NESTLEIND": "FMCG",
    "ULTRACEMCO": "Cement",
    "ADANIENT": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "POWERGRID": "Utilities",
    "NTPC": "Utilities",
    "ONGC": "Oil & Gas",
    "COALINDIA": "Energy",
    "BPCL": "Oil & Gas",
    "DIVISLAB": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "EICHERMOT": "Auto",
    "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto",
    "M&M": "Auto",
    "TATAMOTORS": "Auto",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "VEDL": "Metals",
    "GRASIM": "Cement",
    "SHREECEM": "Cement",
    "INDUSINDBK": "Banking",
    "SBILIFE": "Finance",
    "HDFCLIFE": "Finance",
    "ICICIGI": "Finance",
    "BRITANNIA": "FMCG",
    "ITC": "FMCG",
    "TATACONSUM": "FMCG",
    "PIDILITIND": "Chemicals",
    "BERGEPAINT": "Chemicals",
    "TORNTPHARM": "Pharma",
    "BIOCON": "Pharma",
    "APOLLOHOSP": "Healthcare",
    "FORTIS": "Healthcare",
    "MUTHOOTFIN": "Finance",
    "CHOLAFIN": "Finance",
    "SBICARD": "Finance",
    "PEL": "Finance",
    "SAIL": "Metals",
    "NMDC": "Metals",
    "DLF": "Realty",
    "GODREJPROP": "Realty",
    "PRESTIGE": "Realty",
    "OBEROIRLTY": "Realty",
    "ZOMATO": "Media",
    "NYKAA": "FMCG",
    "PAYTM": "Finance",
    "IRCTC": "Infrastructure",
    "TATAPOWER": "Utilities",
    "ADANIGREEN": "Utilities",
    "HAL": "Infrastructure",
    "BEL": "Infrastructure",
    "BHEL": "Infrastructure",
    "GAIL": "Oil & Gas",
    "IOC": "Oil & Gas",
    "HPCL": "Oil & Gas",
    "DMART": "FMCG",
    "TRENT": "FMCG",
    "PAGEIND": "FMCG",
    "MCDOWELL-N": "FMCG",
    "GODREJCP": "FMCG",
    "MARICO": "FMCG",
    "COLPAL": "FMCG",
    "DABUR": "FMCG",
    "EMAMILTD": "FMCG",
    "HAVELLS": "Infrastructure",
    "VOLTAS": "Infrastructure",
    "WHIRLPOOL": "Infrastructure",
    "SIEMENS": "Infrastructure",
    "ABB": "Infrastructure",
    "CUMMINSIND": "Infrastructure",
    "THERMAX": "Infrastructure",
    "ESCORTS": "Auto",
    "ASHOKLEY": "Auto",
    "TIINDIA": "Auto",
    "BALKRISIND": "Auto",
    "MRF": "Auto",
}


class NiftyInstruments:
    """
    Manages the Nifty 500 universe: symbol list, sector classification, and
    m.Stock instrument token mapping.

    Typical usage
    -------------
    ::

        instruments = NiftyInstruments()
        await instruments.sync(mconnect_obj)
        token = instruments.get_token("RELIANCE")
        scannable = instruments.get_scannable_symbols()
    """

    def __init__(self) -> None:
        #: Full instrument records – [{symbol, token, exchange, sector}]
        self.instruments: List[Dict] = []
        #: symbol → m.Stock instrument token
        self.token_map: Dict[str, str] = {}
        #: symbol → sector string (starts with static map, enriched by NSE API)
        self.sector_map: Dict[str, str] = dict(NIFTY500_SECTOR_MAP)
        #: Ordered list of Nifty 500 trading symbols
        self.nifty500_symbols: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync(self, mconnect_obj) -> bool:
        """
        Fetch Nifty 500 constituent list from NSE API and map tokens from m.Stock.

        Parameters
        ----------
        mconnect_obj :
            An initialised m.Stock MConnect instance that exposes
            ``get_instruments()``.  Pass ``None`` to skip token mapping.

        Returns
        -------
        bool
            ``True`` on success, ``False`` if either step failed.
        """
        try:
            # Step 1: Fetch Nifty 500 from NSE API
            await self._download_nifty500_list()
            logger.info(
                f"Nifty 500 symbols loaded: {len(self.nifty500_symbols)}",
                extra={"reason_code": "NIFTY500_SYMBOLS_LOADED"},
            )

            # Step 2: Get instrument master from m.Stock
            if mconnect_obj is not None:
                loop = asyncio.get_running_loop()
                resp = await loop.run_in_executor(None, mconnect_obj.get_instruments)
                
                instruments_data = []
                if isinstance(resp, bytes):
                    import io
                    import pandas as pd
                    try:
                        df = pd.read_csv(io.StringIO(resp.decode('utf-8')), low_memory=False)
                        instruments_data = df.to_dict('records')
                    except Exception as e:
                        logger.error(f"Failed to parse mStock instruments CSV: {e}")
                elif hasattr(resp, "json"):
                    data = resp.json()
                    instruments_data = data.get("data", []) if isinstance(data, dict) else []
                elif isinstance(resp, list):
                    instruments_data = resp
                    
                if instruments_data:
                    await self._build_token_map(instruments_data)
                    logger.info(
                        f"Token map built: {len(self.token_map)} symbols mapped",
                        extra={"reason_code": "TOKEN_MAP_BUILT"},
                    )

            return True

        except Exception as exc:
            logger.error(f"Failed to sync instruments: {exc}", exc_info=True)
            if not self.nifty500_symbols:
                self._use_fallback_list()
            return False

    def get_token(self, symbol: str) -> Optional[str]:
        """
        Return the m.Stock instrument token for *symbol*, or ``None`` if not
        mapped.

        Parameters
        ----------
        symbol : str
            NSE trading symbol (e.g. ``"RELIANCE"``).
        """
        return self.token_map.get(symbol)

    def get_sector(self, symbol: str) -> str:
        """
        Return the sector classification string for *symbol*.

        Falls back to ``"Unknown"`` when the symbol is not in the map.

        Parameters
        ----------
        symbol : str
            NSE trading symbol.
        """
        return self.sector_map.get(symbol, "Unknown")

    def get_scannable_symbols(self) -> List[Dict]:
        """
        Return the list of instruments that the scanner can process.

        Each entry is a dict with keys: ``symbol``, ``token``, ``exchange``,
        ``sector``.

        When token mapping is available (``self.instruments`` is populated) that
        list is returned directly.  Otherwise every symbol in
        ``nifty500_symbols`` is returned with ``token`` set to the symbol
        string itself (caller must handle the missing-token case).
        """
        if self.instruments:
            return self.instruments

        # Fallback: return symbols without real tokens
        return [
            {
                "symbol": s,
                "token": s,
                "exchange": "NSE",
                "sector": self.sector_map.get(s, "Unknown"),
            }
            for s in self.nifty500_symbols
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _download_nifty500_list(self) -> None:
        """
        Load Nifty 500 constituents.
        Priority:
          1. Local CSV (config/ind_nifty500list.csv) - 100% reliable
          2. NSE JSON API (marketWatchApi)
          3. Built-in hardcoded fallback list
        """
        try:
            import pandas as pd
            import time
            
            # ── 1. Try Local CSV First ────────────────────────────────────────
            csv_path = "/app/config/ind_nifty500list.csv"
            
            if os.path.exists(csv_path):
                with open(csv_path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                    
                lines = raw_text.splitlines()
                header_row_idx = 0
                for i, line in enumerate(lines):
                    if "symbol" in line.lower():
                        header_row_idx = i
                        break

                df = pd.read_csv(
                    io.StringIO(raw_text),
                    skiprows=header_row_idx,
                    on_bad_lines="skip",
                    dtype=str,
                )
                df.columns = [c.strip() for c in df.columns]

                symbol_col = next((c for c in df.columns if "symbol" in c.lower()), None)
                sector_col = next((c for c in df.columns if "industry" in c.lower() or "sector" in c.lower()), None)

                if symbol_col:
                    symbols = df[symbol_col].str.strip().dropna().tolist()
                    self.nifty500_symbols = [s for s in symbols if s and s.lower() != "symbol"]

                    if sector_col:
                        for _, row in df.iterrows():
                            sym = str(row[symbol_col]).strip()
                            sec = str(row.get(sector_col, "Unknown")).strip()
                            if sym and sym.lower() != "symbol" and sym != "nan":
                                self.sector_map[sym] = sec if sec != "nan" else "Unknown"

                    logger.info(
                        f"✅ Nifty 500 loaded from local CSV: {len(self.nifty500_symbols)} symbols",
                        extra={"reason_code": "NIFTY500_LOADED_FROM_CSV"},
                    )
                    return
                else:
                    logger.warning("Symbol column not found in local CSV — falling back to API")

            # ── 2. Try NSE API ────────────────────────────────────────────────
            HEADERS = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
            API_URL = "https://www.nseindia.com/api/NextApi/apiClient/marketWatchApi?functionName=getIndicesData&symbol=NIFTY%20500"

            loop = asyncio.get_running_loop()
            def _fetch():
                session = requests.Session()
                session.headers.update(HEADERS)
                session.get("https://www.nseindia.com/", timeout=10)
                time.sleep(1)
                api_resp = session.get(API_URL, timeout=15)
                api_resp.raise_for_status()
                return api_resp.json()

            data = await loop.run_in_executor(None, _fetch)
            stocks = data.get("data", [])
            
            # NSE API sometimes nests the array under data -> data
            if isinstance(stocks, dict):
                stocks = stocks.get("data", [])
            
            symbols = []
            for item in stocks:
                if not isinstance(item, dict):
                    continue
                    
                sym = (item.get("symbol") or "").strip()
                # Skip the index itself if returned
                if not sym or sym == "NIFTY 500" or sym.startswith("NIFTY"):
                    continue
                
                meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
                industry = (
                    meta.get("industry")
                    or item.get("industry")
                    or "Unknown"
                ).strip()
                
                symbols.append(sym)
                self.sector_map[sym] = industry or "Unknown"

            if symbols:
                self.nifty500_symbols = symbols
                logger.info(
                    f"✅ Nifty 500 loaded from NSE API: {len(symbols)} symbols",
                    extra={"reason_code": "NIFTY500_LOADED_FROM_NSE_API"},
                )
                return
            else:
                raise ValueError("Empty data from NSE API")

        except Exception as exc:
            logger.warning(
                f"NSE API fetch/parse failed ({exc}) — using built-in fallback list",
                extra={"reason_code": "NIFTY500_FALLBACK_API_ERROR"},
            )
            self._use_fallback_list()

    def _use_fallback_list(self) -> None:
        """
        Populate ``nifty500_symbols`` from the static ``NIFTY500_SECTOR_MAP``
        when the NSE API/CSV is unreachable.
        """
        self.nifty500_symbols = list(NIFTY500_SECTOR_MAP.keys())
        logger.info(
            f"Using built-in fallback list: {len(self.nifty500_symbols)} symbols",
            extra={"reason_code": "NIFTY500_FALLBACK_LIST_USED"},
        )

    async def _build_token_map(self, instruments_data: list) -> None:
        """
        Iterate over the m.Stock instrument master and map Nifty 500 symbols
        to their instrument tokens.

        Parameters
        ----------
        instruments_data : list
            Raw list of instrument dicts returned by ``mconnect.get_instruments()``.
            Expected dict keys (any of these are accepted):
            ``tradingsymbol`` / ``Symbol`` / ``symbol``,
            ``instrument_token`` / ``Token`` / ``token``,
            ``exchange`` / ``Exchange``.
        """
        nifty_set: set = set(self.nifty500_symbols)

        for item in instruments_data:
            if not isinstance(item, dict):
                continue

            symbol: str = (
                item.get("tradingsymbol")
                or item.get("Symbol")
                or item.get("symbol", "")
            )
            token: str = str(
                item.get("instrument_token")
                or item.get("Token")
                or item.get("token", "")
            )
            exchange: str = str(
                item.get("exchange") or item.get("Exchange", "NSE")
            )

            if symbol and token and exchange == "NSE" and symbol in nifty_set:
                self.token_map[symbol] = token
                sector = self.sector_map.get(symbol, "Unknown")
                self.instruments.append(
                    {
                        "symbol": symbol,
                        "token": token,
                        "exchange": exchange,
                        "sector": sector,
                    }
                )
