export interface ChatResult {
  thread_id: string;
  answer: string;
}

export interface ThreadItem {
  thread_id: string;
  title: string;
  last_message_preview: string;
  updated_at: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface UserProfile {
  city: string;
  dining_preferences: string[];
  transport_preferences: string[];
  accommodation_preferences: string[];
  activity_preferences: string[];
}

export const emptyProfile = (): UserProfile => ({
  city: "",
  dining_preferences: [],
  transport_preferences: [],
  accommodation_preferences: [],
  activity_preferences: [],
});
