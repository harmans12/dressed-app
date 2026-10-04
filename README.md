# DRESSED v18.1

Stable root-level Render Docker deployment.

IMPORTANT: The GitHub repository root must contain `Dockerfile`, `requirements.txt`, `index.html`, `manifest.webmanifest`, the icon PNGs, `render.yaml`, and `server/`.

This layout deliberately avoids `COPY public ./public`, which caused the Render build failure when `/public` was not present in the Docker build context.

Invitation processing is server-side with PDF text extraction, OCR fallback, and ffmpeg frame extraction for videos. No OpenAI API key is required.


v18.1 fixes invitation-reader stalls by bounding Tesseract OCR work and adding a 120-second client timeout with a clear error message.
