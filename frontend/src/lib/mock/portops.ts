import type {
  ComplianceIssue,
  ComplianceResult,
  Escalation,
  ExtractedDocument,
  ExtractedField,
  InspectionDecision,
  PortCallEvent,
  PortCallPhase,
  PortCallState,
  PortCallStatus,
  RiskResult,
} from "../types";
import { VESSELS } from "./fleet";

const f = (
  value: ExtractedField["value"],
  confidence = 0.96,
  source_text?: string,
): ExtractedField => ({
  value,
  confidence,
  source_text: source_text ?? (value === null ? null : String(value)),
});

const iso = (d: Date) => d.toISOString();
const ago = (mins: number) => iso(new Date(Date.now() - mins * 60_000));

/* ------------------------------------------------------------
   The real, deterministic scoring rules from compliance/risk.py.
   Reimplemented here so the console can explain a score rather
   than just display one.
   ------------------------------------------------------------ */
export const RISK_WEIGHTS = {
  correction_required: 30,
  human_review: 20,
  dangerous_goods: 25,
  radioactive: 40,
  first_call: 10,
  inconsistency: 30,
} as const;

export function computeRisk(input: {
  compliance_status: ComplianceResult["status"];
  carrying_dangerous_goods: boolean;
  radioactive_material: boolean;
  first_singapore_call: boolean;
  document_inconsistency: boolean;
}): RiskResult {
  let score = 0;
  const risk_factors: string[] = [];

  if (input.compliance_status === "CORRECTION_REQUIRED") {
    score += RISK_WEIGHTS.correction_required;
    risk_factors.push("Compliance issues detected.");
  } else if (input.compliance_status === "HUMAN_REVIEW") {
    score += RISK_WEIGHTS.human_review;
    risk_factors.push("Human compliance review required.");
  }
  if (input.carrying_dangerous_goods) {
    score += RISK_WEIGHTS.dangerous_goods;
    risk_factors.push("Dangerous goods declared.");
  }
  if (input.radioactive_material) {
    score += RISK_WEIGHTS.radioactive;
    risk_factors.push("Radioactive material declared.");
  }
  if (input.first_singapore_call) {
    score += RISK_WEIGHTS.first_call;
    risk_factors.push("First Singapore port call.");
  }
  if (input.document_inconsistency) {
    score += RISK_WEIGHTS.inconsistency;
    risk_factors.push("Inconsistencies detected across documents.");
  }

  return {
    risk_score: score,
    risk_level: score >= 60 ? "high" : score >= 30 ? "medium" : "low",
    risk_factors,
  };
}

export function determineEscalation(
  status: ComplianceResult["status"],
  inspectionRequired: boolean,
): Escalation {
  if (status === "CORRECTION_REQUIRED")
    return {
      action: "CORRECTION_REQUIRED",
      message: "Agent must return the submission to the agent for correction.",
    };
  if (status === "HUMAN_REVIEW")
    return {
      action: "HUMAN_REVIEW",
      message: "A port officer must review this submission before clearance.",
    };
  if (inspectionRequired)
    return {
      action: "INSPECTION_REQUIRED",
      message: "Physical inspection must be completed before the phase can clear.",
    };
  return { action: "NONE", message: "No escalation required. Phase may clear." };
}

/* ------------------------------------------------------------
   Document builders
   ------------------------------------------------------------ */
export const DOCUMENT_LABELS: Record<string, string> = {
  certificate_of_registry: "Certificate of Registry",
  arrival_general_declaration: "Arrival General Declaration",
  departure_general_declaration: "Departure General Declaration",
  crew_list: "Crew List",
  cargo_declaration: "Cargo Declaration",
  ship_sanitation_certificate: "Ship Sanitation Control Certificate",
  maritime_declaration_of_health: "Maritime Declaration of Health",
  dangerous_goods_manifest: "Dangerous Goods Manifest",
  bunker_delivery_note: "Bunker Delivery Note",
};

let docSeq = 1000;

