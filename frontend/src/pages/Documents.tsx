import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  FileText,
  Loader,
  ScanLine,
  Upload,
  TriangleAlert,
} from "lucide-react";

import {
  Button,
  Chip,
  ConfidenceBar,
  Metric,
  Panel,
  PanelHead,
} from "../components/ui";
import { PORT_OPS_API, READ_ONLY, uploadDocument } from "../lib/api";
import { relative, titleCase } from "../lib/format";
import { DOCUMENT_LABELS } from "../lib/mock/portops";
import { useData } from "../lib/store";
import type { ExtractedDocument } from "../lib/types";

const STAGES = [
  { key: "parse", label: "Extract text", detail: "PDF text layer, falling back to Textract OCR" },
  { key: "classify", label: "Classify", detail: "Match the document against the maritime type set" },
  { key: "extract", label: "Extract fields", detail: "Pull vessel identity, dates, cargo and people" },
  { key: "validate", label: "Validate", detail: "Field-level rules and confidence thresholds" },
];


function meanConfidence(d: ExtractedDocument) {
  const v = Object.values(d.fields);
  return v.reduce((a, f) => a + f.confidence, 0) / Math.max(1, v.length);
}

export default function Documents() {
  const { portCalls } = useData();
  const ALL_DOCS = useMemo(
    () => portCalls.flatMap((p) => p.documents.map((d) => ({ doc: d, call: p }))),
    [portCalls],
  );
  const [stage, setStage] = useState(-1);
  const [result, setResult] = useState<ExtractedDocument | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const sample = useMemo(
    () =>
      ALL_DOCS.find((d) => d.doc.extraction_method === "textract_ocr")?.doc ??
      ALL_DOCS[0].doc,
    [ALL_DOCS],
  );

  useEffect(() => {
    if (stage < 0 || stage >= STAGES.length) return;
    const t = setTimeout(() => setStage((s) => s + 1), 700);
    return () => clearTimeout(t);
  }, [stage]);

  useEffect(() => {
    if (stage === STAGES.length && !result) setResult(sample);
  }, [stage, result, sample]);

  const run = useCallback(
    async (file?: File) => {
      setError(null);
      setResult(null);
      setFileName(file?.name ?? "sample_ship_sanitation_certificate.pdf");
      setStage(0);
      if (file && PORT_OPS_API) {
        try {
          const live = await uploadDocument(file);
          if (live?.document) setResult(live.document as ExtractedDocument);
        } catch {
          setError(
            "Live extraction failed — showing the bundled sample instead.",
          );
        }
      }
    },
    [],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are currently supported.");
      return;
    }
    void run(file);
  };

  const stats = {
    docs: ALL_DOCS.length,
    ocr: ALL_DOCS.filter((d) => d.doc.extraction_method === "textract_ocr").length,
    fields: ALL_DOCS.reduce((a, d) => a + Object.keys(d.doc.fields).length, 0),
    low: ALL_DOCS.reduce(
      (a, d) =>
        a + Object.values(d.doc.fields).filter((f) => f.confidence < 0.7).length,
      0,
    ),
  };

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      <Panel className="rise" ticked>
        <div className="grid grid-cols-2 gap-px bg-[var(--color-rail)] xl:grid-cols-4">
          <div className="bg-[var(--color-hull)]">
            <Metric label="Documents parsed" value={stats.docs} hint="across every open port call" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Fields extracted" value={stats.fields} tone="agent" hint="with per-field confidence" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Routed to OCR" value={stats.ocr} tone="hold" hint="no usable PDF text layer" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Below 70%" value={stats.low} tone={stats.low ? "blocked" : "clear"} hint="fields flagged for review" />
          </div>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        {/* ---------------- ingest ---------------- */}
        <Panel className="rise" ticked>
          <PanelHead
            title="Ingest a document"
            sub={
              PORT_OPS_API
                ? "POST /documents/upload — live extraction service"
                : "Demo pipeline · set VITE_PORT_OPS_API to run the real extractor"
            }
            accent="var(--color-beacon)"
          />

          <div className="px-6 py-5">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => {
                if (READ_ONLY) return;
                input.current?.click();
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-[4px] border border-dashed px-6 py-10 text-center transition-colors ${
                dragging
                  ? "border-[var(--color-signal)] bg-[color-mix(in_srgb,var(--color-signal)_8%,transparent)]"
                  : "border-[var(--color-rail)] hover:border-[var(--color-mist)]"
              }`}
            >
              <Upload
                size={22}
                strokeWidth={1.5}
                className={dragging ? "text-[var(--color-signal)]" : "text-[var(--color-slate-ink)]"}
              />
              <div>
                <p className="text-[12.5px] text-[var(--color-chalk)]">
                  {READ_ONLY
                    ? "Upload is disabled on this deployment"
                    : "Drop a PDF declaration or certificate"}
                </p>
                <p className="mono mt-1 text-[10px] tracking-[0.1em] text-[var(--color-slate-ink)] uppercase">
                  {READ_ONLY
                    ? "documents below were extracted by the live service"
                    : "or click to browse"}
                </p>
              </div>
              <input
                ref={input}
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void run(f);
                }}
              />
            </div>

            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="mono truncate text-[10.5px] text-[var(--color-slate-ink)]">
                {fileName ?? "no file selected"}
              </span>
              <Button variant="signal" onClick={() => void run()}>
                run sample extraction
              </Button>
            </div>

            {error && (
              <p className="mono mt-3 flex items-center gap-2 text-[10.5px] text-[var(--color-port)]">
                <TriangleAlert size={11} /> {error}
              </p>
            )}

            {/* pipeline */}
            <ol className="mt-6 space-y-0">
              {STAGES.map((s, i) => {
                const done = stage > i;
                const active = stage === i;
                return (
                  <li
                    key={s.key}
                    className="flex items-center gap-3.5 border-b border-dashed border-[var(--color-rail)] py-3 last:border-0"
                    style={{ opacity: stage < 0 ? 0.4 : 1, transition: "opacity .3s" }}
                  >
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border"
                      style={{
                        borderColor: done
                          ? "var(--color-starboard)"
                          : active
                            ? "var(--color-beacon)"
                            : "var(--color-rail)",
                        color: done
                          ? "var(--color-starboard)"
                          : active
                            ? "var(--color-beacon)"
                            : "var(--color-slate-ink)",
                      }}
                    >
                      {done ? (
                        <Check size={11} />
                      ) : active ? (
                        <Loader size={11} className="animate-spin" />
                      ) : (
                        <span className="mono text-[9px]">{i + 1}</span>
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-[12.5px] font-medium"
                        style={{
                          color:
                            done || active
                              ? "var(--color-chalk)"
                              : "var(--color-slate-ink)",
                        }}
                      >
                        {s.label}
                      </div>
                      <div className="text-[10.5px] text-[var(--color-slate-ink)]">
                        {s.detail}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </Panel>

        {/* ---------------- result ---------------- */}
        <Panel className="rise" ticked>
          <PanelHead
            title="Extraction result"
            sub={
              result
                ? `${DOCUMENT_LABELS[result.document_type] ?? titleCase(result.document_type)} · ${Object.keys(result.fields).length} fields`
                : "Run an extraction to see structured output"
            }
            accent="var(--color-signal)"
            right={
              result && (
                <Chip tone={result.extraction_method === "textract_ocr" ? "hold" : "clear"}>
                  {result.extraction_method === "textract_ocr"
                    ? "textract ocr"
                    : "pdf text layer"}
                </Chip>
              )
            }
          />
          {result ? (
            <div className="px-6 py-4">
              {Object.entries(result.fields).map(([k, f], i) => (
                <div
                  key={k}
                  className="rise flex items-center justify-between gap-4 border-b border-dashed border-[var(--color-rail)] py-2.5 last:border-0"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <div className="min-w-0">
                    <div className="label">{k}</div>
                    <div
                      className={`mono mt-1 truncate text-[12.5px] ${
                        f.value === null
                          ? "text-[var(--color-port)] italic"
                          : "text-[var(--color-chalk)]"
                      }`}
                    >
                      {f.value === null ? "not found" : String(f.value)}
                    </div>
                  </div>
                  <ConfidenceBar value={f.confidence} />
                </div>
              ))}
            </div>
          ) : (
            <div className="px-6 py-16 text-center">
              <ScanLine
                size={26}
                strokeWidth={1.4}
                className="mx-auto text-[var(--color-rail)]"
              />
              <p className="mt-3 text-[12px] text-[var(--color-slate-ink)]">
                Nothing extracted yet.
              </p>
            </div>
          )}
        </Panel>
      </div>

      {/* ---------------- library ---------------- */}
      <Panel className="rise" ticked>
        <PanelHead
          title="Document library"
          sub="Everything the extraction service has produced today"
        />
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[900px]">
            <thead>
              <tr className="border-b border-[var(--color-rail)]">
                {["Document", "Port call", "Vessel", "Method", "Fields", "Confidence", "Received"].map(
                  (h) => (
                    <th key={h} className="label px-4 py-2.5 text-left">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {ALL_DOCS.slice(0, 26).map(({ doc, call }, i) => (
                <tr
                  key={doc.document_id}
                  className="rise border-b border-dashed border-[var(--color-rail)] transition-colors last:border-0 hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                  style={{ animationDelay: `${Math.min(i, 16) * 30}ms` }}
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {doc.extraction_method === "textract_ocr" ? (
                        <ScanLine size={13} className="text-[var(--color-signal)]" />
                      ) : (
                        <FileText size={13} className="text-[var(--color-slate-ink)]" />
                      )}
                      <span className="text-[12px] text-[var(--color-chalk)]">
                        {DOCUMENT_LABELS[doc.document_type] ??
                          titleCase(doc.document_type)}
                      </span>
                    </div>
                  </td>
                  <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-signal)]">
                    {call.port_call_id}
                  </td>
                  <td className="px-4 py-2.5 text-[11.5px] text-[var(--color-fog)]">
                    {call.vessel_name}
                  </td>
                  <td className="mono px-4 py-2.5 text-[10.5px] text-[var(--color-slate-ink)]">
                    {doc.extraction_method}
                  </td>
                  <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                    {Object.keys(doc.fields).length}
                  </td>
                  <td className="px-4 py-2.5">
                    <ConfidenceBar value={meanConfidence(doc)} />
                  </td>
                  <td className="mono px-4 py-2.5 text-[10.5px] text-[var(--color-slate-ink)]">
                    {relative(doc.received_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
