// 핸드폰 브라우저 안에서 파이썬(Pyodide)으로 예배 PDF 를 만드는 작업 스레드.
// 화면(web_page.html)과 메시지로 대화합니다. 서버가 필요 없고, 올린 파일은 폰 밖으로 나가지 않습니다.

const BASE = self.location.href.replace(/[^/]*$/, "");
let py = null, br = null, ready = null;

const say = (text) => postMessage({ type: "progress", text });

// ---- 폰 안에 기억 저장 (찬송가 제목, 교독문, 올린 악보 등) -------------------
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("worship", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("files");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function dbAll() {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const out = [], tx = db.transaction("files").objectStore("files").openCursor();
      tx.onsuccess = () => { const c = tx.result; if (c) { out.push([c.key, c.value]); c.continue(); } else resolve(out); };
      tx.onerror = () => reject(tx.error);
    });
  } catch { return []; }  // 저장 공간을 못 쓰는 환경(시크릿 모드 등)에서도 동작
}
async function dbPut(entries) {
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction("files", "readwrite"); const store = tx.objectStore("files");
      for (const [k, v] of entries) store.put(v, k);
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
  } catch { /* 저장 못 해도 PDF 만들기에는 영향 없음 */ }
}

function mkdirs(path) {
  const parts = path.split("/").filter(Boolean); let cur = "";
  for (const p of parts.slice(0, -1)) { cur += "/" + p; try { py.FS.mkdir(cur); } catch { /* 이미 있음 */ } }
}

async function persist() {
  const changed = JSON.parse(br.changed_files());
  const entries = changed.map(rel => [rel, py.FS.readFile("/app/" + rel)]);
  if (entries.length) await dbPut(entries);
}

// ---- 준비 ------------------------------------------------------------------
async function init() {
  importScripts(BASE + "pyodide/pyodide.js");
  say("파이썬 엔진을 내려받는 중… (처음 한 번만 1~2분 걸립니다)");
  py = await loadPyodide({ indexURL: BASE + "pyodide/" });
  const manifest = await (await fetch(BASE + "manifest.json", { cache: "no-cache" })).json();
  say("PDF 엔진을 설치하는 중…");
  for (const wheel of manifest.wheels) await py.loadPackage(BASE + wheel);
  say("예배 프로그램을 준비하는 중…");
  const zip = await (await fetch(BASE + manifest.app)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/app" });
  py.runPython("import sys, os\nsys.path.insert(0, '/app')\nos.chdir('/app')");
  br = py.pyimport("worship.browser");
  br.init();
  // 예전에 기억시킨 내용 되살리기
  const saved = await dbAll();
  if (saved.length) {
    try { py.FS.mkdir("/restore"); } catch { /* 이미 있음 */ }
    for (const [rel, bytes] of saved) {
      mkdirs("/restore/" + rel);
      py.FS.writeFile("/restore/" + rel, bytes);
      br.restore(rel);
    }
  }
  say("준비 완료");
}

// ---- 일 시키기 ---------------------------------------------------------------
function cleanName(name) { return String(name || "file").split(/[\\/]/).pop(); }

function finish(raw) {
  const result = JSON.parse(raw);
  if (result.ok === false) return { result };
  const pdf = py.FS.readFile(result.pdf_path);
  return { result, pdf };
}

const jobs = {
  async bulletin({ name, bytes }) {
    const path = "/app/주보/" + cleanName(name);
    py.FS.writeFile(path, new Uint8Array(bytes));
    say("주보를 읽고 PDF 를 만드는 중…");
    const out = finish(br.from_hwp(path));
    if (out.pdf) await persist();
    return out;
  },
  async build({ json }) {
    say("PDF 를 다시 만드는 중…");
    const out = finish(br.from_data(json));
    if (out.pdf) await persist();
    return out;
  },
  async hymn({ num, name, bytes }) {
    const ext = (cleanName(name).match(/\.[^.]+$/) || [""])[0].toLowerCase();
    if (![".ppt", ".pptx", ".pdf", ".zip", ".png", ".jpg", ".jpeg"].includes(ext))
      return { result: { ok: false, error: "PPT / PPTX / PDF / ZIP / 그림 파일을 올려 주세요." } };
    py.FS.writeFile(`/app/hymns/inbox/${parseInt(num, 10)}장${ext}`, new Uint8Array(bytes));
    br.add_hymn(String(num), name);
    return { result: { ok: true } };
  },
};

onmessage = async (e) => {
  const { id, type, payload } = e.data;
  try {
    ready = ready || init();
    await ready;
    if (type === "init") return postMessage({ id, ok: true, result: {} });
    const { result, pdf } = await jobs[type](payload);
    postMessage({ id, ok: true, result, pdf }, pdf ? [pdf.buffer] : []);
  } catch (err) {
    ready = null;  // 준비 단계에서 실패했으면 다음 요청 때 다시 시도
    const text = String(err && err.message || err);
    postMessage({ id, ok: false, error: text.split("\n").slice(-6).join("\n") });
  }
};
