from dotenv import load_dotenv
load_dotenv()
import os

class Settings:
    # llm
    MODEL = "deepseek-v4-pro"
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL")

    # 中国气象局
    CMA_API_KEY = os.getenv("CMA_API_KEY")
    CMA_BASE_URL = os.getenv("CMA_BASE_URL")
    CMA_USER_ID = os.getenv("CMA_USER_ID")

    # 高德地图
    AMAP_API_KEY = os.getenv("AMAP_API_KEY")
    AMAP_BASE_URL = os.getenv("AMAP_BASE_URL")

    # 向量模型
    EMBEDDING_MODEL = "text-embedding-v3"
    EMBEDDING_DIM=1024
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")

    # Mineru文档解析
    MINERU_TOKEN = os.getenv("MINERU_TOKEN")

    # Milvus
    MILVUS_URI = os.getenv("MILVUS_URI")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN")

    # Redis
    REDIS_URL = os.getenv("REDIS_URL")

    # 途牛
    TUNIU_API_KEY = os.getenv("TUNIU_API_KEY")
    TUNIU_BASE_URL = os.getenv("TUNIU_BASE_URL")

    # 飞猪
    FLYAI_API_KEY= os.getenv("FLYAI_API_KEY")

    # PostgreSOL
    POSTGRE_URI=os.getenv("POSTGRE_URI")

    # rerank模型
    RERANK_MODEL="qwen3.7-text-rerank"
    RERANK_BASE_URL=os.getenv("RERANK_BASE_URL")

settings = Settings()