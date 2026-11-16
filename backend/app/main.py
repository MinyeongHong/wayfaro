from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router
from app.api.analysis import router as analysis_router
from fastapi.exceptions import RequestValidationError
from app.services.matching.privacy import PrivateAnalysisMiddleware, private_validation_error

app = FastAPI(title="Wayfaro", description="Private, evidence-based CV and job description comparison", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cv_match_allowed_origins,
                   allow_credentials=True, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])
app.include_router(router)

app.include_router(analysis_router)
app.add_exception_handler(RequestValidationError, private_validation_error)
app.add_middleware(PrivateAnalysisMiddleware)
