export type SseStatus = "connecting" | "live" | "disconnected";

export type StageState = {
  name: string;
  label_zh?: string;
  status: string;
  timestamp?: string;
  stalled?: boolean;
  stalled_minutes?: number;
  error?: string;
  gated?: boolean;
  human_approved?: boolean;
  undeclared?: boolean;
  metadata?: Record<string, unknown>;
  partial_progress?: { beats_done?: unknown; completed_scene_ids?: unknown };
  history_entries?: { status?: string }[];
};

export type CommercialAsset = {
  path?: string;
  file?: string;
  role_zh?: string;
  exists?: boolean;
  selected?: boolean;
  hero_only_motion?: boolean;
};

export type CommercialBeat = {
  beat?: string;
  time?: string;
  copy_plan_zh?: string;
  shot_plan_zh?: string;
  generation_prompt_zh?: string;
  method?: string;
  provider?: string;
  model?: string;
  angle_use?: string;
  ref?: string;
  reference_path?: string;
  asset_path?: string;
  asset_plan_zh?: string;
  assignment_status?: string;
  assignment_status_zh?: string;
  assignment_reason?: string;
  assignment_warning?: string;
  assignment_warnings?: string[];
  required_count?: number;
  need_count?: number;
  available_count?: number;
  have_count?: number;
  need_detail_zh?: string;
  gap_fill?: string | null;
  reuse_status?: string | null;
  ledger?: LedgerItem[];
  planned_entries?: PlannedEntry[];
  candidate_previews?: CandidatePreview[];
}

export type CandidatePreview = {
  path?: string;
  file?: string;
  label_zh?: string;
  status?: string;
  review_status?: string;
  provider?: string;
  model?: string;
};

export type LedgerItem = {
  kind?: string;
  path?: string;
  file?: string;
  label_zh?: string;
  label?: string;
  selected?: boolean;
  exists?: boolean;
  missing_path?: string;
  note_zh?: string;
};

export type PlannedEntry = {
  kind?: string;
  status?: string;
  path?: string;
  exists?: boolean;
  label_zh?: string;
  prompt_zh?: string;
  provider?: string;
  model?: string;
  planned_output_path?: string;
  missing_output_path?: string;
  output_path?: string;
  error_zh?: string;
  preview_kind?: string;
};

export type TimelineMark = {
  seconds?: number;
  kind?: string;
  label?: string;
  beat?: string;
};

export type StageEvidenceItem = {
  status?: string;
  duration_seconds?: number;
  path?: string;
  exists?: boolean;
  missing_path?: string;
  missing_reason_zh?: string;
  artifact_path?: string;
  user_confirmation_text?: string;
  candidate?: { path?: string };
  issue_segments?: { beat?: string; time?: string; issue_zh?: string; issue?: string }[];
  modification_list?: string[];
  technical_probe?: {
    duration_seconds?: number;
    resolution?: string;
    fps?: number;
    has_audio?: boolean;
    issues?: string[];
  };
  issues_found?: string[];
  quality_status?: string;
  decision_label_zh?: string;
  decision?: string;
  decision_response_zh?: string;
  beat_ids?: string[];
};

export type BoardEvent = {
  ts?: string;
  tool?: string;
  scene_id?: string;
  event?: string;
  success?: boolean;
  duration_s?: number;
  cost_usd?: number;
};

export type EditingGate = {
  enabled?: boolean;
  friendly_zh?: string;
  reason_codes?: string[];
  cut_count?: number;
  latest_render?: { path?: string | null; exists?: boolean; artifact?: string };
};

export type EditCut = {
  id?: string;
  source?: string;
  in_seconds?: number;
  out_seconds?: number;
};

export type BoardState = {
  project_id: string;
  title: string;
  live?: boolean;
  last_activity?: number;
  locale?: string;
  has_pipeline_state?: boolean;
  pipeline: { pipeline_type: string; stages?: unknown[]; known?: boolean };
  stages: StageState[];
  artifacts: Record<string, unknown>;
  media: { renders: unknown[]; snapshots: unknown[]; music: unknown[] };
  events: BoardEvent[];
  storyboard: unknown;
  cost?: { total_spent_usd?: number; budget_remaining_usd?: number };
  editing_gate?: EditingGate | null;
  commercial: CommercialState | null;
};

