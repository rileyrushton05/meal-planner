import { useState } from "react";

import type { GroceryLine } from "../api/types";
import { formatDate } from "../lib/dates";
import { Button, Card, Empty, SectionTitle } from "./ui";

interface Props {
  weekStart: string;
  lines: GroceryLine[] | null;
  busy: boolean;
  onGenerate: () => void;
}

export function GroceryTab({ weekStart, lines, busy, onGenerate }: Props) {
  const [copied, setCopied] = useState(false);

  const asText = (lines ?? [])
    .map((line) => `- ${line.name}: ${line.display}`)
    .join("\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked; the textarea below is the fallback.
      setCopied(false);
    }
  };

  const download = () => {
    const blob = new Blob([asText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `grocery-list-${weekStart}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle>Grocery List — Week of {formatDate(weekStart)}</SectionTitle>
        <Button disabled={busy} onClick={onGenerate}>
          {lines ? "Regenerate" : "Generate Grocery List"}
        </Button>
      </div>

      {lines === null ? (
        <Empty>Generate a list to see everything you need for this week.</Empty>
      ) : lines.length === 0 ? (
        <Empty>No meals assigned this week yet.</Empty>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            {lines.map((line) => (
              <div
                key={`${line.name}-${line.unit}`}
                className="flex items-center justify-between rounded-xl border border-edge bg-surface px-4 py-3"
              >
                <span>{line.name}</span>
                <span className="font-bold text-accent tabular-nums">
                  {line.display}
                </span>
              </div>
            ))}
          </div>

          <Card className="flex flex-col gap-3">
            <div className="flex gap-2">
              <Button variant="secondary" onClick={copy}>
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button variant="secondary" onClick={download}>
                Download .txt
              </Button>
            </div>
            <textarea
              readOnly
              value={asText}
              rows={Math.min(lines.length + 1, 12)}
              className="w-full rounded-lg border border-edge bg-canvas p-3 font-mono text-xs text-ink"
            />
          </Card>
        </>
      )}
    </div>
  );
}
