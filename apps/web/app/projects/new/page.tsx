"use client"

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { db, Project, AudienceConfig, SurveyConfig } from '@/lib/db';
import { v4 as uuidv4 } from 'uuid';
import { Plus, Trash2, Save } from 'lucide-react';

export default function NewProjectPage() {
  const router = useRouter();
  const [projectId] = useState(() => uuidv4());
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [episodes, setEpisodes] = useState([{ id: uuidv4(), title: 'Серия 1', url: '' }]);
  
  const [audiences, setAudiences] = useState<AudienceConfig[]>([]);
  const [surveys, setSurveys] = useState<SurveyConfig[]>([]);
  
  const [selectedAudience, setSelectedAudience] = useState<string>('');
  const [selectedSurvey, setSelectedSurvey] = useState<string>('');

  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    document.title = "Новый проект | Agora";
    loadData();
  }, []);

  const loadData = async () => {
    const auds = await db.audiences.getAll();
    const survs = await db.surveys.getAll();
    setAudiences(auds);
    setSurveys(survs);
    if (auds.length > 0) setSelectedAudience(auds[0].id);
    if (survs.length > 0) setSelectedSurvey(survs[0].id);
  };

  const performSave = async (isManual = false) => {
    if (!title.trim() && !isManual) return; // Skip auto-save if no title

    setIsSaving(true);
    try {
      const newProject: Project = {
        id: projectId,
        title: title || 'Черновик проекта',
        description,
        episodes: episodes.filter(ep => ep.url.trim() !== ''),
        audienceId: selectedAudience,
        surveyId: selectedSurvey,
        status: 'draft',
        createdAt: Date.now()
      };

      await db.projects.save(newProject);
      setLastSaved(new Date());
    } catch (error) {
      console.error("Failed to save project:", error);
      if (isManual) {
        alert("Ошибка при сохранении проекта. Пожалуйста, проверьте подключение к базе данных.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  // Auto-save every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      performSave();
    }, 60000);
    return () => clearInterval(interval);
  }, [title, description, episodes, selectedAudience, selectedSurvey]);

  // Auto-save on significant changes (debounced)
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (title.trim()) performSave();
    }, 3000);
    return () => clearTimeout(timeout);
  }, [title, description, episodes, selectedAudience, selectedSurvey]);

  const addEpisode = () => {
    setEpisodes([...episodes, { id: uuidv4(), title: `Серия ${episodes.length + 1}`, url: '' }]);
  };

  const removeEpisode = (id: string) => {
    if (episodes.length > 1) {
      setEpisodes(episodes.filter(ep => ep.id !== id));
    }
  };

  const updateEpisode = (id: string, field: 'title' | 'url', value: string) => {
    setEpisodes(episodes.map(ep => ep.id === id ? { ...ep, [field]: value } : ep));
  };

  const handleSave = async () => {
    if (!title.trim()) {
      alert('Введите название проекта');
      return;
    }
    await performSave(true);
    router.push('/projects');
  };

  return (
    <main className="flex-1 container mx-auto max-w-4xl p-4 md:p-6 lg:p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Новый проект</h2>
          <p className="text-muted-foreground">Создание исследования видеоконтента</p>
        </div>
        <div className="flex items-center gap-4">
          {lastSaved && (
            <span className="text-sm text-muted-foreground">
              {isSaving ? 'Сохранение...' : `Сохранено в ${lastSaved.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`}
            </span>
          )}
          <Button onClick={handleSave} disabled={isSaving}>
            <Save className="mr-2 h-4 w-4" /> Сохранить и выйти
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Основная информация</CardTitle>
            <CardDescription>Название и описание тестируемого контента</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Название проекта</label>
              <Input 
                placeholder="Например: Константинополь (1 сезон)" 
                value={title} 
                onChange={e => setTitle(e.target.value)} 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Описание</label>
              <textarea 
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="Краткое описание сюжета и жанра"
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Настройки исследования</CardTitle>
            <CardDescription>Выберите аудиторию и анкету для тестирования</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Синтетическая аудитория</label>
                <select 
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={selectedAudience}
                  onChange={e => setSelectedAudience(e.target.value)}
                >
                  <option value="" disabled>Выберите аудиторию...</option>
                  {audiences.map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.size} агентов)</option>
                  ))}
                </select>
                {audiences.length === 0 && <p className="text-xs text-destructive">Сначала создайте аудиторию в разделе &quot;Аудитории&quot;</p>}
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Анкета</label>
                <select 
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={selectedSurvey}
                  onChange={e => setSelectedSurvey(e.target.value)}
                >
                  <option value="" disabled>Выберите анкету...</option>
                  {surveys.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({s.questions.length} вопросов)</option>
                  ))}
                </select>
                {surveys.length === 0 && <p className="text-xs text-destructive">Сначала создайте анкету в разделе &quot;Анкеты&quot;</p>}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Эпизоды</CardTitle>
              <CardDescription>Добавьте ссылки на видео (Rutube, YouTube, и т.д.)</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={addEpisode}>
              <Plus className="mr-2 h-4 w-4" /> Добавить серию
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {episodes.map((ep, index) => (
              <div key={ep.id} className="flex items-start gap-4 p-4 border rounded-lg bg-muted/50">
                <div className="flex-1 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2 md:col-span-1">
                      <label className="text-xs font-medium text-muted-foreground">Название</label>
                      <Input 
                        value={ep.title} 
                        onChange={e => updateEpisode(ep.id, 'title', e.target.value)} 
                        placeholder="Серия 1"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <label className="text-xs font-medium text-muted-foreground">Ссылка на видео (Rutube)</label>
                      <Input 
                        value={ep.url} 
                        onChange={e => updateEpisode(ep.id, 'url', e.target.value)} 
                        placeholder="https://rutube.ru/video/..."
                      />
                    </div>
                  </div>
                </div>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="mt-6 text-muted-foreground hover:text-destructive"
                  onClick={() => removeEpisode(ep.id)}
                  disabled={episodes.length === 1}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
