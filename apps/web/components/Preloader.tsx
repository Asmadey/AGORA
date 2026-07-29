"use client"

import React, { useState, useEffect } from 'react';

const SIMCITY_MESSAGES = [
  "Reticulating splines...",
  "Generating synthetic citizens...",
  "Calculating emotional vectors...",
  "Simulating existential crises...",
  "Connecting to the noosphere...",
  "Calibrating demographic matrices...",
  "Synthesizing cultural context...",
  "Loading neural pathways...",
  "Adjusting cognitive dissonance parameters...",
  "Polishing pixels...",
  "Recruiting respondents in Saratov...",
  "Analyzing cognitive dissonance...",
  "Loading Kinopoisk profiles...",
  "Merging data into a single matrix..."
];

interface PreloaderProps {
  isVisible: boolean;
  progress?: number;
  message?: string;
}

export function Preloader({ isVisible, progress, message }: PreloaderProps) {
  const [currentMessage, setCurrentMessage] = useState(SIMCITY_MESSAGES[0]);
  const [memValue, setMemValue] = useState(1024);

  useEffect(() => {
    setMemValue(Math.floor(Math.random() * 4000 + 1000));
  }, []);

  useEffect(() => {
    if (!isVisible) return;
    if (message) {
      setCurrentMessage(message);
      return;
    }
    const interval = setInterval(() => {
      setCurrentMessage(SIMCITY_MESSAGES[Math.floor(Math.random() * SIMCITY_MESSAGES.length)]);
      setMemValue(Math.floor(Math.random() * 4000 + 1000)); // Fluctuating memory usage
    }, 2000);
    return () => clearInterval(interval);
  }, [isVisible, message]);

  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/95 text-green-500 font-mono">
      <div className="w-full max-w-lg p-8 border-4 border-green-500 bg-black shadow-[0_0_30px_rgba(34,197,94,0.3)]">
        <h2 className="text-3xl mb-6 text-center uppercase tracking-widest font-bold">Agora OS v2.0</h2>
        
        <div className="h-12 flex items-center justify-center mb-8 border border-green-500/50 bg-green-950/30 px-4">
          <p className="text-sm md:text-base animate-pulse text-center">{currentMessage}</p>
        </div>
        
        {progress !== undefined && (
          <div className="w-full h-6 border-2 border-green-500 p-1 bg-black">
            <div 
              className="h-full bg-green-500 transition-all duration-300 ease-out relative overflow-hidden"
              style={{ width: `${progress}%` }}
            >
              <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(0,0,0,0.2)_50%,transparent_75%,transparent_100%)] bg-[length:20px_20px] animate-[stripes_1s_linear_infinite]" />
            </div>
          </div>
        )}
        
        <div className="mt-4 flex justify-between text-xs text-green-500/70">
          <span>SYSTEM: ONLINE</span>
          <span>MEM: {memValue}MB</span>
        </div>
      </div>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes stripes {
          from { background-position: 20px 0; }
          to { background-position: 0 0; }
        }
      `}} />
    </div>
  );
}