export type CommercialState = {
  completed?: boolean;
  user_stage_zh?: string;
  review_mode?: string;
  review_mode_preset?: string;
  confirm_stop_ids?: string[];
  runner_status?: {
    phase?: string;
    friendly_zh?: string;
    current_question?: string;
    runner_alive?: boolean;
  };
  runner_bind?: { bound?: boolean };
  board_stop?: {
    stage?: string;
    paused?: boolean;
    producing_wait?: boolean;
    needs_user_decision?: boolean;
  };
  decision?: CommercialDecision;
  fast_track_pause?: { friendly_zh?: string; current_question?: string };
  cost_cny?: {
    spent_cny?: number;
    budget_cny?: number;
    remaining_cny?: number;
    spent_usd?: number;
  };
  brief_summary?: {
    theme?: string;
    duration_seconds?: number;
    production_tier?: string;
    video_channel?: string;
    video_model?: string;
    video_model_zh?: string;
    review_mode_zh?: string;
    review_mode_preset?: string;
    review_mode?: string;
    motion_mix?: string;
    motion_mix_zh?: string;
    ai_share_pct?: number | string | null;
    budget_cny?: number;
    candidate_mode_zh?: string;
    style_label_zh?: string;
    imported_asset_count?: number;
  };
  plan_archive?: {
    sealed_zh?: string;
    has_brief?: boolean;
    has_video_plan?: boolean;
    has_segment_cards?: boolean;
    segment_count?: number;
    overall_prompt_zh?: string;
  };
  decisions?: {
    category_zh?: string;
    category?: string;
    subject?: string;
    selected_label_zh?: string;
    selected?: string;
    user_response_text?: string;
    reason?: string;
  }[];
  assets?: CommercialAsset[];
  unused_assets?: { path?: string; file?: string; reason?: string; status?: string }[];
  asset_precheck?: {
    summary?: {
      total_images?: number;
      low_resolution_count?: number;
      duplicate_group_count?: number;
      vision_enriched?: boolean;
      vision_model?: string;
      needs_user_attention?: boolean;
    };
    entries?: {
      file?: string;
      suggested_class?: string;
      vision_description_zh?: string;
      issues?: string[];
      duplicate_of?: string;
    }[];
  };
  beats?: CommercialBeat[];
  batches?: unknown[];
  timeline?: { duration_seconds?: number; beat_marks?: TimelineMark[]; batch_marks?: TimelineMark[] };
  stage_evidence?: {
    sample?: StageEvidenceItem;
    draft?: StageEvidenceItem;
    compose?: StageEvidenceItem;
    delivery?: StageEvidenceItem;
    segment?: { exists?: boolean }[];
  };
  produce_job?: { beat_ids?: string[]; friendly_zh?: string; batch_id?: string };
  final_video?: { exists?: boolean; path?: string };
  interaction_intents?: InteractionIntent[];
  legacy_checkpoints?: { stage?: string }[];
  editing_gate?: EditingGate | null;
};

export type DecisionOption = {
  id?: string;
  option_id?: string;
  label_zh?: string;
  label?: string;
  description_zh?: string;
  impact_zh?: string;
  disabled?: boolean;
};

export type GapPlan = {
  covered?: { beat_id?: string; need_zh?: string; path?: string }[];
  gaps?: { beat_id?: string; need_zh?: string }[];
  reuse_paths?: string[];
  image_models?: { id: string; label_zh?: string; available?: boolean }[];
  image_key_present?: boolean;
  default_image_model?: string;
};

export type CommercialDecision = {
  paused?: boolean;
  producing_wait?: boolean;
  prompt_zh?: string;
  title_zh?: string;
  stage_label_zh?: string;
  stage?: string;
  context_zh?: string;
  examples_zh?: string;
  timestamp?: string;
  options?: DecisionOption[];
  gap_plan?: GapPlan;
};

export type InteractionIntent = {
  status?: string;
  stage?: string;
  summary?: string;
  revision?: string;
};

export type ContentView =
  | "plan"
  | "assets"
  | "sample"
  | "segment"
  | "draft"
  | "compose"
  | "delivery";
