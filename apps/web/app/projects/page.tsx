"use client"

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { db, Project } from '@/lib/db';
import { Plus, Film, Calendar, Trash2 } from 'lucide-react';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectToDelete, setProjectToDelete] = useState<string | null>(null);

  const loadProjects = async () => {
    const data = await db.projects.getAll();
    setProjects(data.sort((a, b) => b.createdAt - a.createdAt));
  };

  useEffect(() => {
    document.title = "Проекты | Agora";
    loadProjects();
  }, []);

  const deleteProject = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    setProjectToDelete(id);
  };

  const confirmDelete = async () => {
    if (projectToDelete) {
      await db.projects.delete(projectToDelete);
      setProjectToDelete(null);
      loadProjects();
    }
  };

  return (
    <main className="flex-1 container mx-auto max-w-6xl p-4 md:p-6 lg:p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Проекты</h2>
          <p className="text-muted-foreground">Управление исследованиями видеоконтента</p>
        </div>
        <Link href="/projects/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" /> Новый проект
          </Button>
        </Link>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-20 border rounded-lg border-dashed">
          <Film className="mx-auto h-12 w-12 text-muted-foreground mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Нет проектов</h3>
          <p className="text-muted-foreground mt-1 mb-4">Создайте свой первый проект для исследования.</p>
          <Link href="/projects/new">
            <Button variant="outline">Создать проект</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map(project => (
            <Link key={project.id} href={`/projects/${project.id}`}>
              <Card className="h-full hover:border-primary transition-colors cursor-pointer flex flex-col">
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <CardTitle className="line-clamp-1">{project.title}</CardTitle>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive -mt-2 -mr-2" onClick={(e) => deleteProject(project.id, e)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <CardDescription className="line-clamp-2">{project.description || 'Нет описания'}</CardDescription>
                </CardHeader>
                <CardContent className="mt-auto">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Film className="h-4 w-4" /> {project.episodes.length} эпизодов
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar className="h-4 w-4" /> {new Date(project.createdAt).toLocaleDateString('ru-RU')}
                    </span>
                  </div>
                  <div className="mt-4 pt-4 border-t flex justify-between items-center">
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      project.status === 'completed' ? 'bg-green-500/20 text-green-500' :
                      project.status === 'in_progress' ? 'bg-blue-500/20 text-blue-500' :
                      'bg-muted text-muted-foreground'
                    }`}>
                      {project.status === 'completed' ? 'Завершено' :
                       project.status === 'in_progress' ? 'В процессе' : 'Черновик'}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={!!projectToDelete} onOpenChange={(open) => !open && setProjectToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Удалить проект?</DialogTitle>
            <DialogDescription>
              Вы уверены, что хотите удалить этот проект? Это действие нельзя отменить, и все связанные данные будут потеряны.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProjectToDelete(null)}>Отмена</Button>
            <Button variant="destructive" onClick={confirmDelete}>Удалить</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