function doc(
  document_type: string,
  fields: Record<string, ExtractedField>,
  opts: Partial<ExtractedDocument> = {},
): ExtractedDocument {
  docSeq += 1;
  return {
    document_id: `DOC-${docSeq}`,
    document_type,
    file_name: `${document_type}.pdf`,
    pages: opts.pages ?? 2,
    extraction_method: opts.extraction_method ?? "text_layer",
    received_at: opts.received_at ?? ago(180),
    fields,
    ...opts,
  };
}

interface Recipe {
  port_call_id: string;
  /** Matched by name so each story lands on a vessel it actually fits. */
  vessel: string;
  phase: PortCallPhase;
  first_singapore_call: boolean;
  purpose_of_call: string;
  carrying_dangerous_goods: boolean;
  radioactive_material: boolean;
  issues: ComplianceIssue[];
  complianceStatus: ComplianceResult["status"];
  inspection: InspectionDecision;
  status: PortCallStatus;
  extraDocs?: string[];
  ocrDoc?: string;
  agent_reasoning: string;
}

const RECIPES: Recipe[] = [
  {
    port_call_id: "SGSIN-2601",
    vessel: "APL TEMASEK",
    phase: "arrival",
    first_singapore_call: false,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: false,
    radioactive_material: false,
    issues: [],
    complianceStatus: "PASS",
    inspection: { decision: "no_inspection", reasons: ["Low risk, all required documents consistent."] },
    status: "arrival_cleared",
    agent_reasoning:
      "All five required arrival documents are present, every cross-document field agrees, and no risk factor applies. Nothing here needs a human. Advancing the port call to operations.",
  },
  {
    port_call_id: "SGSIN-2602",
    vessel: "STAR OF MALACCA",
    phase: "arrival",
    first_singapore_call: false,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: true,
    radioactive_material: false,
    issues: [
      {
        code: "FIELD_MISMATCH",
        message:
          "call_sign differs between certificate_of_registry (9V1234) and arrival_general_declaration (9V5678).",
        severity: "error",
        document_type: "arrival_general_declaration",
        field: "call_sign",
      },
    ],
    complianceStatus: "CORRECTION_REQUIRED",
    inspection: {
      decision: "inspection_required",
      reasons: ["Document inconsistency on a vessel-identity field.", "Dangerous goods declared."],
    },
    status: "correction_required",
    extraDocs: ["dangerous_goods_manifest"],
    agent_reasoning:
      "The call sign on the arrival declaration does not match the certificate of registry. Vessel identity fields are not something I will reconcile on my own, so the submission goes back to the agent for correction before any clearance decision.",
  },
  {
    port_call_id: "SGSIN-2603",
    vessel: "EAGLE MELBOURNE",
    phase: "arrival",
    first_singapore_call: true,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: true,
    radioactive_material: true,
    issues: [
      {
        code: "MISSING_DOCUMENT",
        message: "ship_sanitation_certificate is required for a first Singapore call.",
        severity: "warning",
        document_type: "ship_sanitation_certificate",
        field: null,
      },
    ],
    complianceStatus: "HUMAN_REVIEW",
    inspection: {
      decision: "inspection_required",
      reasons: [
        "Radioactive material declared.",
        "First Singapore call.",
        "Risk score in the high band.",
      ],
    },
    status: "inspection_required",
    extraDocs: ["dangerous_goods_manifest"],
    ocrDoc: "ship_sanitation_certificate",
    agent_reasoning:
      "Radioactive material plus a first Singapore call puts this at risk 95, and the sanitation certificate is missing. I am not clearing this. Physical inspection is mandatory and a port officer must review the submission.",
  },
  {
    port_call_id: "SGSIN-2604",
    vessel: "MAERSK SENTOSA",
    phase: "operations",
    first_singapore_call: false,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: false,
    radioactive_material: false,
    issues: [],
    complianceStatus: "PASS",
    inspection: { decision: "no_inspection", reasons: ["Arrival cleared without findings."] },
    status: "operations",
    agent_reasoning:
      "Arrival cleared cleanly. The vessel is working cargo; departure documents are not expected until the operations phase closes.",
  },
  {
    port_call_id: "SGSIN-2605",
    vessel: "HAFNIA VICTORIA",
    phase: "departure",
    first_singapore_call: false,
    purpose_of_call: "bunkering",
    carrying_dangerous_goods: false,
    radioactive_material: false,
    issues: [],
    complianceStatus: "PASS",
    inspection: { decision: "no_inspection", reasons: ["No outstanding findings from arrival."] },
    status: "departure_cleared",
    extraDocs: ["departure_general_declaration", "bunker_delivery_note"],
    agent_reasoning:
      "Departure declaration and bunker delivery note agree with the arrival record. Nothing outstanding. Port call may complete.",
  },
  {
    port_call_id: "SGSIN-2606",
    vessel: "TIGER SPIRIT",
    phase: "arrival",
    first_singapore_call: true,
    purpose_of_call: "repair",
    carrying_dangerous_goods: false,
    radioactive_material: false,
    issues: [
      {
        code: "LOW_CONFIDENCE",
        message:
          "gross_tonnage extracted at 0.48 confidence from a scanned page; value could not be corroborated.",
        severity: "warning",
        document_type: "certificate_of_registry",
        field: "gross_tonnage",
      },
      {
        code: "EXPIRED_DOCUMENT",
        message: "ship_sanitation_certificate expired 2026-08-19.",
        severity: "error",
        document_type: "ship_sanitation_certificate",
        field: "expiry_date",
      },
    ],
    complianceStatus: "CORRECTION_REQUIRED",
    inspection: { decision: "no_inspection", reasons: ["Awaiting corrected submission."] },
    status: "correction_required",
    ocrDoc: "certificate_of_registry",
    agent_reasoning:
      "The sanitation certificate is expired and the tonnage field came off a scan at 0.48 confidence. Both are correctable by the agent, so this returns for correction rather than escalating to an officer.",
  },
  {
    port_call_id: "SGSIN-2607",
    vessel: "NYK ATLAS",
    phase: "arrival",
    first_singapore_call: false,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: false,
    radioactive_material: false,
    issues: [],
    complianceStatus: "PASS",
    inspection: { decision: "no_inspection", reasons: ["Low risk."] },
    status: "inspection_cleared",
    agent_reasoning:
      "Random physical inspection completed by the boarding officer with no findings. Arrival cleared; the port call can advance.",
  },
  {
    port_call_id: "SGSIN-2608",
    vessel: "GOLDEN STRAIT",
    phase: "arrival",
    first_singapore_call: false,
    purpose_of_call: "cargo",
    carrying_dangerous_goods: true,
    radioactive_material: false,
    issues: [
      {
        code: "FIELD_MISMATCH",
        message:
          "imo_number differs between certificate_of_registry (9256179) and cargo_declaration (9256719).",
        severity: "error",
        document_type: "cargo_declaration",
        field: "imo_number",
      },
      {
        code: "MISSING_FIELD",
        message: "total_cargo is absent from the cargo declaration.",
        severity: "error",
        document_type: "cargo_declaration",
        field: "total_cargo",
      },
    ],
    complianceStatus: "CORRECTION_REQUIRED",
    inspection: {
      decision: "inspection_required",
      reasons: ["Dangerous goods declared with an inconsistent manifest."],
    },
    status: "inspection_in_progress",
    extraDocs: ["dangerous_goods_manifest"],
    agent_reasoning:
      "Two digits are transposed in the IMO number on the cargo declaration and the cargo total is blank — on a dangerous-goods call that combination is not something to wave through. Inspection is under way.",
  },
];

