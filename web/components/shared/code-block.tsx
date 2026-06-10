"use client";

import { useState, useEffect } from "react";
import { Check, Copy } from "lucide-react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import typescript from "highlight.js/lib/languages/typescript";
import "highlight.js/styles/github-dark-dimmed.css";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// 只注册我们用的语言, 减小 bundle
hljs.registerLanguage("python", python);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("shell", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("ts", typescript);

interface CodeBlockProps {
  code: string;
  lang?: string;
  filename?: string;
  className?: string;
}

export function CodeBlock({ code, lang = "python", filename, className }: CodeBlockProps) {
  const [html, setHtml] = useState<string>(`<pre><code>${escapeHtml(code)}</code></pre>`);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    try {
      const result = hljs.highlight(code, {
        language: hljs.getLanguage(lang) ? lang : "plaintext",
        ignoreIllegals: true,
      });
      setHtml(`<pre><code class="hljs">${result.value}</code></pre>`);
    } catch {
      setHtml(`<pre><code>${escapeHtml(code)}</code></pre>`);
    }
  }, [code, lang]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard 不可用时静默 */
    }
  };

  return (
    <div
      className={cn(
        "relative rounded-lg border border-zinc-700 bg-[#22272e] overflow-hidden",
        className
      )}
    >
      {filename && (
        <div className="flex items-center justify-between border-b border-zinc-700/50 bg-[#1c2128] px-4 py-2">
          <span className="text-xs font-mono text-zinc-400">{filename}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onCopy}
            className="h-7 gap-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" /> 已复制
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" /> 复制
              </>
            )}
          </Button>
        </div>
      )}
      <div
        className="overflow-x-auto text-[13px] [&_pre]:!bg-transparent [&_pre]:p-4 [&_pre]:!m-0 [&_code]:!bg-transparent"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {!filename && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onCopy}
          className="absolute right-2 top-2 h-7 gap-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" /> 已复制
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" /> 复制
            </>
          )}
        </Button>
      )}
    </div>
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
