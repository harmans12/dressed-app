# DRESSED v15

Private personal event + outfit planner. This version uses a small server-side PDF/image/video reader so invitation processing does not depend on a browser's OCR support and does not require an OpenAI API key.

## Render
Create a **Web Service** from this repo using the Docker runtime. No environment variables are required.

The service serves the PWA and exposes `POST /api/extract` for invitation processing.

## Notes
- PDFs: embedded text first, OCR fallback.
- Images: multi-pass OCR with focused crops.
- Videos: FFmpeg samples frames and OCR reads visible invitation text.
- Video audio is not transcribed in this API-free version.
- Profiles/events/looks are stored in the browser using IndexedDB.
