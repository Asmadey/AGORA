/** Shared AGORA types — safe to import from both client and server. */

export interface Agent {
  id: string;
  name: string;
  age: number;
  gender: string;
  city: string;
  profession: string;
  income: string;
  values: string[];
  personality: string;
  newsMemory?: {
    dominantNarratives: string[];
    anxietyIndex: number;
    trendingTopics: string[];
  };
  economicContext?: {
    financialWellbeing: number;
    economicAnxiety: number;
  };
}

/** Five brief criteria (1–10) + qualitative fields. */
export interface SurveyResponse {
  agentId: string;
  overallScore: number; // Общее впечатление
  plotScore: number; // Сюжет
  actingScore: number; // Игра актёров
  musicScore: number; // Музыка
  cameraScore: number; // Качество съёмок
  emotions: string[];
  values: string[];
  nps: number;
  qualitativeFeedback: string;
}

export interface Report {
  summary: string;
  averageScores: {
    overall: number;
    plot: number;
    acting: number;
    music: number;
    camera: number;
  };
  npsScore: number;
  topEmotions: { name: string; count: number }[];
  topValues: { name: string; count: number }[];
}