function buildDocuments(
  recipe: Recipe,
  vesselName: string,
  imo: string,
  callSign: string,
  flag: string,
  vesselType: string,
) {
  const base = [
    doc("certificate_of_registry", {
      vessel_name: f(vesselName),
      imo_number: f(imo),
      call_sign: f(callSign),
      flag: f(flag),
      port_of_registry: f("Singapore"),
      official_number: f("398271"),
      gross_tonnage: f(
        62410,
        recipe.ocrDoc === "certificate_of_registry" ? 0.48 : 0.97,
      ),
      issuing_authority: f("Maritime and Port Authority of Singapore"),
      issue_date: f("2021-03-14"),
    }),
    doc("arrival_general_declaration", {
      vessel_name: f(vesselName),
      imo_number: f(imo),
      call_sign: f(
        recipe.issues.some((i) => i.field === "call_sign") ? "9V5678" : callSign,
        0.93,
      ),
      flag: f(flag),
      vessel_type: f(vesselType),
      arrival_date_time: f(new Date(Date.now() + 3 * 3600_000).toISOString().slice(0, 16)),
      last_port: f("Port Klang"),
      purpose_of_call: f(recipe.purpose_of_call),
      master: f("A. Ramachandran"),
      crew: f(21),
      passengers: f(0),
      gross_tonnage: f(62410),
    }),
    doc("crew_list", {
      vessel_name: f(vesselName),
      imo_number: f(imo),
      crew: f(21),
      master: f("A. Ramachandran"),
    }),
    doc("cargo_declaration", {
      vessel_name: f(vesselName),
      imo_number: f(
        recipe.issues.some((i) => i.field === "imo_number") ? "9256719" : imo,
        0.88,
      ),
      total_cargo: recipe.issues.some((i) => i.field === "total_cargo")
        ? f(null, 0)
        : f("8 240 t"),
      last_port: f("Port Klang"),
      next_port: f("Hong Kong"),
    }),
    doc("maritime_declaration_of_health", {
      vessel_name: f(vesselName),
      imo_number: f(imo),
      master: f("A. Ramachandran"),
      crew: f(21),
    }),
  ];

  (recipe.extraDocs ?? []).forEach((t) =>
    base.push(
      doc(t, {
        vessel_name: f(vesselName),
        imo_number: f(imo),
        ...(t === "dangerous_goods_manifest"
          ? { total_cargo: f("IMDG Class 3 · 140 t"), issuing_authority: f("Shipper") }
          : {}),
        ...(t === "bunker_delivery_note"
          ? { total_cargo: f("MGO 480 t"), issue_date: f("2026-09-06") }
          : {}),
        ...(t === "departure_general_declaration"
          ? {
              departure_date_time: f(
                new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 16),
              ),
              next_port: f("Hong Kong"),
            }
          : {}),
      }),
    ),
  );

  if (recipe.ocrDoc === "ship_sanitation_certificate") {
    base.push(
      doc(
        "ship_sanitation_certificate",
        {
          vessel_name: f(vesselName, 0.71),
          imo_number: f(imo, 0.64),
          expiry_date: f("2026-08-19", 0.58),
          issuing_authority: f("Port Health Authority", 0.52),
        },
        { extraction_method: "textract_ocr", pages: 1 },
      ),
    );
  }

  return base;
}

