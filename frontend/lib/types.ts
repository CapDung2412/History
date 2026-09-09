export type RecognitionStatus =
  | "accepted"
  | "needs_confirmation"
  | "rejected";

export type QualityStatus = "passed" | "warning" | "failed";

export interface QualityIssue {
  code: string;
  message: string;
  guidance?: string | null;
  severity?: "warning" | "error";
}

export interface QualityMetrics {
  width: number;
  height: number;
  file_size_bytes?: number;
  brightness?: number;
  sharpness?: number;
  blur_score?: number;
  glare_ratio?: number;
  [key: string]: number | undefined;
}

export interface QualityResult {
  status: QualityStatus;
  metrics: QualityMetrics;
  issues: QualityIssue[];
}

export interface ArtifactImage {
  id: string;
  url?: string | null;
  image_url?: string | null;
  filename?: string | null;
  caption: string;
  view?: string | null;
  year?: number | null;
  alt_text?: string | null;
}

export interface RecognitionCandidate {
  item_id: string;
  location_id?: string;
  name: string;
  title?: string;
  category: string;
  period?: string | null;
  historical_period?: string | null;
  year?: number | null;
  score: number;
  image_url?: string | null;
  image_caption?: string | null;
}

export interface RecognitionTimings {
  total?: number;
  quality?: number;
  embedding?: number;
  vector_search?: number;
  content_lookup?: number;
  [key: string]: number | undefined;
}

export interface RecognitionResponse {
  request_id: string;
  quality: QualityResult;
  recognition_status: RecognitionStatus;
  confidence_label: string;
  top_score: number | null;
  score_margin: number | null;
  candidates: RecognitionCandidate[];
  selected_item: RecognitionCandidate | null;
  timings_ms: RecognitionTimings;
}

export interface ArtifactLocation {
  address?: string | null;
  city?: string | null;
  province?: string | null;
  country?: string | null;
}

export interface Artifact {
  item_id: string;
  slug?: string;
  name: string;
  title?: string;
  category: string;
  tags: string[];
  historical_period?: string | null;
  period?: string | null;
  year?: number | null;
  description: string;
  event?: string | null;
  source?: string | null;
  source_verified?: boolean;
  location?: ArtifactLocation | null;
  images: ArtifactImage[];
}

export interface StoryQuick {
  title: string;
  category: string;
  period?: string | null;
  year?: number | null;
  image?: ArtifactImage | null;
}

export interface StoryOverview {
  description?: string | null;
  event?: string | null;
  what_it_is?: string | null;
  role?: string | null;
  context?: string | null;
  significance?: string | null;
  paragraphs?: string[];
}

export interface StoryDeep {
  description: string;
  event?: string | null;
  people?: string[];
  related_events?: string[];
  images: ArtifactImage[];
  source?: string | null;
  source_verified?: boolean;
}

export interface ArtifactStory {
  item_id: string;
  quick: StoryQuick;
  overview: StoryOverview;
  deep: StoryDeep;
}

export type ChallengeType =
  | "single_choice"
  | "true_false"
  | "period"
  | "category";

export interface ChallengeOption {
  id: string;
  label: string;
}

export interface Challenge {
  id: string;
  item_id: string;
  type: ChallengeType;
  question: string;
  options: ChallengeOption[];
  correct_option_id: string;
  explanation: string;
  source_field?: string;
}

export interface FeedbackPayload {
  is_correct: boolean;
  selected_item_id?: string;
  none_of_the_above?: boolean;
  comment?: string;
}

export interface FeedbackResponse {
  status: "recorded";
  request_id: string;
}
