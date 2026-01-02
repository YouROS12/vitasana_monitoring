"""
Authentication session management with cookie persistence.
Handles login flow, token management, and saves cookies to config for reuse.
Supports multiple credentials for load balancing.
"""

import requests
import logging
import threading
import time
import yaml
from urllib.parse import unquote
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from itertools import cycle

logger = logging.getLogger(__name__)


@dataclass
class Credential:
    """Single credential set."""
    name: str
    username: str
    password: str
    client_id: str


@dataclass
class SessionConfig:
    """Thread-safe session configuration."""
    laravel_session: str
    xsrf_token: str
    cookies: Dict[str, str]
    headers: Dict[str, str]
    credential_name: str
    auth: tuple  # (username, password) for HTTP Basic Auth


def _get_config_path() -> Path:
    """Get path to config.yaml."""
    return Path(__file__).resolve().parent.parent.parent / "config.yaml"


def _load_config() -> dict:
    """Load config.yaml."""
    config_path = _get_config_path()
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _save_cookies_to_config(laravel_session: str, xsrf_token: str):
    """Save cookies to config.yaml for later use."""
    config_path = _get_config_path()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if 'session_cookies' not in config:
            config['session_cookies'] = {}
        
        config['session_cookies']['laravel_session'] = laravel_session
        config['session_cookies']['xsrf_token'] = xsrf_token
        config['session_cookies']['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Cookies saved to config.yaml at {datetime.now()}")
        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


def _get_saved_cookies() -> Optional[Tuple[str, str]]:
    """Get saved cookies from config.yaml if valid."""
    try:
        config = _load_config()
        cookies = config.get('session_cookies', {})
        
        laravel = cookies.get('laravel_session', '')
        xsrf = cookies.get('xsrf_token', '')
        
        if laravel and xsrf:
            logger.info("Found saved cookies in config.yaml")
            return laravel, xsrf
    except Exception as e:
        logger.debug(f"Could not load saved cookies: {e}")
    
    return None


def perform_login(username: str, password: str, login_url: str, user_agent: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Perform login and return (laravel_session, xsrf_token, decoded_xsrf, auth_tuple).
    
    Returns:
        Tuple of (laravel_session, xsrf_token, decoded_xsrf, client_id) on success, None on failure
    """
    from bs4 import BeautifulSoup
    
    logger.info(f"Performing login for {username}...")
    
    session = requests.Session()
    session.headers.update({'User-Agent': user_agent})
    
    try:
        # Step 1: Get login page
        response = session.get(login_url, timeout=30)
        response.raise_for_status()
        
        # Get XSRF from cookies
        initial_xsrf = session.cookies.get('XSRF-TOKEN')
        
        # Parse HTML for form token
        soup = BeautifulSoup(response.text, 'lxml')
        token_input = soup.find('input', {'name': '_token'})
        if not token_input or not token_input.get('value'):
            logger.error("Could not find _token in login form")
            return None
        
        form_token = token_input.get('value')
        
        # Step 2: Submit login
        login_data = {
            '_token': form_token,
            'username': username,
            'password': password,
            'remember': '1'
        }
        
        headers = {
            'Referer': login_url,
            'Origin': 'https://webdash.lacdp.ma',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        if initial_xsrf:
            headers['X-XSRF-TOKEN'] = initial_xsrf
        
        login_response = session.post(
            login_url,
            data=login_data,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )
        
        # Check result
        laravel_session = session.cookies.get('laravel_session')
        xsrf_token = session.cookies.get('XSRF-TOKEN')
        
        if not laravel_session or not xsrf_token:
            logger.error("Login failed - missing cookies")
            if 'login' in login_response.url.lower():
                logger.error("Landed back on login page - check credentials")
            return None
        
        logger.info("Login successful!")
        
        # Decode XSRF for header use
        decoded_xsrf = unquote(xsrf_token)
        
        return laravel_session, xsrf_token, decoded_xsrf
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return None


class AuthSession:
    """
    Manages authenticated sessions with cookie persistence.
    Reads cookies from config, or performs login if needed.
    """
    
    def __init__(
        self,
        credentials: List[Credential],
        login_url: str,
        user_agent: str = "Vitasana/1.0"
    ):
        self.credentials = credentials
        self.login_url = login_url
        self.user_agent = user_agent
        
        self._session_config: Optional[SessionConfig] = None
        self._lock = threading.Lock()
    
    def _build_session_config(
        self, 
        laravel_session: str, 
        xsrf_token: str, 
        credential: Credential
    ) -> SessionConfig:
        """Build SessionConfig from cookies."""
        decoded_xsrf = unquote(xsrf_token)
        
        return SessionConfig(
            laravel_session=laravel_session,
            xsrf_token=decoded_xsrf,
            cookies={
                'laravel_session': laravel_session,
                'XSRF-TOKEN': xsrf_token,
            },
            headers={
                'User-Agent': self.user_agent,
                'X-XSRF-TOKEN': decoded_xsrf,
                'Accept': 'application/json',
            },
            credential_name=credential.name,
            auth=(credential.username, credential.password)
        )
    
    def get_session_config(self) -> Optional[SessionConfig]:
        """
        Get session config. Tries saved cookies first, then login.
        """
        with self._lock:
            if self._session_config:
                return self._session_config
        
        # Try saved cookies first
        saved = _get_saved_cookies()
        if saved:
            laravel, xsrf = saved
            config = self._build_session_config(laravel, xsrf, self.credentials[0])
            with self._lock:
                self._session_config = config
            return config
        
        # No saved cookies - perform login
        logger.info("No saved cookies, performing fresh login...")
        credential = self.credentials[0]
        
        result = perform_login(
            credential.username,
            credential.password,
            self.login_url,
            self.user_agent
        )
        
        if result:
            laravel, xsrf, decoded_xsrf = result
            
            # Save to config for next time
            _save_cookies_to_config(laravel, xsrf)
            
            config = self._build_session_config(laravel, xsrf, credential)
            with self._lock:
                self._session_config = config
            return config
        
        return None
    
    def refresh_cookies(self, credential_index: int = 0) -> bool:
        """Force a fresh login and save cookies."""
        credential = self.credentials[credential_index]
        
        result = perform_login(
            credential.username,
            credential.password,
            self.login_url,
            self.user_agent
        )
        
        if result:
            laravel, xsrf, decoded_xsrf = result
            _save_cookies_to_config(laravel, xsrf)
            
            config = self._build_session_config(laravel, xsrf, credential)
            with self._lock:
                self._session_config = config
            return True
        
        return False
    
    def invalidate_session(self):
        """Clear cached session (forces re-read or re-login)."""
        with self._lock:
            self._session_config = None
        logger.info("Session invalidated")


def create_auth_session_from_config() -> AuthSession:
    """Create AuthSession from config file with all credentials."""
    from ..core.config import get_config
    
    config = get_config()
    
    # Load credentials list
    creds_list = config.get('credentials', default=[])
    
    credentials = []
    if isinstance(creds_list, list):
        for i, cred in enumerate(creds_list):
            credentials.append(Credential(
                name=cred.get('name', f'Account_{i+1}'),
                username=cred.get('username'),
                password=cred.get('password'),
                client_id=cred.get('client_id')
            ))
    
    if not credentials:
        raise ValueError("No credentials found in config")
    
    logger.info(f"Loaded {len(credentials)} credential(s): {[c.name for c in credentials]}")
    
    return AuthSession(
        credentials=credentials,
        login_url=config.get('api', 'login_url'),
        user_agent=config.get('api', 'user_agent', default='Vitasana/1.0')
    )