function buildEvents(recipe: Recipe): PortCallEvent[] {
  const events: PortCallEvent[] = [
    {
      event: "PORT_CALL_CREATED",
      description: "Port call created from the OCEANS-X arrival feed.",
      source: "system",
      at: ago(410),
    },
    {
      event: "DOCUMENTS_SUBMITTED",
      description: "Submission received and queued for extraction.",
      source: "agent_portal",
      at: ago(360),
    },
    {
      event: "DOCUMENTS_EXTRACTED",
      description: "Text layer parsed; scanned pages routed to Textract OCR.",
      source: "ocr_service",
      at: ago(352),
    },
    {
      event: "COMPLIANCE_CHECKED",
      description: `Compliance check completed with status ${recipe.complianceStatus}.`,
      source: "compliance_engine",
      at: ago(348),
    },
  ];

  if (recipe.inspection.decision === "inspection_required")
    events.push({
      event: "INSPECTION_REQUIRED",
      description: recipe.inspection.reasons.join(" "),
      source: "inspection_rules",
      at: ago(344),
    });

  if (recipe.status === "inspection_in_progress")
    events.push({
      event: "INSPECTION_STARTED",
      description: "Boarding officer assigned; inspection under way at the berth.",
      source: "port_officer",
      at: ago(120),
    });

  if (recipe.status === "inspection_cleared")
    events.push({
      event: "INSPECTION_COMPLETED",
      description: "Inspection cleared with no findings.",
      source: "port_officer",
      at: ago(96),
    });

  if (recipe.status === "arrival_cleared" || recipe.status === "operations")
    events.push({
      event: "ARRIVAL_CLEARED",
      description: "Arrival phase cleared by the agent.",
      source: "workflow",
      at: ago(340),
    });

  if (recipe.status === "operations")
    events.push({
      event: "PORT_CALL_ADVANCED",
      description: "Arrival cleared. Port call advanced to operations.",
      source: "workflow",
      at: ago(338),
    });

  if (recipe.status === "departure_cleared")
    events.push({
      event: "DEPARTURE_CLEARED",
      description: "Departure cleared. Port call may complete.",
      source: "workflow",
      at: ago(60),
    });

  return events.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}

