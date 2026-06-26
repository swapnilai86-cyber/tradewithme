import os
import asyncio
import hashlib
from typing import Optional, Dict
from backend.logging_config import get_logger

try:
    from tradingapi_a.mconnect import MConnect
except ImportError:
    MConnect = None

logger = get_logger(__name__)

class MStockAuth:
    def __init__(self):
        self.api_key = os.getenv("MSTOCK_API_KEY")
        self.client_id = os.getenv("MSTOCK_CLIENT_ID")
        self.password = os.getenv("MSTOCK_PASSWORD")
        
        self.mconnect_obj = MConnect() if MConnect else None
        self.access_token: Optional[str] = None
        self.is_authenticated = False

    def _get_cache_path(self) -> str:
        # Save session in the mapped config folder
        return os.path.join("config", "mstock_session.json")

    def _save_session(self):
        if not self.mconnect_obj:
            return
        
        token = getattr(self.mconnect_obj, "access_token", None)
        if not token:
            return

        import json
        cache_path = self._get_cache_path()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, "w") as f:
                json.dump({
                    "access_token": token,
                    "api_key": self.api_key
                }, f)
            logger.info("MStock session cached successfully")
        except Exception as e:
            logger.warning(f"Failed to cache session: {e}")

    async def auto_login(self) -> bool:
        """Attempt to restore session from cache and verify it."""
        if not self.mconnect_obj:
            return False

        import json
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return False

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            
            token = data.get("access_token")
            api_key = data.get("api_key")
            
            if not token or not api_key:
                return False

            # Inject cached tokens into SDK
            self.mconnect_obj.set_access_token(token)
            self.mconnect_obj.set_api_key(api_key)
            self.access_token = token
            self.api_key = api_key

            # Verify session is still valid by making a lightweight API call
            loop = asyncio.get_running_loop()
            logger.info("Verifying cached MStock session...")
            resp = await loop.run_in_executor(None, self.mconnect_obj.get_fund_summary)
            
            # Check if response indicates success
            if hasattr(resp, "status") and getattr(resp, "status", False) is True:
                self.is_authenticated = True
                logger.info("Cached session verified successfully! Auto-login complete.", extra={"reason_code": "AUTO_LOGIN_SUCCESS"})
                return True
            else:
                logger.warning("Cached session expired or invalid.")
                self.is_authenticated = False
                return False

        except Exception as e:
            logger.warning(f"Failed to restore cached session: {e}")
            return False

    async def login(self, totp_code: str) -> bool:
        if not self.mconnect_obj:
            logger.error("mStock-TradingApi-A SDK is not installed.")
            return False
            
        if not all([self.api_key, self.client_id, self.password]):
            logger.error("MStock credentials missing", extra={"reason": "MISSING_CREDENTIALS"})
            return False

        loop = asyncio.get_running_loop()
        try:
            # Step 1: Login with ID/Password
            logger.info("Initiating MStock login with credentials...")
            login_resp = await loop.run_in_executor(None, self.mconnect_obj.login, self.client_id, self.password)
            
            # Step 2: Generate Session
            if login_resp and getattr(login_resp, "status", False):
                request_token = login_resp.data.get("requestToken")
                
                # Type A API usually uses a static 'W' checksum when no API Secret is issued
                checksum = "W"
                
                await loop.run_in_executor(
                    None, 
                    self.mconnect_obj.generate_session, 
                    self.api_key, 
                    request_token, 
                    checksum
                )
                logger.info("Session generated successfully")
            
            # Step 3: Verify TOTP via provided code
            await loop.run_in_executor(None, self.mconnect_obj.verify_totp, self.api_key, totp_code)
            logger.info("TOTP verified successfully")
            
            self.is_authenticated = True
            self.access_token = getattr(self.mconnect_obj, "access_token", None)
            
            # Cache the session for future restarts
            self._save_session()
            
            return True
            
        except Exception as e:
            logger.error(f"MStock Login failed: {str(e)}", exc_info=True)
            self.is_authenticated = False
            raise e

    def get_auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}" if self.access_token else "",
            "Content-Type": "application/json"
        }
