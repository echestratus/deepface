import { $, api, notice, setResult, cameraDisplay, clearOverlay, drawOverlay, cameraError } from "./common.mjs";
import { LiveCamera } from "./camera.mjs";

export function setupRegistration(config) {
  const camera = new LiveCamera($("camera"));
  let enrollment = null;
  let opening = false;
  let captured = false;
  let saving = false;
  let attempt = 0;

  function renderChecks(checks) {
    const rows = checks.map((check) => {
      const row = document.createElement("li");
      row.className = check.passed === true ? "passed" : check.passed === false ? "failed" : "pending";
      const icon = document.createElement("span");
      icon.textContent = check.passed === true ? "✓" : check.passed === false ? "!" : "·";
      icon.setAttribute("aria-hidden", "true");
      const label = document.createElement("span"); label.textContent = check.label;
      row.append(icon, label);
      return row;
    });
    $("guide-checks").replaceChildren(...rows);
  }

  function discard() {
    const previous = enrollment;
    enrollment = null;
    if (previous) void api(`/api/enrollments/${previous}`, { method: "DELETE", keepalive: true }).catch(() => {});
  }

  function reset(message = "Isi identitas lalu mulai kamera untuk mengambil foto.") {
    attempt += 1;
    camera.stop(); discard();
    opening = captured = false;
    $("identity-fields").disabled = false;
    $("register-start").disabled = false;
    $("register-start").textContent = "Mulai kamera & panduan";
    $("capture-review").classList.add("hidden");
    $("captured-stage").classList.add("hidden");
    $("capture-preview").removeAttribute("src");
    $("captured-stage").removeAttribute("src");
    cameraDisplay(false); clearOverlay();
    $("capture-progress").value = 0;
    $("capture-progress-label").textContent = "Menunggu posisi wajah yang sesuai";
    renderChecks(config.enrollment_checks);
    setResult("idle", message, 0, config.capture_matches);
    $("step-camera").classList.remove("current");
    $("step-save").classList.remove("current");
  }

  $("enrollment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (opening || camera.active || captured || saving) return;
    if (!event.target.reportValidity()) return;
    const identity = { name: $("name").value.trim(), email: $("email").value.trim(), consent: $("consent").checked };
    const currentAttempt = ++attempt;
    opening = true;
    $("identity-fields").disabled = true;
    $("register-start").disabled = true;
    $("register-start").textContent = "Membuka kamera…";
    $("stop-camera").disabled = false;
    $("enroll-message").textContent = "";
    await camera.start({
      interval: config.guide_interval_ms, maxSide: config.max_side,
      prepare: async (signal) => {
        const result = await api("/api/enrollments", { method: "POST", signal,
          headers: { "Content-Type": "application/json" }, body: JSON.stringify(identity) });
        if (currentAttempt !== attempt || signal.aborted) {
          void api(`/api/enrollments/${result.enrollment_id}`, { method: "DELETE", keepalive: true }).catch(() => {});
          return;
        }
        enrollment = result.enrollment_id;
      },
      requestFrame: (blob, signal) => {
        const form = new FormData(); form.append("photo", blob, "camera-frame.jpg");
        return api(`/api/enrollments/${enrollment}/frames`, { method: "POST", body: form, signal });
      },
      onStarted: () => {
        opening = false;
        cameraDisplay(true, camera.video.videoWidth, camera.video.videoHeight);
        $("register-start").textContent = "Panduan kamera aktif";
        $("step-camera").classList.add("current");
        setResult("idle", "Tempatkan wajah di dalam oval dan ikuti arahan yang muncul.");
        drawOverlay({ frame: { width: camera.video.videoWidth, height: camera.video.videoHeight } }, true);
      },
      onFrame: (result) => {
        renderChecks(result.checks || config.enrollment_checks);
        const count = result.consecutive_ready || 0;
        $("capture-progress").value = count;
        $("capture-progress-label").textContent = result.ready ? `${count} dari ${config.capture_matches} pemeriksaan siap` : "Sesuaikan wajah mengikuti arahan";
        setResult(result.status, result.message, count, config.capture_matches);
        drawOverlay(result, true);
        if (result.captured) {
          captured = true;
          camera.stop(); cameraDisplay(false); clearOverlay();
          $("camera-empty").classList.add("hidden");
          $("camera-indicator").textContent = "FOTO BERHASIL DIAMBIL";
          const photo = `/api/enrollments/${enrollment}/photo`;
          $("capture-preview").src = photo;
          $("captured-stage").src = photo;
          $("captured-stage").classList.remove("hidden");
          $("capture-review").classList.remove("hidden");
          $("register-start").textContent = "Foto siap ditinjau";
          $("step-camera").classList.remove("current");
          $("step-save").classList.add("current");
        }
      },
      onError: (error) => { reset(); setResult("error", cameraError(error)); },
      onEnded: () => reset("Kamera terputus. Mulai kembali untuk mengambil foto."),
    });
  });

  $("stop-camera").addEventListener("click", () => reset("Kamera dihentikan. Foto belum disimpan; mulai lagi saat siap."));
  $("retake-capture").addEventListener("click", () => {
    if (saving) return;
    reset(); $("enrollment-form").requestSubmit();
  });
  $("save-capture").addEventListener("click", async () => {
    if (!captured || !enrollment || saving) return;
    saving = true;
    $("save-capture").disabled = $("retake-capture").disabled = true;
    $("save-capture").textContent = "Menyimpan identitas…";
    try {
      const result = await api(`/api/enrollments/${enrollment}/complete`, { method: "POST" });
      enrollment = null;
      window.location.assign(`/verify?user=${encodeURIComponent(result.user.id)}`);
    } catch (error) {
      notice(error.message);
      if (error.status === 404) reset("Sesi foto berakhir. Mulai kamera untuk mengambil foto kembali.");
      saving = false;
      $("save-capture").disabled = $("retake-capture").disabled = false;
      $("save-capture").textContent = "Simpan & lanjut uji verifikasi";
    }
  });

  window.addEventListener("pagehide", () => { camera.stop(); discard(); });
  window.addEventListener("pageshow", (event) => { if (event.persisted) reset(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && (camera.active || opening)) reset("Kamera dihentikan karena tab disembunyikan. Mulai kembali saat siap.");
  });
  reset();
}