export const PORT_CALLS: PortCallState[] = RECIPES.map((recipe) => {
  const v =
    VESSELS.find((x) => x.vessel_name === recipe.vessel) ?? VESSELS[0];
  const documents = buildDocuments(
    recipe,
    v.vessel_name,
    v.imo_number,
    v.call_sign,
    v.flag,
    v.vessel_type ?? "Container",
  );
  const compliance: ComplianceResult = {
    status: recipe.complianceStatus,
    issues: recipe.issues,
  };
  const risk = computeRisk({
    compliance_status: recipe.complianceStatus,
    carrying_dangerous_goods: recipe.carrying_dangerous_goods,
    radioactive_material: recipe.radioactive_material,
    first_singapore_call: recipe.first_singapore_call,
    document_inconsistency: recipe.issues.some((i) => i.code === "FIELD_MISMATCH"),
  });

  const agent_action =
    recipe.complianceStatus === "CORRECTION_REQUIRED"
      ? "REQUEST_CORRECTION"
      : recipe.complianceStatus === "HUMAN_REVIEW"
        ? "REQUEST_HUMAN_REVIEW"
        : recipe.inspection.decision === "inspection_required"
          ? "REQUEST_INSPECTION"
          : "PROCEED";

  return {
    port_call_id: recipe.port_call_id,
    vessel_name: v.vessel_name,
    imo_number: v.imo_number,
    call_sign: v.call_sign,
    flag: v.flag,
    phase: recipe.phase,
    status: recipe.status,
    first_singapore_call: recipe.first_singapore_call,
    purpose_of_call: recipe.purpose_of_call,
    carrying_dangerous_goods: recipe.carrying_dangerous_goods,
    radioactive_material: recipe.radioactive_material,
    berth: v.allocations.berth?.resource_id ?? "—",
    eta: v.current_eta,
    documents,
    events: buildEvents(recipe),
    compliance,
    risk,
    inspection: recipe.inspection,
    escalation: determineEscalation(
      recipe.complianceStatus,
      recipe.inspection.decision === "inspection_required",
    ),
    agent_action,
    agent_reasoning: recipe.agent_reasoning,
  } satisfies PortCallState;
});

export const portCallById = (id: string) =>
  PORT_CALLS.find((p) => p.port_call_id === id);

export const complianceStats = () => ({
  total: PORT_CALLS.length,
  cleared: PORT_CALLS.filter((p) =>
    ["arrival_cleared", "operations", "departure_cleared", "inspection_cleared", "completed"].includes(
      p.status,
    ),
  ).length,
  correction: PORT_CALLS.filter((p) => p.status === "correction_required").length,
  review: PORT_CALLS.filter((p) => p.status === "human_review").length,
  inspection: PORT_CALLS.filter((p) =>
    ["inspection_required", "inspection_in_progress"].includes(p.status),
  ).length,
  documents: PORT_CALLS.reduce((a, p) => a + p.documents.length, 0),
  fieldsExtracted: PORT_CALLS.reduce(
    (a, p) => a + p.documents.reduce((b, d) => b + Object.keys(d.fields).length, 0),
    0,
  ),
  avgConfidence:
    PORT_CALLS.flatMap((p) =>
      p.documents.flatMap((d) => Object.values(d.fields).map((x) => x.confidence)),
    ).reduce((a, b) => a + b, 0) /
    PORT_CALLS.flatMap((p) =>
      p.documents.flatMap((d) => Object.values(d.fields)),
    ).length,
});
