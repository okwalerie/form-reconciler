// Run a fillable PDF's own calculation scripts outside Acrobat.
//
// Usage: node run_pdf.js extracted.json inputs.json [fields.json] > outputs.json
// extracted.json: fields, calculation order and document-level JS (from extract_pdf).
// inputs.json: [{fieldName: exportValue, ...}, ...]
// fields.json: optional list of field names; if given, each result is a list of
// their values in that order (compact for large runs), otherwise an object
//
// Implements just enough of the Acrobat JavaScript API (this.getField,
// event.value) to run the scripts in calculation order, as a viewer would.

const fs = require("fs");
const vm = require("vm");

const form = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const inputs = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const wanted = process.argv[4] ? JSON.parse(fs.readFileSync(process.argv[4], "utf8")) : null;

const doc = { fields: {} };
doc.getField = (name) => {
  const f = doc.fields[name];
  if (!f) throw new Error(`getField: no field named ${name}`);
  return f;
};

const ctx = vm.createContext({ event: null, console });
vm.runInContext(form.document_js.join("\n"), ctx);
const scripts = form.calculation_order.map((name) => ({
  name,
  fn: vm.runInContext(`(function () {\n${form.fields[name].calculate}\n})`, ctx),
}));

const results = inputs.map((values) => {
  for (const [name, f] of Object.entries(form.fields)) {
    doc.fields[name] = { name, value: f.default ?? "" };
  }
  for (const [name, v] of Object.entries(values)) doc.fields[name].value = v;
  for (const { name, fn } of scripts) {
    ctx.event = { value: doc.fields[name].value, target: doc.fields[name] };
    fn.call(doc);
    doc.fields[name].value = ctx.event.value;
  }
  if (wanted) return wanted.map((n) => doc.fields[n].value);
  return Object.fromEntries(Object.entries(doc.fields).map(([n, f]) => [n, f.value]));
});

process.stdout.write(JSON.stringify(results));
