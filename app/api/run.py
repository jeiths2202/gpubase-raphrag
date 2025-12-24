#!/usr/bin/env python3
"""
Run script for KMS API server
Usage: python -m app.api.run
"""
import uvicorn
from .core.config import api_settings


def main():
    """Run the FastAPI server"""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    KMS API Server                             ║
║           GPU Hybrid RAG Knowledge Management System          ║
╠═══════════════════════════════════════════════════════════════╣
║  Version: {api_settings.APP_VERSION:<10}                                      ║
║  Host:    {api_settings.HOST:<15}                                 ║
║  Port:    {api_settings.PORT:<5}                                        ║
║  Debug:   {str(api_settings.DEBUG):<5}                                        ║
╠═══════════════════════════════════════════════════════════════╣
║  Docs:    http://{api_settings.HOST}:{api_settings.PORT}/docs                          ║
║  ReDoc:   http://{api_settings.HOST}:{api_settings.PORT}/redoc                         ║
║  Health:  http://{api_settings.HOST}:{api_settings.PORT}/api/v1/health                 ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app.api.main:app",
        host=api_settings.HOST,
        port=api_settings.PORT,
        reload=api_settings.DEBUG,
        workers=1 if api_settings.DEBUG else api_settings.WORKERS,
        log_level="debug" if api_settings.DEBUG else "info"
    )


if __name__ == "__main__":
    main()
