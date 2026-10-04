import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "Kubernetes FaaS Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security / JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "faas-super-secret-key-change-in-production-123456789")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # Database (PostgreSQL with SQLite fallback)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./faas_metadata.db")
    
    # Docker & Registry
    DOCKER_REGISTRY: str = os.getenv("DOCKER_REGISTRY", "localhost:5000")
    DOCKER_SOCKET: str = os.getenv("DOCKER_SOCKET", "")  # empty uses default docker client
    
    # Kubernetes Configuration
    K8S_IN_CLUSTER: bool = os.getenv("K8S_IN_CLUSTER", "false").lower() == "true"
    K8S_NAMESPACE: str = os.getenv("K8S_NAMESPACE", "faas-fn")
    
    # Function Lifecycle & Scale-to-Zero
    IDLE_TIMEOUT_SECONDS: int = int(os.getenv("IDLE_TIMEOUT_SECONDS", "60"))
    REAPER_INTERVAL_SECONDS: int = int(os.getenv("REAPER_INTERVAL_SECONDS", "10"))
    DEFAULT_MEMORY_LIMIT: str = "256Mi"
    DEFAULT_CPU_LIMIT: str = "500m"
    DEFAULT_TIMEOUT_SECONDS: int = 10

    # Runs user code with exec() inside the API process when Kubernetes is unavailable.
    # UNSAFE (arbitrary code execution on the host) - only enable for local development/tests.
    # Public (API key) invocation limits
    API_KEY_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("API_KEY_RATE_LIMIT_PER_MINUTE", "120"))
    MAX_PAYLOAD_BYTES: int = int(os.getenv("MAX_PAYLOAD_BYTES", str(1024 * 1024)))
    MAX_API_KEYS_PER_FUNCTION: int = 10

    ALLOW_LOCAL_SANDBOX: bool = os.getenv("ALLOW_LOCAL_SANDBOX", "false").lower() == "true"

settings = Settings()
