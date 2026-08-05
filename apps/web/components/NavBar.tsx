"use client"

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';

const links = [
  { href: '/', label: 'Быстрый тест' },
  { href: '/projects', label: 'Проекты' },
  { href: '/audience', label: 'Аудитории' },
  { href: '/surveys', label: 'Анкеты' },
];

function NavLinks({ mobile = false, onNavigate }: { mobile?: boolean, onNavigate?: () => void }) {
  const pathname = usePathname();
  
  return (
    <>
      {links.map(link => (
        <Link
          key={link.href}
          href={link.href}
          onClick={() => {
            if (mobile && onNavigate) onNavigate();
          }}
          className={cn(
            "text-sm font-medium transition-colors hover:text-primary",
            pathname === link.href ? "text-primary" : "text-muted-foreground",
            mobile ? "block py-4 text-xl border-b border-border/50" : ""
          )}
        >
          {link.label}
        </Link>
      ))}
    </>
  );
}

export function NavBar() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <header className="border-b border-border bg-card px-4 md:px-6 py-4 sticky top-0 z-50">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary rounded-md flex items-center justify-center text-primary-foreground font-bold">A</div>
            <h1 className="text-xl font-bold tracking-tight">Agora</h1>
          </Link>
          <nav className="hidden md:flex items-center gap-4 ml-6">
            <NavLinks />
          </nav>
        </div>
        
        <div className="md:hidden">
          <Button variant="ghost" size="icon" onClick={() => setIsOpen(!isOpen)}>
            {isOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </Button>
        </div>
      </div>

      {/* Mobile Menu Overlay */}
      {isOpen && (
        <div className="md:hidden absolute top-full left-0 right-0 bg-background border-b border-border shadow-lg p-4 flex flex-col">
          <NavLinks mobile onNavigate={() => setIsOpen(false)} />
        </div>
      )}
    </header>
  );
}
