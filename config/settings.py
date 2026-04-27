import os
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY: str = os.environ["RAPIDAPI_KEY"]
GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]

GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

CRAWL_MAX_DEPTH: int = int(os.getenv("CRAWL_MAX_DEPTH", "2"))
CRAWL_MAX_PAGES: int = int(os.getenv("CRAWL_MAX_PAGES", "10"))
CRAWL_DELAY_SECONDS: float = float(os.getenv("CRAWL_DELAY_SECONDS", "1.0"))
REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))

MAPS_API_HOST = "maps-data.p.rapidapi.com"
MAPS_API_BASE_URL = f"https://{MAPS_API_HOST}"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
