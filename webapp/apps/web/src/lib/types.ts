// Types mirroring publish_test.py's student_json / answers_json / timeline_json
// payloads (see webapp/db/schema.sql and publish_test.py).

export interface Option {
  letter: string;
  text: string;
}

export interface QuestionGroup {
  id: string;
  type:
    | "form_completion"
    | "note_completion"
    | "table_completion"
    | "flow_chart_completion"
    | "sentence_completion"
    | "summary_completion"
    | "short_answer"
    | "multiple_choice"
    | "multiple_response"
    | "matching"
    | "plan_map_labelling"
    | "diagram_labelling";
  from: number;
  to: number;
  instruction: string;
  heading: string;
  layout: string;
  options: Option[];
  visual_id: string;
  /** present only on multiple_response groups (added by publish_test.py) */
  letters_required?: number;
}

export interface Question {
  number: number;
  group: string;
  text: string;
  options: Option[];
}

export interface Visual {
  id: string;
  type: "map" | "floorplan" | "flowchart" | "timeline" | "process" | "diagram";
  title: string;
  purpose: string;
  mermaid: string;
  image_prompt: string;
  questions: number[];
  /** R2-hosted PNG URL, resolved server-side in the /api/tests/[slug] endpoint */
  image_url?: string;
}

export interface TestPart {
  part: number;
  situation: string;
  question_groups: QuestionGroup[];
  questions: Question[];
  visuals: Visual[];
}

export interface TestMetadata {
  title: string;
  target_band: string;
  difficulty: string;
  context: string;
  total_parts: number;
  total_questions: number;
  total_marks: number;
  generated_at: string;
  part_topics: Record<string, string>;
  visuals_required: boolean;
}

export interface StudentTest {
  metadata: TestMetadata;
  parts: TestPart[];
}

export interface TranscriptLine {
  speaker: string;
  line: string;
}

export interface TranscriptPayload {
  parts: Array<{ part: number; transcript: TranscriptLine[] }>;
}

export type SegmentKind =
  | "intro"
  | "intro_pause"
  | "narr_intro"
  | "prep"
  | "narr_listen"
  | "dialogue_1"
  | "narr_mid"
  | "mid_break"
  | "narr_listen2"
  | "dialogue_2"
  | "narr_end"
  | "checking"
  | "between_parts"
  | "turn_to_part"
  | "end_test";

export interface TimelineSegment {
  kind: SegmentKind;
  part: number | null;
  start: number;
  end: number;
  duration: number;
  q_from: number | null;
  q_to: number | null;
  countdown?: number;
  audio_file?: string;
}

export interface Timeline {
  sample_rate: number;
  total_duration: number;
  segments: TimelineSegment[];
}

export interface TestCatalogEntry {
  slug: string;
  title: string;
  target_band: string;
  context: string;
  part_topics: Record<string, string>;
  duration_sec: number;
}

export interface TestDetailResponse {
  slug: string;
  student: StudentTest;
  timeline: Timeline;
  audio_url: string;
}
