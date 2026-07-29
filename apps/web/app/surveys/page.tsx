"use client"

import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { db, SurveyConfig } from '@/lib/db';
import { FileText, Plus, Trash2, Edit } from 'lucide-react';

export default function SurveysPage() {
  const [surveys, setSurveys] = useState<SurveyConfig[]>([]);

  const loadSurveys = async () => {
    const data = await db.surveys.getAll();
    setSurveys(data.sort((a, b) => b.createdAt - a.createdAt));
  };

  useEffect(() => {
    document.title = "Анкеты | Agora";
    loadSurveys();
  }, []);

  const handleCreateDefault = async () => {
    const newId = crypto.randomUUID();
    const newSurvey: SurveyConfig = {
      id: newId,
      name: `Стандартная анкета Агора`,
      questions: [
        { id: crypto.randomUUID(), type: 'rating', text: 'Общее впечатление', scale: 10 },
        { id: crypto.randomUUID(), type: 'rating', text: 'Оценка сюжета', scale: 10 },
        { id: crypto.randomUUID(), type: 'rating', text: 'Оценка игры актеров', scale: 10 },
        { id: crypto.randomUUID(), type: 'rating', text: 'Оценка музыки', scale: 10 },
        { id: crypto.randomUUID(), type: 'rating', text: 'Оценка качества съемок', scale: 10 },
        { id: crypto.randomUUID(), type: 'emotions', text: 'Испытанные эмоции', max: 3 },
        { id: crypto.randomUUID(), type: 'values', text: 'Считанные ценности', max: 3 },
        { id: crypto.randomUUID(), type: 'nps', text: 'Готовность рекомендовать (NPS)', scale: 10 },
        { id: crypto.randomUUID(), type: 'open', text: 'Развернутый комментарий' }
      ],
      createdAt: Date.now()
    };
    
    await db.surveys.save(newSurvey);
    window.location.href = `/surveys/${newId}`;
  };

  const handleCreateEmpty = () => {
    window.location.href = `/surveys/${crypto.randomUUID()}`;
  };

  const deleteSurvey = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    if (confirm('Удалить анкету?')) {
      await db.surveys.delete(id);
      loadSurveys();
    }
  };

  return (
    <main className="flex-1 container mx-auto max-w-6xl p-4 md:p-6 lg:p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Анкеты</h2>
          <p className="text-muted-foreground">Конструктор опросников для исследований</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleCreateDefault}>
            Стандартная анкета
          </Button>
          <Button onClick={handleCreateEmpty}>
            <Plus className="mr-2 h-4 w-4" /> Создать анкету
          </Button>
        </div>
      </div>

      {surveys.length === 0 ? (
        <div className="text-center py-20 border rounded-lg border-dashed">
          <FileText className="mx-auto h-12 w-12 text-muted-foreground mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Нет анкет</h3>
          <p className="text-muted-foreground mt-1 mb-4">Создайте первую анкету для тестирования контента.</p>
          <Button variant="outline" onClick={handleCreateDefault}>
            Создать стандартную анкету
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {surveys.map(survey => (
            <Card key={survey.id} className="h-full flex flex-col">
              <CardHeader>
                <div className="flex justify-between items-start">
                  <CardTitle className="line-clamp-1 text-lg">{survey.name}</CardTitle>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive -mt-2 -mr-2" onClick={(e) => deleteSurvey(survey.id, e)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <CardDescription>{new Date(survey.createdAt).toLocaleString('ru-RU')}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <FileText className="h-4 w-4" /> {survey.questions.length} вопросов
                  </span>
                  <Button variant="secondary" size="sm" onClick={() => window.location.href = `/surveys/${survey.id}`}>
                    <Edit className="mr-2 h-4 w-4" /> Редактировать
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </main>
  );
}
