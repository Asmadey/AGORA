"use client"

import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { db, AudienceConfig } from '@/lib/db';
import { Users, Plus, Trash2, Settings, Loader2 } from 'lucide-react';
import { generateAudience, fetchNewsContext } from '@/lib/ai';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from '@/components/ui/input';

export default function AudiencePage() {
  const [audiences, setAudiences] = useState<AudienceConfig[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isBuilderOpen, setIsBuilderOpen] = useState(false);

  // Builder form state
  const [bName, setBName] = useState('');
  const [bSize, setBSize] = useState('20');
  const [bAge, setBAge] = useState('all');
  const [bGender, setBGender] = useState('all');
  const [bLocation, setBLocation] = useState('all');
  const [bIncome, setBIncome] = useState('all');
  const [bExtra, setBExtra] = useState('');

  const loadAudiences = async () => {
    const data = await db.audiences.getAll();
    setAudiences(data.sort((a, b) => b.createdAt - a.createdAt));
  };

  useEffect(() => {
    document.title = "Аудитории | Agora";
    loadAudiences();
  }, []);

  const handleOpenBuilder = () => {
    setBName(`Синтетическая аудитория (${new Date().toLocaleDateString()})`);
    setBSize('20');
    setBAge('all');
    setBGender('all');
    setBLocation('all');
    setBIncome('all');
    setBExtra('');
    setIsBuilderOpen(true);
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const context = await fetchNewsContext();
      
      const options: Record<string, any> = {};
      if (bAge !== 'all') options.ageGroup = bAge;
      if (bGender !== 'all') options.gender = bGender;
      if (bLocation !== 'all') options.locationType = bLocation;
      if (bIncome !== 'all') options.incomeLevel = bIncome;
      if (bExtra.trim()) options.extraRequirements = bExtra.trim();

      const agents = await generateAudience(parseInt(bSize, 10) || 20, context, options);
      
      const newAudience: AudienceConfig = {
        id: crypto.randomUUID(),
        name: bName || `Синтетическая аудитория (${new Date().toLocaleDateString()})`,
        size: agents.length,
        agents,
        createdAt: Date.now()
      };
      
      await db.audiences.save(newAudience);
      await loadAudiences();
      setIsBuilderOpen(false);
    } catch (error) {
      console.error(error);
      alert('Ошибка при генерации аудитории');
    } finally {
      setIsGenerating(false);
    }
  };

  const deleteAudience = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    if (confirm('Удалить аудиторию?')) {
      await db.audiences.delete(id);
      loadAudiences();
    }
  };

  return (
    <main className="flex-1 container mx-auto max-w-6xl p-4 md:p-6 lg:p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Аудитории</h2>
          <p className="text-muted-foreground">Управление синтетическими респондентами</p>
        </div>
        <Button onClick={handleOpenBuilder} disabled={isGenerating}>
          {isGenerating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Генерация...</> : <><Plus className="mr-2 h-4 w-4" /> Конструктор аудитории</>}
        </Button>
      </div>

      {audiences.length === 0 ? (
        <div className="text-center py-20 border rounded-lg border-dashed">
          <Users className="mx-auto h-12 w-12 text-muted-foreground mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Нет аудиторий</h3>
          <p className="text-muted-foreground mt-1 mb-4">Сгенерируйте первую синтетическую аудиторию.</p>
          <Button variant="outline" onClick={handleOpenBuilder} disabled={isGenerating}>
            Открыть конструктор
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {audiences.map(aud => (
            <Card key={aud.id} className="h-full flex flex-col">
              <CardHeader>
                <div className="flex justify-between items-start">
                  <CardTitle className="line-clamp-1 text-lg">{aud.name}</CardTitle>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive -mt-2 -mr-2" onClick={(e) => deleteAudience(aud.id, e)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <CardDescription>{new Date(aud.createdAt).toLocaleString('ru-RU')}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Users className="h-4 w-4" /> {aud.size} агентов
                  </span>
                  <Button variant="secondary" size="sm">
                    <Settings className="mr-2 h-4 w-4" /> Настроить
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={isBuilderOpen} onOpenChange={(open) => !isGenerating && setIsBuilderOpen(open)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Продвинутый конструктор аудитории</DialogTitle>
            <DialogDescription>
              Настройте параметры для генерации специфической выборки искусственных респондентов.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="name" className="text-right text-sm font-medium">
                Название
              </label>
              <Input
                id="name"
                value={bName}
                onChange={(e) => setBName(e.target.value)}
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="size" className="text-right text-sm font-medium">
                Размер
              </label>
              <Input
                id="size"
                type="number"
                min="1"
                max="100"
                value={bSize}
                onChange={(e) => setBSize(e.target.value)}
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="age" className="text-right text-sm font-medium">
                Возраст
              </label>
              <select
                id="age"
                value={bAge}
                onChange={(e) => setBAge(e.target.value)}
                className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              >
                <option value="all">Любой (репрезентативно)</option>
                <option value="18-24">Молодежь (18-24)</option>
                <option value="25-34">Молодые взрослые (25-34)</option>
                <option value="35-44">Взрослые (35-44)</option>
                <option value="45-54">Зрелые (45-54)</option>
                <option value="55+">Старшее поколение (55+)</option>
              </select>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="gender" className="text-right text-sm font-medium">
                Пол
              </label>
              <select
                id="gender"
                value={bGender}
                onChange={(e) => setBGender(e.target.value)}
                className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              >
                <option value="all">Смешанный</option>
                <option value="male">Только мужчины</option>
                <option value="female">Только женщины</option>
              </select>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="location" className="text-right text-sm font-medium">
                Локация
              </label>
              <select
                id="location"
                value={bLocation}
                onChange={(e) => setBLocation(e.target.value)}
                className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              >
                <option value="all">Вся Россия</option>
                <option value="mega">Только миллионники (Москва, СПб и др.)</option>
                <option value="regions">Регионы и малые города</option>
              </select>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <label htmlFor="income" className="text-right text-sm font-medium">
                Доход
              </label>
              <select
                id="income"
                value={bIncome}
                onChange={(e) => setBIncome(e.target.value)}
                className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              >
                <option value="all">Разный</option>
                <option value="low">Низкий</option>
                <option value="medium">Средний</option>
                <option value="high">Высокий</option>
              </select>
            </div>
            <div className="grid grid-cols-4 flex-col gap-4">
              <label htmlFor="extra" className="text-right text-sm font-medium pt-2">
                Доп. условия
              </label>
              <textarea
                id="extra"
                placeholder="Специфические профессии, хобби, взгляды..."
                value={bExtra}
                onChange={(e) => setBExtra(e.target.value)}
                className="col-span-3 min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsBuilderOpen(false)} disabled={isGenerating}>Отмена</Button>
            <Button onClick={handleGenerate} disabled={isGenerating}>
              {isGenerating ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Генерация ({bSize})...</> : 'Создать'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

