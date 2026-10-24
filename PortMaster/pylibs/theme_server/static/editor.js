/* SPDX-License-Identifier: MIT

   The theme server's Edit view: theme.json in CodeMirror 5, with
   - suggestions (Ctrl+Space, and as you type) for keys, values, {tags} and [capabilities],
     from /api/schema: what pugwash's own code accepts
   - checks as you type: JSON mistakes, unknown keys ("did you mean"), values of the wrong type
   - a preview of one screen that follows the typing (unsaved text goes to /api/theme_draft,
     which renders it from a copy of the theme made of links), whose region boxes jump to
     their place in theme.json
   - saving (Ctrl+S) to theme.json, the old one kept as theme.json.bak; a theme that can't be
     changed here (the built-in one) can be copied to a new theme first.
   Uses index.html's globals: $, state, theme(), poll(), status(), boxes(). */
"use strict";

const edit = {
  cm: null, schema: null, file: null, loaded: null, dirty: false, draftTimer: null, previewTheme: null,
  previewController: null, previewInfo: null, regionsAt: [], shot: "main_menu", busy: false,
};

/* ---------------------------------------------------------------- JSON with positions */
class JSONError extends Error { constructor(message, pos) { super(message); this.pos = pos; } }

/* Parses text as JSON and says where everything is: nodes are {path, keyFrom, keyTo, from, to, value}
   for every value inside an object or array. Throws JSONError at the first mistake, worded for people
   who don't write JSON every day. */
function parseJSON(text) {
  const n = text.length, nodes = [], duplicates = [];
  let i = 0;
  const ws = () => { while (i < n) { const c = text.charCodeAt(i); if (c === 32 || c === 9 || c === 10 || c === 13) i++; else break; } };
  const fail = (message, pos = i) => { throw new JSONError(message, pos); };
  function string() {
    const start = i; i++;
    let out = "";
    for (;;) {
      if (i >= n) fail("This string has no closing \"", start);
      const c = text[i];
      if (c === '"') { i++; return out; }
      if (c === "\\") {
        const e = text[i + 1];
        const simple = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e in simple) { out += simple[e]; i += 2; continue; }
        if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) { out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue; }
        fail(`\\${e || ""} isn't a JSON escape: write \\\\ for a backslash`);
      }
      if (c === "\n") fail("A string can't go over two lines: write \\n for a line break", start);
      if (c < " ") fail("A control character in a string: write \\t for a tab");
      out += c; i++;
    }
  }
  function value(path) {
    ws();
    if (i >= n) fail("The file ends where a value should be");
    const c = text[i];
    if (c === "{") return object(path);
    if (c === "[") return array(path);
    if (c === '"') return string();
    const number = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y; number.lastIndex = i;
    const m = number.exec(text);
    if (m && m[0].length && m[0] !== "-") { i += m[0].length; return Number(m[0]); }
    for (const [word, v] of [["true", true], ["false", false], ["null", null]]) if (text.startsWith(word, i)) { i += word.length; return v; }
    if (c === "'") fail("JSON strings use double quotes \", not '");
    if (text.startsWith("//", i) || text.startsWith("/*", i)) fail("JSON has no comments: use a \"comment\" key instead");
    if (/[A-Za-z_]/.test(c)) fail(`A word needs quotes in JSON: "${(text.slice(i).match(/^[\w-]+/) || [""])[0]}"`);
    fail(`Expected a value, found ${JSON.stringify(c)}`);
  }
  function object(path) {
    const result = {}, seen = new Set();
    i++; ws();
    if (text[i] === "}") { i++; return result; }
    for (;;) {
      ws();
      if (text[i] === "}") fail("A , before } isn't allowed in JSON: remove the last comma");
      if (text[i] === "'") fail("JSON keys use double quotes \", not '");
      if (text[i] !== '"') fail(i >= n ? "The file ends inside { }: a } is missing" : /[A-Za-z_]/.test(text[i]) ? "Keys need double quotes in JSON" : "Expected a \"key\"");
      const keyFrom = i, key = string(), keyTo = i;
      ws();
      if (text[i] !== ":") fail(`Expected : after "${key}"`);
      i++; ws();
      const from = i, v = value([...path, key]);
      nodes.push({ path: [...path, key], keyFrom, keyTo, from, to: i, value: v });
      if (seen.has(key)) duplicates.push({ path: [...path, key], keyFrom, keyTo });
      seen.add(key);
      result[key] = v;
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "}") { i++; return result; }
      fail(i >= n ? "The file ends inside { }: a } is missing" : text[i] === '"' ? "A , is missing before this key" : "Expected , or }");
    }
  }
  function array(path) {
    const result = [];
    i++; ws();
    if (text[i] === "]") { i++; return result; }
    for (;;) {
      ws();
      if (text[i] === "]") fail("A , before ] isn't allowed in JSON: remove the last comma");
      const from = i, v = value([...path, result.length]);
      nodes.push({ path: [...path, result.length], keyFrom: null, keyTo: null, from, to: i, value: v });
      result.push(v);
      ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "]") { i++; return result; }
      fail(i >= n ? "The file ends inside [ ]: a ] is missing" : "A , or ] is missing");
    }
  }
  ws();
  const result = value([]);
  ws();
  if (i < n) fail("There's more after the end of the theme: a { or [ too few, or a } too many?");
  if (result === null || typeof result !== "object" || Array.isArray(result)) fail("theme.json has to be one { } object", 0);
  return { value: result, nodes, duplicates };
}

