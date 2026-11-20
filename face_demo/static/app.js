import { $, api, notice } from "./common.mjs";
import { setupRegistration } from "./register.mjs";
import { setupVerification } from "./verify.mjs";

try {
  const config = await api("/api/health");
  $("engine-info").textContent = `SFace + YuNet · ${config.threads} thread · CPU only`;
  $("spoof-badge").textContent = config.anti_spoofing ? "Filter anti-spoof aktif" : "Filter anti-spoof nonaktif";
  if (!config.anti_spoofing) notice("Filter anti-spoof sedang nonaktif. Hasil hanya menunjukkan kecocokan wajah.");
  if (document.body.dataset.page === "verify") await setupVerification(config);
  else setupRegistration(config);
} catch (error) {
  notice(`Server belum siap: ${error.message}. Muat ulang halaman setelah server berjalan.`);
}
