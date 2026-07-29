"use client";

import { useState, useEffect } from 'react';
import { db, NewsReport, AudienceConfig } from '@/lib/db';
import { Agent, generateNewsAnalysis } from '@/lib/ai';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Preloader } from '@/components/Preloader';
import { Progress } from '@/components/ui/progress';
import { Newspaper, Target, TrendingUp, AlertTriangle, Lightbulb, Activity, BarChart2 } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

import { fetchRealNews } from '@/app/actions/news';

export default function NewsPage() {
  const [reports, setReports] = useState<NewsReport[]>([]);
  const [audiences, setAudiences] = useState<AudienceConfig[]>([]);
  const [selectedAudience, setSelectedAudience] = useState<string>('');
  
  const [isGenerating, setIsGenerating] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [loadingProgress, setLoadingProgress] = useState(0);

  const loadData = async () => {
    const loadedReports = await db.newsReports.getAll();
    setReports(loadedReports.sort((a, b) => b.createdAt - a.createdAt));

    const loadedAudiences = await db.audiences.getAll();
    setAudiences(loadedAudiences);
    if (loadedAudiences.length > 0) {
      setSelectedAudience(loadedAudiences[0].id);
    }
  };

  useEffect(() => {
    document.title = "Новости и Тренды | Agora";
    loadData();
  }, []);

  const handleGenerate = async () => {
    if (!selectedAudience) {
      alert("Выберите аудиторию для анализа");
      return;
    }

    const audience = audiences.find(a => a.id === selectedAudience);
    if (!audience || !audience.agents || audience.agents.length === 0) {
      alert("Выбранная аудитория пуста или не найдена");
      return;
    }

    setIsGenerating(true);
    setLoadingProgress(10);
    setLoadingMessage("Подключение к Google News...");

    try {
      const realNews = await fetchRealNews();
      if (realNews.length === 0) {
        throw new Error("Не удалось загрузить новости. Попробуйте еще раз.");
      }

      setLoadingProgress(40);
      setLoadingMessage("Отправка новостей нейро-агентам...");

      const result = await generateNewsAnalysis(audience.agents, realNews);

      setLoadingProgress(80);
      setLoadingMessage("Анализ реакций аудитории...");

      const newReport: NewsReport = {
        id: uuidv4(),
        createdAt: Date.now(),
        audienceId: audience.id,
        newsItems: result.newsItems || [],
        analysis: result.analysis || {
          fears: [], hopes: [], expectations: [], overallMood: 'Н/Д', summary: 'Ошибка анализа', anxietyIndex: 50, trendingTopics: []
        }
      };

      await db.newsReports.save(newReport);
      await loadData();
      
      setLoadingProgress(100);
      setLoadingMessage("Готово!");
    } catch (error) {
      console.error(error);
      alert(error instanceof Error ? error.message : "Ошибка при генерации анализа новостей");
    } finally {
      setTimeout(() => setIsGenerating(false), 500);
    }
  };

  const deleteReport = async (id: string) => {
    if (confirm("Удалить этот отчет?")) {
      await db.newsReports.delete(id);
      loadData();
    }
  };

  return (
    <main className="flex-1 p-6 lg:p-8 overflow-y-auto w-full max-w-7xl mx-auto">
      <Preloader isVisible={isGenerating} progress={loadingProgress} message={loadingMessage} />

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Новости и Тренды</h2>
          <p className="text-muted-foreground">Мониторинг информационного поля и анализ реакций синтетической аудитории</p>
        </div>
        <div className="flex gap-4 items-center">
          <select 
            value={selectedAudience}
            onChange={(e) => setSelectedAudience(e.target.value)}
            className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {audiences.length === 0 && <option value="">Нет доступных аудиторий</option>}
            {audiences.map((aud) => (
              <option key={aud.id} value={aud.id}>{aud.name} ({aud.size} чел.)</option>
            ))}
          </select>
          <Button onClick={handleGenerate} disabled={isGenerating || audiences.length === 0}>
            <Newspaper className="mr-2 h-4 w-4" /> Анализировать
          </Button>
        </div>
      </div>

      {reports.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-12 text-center border-dashed">
          <CardHeader>
            <CardTitle>Нет данных</CardTitle>
            <CardDescription>
              Сгенерируйте первый отчет, выбрав аудиторию и нажав кнопку &quot;Анализировать&quot;.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-8">
          {reports.map((report) => {
            const audienceName = audiences.find(a => a.id === report.audienceId)?.name || 'Неизвестная аудитория';
            return (
              <Card key={report.id} className="overflow-hidden">
                <CardHeader className="bg-muted/50 border-b">
                  <div className="flex justify-between items-start">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5 text-primary" />
                        Сводка за {new Date(report.createdAt).toLocaleDateString()}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        Аудитория: {audienceName} | Настроение: <span className="font-semibold text-primary uppercase">{report.analysis.overallMood}</span>
                      </CardDescription>
                    </div>
                    <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => deleteReport(report.id)}>Удалить</Button>
                  </div>
                </CardHeader>
                <CardContent className="p-6">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    
                    {/* Новости */}
                    <div className="space-y-4">
                      <h3 className="text-lg font-semibold flex items-center gap-2">
                        <Newspaper className="h-5 w-5" /> Топ новостей недели
                      </h3>
                      <div className="space-y-4 max-h-[600px] overflow-y-auto pr-4 custom-scrollbar">
                        {report.newsItems.map((news, idx) => (
                          <div key={idx} className="border rounded-lg p-4 bg-card hover:bg-accent/5 transition-colors">
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{news.source}</span>
                            <h4 className="font-medium mt-1 leading-tight">{news.title}</h4>
                            <p className="text-sm text-muted-foreground mt-2">{news.summary}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Аналитика */}
                    <div className="space-y-6">
                      <h3 className="text-lg font-semibold flex items-center gap-2">
                        <Target className="h-5 w-5" /> Реакция аудитории
                      </h3>
                      
                      <div className="prose dark:prose-invert text-sm max-w-none">
                        <p>{report.analysis.summary}</p>
                      </div>

                      {/* Интерактивные графики: Индекс тревожности и Тренды */}
                      {(report.analysis.anxietyIndex !== undefined || (report.analysis.trendingTopics && report.analysis.trendingTopics.length > 0)) && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4 border-t border-b">
                          {report.analysis.anxietyIndex !== undefined && (
                            <div className="space-y-2">
                              <h4 className="text-sm font-semibold flex items-center gap-2 text-primary">
                                <Activity className="h-4 w-4" /> Индекс тревожности
                              </h4>
                              <div className="flex items-center gap-4">
                                <Progress value={report.analysis.anxietyIndex} className="h-3 flex-1" />
                                <span className="text-lg font-bold">{report.analysis.anxietyIndex}/100</span>
                              </div>
                              <p className="text-xs text-muted-foreground mt-1">Отражает общий уровень беспокойства аудитории.</p>
                            </div>
                          )}

                          {report.analysis.trendingTopics && report.analysis.trendingTopics.length > 0 && (
                            <div className="space-y-2">
                              <h4 className="text-sm font-semibold flex items-center gap-2 text-primary">
                                <BarChart2 className="h-4 w-4" /> Топ волнующих тем
                              </h4>
                              <div className="h-32">
                                <ResponsiveContainer width="100%" height="100%">
                                  <BarChart data={report.analysis.trendingTopics} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                                    <XAxis type="number" hide />
                                    <YAxis dataKey="topic" type="category" width={100} textAnchor="end" tick={{ fontSize: 11, fill: 'currentColor' }} axisLine={false} tickLine={false} />
                                    <Tooltip contentStyle={{ borderRadius: '8px', fontSize: '12px' }} />
                                    <Bar dataKey="weight" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]}>
                                      {report.analysis.trendingTopics.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={index === 0 ? 'hsl(var(--destructive))' : 'hsl(var(--primary))'} />
                                      ))}
                                    </Bar>
                                  </BarChart>
                                </ResponsiveContainer>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t">
                        <div className="space-y-3">
                          <h4 className="text-sm font-semibold flex items-center gap-2 text-red-500">
                            <AlertTriangle className="h-4 w-4" /> Страхи
                          </h4>
                          <ul className="text-sm space-y-2">
                            {report.analysis.fears.map((f, i) => <li key={i} className="bg-red-500/10 text-red-700 dark:text-red-400 p-2 rounded-md leading-tight">{f}</li>)}
                          </ul>
                        </div>
                        <div className="space-y-3">
                          <h4 className="text-sm font-semibold flex items-center gap-2 text-green-500">
                            <Lightbulb className="h-4 w-4" /> Надежды
                          </h4>
                          <ul className="text-sm space-y-2">
                            {report.analysis.hopes.map((h, i) => <li key={i} className="bg-green-500/10 text-green-700 dark:text-green-400 p-2 rounded-md leading-tight">{h}</li>)}
                          </ul>
                        </div>
                        <div className="space-y-3">
                          <h4 className="text-sm font-semibold flex items-center gap-2 text-blue-500">
                            <TrendingUp className="h-4 w-4" /> Ожидания
                          </h4>
                          <ul className="text-sm space-y-2">
                            {report.analysis.expectations.map((e, i) => <li key={i} className="bg-blue-500/10 text-blue-700 dark:text-blue-400 p-2 rounded-md leading-tight">{e}</li>)}
                          </ul>
                        </div>
                      </div>
                    </div>

                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </main>
  );
}
