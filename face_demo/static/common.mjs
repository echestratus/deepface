export const $ = (id) => document.getElementById(id);
export const titles = {
  ready: "Posisi sudah sesuai", captured: "Foto berhasil diambil", matching: "Wajah cocok, tahan posisi…",
  verified: "Identitas terverifikasi", mismatch: "Wajah tidak cocok", no_face: "Wajah belum terdeteksi",
  multiple_faces: "Hanya satu wajah yang diperbolehkan", too_far: "Dekatkan wajah", too_close: "Mundur sedikit",
  off_center: "Posisikan wajah di tengah", pose: "Hadapkan wajah ke kamera", lighting: "Perbaiki pencahayaan",
  blurred: "Tahan wajah agar tidak buram", low_quality: "Perbaiki kualitas gambar",
  spoof_detected: "Frame ditolak filter anti-spoof", error: "Pemeriksaan terhenti",
  idle: "Menunggu kamera", paused: "Kamera dihentikan",
};

export async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "X-Face-Demo": "local", ...options.headers } });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const error = new Error(typeof detail === "string" ? detail : detail?.message || "Permintaan gagal. Periksa input dan coba lagi.");
    error.status = response.status;
    throw error;
  }
  return data;
}

export function notice(message) {
  $("global-message").textContent = message;
  $("global-message").classList.toggle("hidden", !message);
}

export function setResult(status, message, streak = 0, required = 3) {
  const good = ["verified", "captured"].includes(status);
  const bad = ["mismatch", "spoof_detected", "multiple_faces", "error"].includes(status);
  $("result-card").classList.toggle("good", good);
  $("result-card").classList.toggle("bad", bad);
  $("result-title").textContent = titles[status] || "Pemeriksaan wajah";
  $("result-message").textContent = message;
  $("streak").textContent = `${streak} / ${required}`;
  $("result-icon").textContent = good ? "✓" : bad ? "!" : "◎";
}

export function cameraDisplay(active, width = 640, height = 480) {
  $("camera-stage").classList.toggle("active", active);
  $("camera-empty").classList.toggle("hidden", active);
  $("camera-indicator").textContent = active ? "KAMERA AKTIF" : "KAMERA NONAKTIF";
  $("camera-size").textContent = `${width} × ${height}`;
  $("stop-camera").disabled = !active;
}

export function clearOverlay() {
  const canvas = $("overlay");
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}

export function drawOverlay(result, guide = false) {
  const canvas = $("overlay");
  if (!result.frame) { clearOverlay(); return; }
  canvas.width = result.frame.width;
  canvas.height = result.frame.height;
  const ctx = canvas.getContext("2d");
  if (guide) {
    ctx.strokeStyle = result.ready ? "#67dfb0" : "#b1bcec";
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 6]);
    ctx.beginPath();
    ctx.ellipse(canvas.width * .5, canvas.height * .46, canvas.width * .18, canvas.height * .26, 0, 0, 2 * Math.PI);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (result.face) {
    const { x, y, w, h } = result.face;
    ctx.strokeStyle = result.ready || result.matched ? "#67dfb0" : "#ffc684";
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
  }
}

export function cameraError(error) {
  if (error.name === "NotAllowedError") return "Akses kamera ditolak. Izinkan kamera pada browser lalu mulai kembali.";
  if (error.name === "NotFoundError") return "Tidak ada kamera terdeteksi. Sambungkan kamera lalu coba kembali.";
  if (error.name === "NotReadableError") return "Kamera sedang digunakan aplikasi lain. Tutup aplikasi tersebut lalu coba kembali.";
  return error.message;
}
