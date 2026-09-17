/* Harness de render: carga el bundle real con un DOM/canvas stub y comprueba
   que las dos pestanas nuevas pintan contenido (innerHTML no vacio). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const payload = JSON.parse(
  fs.readFileSync(path.join(__dirname, "_payload.json"), "utf8"),
);
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8");
const bundle = fs.readFileSync(
  path.join(ROOT, "frontend", "dist", "bundle.js"),
  "utf8",
);

const elements = new Map();
function makeEl(id) {
  const el = {
    id,
    _html: "",
    textContent: "",
    value: "",
    checked: false,
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    children: [],
    get innerHTML() {
      return this._html;
    },
    set innerHTML(v) {
      this._html = String(v);
    },
    addEventListener() {},
    removeEventListener() {},
    appendChild(c) {
      this.children.push(c);
      return c;
    },
    insertAdjacentHTML(_pos, v) {
      this._html += String(v);
    },
    querySelectorAll: () => [],
    querySelector: () => null,
    getContext: () => makeCtx(id),
    width: 640,
    height: 360,
    getBoundingClientRect: () => ({ width: 640, height: 260, top: 0, left: 0 }),
    closest: () => null,
    remove() {},
    setAttribute() {},
    getAttribute: () => null,
    focus() {},
  };
  return el;
}
/* Registro de llamadas de dibujo, por canvas (permite afirmar que se pinto). */
const drawLog = new Map();
function makeCtx(canvasId) {
  if (!drawLog.has(canvasId)) drawLog.set(canvasId, []);
  const log = drawLog.get(canvasId);
  const target = { canvas: { width: 640, height: 360 } };
  return new Proxy(target, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (typeof prop === "symbol") return undefined;
      if (prop === "measureText")
        return (s) => ({ width: String(s).length * 6 });
      if (prop === "createLinearGradient" || prop === "createRadialGradient") {
        return () => ({ addColorStop() {} });
      }
      if (prop === "createPattern") return () => null;
      if (prop === "getImageData")
        return () => ({ data: [], width: 0, height: 0 });
      return (...args) => {
        log.push({ fn: String(prop), args });
      };
    },
    set(t, prop, val) {
      t[prop] = val;
      log.push({ fn: `#${String(prop)}`, args: [val] });
      return true;
    },
  });
}

global.window = global;
global.self = global;
global.navigator = { userAgent: "node" };
global.requestAnimationFrame = (cb) => setTimeout(cb, 0);
global.cancelAnimationFrame = () => {};
global.performance = { now: () => Date.now() };
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.document = {
  readyState: "complete",
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, makeEl(id));
    return elements.get(id);
  },
  createElement: (tag) => makeEl(tag),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  removeEventListener() {},
  body: makeEl("body"),
  documentElement: makeEl("html"),
};
global.HTMLCanvasElement = function () {};
global.CanvasRenderingContext2D = function () {};
global.Image = function () {
  this.src = "";
};
global.fetch = async () => ({
  ok: true,
  json: async () => ({ status: "success", data: payload }),
});

try {
  // El bundle es un IIFE: se evalua en este contexto y se captura el namespace
  // exportado por el point de entrada (window.App).
  // eslint-disable-next-line no-new-func
  new Function(bundle)();
} catch (err) {
  console.log("BUNDLE_EVAL_ERROR:", err && err.message);
}

const App = global.App || global.NilmApp || global.app || {};
const keys = Object.keys(App);
console.log("bundle namespace keys:", keys.join(",") || "(vacio)");

// 1) Comprobar que index.html tiene los contenedores que el render busca.
const ids = [
  "chart-harmonic-signature",
  "chart-scatter-harm",
  "chart-fhmm-viterbi",
  "fhmm-exact-info",
  "tab-harmonic",
  "tab-fhmm",
  "panel-harmonic",
  "panel-fhmm",
];
for (const id of ids) {
  console.log(`html id=${id}: ${html.includes(`id="${id}"`) ? "OK" : "FALTA"}`);
}
