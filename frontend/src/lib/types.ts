/**
 * Types mirror the FastAPI payloads exactly, so the console can be pointed at
 * the live services without reshaping anything:
 *   - rescheduling_agent  →  vessel_state / *_assignments / eta_history / schedule_changes
 *   - port_ops_agent      →  PortCallState / ExtractedDocument / ComplianceResult
 */

/* ============================================================
   Rescheduling agent
   ============================================================ */

export type ResourceType = "berth" | "pilot" | "tug";

export type AllocationStatus = "confirmed" | "unconfirmed" | "pending_review";

export interface Allocation {
  resource_type: ResourceType;
  resource_id: string;
  start_time: string;
  end_time: string;
  buffer_minutes: number;
  status: AllocationStatus;
}

export interface VesselState {
  vessel_name: string;
  imo_number: string;
  call_sign: string;
  flag: string;
  location_from: string;
  location_to: string;
  vessel_type: string;
  loa_m: number;
  original_eta: string;
  previous_eta: string | null;
  current_eta: string;
  eta_source: string;
  eta_confidence: number;
  status: "active" | "staged";
  last_updated: string;
  allocations: Record<ResourceType, Allocation | null>;
}

export interface EtaEvent {
  eta_event_id: number;
  vessel_name: string;
  imo_number: string;
  previous_eta: string | null;
  reported_eta: string;
  source: string;
  confidence: number;
  received_at: string;
}

export interface ScheduleOption {
  option_id: string;
  rank: number | null;
  valid: boolean;
  invalid_reason: string | null;
  score: number;
  moves: {
    resource_type: ResourceType;
    from_resource: string;
    to_resource: string;
    from_start: string;
    to_start: string;
    to_end: string;
  }[];
  displaced_vessels: string[];
  total_shift_minutes: number;
}

export interface ScheduleChange {
  change_id: number;
  vessel_name: string;
  imo_number: string;
  resource_type: ResourceType;
  resource_id: string;
  old_start_time: string | null;
  old_end_time: string | null;
  new_start_time: string;
  new_end_time: string;
  reason: string;
  decision_score: number;
  execution_mode: "autonomous" | "new_vessel_retry" | "manual";
  changed_at: string;
}

export interface AgentRun {
  run_id: string;
  vessel_name: string;
  imo_number: string;
  trigger: "ETA_CHANGED" | "NEW_VESSEL_DISCOVERED" | "INCOMPLETE_ASSIGNMENT";
  started_at: string;
  duration_ms: number;
  previous_eta: string | null;
  new_eta: string;
  options_generated: number;
  options_valid: number;
  outcome: "resources_allocated" | "pending_review" | "no_action";
  selected_option: string | null;
  rationale: string;
  steps: AgentStep[];
  options: ScheduleOption[];
}

export interface AgentStep {
  key: string;
  title: string;
  detail: string;
  actor: "monitor" | "agent" | "rules" | "database";
  status: "done" | "blocked";
  ms: number;
}

export interface AutomationJob {
  name: string;
  schedule: string;
  last_run: string | null;
  next_run: string;
  status: "ok" | "running" | "error" | "idle";
  summary: string;
}

export interface AutomationStatus {
  running: boolean;
  timezone: string;
  jobs: AutomationJob[];
}

export interface MonitorChange {
  event: "ETA_CHANGED" | "NEW_VESSEL_DISCOVERED";
  vessel_name: string;
  imo_number: string;
  previous_eta?: string;
  new_eta?: string;
  eta?: string;
  assigned?: Record<string, { resource_id: string; status: string }>;
  assignment_error?: string | null;
}

/* ============================================================
   Port-ops agent
   ============================================================ */

export type PortCallPhase = "arrival" | "operations" | "departure";

export type PortCallStatus =
  | "created"
  | "arrival_pending"
  | "arrival_checking"
  | "arrival_cleared"
  | "operations"
  | "departure_pending"
  | "departure_checking"
  | "departure_cleared"
  | "correction_required"
  | "human_review"
  | "inspection_required"
  | "inspection_in_progress"
  | "inspection_cleared"
  | "inspection_rejected"
  | "completed";

export interface ExtractedField {
  value: string | number | boolean | null;
  confidence: number;
  source_text: string | null;
}

export interface ExtractedDocument {
  document_id: string;
  document_type: string;
  file_name: string;
  pages: number;
  extraction_method: "text_layer" | "textract_ocr";
  received_at: string;
  fields: Record<string, ExtractedField>;
}

export interface ComplianceIssue {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  document_type: string | null;
  field: string | null;
}

export interface ComplianceResult {
  status: "PASS" | "CORRECTION_REQUIRED" | "HUMAN_REVIEW";
  issues: ComplianceIssue[];
}

export interface RiskResult {
  risk_score: number;
  risk_level: "low" | "medium" | "high";
  risk_factors: string[];
}

export interface InspectionDecision {
  decision: "inspection_required" | "no_inspection";
  reasons: string[];
}

export interface Escalation {
  action:
    | "NONE"
    | "CORRECTION_REQUIRED"
    | "HUMAN_REVIEW"
    | "INSPECTION_REQUIRED";
  message: string;
}

export interface PortCallEvent {
  event: string;
  description: string;
  source: string;
  at: string;
}

export interface PortCallState {
  port_call_id: string;
  vessel_name: string;
  imo_number: string;
  call_sign: string;
  flag: string;
  phase: PortCallPhase;
  status: PortCallStatus;
  first_singapore_call: boolean;
  purpose_of_call: string;
  carrying_dangerous_goods: boolean;
  radioactive_material: boolean;
  berth: string;
  eta: string;
  documents: ExtractedDocument[];
  events: PortCallEvent[];
  compliance: ComplianceResult;
  risk: RiskResult;
  inspection: InspectionDecision;
  escalation: Escalation;
  agent_action:
    | "PROCEED"
    | "REQUEST_CORRECTION"
    | "REQUEST_INSPECTION"
    | "REQUEST_HUMAN_REVIEW";
  agent_reasoning: string;
}
