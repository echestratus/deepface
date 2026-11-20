"""Run with: python -m uvicorn face_demo.app:app --host 127.0.0.1 --port 8000"""

from .config import settings

import logging
import asyncio
import re
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from .engine import PIPELINE, FaceEngine, FaceError, cosine_distance, decode_image
from .sessions import Sessions
from .storage import Store
from .enrollment import Enrollments
from .guidance import empty_checks

logger = logging.getLogger("face_demo")
STATIC = Path(__file__).parent / "static"


class SessionInput(BaseModel):
    user_id: str = Field(min_length=36, max_length=36)


class EnrollmentInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254)
    consent: bool


def create_app(engine=None, data_dir=None):
    engine = engine or FaceEngine()
    store = Store((data_dir or settings.data_dir) / "users.sqlite3")
    sessions = Sessions(settings.required_matches)
    enrollments = Enrollments(settings.capture_matches)

    @asynccontextmanager
    async def lifespan(application):
        await run_in_threadpool(engine.load)
        async def cleanup():
            while True:
                await asyncio.sleep(15)
                enrollments.purge()
        cleaner = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            cleaner.cancel()
            with suppress(asyncio.CancelledError):
                await cleaner
            enrollments.items.clear()

    app = FastAPI(title="Cari Kerja · Face Lab", version="1.0.0", lifespan=lifespan)
    app.state.engine, app.state.store, app.state.sessions = engine, store, sessions
    app.state.enrollments = enrollments
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if request.headers.get("x-face-demo") != "local" or (
                origin and origin != str(request.base_url).rstrip("/")
            ):
                return JSONResponse({"detail": "Permintaan harus berasal dari aplikasi lokal."}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Ukuran request tidak valid."}, status_code=400)
            if size > settings.max_image_bytes + 64 * 1024:
                return JSONResponse({"detail": "Ukuran foto maksimal 5 MB."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
        # Swagger uses CDN assets; keep it available as an integration reference.
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        return response

    @app.get("/", include_in_schema=False)
    @app.get("/register", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/verify", include_in_schema=False)
    def verification_page():
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8").replace(
            'data-page="register"', 'data-page="verify"').replace(
            "Pendaftaran wajah · Face Lab", "Uji verifikasi · Face Lab"))

    @app.get("/api/health")
    def health():
        return {"ready": engine.ready, "backend": "onnx", "provider": "CPUExecutionProvider",
                "model": "SFace", "detector": "yunet", "threads": settings.threads,
                "anti_spoofing": settings.anti_spoofing, "threshold": settings.threshold,
                "required_matches": settings.required_matches,
                "frame_interval_ms": settings.frame_interval_ms, "max_side": settings.max_side,
                "guide_interval_ms": settings.guide_interval_ms, "capture_matches": settings.capture_matches,
                "enrollment_checks": empty_checks()}

    @app.get("/api/users")
    def list_users():
        return {"users": store.list_users()}

    def get_user(user_id):
        user = store.get(user_id)
        if not user:
            raise HTTPException(404, "Data pengguna tidak ditemukan.")
        return user

    async def read_image(photo):
        content = await photo.read(settings.max_image_bytes + 1)
        await photo.close()
        return await run_in_threadpool(decode_image, content)

    def validate_identity(name, email, consent):
        name, email = name.strip(), email.strip().lower()
        if len(name) < 2 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(422, "Isi nama dan alamat email yang valid.")
        if not consent:
            raise HTTPException(422, "Persetujuan penyimpanan foto dan data wajah diperlukan.")
        return name, email

    @app.post("/api/enrollments", status_code=201)
    def begin_enrollment(payload: EnrollmentInput):
        name, email = validate_identity(payload.name, payload.email, payload.consent)
        if store.email_exists(email):
            raise HTTPException(409, "Email sudah terdaftar. Gunakan halaman uji verifikasi atau hapus data lamanya.")
        try:
            token = enrollments.create(name, email)
        except ValueError as err:
            raise HTTPException(429, str(err)) from err
        return {"enrollment_id": token, "expires_in": 300, "required_frames": settings.capture_matches}

    def enrollment_draft(token, *, begin=False, frame=False):
        try:
            return enrollments.begin(token, frame=frame) if begin else enrollments.get(token)
        except KeyError as err:
            raise HTTPException(404, "Sesi pendaftaran berakhir. Mulai kamera kembali.") from err
        except ValueError as err:
            raise HTTPException(429, str(err)) from err

    @app.post("/api/enrollments/{enrollment_id}/frames")
    async def guide(enrollment_id: str, photo: UploadFile = File(...)):
        draft = enrollment_draft(enrollment_id, begin=True, frame=True)
        start = time.perf_counter()
        try:
            if draft.completed_user:
                raise HTTPException(409, "Identitas sudah tersimpan. Buka halaman uji verifikasi.")
            if draft.sample:
                return {"status": "captured", "captured": True, "ready": True,
                        "message": "Foto sudah diambil. Tinjau foto sebelum menyimpan.",
                        "consecutive_ready": draft.streak, "required_frames": settings.capture_matches}
            image = await read_image(photo)
            result = await run_in_threadpool(engine.guide, image)
            capture_now = enrollments.observe(draft, result)
            if capture_now:
                # Recheck the exact accepted frame with the same enrollment embedding pipeline.
                draft.sample = await run_in_threadpool(engine.extract, image, live=False)
                result.update(status="captured", captured=True,
                              message="Foto berhasil diambil. Tinjau foto lalu simpan identitas.")
            else:
                result["captured"] = False
                if result["ready"]:
                    result["message"] = "Posisi sudah sesuai. Tahan wajah tetap stabil untuk pengambilan otomatis."
            result.update(consecutive_ready=draft.streak, required_frames=settings.capture_matches,
                          latency_ms=round((time.perf_counter() - start) * 1000, 1))
            return result
        except FaceError as err:
            draft.streak, draft.last_box = 0, None
            return {"status": err.code, "captured": False, "ready": False, "message": str(err),
                    "checks": empty_checks(), "face": None, "consecutive_ready": 0,
                    "required_frames": settings.capture_matches}
        except HTTPException:
            raise
        except Exception as err:
            draft.streak, draft.last_box = 0, None
            logger.exception("Panduan pendaftaran gagal")
            raise HTTPException(503, "Panduan kamera gagal diproses. Mulai kamera kembali.") from err
        finally:
            enrollments.finish(draft)

    @app.get("/api/enrollments/{enrollment_id}/photo", include_in_schema=False)
    def captured_photo(enrollment_id: str):
        draft = enrollment_draft(enrollment_id)
        if not draft.sample:
            raise HTTPException(409, "Foto belum diambil atau sudah disimpan.")
        return Response(draft.sample.photo, media_type="image/jpeg")

    @app.post("/api/enrollments/{enrollment_id}/complete", status_code=201)
    def complete_enrollment(enrollment_id: str):
        draft = enrollment_draft(enrollment_id, begin=True)
        try:
            if draft.completed_user:
                return {"user": draft.completed_user, "verification_url": "/verify?user=" + draft.completed_user["id"]}
            if not draft.sample:
                raise HTTPException(409, "Ikuti panduan kamera sampai foto berhasil diambil terlebih dahulu.")
            try:
                user = store.create(draft.name, draft.email, draft.sample, consent_at=draft.consent_at)
            except sqlite3.IntegrityError as err:
                raise HTTPException(409, "Email sudah terdaftar. Mulai ulang dengan email lain atau buka halaman uji.") from err
            draft.completed_user, draft.sample = user, None
            return {"user": user, "verification_url": "/verify?user=" + user["id"]}
        finally:
            enrollments.finish(draft)

    @app.delete("/api/enrollments/{enrollment_id}", status_code=204)
    def cancel_enrollment(enrollment_id: str):
        enrollments.remove(enrollment_id)
        return Response(status_code=204)

    @app.post("/api/users", status_code=201)
    async def enroll(name: str = Form(..., min_length=2, max_length=100),
                     email: str = Form(..., max_length=254),
                     consent: bool = Form(False), photo: UploadFile = File(...)):
        name, email = validate_identity(name, email, consent)
        try:
            image = await read_image(photo)
            sample = await run_in_threadpool(engine.extract, image, live=False)
            user = await run_in_threadpool(store.create, name, email, sample)
        except FaceError as err:
            raise HTTPException(422, {"code": err.code, "message": str(err)}) from err
        except sqlite3.IntegrityError as err:
            raise HTTPException(409, "Email sudah terdaftar. Pilih pengguna tersebut atau hapus data lamanya.") from err
        except Exception as err:
            logger.exception("Pendaftaran gagal")
            raise HTTPException(503, "Pemrosesan wajah gagal. Periksa log server dan coba lagi.") from err
        return {"user": user, "message": "Pendaftaran berhasil. Lanjutkan ke verifikasi kamera."}

    @app.get("/api/users/{user_id}/photo", include_in_schema=False)
    def photo(user_id: str):
        return Response(get_user(user_id)["photo"], media_type="image/jpeg")

    @app.delete("/api/users/{user_id}", status_code=204)
    def delete_user(user_id: str):
        get_user(user_id)
        store.delete(user_id)
        sessions.remove_user(user_id)
        enrollments.remove_user(user_id)
        return Response(status_code=204)

    @app.post("/api/sessions", status_code=201)
    def create_session(payload: SessionInput):
        get_user(payload.user_id)
        try:
            token = sessions.create(payload.user_id)
        except ValueError as err:
            raise HTTPException(429, str(err)) from err
        return {"session_id": token, "expires_in": 180, "required_matches": settings.required_matches}

    @app.post("/api/sessions/{session_id}/frames")
    async def verify(session_id: str, photo: UploadFile = File(...)):
        try:
            session = sessions.begin(session_id)
        except KeyError as err:
            raise HTTPException(404, "Sesi berakhir. Mulai verifikasi kembali.") from err
        except ValueError as err:
            raise HTTPException(429, str(err)) from err
        start = time.perf_counter()
        matched = False
        try:
            user = get_user(session.user_id)
            if user["pipeline"] != PIPELINE:
                raise HTTPException(409, "Model data lama berbeda. Daftarkan ulang pengguna.")
            image = await read_image(photo)
            sample = await run_in_threadpool(engine.extract, image, live=True)
            stored = np.frombuffer(user["embedding"], dtype=np.float32)
            distance = cosine_distance(stored, sample.embedding)
            matched = distance <= settings.threshold
            result = {"status": "matching" if matched else "mismatch", "matched": matched,
                      "distance": round(distance, 4), "threshold": settings.threshold,
                      "face": sample.face, "frame": {"width": sample.width, "height": sample.height},
                      "message": "Wajah cocok. Tahan posisi." if matched else "Wajah tidak cocok dengan identitas yang dipilih.",
                      "anti_spoofing": settings.anti_spoofing, "spoof_score": sample.spoof_score}
        except FaceError as err:
            result = {"status": err.code, "matched": False, "message": str(err),
                      "distance": None, "threshold": settings.threshold, "face": None}
        except HTTPException:
            raise
        except Exception as err:
            logger.exception("Verifikasi gagal")
            raise HTTPException(503, "Pemrosesan wajah gagal. Periksa log server dan coba lagi.") from err
        finally:
            streak = sessions.finish(session, matched)
        verified = streak >= settings.required_matches
        if verified:
            result.update(status="verified", message="Wajah terverifikasi untuk identitas yang dipilih.")
        result.update(verified=verified, consecutive_matches=streak,
                      required_matches=settings.required_matches,
                      latency_ms=round((time.perf_counter() - start) * 1000, 1))
        return result

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
