"use client"

import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { db, AudienceConfig } from '@/lib/db';
import { Users, Plus, Trash2, Settings, Loader2 } from 'lucide-react';
import { generateAudience } from '@/lib/ai';
import { AGE_GROUPS, GENDERS, GEOS } from '@/lib/audience';
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
    setIsBuilderOpen(true);
  };

  /**
   * Генерация аудитории.
   *
   * Идёт тем же путём, что шаг визарда: POST /api/audience → заземлённый на
   * корпус генератор → набор сохраняется в базе арендатора. Раньше страница
   * слала вокабуляр прототипа (ageGroup / incomeLevel / extraRequirements) и
   * получала 400 на каждую попытку — контракт маршрута переписали в #9, а
   * страницу забыли.
   *
   * Критерии «доход» и «свободные требования» отброшены сознательно: в корпусе
   * таких полей нет, заземлить их нечем, а молча отправлять незаземлённый
   * критерий в генерацию — ровно тот подлог, от которого уходила задача #9.
   */
  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const result = await generateAudience({
        size: parseInt(bSize, 10) || 20,
        // «Все» означает весь диапазон, а не пустой список: пустой контракт
        // отвергает как незаполненный критерий.
        ageGroups: bAge !== 'all' ? [bAge] : [...AGE_GROUPS],
        geos: bLocation !== 'all' ? [bLocation] : [...GEOS],
        genders: bGender !== 'all' ? [bGender] : [...GENDERS],
      });

      const newAudience: AudienceConfig = {
        id: result.personaSetId,
        name: bName || `Синтетическая аудитория (${new Date().toLocaleDateString()})`,
        size: result.size,
        agents: result.personas as AudienceConfig['agents'],
        createdAt: Date.now()
      };

      await db.audiences.save(newAudience);
      await loadAudiences();
      setIsBuilderOpen(false);
    } catch (error) {
      console.error(error);
      alert(`Не удалось создать аудиторию: ${(error as Error).message}`);
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
                {/* Группы берутся из контракта, а не переписываются здесь.
                    Прежний список расходился с корпусом сразу в трёх местах:
                    45-54 и 55+ против 45-59 и 60+, и не было 14-17. Выбор такой
                    группы отправлял в генератор значение, которого корпус не
                    знает, — то есть заведомо отвергаемый запрос. */}
                <option value="all">Любой (репрезентативно)</option>
                {AGE_GROUPS.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
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
                {GENDERS.map((g) => (
                  <option key={g} value={g}>
                    {g === "муж" ? "Только мужчины" : "Только женщины"}
                  </option>
                ))}
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
                {GEOS.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            {/* Здесь были «Доход» и «Доп. условия». Убраны, а не отключены:
                в корпусе таких полей нет ни у одной записи, заземлить их
                нечем. Поле, которое пользователь заполняет, а генератор
                игнорирует, хуже отсутствующего — оно обещает влияние на
                результат и создаёт доверие к персонам, которого те не
                заслуживают. */}
            <p className="col-span-4 rounded-md border border-border/60 bg-secondary/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
              Персоны собираются по реальным долям исследовательского корпуса.
              Критерии, которых в корпусе нет — доход, профессия, свободные
              требования — не предлагаются: заземлить их нечем.
            </p>
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

