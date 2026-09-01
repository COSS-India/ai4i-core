import logging

from app.core.database import get_primary_session_factory
from app.services.pay_per_use import inference_type_cache

logger = logging.getLogger(__name__)

async def warmup_inference_types() -> None:
    try:
        async with get_primary_session_factory()() as session:
            # sweep=True: a delete that landed while this process was down would
            # otherwise leave a stale per-name key answering lookups. Once
            # per process, so the scan is affordable here.
            types = await inference_type_cache.rebuild(session, sweep=True)
        logger.info("Inference type cache warmed: %d types.", len(types))
    except Exception as exc:
        # Never block startup on cache warming — every read has a DB fallback.
        logger.warning("Inference type cache warm-up skipped: %s", exc)


async def warmup_cache() -> None:
    await warmup_inference_types()
