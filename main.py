"""
A-Share Quantitative Trading System
QMT_THS v2.0 (With FastAPI & Local Frontend)

Usage:
    python main.py            # Start FastAPI backend & local frontend (Default)
    python main.py server     # (Same as above)
    python main.py nightly    # Run nightly screening in CLI mode
    python main.py intraday   # Run intraday monitoring in CLI mode
"""

import sys
import uvicorn
from utils.logger import setup_logger

logger = setup_logger("qmt_ths")


def run_server():
    """Start the FastAPI server and local frontend."""
    logger.info("=" * 50)
    logger.info("Starting Captain Frontend Server...")
    logger.info("Access the dashboard at: http://127.0.0.1:8000")
    logger.info("=" * 50)
    
    # Run uvicorn programmatically
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")


def main():
    if len(sys.argv) < 2:
        # Default to new web dashboard mode
        run_server()
        return

    mode = sys.argv[1].lower()

    if mode in ("server", "web", "ui"):
        run_server()

    elif mode == "nightly":
        from core.engine_manager import manager
        logger.info("Running Nightly Screening in CLI mode...")
        # Since run_screening is a standalone script now
        from run_screening import run_screening
        run_screening()

    elif mode == "intraday":
        from core.engine_manager import manager
        logger.info("Running Intraday Engine in CLI mode...")
        manager.start_intraday()
        # Block the main thread since intraday runs in background thread
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop_intraday()
            logger.info("Exited by user.")

    elif mode in ("--help", "-h"):
        print("Usage: python main.py [server|nightly|intraday]")
        print("  server    — Start local frontend and API (Default)")
        print("  nightly   — Run post-market offline screening")
        print("  intraday  — Run real-time intraday monitoring")

    else:
        print(f"Unknown mode: {mode}. Use --help for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()