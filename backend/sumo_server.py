"""Windows-only SUMO API; launch as the Windows user holding the SUMO license."""
from fastapi import FastAPI
from api.sumo import router

app = FastAPI(title='Windows SUMO Service', docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router, prefix='/api')


@app.get('/api/sumo/health')
def health():
    return {'status': 'ok', 'service': 'windows-sumo'}
