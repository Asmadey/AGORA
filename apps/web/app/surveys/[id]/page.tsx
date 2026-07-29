"use client"

import React, { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { db, SurveyConfig, SurveyQuestion, QuestionType } from '@/lib/db';
import { v4 as uuidv4 } from 'uuid';
import { Save, Plus, Trash2, ArrowLeft, GripVertical } from 'lucide-react';

export default function SurveyBuilderPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [survey, setSurvey] = useState<SurveyConfig | null>(null);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (survey) {
      document.title = `${survey.name} | Agora`;
    } else {
      document.title = "Редактирование анкеты | Agora";
    }
  }, [survey]);

  useEffect(() => {
    if (id) {
      loadSurvey();
    }
  }, [id]);

  const loadSurvey = async () => {
    const data = await db.surveys.get(id);
    if (data) {
      setSurvey(data);
    } else {
      // Create new if not found
      setSurvey({
        id,
        name: 'Новая анкета',
        questions: [],
        createdAt: Date.now()
      });
    }
  };

  const performSave = async (currentSurvey: SurveyConfig, isManual = false) => {
    setIsSaving(true);
    try {
      await db.surveys.save(currentSurvey);
      setLastSaved(new Date());
    } catch (error) {
      console.error("Failed to save survey:", error);
      if (isManual) {
        alert("Ошибка при сохранении анкеты. Пожалуйста, проверьте подключение к базе данных.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  // Auto-save every 60 seconds
  useEffect(() => {
    if (!survey) return;
    const interval = setInterval(() => {
      performSave(survey);
    }, 60000);
    return () => clearInterval(interval);
  }, [survey]);

  // Auto-save on changes (debounced)
  useEffect(() => {
    if (!survey) return;
    const timeout = setTimeout(() => {
      performSave(survey);
    }, 3000);
    return () => clearTimeout(timeout);
  }, [survey]);

  const addQuestion = (type: QuestionType) => {
    if (!survey) return;
    const newQuestion: SurveyQuestion = {
      id: uuidv4(),
      type,
      text: 'Новый вопрос',
      ...(type === 'rating' || type === 'nps' ? { scale: 10 } : {}),
      ...(type === 'emotions' || type === 'values' ? { max: 3 } : {}),
      ...(type === 'matrix' || type === 'slogan' ? { options: ['Вариант 1'] } : {})
    };
    setSurvey({ ...survey, questions: [...survey.questions, newQuestion] });
  };

  const updateQuestion = (qId: string, updates: Partial<SurveyQuestion>) => {
    if (!survey) return;
    setSurvey({
      ...survey,
      questions: survey.questions.map(q => q.id === qId ? { ...q, ...updates } : q)
    });
  };

  const removeQuestion = (qId: string) => {
    if (!survey) return;
    setSurvey({
      ...survey,
      questions: survey.questions.filter(q => q.id !== qId)
    });
  };

  const handleSave = async () => {
    if (!survey) return;
    await performSave(survey, true);
    router.push('/surveys');
  };

  if (!survey) return <div className="p-8 text-center">Загрузка...</div>;

  return (
    <main className="flex-1 container mx-auto max-w-4xl p-4 md:p-6 lg:p-8">
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="icon" onClick={() => router.push('/surveys')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="flex-1">
          <h2 className="text-3xl font-bold tracking-tight">Конструктор анкеты</h2>
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
            <CardTitle>Название анкеты</CardTitle>
          </CardHeader>
          <CardContent>
            <Input 
              value={survey.name} 
              onChange={e => setSurvey({ ...survey, name: e.target.value })} 
              className="text-lg font-medium"
            />
          </CardContent>
        </Card>

        <div className="space-y-4">
          <h3 className="text-xl font-semibold">Вопросы</h3>
          {survey.questions.map((q, index) => (
            <Card key={q.id} className="relative group">
              <div className="absolute left-2 top-1/2 -translate-y-1/2 cursor-grab opacity-0 group-hover:opacity-50">
                <GripVertical className="h-5 w-5" />
              </div>
              <CardContent className="p-6 pl-10 flex gap-4 items-start">
                <div className="flex-1 space-y-4">
                  <div className="flex items-center gap-4">
                    <span className="bg-muted text-muted-foreground px-2 py-1 rounded text-xs font-medium uppercase">
                      {q.type}
                    </span>
                    <Input 
                      value={q.text} 
                      onChange={e => updateQuestion(q.id, { text: e.target.value })} 
                      className="flex-1 font-medium"
                    />
                  </div>
                  
                  {/* Specific fields based on type */}
                  {(q.type === 'rating' || q.type === 'nps') && (
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">Шкала до:</span>
                      <Input 
                        type="number" 
                        value={q.scale} 
                        onChange={e => updateQuestion(q.id, { scale: parseInt(e.target.value) || 10 })} 
                        className="w-20"
                      />
                    </div>
                  )}

                  {(q.type === 'emotions' || q.type === 'values') && (
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">Макс. выборов:</span>
                      <Input 
                        type="number" 
                        value={q.max} 
                        onChange={e => updateQuestion(q.id, { max: parseInt(e.target.value) || 3 })} 
                        className="w-20"
                      />
                    </div>
                  )}

                  {(q.type === 'matrix' || q.type === 'slogan') && (
                    <div className="space-y-2">
                      <span className="text-sm text-muted-foreground">Варианты (через запятую):</span>
                      <Input 
                        value={q.options?.join(', ') || ''} 
                        onChange={e => updateQuestion(q.id, { options: e.target.value.split(',').map(s => s.trim()) })} 
                      />
                    </div>
                  )}
                </div>
                <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive" onClick={() => removeQuestion(q.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="border-dashed">
          <CardContent className="p-6 flex flex-wrap gap-2 justify-center">
            <Button variant="secondary" onClick={() => addQuestion('rating')}><Plus className="mr-2 h-4 w-4" /> Шкала оценки</Button>
            <Button variant="secondary" onClick={() => addQuestion('emotions')}><Plus className="mr-2 h-4 w-4" /> Эмоции</Button>
            <Button variant="secondary" onClick={() => addQuestion('values')}><Plus className="mr-2 h-4 w-4" /> Ценности</Button>
            <Button variant="secondary" onClick={() => addQuestion('nps')}><Plus className="mr-2 h-4 w-4" /> NPS</Button>
            <Button variant="secondary" onClick={() => addQuestion('open')}><Plus className="mr-2 h-4 w-4" /> Открытый вопрос</Button>
            <Button variant="secondary" onClick={() => addQuestion('matrix')}><Plus className="mr-2 h-4 w-4" /> Матрица тем</Button>
            <Button variant="secondary" onClick={() => addQuestion('slogan')}><Plus className="mr-2 h-4 w-4" /> Слоган-тест</Button>
            <Button variant="secondary" onClick={() => addQuestion('retention')}><Plus className="mr-2 h-4 w-4" /> Удержание (Retention)</Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
