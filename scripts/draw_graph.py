import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langgraph.checkpoint.memory import MemorySaver
from mcp_tools_rag.common.logging_config import setup_logging
from mcp_tools_rag.graph.graph import build_graph

logger = logging.getLogger(__name__)


async def main():
    graph = await build_graph(MemorySaver())

    output = Path("../mcp_tools_rag/image/graph.png")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        graph.get_graph().draw_mermaid_png(
            output_file_path=str(output),
            max_retries=3,
            retry_delay=1.0,
        )
        logger.info("graph image saved=%s", output)
    except Exception:
        logger.exception("graph image generation failed")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())