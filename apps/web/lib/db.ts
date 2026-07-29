import localforage from 'localforage';
import { v4 as uuidv4 } from 'uuid';
import { Agent } from './ai';

if (typeof window !== 'undefined') {
  localforage.config({
    name: 'AgoraDB',
    storeName: 'agora_data'
  });
}

export interface Episode {
  id: string;
  title: string;
  url: string;
}

export type QuestionType = 'rating' | 'emotions' | 'values' | 'nps' | 'open' | 'matrix' | 'slogan' | 'retention';

export interface SurveyQuestion {
  id: string;
  type: QuestionType;
  text: string;
  options?: string[];
  scale?: number;
  max?: number;
}

export interface SurveyConfig {
  id: string;
  name: string;
  questions: SurveyQuestion[];
  createdAt: number;
}

export interface Project {
  id: string;
  title: string;
  description: string;
  episodes: Episode[];
  audienceId?: string;
  surveyId?: string;
  status: 'draft' | 'in_progress' | 'completed';
  createdAt: number;
  results?: {
    responses: any[];
    report: any;
  };
}

export interface AudienceConfig {
  id: string;
  name: string;
  size: number;
  agents: Agent[];
  createdAt: number;
}

export interface NewsReport {
  id: string;
  createdAt: number;
  audienceId: string;
  newsItems: { title: string; source: string; summary: string }[];
  analysis: {
    fears: string[];
    hopes: string[];
    expectations: string[];
    overallMood: string;
    summary: string;
    anxietyIndex?: number;
    trendingTopics?: { topic: string; weight: number }[];
  };
}

export const db = {
  projects: {
    getAll: async () => (await localforage.getItem<Project[]>('projects')) || [],
    get: async (id: string) => {
      const projects = await db.projects.getAll();
      return projects.find(p => p.id === id);
    },
    save: async (project: Project) => {
      const projects = await db.projects.getAll();
      const existing = projects.findIndex(p => p.id === project.id);
      if (existing >= 0) projects[existing] = project;
      else projects.push(project);
      await localforage.setItem('projects', projects);
    },
    delete: async (id: string) => {
      const projects = await db.projects.getAll();
      await localforage.setItem('projects', projects.filter(p => p.id !== id));
    }
  },
  audiences: {
    getAll: async () => (await localforage.getItem<AudienceConfig[]>('audiences')) || [],
    get: async (id: string) => {
      const audiences = await db.audiences.getAll();
      return audiences.find(a => a.id === id);
    },
    save: async (aud: AudienceConfig) => {
      const audiences = await db.audiences.getAll();
      const existing = audiences.findIndex(a => a.id === aud.id);
      if (existing >= 0) audiences[existing] = aud;
      else audiences.push(aud);
      await localforage.setItem('audiences', audiences);
    },
    delete: async (id: string) => {
      const audiences = await db.audiences.getAll();
      await localforage.setItem('audiences', audiences.filter(a => a.id !== id));
    }
  },
  surveys: {
    getAll: async () => (await localforage.getItem<SurveyConfig[]>('surveys')) || [],
    get: async (id: string) => {
      const surveys = await db.surveys.getAll();
      return surveys.find(s => s.id === id);
    },
    save: async (survey: SurveyConfig) => {
      const surveys = await db.surveys.getAll();
      const existing = surveys.findIndex(s => s.id === survey.id);
      if (existing >= 0) surveys[existing] = survey;
      else surveys.push(survey);
      await localforage.setItem('surveys', surveys);
    },
    delete: async (id: string) => {
      const surveys = await db.surveys.getAll();
      await localforage.setItem('surveys', surveys.filter(s => s.id !== id));
    }
  },
  newsReports: {
    getAll: async () => (await localforage.getItem<NewsReport[]>('newsReports')) || [],
    get: async (id: string) => {
      const reports = await db.newsReports.getAll();
      return reports.find(r => r.id === id);
    },
    save: async (report: NewsReport) => {
      const reports = await db.newsReports.getAll();
      const existing = reports.findIndex(r => r.id === report.id);
      if (existing >= 0) reports[existing] = report;
      else reports.push(report);
      await localforage.setItem('newsReports', reports);
    },
    delete: async (id: string) => {
      const reports = await db.newsReports.getAll();
      await localforage.setItem('newsReports', reports.filter(r => r.id !== id));
    }
  }
};