/* ---------------------------------------------------------------- What a place in theme.json is */
const bare = (key) => String(key).replace(/\[.*$/, "");

/* The kind of object at path (an array of keys): 'top', 'info', 'region', 'section', 'config',
   'pallet', 'scheme', 'schemes', 'elements', 'resources', 'override', 'translations' or 'other'. */
function kindOf(path) {
  if (!path.length) return "top";
  const [a, ...rest] = path.map(bare);
  if (a === "#info") return rest.length ? "other" : "info";
  if (a === "#base") return rest.length ? "other" : "region";
  if (a === "#elements") return rest.length === 0 ? "elements" : rest.length === 1 ? "region" : "other";
  if (a === "#pallet") return rest.length ? "other" : "pallet";
  if (a === "#resources") return rest.length === 0 ? "resources" : "other";
  if (a === "#override") return rest.length ? "other" : "override";
  if (a === "#translations") return "translations";
  if (a === "#schemes") {
    if (!rest.length) return "schemes";
    if (rest.length === 1) return "scheme";
    return kindOf(path.slice(2));
  }
  if (a.startsWith("#")) return "other";
  if (!rest.length) return "section";
  if (rest.length === 1) return rest[0] === "#config" ? "config" : "region";
  return "other";
}

/* ---------------------------------------------------------------- Checks */
function closest(word, words) {
  let best = null, bestScore = 3;
  for (const other of words) {
    const d = distance(word, other);
    if (d < bestScore || (d === bestScore && best === null && d <= Math.max(1, Math.floor(word.length / 4)))) { best = other; bestScore = d; }
  }
  return bestScore <= 2 ? best : null;
}
function distance(a, b) {
  if (Math.abs(a.length - b.length) > 3) return 9;
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const tmp = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = tmp;
    }
  }
  return row[b.length];
}
const isInt = (v) => typeof v === "number" && Number.isInteger(v);
const isNum = (v) => typeof v === "number";
function colorProblem(v, colors) {
  if (typeof v === "string") {
    if (colors.includes(v)) return null;
    if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(v)) return null;
    if (v.startsWith("#")) return "a color is #rrggbb, #rgb or #rrggbbaa";
    const near = closest(v, colors);
    return `"${v}" isn't a color in this theme's #pallet` + (near ? `: did you mean "${near}"?` : "");
  }
  if (Array.isArray(v) && (v.length === 3 || v.length === 4) && v.every((p) => isInt(p) && p >= 0 && p <= 255)) return null;
  return "a color is a #pallet name, \"#rrggbb\" or [r, g, b] / [r, g, b, a] of 0-255";
}
/* What's wrong with value v for region key `key`, or null. */
function valueProblem(key, v, names) {
  const spec = edit.schema.keys[key];
  if (!spec) return null;
  const { type } = spec;
  const range = (x) => (spec.min !== undefined && x < spec.min) || (spec.max !== undefined && x > spec.max)
    ? `${key} goes from ${spec.min ?? "…"} to ${spec.max ?? "…"}` : null;
  switch (type) {
    case "int": return isInt(v) ? range(v) : `${key} is a whole number`;
    case "float": return isNum(v) ? range(v) : `${key} is a number`;
    case "bool": return typeof v === "boolean" ? null : `${key} is true or false`;
    case "color": return colorProblem(v, names.colors);
    case "rect": return Array.isArray(v) && v.length === 4 && v.every(isNum) ? null : "area is [x, y, width, height] or fractions [left, top, right, bottom]";
    case "ints": return Array.isArray(v) && (!spec.count || v.length === spec.count) && v.every(isInt) ? null : `${key} is ${spec.count ? spec.count + " " : ""}whole numbers: [${Array(spec.count || 2).fill("0").join(", ")}]`;
    case "option": {
      const options = spec.options || [];
      const one = (x) => typeof x === "string" && options.includes(x);
      if (spec.count) return Array.isArray(v) && v.length === spec.count && v.every(one) ? null : `${key} is [${Array(spec.count).fill('"…"').join(", ")}] of: ${options.join(", ")}`;
      if (v === null || one(v)) return null;
      const near = typeof v === "string" ? closest(v, options) : null;
      return `${key} is one of: ${options.join(", ")}` + (near ? ` (did you mean "${near}"?)` : "") + ": PortMaster uses its default instead";
    }
    case "text": return typeof v === "string" ? null : `${key} is text: "…"`;
    case "file": case "image": {
      if (v === null) return null;
      if (typeof v !== "string") return `${key} is a file name: "…"`;
      if (v.includes("{") || v.startsWith("qr:")) return null;
      const files = type === "image" ? [...edit.schema.files.image, ...names.resources] : [...edit.schema.files.font, ...edit.schema.files.sound, ...names.resources];
      if (key === "font" && !files.includes(v)) return `there's no font "${v}" in this theme or PortMaster`;
      if (type === "image" && !files.includes(v)) return `there's no image "${v}" in this theme or its #resources`;
      return null;
    }
    case "outline": return Array.isArray(v) && v.length === 2 && !colorProblem(v[0], names.colors) && isInt(v[1]) ? null : `${key} is [color, thickness]`;
    case "list": return v === null || Array.isArray(v) ? null : `${key} is a list: [ … ]`;
    default: return null;
  }
}

