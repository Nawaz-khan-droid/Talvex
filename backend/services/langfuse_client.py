"""
TALVEX — Langfuse LLM Observability Client
Optional integration. Requires LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST env vars.
If not configured, all tracing calls are no-ops.
"""
import os
import logging

logger = logging.getLogger("talvex.langfuse")

_langfuse_sdk = None
_initialized = False

def _get_client():
    global _langfuse_sdk, _initialized
    if _initialized:
        return _langfuse_sdk

    _initialized = True
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        logger.info("Langfuse not configured — LLM tracing disabled. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable.")
        return None

    try:
        from langfuse import Langfuse
        from langfuse.decorators import observe
        _langfuse_sdk = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        logger.info("Langfuse client initialized (host=%s)", host)
        return _langfuse_sdk
    except ImportError:
        logger.warning("langfuse package not installed. Run: pip install langfuse")
        return None
    except Exception as e:
        logger.error("Langfuse initialization failed: %s", e)
        return None

def trace_llm_call(name: str, model: str, input_data: dict, output_data: dict = None, metadata: dict = None, cost: dict = None):
    """Log an LLM call to Langfuse. No-op if not configured."""
    client = _get_client()
    if not client:
        return

    try:
        trace = client.trace(name=name, input=input_data, metadata=metadata or {})
        trace.generation(
            name=f"{name}_generation",
            model=model,
            input=input_data,
            output=output_data or {},
            usage=cost or {},
        )
        client.flush()
    except Exception as e:
        logger.warning("Langfuse trace failed: %s", e)

def shutdown():
    """Flush and close Langfuse client on shutdown."""
    client = _get_client()
    if client:
        try:
            client.flush()
            client.shutdown()
        except Exception:
            pass
