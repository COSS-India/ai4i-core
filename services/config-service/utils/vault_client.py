"""
Vault Client for managing encrypted configurations in HashiCorp Vault
"""
import os
import logging
from typing import Optional, Dict, Any
import hvac
from hvac.exceptions import VaultError


logger = logging.getLogger(__name__)


class VaultClient:
    """
    Client for interacting with HashiCorp Vault to store and retrieve encrypted configurations.
    
    Uses the KV v2 secrets engine to store configurations in a structured path:
    secret/data/{environment}/{service_name}/{key}
    """
    
    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        mount_point: str = "secret",
        kv_version: int = 2,
    ):
        """
        Initialize Vault client.
        
        Args:
            vault_addr: Vault server address (defaults to VAULT_ADDR env var)
            vault_token: Vault authentication token (defaults to VAULT_TOKEN env var)
            mount_point: KV secrets engine mount point (default: "secret")
            kv_version: KV secrets engine version (default: 2 for KV v2)
        """
        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR", "http://vault:8200")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.kv_version = kv_version
        
        self._client: Optional[hvac.Client] = None
        self._connected = False
        
        if not self.vault_token:
            logger.warning("VAULT_TOKEN not provided. Vault operations will be disabled.")
        else:
            self._connect()
    
    def _connect(self) -> None:
        """Establish connection to Vault."""
        if not self.vault_token:
            return
        
        try:
            self._client = hvac.Client(url=self.vault_addr, token=self.vault_token)
            # Verify connection by checking if token is valid
            if self._client.is_authenticated():
                self._connected = True
                logger.info(f"Connected to Vault at {self.vault_addr}")
            else:
                logger.warning("Vault authentication failed. Vault operations will be disabled.")
                self._connected = False
        except Exception as e:
            logger.warning(f"Failed to connect to Vault: {e}. Vault operations will be disabled.")
            self._connected = False
            self._client = None
    
    def is_connected(self) -> bool:
        """Check if Vault client is connected and authenticated."""
        return self._connected and self._client is not None
    
    def _get_secret_path(self, environment: str, service_name: str, key: str) -> str:
        """
        Generate Vault secret path for a configuration.
        
        Path format: {environment}/{service_name}/{key}
        """
        return f"{environment}/{service_name}/{key}"
    
    def write_secret(
        self,
        environment: str,
        service_name: str,
        key: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Write a secret to Vault.
        
        Args:
            environment: Environment name (e.g., development, staging, production)
            service_name: Service name
            key: Configuration key
            value: Configuration value to store
            metadata: Optional metadata to store with the secret
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            logger.warning("Vault not connected. Cannot write secret.")
            return False
        
        try:
            secret_path = self._get_secret_path(environment, service_name, key)
            
            # Prepare data to write
            data = {"value": value}
            if metadata:
                data.update(metadata)
            
            if self.kv_version == 2:
                # KV v2 requires data to be nested under 'data'
                self._client.secrets.kv.v2.create_or_update_secret(
                    path=secret_path,
                    secret={"data": data},
                    mount_point=self.mount_point,
                )
            else:
                # KV v1
                self._client.secrets.kv.v1.create_or_update_secret(
                    path=secret_path,
                    secret=data,
                    mount_point=self.mount_point,
                )
            
            logger.debug(f"Successfully wrote secret to Vault: {secret_path}")
            return True
            
        except VaultError as e:
            logger.error(f"Vault error writing secret {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing secret to Vault: {e}")
            return False
    
    def read_secret(
        self,
        environment: str,
        service_name: str,
        key: str,
    ) -> Optional[str]:
        """
        Read a secret from Vault.
        
        Args:
            environment: Environment name
            service_name: Service name
            key: Configuration key
            
        Returns:
            Secret value if found, None otherwise
        """
        if not self.is_connected():
            logger.warning("Vault not connected. Cannot read secret.")
            return None
        
        try:
            secret_path = self._get_secret_path(environment, service_name, key)
            
            if self.kv_version == 2:
                # KV v2 returns data nested under 'data'
                response = self._client.secrets.kv.v2.read_secret_version(
                    path=secret_path,
                    mount_point=self.mount_point,
                )
                if response and "data" in response and "data" in response["data"]:
                    return response["data"]["data"].get("value")
            else:
                # KV v1
                response = self._client.secrets.kv.v1.read_secret(
                    path=secret_path,
                    mount_point=self.mount_point,
                )
                if response and "data" in response:
                    return response["data"].get("value")
            
            return None
            
        except VaultError as e:
            # 404 errors are expected for non-existent secrets
            if "not found" in str(e).lower() or "404" in str(e):
                logger.debug(f"Secret not found in Vault: {secret_path}")
            else:
                logger.error(f"Vault error reading secret {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading secret from Vault: {e}")
            return None
    
    def delete_secret(
        self,
        environment: str,
        service_name: str,
        key: str,
    ) -> bool:
        """
        Delete a secret from Vault.
        
        Args:
            environment: Environment name
            service_name: Service name
            key: Configuration key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            logger.warning("Vault not connected. Cannot delete secret.")
            return False
        
        try:
            secret_path = self._get_secret_path(environment, service_name, key)
            
            if self.kv_version == 2:
                # KV v2 delete
                self._client.secrets.kv.v2.delete_metadata_and_all_versions(
                    path=secret_path,
                    mount_point=self.mount_point,
                )
            else:
                # KV v1 delete
                self._client.secrets.kv.v1.delete_secret(
                    path=secret_path,
                    mount_point=self.mount_point,
                )
            
            logger.debug(f"Successfully deleted secret from Vault: {secret_path}")
            return True
            
        except VaultError as e:
            # 404 errors are expected for non-existent secrets
            if "not found" in str(e).lower() or "404" in str(e):
                logger.debug(f"Secret not found in Vault (already deleted): {secret_path}")
                return True
            logger.error(f"Vault error deleting secret {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting secret from Vault: {e}")
            return False
    
    def list_secrets(
        self,
        environment: str,
        service_name: Optional[str] = None,
    ) -> list:
        """
        List secrets in Vault for a given environment and optionally service.
        
        Args:
            environment: Environment name
            service_name: Optional service name to filter by
            
        Returns:
            List of secret paths
        """
        if not self.is_connected():
            logger.warning("Vault not connected. Cannot list secrets.")
            return []
        
        try:
            if service_name:
                path = f"{environment}/{service_name}"
            else:
                path = environment
            
            if self.kv_version == 2:
                response = self._client.secrets.kv.v2.list_secrets(
                    path=path,
                    mount_point=self.mount_point,
                )
            else:
                response = self._client.secrets.kv.v1.list_secrets(
                    path=path,
                    mount_point=self.mount_point,
                )
            
            if response and "data" in response and "keys" in response["data"]:
                return response["data"]["keys"]
            
            return []
            
        except VaultError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                logger.debug(f"No secrets found in Vault path: {path}")
            else:
                logger.error(f"Vault error listing secrets: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing secrets from Vault: {e}")
            return []

