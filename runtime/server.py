from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# 确保项目根目录在 PYTHONPATH 中，使 `runtime.*` 模块可导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# 这个入口用于启动 Runtime 内部 FastAPI 服务，供 Go Gateway 通过内网 HTTP 调用。
def main() -> None:
    host = os.getenv("RUNTIME_HOST", "127.0.0.1")
    port = int(os.getenv("RUNTIME_PORT", "8001"))
    uvicorn.run("runtime.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
