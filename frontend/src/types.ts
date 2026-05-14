export type ApiError = {
  code: string;
  details?: unknown;
};

export type ApiResponse<T> = {
  success: boolean;
  data: T;
  message: string;
  error: ApiError | null;
};

export type UserPreferences = {
  travel_style: string[];
  favorite_categories: string[];
  budget_currency: string;
  language: string;
};

export type User = {
  id: string;
  google_id: string;
  email: string;
  name: string;
  profile_image?: string | null;
  preferences: UserPreferences;
  trips: string[];
  created_at: string;
  updated_at: string;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type AuthResponse = {
  user: User;
  tokens: TokenPair;
};

export type Coordinates = {
  lat: number;
  lng: number;
};

export type Place = {
  id: string;
  slug: string;
  name: string;
  category: string;
  coordinates: Coordinates;
  image_url: string;
  short_description: string;
  full_description: string;
  history: string;
  photo_spot_tips: string[];
  estimated_visit_duration: string;
  admission_fee?: string | null;
  location: string;
  tags: string[];
  popularity: number;
};

export type ItineraryPlace = {
  place_id?: string | null;
  name: string;
  coordinates?: Coordinates | null;
  category?: string | null;
  cuisine?: string[] | string | null;
  admission_fee?: string | null;
  admission_fee_amount?: number | null;
  rating?: number | null;
  review_count?: number | null;
  google_place_id?: string | null;
  google_maps_uri?: string | null;
};

export type RouteStep = {
  instruction: string;
  travel_mode?: string | null;
  line_name?: string | null;
  line_short_name?: string | null;
  vehicle_type?: string | null;
  departure_stop?: string | null;
  arrival_stop?: string | null;
  duration_text?: string | null;
  stop_count?: number | null;
};

export type RouteLeg = {
  mode: string;
  summary: string;
  distance_meters?: number | null;
  duration_seconds?: number | null;
  duration_text: string;
  buffer_minutes?: number | null;
  scheduled_duration_seconds?: number | null;
  scheduled_duration_text?: string | null;
  compact_summary?: string | null;
  steps: RouteStep[];
  transit_lines: string[];
  fallback: boolean;
};

export type ItineraryItem = {
  id?: string | null;
  time_slot: "morning" | "lunch" | "afternoon" | "evening";
  start_time: string;
  end_time?: string | null;
  title: string;
  place: ItineraryPlace;
  description: string;
  estimated_duration: string;
  duration_minutes?: number | null;
  role_label?: string | null;
  role_icon?: string | null;
  reasoning?: string | null;
  energy_level?: number | null;
  route_to_next?: RouteLeg | null;
};

export type ItineraryDay = {
  id?: string | null;
  day_number: number;
  date?: string | null;
  title: string;
  theme?: string | null;
  items: ItineraryItem[];
  route_summary?: string | null;
};

export type Trip = {
  id: string;
  user_id: string;
  trip_title: string;
  prompt?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  total_days: number;
  style_tags: string[];
  status: string;
  itinerary_days: ItineraryDay[];
  route_summary?: string | null;
  created_at: string;
  updated_at: string;
};

export type TripGenerateRequest = {
  prompt: string;
  start_date?: string;
  end_date?: string;
  total_days?: number;
  style_tags?: string[];
};

export type BudgetItem = {
  id: string;
  category: "attraction" | "hotel" | "custom" | "other";
  title: string;
  amount: number;
  currency: string;
  day_number?: number | null;
  note?: string | null;
};

export type BudgetSummary = {
  id: string;
  trip_id: string;
  attraction_total: number;
  hotel_total: number;
  custom_expenses: BudgetItem[];
  grand_total: number;
  currency: string;
  last_updated?: string;
};

export type Reservation = {
  id: string;
  trip_id: string;
  user_id: string;
  reservation_type: "hotel" | "flight" | "ticket" | "activity";
  provider: string;
  title: string;
  start_date?: string | null;
  end_date?: string | null;
  price: number;
  currency: string;
  status: "pending" | "confirmed" | "canceled";
  booking_reference?: string | null;
  created_at: string;
  updated_at: string;
};

export type DiaryEntry = {
  id: string;
  user_id: string;
  trip_id: string;
  entry_date: string;
  photo_urls: string[];
  emotion_tags: string[];
  notes: string;
  place?: string | null;
  title?: string | null;
  generated_diary_text?: string | null;
  mood_keywords: string[];
  created_at: string;
  updated_at: string;
};

export type DiaryGenerated = {
  title: string;
  generated_diary_text: string;
  mood_keywords: string[];
};

export type WeatherDay = {
  date: string;
  condition: string;
  icon: string;
  temp_min_c: number;
  temp_max_c: number;
  precipitation_chance: number;
  travel_tip: string;
};

export type WeatherForecast = {
  city: string;
  country: string;
  timezone: string;
  days: WeatherDay[];
};
