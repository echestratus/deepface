/** One camera, one request at a time. Results from a canceled run are discarded. */
export class LiveCamera {
  constructor(video, { getMedia, createCanvas } = {}) {
    this.video = video;
    this.getMedia = getMedia || ((constraints) => {
      if (!globalThis.navigator?.mediaDevices?.getUserMedia) throw new Error("Kamera memerlukan localhost atau HTTPS. Buka alamat lokal aplikasi.");
      return navigator.mediaDevices.getUserMedia(constraints);
    });
    this.createCanvas = createCanvas || (() => document.createElement("canvas"));
    this.generation = 0;
    this.stream = null;
    this.timer = null;
    this.controller = null;
    this.active = false;
  }

  stop() {
    this.generation += 1;
    this.active = false;
    clearTimeout(this.timer);
    this.timer = null;
    this.controller?.abort();
    this.controller = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video.srcObject = null;
  }

  async start({ prepare, requestFrame, onStarted, onFrame, onError, onEnded, interval = 1000, maxSide = 640 }) {
    this.stop();
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    const current = () => generation === this.generation && !controller.signal.aborted;
    try {
      const stream = await this.getMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false });
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      this.stream = stream;
      await prepare?.(controller.signal);
      if (!current()) return;
      this.video.srcObject = stream;
      await this.video.play();
      if (!current()) return;
      this.active = true;
      for (const track of stream.getVideoTracks()) {
        track.addEventListener("ended", () => {
          if (current()) { this.stop(); onEnded?.(); }
        });
      }
      onStarted?.();
      const tick = async () => {
        if (!current() || !this.active) return;
        const started = performance.now();
        try {
          const blob = await this.capture(maxSide);
          if (!current()) return;
          const result = await requestFrame(blob, controller.signal);
          if (!current()) return;
          onFrame(result);
        } catch (error) {
          if (!current()) return;
          this.stop(); onError?.(error); return;
        }
        if (current() && this.active) this.timer = setTimeout(tick, Math.max(100, interval - (performance.now() - started)));
      };
      void tick();
    } catch (error) {
      if (!current()) return;
      this.stop(); onError?.(error);
    }
  }

  async capture(maxSide) {
    if (!this.video.videoWidth || this.video.readyState < 2) throw new Error("Kamera belum menghasilkan gambar. Mulai ulang kamera.");
    const canvas = this.createCanvas();
    const scale = Math.min(1, maxSide / Math.max(this.video.videoWidth, this.video.videoHeight));
    canvas.width = Math.round(this.video.videoWidth * scale);
    canvas.height = Math.round(this.video.videoHeight * scale);
    canvas.getContext("2d").drawImage(this.video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Frame kamera tidak dapat dibaca.")), "image/jpeg", .85));
  }
}
