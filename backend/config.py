import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # MongoDB Atlas settings
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = "order_to_cash_db"
    
    # Ollama settings
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "qwen2.5:3b")
    
    # CORS settings
    ALLOWED_ORIGINS: list = [
        "http://localhost:5173",  # Vite React default
        "http://localhost:3000",
    ]

settings = Settings()
