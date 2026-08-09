export interface Genre {
  id: number;
  name: string;
}

export interface Person {
  id: number;
  tmdb_id: number;
  name: string;
  profile_path: string | null;
  known_for_dept?: string;
}

export interface MovieCard {
  id: number;
  tmdb_id: number;
  title: string;
  poster_path: string | null;
  vote_average: number | null;
  release_date: string | null;
  genres: Genre[];
}

export interface CastMember {
  person: Person;
  character: string | null;
  cast_order: number;
  is_lead: boolean;
}

export interface MovieDetail extends MovieCard {
  original_title: string | null;
  overview: string | null;
  tagline: string | null;
  runtime: number | null;
  vote_count: number | null;
  popularity: number | null;
  backdrop_path: string | null;
  trailer_key: string | null;
  language: string | null;
  cast: CastMember[];
  directors: Person[];
  keywords: string[];
  user_rating: number | null;
  in_watchlist: boolean | null;
  user_liked: boolean | null;
}

export interface RecommendedMovie {
  movie: MovieCard;
  hybrid_score: number;
  content_score: number | null;
  collab_score: number | null;
  neural_score: number | null;
  popularity_score: number | null;
  explanation: string;
}

export interface HomeSection {
  section_key: string;
  title: string;
  items: RecommendedMovie[];
  anchor_movie: { id: number; title: string } | null;
}

export interface HomepageData {
  sections: HomeSection[];
  user_interaction_count: number;
  is_cold_start: boolean;
}

export interface SearchResult {
  movies: MovieCard[];
  total: number;
  query: string;
  semantic_used: boolean;
}