/* [{from, to, severity, message}] for the text. */
function check(text) {
  let parsed;
  try { parsed = parseJSON(text); }
  catch (error) {
    if (!(error instanceof JSONError)) throw error;
    return { parsed: null, problems: [{ from: error.pos, to: Math.min(error.pos + 1, text.length), severity: "error", message: error.message }] };
  }
  const s = edit.schema, problems = [];
  const names = mergedNames(parsed.value);
  const sections = Object.keys(s.sections);
  const warn = (from, to, message, severity = "warning") => problems.push({ from, to, severity, message });
  for (const dup of parsed.duplicates) warn(dup.keyFrom, dup.keyTo, `"${dup.path[dup.path.length - 1]}" is here twice: only the last one counts`);
  for (const node of parsed.nodes) {
    const key = node.path[node.path.length - 1];
    if (typeof key !== "string") continue;
    const parent = node.path.slice(0, -1), kind = kindOf(parent), name = bare(key);
    const at = [node.keyFrom, node.keyTo];
    if (kind === "top") {
      if (key.startsWith("#") && !(key in s.top)) warn(...at, `PortMaster doesn't use "${key}"` + hint(key, Object.keys(s.top)));
      else if (!key.startsWith("#") && !sections.includes(name)) warn(...at, `There's no screen called "${name}"` + hint(name, sections), "info");
    } else if (kind === "scheme") {
      if (key.startsWith("#") && !["#pallet", "#resources", "#base"].includes(key)) warn(...at, `A color scheme can have #pallet, #resources and sections, not "${key}"`);
    } else if (kind === "info") {
      if (!(key in s.info)) warn(...at, `#info has ${Object.keys(s.info).join(", ")}`, "info");
      else if (key === "default-scheme" && !names.schemes.includes(node.value)) warn(node.from, node.to, `There's no color scheme "${node.value}" in #schemes`);
    } else if (kind === "section") {
      if (key.startsWith("#element:")) {
        const element = key.slice(9).split(":")[0].replace(/\[.*$/, "");
        if (!names.elements.includes(element)) warn(...at, `There's no "${element}" in #elements` + hint(element, names.elements));
      }
      if (node.value !== null && typeof node.value !== "object" && key !== "#config") warn(node.from, node.to, "A region is an object: { … }", "error");
    } else if (kind === "region") {
      if (!(name in s.keys)) { warn(...at, `PortMaster doesn't know "${name}": it's ignored` + hint(name, Object.keys(s.keys))); continue; }
      const problem = valueProblem(name, node.value, names);
      /* PortMaster quietly uses the default for an option it doesn't know, a missing file
         shows nothing; the rest stop the screen loading. */
      if (problem) warn(node.from, node.to, problem, ["image", "file", "option"].includes(s.keys[name].type) ? "warning" : "error");
      if (name === "parent" && typeof node.value === "string" && node.value !== "root" && !names.elements.includes(node.value)) {
        const regions = Object.keys((parsed.value[parent[0]] || {})).filter((r) => !r.startsWith("#"));
        if (!regions.includes(node.value)) warn(node.from, node.to, `There's no "${node.value}" in #elements or this section, so it's the whole screen` + hint(node.value, [...names.elements, ...regions]));
      }
    } else if (kind === "pallet") {
      if (colorProblem(node.value, [])) warn(node.from, node.to, "A #pallet color is \"#rrggbb\" or [r, g, b] / [r, g, b, a]", "error");
    }
  }
  return { parsed, problems };
}
const hint = (word, words) => { const near = closest(word, words); return near ? `: did you mean "${near}"?` : ""; };

/* The theme's names, from the text being typed (so a new color can be used straight away)
   and from the server (its files). */
function mergedNames(value) {
  const names = { colors: new Set(), resources: new Set(edit.schema.names.resources), elements: new Set(), schemes: [] };
  const take = (section) => {
    if (!section || typeof section !== "object") return;
    for (const k of Object.keys(section["#pallet"] || {})) names.colors.add(k);
    for (const [file, info] of Object.entries(section["#resources"] || {})) {
      names.resources.add(file);
      if (info && typeof info === "object") {
        if (typeof info.name === "string") names.resources.add(info.name);
        for (const part of Object.keys(info.atlas || {})) names.resources.add(part);
      }
    }
  };
  take(value);
  for (const [name, scheme] of Object.entries(value["#schemes"] || {})) { take(scheme); if (!name.startsWith("#")) names.schemes.push(name); }
  for (const k of Object.keys(value["#elements"] || {})) names.elements.add(k);
  return { colors: [...names.colors], resources: [...names.resources], elements: [...names.elements], schemes: names.schemes };
}

/* ---------------------------------------------------------------- Where the cursor is */
/* A forgiving scan of the text up to index: the path of the object or array it's in, and
   whether it's in a key, a string value or a bare value. Works on half-typed text. */
function contextAt(text, index) {
  const stack = [{ type: "obj", key: null, expectKey: false, name: null, top: true }];
  let i = 0;
  /* stack[0] is outside the file, stack[1] the file's { }: paths start below that. */
  const path = () => stack.slice(2).map((f) => f.name);
  /* The object a value belongs to, and its key: for [ ... ] values, the object holding the array. */
  const owner = () => {
    let at = stack.length - 1;
    while (at > 0 && stack[at].type === "arr") at--;
    return { key: stack[at].key, path: stack.slice(2, at + 1).map((f) => f.name), inArray: at !== stack.length - 1 };
  };
  while (i < index) {
    const c = text[i];
    const top = stack[stack.length - 1];
    if (c === '"') {
      const start = i; i++;
      let out = "";
      while (i < text.length && text[i] !== '"' && text[i] !== "\n") {
        if (text[i] === "\\") { out += text[i + 1] === "n" ? "\n" : text[i + 1] || ""; i += 2; continue; }
        out += text[i]; i++;
      }
      if (i >= index) {
        const isKey = top.type === "obj" && top.expectKey;
        return { in: isKey ? "key" : "value", ...owner(), key: isKey ? null : owner().key, path: isKey ? path() : owner().path,
                 prefix: text.slice(start + 1, index), from: start + 1, closed: text[i] === '"', end: i };
      }
      i++;
      if (top.type === "obj" && top.expectKey) { top.key = out; top.expectKey = false; }
      continue;
    }
    if (c === "{" || c === "[") {
      const name = top.type === "obj" ? top.key : (top.index || 0);
      stack.push({ type: c === "{" ? "obj" : "arr", key: null, expectKey: c === "{", name, index: 0 });
    } else if (c === "}" || c === "]") {
      if (stack.length > 1) stack.pop();
    } else if (c === ",") {
      if (top.type === "obj") { top.expectKey = true; top.key = null; } else top.index = (top.index || 0) + 1;
    } else if (c === ":") {
      if (top.type === "obj") top.expectKey = false;
    }
    i++;
  }
  const top = stack[stack.length - 1];
  if (stack.length === 1 && !top.key) return { in: "start", path: [] };
  const word = text.slice(0, index).match(/[\w.-]*$/)[0];
  if (top.type === "obj" && top.expectKey) return { in: "key-bare", path: path(), prefix: word, from: index - word.length };
  return { in: "bare", ...owner(), prefix: word, from: index - word.length };
}

/* ---------------------------------------------------------------- Suggestions */
function keysFor(kind, path, value) {
  const s = edit.schema;
  const doc = (key) => { const spec = s.keys[key]; if (!spec) return ""; return spec.options ? spec.options.slice(0, 4).join(" | ") + (spec.options.length > 4 ? " …" : "") : spec.type + (spec.count ? ` ×${spec.count}` : ""); };
  switch (kind) {
    case "top": return [...Object.entries(s.top).map(([k, d]) => [k, d]), ...Object.keys(s.sections).map((k) => [k, "screen"])];
    case "info": return Object.keys(s.info).map((k) => [k, s.info[k].type]);
    case "region": return Object.keys(s.keys).map((k) => [k, doc(k)]);
    case "section": {
      const section = bare(path[path.length - 1]);
      const names = value ? mergedNames(value) : { elements: s.names.elements };
      return [["#config", "buttons"], ["#base", "keys every region here starts from"],
        ...(s.sections[section] || []).map((r) => [r, "region"]),
        ...names.elements.map((e) => ["#element:" + e, "a region from #elements"])];
    }
    case "scheme": return [["#pallet", "named colors"], ["#resources", "image changes"], ...Object.keys(s.sections).map((k) => [k, "screen"])];
    case "config": return Object.keys(s.config).map((k) => [k, s.config[k].type]);
    case "override": return s.special_words.map((w) => [w, "special word"]);
    case "pallet": return (value ? mergedNames(value).colors : s.names.colors).map((c) => [c, "color"]);
    default: return [];
  }
}
function valuesFor(key, value, path) {
  const s = edit.schema, name = bare(key || "");
  const kind = kindOf(path);
  const names = value ? mergedNames(value) : s.names;
  if (kind === "info" && name === "default-scheme") return names.schemes.map((x) => [x, "color scheme"]);
  if (kind !== "region") return [];
  const spec = s.keys[name];
  if (!spec) return [];
  if (spec.options) return spec.options.map((o) => [o, name]);
  if (spec.type === "color") return names.colors.map((c) => [c, "color"]);
  if (name === "font") return s.files.font.map((f) => [f, "font"]);
  if (spec.type === "image") return [...s.files.image.map((f) => [f, "image file"]), ...names.resources.filter((r) => !s.files.image.includes(r)).map((r) => [r, "resource"]), ["qr:", "a QR code of the text after it"]];
  if (/sound/.test(name) || name === "music") return [...s.files.sound, ...names.resources.filter((r) => /\.(ogg|wav|mp3)$/i.test(r) || !r.includes("."))].map((f) => [f, "sound"]);
  if (name === "parent") return [["root", "the whole screen"], ...names.elements.map((e) => [e, "element"])];
  return [];
}

function hintAt(cm, options) {
  if (!edit.schema) return null;
  const text = cm.getValue(), cursor = cm.getCursor(), index = cm.indexFromPos(cursor);
  const ctx = contextAt(text, index);
  let value = null;
  try { value = JSON.parse(text); } catch (e) { /* half-typed: the server's names */ }
  /* items [[text, doc]] matching what's typed since filterFrom, replacing from..to. */
  const make = (items, from, to, wrap, filterFrom = from) => {
    const prefix = text.slice(filterFrom, index).toLowerCase();
    const list = items.filter(([t]) => !prefix || t.toLowerCase().includes(prefix))
      .sort(([a], [b]) => (b.toLowerCase().startsWith(prefix) - a.toLowerCase().startsWith(prefix)))
      .slice(0, 200)
      .map(([t, d]) => ({ text: wrap(t), displayText: t, render: (el) => { el.textContent = t; if (d) { const small = document.createElement("span"); small.className = "hint-doc"; small.textContent = d; el.append(small); } } }));
    if (!list.length) return null;
    return { list, from: cm.posFromIndex(from), to: cm.posFromIndex(to) };
  };
  if (ctx.in === "key" || ctx.in === "key-bare") {
    const kind = kindOf(ctx.path);
    /* "key[" : a capability. */
    const bracket = ctx.in === "key" ? ctx.prefix.lastIndexOf("[") : -1;
    if (bracket >= 0 && !ctx.prefix.slice(bracket).includes("]")) {
      const sep = Math.max(ctx.prefix.lastIndexOf("|"), ctx.prefix.lastIndexOf(","), bracket);
      const from = ctx.from + sep + 1 + (ctx.prefix[sep + 1] === "!" ? 1 : 0);
      return make(edit.schema.capabilities.map((c) => [c, "capability"]), from, index, (t) => t);
    }
    const items = keysFor(kind, ctx.path, value);
    if (ctx.in === "key") {
      const end = ctx.closed ? ctx.end + 1 : index;
      const colon = ctx.closed && /^\s*:/.test(text.slice(end));
      return make(items, ctx.from - 1, end, (t) => `"${t}"` + (colon ? "" : ": "), ctx.from);
    }
    return make(items, ctx.from, index, (t) => `"${t}": `);
  }
  if (ctx.in === "value") {
    /* In a string: {tags}, or the key's values. */
    const brace = ctx.prefix.lastIndexOf("{");
    if (brace >= 0 && !ctx.prefix.slice(brace).includes("}")) {
      const tags = [...edit.schema.tags.map((t) => [t, "tag"]), ["if:", "{if:tag}…{else}…{endif}"], ["else", ""], ["endif", ""]];
      const from = ctx.from + brace + 1 + (ctx.prefix.slice(brace + 1).startsWith("if:") ? 3 + (ctx.prefix[brace + 4] === "!" ? 1 : 0) : 0);
      return make(tags, from, index, (t) => (t.endsWith(":") ? t : t + "}"));
    }
    const items = valuesFor(ctx.key, value, ctx.path);
    const end = ctx.closed ? ctx.end + 1 : index;
    return make(items, ctx.from - 1, end, (t) => `"${t}"`, ctx.from);
  }
  if (ctx.in === "bare") {
    const spec = edit.schema.keys[bare(ctx.key || "")];
    if (spec && spec.type === "bool" && kindOf(ctx.path) === "region") return make([["true", ""], ["false", ""]], ctx.from, index, (t) => t);
    const items = valuesFor(ctx.key, value, ctx.path);
    if (items.length) return make(items, ctx.from, index, (t) => `"${t}"`);
  }
  return null;
}

/* ---------------------------------------------------------------- The page */
function loadAssets() {
  if (window.CodeMirror) return Promise.resolve();
  if (edit.assets) return edit.assets;
  edit.assets = new Promise((resolve, reject) => {
    const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "/static/codemirror.css"; document.head.append(css);
    const js = document.createElement("script"); js.src = "/static/codemirror.js"; js.onload = resolve; js.onerror = () => reject(new Error("Can't load the editor"));
    document.head.append(js);
  });
  return edit.assets;
}

async function buildEdit() {
  const pane = $("edit");
  $("estate").textContent = "Loading…";
  try {
    await loadAssets();
    const [file, schemaInfo] = await Promise.all([
      fetch("/api/theme_file?" + new URLSearchParams({ theme: state.theme })).then(jsonOrThrow),
      fetch("/api/schema?" + new URLSearchParams({ theme: state.theme })).then(jsonOrThrow)]);
    edit.schema = schemaInfo;
    if (!edit.cm) makeEditor();
    if (edit.loaded !== state.theme || !edit.dirty) loadText(file);
    else edit.file = { ...edit.file, writable: file.writable, can_copy: file.can_copy };
  } catch (error) {
    $("estate").textContent = error.message;
    return;
  }
  fillShots();
  updateState();
  edit.cm.refresh();
  preview();
  pane.hidden = false;
}

async function jsonOrThrow(r) {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { const error = new Error(body.error || r.statusText); error.status = r.status; error.body = body; throw error; }
  return body;
}

function lintText(text, options, cm) {
  if (!edit.schema) return [];
  const { problems } = check(text);
  edit.problems = problems;
  showProblems();
  return problems.map((p) => ({ from: cm.posFromIndex(p.from), to: cm.posFromIndex(Math.max(p.to, p.from + 1)), severity: p.severity === "info" ? "warning" : p.severity, message: p.message }));
}

function makeEditor() {
  edit.cm = CodeMirror.fromTextArea($("etext"), {
    mode: { name: "javascript", json: true }, lineNumbers: true, indentUnit: 4, tabSize: 4, indentWithTabs: false,
    matchBrackets: true, autoCloseBrackets: true, styleActiveLine: true, foldGutter: true,
    gutters: ["CodeMirror-lint-markers", "CodeMirror-linenumbers", "CodeMirror-foldgutter"],
    lint: { getAnnotations: lintText, delay: 250 },
    hintOptions: { hint: hintAt, completeSingle: false, closeCharacters: /[\s()[\]{};>,]/ },
    extraKeys: {
      "Ctrl-Space": "autocomplete", "Cmd-Space": "autocomplete",
      "Ctrl-S": () => saveTheme(), "Cmd-S": () => saveTheme(),
      Tab: (cm) => (cm.somethingSelected() ? cm.indentSelection("add") : cm.replaceSelection("    ", "end")),
      "Shift-Tab": (cm) => cm.indentSelection("subtract"),
    },
  });
  edit.cm.on("change", (cm, change) => {
    if (change.origin === "setValue") return;
    edit.dirty = !cm.isClean(edit.clean);
    updateState();
    clearTimeout(edit.draftTimer);
    edit.draftTimer = setTimeout(draft, 700);
  });
  edit.cm.on("inputRead", (cm, change) => {
    const typed = change.text.join("");
    /* Suggest as you type: in a key, after { in a string, after [ in a key, after ": ". */
    if (/^[\w"{[#|:!-]$/.test(typed) && !cm.state.completionActive) cm.showHint({ completeSingle: false });
  });
  edit.cm.on("cursorActivity", () => highlightRegionAtCursor());
}

function loadText(file) {
  edit.file = file;
  edit.loaded = file.theme;
  const cursor = edit.cm.getCursor(), scroll = edit.cm.getScrollInfo();
  edit.cm.setValue(file.text);
  edit.cm.clearHistory();
  edit.clean = edit.cm.changeGeneration();
  edit.dirty = false;
  edit.previewTheme = null;
  if (cursor.line < edit.cm.lineCount()) { edit.cm.setCursor(cursor); edit.cm.scrollTo(scroll.left, scroll.top); }
  updateState();
}

function updateState() {
  if (!edit.file) return;
  const file = edit.file;
  $("esave").disabled = !file.writable || !edit.dirty || edit.busy;
  $("erevert").disabled = !edit.dirty || edit.busy;
  $("ecopy").hidden = !file.can_copy;
  let text;
  if (!file.writable) text = file.can_copy ? "Built-in or read-only theme: changes show in the preview, “Copy to a new theme” keeps them" : "This theme can't be changed here: changes only show in the preview";
  else text = edit.dirty ? "Unsaved changes · Ctrl+S saves" : "Saved";
  if (file.writable && file.downloaded) text += " · downloaded theme: updating it from the theme list replaces your changes, a copy keeps them";
  $("estate").textContent = text;
  $("estate").classList.toggle("dirty", edit.dirty);
}

function fillShots() {
  const select = $("eshot");
  if (!select.options.length) for (const [name, title] of state.info.shots) option(select, name, title);
  if (!state.info.shots.some(([name]) => name === edit.shot)) edit.shot = state.info.shots[0][0];
  select.value = edit.shot;
}

/* Unsaved text: a draft theme on the server, rendered instead of the saved one. */
async function draft() {
  const text = edit.cm.getValue();
  if (!edit.dirty) { edit.previewTheme = null; preview(); return; }
  if (check(text).parsed === null) return;   // the preview keeps the last good text
  try {
    const answer = await fetch("/api/theme_draft", { method: "POST", headers: postHeaders(), body: JSON.stringify({ theme: edit.loaded, text }) }).then(jsonOrThrow);
    edit.previewTheme = answer.theme;
    preview();
  } catch (error) { $("estate").textContent = `Preview failed: ${error.message}`; }
}
const postHeaders = () => ({ "Content-Type": "application/json", "X-Theme-Server": "1" });

async function preview() {
  if (state.view !== "edit") return;
  if (edit.previewController) edit.previewController.abort();
  const controller = edit.previewController = new AbortController();
  const view = $("eshotview");
  view.classList.add("rendering");
  const query = new URLSearchParams({ theme: edit.previewTheme || state.theme, scheme: state.scheme, res: state.res, lang: state.lang, shot: edit.shot });
  try {
    const info = await fetch("/api/render.json?" + query, { signal: controller.signal }).then(jsonOrThrow);
    edit.previewInfo = info;
    const shot = document.createElement("div"); shot.className = "shot";
    const [w, h] = info.resolution.split("x").map(Number);
    shot.style.setProperty("--aspect", `${w}/${h}`);
    if (info.missing) { shot.innerHTML = `<div class="missing"></div>`; shot.firstChild.textContent = info.missing; }
    else {
      const img = new Image(); img.alt = edit.shot;
      img.src = "/api/render.png?" + query + "&v=" + info.version;
      await img.decode().catch(() => {});
      if (controller.signal.aborted) return;
      shot.append(img);
      const layer = boxes(info, false);
      layer.classList.add("edit-boxes");
      layer.hidden = !$("eboxes").checked;
      for (const box of layer.children) {
        box.addEventListener("click", (event) => { event.stopPropagation(); jumpToRegion(info.regions[box.dataset.index]); });
        box.title = info.regions[box.dataset.index].name;
      }
      shot.append(layer);
    }
    view.replaceChildren(shot);
    showProblems();
    highlightRegionAtCursor();
  } catch (error) {
    if (controller.signal.aborted) return;
    view.innerHTML = `<div class="missing"></div>`; view.firstChild.textContent = error.message;
  } finally {
    if (edit.previewController === controller) view.classList.remove("rendering");
  }
}

/* The problems the checks found, and the render's errors, as a list that jumps to them. */
function showProblems() {
  if (!edit.cm) return;   // (the first check runs while CodeMirror is being made)
  const list = $("eproblems");
  list.replaceChildren();
  const problems = edit.problems || [];
  const renderErrors = (edit.previewInfo && edit.previewInfo.errors) || [];
  for (const error of renderErrors) {
    const li = document.createElement("li"); li.className = "error"; li.textContent = `Render: ${error}`;
    list.append(li);
  }
  const order = { error: 0, warning: 1, info: 2 };
  for (const p of [...problems].sort((a, b) => order[a.severity] - order[b.severity] || a.from - b.from).slice(0, 100)) {
    const li = document.createElement("li"); li.className = p.severity;
    const pos = edit.cm.posFromIndex(p.from);
    li.textContent = `${pos.line + 1}: ${p.message}`;
    li.onclick = () => { edit.cm.focus(); edit.cm.setSelection(pos, edit.cm.posFromIndex(Math.max(p.to, p.from + 1))); edit.cm.scrollIntoView(pos, 80); };
    list.append(li);
  }
  $("eproblems-title").textContent = problems.length + renderErrors.length ? `Problems (${problems.length + renderErrors.length})` : "No problems";
}

/* A region box clicked: its place in theme.json (the section's region, else its #elements entry). */
function jumpToRegion(region) {
  let parsed;
  try { parsed = parseJSON(edit.cm.getValue()); } catch (error) { return; }
  const byKey = (path) => parsed.nodes.find((n) => n.path.length === path.length && n.path.every((k, i) => bare(k) === bare(path[i])));
  const node = byKey([region.section, region.name]) || byKey([region.section, "#element:" + region.name]) ||
    parsed.nodes.find((n) => n.path.length === 2 && n.path[0] === region.section && typeof n.path[1] === "string" && n.path[1].startsWith("#element:") && n.path[1].endsWith(":" + region.name)) ||
    byKey(["#elements", region.name]) || byKey([region.section]);
  if (!node) return;
  const from = edit.cm.posFromIndex(node.keyFrom), to = edit.cm.posFromIndex(node.keyTo);
  edit.cm.focus();
  edit.cm.setSelection(from, to);
  edit.cm.scrollIntoView({ from, to }, 120);
}

/* The cursor in a region of this screen's section: its box lights up. */
function highlightRegionAtCursor() {
  const info = edit.previewInfo;
  if (!info || !edit.cm) return;
  const ctx = contextAt(edit.cm.getValue(), edit.cm.indexFromPos(edit.cm.getCursor()));
  let [section, region] = ctx.path || [];
  if (ctx.in === "key" && ctx.path.length === 1) region = ctx.prefix;
  for (const box of document.querySelectorAll("#eshotview .box")) {
    const r = info.regions[box.dataset.index];
    const name = region ? bare(region).replace(/^#element:(?:[^:]*:)?/, "") : null;
    box.classList.toggle("hot", !!name && (bare(section) === r.section || section === "#elements") && r.name === name);
  }
}

async function saveTheme(overwrite) {
  if (!edit.file || !edit.file.writable || edit.busy) return;
  const text = edit.cm.getValue();
  const result = check(text);
  if (result.parsed === null) {
    const p = result.problems[0], pos = edit.cm.posFromIndex(p.from);
    $("estate").textContent = `Not saved: line ${pos.line + 1}: ${p.message}`;
    edit.cm.setCursor(pos);
    return;
  }
  edit.busy = true; updateState();
  try {
    const answer = await fetch("/api/theme_file", { method: "POST", headers: postHeaders(),
      body: JSON.stringify({ theme: edit.loaded, text, version: overwrite || edit.file.version }) }).then(jsonOrThrow);
    edit.file.version = answer.version; edit.file.text = text;
    edit.clean = edit.cm.changeGeneration();
    edit.dirty = false; edit.previewTheme = null;
    edit.busy = false; updateState();
    $("estate").textContent = `Saved ${new Date().toLocaleTimeString()} · the old one is theme.json.bak`;
    poll();
    preview();
  } catch (error) {
    edit.busy = false; updateState();
    if (error.status === 409) {
      if (confirm("theme.json was changed on disk since you opened it.\n\nOK: save yours over it (the one on disk becomes theme.json.bak).\nCancel: keep editing, nothing is saved.")) saveTheme(error.body.version);
      return;
    }
    $("estate").textContent = `Not saved: ${error.message}`;
  }
}

async function revert() {
  if (edit.dirty && !confirm("Throw away your changes since the last save?")) return;
  const file = await fetch("/api/theme_file?" + new URLSearchParams({ theme: edit.loaded })).then(jsonOrThrow);
  loadText(file);
  preview();
}

async function copyTheme() {
  const current = theme();
  const name = prompt(`A name for the new theme (a copy of ${current.name}${edit.dirty ? ", with your changes" : ""}):`, `${current.name} copy`);
  if (!name) return;
  try {
    /* Unsaved changes go into the copy (if they're valid JSON), not the original. */
    const body = { theme: edit.loaded, name };
    if (edit.dirty && check(edit.cm.getValue()).parsed !== null) body.text = edit.cm.getValue();
    const answer = await fetch("/api/theme_copy", { method: "POST", headers: postHeaders(), body: JSON.stringify(body) }).then(jsonOrThrow);
    state.info = await fetch("/api/info").then(jsonOrThrow);
    state.theme = answer.theme;
    fillControls();
    edit.dirty = false;
    save();
    state.version = null;
    await poll();
    await buildEdit();
    $("estate").textContent = `Copied to ${answer.theme}: changes here are saved to it`;
  } catch (error) {
    alert(`Not copied: ${error.message}`);
  }
}

/* The theme changed on disk (poll): if nothing is unsaved, load it; else say so. */
async function editThemeChanged() {
  if (!edit.file || state.view !== "edit") return;
  let file;
  try { file = await fetch("/api/theme_file?" + new URLSearchParams({ theme: edit.loaded })).then(jsonOrThrow); } catch (e) { return; }
  if (file.version === edit.file.version) { preview(); return; }
  if (!edit.dirty) { loadText(file); preview(); $("estate").textContent = "Loaded the changes made on disk"; }
  else $("estate").textContent = "theme.json changed on disk: Revert loads it, Save keeps yours";
}

$("esave").onclick = () => saveTheme();
$("erevert").onclick = () => revert();
$("ecopy").onclick = () => copyTheme();
$("eshot").onchange = () => { edit.shot = $("eshot").value; preview(); };
$("eboxes").onchange = () => { const layer = document.querySelector("#eshotview .boxes"); if (layer) layer.hidden = !$("eboxes").checked; };
$("eformat").onclick = () => {
  try { const value = JSON.parse(edit.cm.getValue()); if (confirm("Rewrite theme.json with even indents? Arrays go one item a line.")) edit.cm.setValue(JSON.stringify(value, null, 4) + "\n"); }
  catch (e) { $("estate").textContent = "Fix the JSON mistakes first"; }
};
window.addEventListener("beforeunload", (event) => { if (edit.dirty) { event.preventDefault(); event.returnValue = ""; } });
