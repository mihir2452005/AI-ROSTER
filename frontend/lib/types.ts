/* RoastGPT — TypeScript types for the API */

export type RoastMode =
  | "friendly"
  | "savage"
  | "programmer"
  | "student"
  | "gamer"
  | "corporate"
  | "startup"
  | "general";

export type Personality =
  | "savage_one"
  | "sarcastic_friend"
  | "toxic_interviewer"
  | "startup_investor"
  | "professor"
  | "gamer";

export interface SessionScores {
  confidence_lost: number;
  emotional_damage: number;
  delusion_level: string;
  questionable_decisions: number;
  reality_checks: number;
  excuses_used: number;
  recovery_time: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intents?: string[];
  // Optional client-side id used by ChatClient to identify
  // optimistic messages and roll them back on failure without
  // affecting the rest of the list (e.g., after a 404-recovery path
  // has replaced the whole list).
  _id?: string;
}

export interface StartSessionRequest {
  mode: RoastMode;
  personality: Personality;
  username?: string;
  roaster_gender?: "male" | "female" | "neutral";
}

export interface StartSessionResponse {
  session_id: string;
  opener: string;
  scores: SessionScores;
  mode: RoastMode;
  personality: Personality;
  roaster_gender?: "male" | "female" | "neutral" | null;
}

export interface RoastRequest {
  message: string;
}

export interface RoastResponse {
  roast: string;
  scores: SessionScores;
  intents_detected: string[];
  is_opener: boolean;
  is_closer: boolean;
  is_comeback: boolean;
  template_id: string | null;
}

export interface EndSessionResponse {
  session_id: string;
  final_scores: SessionScores;
  closer: string | null;
  share_url: string | null;
}

export interface SessionStateResponse {
  session_id: string;
  mode: RoastMode;
  personality: Personality;
  message_count: number;
  scores: SessionScores;
  history: ChatMessage[];
  is_ended: boolean;
}

export const MODES: { value: RoastMode; label: string; emoji: string; description: string }[] = [
  { value: "friendly",   label: "Friendly Roast",  emoji: "💛", description: "Light teasing. Safe to send to your mom." },
  { value: "savage",     label: "Savage Roast",    emoji: "🔥", description: "Brutal but safe. No mercy, no chill." },
  { value: "programmer", label: "Programmer Roast", emoji: "💻", description: "Code reviews from hell. Stack Overflow is tired of you." },
  { value: "student",    label: "Student Roast",   emoji: "🎓", description: "Your GPA, your procrastination, your excuses — all roasted." },
  { value: "gamer",      label: "Gamer Roast",     emoji: "🎮", description: "Trash-talk like it's a ranked match. GG." },
  { value: "corporate",  label: "Corporate Roast", emoji: "💼", description: "LinkedIn buzzwords, meetings about meetings." },
  { value: "startup",    label: "Startup Roast",   emoji: "📈", description: "Notion docs and Squarespace domains. TAM = everyone." },
];

export const PERSONALITIES: { value: Personality; label: string; emoji: string; description: string }[] = [
  { value: "savage_one",        label: "The Savage One",        emoji: "💀", description: "Maximum damage. No mercy." },
  { value: "sarcastic_friend",  label: "The Sarcastic Friend",  emoji: "🙃", description: "Playful, loving, but cuts deep." },
  { value: "toxic_interviewer", label: "The Toxic Interviewer", emoji: "💼", description: "World's toughest recruiter." },
  { value: "startup_investor",  label: "The Startup Investor",  emoji: "📉", description: "Destroys startup ideas with VC-speak." },
  { value: "professor",         label: "The Professor",         emoji: "📚", description: "Academically humiliates you with citations." },
  { value: "gamer",             label: "The Gamer",             emoji: "🕹️", description: "Trash-talks like it's ranked." },
];
