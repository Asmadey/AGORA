"use client"

import React, { useEffect, useState, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { db, Project, AudienceConfig, SurveyConfig } from '@/lib/db';
import { simulateSurvey, generateReport, chatWithAudience, Agent } from '@/lib/ai';
import { ArrowLeft, Play, FileText, Users, Film, CheckCircle2, Download, Search, Filter, Loader2, MessageSquare, Send } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { Preloader } from '@/components/Preloader';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { ScrollArea } from '@/components/ui/scroll-area';

import { fetchVideoMetadata } from '@/app/actions/video';

export default function ProjectDetailsPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [audience, setAudience] = useState<AudienceConfig | null>(null);
  const [survey, setSurvey] = useState<SurveyConfig | null>(null);
  
  const [isSimulating, setIsSimulating] = useState(false);
  const [progress, setProgress] = useState(0);
  
  const [searchQuery, setSearchQuery] = useState('');
  const [isDownloading, setIsDownloading] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const [chatHistory, setChatHistory] = useState<{role: 'user'|'assistant', content: string}[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [selectedChatAgent, setSelectedChatAgent] = useState<string>('all');
  const [isChatting, setIsChatting] = useState(false);

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMessage = chatInput;
    setChatInput('');
    setChatHistory(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsChatting(true);

    try {
      const responses = project?.results?.responses || [];
      const agents = audience?.agents || [];
      const response = await chatWithAudience(userMessage, chatHistory, agents, responses, selectedChatAgent, project);
      setChatHistory(prev => [...prev, { role: 'assistant', content: response }]);
    } catch (error) {
      console.error("Chat failed:", error);
      setChatHistory(prev => [...prev, { role: 'assistant', content: "Ошибка связи с агентами." }]);
    } finally {
      setIsChatting(false);
    }
  };

  const downloadPDF = async () => {
    if (!reportRef.current) return;
    setIsDownloading(true);
    try {
      // Create a temporary clone for better rendering or just use the hidden container
      const canvas = await html2canvas(reportRef.current, { 
        scale: 2, 
        useCORS: true,
        backgroundColor: '#ffffff'
      });
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = (canvas.height * pdfWidth) / canvas.width;
      
      let heightLeft = pdfHeight;
      let position = 0;
      
      // Add first page
      pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, pdfHeight);
      heightLeft -= 297; // A4 height in mm
      
      // Add subsequent pages if the content is longer than one page
      while (heightLeft >= 0) {
        position = heightLeft - pdfHeight;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, pdfHeight);
        heightLeft -= 297;
      }
      
      pdf.save(`Agora_Report_${project?.title.replace(/\s+/g, '_')}.pdf`);
    } catch (e) {
      console.error("Failed to generate PDF", e);
      alert("Не удалось сгенерировать PDF отчет");
    } finally {
      setIsDownloading(false);
    }
  };

  useEffect(() => {
    if (project) {
      document.title = `${project.title} | Agora`;
    } else {
      document.title = "О проекте | Agora";
    }
  }, [project]);

  useEffect(() => {
    if (id) {
      loadData();
    }
  }, [id]);

  const loadData = async () => {
    const p = await db.projects.get(id);
    if (p) {
      setProject(p);
      if (p.audienceId) {
        const a = await db.audiences.get(p.audienceId);
        setAudience(a || null);
      }
      if (p.surveyId) {
        const s = await db.surveys.get(p.surveyId);
        setSurvey(s || null);
      }
    }
  };

  const runSimulation = async () => {
    if (!project || !audience || !survey) return;
    
    setIsSimulating(true);
    setProgress(10);
    
    try {
      // Fetch metadata for episodes
      setProgress(20);
      const enrichedEpisodes = await Promise.all(
        project.episodes.map(async (ep) => {
          try {
            const data = await fetchVideoMetadata(ep.url);
            if (data) {
              return { ...ep, metadata: data };
            }
          } catch (e) {}
          return ep;
        })
      );
      
      const enrichedProject = { ...project, episodes: enrichedEpisodes };

      // 1. Simulate Survey
      setProgress(30);
      const responses = await simulateSurvey(audience.agents, enrichedProject, survey);
      
      // 2. Generate Report
      setProgress(70);
      const report = await generateReport(responses, survey);
      
      // 3. Save Results
      setProgress(90);
      const updatedProject = {
        ...project,
        status: 'completed' as const,
        results: { responses, report }
      };
      await db.projects.save(updatedProject);
      setProject(updatedProject);
      
      setProgress(100);
    } catch (error) {
      console.error(error);
      alert('Ошибка при симуляции');
    } finally {
      setIsSimulating(false);
    }
  };

  if (!project) return <div className="p-8 text-center">Загрузка...</div>;

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d'];

  const filteredResponses = project?.results?.responses.filter((resp: any) => {
    if (!searchQuery) return true;
    const agent = audience?.agents.find((a: any) => a.id === resp.agentId);
    if (!agent) return false;
    
    const term = searchQuery.toLowerCase();
    
    // Check demographic info
    if (
      agent.name.toLowerCase().includes(term) ||
      agent.profession.toLowerCase().includes(term) ||
      agent.city.toLowerCase().includes(term)
    ) {
      return true;
    }
    
    // Check responses text
    for (const key in resp.answers) {
      const ans = resp.answers[key];
      if (typeof ans === 'string' && ans.toLowerCase().includes(term)) return true;
      if (Array.isArray(ans) && ans.some(a => typeof a === 'string' && a.toLowerCase().includes(term))) return true;
    }
    
    return false;
  }) || [];

  return (
    <main className="flex-1 container mx-auto max-w-6xl p-4 md:p-6 lg:p-8">
      <div className="flex flex-col md:flex-row items-start md:items-center gap-4 mb-8">
        <Button variant="ghost" size="icon" onClick={() => router.push('/projects')} className="hidden md:flex">
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={() => router.push('/projects')} className="md:hidden">
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h2 className="text-3xl font-bold tracking-tight">{project.title}</h2>
          </div>
          <p className="text-muted-foreground mt-1 md:mt-0">{project.description}</p>
        </div>
        <div className="flex items-center gap-3 w-full md:w-auto">
          {project.status === 'completed' && (
            <Button onClick={downloadPDF} variant="outline" disabled={isDownloading} className="flex-1 md:flex-none">
              {isDownloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
              Скачать отчет (PDF)
            </Button>
          )}
          {project.status !== 'completed' && (
            <Button onClick={runSimulation} disabled={isSimulating || !audience || !survey} className="w-full md:w-auto">
              {isSimulating ? 'Симуляция...' : <><Play className="mr-2 h-4 w-4" /> Запустить исследование</>}
            </Button>
          )}
        </div>
      </div>

      <Preloader 
        isVisible={isSimulating} 
        progress={progress} 
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Film className="h-4 w-4" /> Эпизоды
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{project.episodes.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {project.episodes.map(e => e.title).join(', ')}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Users className="h-4 w-4" /> Аудитория
            </CardTitle>
          </CardHeader>
          <CardContent>
            {audience ? (
              <>
                <div className="text-2xl font-bold">{audience.size} агентов</div>
                <p className="text-xs text-muted-foreground mt-1">{audience.name}</p>
              </>
            ) : (
              <p className="text-sm text-destructive">Не выбрана</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <FileText className="h-4 w-4" /> Анкета
            </CardTitle>
          </CardHeader>
          <CardContent>
            {survey ? (
              <>
                <div className="text-2xl font-bold">{survey.questions.length} вопросов</div>
                <p className="text-xs text-muted-foreground mt-1">{survey.name}</p>
              </>
            ) : (
              <p className="text-sm text-destructive">Не выбрана</p>
            )}
          </CardContent>
        </Card>
      </div>

      {project.status === 'completed' && project.results && (
        <Tabs defaultValue="summary" className="space-y-6">
          <TabsList>
            <TabsTrigger value="summary">Резюме</TabsTrigger>
            <TabsTrigger value="analytics">Аналитика</TabsTrigger>
            <TabsTrigger value="responses">Ответы агентов</TabsTrigger>
            <TabsTrigger value="chat">Чат с аудиторией</TabsTrigger>
          </TabsList>

          <TabsContent value="summary" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Аналитическое резюме</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="prose dark:prose-invert max-w-none space-y-4">
                  {project.results.report.summary?.split('\n').map((paragraph: string, i: number) => (
                    <p key={i}>{paragraph}</p>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {project.results.report.npsScore !== undefined && (
                <Card>
                  <CardHeader>
                    <CardTitle>NPS (Готовность рекомендовать)</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col items-center justify-center py-6">
                    <div className={`text-6xl font-bold ${
                      project.results.report.npsScore > 20 ? 'text-green-500' : 
                      project.results.report.npsScore > 0 ? 'text-yellow-500' : 'text-red-500'
                    }`}>
                      {project.results.report.npsScore}
                    </div>
                  </CardContent>
                </Card>
              )}

              {project.results.report.retentionRate !== undefined && (
                <Card>
                  <CardHeader>
                    <CardTitle>Удержание (Retention)</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col items-center justify-center py-6">
                    <div className="text-6xl font-bold text-primary">
                      {project.results.report.retentionRate}%
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            {project.results.report.insights && (
              <Card>
                <CardHeader>
                  <CardTitle>Ключевые инсайты</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-3">
                    {project.results.report.insights.map((insight: string, i: number) => (
                      <li key={i} className="flex items-start gap-3">
                        <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                        <span>{insight}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="analytics" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {project.results.report.averageRatings && Object.keys(project.results.report.averageRatings).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Средние оценки</CardTitle>
                  </CardHeader>
                  <CardContent className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={
                        Object.entries(project.results.report.averageRatings).map(([id, val]) => {
                          const q = survey?.questions.find(q => q.id === id);
                          return { name: q ? q.text.substring(0, 15) + '...' : id, score: val };
                        })
                      }>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                        <XAxis dataKey="name" tick={{fill: 'currentColor', fontSize: 12}} />
                        <YAxis domain={[0, 10]} tick={{fill: 'currentColor'}} />
                        <Tooltip contentStyle={{backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))'}} />
                        <Bar dataKey="score" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {project.results.report.topEmotions && (
                <Card>
                  <CardHeader>
                    <CardTitle>Эмоциональный профиль</CardTitle>
                  </CardHeader>
                  <CardContent className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={project.results.report.topEmotions}
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#8884d8"
                          dataKey="count"
                          label={({name, percent}) => percent ? `${name} ${(percent * 100).toFixed(0)}%` : name}
                        >
                          {project.results.report.topEmotions.map((entry: any, index: number) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))'}} />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {project.results.report.topValues && (
                <Card className="md:col-span-2">
                  <CardHeader>
                    <CardTitle>Считанные ценности</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {project.results.report.topValues.map((v: any, i: number) => (
                        <Badge key={i} variant="secondary" className="text-sm py-1 px-3">
                          {v.name} ({v.count})
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          <TabsContent value="responses">
            <Card>
              <CardHeader className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <CardTitle>Сырые данные</CardTitle>
                  <CardDescription>Ответы каждого агента на вопросы анкеты ({filteredResponses.length})</CardDescription>
                </div>
                <div className="relative w-full md:w-72">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input 
                    type="search" 
                    placeholder="Поиск по имени, городу, ответам..." 
                    className="pl-8"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-8">
                  {filteredResponses.length === 0 ? (
                    <div className="text-center py-10 text-muted-foreground">
                      Ничего не найдено по вашему запросу.
                    </div>
                  ) : filteredResponses.map((resp: any, i: number) => {
                    const agent = audience?.agents.find(a => a.id === resp.agentId);
                    return (
                      <div key={i} className="border-b pb-6 last:border-0">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4">
                          <div>
                            <h4 className="font-semibold text-lg">{agent?.name || resp.agentId}</h4>
                            <p className="text-sm text-muted-foreground">{agent?.age} лет, {agent?.city}, {agent?.profession}</p>
                          </div>
                          {resp.answers && Object.keys(resp.answers).find((k) => survey?.questions.find(q => q.id === k)?.type === 'nps') && (
                            <Badge variant={resp.answers[Object.keys(resp.answers).find(k => survey?.questions.find(q => q.id === k)?.type === 'nps')!] >= 9 ? 'default' : resp.answers[Object.keys(resp.answers).find(k => survey?.questions.find(q => q.id === k)?.type === 'nps')!] >= 7 ? 'secondary' : 'destructive'} className="mt-2 sm:mt-0 w-max">
                              NPS: {resp.answers[Object.keys(resp.answers).find(k => survey?.questions.find(q => q.id === k)?.type === 'nps')!]}
                            </Badge>
                          )}
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
                          {Object.entries(resp.answers || {}).map(([qId, answer]: [string, any]) => {
                            const q = survey?.questions.find(q => q.id === qId);
                            // Avoid showing NPS twice if we highlighted it
                            if (q?.type === 'nps') return null;
                            return (
                              <div key={qId} className="bg-muted/50 p-3 rounded-md">
                                <span className="text-muted-foreground block mb-1">{q?.text || qId}:</span>
                                <span className="font-medium">
                                  {Array.isArray(answer) ? answer.join(', ') : 
                                   typeof answer === 'boolean' ? (answer ? 'Да' : 'Нет') : 
                                   answer}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="chat">
            <Card className="h-[600px] flex flex-col">
              <CardHeader>
                <CardTitle>Диалог с синтетической аудиторией</CardTitle>
                <CardDescription>Задайте любые вопросы о просмотренных видео или впечатлениях агентов.</CardDescription>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden flex flex-col">
                <div className="flex flex-col h-full">
                  <ScrollArea className="flex-1 p-4 mb-4 border rounded-md min-h-[300px]">
                    {chatHistory.length === 0 && (
                      <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground p-8">
                        <MessageSquare className="h-12 w-12 mb-4 opacity-20" />
                        <p>Начните чат с синтетической аудиторией.</p>
                        <p className="text-sm">Агенты ответят, опираясь на свои профили и глубокую память просмотренных эпизодов проекта &quot;{project.title}&quot;.</p>
                      </div>
                    )}
                    <div className="space-y-4">
                      {chatHistory.map((msg, i) => (
                        <div key={i} className={`flex gap-3 max-w-[80%] ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}>
                          {msg.role === 'assistant' && (
                            <Avatar className="h-8 w-8">
                              <AvatarFallback><Users className="h-4 w-4" /></AvatarFallback>
                            </Avatar>
                          )}
                          <div className={`p-3 rounded-lg ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                          </div>
                          {msg.role === 'user' && (
                            <Avatar className="h-8 w-8">
                              <AvatarFallback>Вы</AvatarFallback>
                            </Avatar>
                          )}
                        </div>
                      ))}
                      {isChatting && (
                        <div className="flex gap-3 max-w-[80%] mr-auto">
                          <Avatar className="h-8 w-8">
                            <AvatarFallback><Loader2 className="h-4 w-4 animate-spin" /></AvatarFallback>
                          </Avatar>
                          <div className="p-3 rounded-lg bg-muted">
                            <p className="text-sm text-muted-foreground">Агенты печатают...</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                  
                  <form onSubmit={handleChatSubmit} className="flex flex-col sm:flex-row gap-2">
                    <select 
                      className="flex h-10 w-full sm:w-[250px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
                      value={selectedChatAgent}
                      onChange={(e) => setSelectedChatAgent(e.target.value)}
                      disabled={isChatting}
                    >
                      <option value="all">Все агенты (Коллективное)</option>
                      {audience?.agents.map(a => (
                        <option key={a.id} value={a.id}>{a.name} ({a.age}, {a.profession})</option>
                      ))}
                    </select>
                    <div className="flex flex-1 gap-2">
                      <Input 
                        placeholder="Спросите их о сюжете, таймкодах или мнениях..." 
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        disabled={isChatting}
                        className="flex-1"
                      />
                      <Button type="submit" disabled={isChatting || !chatInput.trim()}>
                        <Send className="h-4 w-4" />
                      </Button>
                    </div>
                  </form>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}

      {/* Hidden Container for PDF Rendering */}
      {project.status === 'completed' && project.results && (
        <div style={{ position: 'absolute', left: '-9999px', top: '-9999px' }}>
          <div ref={reportRef} style={{ width: '1000px', padding: '60px', background: 'white', color: 'black', fontFamily: 'sans-serif' }}>
            <h1 style={{ fontSize: '32px', fontWeight: 'bold', borderBottom: '2px solid #22c55e', paddingBottom: '10px', marginBottom: '20px' }}>Консолидированный отчет: {project.title}</h1>
            <p style={{ fontSize: '18px', color: '#666', marginBottom: '40px' }}>Методология исследования: Синтетическая аудитория</p>
            
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '15px' }}>1. Аналитическое резюме</h2>
            <div style={{ fontSize: '16px', lineHeight: '1.6', marginBottom: '40px', color: '#111' }}>
              {project.results.report.summary?.split('\n').map((paragraph: string, i: number) => (
                <p key={i} style={{ marginBottom: '12px' }}>{paragraph}</p>
              ))}
            </div>

            <div style={{ display: 'flex', gap: '20px', marginBottom: '40px' }}>
              {project.results.report.npsScore !== undefined && (
                <div style={{ flex: 1, padding: '24px', background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <h4 style={{ fontWeight: 'bold', fontSize: '16px', color: '#64748b', marginBottom: '10px' }}>Индекс NPS (Готовность рекомендовать)</h4>
                  <div style={{ fontSize: '48px', fontWeight: 'bold', color: project.results.report.npsScore > 20 ? '#22c55e' : project.results.report.npsScore > 0 ? '#eab308' : '#ef4444' }}>
                    {project.results.report.npsScore}
                  </div>
                </div>
              )}
              {project.results.report.retentionRate !== undefined && (
                <div style={{ flex: 1, padding: '24px', background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                  <h4 style={{ fontWeight: 'bold', fontSize: '16px', color: '#64748b', marginBottom: '10px' }}>Удержание (Retention Rate)</h4>
                  <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#3b82f6' }}>
                    {project.results.report.retentionRate}%
                  </div>
                </div>
              )}
            </div>

            {project.results.report.insights && project.results.report.insights.length > 0 && (
              <div style={{ marginBottom: '40px' }}>
                <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '15px' }}>2. Ключевые выводы</h2>
                <ul style={{ paddingLeft: '20px', fontSize: '16px', lineHeight: '1.6' }}>
                  {project.results.report.insights.map((insight: string, i: number) => (
                    <li key={i} style={{ marginBottom: '10px' }}>{insight}</li>
                  ))}
                </ul>
              </div>
            )}

            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '20px' }}>3. Детальная аналитика</h2>
            {project.results.report.averageRatings && Object.keys(project.results.report.averageRatings).length > 0 && (
              <div style={{ marginBottom: '30px' }}>
                <h3 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '10px' }}>Средние оценки параметров (из 10)</h3>
                <div style={{ padding: '20px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={Object.entries(project.results.report.averageRatings).map(([id, val]) => ({ name: survey?.questions.find(q => q.id === id)?.text.substring(0, 20) + '...', score: val }))}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.5} />
                      <XAxis dataKey="name" tick={{fontSize: 12, fill: '#333'}} />
                      <YAxis domain={[0, 10]} tick={{fill: '#333'}} />
                      <Bar dataKey="score" fill="#3b82f6" isAnimationActive={false} label={{ position: 'top', fill: '#333' }} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {project.results.report.topValues && project.results.report.topValues.length > 0 && (
              <div style={{ marginBottom: '30px' }}>
                <h3 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '10px' }}>Топ считанных ценностей</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                  {project.results.report.topValues.map((v: any, i: number) => (
                    <span key={i} style={{ padding: '8px 16px', background: '#e2e8f0', borderRadius: '20px', fontSize: '14px', fontWeight: '500' }}>
                      {v.name} ({v.count})
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginTop: '60px', paddingTop: '20px', borderTop: '1px solid #e2e8f0', fontSize: '12px', color: '#94a3b8', textAlign: 'center' }}>
              Отчет подготовлен автоматически системой Agora OS • Синтетическая выборка: {audience?.size} ИИ-агентов
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
