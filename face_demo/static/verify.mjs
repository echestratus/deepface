import { $, api, notice, titles, setResult, cameraDisplay, clearOverlay, drawOverlay, cameraError } from "./common.mjs";
import { LiveCamera } from "./camera.mjs";

export async function setupVerification(config) {
  const camera = new LiveCamera($("camera"));
  let users = [];
  let session = null;
  let starting = false;
  let history = [];
  let count = 0;
  const initialUser = new URLSearchParams(window.location.search).get("user");
  $("camera-title").textContent = "Verifikasi wajah secara langsung";
  $("camera-empty-title").textContent = "Siap menguji kecocokan wajah";
  $("camera-empty-copy").textContent = "Pilih identitas lalu nyalakan kamera uji.";
  $("frame-rate").textContent = "1 pemeriksaan / detik";
  $("threshold").textContent = config.threshold.toFixed(3);
  setResult("idle", "Pilih identitas lalu nyalakan kamera untuk memulai uji.");

  function stop(message = "Kamera dihentikan. Riwayat hasil tetap dapat ditinjau di bawah.") {
    camera.stop(); starting = false; session = null;
    cameraDisplay(false); clearOverlay();
    $("verify-user").disabled = false;
    $("start-camera").disabled = !$("verify-user").value;
    $("start-camera").textContent = "Nyalakan kamera uji";
    setResult("paused", message);
  }

  function renderHistory() {
    $("frame-count").textContent = count;
    const rows = history.map((item) => {
      const row = document.createElement("tr");
      for (const value of [item.time, titles[item.status] || item.status,
        item.distance == null ? "—" : item.distance.toFixed(3),
        item.latency_ms == null ? "—" : `${Math.round(item.latency_ms)} ms`]) {
        const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
      }
      return row;
    });
    if (!rows.length) {
      const row = document.createElement("tr"); const cell = document.createElement("td");
      cell.colSpan = 4; cell.className = "empty-history"; cell.textContent = "Belum ada pemeriksaan kamera.";
      row.append(cell); rows.push(row);
    }
    $("frame-history").replaceChildren(...rows);
  }

  function clearResults() {
    history = []; count = 0; renderHistory();
    $("distance").textContent = $("latency").textContent = "—";
  }

  function reference() {
    const user = users.find((item) => item.id === $("verify-user").value);
    $("reference-card").classList.toggle("hidden", !user);
    if (user) {
      $("reference-photo").src = `/api/users/${encodeURIComponent(user.id)}/photo`;
      $("reference-photo").alt = `Foto referensi ${user.name}`;
      $("reference-name").textContent = user.name;
      $("reference-email").textContent = user.email;
    } else $("reference-photo").removeAttribute("src");
  }

  async function refreshUsers(selectedId) {
    const selected = selectedId || $("verify-user").value;
    users = (await api("/api/users")).users;
    const select = $("verify-user"); select.replaceChildren(new Option("Pilih identitas terdaftar", ""));
    for (const user of users) select.add(new Option(`${user.name} · ${user.email}`, user.id));
    if (users.some((user) => user.id === selected)) select.value = selected;
    else if (users.length === 1) select.value = users[0].id;
    if ((camera.active || starting) && select.value !== selected) { stop(); clearResults(); }
    $("start-camera").disabled = !select.value || camera.active || starting;
    $("no-identities").classList.toggle("hidden", users.length > 0);
    $("user-count").textContent = users.length;
    reference();
    const rows = users.map((user) => {
      const row = document.createElement("div"); row.className = "user-row";
      const image = document.createElement("img"); image.src = `/api/users/${encodeURIComponent(user.id)}/photo`;
      image.alt = `Foto ${user.name}`; image.loading = "lazy";
      const info = document.createElement("div"); info.className = "user-info";
      const name = document.createElement("strong"); name.textContent = user.name;
      const email = document.createElement("span"); email.textContent = user.email; info.append(name, email);
      const remove = document.createElement("button"); remove.className = "delete-user"; remove.type = "button";
      remove.textContent = "Hapus"; remove.setAttribute("aria-label", `Hapus data ${user.name}`);
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Hapus foto dan data wajah ${user.name} dari komputer ini?`)) return;
        remove.disabled = true;
        try {
          if (select.value === user.id) { stop(); clearResults(); }
          await api(`/api/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
          await refreshUsers(); notice("Identitas dan foto referensinya telah dihapus.");
        } catch (error) { notice(error.message); remove.disabled = false; }
      });
      row.append(image, info, remove); return row;
    });
    if (!rows.length) {
      const empty = document.createElement("p"); empty.className = "empty-users";
      empty.textContent = "Belum ada identitas. Buka halaman Daftarkan wajah untuk memulai."; rows.push(empty);
    }
    $("users-list").replaceChildren(...rows);
  }

  $("start-camera").addEventListener("click", async () => {
    const userId = $("verify-user").value;
    if (!userId || starting || camera.active) return;
    starting = true; clearResults();
    $("start-camera").disabled = true;
    $("start-camera").textContent = "Membuka kamera…";
    $("verify-user").disabled = true; $("stop-camera").disabled = false;
    await camera.start({
      interval: config.frame_interval_ms, maxSide: config.max_side,
      prepare: async (signal) => {
        const result = await api("/api/sessions", { method: "POST", signal,
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
        if (!signal.aborted) session = result.session_id;
      },
      requestFrame: (blob, signal) => {
        const form = new FormData(); form.append("photo", blob, "camera-frame.jpg");
        return api(`/api/sessions/${session}/frames`, { method: "POST", body: form, signal });
      },
      onStarted: () => {
        starting = false; cameraDisplay(true, camera.video.videoWidth, camera.video.videoHeight);
        $("start-camera").textContent = "Kamera uji aktif";
        setResult("idle", "Hadapkan wajah ke kamera. Membandingkan dengan identitas yang dipilih…");
      },
      onFrame: (result) => {
        setResult(result.status, result.message, result.consecutive_matches, config.required_matches);
        $("distance").textContent = result.distance == null ? "—" : result.distance.toFixed(3);
        $("latency").textContent = `${Math.round(result.latency_ms)} ms`;
        drawOverlay(result);
        count += 1;
        history.unshift({ ...result, time: new Intl.DateTimeFormat("id-ID", { timeStyle: "medium" }).format(new Date()) });
        history = history.slice(0, 10); renderHistory();
      },
      onError: (error) => { stop(); setResult("error", cameraError(error)); },
      onEnded: () => stop("Kamera terputus. Mulai uji kembali saat kamera siap."),
    });
  });
  $("stop-camera").addEventListener("click", () => stop());
  $("verify-user").addEventListener("change", () => { stop(); clearResults(); reference(); });
  $("refresh-users").addEventListener("click", () => refreshUsers().catch((error) => notice(error.message)));
  $("clear-history").addEventListener("click", clearResults);
  window.addEventListener("pagehide", () => camera.stop());
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) { stop(); clearResults(); void refreshUsers().catch((error) => notice(error.message)); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden && (camera.active || starting)) stop("Kamera dihentikan karena tab disembunyikan. Mulai uji kembali saat siap."); });
  await refreshUsers(initialUser); renderHistory();
}
